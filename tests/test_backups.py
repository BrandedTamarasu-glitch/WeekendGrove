import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import backups
import server
import discovery
import test_discovery


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.data = self.root/'data'; self.data.mkdir()
        self.dest = self.root/'copies'; self.dest.mkdir()
        self.db = self.data/'weekend.sqlite3'
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('create table records(id integer primary key, value text)')
            db.execute("insert into records values(1,'Original fixture')"); db.commit()
        self.manager = backups.Manager(self.db, self.dest)

    def test_default_disabled_no_writes_and_unconfigured_activation_rejected(self):
        missing = backups.Manager(self.db)
        self.assertFalse(missing.view()['configured'])
        self.assertFalse(self.manager.run(scheduled=True))
        self.assertEqual(list(self.dest.iterdir()), [])
        self.assertFalse(self.manager.view()['settings']['enabled'])
        with self.assertRaises(ValueError): missing.configure(dict(settings=dict(backups.DEFAULT,enabled=True),approve_schedule=True))
        with self.assertRaises(ValueError): self.manager.configure(dict(settings=dict(backups.DEFAULT,enabled=True)))
        with self.assertRaises(ValueError): self.manager.configure(dict(settings=dict(backups.DEFAULT,prune=True)))
        with patch('backups.fcntl',None):self.assertFalse(self.manager.view()['configured'])

    def test_consistent_backup_excludes_files_and_is_private(self):
        (self.data/'secrets').mkdir(); (self.data/'secrets'/'dummy.key').write_text('TEST_SECRET_NEVER_COPY_ABC')
        self.assertTrue(self.manager.run())
        result = self.manager.read(); target=self.dest/result['files'][0]['name']
        self.assertEqual(target.stat().st_mode & 0o777,0o600)
        self.assertNotIn(b'TEST_SECRET_NEVER_COPY_ABC',target.read_bytes())
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('pragma integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('select * from records').fetchall(),[(1,'Original fixture')])
        self.assertFalse(result['settings']['enabled']); self.assertTrue(result['last_success'])
        self.assertFalse(list(self.dest.glob('.grove-incomplete-*')))

    def test_failure_preserves_success_and_never_prunes(self):
        self.assertTrue(self.manager.run()); old=list(self.dest.iterdir())
        self.manager.configure(dict(settings=dict(backups.DEFAULT,prune=True,keep=1),approve_deletion=True))
        with patch('backups.os.link',side_effect=OSError('disk full')): self.assertFalse(self.manager.run())
        status=self.manager.view()
        self.assertTrue(status['last_success']); self.assertIn('Backup failed',status['error'])
        self.assertEqual(list(self.dest.iterdir()),old)

    def test_retention_only_owned_unchanged_files(self):
        manual=self.dest/'manual.sqlite3';manual.write_text('keep')
        migration=self.dest/'before-upgrade-v6.sqlite3';migration.write_text('keep')
        impostor=self.dest/('grove-auto-'+'1'*32+'.sqlite3');impostor.write_text('keep')
        self.assertTrue(self.manager.run()); first=self.dest/self.manager.read()['files'][0]['name']
        self.assertTrue(self.manager.run()); second=self.dest/self.manager.read()['files'][1]['name']
        first.write_text('User changed this copy')
        self.manager.configure(dict(settings=dict(backups.DEFAULT,prune=True,keep=1),approve_deletion=True))
        self.assertTrue(self.manager.run())
        self.assertTrue(first.exists());self.assertFalse(second.exists())
        self.assertTrue(all(p.exists() for p in (manual,migration,impostor)))
        self.assertIn('kept',self.manager.view()['warning'])

    def test_overlap_symlink_and_invalid_config_fail_closed(self):
        with self.manager.exclusive():
            with self.assertRaisesRegex(ValueError,'already running'): self.manager.run()
        link=self.root/'link';link.symlink_to(self.dest,target_is_directory=True)
        self.assertFalse(backups.Manager(self.db,link).run())
        self.assertFalse(backups.Manager(self.db,self.data).run())
        self.manager.control.write_text('broken')
        with self.assertRaisesRegex(ValueError,'stopped'): self.manager.run(scheduled=True)

    def test_destination_change_requires_new_approval(self):
        self.manager.configure(dict(settings=dict(backups.DEFAULT,enabled=True,prune=True),approve_schedule=True,approve_deletion=True))
        other=self.root/'other';other.mkdir();changed=backups.Manager(self.db,other)
        self.assertFalse(changed.run(scheduled=True,now=datetime.now(timezone.utc)+timedelta(days=2)))
        self.assertFalse(changed.view()['settings']['enabled'])
        self.assertFalse(changed.view()['settings']['prune'])
        self.assertEqual(list(other.iterdir()),[])

    def test_corrupt_source_and_interrupted_status(self):
        self.db.write_bytes(b'not a database')
        self.assertFalse(self.manager.run())
        self.assertEqual(list(self.dest.iterdir()),[])
        value=self.manager.read();value.update(running=True,error='');self.manager.write(value)
        self.assertIn('interrupted',self.manager.view()['status'])
        with self.manager.exclusive():self.assertEqual(self.manager.view()['status'],'running')

    def test_missing_destination_can_be_paused_and_interrupted_copy_is_not_published(self):
        self.manager.configure(dict(settings=dict(backups.DEFAULT,enabled=True),approve_schedule=True))
        self.dest.rmdir()
        self.assertFalse(self.manager.run())
        self.manager.configure(dict(settings=backups.DEFAULT.copy()))
        self.assertFalse(self.manager.view()['settings']['enabled'])
        self.dest.mkdir()
        with patch('backups.time.monotonic',side_effect=[0,31]):self.assertFalse(self.manager.run())
        self.assertEqual(list(self.dest.iterdir()),[])
        self.assertTrue(self.manager.view()['last_failure'])

    def test_one_due_attempt_catchup_dst_and_explicit_pause(self):
        s=dict(backups.DEFAULT,enabled=True,time='03:00',timezone='America/Los_Angeles')
        self.manager.configure(dict(settings=s,approve_schedule=True))
        control=self.manager.read();control['enabled_at']='2026-10-01T00:00:00+00:00';self.manager.write(control)
        now=datetime(2026,10,8,12,tzinfo=timezone.utc)
        self.assertTrue(self.manager.run(scheduled=True,now=now))
        self.assertFalse(self.manager.run(scheduled=True,now=now+timedelta(minutes=1)))
        with patch('backups.os.link',side_effect=OSError()):self.assertFalse(self.manager.run(scheduled=True,now=now+timedelta(days=1)))
        self.assertFalse(self.manager.run(scheduled=True,now=now+timedelta(days=1,minutes=1)))
        self.assertEqual(backups.Manager.slot(dict(s,time='01:30'),datetime(2026,11,1,10,tzinfo=timezone.utc)).hour,8)
        self.assertEqual(backups.Manager.slot(dict(s,time='01:30'),datetime(2026,11,1,9,tzinfo=timezone.utc)).hour,8)
        spring=datetime(2026,3,8,10,tzinfo=timezone.utc)
        self.assertLess(backups.Manager.slot(dict(s,time='02:30'),spring),spring)
        self.assertEqual(backups.Manager.slot(dict(s,time='02:30'),spring+timedelta(minutes=30)),spring+timedelta(minutes=30))
        self.manager.configure(dict(settings=dict(s,enabled=False)))
        self.assertFalse(self.manager.run(scheduled=True,now=now+timedelta(days=2)))

    def test_restore_into_isolated_app_matches_export_and_has_no_backup_activation(self):
        appdb=self.data/'app.sqlite3'
        with patch.object(server,'DB',appdb):
            server.initialize()
            with server.connect() as db:
                db.execute("insert into ideas(uid,title,category,location,environment) values('12345678-1234-4234-8234-123456789012','Generic picnic','Activities','Example garden','outdoor')")
                bank=[discovery.idea_row(r) for r in db.execute('select * from ideas')]
                plan=server.generate(bank,dict(minutes=240,budget=80,energy='medium',count=1,weekend_date='2026-10-10'))
                db.execute('insert into plans(uid,name,created,payload) values(?,?,?,?)',('12345678-1234-4234-8234-123456789013','Generic saved weekend','2026-10-08T00:00:00+00:00',json.dumps(plan)))
                records,_=test_discovery.records()
                discovery.apply_records(db,records,now=test_discovery.NOW)
                db.commit()
                discovery.decide(db,records[0][0],'dismiss')
                server.set_currency(db,'CAD',False)
            with server.connect() as db:before=server.export_state(db)
        manager=backups.Manager(appdb,self.dest);self.assertTrue(manager.run())
        restored=self.root/'restored';restored.mkdir(); restored_db=restored/'weekend.sqlite3'
        shutil.copyfile(self.dest/manager.read()['files'][0]['name'],restored_db)
        with patch.object(server,'DB',restored_db):
            server.initialize()
            with server.connect() as db:self.assertEqual(before,server.export_state(db))
            server.initialize()
            with server.connect() as db:self.assertEqual(before,server.export_state(db))
        self.assertFalse(backups.Manager(restored_db,self.dest).view()['settings']['enabled'])

    def test_uncommitted_transaction_is_not_in_backup(self):
        with closing(sqlite3.connect(self.db)) as source:
            source.execute('pragma journal_mode=WAL')
            source.execute("insert into records values(2,'Uncommitted')")
            self.assertTrue(self.manager.run())
            path=self.dest/self.manager.read()['files'][0]['name']
            with closing(sqlite3.connect(path)) as copy:self.assertEqual(copy.execute('select count(*) from records').fetchone()[0],1)

if __name__=='__main__':unittest.main()
