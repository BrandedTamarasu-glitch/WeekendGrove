import json
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import closing
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import clean_idea, estimates, generate
import server

def idea(id, duration=60, cost=10, energy='low', archived=0):
    return dict(id=id, title=f'Generic idea {id}', category='Activities', duration=duration, cost=cost, energy=energy, archived=archived, sample=0, location='')


def strip_discovery(data):
    data.pop('discovery',None)
    for i in data['ideas']:i.pop('metadata',None)
    for p in data['plans']:
        for i in p['items']:i.pop('metadata',None)

class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.limits = dict(minutes=180, budget=40, energy='medium', count=3)

    def test_empty_and_no_match(self):
        self.assertEqual(generate([], self.limits)['items'], [])
        self.assertEqual(generate([idea(1, 500), idea(2,cost=100), idea(3,energy='high'), idea(4,archived=1)], self.limits)['items'], [])

    def test_repeated_reroll_preserves_locks_and_limits(self):
        ideas = [idea(i, 30+i*5, i*2) for i in range(1, 12)]
        previous = []
        for seed in range(200):
            plan = generate(ideas, dict(self.limits, locked=[1], previous=previous), random.Random(seed))
            ids = [i['id'] for i in plan['items']]
            self.assertIn(1, ids)
            self.assertEqual(len(ids), len(set(ids)))
            self.assertLessEqual(plan['minutes'], self.limits['minutes'])
            self.assertLessEqual(plan['cost'], self.limits['budget'])
            self.assertLessEqual(len(ids), 3)
            previous = ids

    def test_reroll_uses_alternatives(self):
        plan = generate([idea(i) for i in range(1, 7)], dict(self.limits, locked=[1], previous=[1,2,3]), random.Random(1))
        self.assertEqual(len(plan['items']),3)
        self.assertTrue({i['id'] for i in plan['items']}.isdisjoint({2,3}))

    def test_full_locks_and_small_bank(self):
        data = dict(self.limits, locked=[1,2,3], previous=[1,2,3])
        self.assertEqual([i['id'] for i in generate([idea(i) for i in range(1,4)],data)['items']], [1,2,3])
        self.assertEqual(len(generate([idea(1)],self.limits)['items']),1)

    def test_invalid_locks(self):
        for extra in [dict(locked=[99]),dict(locked=[1,1]),dict(locked=[1],budget=0),dict(locked=[1],minutes=5),dict(locked=[1],energy='low')]:
            with self.assertRaises(ValueError):
                generate([idea(1, energy='medium')],dict(self.limits,**extra))

    def test_estimates_and_zero_cost(self):
        self.assertEqual(estimates(idea(1,None,None,None)),(60,20,'medium'))
        self.assertEqual(estimates(idea(1,cost=0))[1],0)
        result = generate([idea(1,None,None,None)],dict(self.limits,energy='low'))
        self.assertEqual(result['items'],[])

    def test_decimal_cost_boundary(self):
        result = generate([idea(1,cost=.1),idea(2,cost=.2)],dict(self.limits,budget=.3))
        self.assertEqual(len(result['items']),2)
        self.assertEqual(result['cost'],.3)
        with self.assertRaises(ValueError):
            generate([idea(1,cost=.01)],dict(self.limits,budget=.006))

    def test_validation(self):
        valid = dict(title=' Test ', category='Projects', duration=None, cost=None, energy=None)
        self.assertEqual(clean_idea(valid)['title'],'Test')
        for field,value in [('title',' '),('category','Other'),('duration',-1),('duration',1.5),('cost',-1),('cost',float('nan')),('energy','extreme')]:
            with self.assertRaises(ValueError): clean_idea(dict(valid,**{field:value}))

    def test_custom_estimates_and_locked_slots(self):
        defaults = dict(duration=30,cost=5,energy='low')
        result = generate([idea(1,None,None,None)],dict(self.limits,energy='low'),defaults=defaults)
        self.assertEqual((result['minutes'],result['cost'],result['defaults']),(30,5,defaults))
        result = generate([idea(i) for i in range(1,7)],dict(self.limits,locked=[2],previous=[1,2,3]),random.Random(1))
        self.assertEqual(result['items'][1]['id'],2)
        for defaults in [{},dict(duration=None,cost=20,energy='medium'),dict(duration=30,cost=-1,energy='low')]:
            with self.assertRaises(ValueError): generate([],self.limits,defaults=defaults)

class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = server.DB
        server.DB = Path(self.temp.name)/'source'/'weekend.sqlite3'
        server.initialize()
        with server.connect() as db:
            values = dict(idea(1,None,None,None),uid=str(uuid.uuid4()),title='Generic <雨> & picnic',location='At home',archived=0)
            db.execute('INSERT INTO ideas(id,uid,title,category,duration,cost,location,energy,archived,sample) VALUES (:id,:uid,:title,:category,:duration,:cost,:location,:energy,:archived,:sample)',values)
            demo = dict(idea(2,45,0,'low',1),uid=str(uuid.uuid4()),sample=1)
            db.execute('INSERT INTO ideas(id,uid,title,category,duration,cost,location,energy,archived,sample) VALUES (:id,:uid,:title,:category,:duration,:cost,:location,:energy,:archived,:sample)',demo)
            defaults = dict(duration=30,cost=7.25,energy='low')
            db.execute("UPDATE settings SET value=? WHERE key='defaults'",(json.dumps(defaults),))
            payload = server.generate([values],dict(minutes=120,budget=20,energy='low',count=1),defaults=defaults)
            db.execute('INSERT INTO plans(uid,name,created,payload) VALUES (?,?,?,?)',(str(uuid.uuid4()),'Generic snapshot','2026-10-01T10:00:00+00:00',json.dumps(payload)))
            # A saved snapshot is deliberately different from its current source idea.
            db.execute("UPDATE ideas SET title='Generic edited idea',archived=1 WHERE id=1")
        with server.connect() as db: self.source = server.export_state(db)
        self.text = json.dumps(self.source,ensure_ascii=False)
        server.DB = Path(self.temp.name)/'target'/'weekend.sqlite3'
        server.initialize()

    def tearDown(self):
        server.DB = self.original_db
        self.temp.cleanup()

    def test_lossless_roundtrip_and_repeat(self):
        backup = server.validate_backup(self.text)
        with server.connect() as db:
            before = server.export_state(db)
            summary = server.restore_summary(db,backup)
            self.assertEqual(server.export_state(db),before)
            self.assertEqual((summary['ideas_to_add'],summary['plans_to_add']),(2,1))
            result = server.restore_backup(db,backup,True)
            self.assertTrue(result['defaults_applied'])
        with server.connect() as db:
            self.assertEqual(server.export_state(db),self.source)
            result = server.restore_backup(db,backup,True)
            self.assertEqual((result['ideas_to_add'],result['plans_to_add']),(0,0))
        with server.connect() as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(server.export_state(db),self.source)

    def test_merge_preserves_edits_and_remaps_snapshot_ids(self):
        original = self.source['ideas'][1]
        with server.connect() as db:
            db.execute('INSERT INTO ideas(uid,title,category) VALUES (?,?,?)',(str(uuid.uuid4()),'Existing unrelated own idea','Projects'))
            db.execute('INSERT INTO ideas(uid,title,category) VALUES (?,?,?)',(original['uid'],'Existing user edit','Activities'))
        with server.connect() as db:
            settings = server.defaults_from(db)
            summary = server.restore_backup(db,server.validate_backup(self.text))
            self.assertEqual((summary['ideas_to_add'],summary['ideas_skipped']),(1,1))
        with server.connect() as db:
            exported = server.export_state(db)
            own = next(i for i in exported['ideas'] if i['uid']==original['uid'])
            self.assertEqual(own['title'],'Existing user edit')
            snapshot = exported['plans'][0]['items'][0]
            self.assertEqual(snapshot['title'],'Generic <雨> & picnic')
            self.assertEqual(snapshot['id'],own['id'])
            self.assertEqual(snapshot['uid'],own['uid'])
            self.assertEqual(exported['defaults'],settings)
            # The merged database can itself be exported and restored without loss.
            server.validate_backup(json.dumps(exported))

    def test_malformed_backup_is_atomic(self):
        corruptions = []
        for mutate in [
            lambda b:b.update(version=99),
            lambda b:b['ideas'][0].update(cost=-1),
            lambda b:b['ideas'][0].update(archived=True),
            lambda b:b['ideas'][0].update(uid='broken'),
            lambda b:b['ideas'][0].update(title=''),
            lambda b:b['ideas'][0].update(location=['unexpected']),
            lambda b:b['ideas'].append(b['ideas'][0].copy()),
            lambda b:b['plans'][0].update(minutes=999),
            lambda b:b['plans'][0]['items'][0].update(id=999),
            lambda b:b['plans'][0].update(extra='future unsupported field'),
            lambda b:b['defaults'].update(cost=None),
        ]:
            data = json.loads(self.text); mutate(data); corruptions.append(json.dumps(data))
        corruptions += ['not json','{"version":2,"version":2}',self.text.replace('7.25','NaN'), 'x'*(server.MAX_BACKUP+1)]
        with server.connect() as db:
            before = server.export_state(db)
            for text in corruptions:
                with self.subTest(text=text[:70]):
                    with self.assertRaises((ValueError,TypeError)):
                        server.restore_backup(db,server.validate_backup(text))
                    self.assertEqual(server.export_state(db),before)

    def test_legacy_v1_import(self):
        legacy = json.loads(self.text)
        strip_discovery(legacy); legacy['version']=1; legacy.pop('defaults')
        legacy.pop('currency'); legacy.pop('currency_assumed')
        for i in legacy['ideas']: i.pop('uid')
        for p in legacy['plans']:
            p.pop('schedule',None)
            p.pop('uid'); p.pop('defaults')
            p.pop('currency'); p.pop('currency_assumed')
            # v1 always used the original fixed estimates.
            p['minutes']=60; p['cost']=20
            p['limits']['energy']='medium'
            for i in p['items']: i.pop('uid')
        text=json.dumps(legacy)
        with server.connect() as db: server.restore_backup(db,server.validate_backup(text))
        with server.connect() as db:
            result=server.restore_backup(db,server.validate_backup(text))
            self.assertEqual((result['ideas_to_add'],result['plans_to_add']),(0,0))
            exported=server.export_state(db)
            self.assertEqual(exported['plans'][0]['defaults'],server.DEFAULTS)
            self.assertEqual(exported['ideas'][0]['archived'],1)

    def test_v1_schema_migration_keeps_safety_backup(self):
        server.DB=Path(self.temp.name)/'old.sqlite3'
        with closing(sqlite3.connect(server.DB)) as db:
            db.executescript('CREATE TABLE ideas(id INTEGER PRIMARY KEY,title TEXT,category TEXT,duration INTEGER,cost REAL,location TEXT,energy TEXT,archived INTEGER,sample INTEGER); CREATE TABLE plans(id INTEGER PRIMARY KEY,name TEXT,created TEXT,payload TEXT);')
            db.execute('INSERT INTO ideas VALUES (1,?,?,?,?,?,?,?,?)',('Existing generic idea','Places',None,None,'',None,0,0))
            db.commit()
        server.initialize()
        with server.connect() as db:
            record=server.export_state(db)['ideas'][0]
            self.assertEqual(record['title'],'Existing generic idea')
            first_uid=record['uid']
        server.initialize()
        with server.connect() as db: self.assertEqual(server.export_state(db)['ideas'][0]['uid'],first_uid)
        with closing(sqlite3.connect(Path(self.temp.name)/'before-upgrade-v2.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT title FROM ideas').fetchone()[0],'Existing generic idea')
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); cls.port = sock.getsockname()[1]
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = f'http://127.0.0.1:{cls.port}'
        cls.start()

    @classmethod
    def start(cls):
        cls.proc = subprocess.Popen([sys.executable, 'server.py','--port',str(cls.port)], cwd=Path(__file__).resolve().parents[1], env=dict(os.environ,DATA_DIR=cls.temp.name), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try: urllib.request.urlopen(cls.base+'/api/state',timeout=1); return
            except OSError: time.sleep(.05)
        raise RuntimeError('Server failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate(); cls.proc.wait(timeout=5); cls.temp.cleanup()

    def request(self,path,data=None,headers=None):
        headers = headers or {}
        if data is not None: headers['Content-Type']='application/json'
        request = urllib.request.Request(self.base+path, data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with urllib.request.urlopen(request) as response: return json.load(response)

    def test_durable_crud_plans_export_backup(self):
        self.assertEqual(self.request('/api/state')['ideas'],[])
        payload = dict(title='<Generic & title>',category='Projects',duration=30,cost=0,energy='low',location='At home')
        self.request('/api/ideas',payload)
        saved = self.request('/api/state')['ideas'][0]
        self.request('/api/ideas',dict(payload,id=saved['id'],title='Edited generic idea'))
        self.request('/api/archive',dict(id=saved['id'],archived=True))
        limits = dict(minutes=120,budget=20,energy='low',count=3)
        self.assertEqual(self.request('/api/generate',limits)['items'],[])
        self.request('/api/archive',dict(id=saved['id'],archived=False))
        generated = self.request('/api/generate',limits)
        self.request('/api/plans',dict(name='Generic saved weekend',ids=[saved['id']],limits=generated['limits']))
        self.request('/api/ideas',dict(payload,id=saved['id'],title='Changed after saving'))
        self.proc.terminate(); self.proc.wait(timeout=5); self.start()
        state = self.request('/api/state')
        self.assertEqual(state['ideas'][0]['title'],'Changed after saving')
        self.assertEqual(state['plans'][0]['items'][0]['title'],'Edited generic idea')
        self.assertEqual(state,self.request('/api/export'))
        backup = Path(self.temp.name)/'check.sqlite3'
        backup.write_bytes(urllib.request.urlopen(self.base+'/api/backup').read())
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM plans').fetchone()[0],1)
        self.request('/api/samples',{})
        self.request('/api/samples',{})
        self.assertEqual(len(self.request('/api/state')['ideas']),9)

    def test_reject_cross_origin_and_host(self):
        for headers in [{'Origin':'https://unrelated.example'}, {'Host':'unrelated.example'}]:
            with self.assertRaises(urllib.error.HTTPError) as context:
                self.request('/api/ideas',dict(title='Generic',category='Places'),headers)
            self.assertEqual(context.exception.code,403)
            context.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request('/api/ideas',dict(title='',category='Places'))
        self.assertEqual(context.exception.code,400)
        context.exception.close()

    def test_estimate_snapshots_stale_save_and_demo_controls(self):
        self.request('/api/ideas',dict(title='Generic unknown details',category='Activities',duration=None,cost=None,energy=None))
        captured=self.request('/api/state')['ideas'][0]
        defaults=dict(duration=25,cost=3.25,energy='low')
        self.request('/api/defaults',defaults)
        limits=dict(minutes=120,budget=20,energy='low',count=1,locked=[captured['id']],include_samples=False)
        plan=self.request('/api/generate',limits)
        self.assertEqual((plan['minutes'],plan['cost']),(25,3.25))
        self.request('/api/defaults',dict(duration=80,cost=9,energy='high'))
        self.request('/api/plans',dict(name='Generic estimate snapshot',ids=[captured['id']],expected_items=plan['items'],defaults=plan['defaults'],limits=plan['limits']))
        saved=self.request('/api/state')['plans'][0]
        self.assertEqual(saved['defaults'],defaults)
        self.request('/api/ideas',dict(captured,title='Generic edited after generation'))
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request('/api/plans',dict(name='Should not save stale preview',ids=[captured['id']],expected_items=plan['items'],defaults=plan['defaults'],limits=plan['limits']))
        self.assertEqual(context.exception.code,400); context.exception.close()
        sample=next(i for i in self.request('/api/state')['ideas'] if i['sample'])
        self.request('/api/ideas',dict(sample,title='Generic personalized demo'))
        edited=next(i for i in self.request('/api/state')['ideas'] if i['id']==sample['id'])
        self.assertEqual(edited['sample'],0)
        self.request('/api/archive-samples',{})
        state=self.request('/api/state')
        self.assertTrue(all(i['archived'] for i in state['ideas'] if i['sample']))
        self.assertFalse(next(i for i in state['ideas'] if i['id']==sample['id'])['archived'])
        self.proc.terminate(); self.proc.wait(timeout=5); self.start()
        self.assertEqual(self.request('/api/state')['defaults'],dict(duration=80,cost=9,energy='high'))

    def test_restore_preview_and_repeat_http(self):
        text=json.dumps(self.request('/api/export'))
        before=self.request('/api/state')
        preview=self.request('/api/restore/preview',dict(backup_text=text))
        self.assertEqual(self.request('/api/state'),before)
        self.assertEqual((preview['ideas_to_add'],preview['plans_to_add']),(0,0))
        result=self.request('/api/restore',dict(backup_text=text,digest=preview['digest'],apply_defaults=False))
        self.assertEqual(result['ideas_to_add'],0)
        self.assertEqual(self.request('/api/state'),before)
        for payload in [dict(backup_text=text,digest='wrong',apply_defaults=False),dict(backup_text='broken')]:
            with self.assertRaises(urllib.error.HTTPError) as context: self.request('/api/restore',payload)
            self.assertEqual(context.exception.code,400); context.exception.close()
            self.assertEqual(self.request('/api/state'),before)

class CurrencyTests(unittest.TestCase):
    setUp = RestoreTests.setUp
    tearDown = RestoreTests.tearDown

    def test_budget_selection_and_numeric_values_unchanged(self):
        ideas=[idea(1,cost=12.34),idea(2,cost=0),idea(3,cost=25)]
        limits=dict(minutes=120,budget=20,energy='low',count=2,locked=[1])
        expected=None
        for currency in server.CURRENCIES:
            plan=server.generate(ideas,limits,random.Random(5),currency=currency)
            result=(plan['items'],plan['minutes'],plan['cost'],plan['limits'],plan['defaults'])
            if expected is None: expected=result
            self.assertEqual(result,expected)
            self.assertEqual(plan['currency'],currency)
            self.assertFalse(plan['currency_assumed'])
        for currency in ['usd','JPY','BTC','<script>',None,True]:
            with self.assertRaises(ValueError): server.clean_currency(currency)

    def test_v2_migration_keeps_amounts_and_marks_assumptions(self):
        with server.connect() as db: server.restore_backup(db,server.validate_backup(self.text),True)
        with server.connect() as db:
            db.execute("DELETE FROM settings WHERE key IN ('currency','currency_assumed')")
            for row in db.execute('SELECT id,payload FROM plans').fetchall():
                payload=json.loads(row['payload']); payload.pop('currency'); payload.pop('currency_assumed')
                db.execute('UPDATE plans SET payload=? WHERE id=?',(json.dumps(payload),row['id']))
        server.initialize()
        with server.connect() as db:
            after=server.export_state(db)
            self.assertEqual(after['ideas'],self.source['ideas'])
            self.assertEqual(after['defaults'],self.source['defaults'])
            self.assertEqual((after['currency'],after['currency_assumed']),('USD',True))
            saved=after['plans'][0]
            self.assertEqual((saved['currency'],saved['currency_assumed']),('USD',True))
            for key in ('items','cost','minutes','limits','defaults','uid','name','created'): self.assertEqual(saved[key],self.source['plans'][0][key])
        with closing(sqlite3.connect(server.DB.parent/'before-upgrade-v3.sqlite3')) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(db.execute("SELECT 1 FROM settings WHERE key='currency'").fetchone())
        server.initialize()
        with server.connect() as db: self.assertEqual(server.export_state(db),after)

    def test_cross_currency_merge_requires_acknowledgment(self):
        source=json.loads(self.text); source['currency']='EUR'; source['plans'][0]['currency']='GBP'
        backup=server.validate_backup(json.dumps(source))
        with server.connect() as db:
            before=server.export_state(db); preview=server.restore_summary(db,backup)
            self.assertTrue(preview['currency_mismatch'])
            self.assertEqual((preview['currency'],preview['current_currency']),('EUR','USD'))
        with self.assertRaises(ValueError):
            with server.connect() as db: server.restore_backup(db,backup)
        with server.connect() as db: self.assertEqual(server.export_state(db),before)
        with server.connect() as db: server.restore_backup(db,backup,False,True)
        with server.connect() as db:
            after=server.export_state(db)
            self.assertEqual(after['currency'],'USD')
            self.assertEqual(after['plans'][0]['currency'],'GBP')
            self.assertEqual(after['ideas'],source['ideas'])
            self.assertEqual(after['plans'][0]['cost'],source['plans'][0]['cost'])
            server.validate_backup(json.dumps(after))

    def test_restore_currency_settings_and_snapshot_roundtrip(self):
        source=json.loads(self.text); source['currency']='EUR'; source['plans'][0]['currency']='GBP'
        backup=server.validate_backup(json.dumps(source))
        with server.connect() as db:
            db.execute('INSERT INTO ideas(uid,title,category,cost) VALUES (?,?,?,?)',(str(uuid.uuid4()),'Existing numeric amount','Projects',17.25))
        with server.connect() as db: server.restore_backup(db,backup,True,True)
        with server.connect() as db:
            after=server.export_state(db)
            self.assertEqual((after['currency'],after['currency_assumed']),('EUR',False))
            self.assertEqual(next(i['cost'] for i in after['ideas'] if i['title']=='Existing numeric amount'),17.25)
            self.assertEqual(after['plans'][0],source['plans'][0] | {'items':[dict(source['plans'][0]['items'][0],id=2)],'schedule':[dict(e,id=2) for e in source['plans'][0]['schedule']]})
            # IDs remap when merging, while all snapshot fields and currencies survive.
            new_backup=server.validate_backup(json.dumps(after))
        server.DB=Path(self.temp.name)/'currency-roundtrip'/'weekend.sqlite3'; server.initialize()
        with server.connect() as db: server.restore_backup(db,new_backup,True,True)
        with server.connect() as db: self.assertEqual(server.export_state(db),after)

    def test_legacy_v2_currency_is_explicitly_assumed(self):
        data=json.loads(self.text); strip_discovery(data); data['version']=2
        for p in data['plans']: p.pop('schedule',None)
        data.pop('currency'); data.pop('currency_assumed')
        for plan in data['plans']: plan.pop('currency'); plan.pop('currency_assumed')
        backup=server.validate_backup(json.dumps(data))
        self.assertEqual((backup['currency'],backup['currency_assumed']),('USD',True))
        self.assertEqual((backup['plans'][0]['currency'],backup['plans'][0]['currency_assumed']),('USD',True))
        with server.connect() as db: server.restore_backup(db,backup,True)
        with server.connect() as db:
            result=server.restore_backup(db,backup,True)
            self.assertEqual((result['ideas_to_add'],result['plans_to_add']),(0,0))

    def test_currency_backup_validation_is_atomic(self):
        for field,value in [('currency','JPY'),('currency',None),('currency_assumed',1)]:
            data=json.loads(self.text); data[field]=value
            with self.assertRaises(ValueError): server.validate_backup(json.dumps(data))
        for field,value in [('currency','OTHER'),('currency_assumed','false')]:
            data=json.loads(self.text); data['plans'][0][field]=value
            with self.assertRaises(ValueError): server.validate_backup(json.dumps(data))
        with server.connect() as db: self.assertEqual(server.export_state(db)['ideas'],[])

class CurrencyIntegrationTests(unittest.TestCase):
    setUpClass = classmethod(IntegrationTests.setUpClass.__func__)
    start = classmethod(IntegrationTests.start.__func__)
    tearDownClass = classmethod(IntegrationTests.tearDownClass.__func__)
    request = IntegrationTests.request

    def test_currency_persistence_and_preview_snapshot(self):
        self.assertEqual(self.request('/api/state')['currency'],'USD')
        self.request('/api/ideas',dict(title='Generic priced idea',category='Restaurants',duration=45,cost=12.34,energy='low'))
        captured=self.request('/api/state')['ideas'][0]
        limits=dict(minutes=60,budget=20,energy='low',count=1,locked=[captured['id']])
        preview=self.request('/api/generate',limits)
        self.request('/api/currency',dict(currency='EUR'))
        self.request('/api/plans',dict(name='USD preview after currency change',ids=[captured['id']],expected_items=preview['items'],defaults=preview['defaults'],limits=preview['limits'],currency=preview['currency'],currency_assumed=preview['currency_assumed']))
        euro=self.request('/api/generate',limits)
        self.assertEqual((euro['cost'],euro['limits']['budget'],euro['items']),(preview['cost'],20,preview['items']))
        self.assertEqual(euro['currency'],'EUR')
        before=self.request('/api/state')
        for currency in ['JPY','usd',None]:
            with self.assertRaises(urllib.error.HTTPError) as context: self.request('/api/currency',dict(currency=currency))
            self.assertEqual(context.exception.code,400); context.exception.close()
            self.assertEqual(self.request('/api/state'),before)
        self.proc.terminate(); self.proc.wait(timeout=5); self.start()
        after=self.request('/api/state')
        self.assertEqual(after,before)
        self.assertEqual(after['currency'],'EUR'); self.assertFalse(after['currency_assumed'])
        self.assertEqual(after['plans'][0]['currency'],'USD')
        self.assertEqual(after['ideas'][0]['cost'],12.34)
        self.assertEqual(self.request('/api/export'),after)
        server.validate_backup(json.dumps(after))

    def test_restore_currency_acknowledgment_http(self):
        source=self.request('/api/export'); source['currency']='GBP'
        text=json.dumps(source); before=self.request('/api/state')
        preview=self.request('/api/restore/preview',dict(backup_text=text))
        self.assertTrue(preview['currency_mismatch'])
        payload=dict(backup_text=text,digest=preview['digest'],apply_defaults=True)
        with self.assertRaises(urllib.error.HTTPError) as context: self.request('/api/restore',payload)
        self.assertEqual(context.exception.code,400); context.exception.close()
        self.assertEqual(self.request('/api/state'),before)
        self.request('/api/restore',dict(payload,acknowledge_relabel=True))
        after=self.request('/api/state')
        self.assertEqual(after['currency'],'GBP')
        self.assertEqual(after['ideas'],before['ideas'])
        self.assertEqual(after['plans'],before['plans'])

if __name__ == '__main__': unittest.main()
