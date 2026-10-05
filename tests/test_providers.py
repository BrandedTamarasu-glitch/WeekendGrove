"""Offline provider contracts. Dummy credentials are never used for live requests."""
import copy
import json
import os
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import discovery as d
import discovery_providers as p
import server
from test_discovery import NOW, SETTINGS, FEED

ORIGIN=(34.09,-118.4)
GEO=dict(results=[dict(country_code='us',postcode='90210',lat=34.09,lon=-118.4)])
PLACE=dict(features=[dict(properties=dict(place_id='generic-place-1',name='Example Museum',formatted='Example Museum, Example City',lat=34.1,lon=-118.4,categories=['entertainment.museum']))])
EVENT=dict(id='generic-event-1',name='Example family performance',url='https://www.ticketmaster.com/example/event/example1',classifications=[dict(family=True)],dates=dict(start=dict(localDate='2030-06-01',localTime='12:00:00'),timezone='America/Los_Angeles',status=dict(code='onsale')),_embedded=dict(venues=[dict(name='Example Venue',timezone='America/Los_Angeles',location=dict(latitude='34.1',longitude='-118.4'),address=dict(line1='Example public address'),city=dict(name='Example City'))]))
ENV={'GEOAPIFY_API_KEY':'test_dummy_geo_key','TICKETMASTER_API_KEY':'test_dummy_ticket_key'}


def event_data(event=EVENT):return {'_embedded':{'events':[event]}}


class ProviderParserTests(unittest.TestCase):
    def test_geoapify_places_are_evergreen_and_unknown_costs(self):
        records,skipped=p.geoapify_records(PLACE,'Places',ORIGIN,SETTINGS,NOW)
        self.assertEqual((len(records),skipped),(1,0));idea=records[0][1]
        self.assertIsNone(idea['cost']);self.assertIsNone(idea['duration']);self.assertIsNone(idea['metadata']['start_date'])
        self.assertTrue(d.eligible(idea,'Saturday',{}));self.assertFalse(d.expired(idea,NOW+timedelta(days=365)))
        self.assertEqual(d.clean_metadata(idea['metadata']),idea['metadata'])
        self.assertNotIn('apiKey',json.dumps(idea))
        restaurant=copy.deepcopy(PLACE);restaurant['features'][0]['properties'].update(name='Example restaurant',categories=['catering.restaurant'])
        meal=p.geoapify_records(restaurant,'Restaurants',ORIGIN,SETTINGS,NOW)[0][0][1]
        self.assertEqual(meal['category'],'Restaurants');self.assertIsNone(meal['cost'])
        for change in [dict(lat=float('nan')),dict(lat=91),dict(lat=40),dict(name=''),dict(categories=['commercial.supermarket'])]:
            data=copy.deepcopy(PLACE);data['features'][0]['properties'].update(change)
            self.assertEqual(p.geoapify_records(data,'Places',ORIGIN,SETTINGS,NOW),([],1))

    def test_geoapify_three_bounded_requests_and_zip_match(self):
        calls=[]
        def getter(url,deadline):
            q=parse_qs(urlsplit(url).query);calls.append(q)
            if '/geocode/' in url:return json.dumps(GEO)
            if q['categories']==['catering.restaurant']:return json.dumps({'features':[]})
            return json.dumps(PLACE)
        with patch.object(p.time,'sleep') as throttle:
            origin,records,skipped=p.geoapify_lookup(SETTINGS,ENV['GEOAPIFY_API_KEY'],getter,time.monotonic()+60,NOW)
        self.assertEqual(origin,ORIGIN);self.assertEqual(len(records),1);self.assertEqual(len(calls),3)
        self.assertEqual(calls[0]['type'],['postcode']);self.assertEqual(calls[0]['filter'],['countrycode:us'])
        self.assertEqual(calls[1]['limit'],['20']);self.assertTrue(calls[1]['filter'][0].startswith('circle:-118.4,34.09,'))
        self.assertEqual(throttle.call_count,2)
        with self.assertRaises(d.FetchError):p.geoapify_lookup(SETTINGS,'dummy',lambda *a:json.dumps({'results':[dict(GEO['results'][0],postcode='00000')]}),time.monotonic()+10,NOW)
        with self.assertRaises(d.FetchError):p.geoapify_records({'features':PLACE['features']*21},'Places',ORIGIN,SETTINGS,NOW)

    def test_ticketmaster_family_dates_bounds_and_provenance(self):
        records,skipped=p.ticketmaster_records(event_data(),ORIGIN,SETTINGS,NOW)
        self.assertEqual((len(records),skipped),(1,0));idea=records[0][1]
        self.assertEqual(idea['metadata']['start_date'],'2030-06-01');self.assertIsNone(idea['metadata']['ends_at'])
        self.assertIsNone(idea['duration']);self.assertIsNone(idea['cost'])
        self.assertTrue(d.eligible(idea,'Saturday',{'weekend_date':'2030-06-01'},NOW))
        self.assertFalse(d.eligible(idea,'Sunday',{'weekend_date':'2030-06-01'},NOW))
        self.assertTrue(d.expired(idea,NOW+timedelta(hours=25)))
        for code in ['cancelled','postponed','rescheduled','offsale']:
            bad=copy.deepcopy(EVENT);bad['dates']['status']['code']=code
            self.assertEqual(p.ticketmaster_records(event_data(bad),ORIGIN,SETTINGS,NOW),([],1))
        for change in [dict(classifications=[]),dict(url='http://www.ticketmaster.com/bad'),dict(url='https://evil.example/bad'),dict(name='21+ performance')]:
            bad=dict(EVENT,**change);self.assertEqual(p.ticketmaster_records(event_data(bad),ORIGIN,SETTINGS,NOW),([],1))
        bad=copy.deepcopy(EVENT);bad['dates']['start']['dateTBA']=True
        self.assertEqual(p.ticketmaster_records(event_data(bad),ORIGIN,SETTINGS,NOW),([],1))
        bad=copy.deepcopy(EVENT);bad['dates']['start']['localDate']='2031-06-01'
        self.assertEqual(p.ticketmaster_records(event_data(bad),ORIGIN,SETTINGS,NOW),([],0))
        bad=copy.deepcopy(EVENT);bad['dates']['timezone']='Bad/Zone'
        self.assertEqual(p.ticketmaster_records(event_data(bad),ORIGIN,SETTINGS,NOW),([],1))

    def test_ticketmaster_one_request_geohash_and_family_filter(self):
        calls=[]
        def getter(url,deadline):calls.append(parse_qs(urlsplit(url).query));return json.dumps(event_data())
        self.assertEqual(p.geohash(42.6,-5.6,5),'ezs42')
        records,_=p.ticketmaster_lookup(SETTINGS,ORIGIN,ENV['TICKETMASTER_API_KEY'],getter,time.monotonic()+60,NOW)
        self.assertEqual(len(records),1);self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['includeFamily'],['only']);self.assertEqual(calls[0]['size'],['100']);self.assertEqual(calls[0]['page'],['0'])
        self.assertEqual(calls[0]['startDateTime'],['2030-06-01T08:00:00Z'])
        self.assertNotIn('latlong',calls[0]);self.assertEqual(len(calls[0]['geoPoint'][0]),8)

    def test_endpoint_guard_and_no_secret_status(self):
        with patch.dict(os.environ,ENV,clear=True):
            self.assertTrue(d.provider_endpoint_allowed(urlsplit('https://api.geoapify.com/v2/places?apiKey=test_dummy_geo_key')))
            self.assertFalse(d.provider_endpoint_allowed(urlsplit('https://api.geoapify.com/v2/places?apiKey=wrong')))
            self.assertFalse(d.provider_endpoint_allowed(urlsplit('https://evil.example/v2/places?apiKey=test_dummy_geo_key')))
            self.assertFalse(d.provider_endpoint_allowed(urlsplit('https://api.geoapify.com/v1/other?apiKey=test_dummy_geo_key')))
            status=d.provider_status(SETTINGS);self.assertTrue(status['geoapify']['configured']);self.assertFalse(status['geoapify']['active'])
            self.assertNotIn('test_dummy',json.dumps(status))
        with patch.dict(os.environ,{'GEOAPIFY_API_KEY':'bad\nkey'},clear=True):self.assertFalse(d.provider_key('GEOAPIFY_API_KEY'))

    def test_private_key_file_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'provider.key';path.write_text('test_dummy_file_key\n');path.chmod(0o600)
            with patch.dict(os.environ,{'GEOAPIFY_API_KEY_FILE':str(path)},clear=True):
                self.assertEqual(d.provider_key('GEOAPIFY_API_KEY'),'test_dummy_file_key')
                path.chmod(0o644);self.assertEqual(d.provider_key('GEOAPIFY_API_KEY'),'')
                path.chmod(0o600);path.write_text('x'*300);self.assertEqual(d.provider_key('GEOAPIFY_API_KEY'),'')
            link=Path(temp)/'link.key';link.symlink_to(path)
            with patch.dict(os.environ,{'GEOAPIFY_API_KEY_FILE':str(link)},clear=True):self.assertEqual(d.provider_key('GEOAPIFY_API_KEY'),'')


class ProviderPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=server.DB;server.DB=Path(self.temp.name)/'grove.sqlite3';server.initialize()
        self.env=patch.dict(os.environ,ENV,clear=True);self.env.start()
    def tearDown(self):self.env.stop();server.DB=self.old;self.temp.cleanup()
    def job(self,settings,now=NOW):
        with server.connect() as db:d.configure(db,settings)
        with server.connect() as db:return d.claim(db,manual=True,now=now)
    def getter(self,url,deadline):
        if url==d.FEED_URL:return FEED
        if 'zippopotam' in url:return json.dumps({'places':[{'latitude':'48.2','longitude':'-122.3'}]})
        if '/geocode/' in url:return json.dumps(GEO)
        if '/v2/places' in url:
            return json.dumps(PLACE if 'entertainment.museum' in url else {'features':[]})
        if 'ticketmaster' in url:return json.dumps(event_data())
        raise AssertionError('Unrecognized endpoint')
    def run_job(self,settings=SETTINGS,now=NOW,getter=None):
        job=self.job(settings,now)
        with patch.object(d,'utcnow',return_value=now),patch.object(p.time,'sleep'):
            d.perform(server.connect,*job,getter=getter or self.getter)
    def test_existing_local_settings_gain_no_new_permission(self):
        legacy={k:v for k,v in SETTINGS.items() if k not in ('geoapify_consent','ticketmaster_consent')}
        with server.connect() as db:db.execute("UPDATE settings SET value=? WHERE key='discovery'",(json.dumps(legacy),))
        server.initialize()
        with server.connect() as db:
            settings=d.settings_from(db);self.assertTrue(settings['consent'])
            self.assertFalse(settings['geoapify_consent']);self.assertFalse(settings['ticketmaster_consent'])
            self.assertFalse(d.provider_status(settings)['geoapify']['active'])
    def test_keys_alone_never_enable_credentialed_requests(self):
        calls=[]
        def getter(url,deadline):calls.append(url);return self.getter(url,deadline)
        self.run_job(getter=getter)
        self.assertFalse(any('geoapify' in u or 'ticketmaster' in u for u in calls))
        with server.connect() as db:
            v=d.view(db);self.assertFalse(v['providers']['geoapify']['active'])
            self.assertNotIn('test_dummy',json.dumps(v));self.assertNotIn('test_dummy',json.dumps(server.export_state(db)))
        with patch.dict(os.environ,{},clear=True):
            calls.clear();self.run_job(dict(SETTINGS,geoapify_consent=True,ticketmaster_consent=True),NOW+timedelta(minutes=6),getter)
            self.assertFalse(any('geoapify' in u or 'ticketmaster' in u for u in calls))
    def test_opt_in_merge_and_no_secret_in_database_or_export(self):
        self.run_job(dict(SETTINGS,geoapify_consent=True,ticketmaster_consent=True))
        with patch.object(d,'utcnow',return_value=NOW),server.connect() as db:
            v=d.view(db);self.assertEqual(len(v['candidates']),2)
            source=server.export_state(db);self.assertNotIn('test_dummy',json.dumps(source));self.assertNotIn('test_dummy','\n'.join(db.iterdump()))
            self.assertNotIn('geoapify_consent',source['discovery']['preferences'])
            self.assertEqual(server.validate_backup(json.dumps(source))['version'],5)
            backup=server.validate_backup(json.dumps(source));d.restore(db,backup['discovery'],True)
            self.assertFalse(d.settings_from(db)['geoapify_consent']);self.assertFalse(d.settings_from(db)['ticketmaster_consent'])
    def test_revocation_prevents_subsequent_requests_and_writes(self):
        calls=[];settings=dict(SETTINGS,geoapify_consent=True,ticketmaster_consent=True)
        def revoke(url,deadline):
            calls.append(url)
            with server.connect() as db:d.configure(db,dict(settings,geoapify_consent=False,ticketmaster_consent=False))
            return self.getter(url,deadline)
        self.run_job(settings,getter=revoke)
        self.assertEqual(len(calls),1)
        with server.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM discovery_candidates').fetchone()[0],0)
    def test_failure_redacts_exception_and_keeps_ideas(self):
        def failure(*args):raise d.FetchError('sensitive dummy test_dummy_geo_key')
        self.run_job(dict(SETTINGS,geoapify_consent=True,ticketmaster_consent=True),getter=failure)
        with server.connect() as db:self.assertNotIn('test_dummy',json.dumps(d.view(db)))
    def test_ticket_cache_cleanup_keeps_decisions_user_edits_and_restore(self):
        records,_=p.ticketmaster_records(event_data(),ORIGIN,SETTINGS,NOW);key=records[0][0]
        with patch.object(d,'utcnow',return_value=NOW):
            with server.connect() as db:d.apply_records(db,records,NOW.isoformat())
            with server.connect() as db:d.decide(db,key,'save')
        with server.connect() as db:db.execute("UPDATE ideas SET title='User title'")
        with patch.object(d,'utcnow',return_value=NOW+timedelta(hours=25)),server.connect() as db:
            source=server.export_state(db);row=source['discovery']['candidates'][0]
            self.assertIsNone(row['payload']);self.assertEqual(row['status'],'saved');self.assertEqual(source['ideas'][0]['title'],'User title')
            self.assertEqual(d.view(db)['candidates'],[]);server.validate_backup(json.dumps(source))
            d.apply_records(db,records,NOW.isoformat());self.assertEqual(db.execute('SELECT COUNT(*) FROM ideas').fetchone()[0],1)
        server.DB=Path(self.temp.name)/'restore.sqlite3';server.initialize()
        with server.connect() as db:server.restore_backup(db,server.validate_backup(json.dumps(source)),apply_discovery=True)
        with server.connect() as db:self.assertEqual(server.export_state(db)['ideas'][0]['title'],'User title')
    def test_successful_ticket_refresh_removes_missing_pending_facts(self):
        settings=dict(SETTINGS,geoapify_consent=True,ticketmaster_consent=True)
        self.run_job(settings)
        def noevents(url,deadline):return json.dumps({'_embedded':{'events':[]}}) if 'ticketmaster' in url else self.getter(url,deadline)
        self.run_job(settings,NOW+timedelta(minutes=6),noevents)
        with patch.object(d,'utcnow',return_value=NOW+timedelta(minutes=6)),server.connect() as db:
            v=d.view(db);self.assertEqual(len(v['candidates']),1);self.assertEqual(v['candidates'][0]['payload']['metadata']['source_id'],'geoapify')
            self.assertEqual(db.execute("SELECT count(*) FROM discovery_candidates WHERE payload='null'").fetchone()[0],1)


if __name__=='__main__':unittest.main()

class SecretHTTPTests(unittest.TestCase):
    import test_app as support
    setUpClass=classmethod(support.IntegrationTests.setUpClass.__func__)
    tearDownClass=classmethod(support.IntegrationTests.tearDownClass.__func__)
    start=classmethod(support.IntegrationTests.start.__func__)
    request=support.IntegrationTests.request

    def test_secret_files_are_not_in_routes_exports_or_database_backup(self):
        import urllib.request
        import urllib.error
        import sqlite3
        from contextlib import closing
        folder=Path(self.temp.name)/'secrets';folder.mkdir(mode=0o700)
        secret=folder/'geoapify.key';marker=b'offline_secret_route_test_only';secret.write_bytes(marker);secret.chmod(0o600)
        for route in ['/data/secrets/geoapify.key','/secrets/geoapify.key','/../data/secrets/geoapify.key','/%2e%2e/data/secrets/geoapify.key','/static/../data/secrets/geoapify.key','/api/backup/../secrets/geoapify.key']:
            with self.assertRaises(urllib.error.HTTPError) as raised:urllib.request.urlopen(self.base+route)
            self.assertEqual(raised.exception.code,404);self.assertNotIn(marker,raised.exception.read());raised.exception.close()
        for route in ['/api/state','/api/export','/api/discovery','/api/backup']:
            with urllib.request.urlopen(self.base+route) as response:body=response.read()
            self.assertNotIn(marker,body)
            if route=='/api/backup':
                backup=Path(self.temp.name)/'download.sqlite3';backup.write_bytes(body)
                with closing(sqlite3.connect(backup)) as db:
                    self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                    self.assertNotIn(marker.decode(),'\n'.join(db.iterdump()))
