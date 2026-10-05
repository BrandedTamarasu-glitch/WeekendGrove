"""Opt-in, bounded public-calendar discovery. No credentials or general web crawler."""
import hashlib
import html
import http.client
import ipaddress
import json
import math
import re
import queue
import socket
import ssl
import threading
import time
import uuid
from datetime import date, datetime, time as clock_time, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULTS = dict(zip='', local_miles=30, day_trip_miles=100, include_day_trips=False,
                timezone='America/Los_Angeles', weekday=3, time='08:00', consent=False, enabled=False)
PREFERENCE_KEYS = set(DEFAULTS) - {'consent', 'enabled'}
SOURCE_ID = 'stanwood-events'
SOURCE_NAME = 'City of Stanwood community events'
SOURCE_URL = 'https://stanwoodwa.org/Calendar.aspx'
FEED_URL = 'https://stanwoodwa.org/common/modules/iCalendar/iCalendar.aspx?catID=27&feed=calendar'
# Source coverage is regional; this is not a user's location or a search default.
VENUE_ZIP = '98292'
MAX_CANDIDATES = 1000


def utcnow():
    return datetime.now(timezone.utc)


def stamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('Invalid discovery timestamp.')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Discovery timestamps need a timezone.')
    return parsed


def clean_settings(data):
    if not isinstance(data, dict) or set(data) != set(DEFAULTS):
        raise ValueError('Discovery settings are missing or unsupported.')
    if not isinstance(data['zip'], str) or (data['zip'] and not re.fullmatch(r'[0-9]{5}', data['zip'])):
        raise ValueError('Enter a five-digit US ZIP code.')
    for key in ('local_miles', 'day_trip_miles'):
        if type(data[key]) is not int or not 1 <= data[key] <= 150:
            raise ValueError('Distances must be whole miles from 1 to 150.')
    if data['day_trip_miles'] < data['local_miles']:
        raise ValueError('Day-trip distance must be at least the local distance.')
    for key in ('enabled', 'consent', 'include_day_trips'):
        if type(data[key]) is not bool:
            raise ValueError('Discovery switches must be true or false.')
    if type(data['weekday']) is not int or not 0 <= data['weekday'] <= 6:
        raise ValueError('Choose a weekly refresh day.')
    if not isinstance(data['time'], str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', data['time']):
        raise ValueError('Choose a refresh time in HH:MM format.')
    try:
        if not isinstance(data['timezone'], str) or len(data['timezone']) > 80:
            raise ValueError('Choose an IANA timezone.')
        ZoneInfo(data['timezone'])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Choose a supported IANA timezone, such as America/Los_Angeles.') from None
    if data['enabled'] and (not data['zip'] or not data['consent']):
        raise ValueError('Set a ZIP and allow the disclosed public lookups before enabling weekly refresh.')
    return dict(data)


def next_run(settings, now=None):
    now = now or utcnow()
    zone = ZoneInfo(settings['timezone'])
    local = now.astimezone(zone)
    hour, minute = map(int, settings['time'].split(':'))
    day = local.date() + timedelta(days=(settings['weekday']-local.weekday()) % 7)
    candidate = datetime.combine(day, clock_time(hour, minute), zone)
    if candidate <= local:
        candidate += timedelta(days=7)
    # Spring gaps normalize forward; fall folds choose the first occurrence once.
    return candidate.astimezone(timezone.utc).isoformat()


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS discovery_candidates (
      key TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL,
      idea_uid TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS discovery_job (
      id INTEGER PRIMARY KEY CHECK(id=1), token TEXT, lease_until TEXT,
      last_started TEXT, last_finished TEXT, next_run TEXT, outcome TEXT NOT NULL DEFAULT 'Never refreshed',
      added INTEGER NOT NULL DEFAULT 0, skipped INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS discovery_zip_cache (zip TEXT PRIMARY KEY, latitude REAL, longitude REAL, fetched TEXT);
    INSERT OR IGNORE INTO discovery_job(id) VALUES (1);
    ''')
    db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)', ('discovery', json.dumps(DEFAULTS)))


def settings_from(db):
    return json.loads(db.execute("SELECT value FROM settings WHERE key='discovery'").fetchone()['value'])


def configure(db, data):
    settings = clean_settings(data)
    db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(settings), 'discovery'))
    # Invalidate pending work, including when consent is revoked.
    db.execute('UPDATE discovery_job SET token=NULL,lease_until=NULL,next_run=?,outcome=? WHERE id=1',
               (next_run(settings) if settings['enabled'] else None, 'Settings saved; refresh has not run with these settings'))
    return settings


def clean_metadata(value):
    if value == {}:
        return {}
    fields = {'source_id','source_name','source_url','fetched_at','latitude','longitude','distance_miles','range',
              'start_date','end_date','timezone','time_label','distance_basis','starts_at','ends_at'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('Invalid discovery provenance.')
    for key, limit in [('source_id',80),('source_name',120),('source_url',500),('time_label',150),('distance_basis',100)]:
        if not isinstance(value[key], str) or not value[key] or len(value[key]) > limit:
            raise ValueError('Invalid discovery source text.')
    link = urlsplit(value['source_url'])
    if link.scheme != 'https' or not link.hostname or link.username or link.password or link.port not in (None,443):
        raise ValueError('Source links must use public HTTPS URLs.')
    if value['source_id'] != SOURCE_ID or value['source_name'] != SOURCE_NAME or not re.fullmatch(re.escape(SOURCE_URL)+r'\?EID=[0-9]{1,12}',value['source_url']):
        raise ValueError('Unknown discovery source.')
    stamp(value['fetched_at'])
    for key, low, high in [('latitude',-90,90),('longitude',-180,180),('distance_miles',0,30000)]:
        if type(value[key]) not in (int,float) or not math.isfinite(value[key]) or not low <= value[key] <= high:
            raise ValueError('Invalid discovery coordinates or distance.')
    if value['range'] not in ('Local','Day trip'):
        raise ValueError('Invalid discovery distance label.')
    try:
        ZoneInfo(value['timezone'])
        start, end = date.fromisoformat(value['start_date']), date.fromisoformat(value['end_date'])
        if start > end or (end-start).days > 31 or start.isoformat() != value['start_date'] or end.isoformat() != value['end_date']:
            raise ValueError()
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        raise ValueError('Invalid discovery event dates or timezone.') from None
    if (value['starts_at'] is None) != (value['ends_at'] is None):
        raise ValueError('Timed events need both start and end timestamps.')
    if value['starts_at'] is not None:
        start_at,end_at=stamp(value['starts_at']),stamp(value['ends_at'])
        if end_at<=start_at or start_at.astimezone(ZoneInfo(value['timezone'])).date()!=start or (end_at-timedelta(microseconds=1)).astimezone(ZoneInfo(value['timezone'])).date()!=end:
            raise ValueError('Invalid event time range.')
    return dict(value)


def idea_row(row):
    value = dict(row)
    value['metadata'] = json.loads(value.get('metadata') or '{}') if isinstance(value.get('metadata', '{}'), str) else value.get('metadata', {})
    return value


def weekend(value):
    if value is None:
        return None  # Legacy undated plans can still contain evergreen ideas.
    if not isinstance(value, str):
        raise ValueError('Choose a Saturday for the weekend date.')
    day = date.fromisoformat(value)
    if day.isoformat() != value or day.weekday() != 5:
        raise ValueError('Choose a Saturday for the weekend date.')
    return day


def eligible(idea, day, limits, now=None, historical=False):
    meta = idea.get('metadata') or {}
    if not meta:
        return True
    start = weekend(limits.get('weekend_date'))
    if start is None:
        return False
    actual = start + timedelta(days=0 if day == 'Saturday' else 1)
    today = (now or utcnow()).astimezone(ZoneInfo(meta['timezone'])).date()
    if not historical and meta.get('ends_at') and stamp(meta['ends_at']) <= (now or utcnow()):
        return False
    return (historical or actual >= today) and date.fromisoformat(meta['start_date']) <= actual <= date.fromisoformat(meta['end_date'])


def expired(payload, now=None):
    m = payload['metadata']
    if m.get('ends_at') and stamp(m['ends_at']) <= (now or utcnow()):
        return True
    return date.fromisoformat(m['end_date']) < (now or utcnow()).astimezone(ZoneInfo(m['timezone'])).date()


def exported(db):
    return dict(preferences={k:v for k,v in settings_from(db).items() if k in PREFERENCE_KEYS},
                candidates=[dict(r, payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM discovery_candidates ORDER BY key')])


def validate_export(value, clean_idea):
    if not isinstance(value, dict) or set(value) != {'preferences','candidates'} or not isinstance(value['preferences'],dict) or set(value['preferences']) != PREFERENCE_KEYS:
        raise ValueError('Invalid discovery backup.')
    clean_settings(dict(value['preferences'], consent=False, enabled=False))
    rows = value['candidates']
    if not isinstance(rows,list) or len(rows)>MAX_CANDIDATES:
        raise ValueError('Too many discovery records in backup.')
    keys=set()
    for row in rows:
        if not isinstance(row,dict) or set(row) != {'key','payload','status','idea_uid','first_seen','last_seen'}:
            raise ValueError('Invalid discovery backup record.')
        if not isinstance(row['key'],str) or not re.fullmatch(r'[0-9a-f]{64}',row['key']) or row['key'] in keys:
            raise ValueError('Invalid or duplicate discovery identity.')
        keys.add(row['key'])
        if row['status'] not in ('pending','saved','dismissed'):
            raise ValueError('Invalid discovery decision.')
        if row['idea_uid'] is not None and (not isinstance(row['idea_uid'],str) or str(uuid.UUID(row['idea_uid'])) != row['idea_uid']):
            raise ValueError('Invalid saved discovery idea identifier.')
        if (row['status']=='saved') != (row['idea_uid'] is not None):
            raise ValueError('Saved discovery records require an idea identifier.')
        stamp(row['first_seen']); stamp(row['last_seen'])
        p=row['payload']
        if not isinstance(p,dict) or set(p) != {'title','category','duration','cost','energy','location','metadata'}:
            raise ValueError('Invalid discovery suggestion.')
        if clean_idea(p) != {k:v for k,v in p.items() if k!='metadata'}:
            raise ValueError('Noncanonical discovery suggestion.')
        if not clean_metadata(p['metadata']):
            raise ValueError('Discovery suggestions require provenance.')
    return value


def restore(db, value, apply_preferences=False):
    if value is None:
        return
    for r in value['candidates']:
        db.execute('INSERT OR IGNORE INTO discovery_candidates VALUES (?,?,?,?,?,?)',
                   (r['key'],json.dumps(r['payload']),r['status'],r['idea_uid'],r['first_seen'],r['last_seen']))
    if apply_preferences:
        configure(db, dict(value['preferences'], consent=False, enabled=False))


def view(db):
    settings = settings_from(db)
    rows=[]
    for r in db.execute('SELECT * FROM discovery_candidates ORDER BY last_seen DESC,key'):
        row=dict(r);row['payload']=json.loads(row['payload']);row['expired']=expired(row['payload']);rows.append(row)
    job=dict(db.execute('SELECT * FROM discovery_job WHERE id=1').fetchone())
    job['running']=bool(job['token'] and job['lease_until'] and stamp(job['lease_until']) > utcnow())
    job.pop('token');job.pop('lease_until');job.pop('id')
    return dict(settings=settings,candidates=rows,job=job,
                coverage='Community events listed by the City of Stanwood only. Other regions, restaurants and places are not covered in this version. Empty results do not mean there is nothing nearby.')


def decide(db, key, action):
    if action not in ('save','dismiss') or not isinstance(key,str):
        raise ValueError('Choose Save or Dismiss.')
    db.execute('BEGIN IMMEDIATE')
    row=db.execute('SELECT * FROM discovery_candidates WHERE key=?',(key,)).fetchone()
    if not row: raise ValueError('Suggestion no longer exists.')
    if row['status'] != 'pending': return dict(status=row['status'])
    p=json.loads(row['payload'])
    if action=='save':
        if expired(p): raise ValueError('This event has ended. It cannot be added to future plans.')
        uid=str(uuid.uuid4())
        db.execute('INSERT INTO ideas(uid,title,category,duration,cost,location,energy,metadata) VALUES (:uid,:title,:category,:duration,:cost,:location,:energy,:metadata)',
                   dict(p,uid=uid,metadata=json.dumps(p['metadata'])))
        db.execute("UPDATE discovery_candidates SET status='saved',idea_uid=? WHERE key=?",(uid,key))
    else:
        db.execute("UPDATE discovery_candidates SET status='dismissed' WHERE key=?",(key,))
    return dict(status='saved' if action=='save' else 'dismissed')


class FetchError(ValueError):
    pass


def fetch(url, deadline=None):
    """Only built-in endpoints; resolve once, reject private IPs, pin TLS socket, no redirects."""
    part=urlsplit(url)
    allowed = ((part.hostname=='api.zippopotam.us' and re.fullmatch(r'/us/[0-9]{5}',part.path) and not part.query)
               or url==FEED_URL)
    if not allowed or part.scheme!='https' or part.username or part.password or part.port not in (None,443) or part.fragment:
        raise FetchError('The requested discovery endpoint is not allowed.')
    timeout=min(12, max(0, (deadline or time.monotonic()+12)-time.monotonic()))
    if timeout < 1: raise FetchError('Refresh reached its time limit.')
    results=queue.Queue(maxsize=1)
    def resolve():
        try:results.put(socket.getaddrinfo(part.hostname,443,type=socket.SOCK_STREAM))
        except OSError:results.put(None)
    threading.Thread(target=resolve,daemon=True).start()
    try:addresses=results.get(timeout=min(3,timeout))
    except queue.Empty:raise FetchError('Provider DNS lookup timed out.') from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise FetchError('Provider resolved to a non-public network address.')
    conn=http.client.HTTPSConnection(part.hostname, timeout=timeout)
    try:
        raw=socket.create_connection(addresses[0][4][:2],timeout=timeout)
        try: conn.sock=ssl.create_default_context().wrap_socket(raw,server_hostname=part.hostname)
        except BaseException:
            raw.close();raise
        conn.request('GET',part.path+('?' + part.query if part.query else ''),headers={'User-Agent':'WeekendGrove/1.0 (+https://github.com/BrandedTamarasu-glitch/WeekendGrove)','Accept':'application/json, text/calendar','Accept-Encoding':'identity'})
        response=conn.getresponse()
        if response.status != 200:
            raise FetchError(f'Provider returned HTTP {response.status}; no automatic retry this run.')
        chunks=[];size=0
        while True:
            if deadline and time.monotonic() > deadline: raise FetchError('Refresh reached its time limit.')
            block=response.read1(16384)
            if not block: break
            size+=len(block)
            if size>1024*1024:raise FetchError('Provider response exceeded 1 MiB.')
            chunks.append(block)
        return b''.join(chunks).decode('utf-8-sig')
    except (OSError, http.client.HTTPException, UnicodeError) as e:
        raise FetchError('Provider unavailable; existing suggestions are kept. Try again later.') from e
    finally:
        conn.close()


def coordinates(zip_code, db, getter=fetch, deadline=None):
    row=db.execute('SELECT * FROM discovery_zip_cache WHERE zip=?',(zip_code,)).fetchone()
    if row and utcnow()-stamp(row['fetched']) < timedelta(days=30): return row['latitude'],row['longitude']
    data=json.loads(getter('https://api.zippopotam.us/us/'+zip_code,deadline))
    places=data.get('places',[])
    if not places:raise FetchError('ZIP lookup returned no location. Check the ZIP code.')
    lat,lon=float(places[0]['latitude']),float(places[0]['longitude'])
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
        raise FetchError('ZIP lookup returned invalid coordinates.')
    # Only the lookup cache is written here; network calls never hold a write transaction.
    db.execute('INSERT OR REPLACE INTO discovery_zip_cache VALUES (?,?,?,?)',(zip_code,lat,lon,utcnow().isoformat()))
    db.commit()
    return lat,lon


def distance(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,(*a,*b))
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 3958.7613*2*math.asin(min(1,math.sqrt(h)))


def plain(value,limit):
    value=re.sub(r'<[^>]*>',' ',value)
    value=value.replace('\\n',' ').replace('\\N',' ').replace('\\,',',').replace('\\;',';').replace('\\\\','\\')
    return re.sub(r'\s+',' ',html.unescape(value)).strip()[:limit]


def calendar_records(text, origin, venue, settings, now=None):
    now=now or utcnow()
    today=now.astimezone(ZoneInfo('America/Los_Angeles')).date()
    miles=distance(origin,venue)
    max_miles=settings['day_trip_miles'] if settings['include_day_trips'] else settings['local_miles']
    if miles>max_miles:return [],0
    # Unfold RFC 5545 continuations. This provider has simple individual occurrences.
    text=re.sub(r'\r?\n[ \t]','',text)
    if not text.startswith('BEGIN:VCALENDAR') or 'END:VCALENDAR' not in text:raise FetchError('Provider did not return a complete calendar.')
    records=[];skipped=0
    blocks=re.findall(r'BEGIN:VEVENT\r?\n(.*?)END:VEVENT',text,re.S)
    if len(blocks)>500:raise FetchError('Calendar exceeded the event limit.')
    for block in blocks:
        try:
            fields={}
            for line in block.splitlines():
                if ':' not in line:continue
                key,value=line.split(':',1);base=key.split(';')[0]
                if base in fields and base in ('UID','DTSTART','DTEND','SUMMARY','LOCATION'):raise ValueError()
                fields[base]=(key,value)
            if any(k in fields for k in ('RRULE','RDATE','EXDATE','RECURRENCE-ID')) or fields.get('STATUS',('', ''))[1]=='CANCELLED':raise ValueError()
            uid=fields['UID'][1]
            if not re.fullmatch(r'[0-9]{1,12}',uid):raise ValueError()
            title=plain(fields['SUMMARY'][1],120)
            location=plain(fields['LOCATION'][1],200)
            # Only accurately locatable venues; unknown locations are not assigned to city center.
            if not title or not re.search(r'\b98292\b',location):raise ValueError()
            if re.search(r'(?:\b(?:21|18)\s*\+|\badults? only\b)',block,re.I):raise ValueError()
            def parse_dt(field):
                key,value=fields[field]
                if 'VALUE=DATE' in key:
                    return datetime.strptime(value,'%Y%m%d').date(), None
                if ';' in key and key != field+';TZID=America/Los_Angeles':raise ValueError()
                dt=datetime.strptime(value,'%Y%m%dT%H%M%SZ' if value.endswith('Z') else '%Y%m%dT%H%M%S')
                dt=dt.replace(tzinfo=timezone.utc if value.endswith('Z') else ZoneInfo('America/Los_Angeles')).astimezone(ZoneInfo('America/Los_Angeles'))
                return dt.date(),dt
            start,start_dt=parse_dt('DTSTART');end,end_dt=parse_dt('DTEND') if 'DTEND' in fields else (start,None)
            if start_dt is None and end>start:end-=timedelta(days=1)  # iCalendar all-day end is exclusive.
            if start_dt and not end_dt:raise ValueError()
            if end_dt and end_dt.time()==clock_time(0) and end>start:end-=timedelta(days=1)
            if end<start or (end-start).days>31:raise ValueError()
            if end<today or start>today+timedelta(days=90):continue
            if start_dt and end_dt and end_dt<=now:continue
            time_label='All day · confirm on source' if not start_dt else start_dt.strftime('%H:%M')+(('–'+end_dt.strftime('%H:%M')) if end_dt else '')+' America/Los_Angeles'
            metadata=dict(source_id=SOURCE_ID,source_name=SOURCE_NAME,source_url=SOURCE_URL+'?EID='+uid,fetched_at=now.isoformat(),
                          latitude=venue[0],longitude=venue[1],distance_miles=round(miles,1),range='Local' if miles<=settings['local_miles'] else 'Day trip',
                          start_date=start.isoformat(),end_date=end.isoformat(),timezone='America/Los_Angeles',time_label=time_label,distance_basis='Approximate ZIP-center to venue ZIP-center distance',starts_at=start_dt.isoformat() if start_dt else None,ends_at=end_dt.isoformat() if end_dt else None)
            clean_metadata(metadata)
            payload=dict(title=title,category='Activities',duration=None,cost=None,location=location,energy=None,metadata=metadata)
            # Provider UID survives rescheduling; a dismissed event must not return with a new date.
            key=hashlib.sha256((SOURCE_ID+':'+uid).encode()).hexdigest()
            records.append((key,payload))
        except (KeyError, ValueError, TypeError):skipped+=1
    return records,skipped


def apply_records(db,records,now):
    count=db.execute('SELECT COUNT(*) FROM discovery_candidates').fetchone()[0]
    added=0
    for key,payload in records:
        old=db.execute('SELECT status FROM discovery_candidates WHERE key=?',(key,)).fetchone()
        if old:
            # Refresh pending source facts only. Saved user ideas and decisions remain untouched.
            if old['status']=='pending':db.execute('UPDATE discovery_candidates SET payload=?,last_seen=? WHERE key=?',(json.dumps(payload),now,key))
        elif count<MAX_CANDIDATES:
            db.execute("INSERT INTO discovery_candidates VALUES (?,?,'pending',NULL,?,?)",(key,json.dumps(payload),now,now));added+=1;count+=1
    return added


def claim(db, manual=False, now=None):
    now=now or utcnow();db.execute('BEGIN IMMEDIATE')
    settings=settings_from(db)
    if not settings['zip'] or not settings['consent']:
        if manual:raise ValueError('Save a ZIP and allow the disclosed public lookups before refreshing.')
        return None
    job=dict(db.execute('SELECT * FROM discovery_job WHERE id=1').fetchone())
    if job['token'] and job['lease_until'] and stamp(job['lease_until'])>now:
        if manual:raise ValueError('A refresh is already running.')
        return None
    if not manual and (not settings['enabled'] or not job['next_run'] or stamp(job['next_run'])>now):return None
    if manual and job['last_started'] and now-stamp(job['last_started'])<timedelta(minutes=5):
        raise ValueError('Please wait five minutes between refreshes.')
    token=str(uuid.uuid4())
    db.execute('UPDATE discovery_job SET token=?,lease_until=?,last_started=?,next_run=?,outcome=? WHERE id=1',
               (token,(now+timedelta(minutes=3)).isoformat(),now.isoformat(),next_run(settings,now) if settings['enabled'] else None,'Refreshing public sources'))
    return token,settings


def perform(connect,token,settings,getter=fetch):
    outcome='';added=skipped=0
    try:
        deadline=time.monotonic()+60
        def consent_checked_getter(url,limit):
            with connect() as check:
                if check.execute('SELECT token FROM discovery_job WHERE id=1').fetchone()['token'] != token or settings_from(check)!=settings:
                    raise FetchError('Refresh stopped because settings or permission changed.')
            return getter(url,limit)
        with connect() as db:
            origin=coordinates(settings['zip'],db,consent_checked_getter,deadline)
            venue=coordinates(VENUE_ZIP,db,consent_checked_getter,deadline)
        radius=settings['day_trip_miles'] if settings['include_day_trips'] else settings['local_miles']
        if distance(origin,venue)>radius:
            records=[];outcome='No supported event source within this range. Restaurants and places are not covered.'
        else:
            text=consent_checked_getter(FEED_URL,deadline)
            records,skipped=calendar_records(text,origin,venue,settings)
            outcome='City calendar checked. Suitability, prices and availability need confirmation on the source.'
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT token FROM discovery_job WHERE id=1').fetchone()
            if row['token']!=token or settings_from(db)!=settings:return
            added=apply_records(db,records,utcnow().isoformat())
            if db.execute('SELECT COUNT(*) FROM discovery_candidates').fetchone()[0]>=MAX_CANDIDATES:
                outcome+=' Inbox history limit reached; new entries were not added beyond the limit.'
    except Exception as error:
        outcome=str(error) if isinstance(error,FetchError) else 'Public lookup failed; existing ideas and suggestions are unchanged.'
    with connect() as db:
        db.execute('UPDATE discovery_job SET token=NULL,lease_until=NULL,last_finished=?,outcome=?,added=?,skipped=? WHERE id=1 AND token=?',
                   (utcnow().isoformat(),outcome,added,skipped,token))


def launch(connect,manual=False):
    with connect() as db:job=claim(db,manual)
    if job:
        threading.Thread(target=perform,args=(connect,*job),daemon=True).start()
    return bool(job)


def start_scheduler(connect):
    stop=threading.Event()
    def run():
        while not stop.wait(30):
            try:launch(connect)
            except Exception:pass  # Next tick can retry a storage failure; no network retry storm.
    threading.Thread(target=run,daemon=True).start()
    return stop
