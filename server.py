#!/usr/bin/env python3
"""Weekend Grove: local-only prototype, Python standard library only."""
import argparse
import hashlib
import json
import os
import random
import sqlite3
import tempfile
import uuid
import discovery
import weather
from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
CATEGORIES = ['Projects', 'Restaurants', 'Places', 'Activities']
ENERGY = {'low': 1, 'medium': 2, 'high': 3}
DB = Path(os.environ.get('DATA_DIR', ROOT / 'data')) / 'weekend.sqlite3'
DEFAULTS = dict(duration=60, cost=20, energy='medium')
DAYS = ('Saturday', 'Sunday')
CURRENCIES = ('USD', 'CAD', 'EUR', 'GBP', 'AUD', 'NZD')
MAX_BACKUP = 2 * 1024 * 1024

class Database(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def connect():
    db = sqlite3.connect(DB, timeout=15, factory=Database)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db

def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        existing = db.execute("SELECT 1 FROM sqlite_master WHERE name='ideas'").fetchone()
        if existing and 'uid' not in {r['name'] for r in db.execute('PRAGMA table_info(ideas)')}:
            safety_copy = DB.parent / 'before-upgrade-v2.sqlite3'
            if not safety_copy.exists():
                with closing(sqlite3.connect(safety_copy)) as target:
                    db.backup(target)
        elif existing:
            settings_exist = db.execute("SELECT 1 FROM sqlite_master WHERE name='settings'").fetchone()
            has_currency = settings_exist and db.execute("SELECT 1 FROM settings WHERE key='currency'").fetchone()
            safety_copy = DB.parent / 'before-upgrade-v3.sqlite3'
            if not has_currency and not safety_copy.exists():
                with closing(sqlite3.connect(safety_copy)) as target:
                    db.backup(target)
        if existing and 'metadata' not in {r['name'] for r in db.execute('PRAGMA table_info(ideas)')}:
            safety_copy = DB.parent / 'before-upgrade-v5.sqlite3'
            if not safety_copy.exists():
                with closing(sqlite3.connect(safety_copy)) as target:
                    db.backup(target)
        db.executescript('''
        CREATE TABLE IF NOT EXISTS ideas (
          id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
          duration INTEGER, cost REAL, location TEXT NOT NULL DEFAULT '',
          energy TEXT, archived INTEGER NOT NULL DEFAULT 0, sample INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS plans (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        for table in ('ideas', 'plans'):
            if 'uid' not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
                db.execute(f'ALTER TABLE {table} ADD COLUMN uid TEXT')
            for row in db.execute(f'SELECT id FROM {table} WHERE uid IS NULL').fetchall():
                db.execute(f'UPDATE {table} SET uid=? WHERE id=?', (str(uuid.uuid4()), row['id']))
            db.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {table}_uid ON {table}(uid)')
        if 'metadata' not in {r['name'] for r in db.execute('PRAGMA table_info(ideas)')}:
            db.execute("ALTER TABLE ideas ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        discovery.initialize(db)
        idea_uids = {r['id']: r['uid'] for r in db.execute('SELECT id,uid FROM ideas')}
        for row in db.execute('SELECT id,uid,payload FROM plans').fetchall():
            payload = json.loads(row['payload'])
            payload.setdefault('defaults', DEFAULTS.copy())
            if 'currency' not in payload:
                payload['currency'] = 'USD'
                payload['currency_assumed'] = True
            for index, item in enumerate(payload['items']):
                item.setdefault('uid', idea_uids.get(item['id'], str(uuid.uuid5(uuid.UUID(row['uid']), str(index)))))
            db.execute('UPDATE plans SET payload=? WHERE id=?', (json.dumps(payload), row['id']))
        db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)', ('defaults', json.dumps(DEFAULTS)))
        had_unlabeled_amounts = bool(existing and (db.execute('SELECT 1 FROM ideas LIMIT 1').fetchone() or db.execute('SELECT 1 FROM plans LIMIT 1').fetchone()))
        db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)', ('currency', json.dumps('USD')))
        db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)', ('currency_assumed', json.dumps(had_unlabeled_amounts)))

def clean_idea(data):
    if not isinstance(data.get('title'), str):
        raise ValueError('Add a text title.')
    title = data['title'].strip()
    if not title or len(title) > 120:
        raise ValueError('Add a title of 1–120 characters.')
    category = data.get('category')
    if category not in CATEGORIES:
        raise ValueError('Choose one of the four categories.')
    duration, cost = data.get('duration'), data.get('cost')
    if duration is not None and (type(duration) is not int or not 5 <= duration <= 1440):
        raise ValueError('Duration must be 5–1440 whole minutes.')
    if cost is not None and (type(cost) not in (int, float) or not 0 <= cost <= 10000):
        raise ValueError('Cost must be between 0 and 10,000.')
    if cost is not None and abs(cost * 100 - round(cost * 100)) > 0.00001:
        raise ValueError('Use at most two decimal places for cost.')
    energy = data.get('energy')
    if energy is not None and energy not in ENERGY:
        raise ValueError('Choose low, medium, or high energy.')
    if not isinstance(data.get('location', ''), str):
        raise ValueError('Location must be text.')
    location = data.get('location', '').strip()
    if len(location) > 200:
        raise ValueError('Location must be 200 characters or fewer.')
    return dict(title=title, category=category, duration=duration, cost=cost,
                energy=energy, location=location)

def clean_defaults(data):
    if not isinstance(data, dict) or set(data) != {'duration', 'cost', 'energy'}:
        raise ValueError('Planning estimates need duration, cost, and energy.')
    values = clean_idea(dict(data, title='Estimate', category='Activities'))
    if any(values[key] is None for key in DEFAULTS):
        raise ValueError('Planning estimates cannot be blank.')
    return {key: values[key] for key in DEFAULTS}

def defaults_from(db):
    return json.loads(db.execute("SELECT value FROM settings WHERE key='defaults'").fetchone()['value'])

def clean_currency(value):
    if not isinstance(value, str) or value not in CURRENCIES:
        raise ValueError('Choose USD, CAD, EUR, GBP, AUD, or NZD.')
    return value

def currency_from(db):
    return {key: json.loads(db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()['value']) for key in ('currency', 'currency_assumed')}

def set_currency(db, currency, assumed=False):
    currency = clean_currency(currency)
    if type(assumed) is not bool:
        raise ValueError('Currency assumption must be true or false.')
    for key, value in [('currency', currency), ('currency_assumed', assumed)]:
        db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(value), key))

def export_state(db):
    return dict(version=5, defaults=defaults_from(db), **currency_from(db), discovery=discovery.exported(db),
                ideas=[discovery.idea_row(r) for r in db.execute('SELECT * FROM ideas ORDER BY id DESC')],
                plans=[dict(id=r['id'], uid=r['uid'], name=r['name'], created=r['created'], **export_payload(r['payload'])) for r in db.execute('SELECT * FROM plans ORDER BY id DESC')])

def export_payload(raw):
    payload=json.loads(raw)
    payload.setdefault('schedule', [])
    payload['items']=[dict(i, metadata=i.get('metadata', {})) for i in payload['items']]
    return payload

def estimates(idea, defaults=None):
    defaults = defaults or DEFAULTS
    return (idea['duration'] if idea['duration'] is not None else defaults['duration'],
            idea['cost'] if idea['cost'] is not None else defaults['cost'],
            idea['energy'] or defaults['energy'])

def day_options(data):
    caps = data.get('day_caps', {day: {category: 3 for category in CATEGORIES} for day in DAYS})
    if not isinstance(caps, dict) or set(caps) != set(DAYS):
        raise ValueError('Set category maximums for Saturday and Sunday.')
    for values in caps.values():
        if not isinstance(values, dict) or set(values) != set(CATEGORIES) or any(type(v) is not int or not 0 <= v <= 6 for v in values.values()):
            raise ValueError('Daily category maximums must be whole numbers from 0 to 6.')
    lazy = data.get('include_lazy', False)
    if type(lazy) is not bool:
        raise ValueError('Choose whether to include Lazy Day time.')
    return caps, lazy

def schedule_entries(schedule):
    if not isinstance(schedule, list) or len(schedule) > 8:
        raise ValueError('A schedule can contain at most six ideas and two relaxation blocks.')
    seen = set()
    for entry in schedule:
        if not isinstance(entry, dict) or entry.get('day') not in DAYS or entry.get('kind') not in ('idea', 'lazy') or type(entry.get('id')) is not int:
            raise ValueError('Every scheduled item needs a valid day, type, and identifier.')
        expected = {'id', 'day', 'kind'} | ({'duration'} if entry['kind'] == 'lazy' else set())
        if set(entry) != expected or entry['id'] in seen:
            raise ValueError('A schedule contains unsupported fields or duplicate identifiers.')
        seen.add(entry['id'])
        if entry['kind'] == 'idea' and entry['id'] <= 0:
            raise ValueError('Scheduled idea identifiers must be positive.')
        if entry['kind'] == 'lazy' and (entry['id'] != -1-DAYS.index(entry['day']) or type(entry['duration']) is not int or entry['duration'] not in (30, 60)):
            raise ValueError('Lazy Day blocks must be 30 or 60 minutes, at most one per day.')
    return schedule

def schedule_totals(items, schedule, limits, defaults, historical=False):
    caps, lazy = day_options(limits)
    schedule_entries(schedule)
    by_id = {i['id']: i for i in items}
    placements = [e for e in schedule if e['kind'] == 'idea']
    if {e['id'] for e in placements} != set(by_id):
        raise ValueError('Every idea must be assigned to exactly one day.')
    counts = {d: {c: 0 for c in CATEGORIES} for d in DAYS}
    for entry in placements:
        if not discovery.eligible(by_id[entry['id']], entry['day'], limits, historical=historical):
            raise ValueError('An event is expired or unavailable on this date. Choose its weekend or unlock it.')
        counts[entry['day']][by_id[entry['id']]['category']] += 1
    if any(counts[d][c] > caps[d][c] for d in DAYS for c in CATEGORIES):
        raise ValueError('Locked ideas exceed a daily category maximum. Raise it or unlock them.')
    relaxation = [e for e in schedule if e['kind'] == 'lazy']
    if relaxation and not lazy:
        raise ValueError('Unlock Lazy Day blocks before turning Lazy Day time off.')
    minutes = sum(estimates(i, defaults)[0] for i in items) + sum(e['duration'] for e in relaxation)
    cost = sum(round(estimates(i, defaults)[1]*100) for i in items)
    if minutes > limits['minutes'] or cost > round(limits['budget']*100) or len(items) > limits['count'] or any(ENERGY[estimates(i,defaults)[2]] > ENERGY[limits['energy']] for i in items):
        raise ValueError('Locked suggestions exceed time, budget, energy, or size limits. Raise the limits or unlock them.')
    return minutes, cost

def generate(ideas, data, rng=None, defaults=None, currency='USD', currency_assumed=False):
    rng = rng or random.SystemRandom()
    defaults = clean_defaults(DEFAULTS if defaults is None else defaults)
    currency = clean_currency(currency)
    if type(currency_assumed) is not bool:
        raise ValueError('Currency assumption must be true or false.')
    minutes, budget = data.get('minutes'), data.get('budget')
    energy, count = data.get('energy'), data.get('count', 3)
    if type(minutes) is not int or not 5 <= minutes <= 2880:
        raise ValueError('Available time must be 5–2880 minutes.')
    if type(budget) not in (int, float) or not 0 <= budget <= 10000:
        raise ValueError('Budget must be between 0 and 10,000.')
    if abs(budget * 100 - round(budget * 100)) > 0.00001:
        raise ValueError('Use at most two decimal places for budget.')
    if energy not in ENERGY or type(count) is not int or not 1 <= count <= 6:
        raise ValueError('Choose an energy level and 1–6 suggestions.')
    caps, lazy = day_options(data)
    discovery.weekend(data.get('weekend_date'))
    limits = dict(minutes=minutes, budget=budget, energy=energy, count=count)
    if 'day_caps' in data or 'include_lazy' in data:
        limits.update(day_caps=caps, include_lazy=lazy)
    if data.get('weekend_date') is not None:
        limits['weekend_date'] = data['weekend_date']
    locked, previous = data.get('locked', []), data.get('previous', [])
    if not isinstance(locked, list) or not isinstance(previous, list) or any(type(i) is not int for i in locked + previous):
        raise ValueError('Suggestion IDs must be whole numbers.')
    if len(set(locked)) != len(locked) or len([i for i in locked if i > 0]) > count:
        raise ValueError('Unlock suggestions before reducing the plan size.')
    previous_schedule = schedule_entries(data.get('previous_schedule', []))
    previous_map = {e['id']: e for e in previous_schedule}
    available = {i['id']: i for i in ideas if not i['archived']}
    if any(i > 0 and i not in available for i in locked):
        raise ValueError('A locked idea is archived, removed, or excluded by the demo filter. Unlock it and try again.')
    if any(i < 0 and (i not in previous_map or previous_map[i]['kind'] != 'lazy') for i in locked) or 0 in locked:
        raise ValueError('A locked relaxation block is missing. Unlock it and try again.')
    chosen = [available[i] for i in locked if i > 0]
    schedule = []
    for ident in locked:
        if ident in previous_map:
            schedule.append(dict(previous_map[ident]))
        elif ident > 0:
            day = DAYS[previous.index(ident) % 2] if ident in previous else DAYS[len(schedule) % 2]
            schedule.append(dict(id=ident,kind='idea',day=day))
    used_time, used_cost = schedule_totals(chosen, schedule, limits, defaults)
    # Reserve relaxation before filling ideas. At most one 30/60-minute block per day.
    if lazy:
        days = [d for d in DAYS if not any(e['kind']=='lazy' and e['day']==d for e in schedule)]
        rng.shuffle(days)
        for day in days[:rng.randint(1, 2)]:
            fits = [n for n in (30,60) if used_time+n <= minutes]
            if fits:
                duration = rng.choice(fits)
                schedule.append(dict(id=-1-DAYS.index(day),kind='lazy',day=day,duration=duration))
                used_time += duration
    counts = {d: {c: 0 for c in CATEGORIES} for d in DAYS}
    day_time = {d: 0 for d in DAYS}
    for e in schedule:
        day_time[e['day']] += e['duration'] if e['kind']=='lazy' else estimates(available[e['id']], defaults)[0]
        if e['kind']=='idea': counts[e['day']][available[e['id']]['category']] += 1
    pool = [i for i in available.values() if i['id'] not in locked and ENERGY[estimates(i, defaults)[2]] <= ENERGY[energy]]
    rng.shuffle(pool); pool.sort(key=lambda i: i['id'] in previous)
    for idea in pool:
        duration, cost, _ = estimates(idea, defaults); cost_units = round(cost*100)
        days = [d for d in DAYS if counts[d][idea['category']] < caps[d][idea['category']] and discovery.eligible(idea,d,limits)]
        if len(chosen) < count and days and used_time+duration <= minutes and used_cost+cost_units <= round(budget*100):
            rng.shuffle(days); day = min(days,key=lambda d: day_time[d])
            chosen.append(idea); schedule.append(dict(id=idea['id'],kind='idea',day=day))
            counts[day][idea['category']] += 1; day_time[day] += duration
            used_time += duration; used_cost += cost_units
    # Retain legacy item ordering as well as the explicit day of every locked item.
    slots = [None] * len(chosen); placed = set()
    for item in chosen:
        if item['id'] in locked and item['id'] in previous:
            position = previous.index(item['id'])
            if position < len(slots) and slots[position] is None:
                slots[position] = item; placed.add(item['id'])
    remaining = iter(i for i in chosen if i['id'] not in placed)
    chosen = [i if i is not None else next(remaining) for i in slots]
    return dict(items=chosen, schedule=schedule, minutes=used_time, cost=used_cost/100, defaults=defaults, currency=currency, currency_assumed=currency_assumed, limits=limits)

SAMPLES = [
    ('Build a small herb planter', 'Projects', 90, 25, 'At home', 'medium'),
    ('Try a neighborhood café', 'Restaurants', 60, 30, 'Nearby', 'low'),
    ('Explore a public garden', 'Places', 90, 10, 'Local garden', 'low'),
    ('Picnic and a short walk', 'Activities', 120, 20, 'Local park', 'medium'),
    ('Make homemade pizza', 'Activities', 90, 15, 'At home', 'low'),
    ('Browse a library display', 'Places', 45, 0, 'Local library', 'low'),
    ('Paint a flowerpot', 'Projects', 45, 10, 'At home', 'low'),
    ('Take a longer nature walk', 'Activities', 180, 0, 'Nearby trail', 'high'),
]

def strict_json(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('The backup has duplicate JSON keys.')
            value[key] = item
        return value
    def invalid_constant(_):
        raise ValueError('JSON numbers must be finite.')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)

def validate_backup(text):
    """Validate every record before any write; never repair or discard unknown fields."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BACKUP:
        raise ValueError('Choose a Weekend Grove JSON export smaller than 2 MiB.')
    data = strict_json(text)
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] not in (1, 2, 3, 4, 5):
        raise ValueError('This is not a supported Weekend Grove export (version 1, 2, 3, 4, or 5).')
    version = data['version']
    expected = {'version', 'ideas', 'plans'} | ({'defaults'} if version >= 2 else set())
    expected |= {'currency', 'currency_assumed'} if version >= 3 else set()
    expected |= {'discovery'} if version >= 5 else set()
    if set(data) != expected:
        raise ValueError('Backup fields are missing or unsupported. No data was restored.')
    for field in ('ideas', 'plans'):
        if not isinstance(data[field], list) or len(data[field]) > 2000:
            raise ValueError('A backup can contain at most 2,000 ideas and 2,000 plans.')
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    settings = clean_defaults(data['defaults']) if version >= 2 else DEFAULTS.copy()
    currency = clean_currency(data['currency']) if version >= 3 else 'USD'
    assumed = data['currency_assumed'] if version >= 3 else True
    if type(assumed) is not bool:
        raise ValueError('The backup currency assumption must be true or false.')
    idea_fields = {'id', 'title', 'category', 'duration', 'cost', 'location', 'energy', 'archived', 'sample'}
    idea_fields |= {'uid'} if version >= 2 else set()
    idea_fields |= {'metadata'} if version >= 5 else set()

    def identity(record, kind):
        if type(record.get('id')) is not int or not 1 <= record['id'] <= 2**53 - 1:
            raise ValueError('Every backup record needs a positive whole-number ID.')
        if version >= 2:
            value = record.get('uid')
            if not isinstance(value, str) or str(uuid.UUID(value)) != value:
                raise ValueError('A backup record has an invalid stable identifier.')
            return value
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'weekend-grove:legacy:{digest}:{kind}:{record["id"]}'))

    def validate_idea(record):
        if not isinstance(record, dict) or set(record) != idea_fields:
            raise ValueError('An idea has missing or unsupported fields.')
        cleaned = clean_idea(record)
        if any(cleaned[key] != record[key] for key in cleaned):
            raise ValueError('An idea contains noncanonical text. Restore was not changed.')
        for flag in ('archived', 'sample'):
            if type(record[flag]) is not int or record[flag] not in (0, 1):
                raise ValueError('Archive and demo flags must be 0 or 1.')
        return dict(record, uid=identity(record, 'idea'), metadata=discovery.clean_metadata(record.get('metadata', {})))

    ideas = [validate_idea(i) for i in data['ideas']]
    if len({i['id'] for i in ideas}) != len(ideas) or len({i['uid'] for i in ideas}) != len(ideas):
        raise ValueError('The backup contains duplicate ideas.')
    by_id = {i['id']: i for i in ideas}
    plan_fields = {'id', 'name', 'created', 'items', 'minutes', 'cost', 'limits'}
    plan_fields |= {'uid', 'defaults'} if version >= 2 else set()
    plan_fields |= {'currency', 'currency_assumed'} if version >= 3 else set()
    plan_fields |= {'schedule'} if version >= 4 else set()
    plans = []
    for row in data['plans']:
        if not isinstance(row, dict) or set(row) != plan_fields:
            raise ValueError('A saved plan has missing or unsupported fields.')
        uid = identity(row, 'plan')
        if not isinstance(row['name'], str) or not row['name'].strip() or row['name'] != row['name'].strip() or len(row['name']) > 120:
            raise ValueError('A saved plan has an invalid name.')
        if not isinstance(row['created'], str) or len(row['created']) > 50 or datetime.fromisoformat(row['created']).tzinfo is None:
            raise ValueError('A saved plan needs a timestamp with a timezone.')
        if not isinstance(row['items'], list) or not 0 <= len(row['items']) <= 6:
            raise ValueError('A saved plan can contain at most six ideas.')
        items = [validate_idea(i) for i in row['items']]
        if len({i['uid'] for i in items}) != len(items) or len({i['id'] for i in items}) != len(items):
            raise ValueError('A saved plan contains duplicate suggestions.')
        if any(i['id'] not in by_id for i in items):
            raise ValueError('A saved plan refers to an idea missing from the export.')
        if version >= 2 and any(by_id[i['id']]['uid'] != i['uid'] for i in items):
            raise ValueError('A saved plan contains an inconsistent idea identifier.')
        defaults = clean_defaults(row['defaults']) if version >= 2 else DEFAULTS.copy()
        plan_currency = clean_currency(row['currency']) if version >= 3 else 'USD'
        plan_assumed = row['currency_assumed'] if version >= 3 else True
        if type(plan_assumed) is not bool:
            raise ValueError('A saved plan has an invalid currency assumption.')
        limits = row['limits']
        if not isinstance(limits, dict) or (set(limits) - ({'weekend_date'} if version >= 5 else set())) not in ({'minutes', 'budget', 'energy', 'count'}, {'minutes', 'budget', 'energy', 'count', 'day_caps', 'include_lazy'}):
            raise ValueError('A saved plan has invalid limits.')
        # Validate limits separately: saved snapshots may refer to now-archived ideas.
        generate([], limits, defaults=defaults)
        schedule = row['schedule'] if version >= 4 else []
        schedule_entries(schedule)
        if schedule:
            schedule_totals(items, schedule, limits, defaults, historical=True)
        elif not items or 'day_caps' in limits:
            raise ValueError('A current plan requires an explicit day schedule.')
        total_minutes = sum(estimates(i, defaults)[0] for i in items) + sum(e['duration'] for e in schedule if e['kind']=='lazy')
        total_cents = sum(round(estimates(i, defaults)[1] * 100) for i in items)
        if (type(row['minutes']) is not int or row['minutes'] != total_minutes or
                type(row['cost']) not in (int, float) or row['cost'] != total_cents / 100 or
                total_minutes > limits['minutes'] or total_cents > round(limits['budget'] * 100) or
                len(items) > limits['count'] or any(ENERGY[estimates(i, defaults)[2]] > ENERGY[limits['energy']] for i in items)):
            raise ValueError('A saved plan has inconsistent totals or constraints.')
        plans.append(dict(row, uid=uid, items=items, schedule=schedule, defaults=defaults, currency=plan_currency, currency_assumed=plan_assumed))
    if len({p['id'] for p in plans}) != len(plans) or len({p['uid'] for p in plans}) != len(plans):
        raise ValueError('The backup contains duplicate saved plans.')
    imported_discovery = discovery.validate_export(data['discovery'], clean_idea) if version >= 5 else None
    if imported_discovery and any(r['idea_uid'] and r['idea_uid'] not in {i['uid'] for i in ideas} for r in imported_discovery['candidates']):
        raise ValueError('A saved discovery refers to a missing idea.')
    return dict(discovery=imported_discovery, ideas=ideas, plans=plans, defaults=settings, currency=currency, currency_assumed=assumed, digest=digest, version=version)

def restore_summary(db, backup):
    ideas = {r['uid'] for r in db.execute('SELECT uid FROM ideas')}
    plans = {r['uid'] for r in db.execute('SELECT uid FROM plans')}
    new_ideas = sum(i['uid'] not in ideas for i in backup['ideas'])
    new_plans = sum(p['uid'] not in plans for p in backup['plans'])
    candidate_keys={r['key'] for r in db.execute('SELECT key FROM discovery_candidates')}
    discovery_rows=(backup.get('discovery') or {}).get('candidates',[])
    return dict(discovery_to_add=sum(r['key'] not in candidate_keys for r in discovery_rows), discovery_skipped=sum(r['key'] in candidate_keys for r in discovery_rows), ideas_to_add=new_ideas, plans_to_add=new_plans,
                ideas_skipped=len(backup['ideas']) - new_ideas,
                plans_skipped=len(backup['plans']) - new_plans,
                defaults=backup['defaults'], currency=backup['currency'], currency_assumed=backup['currency_assumed'],
                current_currency=currency_from(db)['currency'], currency_mismatch=backup['currency'] != currency_from(db)['currency'],
                digest=backup['digest'], version=backup['version'])

def restore_backup(db, backup, apply_defaults=False, acknowledge_relabel=False, apply_discovery=False):
    """Called within one transaction. Stable IDs make v2 merges repeatable."""
    db.execute('BEGIN IMMEDIATE')
    summary = restore_summary(db, backup)
    if summary['currency_mismatch'] and acknowledge_relabel is not True:
        raise ValueError('Backup and bank currencies differ. Confirm relabeling without conversion before merging.')
    existing = {r['uid']: r['id'] for r in db.execute('SELECT id,uid FROM ideas')}
    for row in sorted(backup['ideas'], key=lambda i: i['id']):
        if row['uid'] not in existing:
            cursor = db.execute('INSERT INTO ideas(uid,title,category,duration,cost,location,energy,archived,sample,metadata) VALUES (:uid,:title,:category,:duration,:cost,:location,:energy,:archived,:sample,:metadata)', dict(row,metadata=json.dumps(row['metadata'])))
            existing[row['uid']] = cursor.lastrowid
    plans = {r['uid'] for r in db.execute('SELECT uid FROM plans')}
    for row in sorted(backup['plans'], key=lambda p: p['id']):
        if row['uid'] not in plans:
            items = [dict(i, id=existing.get(i['uid'], i['id'])) for i in row['items']]
            payload = {key: row[key] for key in ('minutes', 'cost', 'limits', 'defaults', 'currency', 'currency_assumed')}
            payload['items'] = items
            remapping = {original['id']: mapped['id'] for original,mapped in zip(row['items'],items)}
            payload['schedule'] = [dict(e,id=remapping.get(e['id'],e['id'])) for e in row['schedule']]
            db.execute('INSERT INTO plans(uid,name,created,payload) VALUES (?,?,?,?)', (row['uid'], row['name'], row['created'], json.dumps(payload)))
    if apply_defaults:
        db.execute("UPDATE settings SET value=? WHERE key='defaults'", (json.dumps(backup['defaults']),))
        set_currency(db, backup['currency'], backup['currency_assumed'])
    discovery.restore(db, backup.get('discovery'), apply_discovery)
    return dict(summary, defaults_applied=apply_defaults, discovery_preferences_applied=apply_discovery)

class Handler(BaseHTTPRequestHandler):
    def allowed_host(self):
        host = urlparse('http://' + self.headers.get('Host', '')).hostname
        allowed = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,::1').split(',')
        if host not in allowed:
            self.send({'error': 'Host is not allowed. Configure ALLOWED_HOSTS for a future home LAN installation.'}, 403)
            return False
        return True

    def send(self, value, status=200, content_type='application/json', filename=None):
        body = json.dumps(value, allow_nan=False).encode() if content_type == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header('Cache-Control', 'no-store')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.allowed_host():
            return
        path = urlparse(self.path).path
        static_types = {
            '/': 'text/html; charset=utf-8', '/app.js': 'text/javascript',
            '/weather.js': 'text/javascript', '/discovery.js': 'text/javascript', '/style.css': 'text/css', '/icon.svg': 'image/svg+xml',
            '/favicon.ico': 'image/vnd.microsoft.icon', '/icon-32.png': 'image/png',
            '/apple-touch-icon.png': 'image/png', '/icon-192.png': 'image/png',
            '/icon-512.png': 'image/png', '/site.webmanifest': 'application/manifest+json',
        }
        if path in static_types:
            name = 'index.html' if path == '/' else path[1:]
            mime = static_types[path]
            return self.send((ROOT / 'static' / name).read_bytes(), content_type=mime)
        with connect() as db:
            if path == '/api/discovery':
                return self.send(discovery.view(db))
            if path in ('/api/state', '/api/export'):
                value = export_state(db)
                return self.send(value, filename='weekend-grove.json' if path.endswith('export') else None)
            if path == '/api/backup':
                with tempfile.TemporaryDirectory() as temp:
                    backup = Path(temp) / 'backup.sqlite3'
                    target = sqlite3.connect(backup)
                    db.backup(target)
                    target.close()
                    return self.send(backup.read_bytes(), content_type='application/vnd.sqlite3', filename='weekend-grove.sqlite3')
        self.send({'error': 'Not found'}, 404)

    def do_POST(self):
        if not self.allowed_host():
            return
        try:
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != self.headers.get('Host'):
                return self.send({'error': 'Cross-origin requests are not allowed.'}, 403)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send({'error': 'Use JSON requests.'}, 415)
            length = int(self.headers.get('Content-Length', 0))
            path = urlparse(self.path).path
            max_length = 4 * MAX_BACKUP if path.startswith('/api/restore') else 65536
            if not 0 < length <= max_length:
                raise ValueError('Request is empty or too large.')
            data = strict_json(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            if path == '/api/weather':
                return self.send(weather.lookup(connect, data))
            if path == '/api/discovery/refresh':
                return self.send({'started': discovery.launch(connect, manual=True)}, 202)
            reply = {'ok': True}
            with connect() as db:
                if path == '/api/discovery/settings':
                    reply = discovery.configure(db, data)
                elif path == '/api/discovery/decision':
                    reply = discovery.decide(db, data.get('key'), data.get('action'))
                elif path == '/api/ideas':
                    idea = clean_idea(data)
                    if data.get('id') is not None:
                        cursor = db.execute('UPDATE ideas SET title=:title, category=:category, duration=:duration, cost=:cost, location=:location, energy=:energy, sample=0 WHERE id=:id', dict(idea, id=data['id']))
                        if cursor.rowcount != 1:
                            raise ValueError('Idea no longer exists.')
                    else:
                        db.execute('INSERT INTO ideas(uid,title,category,duration,cost,location,energy) VALUES (:uid,:title,:category,:duration,:cost,:location,:energy)', dict(idea, uid=str(uuid.uuid4())))
                elif path == '/api/archive':
                    if type(data.get('archived')) is not bool:
                        raise ValueError('Archive state must be true or false.')
                    if db.execute('UPDATE ideas SET archived=? WHERE id=?', (int(data['archived']), data.get('id'))).rowcount != 1:
                        raise ValueError('Idea no longer exists.')
                elif path == '/api/samples':
                    if not db.execute('SELECT 1 FROM ideas WHERE sample=1').fetchone():
                        db.executemany('INSERT INTO ideas(uid,title,category,duration,cost,location,energy,sample) VALUES (?,?,?,?,?,?,?,1)', [(str(uuid.uuid4()), *row) for row in SAMPLES])
                elif path == '/api/archive-samples':
                    cursor = db.execute('UPDATE ideas SET archived=1 WHERE sample=1 AND archived=0')
                    reply['count'] = cursor.rowcount
                elif path == '/api/defaults':
                    defaults = clean_defaults(data)
                    db.execute("UPDATE settings SET value=? WHERE key='defaults'", (json.dumps(defaults),))
                elif path == '/api/currency':
                    if set(data) != {'currency'}:
                        raise ValueError('Choose one currency code.')
                    set_currency(db, data['currency'])
                elif path in ('/api/restore/preview', '/api/restore'):
                    backup = validate_backup(data.get('backup_text'))
                    if path.endswith('/preview'):
                        return self.send(restore_summary(db, backup))
                    if data.get('digest') != backup['digest'] or type(data.get('apply_defaults')) is not bool or type(data.get('apply_discovery',False)) is not bool:
                        raise ValueError('Preview this exact backup before restoring it.')
                    reply = restore_backup(db, backup, data['apply_defaults'], data.get('acknowledge_relabel', False), data.get('apply_discovery', False))
                elif path == '/api/generate':
                    if type(data.get('include_samples', True)) is not bool:
                        raise ValueError('Choose whether to include demo ideas.')
                    ideas = [discovery.idea_row(r) for r in db.execute('SELECT * FROM ideas') if data.get('include_samples', True) or not r['sample']]
                    return self.send(generate(ideas, data, defaults=defaults_from(db), **currency_from(db)))
                elif path == '/api/plans':
                    if not isinstance(data.get('name'), str):
                        raise ValueError('Give the plan a text name.')
                    name = data['name'].strip()
                    if not name or len(name) > 120:
                        raise ValueError('Give the plan a name of 1–120 characters.')
                    ids = data.get('ids', [])
                    if not ids and not data.get('schedule'):
                        raise ValueError('Generate some suggestions before saving.')
                    ideas = [discovery.idea_row(r) for r in db.execute('SELECT * FROM ideas')]
                    if data.get('expected_items') is not None:
                        current = {i['id']: i for i in ideas}
                        snapshots = data['expected_items']
                        if not isinstance(snapshots, list) or not all(isinstance(i, dict) for i in snapshots) or [i.get('id') for i in snapshots] != ids or any(current.get(i['id']) != i for i in snapshots):
                            raise ValueError('An idea changed since this plan was generated. Reroll before saving so the preview matches the saved plan.')
                    denomination = currency_from(db)
                    if 'schedule' in data:
                        selected = {i['id']: i for i in ideas if not i['archived']}
                        if not isinstance(ids,list) or len(set(ids)) != len(ids) or any(type(i) is not int or i not in selected for i in ids):
                            raise ValueError('Saved ideas must be available and distinct.')
                        limits = data.get('limits', {})
                        defaults = clean_defaults(data.get('defaults', defaults_from(db)))
                        limits = generate([], limits, defaults=defaults)['limits']
                        items = [selected[i] for i in ids]
                        minutes, cents = schedule_totals(items, data['schedule'], limits, defaults)
                        if not data['schedule']: raise ValueError('Generate a scheduled plan before saving.')
                        currency = clean_currency(data.get('currency', denomination['currency']))
                        assumed = data.get('currency_assumed', denomination['currency_assumed'])
                        if type(assumed) is not bool: raise ValueError('Invalid currency assumption.')
                        plan = dict(items=items, schedule=data['schedule'], minutes=minutes, cost=cents/100, defaults=defaults, limits=limits, currency=currency,currency_assumed=assumed)
                    else:
                        plan = generate(ideas, dict(data.get('limits', {}), locked=ids, previous=ids, count=len(ids)), defaults=data.get('defaults', defaults_from(db)),
                                        currency=data.get('currency', denomination['currency']), currency_assumed=data.get('currency_assumed', denomination['currency_assumed']))
                    db.execute('INSERT INTO plans(uid,name,created,payload) VALUES (?,?,?,?)', (str(uuid.uuid4()), name, datetime.now(timezone.utc).isoformat(), json.dumps(plan)))
                else:
                    return self.send({'error': 'Not found'}, 404)
            self.send(reply)
        except (ValueError, TypeError, KeyError, sqlite3.InterfaceError, sqlite3.ProgrammingError) as error:
            self.send({'error': str(error)}, 400)
        except sqlite3.Error:
            self.send({'error': 'Storage is unavailable. Check the data directory and try again.'}, 503)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8765, type=int)
    args = parser.parse_args()
    initialize()
    stop = discovery.start_scheduler(connect)
    print(f'Weekend Grove: http://{args.host}:{args.port}', flush=True)
    try:
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    finally:
        stop.set()

if __name__ == '__main__':
    main()
