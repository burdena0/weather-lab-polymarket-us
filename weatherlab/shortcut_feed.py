"""Read automatic Apple Shortcuts exports from a local synced folder.

The export is device-reported evidence, not an authenticated Apple API receipt.
No listener, phone credentials, external upload, or manual temperature entry.
"""
import hashlib
import json
import os
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path

from .core import number, stamp
from .sources import STATIONS

MAX_BYTES = 65536
MAX_AGE = 1800


def validate_export(raw, station, now):
    if raw.get('schema_version') != 1 or raw.get('source') != 'apple_shortcuts':
        raise ValueError('Expected the Apple Shortcuts forecast export schema')
    if station not in STATIONS or raw.get('station') != station:
        raise ValueError('Shortcut station does not match the selected settlement station')
    fetched = stamp(raw['fetched_at'])
    if not 0 <= now-fetched <= MAX_AGE:
        raise ValueError('Shortcut export is future-dated or older than 30 minutes')
    if raw.get('unit') not in ('F', 'C') or raw.get('period') != 'daily':
        raise ValueError('Expected daily high forecasts with explicit F or C units')
    location = raw.get('location')
    if not isinstance(location, str) or not 2 <= len(location.strip()) <= 160:
        raise ValueError('Shortcut must record its fixed forecast location')
    rows = raw.get('forecasts')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 14:
        raise ValueError('Expected 1-14 daily forecasts')
    seen = set()
    for row in rows:
        day = date.fromisoformat(row['date'])
        forecast_time = stamp(row['forecast_time'])
        # Preserve the date alongside its explicitly offset timestamp; never guess
        # a day by position in a list or by the computer's local time zone.
        local_day = datetime.fromisoformat(row['forecast_time'].replace('Z','+00:00')).date()
        if day != local_day or row['date'] in seen:
            raise ValueError('Duplicate or inconsistent forecast date/timestamp')
        if not -86400 <= forecast_time-fetched <= 14*86400:
            raise ValueError('Forecast lies outside the supported daily horizon')
        high = number(row['high'])
        high_f = high if raw['unit'] == 'F' else high*9/5+32
        if not -150 <= high_f <= 160:
            raise ValueError('Invalid daily high')
        seen.add(row['date'])
    return raw


class ShortcutFeed:
    def __init__(self, root):
        self.root = Path(root)
        self.config = self.root/'config.json'
        self.db = self.root/'receipts.sqlite'

    def folder(self):
        if self.config.exists():
            return Path(json.loads(self.config.read_text(encoding='utf-8'))['folder'])
        configured = os.getenv('WEATHERLAB_APPLE_SHORTCUTS_FOLDER', '').strip()
        if configured: return Path(configured)
        try:
            home = Path.home()
        except RuntimeError:
            return self.root/'unconfigured-sync'
        for name in ('iCloud Drive','iCloudDrive'):
            candidate = home/name/'Shortcuts'/'WeatherLab'
            if candidate.is_dir(): return candidate
        return home/'iCloud Drive'/'Shortcuts'/'WeatherLab'

    def configure(self, folder):
        p = Path(folder).expanduser()
        if not p.is_absolute() or str(p).startswith('\\\\') or not p.is_dir():
            raise ValueError('Select an existing absolute local folder synced by iCloud Drive')
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.config.with_suffix('.tmp')
        temp.write_text(json.dumps({'folder': str(p.resolve())}), encoding='utf-8')
        temp.replace(self.config)

    def state(self):
        folder = self.folder()
        return {'folder': str(folder), 'configured': folder.is_dir(),
            'transport': 'local synced files', 'freshness_seconds': MAX_AGE,
            'notice': 'Waiting for automatic iPhone exports; Shortcuts execution and sync timing must be verified on your device.'}

    def forecast(self, market, receipt_root):
        station = market['station']
        if station not in STATIONS: raise ValueError('Unsupported station')
        folder = self.folder().resolve()
        path = folder/(station+'.json')
        if not path.is_file():
            raise ValueError('Waiting for '+station+'.json from the iPhone Shortcut in the synced folder')
        if path.resolve().parent != folder:
            raise ValueError('Forecast file resolves outside the configured folder')
        with path.open('rb') as handle: payload = handle.read(MAX_BYTES+1)
        if len(payload) > MAX_BYTES: raise ValueError('Shortcut export exceeds 64 KB')
        now = time.time()
        raw = validate_export(json.loads(payload.decode('utf-8-sig')), station, now)
        rows = [r for r in raw['forecasts'] if r['date'] == market['date']]
        if len(rows) != 1: raise ValueError('No exact daily forecast for the selected contract date')
        hashed = hashlib.sha256(payload).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db, timeout=5) as db:
            db.execute('CREATE TABLE IF NOT EXISTS receipts (sha256 TEXT PRIMARY KEY, first_seen REAL NOT NULL, payload BLOB NOT NULL)')
            db.execute('INSERT OR IGNORE INTO receipts VALUES (?,?,?)', (hashed, now, payload))
            first_seen = db.execute('SELECT first_seen FROM receipts WHERE sha256=?', (hashed,)).fetchone()[0]
        if first_seen > now: raise ValueError('Local receipt chronology invalid')
        receipt = {'source': 'apple_shortcuts', 'sha256': hashed, 'received_at': first_seen,
                   'checked_at': now, 'data': raw}
        with (Path(receipt_root)/'apple-shortcuts.json').open('x', encoding='utf-8') as handle:
            json.dump(receipt, handle, allow_nan=False)
        high = number(rows[0]['high'])
        return {'station': station, 'date': market['date'],
            'high_f': high if raw['unit']=='F' else high*9/5+32,
            'source': 'apple_shortcuts', 'fetched_at': stamp(raw['fetched_at']),
            'received_at': first_seen, 'available_at': first_seen,
            'expires_at': stamp(raw['fetched_at'])+MAX_AGE,
            'evidence_id': 'shortcut-'+hashed, 'location': raw['location'],
            'location_verified': False, 'interval_verified': False,
            'provenance_authenticated': False,
            'notice': 'Automatic Apple Weather action export from iPhone Shortcuts. Location, civil-day alignment and provider freshness are device-reported; not an authenticated WeatherKit response.'}
