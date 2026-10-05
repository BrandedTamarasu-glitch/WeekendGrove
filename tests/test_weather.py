"""Weather contracts use generic locations and deterministic offline responses."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import server
import weather as w

NOW=datetime(2030,6,1,8,tzinfo=timezone.utc)
REQUEST=dict(zip='90210',weekend_date='2030-06-01',timezone='America/Los_Angeles',consent=True)
DATA=dict(timezone='America/Los_Angeles',daily_units=dict(zip(w.FIELDS,['°F','°F','%'])),daily=dict(time=['2030-06-01','2030-06-02'],temperature_2m_max=[74,70],temperature_2m_min=[56,54],precipitation_probability_max=[10,35]))

class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=server.DB;server.DB=Path(self.temp.name)/'test.sqlite3';server.initialize();w.CACHE.clear();self.calls=[]
    def tearDown(self):server.DB=self.old;self.temp.cleanup();w.CACHE.clear()
    def getter(self,url,deadline):
        self.calls.append(url)
        if 'zippopotam' in url:return json.dumps({'places':[{'latitude':'34.09','longitude':'-118.4'}]})
        return json.dumps(DATA)
    def run_lookup(self,request=None,now=NOW,getter=None):return w.lookup(server.connect,request or REQUEST,getter or self.getter,now)
    def test_permission_validation_no_network(self):
        for changes in [dict(consent=False),dict(consent=1),dict(zip='123'),dict(timezone='../bad'),dict(weekend_date='2030-06-02'),dict(weekend_date=None)]:
            with self.assertRaises(ValueError):self.run_lookup(dict(REQUEST,**changes))
        self.assertEqual(self.calls,[])
    def test_dates_past_and_too_early_do_not_send_location(self):
        for date,status in [('2030-05-25','past'),('2030-06-22','too_early')]:
            r=self.run_lookup(dict(REQUEST,weekend_date=date));self.assertTrue(all(d['status']==status for d in r['days']))
        self.assertEqual(self.calls,[])
    def test_request_data_and_cache_and_no_plan_storage(self):
        r=self.run_lookup();self.assertEqual(r['days'][1]['rain'],35);self.assertFalse(r['cached'])
        query=parse_qs(urlsplit(self.calls[1]).query)
        self.assertEqual(set(query),{'latitude','longitude','daily','temperature_unit','timezone','start_date','end_date'})
        self.assertNotIn('90210',self.calls[1]);self.assertTrue(self.run_lookup()['cached']);self.assertEqual(len(self.calls),2)
        self.run_lookup(now=NOW+timedelta(hours=2));self.assertEqual(len(self.calls),3)
        with server.connect() as db:
            exported=server.export_state(db);self.assertEqual(exported['ideas'],[]);self.assertEqual(exported['plans'],[])
            self.assertNotIn('weather',exported);self.assertFalse(any('weather' in r[0] for r in db.execute('select name from sqlite_master')))
    def test_cache_partition_zip_date_timezone(self):
        self.run_lookup()
        self.run_lookup(dict(REQUEST,zip='10001'))
        self.run_lookup(dict(REQUEST,weekend_date='2030-06-08'))
        self.run_lookup(dict(REQUEST,timezone='America/New_York'))
        self.assertEqual(len(w.CACHE),4)
    def test_partial_null_invalid_and_missing_dates(self):
        data=copy.deepcopy(DATA);data['daily']['temperature_2m_max']=[None,True];data['daily']['precipitation_probability_max']=[float('nan'),101]
        r=self.run_lookup(getter=lambda url,deadline:self.getter(url,deadline) if 'zippopotam' in url else json.dumps(data))
        self.assertTrue(all(d['status']=='partial' and d['high'] is None and d['rain'] is None for d in r['days']))
    def test_outage_sanitized_and_no_stale_fallback(self):
        self.run_lookup()
        def failure(*args):raise RuntimeError('private-provider-url-must-not-leak')
        r=self.run_lookup(now=NOW+timedelta(hours=2),getter=failure)
        self.assertEqual(r['status'],'unavailable');self.assertIsNone(r['fetched_at']);self.assertNotIn('private-provider',json.dumps(r))
        self.assertTrue(all(d['high'] is None for d in r['days']))
    def test_horizon_boundary_partial_weekend(self):
        # Saturday is day 16; Sunday is beyond the forecast horizon.
        now=datetime(2030,5,17,12,tzinfo=timezone.utc)
        r=self.run_lookup(now=now);self.assertEqual(r['days'][1]['status'],'too_early')
        q=parse_qs(urlsplit(self.calls[-1]).query);self.assertEqual(q['end_date'],['2030-06-01'])
    def test_local_midnight_and_dst_use_calendar_dates(self):
        # UTC Sunday remains Saturday in Pacific; Saturday must not be called past.
        r=self.run_lookup(now=datetime(2030,6,2,1,tzinfo=timezone.utc));self.assertNotEqual(r['days'][0]['status'],'past')
        for day in ['2030-03-09','2030-11-02']:
            w.CACHE.clear();r=self.run_lookup(dict(REQUEST,weekend_date=day),now=datetime.fromisoformat(day+'T08:00:00+00:00'))
            self.assertEqual(r['days'][1]['date'],str(datetime.fromisoformat(day).date()+timedelta(days=1)))
    def test_permission_checked_even_for_cached_data(self):
        self.run_lookup()
        with self.assertRaises(ValueError):self.run_lookup(dict(REQUEST,consent=False))

    def test_provider_timezone_mismatch_and_bad_units_fail_closed(self):
        for update in [dict(timezone='UTC'),dict(daily_units={})]:
            w.CACHE.clear();data=dict(DATA,**update)
            r=self.run_lookup(getter=lambda url,deadline:self.getter(url,deadline) if 'zippopotam' in url else json.dumps(data))
            self.assertEqual(r['status'],'unavailable');self.assertTrue(all(d['high'] is None for d in r['days']))

class WeatherHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_app
        test_app.IntegrationTests.setUpClass.__func__(cls)
    @classmethod
    def start(cls):
        import test_app
        test_app.IntegrationTests.start.__func__(cls)
    @classmethod
    def tearDownClass(cls):
        import test_app
        test_app.IntegrationTests.tearDownClass.__func__(cls)
    def test_weather_endpoint_requires_explicit_permission_and_preserves_export(self):
        import urllib.request, urllib.error
        def call(data):
            req=urllib.request.Request(self.base+'/api/weather',json.dumps(data).encode(),{'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as r:return json.load(r)
        with self.assertRaises(urllib.error.HTTPError) as error:call(dict(REQUEST,consent=False))
        self.assertEqual(error.exception.code,400);error.exception.close()
        with urllib.request.urlopen(self.base+'/api/export') as r:before=json.load(r)
        result=call(dict(REQUEST,weekend_date='2099-01-03'))
        self.assertTrue(all(d['status']=='too_early' for d in result['days']))
        with urllib.request.urlopen(self.base+'/api/export') as r:self.assertEqual(json.load(r),before)
        with urllib.request.urlopen(self.base+'/weather.js') as r:self.assertEqual(r.status,200)
