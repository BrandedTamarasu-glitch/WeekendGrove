"""Small opt-in provider adapters. Bounded normalized facts; no raw-response storage."""
import hashlib
import json
import math
import re
import time
from datetime import date, timedelta
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

import discovery as d

PLACE_GROUPS = (('Restaurants', 'catering.restaurant'),
                ('Places', 'entertainment.museum,entertainment.zoo,leisure.park'))


def request_json(base, params, getter, deadline):
    if time.monotonic() >= deadline: raise d.FetchError('Refresh reached its time limit.')
    value=json.loads(getter(base+'?'+urlencode(params),deadline))
    if not isinstance(value,dict): raise d.FetchError('Provider returned an unsupported response.')
    return value


def point(lat,lon):
    lat,lon=float(lat),float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:raise ValueError()
    return lat,lon


def radius(settings):
    return settings['day_trip_miles'] if settings['include_day_trips'] else settings['local_miles']


def metadata(source,name,url,venue,origin,settings,now):
    miles=d.distance(origin,venue)
    if miles>radius(settings): raise ValueError('Outside requested range.')
    return dict(source_id=source,source_name=name,source_url=url,fetched_at=now.isoformat(),latitude=venue[0],longitude=venue[1],
                distance_miles=round(miles,1),range='Local' if miles<=settings['local_miles'] else 'Day trip',
                start_date=None,end_date=None,starts_at=None,ends_at=None,timezone=settings['timezone'],
                time_label='Opening hours unconfirmed',distance_basis='Approximate ZIP-center to venue straight-line distance')


def geoapify_records(data,category,origin,settings,now=None):
    now=now or d.utcnow();records=[];skipped=0
    features=data.get('features')
    if not isinstance(features,list) or len(features)>20: raise d.FetchError('Places response exceeded its supported bounds.')
    for feature in features:
        try:
            p=feature['properties'];uid=p['place_id']
            if not isinstance(uid,str) or not 1<=len(uid)<=512:raise ValueError()
            name=d.plain(p['name'],120);address=d.plain(p['formatted'],200)
            if not name or not address:raise ValueError()
            venue=point(p['lat'],p['lon'])
            cats=p.get('categories',[])
            if not isinstance(cats,list) or not any(isinstance(c,str) and (c=='catering.restaurant' or c.startswith('catering.restaurant.')) for c in cats) and category=='Restaurants':raise ValueError()
            if category=='Places' and not any(isinstance(c,str) and c in ('entertainment.museum','entertainment.zoo','leisure.park') for c in cats):raise ValueError()
            m=metadata('geoapify','Geoapify / OpenStreetMap',f'https://www.openstreetmap.org/?mlat={venue[0]}&mlon={venue[1]}',venue,origin,settings,now)
            d.clean_metadata(m)
            records.append((hashlib.sha256(('geoapify:'+uid).encode()).hexdigest(),dict(title=name,category=category,duration=None,cost=None,energy=None,location=address,metadata=m)))
        except (KeyError,ValueError,TypeError,AttributeError):skipped+=1
    return records,skipped


def destination(origin, miles, bearing):
    """Great-circle sampling point, including polar/dateline-safe longitude."""
    lat,lon=map(math.radians,origin);angle=miles/3958.7613;bearing=math.radians(bearing)
    result=math.asin(math.sin(lat)*math.cos(angle)+math.cos(lat)*math.sin(angle)*math.cos(bearing))
    longitude=lon+math.atan2(math.sin(bearing)*math.sin(angle)*math.cos(lat),math.cos(angle)-math.sin(lat)*math.sin(result))
    return math.degrees(result),(math.degrees(longitude)+180)%360-180


def geoapify_lookup(settings,key,getter,deadline,now=None):
    # https://apidocs.geoapify.com/docs/places/: circle bounds, proximity ranking,
    # limit/offset paging. Maximum 5 requests local-only; 13 with day trips:
    # ZIP + 2 groups * (up to 2 local pages + 4 directional outer samples).
    # Samples are deliberately incomplete, never exhaustive area enumeration.
    geo=request_json('https://api.geoapify.com/v1/geocode/search',dict(text=settings['zip'],type='postcode',filter='countrycode:us',format='json',limit=1,apiKey=key),getter,deadline)
    results=geo.get('results',[])
    if not isinstance(results,list) or len(results)!=1:raise d.FetchError('ZIP lookup returned no unique supported location.')
    p=results[0]
    if p.get('country_code')!='us' or p.get('postcode')!=settings['zip']:raise d.FetchError('ZIP lookup did not match the requested US ZIP.')
    origin=point(p['lat'],p['lon']);records=[];skipped=0
    trips=settings['include_day_trips'] and settings['day_trip_miles']>settings['local_miles']
    for category,categories in PLACE_GROUPS:
        local=[];outer=[];seen=set()
        def collect(bias,miles,offset=0,day_trip=False):
            nonlocal skipped
            time.sleep(0.51)  # No retries/detail calls; the shared deadline still applies.
            data=request_json('https://api.geoapify.com/v2/places',dict(categories=categories,filter=f'circle:{origin[1]},{origin[0]},{round(miles*1609.344)}',bias=f'proximity:{bias[1]},{bias[0]}',limit=20,offset=offset,apiKey=key),getter,deadline)
            new,missed=geoapify_records(data,category,origin,settings,now);skipped+=missed
            for identity,payload in new:
                distance=d.distance(origin,(payload['metadata']['latitude'],payload['metadata']['longitude']))
                if identity in seen or distance>miles or (day_trip and distance<=settings['local_miles']):continue
                if any(d.same_venue(payload,other) for _,other in local+outer):continue
                seen.add(identity);(outer if day_trip else local).append((identity,payload))
            return len(data['features'])
        if collect(origin,settings['local_miles'])==20:
            collect(origin,settings['local_miles'],20)
        if trips:
            middle=(settings['local_miles']+settings['day_trip_miles'])/2
            # Round-robin one result per direction before taking a second: dense
            # neighborhoods in the first quadrant cannot consume the whole quota.
            directional=[]
            for bearing in (0,90,180,270):
                start=len(outer)
                collect(destination(origin,middle,bearing),settings['day_trip_miles'],day_trip=True)
                directional.append(outer[start:])
            outer=[bucket[index] for index in range(20) for bucket in directional if len(bucket)>index]
        # Reserve half the 20 slots for each band when both have results; fill
        # unused capacity from the other. Never expand a user's radius.
        selected=local[:10]+outer[:10] if trips else local[:20]
        chosen={key for key,_ in selected}
        selected.extend(item for item in local+outer if item[0] not in chosen)
        records.extend(selected[:20])
    return origin,records,skipped


def geohash(lat,lon,precision=8):
    # Ticketmaster's geoPoint parameter is a geohash, not a lat,lon string.
    ranges=[[-180.,180.],[-90.,90.]];coords=[lon,lat];alphabet='0123456789bcdefghjkmnpqrstuvwxyz';out='';value=bits=axis=0
    while len(out)<precision:
        lo,hi=ranges[axis];mid=(lo+hi)/2;bit=int(coords[axis]>=mid)
        ranges[axis]=[mid,hi] if bit else [lo,mid];value=(value<<1)|bit;bits+=1;axis=1-axis
        if bits==5:out+=alphabet[value];value=bits=0
    return out


def ticketmaster_records(data,origin,settings,now=None):
    now=now or d.utcnow();records=[];skipped=0
    events=data.get('_embedded',{}).get('events',[])
    if not isinstance(events,list) or len(events)>100:raise d.FetchError('Events response exceeded its supported bounds.')
    for event in events:
        try:
            uid=event['id'];dates=event['dates'];start=dates['start']
            # Unknown family classification, cancellations, postponements and reschedules are omitted.
            if not any(isinstance(c,dict) and c.get('family') is True for c in event.get('classifications',[])) or dates.get('status',{}).get('code')!='onsale':raise ValueError()
            if start.get('dateTBA') or start.get('dateTBD'):raise ValueError()
            if not isinstance(uid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',uid):raise ValueError()
            link=urlsplit(event['url'])
            if link.scheme!='https' or link.hostname!='www.ticketmaster.com' or link.username or link.password or link.port not in (None,443):raise ValueError()
            url='https://www.ticketmaster.com'+link.path
            venue=event['_embedded']['venues'][0];location=venue['location'];coords=point(location['latitude'],location['longitude'])
            zone=dates.get('timezone') or venue.get('timezone')
            if not isinstance(zone,str):raise ValueError()
            ZoneInfo(zone);day=date.fromisoformat(start['localDate'])
            if day<now.astimezone(ZoneInfo(zone)).date() or day>now.date()+timedelta(days=90):continue
            title=d.plain(event['name'],120)
            if not title or re.search(r'\b(?:18|21)\s*\+|adults? only',title,re.I):raise ValueError()
            address=d.plain(' · '.join(filter(None,[venue.get('name'),venue.get('address',{}).get('line1'),venue.get('city',{}).get('name')])),200)
            if not address:raise ValueError()
            m=metadata('ticketmaster','Ticketmaster',url,coords,origin,settings,now)
            m.update(start_date=day.isoformat(),end_date=day.isoformat(),timezone=zone,time_label='Start/end time unconfirmed; check Ticketmaster')
            # Do not invent an end time or duration. The exact local event date restricts planning.
            if start.get('localTime') and not start.get('timeTBA') and re.fullmatch(r'\d{2}:\d{2}:\d{2}',start['localTime']):m['time_label']='Starts '+start['localTime'][:5]+' '+zone+'; end unconfirmed'
            d.clean_metadata(m)
            records.append((hashlib.sha256(('ticketmaster:'+uid).encode()).hexdigest(),dict(title=title,category='Activities',duration=None,cost=None,energy=None,location=address,metadata=m)))
        except (KeyError,ValueError,TypeError,IndexError,AttributeError):skipped+=1
    return records,skipped


def ticketmaster_lookup(settings,origin,key,getter,deadline,now=None):
    now=now or d.utcnow()
    params=dict(apikey=key,geoPoint=geohash(*origin),radius=radius(settings),unit='miles',countryCode='US',includeFamily='only',includeTBA='no',includeTBD='no',includeTest='no',size=100,page=0,sort='date,asc',startDateTime=now.strftime('%Y-%m-%dT%H:%M:%SZ'),endDateTime=(now+timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    return ticketmaster_records(request_json('https://app.ticketmaster.com/discovery/v2/events.json',params,getter,deadline),origin,settings,now)
