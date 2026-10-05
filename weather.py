"""Explicit, manual weather lookups. Forecasts stay in a bounded process cache, never plans."""
import copy
import json
import math
import re
import threading
import time
from datetime import timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import discovery as d

CACHE = {}
LOCK = threading.Lock()
FIELDS = ('temperature_2m_max', 'temperature_2m_min', 'precipitation_probability_max')

def number(value, low, high):
    return value if type(value) in (int, float) and math.isfinite(value) and low <= value <= high else None

def lookup(connect, request, getter=None, now=None):
    if request.get('consent') is not True:
        raise ValueError('Allow the separate weather lookup before requesting a forecast.')
    zip_code = request.get('zip', '')
    if not isinstance(zip_code, str) or not re.fullmatch(r'[0-9]{5}', zip_code):
        raise ValueError('Enter a five-digit US ZIP for weather.')
    start = d.weekend(request.get('weekend_date'))
    if start is None: raise ValueError('Choose a Saturday for weather.')
    zone = request.get('timezone', '')
    try:
        if not isinstance(zone, str) or len(zone) > 80: raise ValueError()
        tz = ZoneInfo(zone)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError('Choose a valid IANA weather timezone, such as America/Los_Angeles.') from None
    now = now or d.utcnow()
    today = now.astimezone(tz).date()
    days = []
    for offset, label in enumerate(('Saturday', 'Sunday')):
        date = start + timedelta(days=offset)
        status = 'past' if date < today else 'too_early' if date > today + timedelta(days=15) else 'unavailable'
        days.append(dict(day=label, date=date.isoformat(), status=status, high=None, low=None, rain=None))
    result = dict(zip=zip_code, timezone=zone, fetched_at=None, cached=False, days=days, status='outside_window')
    wanted = [day['date'] for day in days if day['status'] == 'unavailable']
    if not wanted: return result
    getter = getter or d.fetch
    key = (zip_code, zone, start.isoformat(), today.isoformat())
    with LOCK:
        cached = CACHE.get(key)
        if cached and 0 <= (now - cached[0]).total_seconds() < cached[1]:
            result = copy.deepcopy(cached[2]); result['cached'] = True
            return result
        try:
            deadline = time.monotonic() + 30
            with connect() as db:
                latitude, longitude = d.coordinates(zip_code, db, getter, deadline)
            params = dict(latitude=round(latitude,4), longitude=round(longitude,4), daily=','.join(FIELDS),
                          temperature_unit='fahrenheit', timezone=zone, start_date=min(wanted), end_date=max(wanted))
            data = json.loads(getter('https://api.open-meteo.com/v1/forecast?' + urlencode(params), deadline))
            if data.get('timezone') != zone: raise ValueError()
            daily = data['daily']; dates = daily['time']; units = data['daily_units']
            if not isinstance(dates, list) or len(dates)>2 or len(set(dates))!=len(dates): raise ValueError()
            if units.get(FIELDS[0]) != '°F' or units.get(FIELDS[1]) != '°F' or units.get(FIELDS[2]) != '%': raise ValueError()
            for day in days:
                if day['date'] not in wanted or day['date'] not in dates: continue
                i = dates.index(day['date'])
                def value(field, low, high):
                    values = daily.get(field, [])
                    return number(values[i], low, high) if isinstance(values,list) and i<len(values) else None
                day.update(high=value(FIELDS[0],-150,150), low=value(FIELDS[1],-150,150), rain=value(FIELDS[2],0,100))
                if day['high'] is not None and day['low'] is not None and day['low']>day['high']:
                    day.update(high=None,low=None)
                values = [day[k] for k in ('high','low','rain')]
                day['status'] = 'available' if all(v is not None for v in values) else 'partial' if any(v is not None for v in values) else 'unavailable'
            result.update(fetched_at=now.isoformat(), status='complete')
            ttl = 3600
        except Exception:
            # Provider errors/URLs are never returned or logged; no stale fallback or invented facts.
            result['status'] = 'unavailable'; ttl = 60
        if len(CACHE) >= 32: CACHE.pop(next(iter(CACHE)))
        CACHE[key] = (now, ttl, copy.deepcopy(result))
    return result
