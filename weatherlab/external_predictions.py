"""Private-model probability intake. Imports data only, never executable models."""
import json
import re
from datetime import date
from pathlib import Path
from .core import digest, number, stamp

INPUT_FIELDS = {
    'schema_version', 'model_id', 'model_version_sha256', 'training_end',
    'model_frozen_at', 'input_available_through', 'generated_at', 'expires_at',
    'venue', 'station', 'date', 'source', 'market_id', 'rules_hash',
    'lower_f', 'upper_f', 'probability_yes', 'synthetic',
}
GUIDANCE = ('External probabilities are unverified user-model outputs. Their training and input '
            'timestamps are declarations; only local receipt is independently recorded. '
            'Do not treat these as observed temperatures, calibrated confidence, independent '
            'confirmation, or proof of nitrogen-related predictive skill. Risk gates still apply.')


def validate_input(row):
    from .sources import STATIONS
    if not isinstance(row, dict) or len(json.dumps(row, allow_nan=False).encode()) > 4096:
        raise ValueError('External prediction must be an object of at most 4 KB')
    if set(row) != INPUT_FIELDS:
        raise ValueError('External prediction requires exactly the documented fields')
    if type(row['schema_version']) is not int or row['schema_version'] != 1:
        raise ValueError('External prediction schema must be 1')
    if not isinstance(row['model_id'], str) or not re.fullmatch(r'[a-z0-9_-]{1,64}', row['model_id']):
        raise ValueError('Invalid external model ID')
    for field in ('model_version_sha256', 'rules_hash'):
        if not isinstance(row[field], str) or not re.fullmatch(r'[a-f0-9]{64}', row[field]):
            raise ValueError('External prediction needs '+field)
    if row['venue'] != 'polymarket_us' or row['source'] != 'NWS_CLI' or row['station'] not in STATIONS:
        raise ValueError('External prediction requires supported exact US station and source')
    date.fromisoformat(row['date'])
    if not isinstance(row['market_id'], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}', row['market_id']):
        raise ValueError('Exact market_id required')
    if type(row['synthetic']) is not bool or not 0 <= number(row['probability_yes']) <= 1:
        raise ValueError('Explicit synthetic flag and probability in [0,1] required')
    lo, hi = row['lower_f'], row['upper_f']
    for value in (lo, hi):
        if value is not None and (type(value) is not int or not -150 <= value <= 160):
            raise ValueError('Bounds must be integer Fahrenheit or null')
    if lo is None and hi is None or lo is not None and hi is not None and lo > hi:
        raise ValueError('Invalid contract interval')
    train, frozen, inputs, generated, expires = [stamp(row[k]) for k in
        ('training_end', 'model_frozen_at', 'input_available_through', 'generated_at', 'expires_at')]
    if not 0 <= train <= frozen <= generated < expires or not 0 <= inputs <= generated:
        raise ValueError('External prediction chronology violated')
    if expires-generated > 86400:
        raise ValueError('Prediction validity cannot exceed 24 hours')
    return row


def validate_record(row):
    raw = {k: row[k] for k in INPUT_FIELDS}
    validate_input(raw)
    if row['kind'] != 'external_prediction' or row['evidence_id'] != 'external-'+digest(raw):
        raise ValueError('External prediction identity mismatch')
    if (stamp(row['published_at']) != stamp(row['generated_at']) or
        not stamp(row['generated_at']) <= stamp(row['received_at']) == stamp(row['available_at']) < stamp(row['expires_at'])):
        raise ValueError('External receipt chronology violated')
    if row.get('source_url') != 'urn:weatherlab:external-model:'+row['model_version_sha256']:
        raise ValueError('Private model provenance mismatch')
    if row.get('text') != GUIDANCE:
        raise ValueError('External model limitations must be retained')
    return row


def import_file(path, store, now):
    """Bounded atomic batch; identical reimports retain their first receipt."""
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError('Prediction file exceeds 2 MB; split batches')
    with path.open('rb') as f:
        raw_file = f.read(2_000_001)
    if len(raw_file) > 2_000_000:
        raise ValueError('Prediction file exceeds 2 MB; split batches')
    rows = []
    with store.connect() as db:
        for line in raw_file.decode('utf-8-sig').splitlines():
            if not line.strip():
                continue
            raw = validate_input(json.loads(line))
            ident = 'external-'+digest(raw)
            existing = db.execute('SELECT payload FROM evidence WHERE id=?', (ident,)).fetchone()
            if existing:
                rows.append(json.loads(existing[0]))
            else:
                if not stamp(raw['generated_at']) <= now < stamp(raw['expires_at']):
                    raise ValueError('Prediction is future-dated or expired at local receipt')
                rows.append(dict(raw, evidence_id=ident, kind='external_prediction',
                    published_at=raw['generated_at'], received_at=now, available_at=now,
                    source_url='urn:weatherlab:external-model:'+raw['model_version_sha256'], text=GUIDANCE))
            if len(rows) > 1000:
                raise ValueError('At most 1000 predictions per import')
    if not rows:
        raise ValueError('Prediction file is empty')
    return {'indexed':store.ingest(rows, external_receipt_at=now), 'records':len(rows), 'received_at':now,
            'note':'Unverified model outputs; no training, inference or orders executed.'}


def retrieve(db, market, now, allow_synthetic=False):
    # Limit before materialization. Latest generation per model (including expired
    # revisions) wins, so an expired replacement cannot resurrect an old forecast.
    rows = db.execute("""SELECT payload FROM evidence
        WHERE kind='external_prediction' AND station=? AND event_date=?
        AND published<=? AND received<=? AND available<=?
        AND json_extract(payload,'$.market_id')=?
        AND json_extract(payload,'$.rules_hash')=?
        AND (? OR json_extract(payload,'$.synthetic')=0)
        ORDER BY published DESC, received DESC, id DESC LIMIT 201""",
        (market['station'], market['date'], now, now, now, str(market['id']), market['rules_hash'], allow_synthetic)).fetchall()
    if len(rows) > 200:
        return [], {'reason':'More than 200 matching revisions; narrow the prediction archive'}
    decoded = [validate_record(json.loads(payload)) for (payload,) in rows]
    selected, seen = [], set()
    for row in decoded:
        if row['model_id'] in seen:
            continue
        seen.add(row['model_id'])
        same_generation = [r for r in decoded if r['model_id'] == row['model_id'] and
                           stamp(r['generated_at']) == stamp(row['generated_at'])]
        if len(same_generation) > 1:
            continue
        if stamp(row['expires_at']) <= now or any(row[k] != market[k] for k in ('source', 'lower_f', 'upper_f')):
            continue
        selected.append(row)
        if len(selected) == 3:
            break
    return selected, {'selected_ids':[r['evidence_id'] for r in selected],
                      'verification':'user_declared_model_metadata; local_receipt_recorded',
                      'payload_hashes':{r['evidence_id']:digest(r) for r in selected}}


def inventory(db):
    count = db.execute("SELECT COUNT(*) FROM evidence WHERE kind='external_prediction'").fetchone()[0]
    return {'records':count, 'status':'predictions_imported_unvalidated' if count else 'waiting_for_predictions',
            'note':'Count includes expired/synthetic rows. Actual eligibility is checked per contract and decision.'}
