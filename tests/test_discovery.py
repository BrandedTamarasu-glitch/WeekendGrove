"""Offline fixtures are generic. No requests to real providers or production databases."""
import copy
import hashlib
import json
import random
import socket
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import test_app
import server
import discovery as d

NOW=datetime(2030,6,1,8,tzinfo=timezone.utc)  # Saturday, before the example event.
SETTINGS=dict(d.DEFAULTS,zip='90210',consent=True)
FEED='''BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:42
DTSTART;TZID=America/Los_Angeles:20300601T100000
DTEND;TZID=America/Los_Angeles:20300601T120000
SUMMARY:Example community picnic
LOCATION:Example Park\\, Public Town 98292
END:VEVENT
END:VCALENDAR
'''


def records(feed=FEED,settings=SETTINGS,origin=(34.09,-118.40),venue=(34.09,-118.40)):
    return d.calendar_records(feed,origin,venue,settings,now=NOW)


class CalendarTests(unittest.TestCase):
    def test_parser_dates_source_and_unknown_estimates(self):
        rows,skipped=records();self.assertEqual((len(rows),skipped),(1,0))
        p=rows[0][1];m=p['metadata']
        self.assertIsNone(p['cost']);self.assertIsNone(p['duration']);self.assertEqual(m['range'],'Local')
        self.assertEqual(m['start_date'],'2030-06-01');self.assertEqual(m['end_date'],'2030-06-01')
        self.assertEqual(m['starts_at'],'2030-06-01T10:00:00-07:00');self.assertTrue(m['source_url'].endswith('EID=42'))
        self.assertEqual(d.clean_metadata(m),m)

    def test_multiday_exclusive_end_unfolding_and_escaping(self):
        feed=FEED.replace('DTSTART;TZID=America/Los_Angeles:20300601T100000','DTSTART;VALUE=DATE:20300601').replace('DTEND;TZID=America/Los_Angeles:20300601T120000','DTEND;VALUE=DATE:20300603').replace('Example community picnic','Example <script>alert</script> &amp;\n picnic')
        p=records(feed)[0][0][1]
        self.assertEqual(p['metadata']['end_date'],'2030-06-02');self.assertIsNone(p['metadata']['ends_at'])
        self.assertNotIn('<script>',p['title']);self.assertIn('&',p['title'])

    def test_skip_recurrence_cancellation_unknown_location_and_bad_dates(self):
        for feed in [FEED.replace('UID:42','UID:42\nRRULE:FREQ=WEEKLY'),FEED.replace('UID:42','UID:42\nSTATUS:CANCELLED'),FEED.replace('98292','Unknown'),FEED.replace('20300601T120000','20300501T120000'),FEED.replace('SUMMARY:','DTSTART:20300601T100000\nSUMMARY:'),FEED.replace('TZID=America/Los_Angeles','TZID=Unknown/Zone')]:
            self.assertEqual(records(feed),( [],1))
        self.assertEqual(records(FEED.replace('20300601','20290601')),([],0))
        with self.assertRaises(d.FetchError):records('<html>not a calendar</html>')

    def test_radius_and_optional_day_trips(self):
        self.assertAlmostEqual(d.distance((0,0),(0,1)),69.0934,places=3)
        self.assertEqual(records(origin=(34.09,-118.4),venue=(35,-118.4))[0],[])
        p=records(settings=dict(SETTINGS,include_day_trips=True),venue=(35,-118.4))[0][0][1]
        self.assertEqual(p['metadata']['range'],'Day trip')
        self.assertEqual(records(settings=dict(SETTINGS,include_day_trips=True),venue=(40,-118.4))[0],[])

    def test_weekend_eligibility_expiration_and_historical_snapshots(self):
        p=records()[0][0][1];idea=dict(test_app.idea(1),metadata=p['metadata'])
        limits=dict(minutes=180,budget=100,energy='medium',count=1,weekend_date='2030-06-01')
        with patch.object(d,'utcnow',return_value=NOW):
            result=server.generate([idea],limits,random.Random(1));self.assertEqual(result['schedule'][0]['day'],'Saturday')
            self.assertEqual(server.generate([idea],dict(limits,weekend_date='2030-06-08'))['items'],[])
            undated=dict(limits);undated.pop('weekend_date');self.assertEqual(server.generate([idea],undated)['items'],[])
            with self.assertRaisesRegex(ValueError,'unavailable'):
                server.generate([idea],dict(limits,locked=[1],previous_schedule=[dict(id=1,kind='idea',day='Sunday')]))
            with self.assertRaisesRegex(ValueError,'Saturday'):server.generate([],dict(limits,weekend_date='2030-06-02'))
        with patch.object(d,'utcnow',return_value=NOW+timedelta(hours=12)):
            self.assertTrue(d.expired(p))
            with self.assertRaises(ValueError):server.schedule_totals([idea],result['schedule'],limits,server.DEFAULTS)
            self.assertTrue(server.schedule_totals([idea],result['schedule'],limits,server.DEFAULTS,historical=True))

    def test_settings_and_dst(self):
        self.assertEqual(d.clean_settings(d.DEFAULTS),d.DEFAULTS)
        for change in [dict(zip='123'),dict(zip='12345&url=bad'),dict(local_miles=True),dict(day_trip_miles=20),dict(timezone='../etc/passwd'),dict(enabled=True),dict(time='24:00')]:
            with self.assertRaises(ValueError):d.clean_settings(dict(d.DEFAULTS,**change))
        settings=dict(SETTINGS,weekday=6,time='02:30')
        spring=datetime(2030,3,9,12,tzinfo=timezone.utc)
        result=d.stamp(d.next_run(settings,spring));self.assertGreater(result,spring)
        self.assertEqual(result.astimezone(d.ZoneInfo(settings['timezone'])).hour,3)
        fall=datetime(2030,11,3,7,tzinfo=timezone.utc)
        s=dict(settings,time='01:30');first=d.stamp(d.next_run(s,fall))
        self.assertGreater(d.stamp(d.next_run(s,first)),first+timedelta(days=6))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=server.DB;server.DB=Path(self.temp.name)/'grove.sqlite3';server.initialize()
    def tearDown(self):server.DB=self.old;self.temp.cleanup()
    def seed(self):
        rows,_=records()
        with server.connect() as db:d.apply_records(db,rows,NOW.isoformat())
        return rows[0][0]
    def test_dedupe_dismiss_save_and_user_edit_preserved(self):
        key=self.seed()
        with server.connect() as db:self.assertEqual(d.apply_records(db,records()[0],NOW.isoformat()),0)
        with server.connect() as db:d.decide(db,key,'dismiss')
        self.seed()
        with server.connect() as db:self.assertEqual(d.view(db)['candidates'][0]['status'],'dismissed')
        other=records(FEED.replace('UID:42','UID:43'))[0]
        with server.connect() as db:d.apply_records(db,other,NOW.isoformat())
        with patch.object(d,'utcnow',return_value=NOW):
            with server.connect() as db:d.decide(db,other[0][0],'save')
            with server.connect() as db:d.decide(db,other[0][0],'save')
        with server.connect() as db:db.execute("UPDATE ideas SET title='User edit'")
        with server.connect() as db:
            d.apply_records(db,other,NOW.isoformat());ideas=server.export_state(db)['ideas'];self.assertEqual(len(ideas),1);self.assertEqual(ideas[0]['title'],'User edit');self.assertTrue(ideas[0]['metadata'])
        server.initialize()
        with server.connect() as db:self.assertEqual(len(d.view(db)['candidates']),2)

    def test_v5_roundtrip_dismissals_provenance_and_disabled_restore(self):
        key=self.seed()
        with patch.object(d,'utcnow',return_value=NOW):
            with server.connect() as db:d.decide(db,key,'save')
        with server.connect() as db:
            d.configure(db,dict(SETTINGS,enabled=True));source=server.export_state(db)
        self.assertNotIn('enabled',source['discovery']['preferences']);self.assertNotIn('consent',source['discovery']['preferences'])
        server.DB=Path(self.temp.name)/'restored.sqlite3';server.initialize()
        backup=server.validate_backup(json.dumps(source))
        with server.connect() as db:server.restore_backup(db,backup,apply_discovery=True)
        with server.connect() as db:
            self.assertEqual(server.export_state(db),source);self.assertFalse(d.settings_from(db)['enabled']);self.assertFalse(d.settings_from(db)['consent'])
            self.assertEqual(server.restore_backup(db,backup)['ideas_to_add'],0)
        bad=copy.deepcopy(source);bad['discovery']['candidates'][0]['idea_uid']=str(uuid.uuid4())
        with self.assertRaises(ValueError):server.validate_backup(json.dumps(bad))
        bad=copy.deepcopy(source);bad['ideas'][0]['metadata']['source_url']='javascript:alert(1)'
        with self.assertRaises(ValueError):server.validate_backup(json.dumps(bad))

    def test_v4_migration_backup_preserves_data(self):
        server.DB=Path(self.temp.name)/'v4.sqlite3'
        with closing(sqlite3.connect(server.DB)) as db, db:
            db.executescript('CREATE TABLE ideas(id INTEGER PRIMARY KEY,title TEXT,category TEXT,duration INTEGER,cost REAL,location TEXT,energy TEXT,archived INTEGER,sample INTEGER,uid TEXT);CREATE TABLE plans(id INTEGER PRIMARY KEY,name TEXT,created TEXT,payload TEXT,uid TEXT);CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);')
            db.execute('INSERT INTO ideas VALUES (1,?,?,?,?,?,?,?,?,?)',('Existing example','Places',None,None,'',None,0,0,str(uuid.uuid4())))
            db.execute("INSERT INTO settings VALUES ('currency','\"USD\"')")
        server.initialize();server.initialize()
        with closing(sqlite3.connect(Path(self.temp.name)/'before-upgrade-v5.sqlite3')) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertEqual(db.execute('SELECT title FROM ideas').fetchone()[0],'Existing example')
            self.assertNotIn('metadata',[r[1] for r in db.execute('PRAGMA table_info(ideas)')])
        with server.connect() as db:self.assertEqual(server.export_state(db)['ideas'][0]['metadata'],{})

    def test_leases_missed_run_and_consent(self):
        with server.connect() as db:
            self.assertIsNone(d.claim(db))
        with server.connect() as db:d.configure(db,dict(SETTINGS,enabled=True))
        with server.connect() as db:db.execute('UPDATE discovery_job SET next_run=?',( (NOW-timedelta(days=30)).isoformat(),))
        with server.connect() as db:job=d.claim(db,now=NOW)
        self.assertIsNotNone(job)
        with server.connect() as db:self.assertIsNone(d.claim(db,now=NOW+timedelta(seconds=30)))
        with server.connect() as db:
            j=dict(db.execute('SELECT * FROM discovery_job').fetchone());self.assertGreater(d.stamp(j['next_run']),NOW)
        # An expired lease can be replaced by a manual run, but not a second scheduled catch-up.
        with server.connect() as db:self.assertIsNone(d.claim(db,now=NOW+timedelta(minutes=6)))
        with server.connect() as db:self.assertIsNotNone(d.claim(db,manual=True,now=NOW+timedelta(minutes=6)))
        with server.connect() as db:d.configure(db,dict(SETTINGS,consent=False))
        with server.connect() as db:
            with self.assertRaises(ValueError):d.claim(db,manual=True)

    def test_refresh_failure_preserves_candidates_and_disabled_no_network(self):
        self.seed()
        with server.connect() as db:d.configure(db,SETTINGS)
        with server.connect() as db:job=d.claim(db,manual=True,now=NOW)
        def unavailable(*args):raise d.FetchError('Provider unavailable')
        with patch.object(d,'utcnow',return_value=NOW):d.perform(server.connect,*job,getter=unavailable)
        with server.connect() as db:
            v=d.view(db);self.assertEqual(len(v['candidates']),1);self.assertIn('unavailable',v['job']['outcome']);self.assertFalse(v['job']['running'])
        with patch.object(d,'perform') as run:
            self.assertFalse(d.launch(server.connect));run.assert_not_called()

    def test_success_cache_and_revocation_stops_next_request(self):
        with server.connect() as db:d.configure(db,SETTINGS)
        with server.connect() as db:job=d.claim(db,manual=True,now=NOW)
        calls=[]
        def getter(url,deadline):
            calls.append(url)
            if url==d.FEED_URL:return FEED
            return json.dumps({'places':[{'latitude':'34.09','longitude':'-118.4'}]})
        with patch.object(d,'utcnow',return_value=NOW):d.perform(server.connect,*job,getter=getter)
        self.assertEqual(len(calls),3)
        with server.connect() as db:self.assertEqual(len(d.view(db)['candidates']),1)
        with server.connect() as db:job=d.claim(db,manual=True,now=NOW+timedelta(minutes=6))
        calls.clear()
        with patch.object(d,'utcnow',return_value=NOW+timedelta(minutes=6)):d.perform(server.connect,*job,getter=getter)
        self.assertEqual(calls,[d.FEED_URL])
        with server.connect() as db:
            db.execute('DELETE FROM discovery_zip_cache');d.configure(db,SETTINGS)
        with server.connect() as db:job=d.claim(db,manual=True,now=NOW+timedelta(minutes=12))
        calls.clear()
        def revoke(url,deadline):
            with server.connect() as db:d.configure(db,dict(SETTINGS,consent=False))
            return getter(url,deadline)
        with patch.object(d,'utcnow',return_value=NOW+timedelta(minutes=12)):d.perform(server.connect,*job,getter=revoke)
        self.assertEqual(len(calls),1)


class NetworkSafetyTests(unittest.TestCase):
    def test_allowlist_rejects_arbitrary_urls_before_dns(self):
        with patch('socket.getaddrinfo') as dns:
            for url in ['http://api.zippopotam.us/us/90210','https://api.zippopotam.us@127.0.0.1/us/90210','https://api.zippopotam.us/us/90210?next=http://localhost','https://stanwoodwa.org/other','https://127.0.0.1/']:
                with self.assertRaises(d.FetchError):d.fetch(url)
            dns.assert_not_called()
    def test_dns_private_and_mixed_answers_blocked(self):
        for ips in [['127.0.0.1'],['192.168.1.1'],['1.1.1.1','::1']]:
            with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443)) for ip in ips]),patch('socket.create_connection') as connect:
                with self.assertRaises(d.FetchError):d.fetch('https://api.zippopotam.us/us/90210')
                connect.assert_not_called()


class DiscoveryHTTPTests(unittest.TestCase):
    setUpClass=classmethod(test_app.IntegrationTests.setUpClass.__func__)
    tearDownClass=classmethod(test_app.IntegrationTests.tearDownClass.__func__)
    start=classmethod(test_app.IntegrationTests.start.__func__)
    request=test_app.IntegrationTests.request
    def test_settings_restart_and_no_consent_refresh(self):
        self.assertFalse(self.request('/api/discovery')['settings']['consent'])
        self.request('/api/discovery/settings',dict(d.DEFAULTS,zip='90210'))
        try:self.request('/api/discovery/refresh',{})
        except test_app.urllib.error.HTTPError as e:self.assertEqual(e.code,400);e.close()
        else:self.fail('Missing consent should reject refresh')
        before=self.request('/api/discovery')['settings']
        self.proc.terminate();self.proc.wait(timeout=5);self.start()
        self.assertEqual(self.request('/api/discovery')['settings'],before)
        self.assertFalse(self.request('/api/discovery')['job']['running'])

class AdditionalSafetyTests(unittest.TestCase):
    def test_redirects_and_large_responses_are_rejected(self):
        from unittest.mock import MagicMock
        for status,blocks in [(302,[]),(200,[b'x'*16384]*65)]:
            response=MagicMock();response.status=status;response.read1.side_effect=blocks
            conn=MagicMock();conn.getresponse.return_value=response
            with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('1.1.1.1',443))]),patch('socket.create_connection'),patch('ssl.create_default_context'),patch('http.client.HTTPSConnection',return_value=conn):
                with self.assertRaises(d.FetchError):d.fetch('https://api.zippopotam.us/us/90210')
                self.assertEqual(conn.request.call_count,1);conn.close.assert_called_once()
    def test_source_and_timestamps_cannot_be_forged_in_backup(self):
        m=records()[0][0][1]['metadata']
        for change in [dict(source_url='https://127.0.0.1/'),dict(source_id='unknown'),dict(end_date='2030-06-02'),dict(ends_at=None)]:
            with self.assertRaises(ValueError):d.clean_metadata(dict(m,**change))
    def test_explicit_adult_only_events_are_skipped(self):
        for title in ['Example event 21+ only','Example event adults only','18+ performance']:
            self.assertEqual(records(FEED.replace('Example community picnic',title)),([],1))

class DatedHTTPTests(DiscoveryHTTPTests):
    def test_dated_event_saved_on_correct_day_only_and_restorable_after_expiry(self):
        with closing(sqlite3.connect(Path(self.temp.name)/'weekend.sqlite3')) as db, db:
            p=records()[0][0][1]
            db.execute('INSERT INTO ideas(uid,title,category,metadata) VALUES (?,?,?,?)',(str(uuid.uuid4()),p['title'],p['category'],json.dumps(p['metadata'])))
        limits=dict(minutes=180,budget=100,energy='medium',count=1,weekend_date='2030-06-01')
        plan=self.request('/api/generate',limits)
        data=dict(name='Example future event',ids=[i['id'] for i in plan['items']],schedule=plan['schedule'],limits=plan['limits'],expected_items=plan['items'])
        bad=copy.deepcopy(data);bad['schedule'][0]['day']='Sunday'
        try:self.request('/api/plans',bad)
        except test_app.urllib.error.HTTPError as e:self.assertEqual(e.code,400);e.close()
        else:self.fail('Date-ineligible plan should not save')
        self.request('/api/plans',data)
        exported=self.request('/api/export')
        with patch.object(d,'utcnow',return_value=NOW+timedelta(days=500)):
            validated=server.validate_backup(json.dumps(exported));self.assertTrue(validated['plans'])
