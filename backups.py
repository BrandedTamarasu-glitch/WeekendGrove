"""Opt-in database-only backups. Control state is deliberately not in the database."""
try:
    import fcntl
except ImportError:  # The rest of the app and manual downloads remain usable on Windows.
    fcntl = None
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT = dict(enabled=False, time='03:00', timezone='UTC', keep=7, prune=False)
NAME = re.compile(r'grove-auto-[0-9a-f]{32}\.sqlite3')


class Manager:
    def __init__(self, database, destination=None):
        self.database = Path(database)
        self.destination = Path(destination) if destination else None
        self.control = self.database.parent / 'backup-control.json'
        self.lock = self.database.parent / 'backup-control.lock'

    @contextmanager
    def exclusive(self):
        if fcntl is None: raise ValueError('Automatic backups require Unix file-lock support; manual database downloads remain available.')
        self.database.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError('A backup operation is already running.') from None
            yield
        finally: os.close(fd)

    def read(self):
        if not self.control.exists(): return dict(settings=DEFAULT.copy(), files=[])
        if self.control.is_symlink(): raise ValueError('Backup control storage needs attention.')
        try:
            value = json.loads(self.control.read_text())
            self.validate(value['settings'])
            if not isinstance(value['files'], list): raise ValueError()
            if any(not isinstance(x, dict) or not NAME.fullmatch(x.get('name', '')) or
                   not isinstance(x.get('destination'), str) or not re.fullmatch(r'[0-9a-f]{64}', x.get('sha256', ''))
                   for x in value['files']): raise ValueError()
            for key in ('enabled_at', 'slot', 'last_attempt', 'last_success', 'last_failure'):
                if key in value and datetime.fromisoformat(value[key]).tzinfo is None: raise ValueError()
            return value
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError('Backup control storage is unreadable. Scheduling is stopped; preserve the file for recovery.') from None

    def write(self, value):
        fd, name = tempfile.mkstemp(prefix='.backup-control-', dir=self.database.parent)
        try:
            with os.fdopen(fd, 'w') as out:
                json.dump(value, out); out.flush(); os.fsync(out.fileno())
            os.replace(name, self.control)
            self.sync(self.database.parent)
        finally:
            if os.path.exists(name): os.unlink(name)

    @staticmethod
    def sync(directory):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def folder(self):
        if fcntl is None: raise ValueError('Automatic backups require Unix file-lock support; use the Linux container or manual database downloads.')
        p = self.destination
        if p is None: raise ValueError('Choose and configure a dedicated backup folder on the server first.')
        if not p.is_absolute() or any(x.is_symlink() for x in [p, *p.parents]):
            raise ValueError('Use an absolute backup folder without symlinks.')
        if not p.is_dir() or p.resolve() == self.database.parent.resolve():
            raise ValueError('The dedicated backup folder must already exist and must not be the app data folder itself.')
        if p.name == 'secrets' or 'secrets' in p.parts:
            raise ValueError('Choose a dedicated backup folder outside secrets.')
        return p

    @staticmethod
    def validate(s):
        if not isinstance(s, dict) or set(s) != set(DEFAULT): raise ValueError('Invalid backup settings.')
        if type(s['enabled']) is not bool or type(s['prune']) is not bool: raise ValueError('Choose backup and retention permissions.')
        if not isinstance(s['time'], str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', s['time']): raise ValueError('Choose a valid daily time.')
        if type(s['keep']) is not int or not 1 <= s['keep'] <= 90: raise ValueError('Keep between 1 and 90 successful backups.')
        try: ZoneInfo(s['timezone'])
        except (ValueError, TypeError, KeyError): raise ValueError('Choose a valid IANA timezone.') from None
        return s.copy()

    def view(self):
        value = self.read()
        try: self.folder(); ready, reason = True, ''
        except ValueError as exc: ready, reason = False, str(exc)
        settings = value['settings'].copy()
        attempt_status = 'failed' if value.get('error') else 'idle'
        if value.get('running'):
            try:
                with self.exclusive(): attempt_status = 'interrupted; completion was not recorded'
            except ValueError: attempt_status = 'running'
        changed = (settings['enabled'] or settings['prune']) and value.get('approved_destination') != str(self.destination)
        if changed: settings.update(enabled=False, prune=False)
        return dict(settings=settings, configured=ready, destination=str(self.destination or ''),
                    unavailable=reason, last_attempt=value.get('last_attempt'), last_success=value.get('last_success'),
                    last_failure=value.get('last_failure'), error=value.get('error', ''),
                    status=attempt_status, warning='Destination changed. Review and approve the new folder before scheduling or cleanup.' if changed else value.get('warning', ''), count=len(value['files']))

    def configure(self, data):
        s = self.validate(data.get('settings'))
        with self.exclusive():
            value = self.read()
            if s['enabled'] or s['prune']: self.folder()
            if s['enabled'] and data.get('approve_schedule') is not True:
                raise ValueError('Explicitly approve this destination, daily time and retention before enabling backups.')
            if s['prune'] and data.get('approve_deletion') is not True:
                raise ValueError('Explicitly authorize removal of older automatic backups before enabling retention cleanup.')
            value['settings'] = s
            value['approved_destination'] = str(self.destination)
            # Do not catch up immediately when first enabling or changing the schedule.
            value['enabled_at'] = datetime.now(timezone.utc).isoformat()
            self.write(value)
        return self.view()

    @staticmethod
    def slot(s, now):
        local = now.astimezone(ZoneInfo(s['timezone']))
        hour, minute = map(int, s['time'].split(':'))
        due = local.replace(hour=hour, minute=minute, second=0, microsecond=0, fold=0)
        if now < due.astimezone(timezone.utc): due -= timedelta(days=1)
        return due.astimezone(timezone.utc)

    def run(self, scheduled=False, now=None):
        now = now or datetime.now(timezone.utc)
        with self.exclusive():
            value = self.read(); settings = value['settings']
            if scheduled:
                if not settings['enabled']: return False
                if value.get('approved_destination') != str(self.destination): return False
                due = self.slot(settings, now)
                if due <= datetime.fromisoformat(value.get('enabled_at', now.isoformat())): return False
                slot = due.isoformat()
                if value.get('slot') == slot: return False
                value['slot'] = slot  # One attempt per slot, including failures; no retry storm.
            value.update(last_attempt=now.isoformat(), error='', warning='', running=True)
            self.write(value)
            temporary = None
            try:
                folder = self.folder()
                if not self.database.is_file() or self.database.is_symlink(): raise ValueError('Source database is unavailable.')
                fd, temporary = tempfile.mkstemp(prefix='.grove-incomplete-', dir=folder)
                os.close(fd)
                deadline = time.monotonic() + 30
                def progress(*_):
                    if time.monotonic() > deadline: raise TimeoutError()
                with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)) as source:
                    with closing(sqlite3.connect(temporary)) as target:
                        source.backup(target, pages=256, progress=progress, sleep=.05)
                        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('Backup integrity verification failed.')
                with open(temporary, 'rb') as snapshot:
                    os.fsync(snapshot.fileno()); digest = hashlib.file_digest(snapshot, 'sha256').hexdigest()
                name = 'grove-auto-'+uuid.uuid4().hex+'.sqlite3'
                os.link(temporary, folder/name)  # Exclusive publication; never overwrite a prior backup.
                os.unlink(temporary); temporary = None; self.sync(folder)
                value['files'].append(dict(name=name, sha256=digest, destination=str(folder), created=now.isoformat()))
                value['last_success'] = now.isoformat()
                self.write(value)  # Record ownership before any pruning.
                if settings['prune'] and value.get('approved_destination') == str(folder): self.prune(value, folder)
                value['running'] = False
                self.write(value)
            except (OSError, sqlite3.Error, ValueError, TimeoutError):
                value['last_failure'] = now.isoformat()
                value['running'] = False
                value['error'] = 'Backup failed. Check destination availability, permissions and free space. Previous completed backups were kept.'
                self.write(value)
                return False
            finally:
                if temporary and os.path.exists(temporary): os.unlink(temporary)
        return True

    def prune(self, value, folder):
        owned = [x for x in value['files'] if x.get('destination') == str(folder)]
        for item in owned[:-value['settings']['keep']]:
            name = item.get('name', '')
            if not NAME.fullmatch(name): continue
            path = folder/name
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as old:
                    if hashlib.file_digest(old, 'sha256').hexdigest() != item.get('sha256'): raise ValueError()
                path.unlink(); self.sync(folder); value['files'].remove(item)
            except (OSError, ValueError):
                value['warning'] = 'A new backup succeeded, but some older files could not be verified for cleanup. They were kept.'

    def start(self):
        stop = threading.Event()
        def tick():
            while not stop.wait(30):
                try: self.run(scheduled=True)
                except (ValueError, OSError): pass  # Status endpoint reports unreadable control storage.
        threading.Thread(target=tick, daemon=True).start()
        return stop
