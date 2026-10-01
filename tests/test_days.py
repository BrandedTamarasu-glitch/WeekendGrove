import copy
import json
import random
import unittest

import server
import test_app
idea = test_app.idea


def caps(value=1):
    return {d: {c: value for c in server.CATEGORIES} for d in server.DAYS}


class DayPlannerTests(unittest.TestCase):
    def setUp(self):
        self.data = dict(minutes=360,budget=100,energy='medium',count=6,day_caps=caps(),include_lazy=False)
        self.ideas = [dict(idea(i,30,2),category=server.CATEGORIES[(i-1)%4]) for i in range(1,21)]

    def check_plan(self, p):
        self.assertEqual(server.schedule_totals(p['items'],p['schedule'],p['limits'],p['defaults']),(p['minutes'],round(p['cost']*100)))

    def test_daily_caps_and_locks_across_200_rerolls(self):
        p=server.generate(self.ideas,self.data,random.Random(1))
        fixed=p['schedule'][0]
        for seed in range(200):
            p=server.generate(self.ideas,self.data|dict(locked=[fixed['id']],previous=[e['id'] for e in p['schedule']],previous_schedule=p['schedule']),random.Random(seed))
            self.assertEqual(next(e for e in p['schedule'] if e['id']==fixed['id']),fixed)
            self.check_plan(p)
        changed=copy.deepcopy(self.data)
        changed['day_caps'][fixed['day']][next(i['category'] for i in p['items'] if i['id']==fixed['id'])]=0
        with self.assertRaisesRegex(ValueError,'daily category'):
            server.generate(self.ideas,changed|dict(locked=[fixed['id']],previous_schedule=p['schedule']))

    def test_zero_caps_and_asymmetric_days(self):
        data=self.data|dict(day_caps=caps(0))
        self.assertEqual(server.generate(self.ideas,data)['schedule'],[])
        data['day_caps']['Sunday']['Restaurants']=1
        p=server.generate(self.ideas,data)
        self.assertEqual(len(p['items']),1)
        self.assertEqual(p['items'][0]['category'],'Restaurants')
        self.assertEqual(p['schedule'][0]['day'],'Sunday')

    def test_lazy_time_without_ideas_cost_or_quota(self):
        data=self.data|dict(day_caps=caps(0),budget=0,include_lazy=True)
        for seed in range(50):
            p=server.generate([],data,random.Random(seed))
            self.assertFalse(p['items']);self.assertEqual(p['cost'],0)
            self.assertIn(len(p['schedule']),(1,2));self.check_plan(p)
            self.assertTrue(all(e['kind']=='lazy' for e in p['schedule']))
        self.assertEqual(server.generate([],data|dict(include_lazy=False))['schedule'],[])
        self.assertEqual(server.generate([],data|dict(minutes=29))['schedule'],[])
        self.assertEqual(server.generate([],data|dict(minutes=30))['minutes'],30)

    def test_lazy_locks_and_shared_time_budget(self):
        data=self.data|dict(include_lazy=True,minutes=120)
        p=server.generate(self.ideas,data,random.Random(4))
        lazy=next(e for e in p['schedule'] if e['kind']=='lazy')
        for seed in range(100):
            p=server.generate(self.ideas,data|dict(locked=[lazy['id']],previous_schedule=p['schedule']),random.Random(seed))
            self.assertEqual(next(e for e in p['schedule'] if e['id']==lazy['id']),lazy)
            self.assertLessEqual(p['minutes'],120);self.check_plan(p)
        with self.assertRaisesRegex(ValueError,'turning Lazy Day'):
            server.generate(self.ideas,data|dict(include_lazy=False,locked=[lazy['id']],previous_schedule=p['schedule']))
        with self.assertRaises(ValueError):
            server.generate([],data|dict(minutes=5,locked=[lazy['id']],previous_schedule=p['schedule']))

    def test_invalid_options_and_schedule(self):
        for extra in [dict(day_caps={}),dict(day_caps=caps(-1)),dict(day_caps=caps(True)),dict(include_lazy='yes')]:
            with self.assertRaises(ValueError):server.generate(self.ideas,self.data|extra)
        for schedule in [[dict(id=-1,day='Sunday',kind='lazy',duration=30)],[dict(id=-1,day='Saturday',kind='lazy',duration=31)],{}]:
            with self.assertRaises(ValueError):server.schedule_entries(schedule)


class DayRestoreTests(unittest.TestCase):
    setUp=test_app.RestoreTests.setUp
    tearDown=test_app.RestoreTests.tearDown

    def test_schedule_roundtrip_and_legacy_unassigned(self):
        source=copy.deepcopy(self.source)
        source['plans'][0]['schedule'].append(dict(id=-2,day='Sunday',kind='lazy',duration=30))
        source['plans'][0]['limits'].update(day_caps=caps(),include_lazy=True)
        source['plans'][0]['minutes']+=30
        backup=server.validate_backup(json.dumps(source))
        with server.connect() as db:server.restore_backup(db,backup,True)
        with server.connect() as db:
            self.assertEqual(server.export_state(db),source)
            self.assertEqual(server.restore_backup(db,backup)['plans_to_add'],0)
        old=copy.deepcopy(self.source);old['version']=3
        old['plans'][0].pop('schedule')
        legacy=server.validate_backup(json.dumps(old))
        self.assertEqual(legacy['plans'][0]['schedule'],[])

    def test_reject_invalid_saved_day_constraints(self):
        for change in ('day','caps','duration','missing','type'):
            source=copy.deepcopy(self.source);plan=source['plans'][0]
            if change=='day':plan['schedule'][0]['day']='Monday'
            if change=='caps':plan['limits'].update(day_caps=caps(0),include_lazy=False)
            if change=='duration':plan['schedule'].append(dict(id=-1,day='Saturday',kind='lazy',duration=45))
            if change=='missing':plan['schedule']=[];plan['limits'].update(day_caps=caps(),include_lazy=False)
            if change=='type':plan['schedule']={}
            with self.assertRaises(ValueError):server.validate_backup(json.dumps(source))


class DayHTTPTests(unittest.TestCase):
    setUpClass=classmethod(test_app.IntegrationTests.setUpClass.__func__)
    tearDownClass=classmethod(test_app.IntegrationTests.tearDownClass.__func__)
    start=classmethod(test_app.IntegrationTests.start.__func__)
    request=test_app.IntegrationTests.request

    def test_day_and_lazy_snapshot_restart(self):
        self.request('/api/samples',{})
        self.request('/api/currency',dict(currency='CAD'))
        data=dict(minutes=360,budget=80,energy='medium',count=6,day_caps=caps(),include_lazy=True)
        p=self.request('/api/generate',data)
        self.request('/api/plans',dict(name='Generic day snapshot',ids=[i['id'] for i in p['items']],expected_items=p['items'],schedule=p['schedule'],limits=p['limits'],defaults=p['defaults'],currency=p['currency'],currency_assumed=p['currency_assumed']))
        before=self.request('/api/state')
        self.assertEqual(before['plans'][0]['schedule'],p['schedule'])
        self.proc.terminate();self.proc.wait(timeout=5);self.start()
        self.assertEqual(self.request('/api/state'),before)
        server.validate_backup(json.dumps(before))
        empty=self.request('/api/generate',data|dict(day_caps=caps(0),minutes=30,budget=0))
        self.request('/api/plans',dict(name='Generic relaxation only',ids=[],expected_items=[],schedule=empty['schedule'],limits=empty['limits'],defaults=empty['defaults'],currency='CAD',currency_assumed=False))
        state=self.request('/api/state');self.assertFalse(state['plans'][0]['items']);self.assertEqual(state['plans'][0]['minutes'],30)
        server.validate_backup(json.dumps(state))
