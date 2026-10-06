import copy
import json
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

import server
from test_app import idea


class PlanBTests(unittest.TestCase):
    def setUp(self):
        self.ideas = [dict(idea(i, 30, 5), environment='outdoor' if i == 1 else 'indoor') for i in range(1, 7)]
        self.limits = dict(minutes=100, budget=20, energy='medium', count=2, include_lazy=True,
                           day_caps={d: {c: 2 for c in server.CATEGORIES} for d in server.DAYS})
        self.plan = server.generate(self.ideas[:2], dict(self.limits, locked=[1,2]), random.Random(2))
        self.request = dict(plan=self.plan, target_id=1, locked=[2], include_samples=False)

    def test_explicit_swap_and_undo_preserve_other_items_and_lazy_time(self):
        original = copy.deepcopy(self.plan)
        response = server.plan_b(self.ideas, self.request)
        self.assertEqual([i['id'] for i in response['alternatives']], [3,4,5,6])
        self.assertEqual(self.plan, original)
        swapped = server.plan_b(self.ideas, dict(self.request, replacement_id=3))['plan']
        self.assertEqual(swapped['items'][1], original['items'][1])
        self.assertEqual(swapped['schedule'][1:], original['schedule'][1:])
        restored = server.plan_b(self.ideas, dict(self.request, plan=swapped, target_id=3, replacement_id=1, undo=True))['plan']
        self.assertEqual(restored, original)
        with self.assertRaises(ValueError):
            server.plan_b(self.ideas, dict(self.request, plan=swapped, replacement_id=3))

    def test_locked_target_rejected_even_for_undo(self):
        for undo in (False, True):
            with self.assertRaisesRegex(ValueError, 'Unlock'):
                server.plan_b(self.ideas, dict(self.request, locked=[1,2], replacement_id=3, undo=undo))

    def test_current_snapshot_and_constraints_rechecked(self):
        mutations = [dict(duration=500), dict(cost=1000), dict(energy='high'), dict(archived=1), dict(sample=1)]
        for mutation in mutations:
            bank = copy.deepcopy(self.ideas)
            bank[2].update(mutation)
            self.assertNotIn(3, [i['id'] for i in server.plan_b(bank, self.request)['alternatives']])
            with self.assertRaises(ValueError):
                server.plan_b(bank, dict(self.request, replacement_id=3))
        bank = copy.deepcopy(self.ideas)
        bank[0]['title'] = 'Edited since preview'
        with self.assertRaisesRegex(ValueError, 'changed'):
            server.plan_b(bank, self.request)
        forged = copy.deepcopy(self.plan)
        forged['minutes'] = 1
        with self.assertRaisesRegex(ValueError, 'totals'):
            server.plan_b(self.ideas, dict(self.request, plan=forged))

    def test_no_duplicates_unknown_or_outdoor_and_daily_caps(self):
        bank = copy.deepcopy(self.ideas)
        for row, environment in zip(bank[2:], ['unknown', 'mixed', 'outdoor', 'indoor']):
            row['environment'] = environment
        self.assertEqual([i['id'] for i in server.plan_b(bank, self.request)['alternatives']], [6])
        for replacement in (1,2,3,4,5):
            with self.assertRaises(ValueError):
                server.plan_b(bank, dict(self.request, replacement_id=replacement))
        bank[5]['category'] = 'Projects'
        plan = copy.deepcopy(self.plan)
        for d in server.DAYS: plan['limits']['day_caps'][d]['Projects'] = 0
        self.assertEqual(server.plan_b(bank, dict(self.request, plan=plan))['alternatives'], [])

    def test_day_eligibility_is_checked_for_original_day(self):
        import discovery
        actual = discovery.eligible
        def eligibility(item, day, limits, historical=False):
            return False if item['id'] == 3 else actual(item, day, limits, historical=historical)
        with patch.object(discovery, 'eligible', eligibility):
            self.assertNotIn(3, [i['id'] for i in server.plan_b(self.ideas, self.request)['alternatives']])
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                server.plan_b(self.ideas, dict(self.request, replacement_id=3))

    def test_malformed_limits_fail_with_validation_error(self):
        for value in [None, [], 'bad']:
            broken = copy.deepcopy(self.plan)
            broken['limits'] = value
            with self.assertRaisesRegex(ValueError, 'valid planning limits'):
                server.plan_b(self.ideas, dict(self.request, plan=broken))

    def test_environment_validation_and_default(self):
        self.assertEqual(server.clean_idea(idea(1))['environment'], 'unknown')
        for value in ['indoor','outdoor','mixed','unknown']:
            self.assertEqual(server.clean_idea(dict(idea(1), environment=value))['environment'], value)
        for value in [None, '', 'inside', 1]:
            with self.assertRaises(ValueError): server.clean_idea(dict(idea(1), environment=value))


class EnvironmentMigrationTests(unittest.TestCase):
    def test_migration_backup_and_historical_snapshot_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DB', Path(tmp)/'weekend.sqlite3'):
            server.initialize()
            with server.connect() as db:
                db.execute("INSERT INTO ideas(uid,title,category,energy) VALUES ('01234567-1234-4234-8234-123456789012','Generic','Activities','low')")
                record = server.discovery.idea_row(db.execute('SELECT * FROM ideas').fetchone())
                record.pop('environment')
                plan = server.generate([record], dict(minutes=100, budget=100, energy='low', count=1), random.Random(1))
                raw = json.dumps(plan)
                db.execute('INSERT INTO plans(uid,name,created,payload) VALUES (?,?,?,?)', ('01234567-1234-4234-8234-123456789013','Example','2026-10-01T00:00:00+00:00',raw))
                db.execute('ALTER TABLE ideas DROP COLUMN environment')
            server.initialize()
            with server.connect() as db:
                self.assertEqual(db.execute('SELECT environment FROM ideas').fetchone()[0], 'unknown')
                self.assertEqual(db.execute('SELECT payload FROM plans').fetchone()[0], raw)
                export = server.export_state(db)
            self.assertEqual(export['version'], 6)
            self.assertNotIn('environment', export['plans'][0]['items'][0])
            validated = server.validate_backup(json.dumps(export))
            self.assertEqual(validated['ideas'][0]['environment'], 'unknown')
            legacy = copy.deepcopy(export); legacy['version'] = 5
            for row in legacy['ideas']: row.pop('environment')
            validated_legacy = server.validate_backup(json.dumps(legacy))
            self.assertEqual(validated_legacy['ideas'][0]['environment'], 'unknown')
            self.assertNotIn('environment', validated_legacy['plans'][0]['items'][0])
            safety = Path(tmp)/'before-upgrade-v6.sqlite3'
            self.assertTrue(safety.exists())
            with closing(sqlite3.connect(safety)) as db:
                self.assertNotIn('environment', [r[1] for r in db.execute('PRAGMA table_info(ideas)')])
            before = safety.read_bytes(); server.initialize(); self.assertEqual(safety.read_bytes(), before)

class PlanBHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_app import IntegrationTests
        IntegrationTests.setUpClass.__func__(cls)

    @classmethod
    def start(cls):
        from test_app import IntegrationTests
        IntegrationTests.start.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from test_app import IntegrationTests
        IntegrationTests.tearDownClass.__func__(cls)

    def request(self, *args, **kwargs):
        from test_app import IntegrationTests
        return IntegrationTests.request(self, *args, **kwargs)

    def test_api_metadata_swap_does_not_write_and_restore_is_repeatable(self):
        for number, environment in enumerate(['outdoor', 'indoor'], 1):
            self.request('/api/ideas', dict(idea(number, 30, 0), id=None, environment=environment))
        bank = self.request('/api/state')['ideas']
        outdoor = next(i for i in bank if i['environment'] == 'outdoor')
        indoor = next(i for i in bank if i['environment'] == 'indoor')
        plan = self.request('/api/generate', dict(minutes=60, budget=0, energy='low', count=1, locked=[outdoor['id']]))
        legacy_edit = dict(outdoor)
        legacy_edit.pop('environment')
        self.request('/api/ideas', legacy_edit)
        self.assertEqual(next(i for i in self.request('/api/state')['ideas'] if i['id'] == outdoor['id'])['environment'], 'outdoor')
        before = self.request('/api/export')
        swapped = self.request('/api/plan-b', dict(plan=plan, locked=[], target_id=outdoor['id'], replacement_id=indoor['id']))['plan']
        self.assertEqual(swapped['items'][0]['id'], indoor['id'])
        self.assertEqual(self.request('/api/export'), before)
        text = json.dumps(before)
        preview = self.request('/api/restore/preview', dict(backup_text=text))
        for _ in range(2):
            self.request('/api/restore', dict(backup_text=text, digest=preview['digest'], apply_defaults=False))
        self.assertEqual(self.request('/api/export'), before)


if __name__ == '__main__': unittest.main()
