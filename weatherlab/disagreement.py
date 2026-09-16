"""Prospective Apple/NWS/book study. GET-only; no trading or model authority."""
import copy
import hashlib
import json
import math
import os
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from .core import number, stamp, levels, quote, complete_partition
from .sources import PublicSource, NoRedirect, STATIONS, normalize_market

# Daily CLI products use local standard time. Ask Apple to roll up that same
# interval, then verify returned boundaries against the actual contract anyway.
ZONES = {'KLAX': 'Etc/GMT+8', 'KSFO': 'Etc/GMT+8',
         'KNYC': 'Etc/GMT+5', 'KMIA': 'Etc/GMT+5', 'KMDW': 'Etc/GMT+6'}


def apple_configured():
    return bool(os.getenv('WEATHERLAB_WEATHERKIT_TOKEN') or all(os.getenv('WEATHERLAB_WEATHERKIT_'+k)
        for k in ('TEAM_ID', 'KEY_ID', 'SERVICE_ID', 'KEY_PATH')))


def apple_token():
    token = os.getenv('WEATHERLAB_WEATHERKIT_TOKEN', '').strip()
    if token: return token
    if not apple_configured(): raise ValueError('WeatherKit credentials missing. Configure the local WeatherKit settings and restart the dashboard.')
    node = shutil.which('node')
    if not node: raise ValueError('Node.js is required for local WeatherKit signing')
    try:
        path = Path(os.environ['WEATHERLAB_WEATHERKIT_KEY_PATH'])
        if not path.is_absolute() or path.stat().st_size > 8192: raise ValueError()
        body = {'privateKey': path.read_text(encoding='utf-8'),
            'team': os.environ['WEATHERLAB_WEATHERKIT_TEAM_ID'], 'keyId': os.environ['WEATHERLAB_WEATHERKIT_KEY_ID'],
            'service': os.environ['WEATHERLAB_WEATHERKIT_SERVICE_ID'], 'now': int(time.time())}
        env = {k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','PATH','TEMP','TMP')}
        result = subprocess.run([node, str(Path(__file__).with_name('weatherkit_signer.cjs'))],
            input=json.dumps(body), text=True, capture_output=True, timeout=5, env=env,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or len(result.stdout)>8192 or result.stdout.count('.') != 2: raise ValueError()
        return result.stdout
    except Exception:
        raise ValueError('Local WeatherKit signing failed; check IDs and the P-256 key file') from None


def write_new(path, data):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(data, handle, allow_nan=False, indent=2)


def validate_target(station, day):
    if station not in STATIONS:
        raise ValueError('Choose a supported settlement station')
    date.fromisoformat(day)


def weatherkit_get(path, root, name, token):
    # Fixed host, no redirects; never persist the Authorization header or error body.
    url = 'https://weatherkit.apple.com'+path
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer '+token,
        'Accept': 'application/json'}, method='GET')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=7) as response:
            raw = response.read(4000001)
    except Exception as exc:
        raise ValueError('WeatherKit request failed ('+type(exc).__name__+'); check the local token and access') from None
    if len(raw) > 4000000:
        raise ValueError('Oversized WeatherKit payload')
    received = time.time()
    data = json.loads(raw)
    write_new(Path(root)/name, {'url': url, 'received_at': received,
        'sha256': hashlib.sha256(raw).hexdigest(), 'data': data})
    return data, received


def parse_apple(raw, m, lat, lon, received):
    daily = raw['forecastDaily']; meta = daily['metadata']
    if meta.get('temporarilyUnavailable') or meta.get('units') != 'm':
        raise ValueError('WeatherKit metric daily data unavailable')
    if not stamp(meta['readTime']) <= received < stamp(meta['expireTime']):
        raise ValueError('WeatherKit data is expired or future-dated')
    if abs(number(meta['latitude'])-lat) > .02 or abs(number(meta['longitude'])-lon) > .02:
        raise ValueError('WeatherKit location mismatch')
    # Match exact UTC interval, including daylight-saving differences. Never choose
    # by the UTC date prefix or silently substitute an adjacent civil day.
    days = [d for d in daily['days'] if stamp(d['forecastStart']) == stamp(m['day_start'])
            and stamp(d['forecastEnd']) == stamp(m['close_at'])]
    if len(days) != 1:
        raise ValueError('Apple daily interval differs from the venue weather day; no aligned comparison')
    high = number(days[0]['temperatureMax'])*9/5+32
    if not -150 <= high <= 160:
        raise ValueError('Invalid Apple temperature')
    return {'station': m['station'], 'date': m['date'], 'high_f': high,
        'received_at': received, 'issued_at': meta['readTime'], 'expires_at': stamp(meta['expireTime']),
        'source': 'weatherkit_daily', 'latitude': lat, 'longitude': lon,
        'location_verified': True, 'interval_verified': True,
        'notice': 'Apple WeatherKit daily forecast at station coordinates using standard-time days; iPhone location/day display may differ.'}


def apple_forecast(source, m, root):
    token = apple_token()
    loc, _, _ = source.get('https://api.weather.gov/stations/'+m['station'])
    if loc['properties']['stationIdentifier'] != m['station']:
        raise ValueError('Station mismatch')
    lon, lat = map(number, loc['geometry']['coordinates'][:2])
    query = urllib.parse.urlencode({'dataSets': 'forecastDaily', 'timezone': ZONES[m['station']]})
    raw, received = weatherkit_get(f'/api/v1/weather/en-US/{lat:.5f}/{lon:.5f}?'+query, root, 'apple.json', token)
    result = parse_apple(raw, m, lat, lon, received)
    attrs, _ = weatherkit_get('/attribution/en-US', root, 'apple-attribution.json', token)
    logo = attrs.get('logoDark@2x', '')
    legal = raw['forecastDaily']['metadata'].get('attributionURL', '')
    if not logo.startswith('/') or logo.startswith('//') or urllib.parse.urlparse(legal).scheme != 'https':
        raise ValueError('WeatherKit attribution unavailable')
    result.update(logo_url='https://weatherkit.apple.com'+logo, attribution_url=legal)
    return result


def observation(raw, station, received):
    p = raw['properties']
    if p['station'].rstrip('/').rsplit('/', 1)[-1] != station:
        raise ValueError('NWS observation station mismatch')
    observed = stamp(p['timestamp'])
    if not 0 <= received-observed <= 7200:
        raise ValueError('NWS observation stale or future-dated')
    t = p['temperature']
    if t['unitCode'] != 'wmoUnit:degC' or t.get('value') is None:
        raise ValueError('NWS temperature missing or unit unsupported')
    if t.get('qualityControl') not in ('V', 'S'):
        raise ValueError('NWS temperature quality check not accepted')
    high = number(t['value'])*9/5+32
    if not -150 <= high <= 160:
        raise ValueError('Invalid observed temperature')
    return {'temperature_f': high, 'observed_at': observed, 'received_at': received,
        'quality_control': t['qualityControl'], 'station': station,
        'notice': 'Latest station observation, not the final CLI daily maximum.'}


def matches(m, high):
    # Explicit research convention for mapping continuous forecasts to integer bins.
    rounded = math.floor(number(high)+.5)
    return (m['lower_f'] is None or rounded >= m['lower_f']) and (m['upper_f'] is None or rounded <= m['upper_f'])


def compare_market(m, apple, nws, now):
    row = {k: m[k] for k in ('id', 'slug', 'rules_hash', 'lower_f', 'upper_f')}
    row.update(apple_match=None, nws_match=None, individual_order_count=None,
               executable=False, best_bid=None, best_ask=None, ask_shares=None, bid_shares=None)
    fresh_apple = apple and stamp(apple['received_at']) <= now < stamp(apple['expires_at'])
    if fresh_apple:
        row['apple_match'] = matches(m, apple['high_f'])
    if nws and 0 <= now-stamp(nws['received_at']) <= 900 and 0 <= now-stamp(nws['issued_at']) <= 21600 and stamp(nws['issued_at']) <= stamp(nws['received_at']):
        row['nws_match'] = matches(m, nws['high_f'])
    row['forecast_disagreement'] = (row['apple_match'] != row['nws_match']) if row['apple_match'] is not None and row['nws_match'] is not None else None
    try:
        bids, asks = levels(m, 'YES', 'SELL', now), levels(m, 'YES', 'BUY', now)
        row.update(best_bid=bids[0][0] if bids else None, best_ask=asks[0][0] if asks else None,
            bid_shares=sum(q for _, q in bids), ask_shares=sum(q for _, q in asks),
            bid_levels=len(bids), ask_levels=len(asks),
            best_ask_shares=asks[0][1] if asks else 0,
            ask_shares_within_2c=sum(q for p, q in asks if p <= asks[0][0]+.020000001) if asks else 0,
            book_source_at=m['book']['source_at'], book_received=m['book']['received'])
        qty = max(1, number(m['minimum_qty']))
        cash, _ = quote(m, 'YES', 'BUY', qty, now)
        row.update(quote_qty=qty, stress_cost_per_share=cash/qty,
            break_even_probability=cash/qty, executable=True,
            status='Snapshot quote only; uncalibrated forecasts do not establish an edge')
    except (ValueError, KeyError) as exc:
        row['status'] = str(exc)
    return row


def collect_snapshot(root, station, day, source_factory=PublicSource):
    validate_target(station, day)
    root = Path(root); root.mkdir(parents=True, exist_ok=False)
    source = source_factory(root/'receipts', max_requests=24)
    report = {'station': station, 'date': day, 'started_at': time.time(), 'apple': None,
        'nws_forecast': None, 'nws_observation': None, 'markets': [], 'errors': [],
        'classification': 'forecast-disagreement study', 'apple_mode': 'weatherkit', 'trade_enabled': False,
        'final_cli_high_f': None, 'final_cli_status': 'Awaiting a separately reviewed CLI outcome',
        'profit_verified': False, 'snapshot_path': str(root/'snapshot.json')}
    def attempt(label, fn):
        try:
            return fn()
        except Exception as exc:
            report['errors'].append(label+': '+str(exc)[:200])
            return None
    try:
        inventory, received, complete = source.inventory()
        markets = []
        for raw in inventory:
            try:
                m = normalize_market(raw, received)
                if (m['station'], m['date']) == (station, day): markets.append(m)
            except (ValueError, KeyError):
                pass
        markets.sort(key=lambda m: m['slug'])
        report.update(inventory_complete=complete, matching_contracts=len(markets),
            contracts_truncated=len(markets)>12, complete_partition=complete and len(markets)<=12 and complete_partition(markets))
        if not markets:
            raise ValueError('No supported open US contracts for this station/date')
        selected = markets[:12]; m = selected[0]
        if len({(x['day_start'], x['close_at']) for x in selected}) != 1:
            raise ValueError('Venue weather-day intervals disagree')
        report.update(day_start=stamp(m['day_start']), day_end=stamp(m['close_at']))
        report['apple'] = attempt('WeatherKit', lambda: apple_forecast(source, m, root))
        def nws_forecast():
            f = source.forecast(m)
            if not 0 <= time.time()-stamp(f['issued_at']) <= 21600 or stamp(f['issued_at']) > stamp(f['received_at']):
                raise ValueError('NWS forecast stale or future-dated')
            return f
        report['nws_forecast'] = attempt('NWS full-day forecast', nws_forecast)
        def obs():
            raw, at, _ = source.get('https://api.weather.gov/stations/'+station+'/observations/latest?require_qc=true')
            return observation(raw, station, at)
        report['nws_observation'] = attempt('NWS observation', obs)
        for m in selected:
            book = attempt(m['slug'], lambda: source.book(m))
            if book is not None:
                m['book'] = book
                # Each book is compared immediately; slow later requests cannot make
                # earlier book snapshots look contemporaneously executable.
                row = compare_market(m, report['apple'], report['nws_forecast'], time.time())
                row['compared_at'] = time.time()
                report['markets'].append(row)
        apple, nws = report['apple'], report['nws_forecast']
        report['apple_fresh'] = bool(apple and stamp(apple['received_at']) <= time.time() < stamp(apple['expires_at']))
        report['apple_minus_nws_forecast_f'] = apple['high_f']-nws['high_f'] if report['apple_fresh'] and nws else None
        report['comparison_aligned'] = bool(apple and apple['location_verified'] and apple['interval_verified'])
    except Exception as exc:
        report['errors'].append(type(exc).__name__+': '+str(exc)[:200])
    report['finished_at'] = time.time()
    write_new(root/'snapshot.json', report)
    return report


def score_snapshot(snapshot, outcome, now):
    """Post-hoc weather accuracy only. Never feed final labels into the sampler."""
    if (outcome['station'], outcome['date']) != (snapshot['station'], snapshot['date']):
        raise ValueError('CLI station/day mismatch')
    if outcome.get('reviewed') is not True or not outcome.get('review_note'):
        raise ValueError('Reviewed CLI station/date/MAXIMUM required')
    url = urllib.parse.urlparse(outcome['source_url'])
    if url.scheme != 'https' or url.hostname != 'api.weather.gov' or not url.path.startswith('/products/'):
        raise ValueError('Exact NWS API product URL required')
    if hashlib.sha256(outcome['product_text'].encode()).hexdigest() != outcome['product_sha256']:
        raise ValueError('CLI product hash mismatch')
    if not snapshot['finished_at'] < snapshot['day_end'] <= stamp(outcome['published_at']) <= stamp(outcome['received_at']) <= now:
        raise ValueError('Only prospective snapshots and post-day outcomes can be scored')
    actual = number(outcome['actual_high_f'])
    if actual != int(actual) or not -150 <= actual <= 160:
        raise ValueError('CLI maximum must be integer Fahrenheit')
    apple, nws = snapshot.get('apple'), snapshot.get('nws_forecast')
    return {'station': snapshot['station'], 'date': snapshot['date'], 'actual_cli_high_f': actual,
        'apple_error_f': apple['high_f']-actual if apple and snapshot.get('apple_fresh') else None,
        'nws_error_f': nws['high_f']-actual if nws else None, 'scored_at': now,
        'profit_verified': False, 'note': 'Post-hoc weather accuracy; not a venue payout or trade P&L.'}


class DisagreementStudy:
    def __init__(self, root):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock(); self.stop = threading.Event(); self.thread = None
        self.latest = None; self.count = 0; self.error = None; self.ends_at = None
        path = self.root/'latest.json'
        if path.exists():
            previous = json.loads(path.read_text(encoding='utf-8'))
            if previous.get('apple_mode') == 'weatherkit' and (previous.get('apple') is None or previous['apple'].get('source') == 'weatherkit_daily'):
                self.latest = previous

    def state(self):
        with self.lock:
            return copy.deepcopy({'running': bool(self.thread and self.thread.is_alive()),
                'snapshots': self.count, 'ends_at': self.ends_at, 'error': self.error,
                'weatherkit_configured': apple_configured(),
                'apple_mode': 'weatherkit', 'latest': self.latest})

    def start(self, body):
        station, day = body['station'], body['date']; validate_target(station, day)
        mode = body.get('apple_mode', 'weatherkit')
        if mode != 'weatherkit': raise ValueError('WeatherKit is the only supported Apple source')
        if not apple_configured(): raise ValueError('WeatherKit credentials missing. Complete Tracker setup, then restart the dashboard.')
        duration, interval = int(body.get('duration', 3600)), int(body.get('interval', 300))
        if not 1 <= duration <= 3600 or not 60 <= interval <= 900:
            raise ValueError('Choose 1-3600 seconds duration and 60-900 seconds interval')
        with self.lock:
            if self.thread and self.thread.is_alive(): raise ValueError('Tracker already running or stopping')
            self.stop.clear(); self.count = 0; self.error = None; self.ends_at = time.time()+duration
            run = self.root/str(uuid.uuid4()); run.mkdir()
            write_new(run/'config.json', {'station':station,'date':day,'apple_mode':mode,
                'duration':duration,'interval':interval,'started_at':time.time()})
            def work():
                try:
                    while not self.stop.is_set():
                        result = collect_snapshot(run/str(self.count+1).zfill(4), station, day)
                        with self.lock:
                            self.latest = result; self.count += 1
                            (self.root/'latest.json').write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
                        if self.count >= 60 or time.time()+interval >= self.ends_at: break
                        if self.stop.wait(interval): break
                except Exception as exc:
                    with self.lock: self.error = type(exc).__name__+': '+str(exc)[:180]
            self.thread = threading.Thread(target=work, name='weather-disagreement-sampler', daemon=True)
            self.thread.start()


def main():
    import argparse
    from .models import load_env
    load_env(Path.cwd()/'.env')
    p = argparse.ArgumentParser(description='Apple/NWS public-data study and separate post-day scoring')
    sub = p.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('snapshot')
    c.add_argument('--station', choices=sorted(STATIONS), required=True)
    c.add_argument('--date', required=True); c.add_argument('--out', required=True)
    s = sub.add_parser('score')
    s.add_argument('--snapshot', required=True); s.add_argument('--outcome', required=True); s.add_argument('--out', required=True)
    args = p.parse_args()
    if args.cmd == 'snapshot':
        if not apple_configured(): raise ValueError('Configure local WeatherKit credentials before collecting a snapshot')
        result = collect_snapshot(args.out, args.station, args.date)
        print(json.dumps({'contracts':len(result['markets']), 'errors':result['errors'], 'snapshot':result['snapshot_path']}, indent=2))
    else:
        # Bounded reads; one reviewed record only. The original snapshot stays immutable.
        for path in (args.snapshot, args.outcome):
            if Path(path).stat().st_size > 4000000: raise ValueError('Oversized scoring input')
        snapshot = json.loads(Path(args.snapshot).read_text(encoding='utf-8'))
        outcome = json.loads(Path(args.outcome).read_text(encoding='utf-8-sig'))
        result = score_snapshot(snapshot, outcome, time.time())
        result.update(snapshot_sha256=hashlib.sha256(Path(args.snapshot).read_bytes()).hexdigest(),
                      outcome_sha256=hashlib.sha256(Path(args.outcome).read_bytes()).hexdigest())
        write_new(args.out, result)
        print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
