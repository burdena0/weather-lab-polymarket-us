"""Polymarket US private account reads. No order or transfer transport exists here."""
import base64
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.request

PATHS = frozenset(('/v1/account/balances', '/v1/portfolio/positions'))


def decrypt_windows(data):
    if os.name != 'nt':
        raise ValueError('Saved Windows credentials require the original Windows user')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    outgoing = Blob()
    fn = ctypes.WinDLL('crypt32', use_last_error=True).CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ValueError('Windows could not unlock the saved credentials')
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        free = ctypes.WinDLL('kernel32').LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(ctypes.cast(outgoing.data, ctypes.c_void_p))


def sign(secret, message):
    try:
        seed = base64.b64decode(secret, validate=True)
    except Exception:
        raise ValueError('Invalid account signing key format') from None
    if len(seed) not in (32, 64):
        raise ValueError('Account signing key must contain a 32-byte seed')
    node = shutil.which('node')
    if not node:
        raise ValueError('Account linking requires Node.js with built-in Ed25519 support')
    env = {k: v for k, v in os.environ.items() if k.upper() in ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP')}
    try:
        result = subprocess.run([node, str(Path(__file__).with_name('account_signer.cjs'))],
                                input=json.dumps({'seed': base64.b64encode(seed[:32]).decode(), 'message': message}),
                                capture_output=True, text=True, timeout=5, env=env,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        signature = result.stdout.strip()
        if result.returncode or len(base64.b64decode(signature, validate=True)) != 64:
            raise ValueError()
        return signature
    except Exception:
        raise ValueError('Account signature could not be generated') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Account API redirect rejected')


def private_get(credentials, path):
    if path not in PATHS:
        raise ValueError('Account endpoint is outside the read-only allowlist')
    timestamp = str(int(time.time() * 1000))
    signature = sign(credentials['secret'], timestamp + 'GET' + path)
    request = urllib.request.Request('https://api.polymarket.us' + path, method='GET', headers={
        'X-PM-Access-Key': credentials['key_id'], 'X-PM-Timestamp': timestamp,
        'X-PM-Signature': signature, 'Accept': 'application/json', 'User-Agent': 'WeatherLab/1.0'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=8) as response:
            raw = response.read(1000001)
        if len(raw) > 1000000:
            raise ValueError('Account response exceeded the size limit')
        return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Polymarket US account request returned HTTP {exc.code}') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('Polymarket US account request timed out or could not connect') from None


def amount(value):
    if isinstance(value, bool):
        raise ValueError('Invalid account balance response')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Invalid account balance response')
    return number


class AccountLink:
    def __init__(self, root):
        self.root = Path(root)
        self.config = self.root / 'account-link.json'
        self.linked = self.config.exists() and json.loads(self.config.read_text(encoding='utf-8')).get('linked') is True
        self.snapshot = {'status': 'unverified' if self.linked else 'disconnected', 'linked': self.linked,
                         'read_only': True, 'checked_at': None}

    def credentials(self):
        key = os.getenv('WEATHERLAB_POLYMARKET_KEY_ID', '')
        secret = os.getenv('WEATHERLAB_POLYMARKET_SECRET_KEY', '')
        if key and secret:
            return {'key_id': key, 'secret': secret}
        override = os.getenv('WEATHERLAB_POLYMARKET_DPAPI_PATH', '')
        # Existing SupahTrade layout only; standalone deployments use .env.
        candidate = Path(override) if override else self.root.parent.parent.parent / 'data/connections/polymarket-us.dpapi'
        if not candidate.is_file():
            raise ValueError('No saved account credentials found. Configure the local .env; never paste keys into chat.')
        if candidate.stat().st_size > 16384:
            raise ValueError('Saved account credential file is invalid')
        result = json.loads(decrypt_windows(candidate.read_bytes()))
        if not isinstance(result.get('key_id'), str) or not isinstance(result.get('secret'), str):
            raise ValueError('Saved account credentials are incomplete')
        return result

    def state(self):
        return dict(self.snapshot)

    def refresh(self):
        try:
            credentials = self.credentials()
            balances = private_get(credentials, '/v1/account/balances')
            rows = [r for r in balances['balances'] if r.get('currency') == 'USD']
            if len(rows) != 1:
                raise ValueError('Expected exactly one USD account balance')
            row = rows[0]
            snapshot = {'linked': True, 'read_only': True, 'status': 'connected', 'checked_at': time.time(),
                        'buying_power': amount(row['buyingPower']),
                        'current_balance': amount(row['currentBalance']) if row.get('currentBalance') is not None else None,
                        'positions_count': None, 'positions_complete': False}
            try:
                positions = private_get(credentials, '/v1/portfolio/positions')
                if not isinstance(positions.get('positions'), dict):
                    raise ValueError('Unexpected positions response')
                snapshot.update(positions_count=len(positions['positions']),
                                positions_complete=positions.get('eof') is True and not positions.get('nextCursor'))
            except Exception:
                snapshot['positions_notice'] = 'Positions unavailable; balance authentication succeeded.'
            self.root.mkdir(parents=True, exist_ok=True)
            temp = self.config.with_suffix('.tmp')
            temp.write_text('{"linked":true}', encoding='utf-8')
            temp.replace(self.config)
            self.linked = True
            self.snapshot = snapshot
        except Exception as exc:
            # Never expose provider bodies, credentials, file contents, or signing input.
            message = str(exc) if isinstance(exc, ValueError) and str(exc).startswith((
                'Polymarket US account request', 'No saved account credentials', 'Windows could not',
                'Account linking requires', 'Saved Windows credentials')) else 'Account verification failed; check local credentials and connectivity.'
            self.snapshot = {'linked': self.linked, 'read_only': True, 'status': 'error',
                             'checked_at': time.time(), 'error': message}
        return self.state()

    def disconnect(self):
        self.config.unlink(missing_ok=True)
        self.linked = False
        self.snapshot = {'linked': False, 'read_only': True, 'status': 'disconnected', 'checked_at': None}
        return self.state()
