"""Bounded public evidence collection and immutable post-run reconciliation."""
import copy
import hashlib
import json
import sqlite3
import time
import urllib.parse
from pathlib import Path
from .core import Account, digest, number, stamp
from .sources import PublicSource, normalize_market, select_markets
from .harness import verify_run


def record_outcome(url, station, day, high, review_note, out):
    """Archive a user-reviewed CLI product. Never infer station/day from city aliases."""
    from datetime import date
    from .sources import STATIONS
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.hostname!='api.weather.gov' or not parsed.path.startswith('/products/') or parsed.query:
        raise ValueError('An exact NWS API product URL is required')
    date.fromisoformat(day)
    if station not in STATIONS or not review_note.strip() or number(high)!=int(number(high)):
        raise ValueError('Specify supported station, integer Fahrenheit maximum, and review note')
    out=Path(out)
    if out.exists():raise ValueError('Outcome output must be new')
    source=PublicSource(out.parent/(out.stem+'-receipts'),max_requests=1)
    raw,received,_=source.get(url)
    if raw.get('productCode')!='CLI' or not raw.get('productText'):
        raise ValueError('Source must be an NWS CLI text product')
    if not -150<=number(high)<=160:raise ValueError('Invalid CLI maximum')
    row={'station':station,'date':day,'actual_high_f':int(high),'source_url':url,
         'published_at':raw['issuanceTime'],'received_at':received,'reviewed':True,'review_note':review_note,
         'product_text':raw['productText'],'product_sha256':hashlib.sha256(raw['productText'].encode()).hexdigest()}
    out.write_text(json.dumps(row)+'\n',encoding='utf-8')
    return {'out':str(out),'station':station,'date':day,'requires_review':'Station, target date and MAXIMUM row supplied by the reviewer, not automatically inferred.'}


def pair_history(archive, outcomes, out, store):
    """Join our pre-day snapshots to human-reviewed CLI products without backdating."""
    forecasts=json.loads(Path(archive).read_text(encoding='utf-8'))
    actuals=[json.loads(line) for line in Path(outcomes).read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    latest={}
    for entry in forecasts:
        m,f=entry['market'],entry['forecast'];key=(m['station'],m['date'])
        if stamp(f['received_at'])>=stamp(f['day_start']) or stamp(f['issued_at'])>stamp(f['received_at']):
            raise ValueError('Forecast archive chronology invalid')
        if key not in latest or stamp(f['received_at'])>stamp(latest[key]['forecast']['received_at']):latest[key]=entry
    rows=[];seen=set()
    for actual in actuals:
        key=(actual['station'],actual['date'])
        if key in seen:raise ValueError('Duplicate CLI station-day outcome')
        seen.add(key)
        if key not in latest:raise ValueError('No pre-day forecast for CLI station-day')
        if actual.get('reviewed') is not True or not actual.get('review_note'):
            raise ValueError('CLI station/date/maximum requires a documented review')
        parsed=urllib.parse.urlparse(actual['source_url'])
        if parsed.scheme!='https' or parsed.hostname!='api.weather.gov' or not parsed.path.startswith('/products/'):
            raise ValueError('Use the exact NWS API CLI product URL')
        if not actual.get('product_text') or not actual.get('product_sha256') or hashlib.sha256(actual['product_text'].encode()).hexdigest()!=actual['product_sha256']:
            raise ValueError('CLI product text and SHA256 must match')
        value=number(actual['actual_high_f'])
        if value!=int(value) or not -150<=value<=160:raise ValueError('CLI maximum must be integer Fahrenheit')
        f=latest[key]['forecast'];received=stamp(actual['received_at']);published=stamp(actual['published_at'])
        if not stamp(f['day_end'])<=published<=received<=time.time():raise ValueError('CLI outcome chronology invalid')
        available=time.time() # Review/ingestion completed now; never backdate to the weather date.
        rows.append({'evidence_id':'history-'+digest([f,actual])[:40],'kind':'history','station':key[0],'date':key[1],
            'source':'NWS_CLI','source_url':actual['source_url'],'forecast_high_f':f['high_f'],'actual_high_f':value,
            'forecast_issued':f['issued_at'],'forecast_received':f['received_at'],'day_start':f['day_start'],'day_end':f['day_end'],
            'outcome_received':received,'published_at':published,'received_at':received,'available_at':available,
            'synthetic':False,'text':'Reviewed CLI daily maximum paired with an archived pre-day hourly grid forecast.',
            'forecast_evidence_id':f['evidence_id'],'product_sha256':actual['product_sha256'],'review_note':actual['review_note']})
    if not rows:raise ValueError('No reviewed outcomes supplied')
    out=Path(out)
    if out.exists():raise ValueError('History output must be new')
    store.ingest(rows)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    return {'history_pairs':len(rows),'out':str(out)}


def collect_evidence(root, store):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    source = PublicSource(root/'receipts', max_requests=24)
    rows, errors, forecasts = [], [], []
    try:
        inventory, received, complete = source.inventory()
        normalized = []
        for raw in inventory:
            try:
                m = normalize_market(raw, received)
                normalized.append(m)
                rows.append({'evidence_id':'rules-'+digest([m['id'],m['rules_hash'],received])[:32],
                    'kind':'rules','station':m['station'],'date':m['date'],'source':'NWS_CLI',
                    'source_url':'https://gateway.polymarket.us/v1/market/slug/'+urllib.parse.quote(m['slug'],safe=''),
                    'published_at':received,'received_at':received,'available_at':received,
                    'publication_time_policy':'Conservative first observation; publication time not independently known',
                    'synthetic':False,'text':raw['description'],'market_id':m['id'],'rules_hash':m['rules_hash']})
            except (ValueError,KeyError) as exc:
                errors.append({'slug':raw.get('slug'),'reason':str(exc)[:160]})
        seen=set()
        for m in select_markets(normalized, time.time(), len(normalized)):
            key=(m['station'],m['date'])
            if key in seen: continue
            seen.add(key)
            if len(seen)>5: break
            try:
                f=source.forecast(m)
                if stamp(f['received_at'])>=f['day_start']:
                    raise ValueError('Forecast was not received before venue day start')
                forecasts.append({'market':m,'forecast':f})
                rows.append({'evidence_id':f['evidence_id']+'-'+m['date']+'-'+digest(f)[:12],
                    'kind':'forecast','station':m['station'],'date':m['date'],'source_url':f['source_url'],
                    'published_at':f['issued_at'],'received_at':f['received_at'],'available_at':f['received_at'],
                    'synthetic':False,'text':'NWS hourly grid forecast for '+m['station']+'; not a CLI observation.',
                    'forecast':f})
            except Exception as exc:
                errors.append({'station':m['station'],'date':m['date'],'reason':str(exc)[:160]})
        added=store.ingest(rows)
        report={'inventory_complete':complete,'rules_records':sum(r['kind']=='rules' for r in rows),
                'forecast_records':len(forecasts),'history_pairs_created':0,'indexed':added,'errors':errors,
                'next_step':'After the target day, pair archived forecasts with verified station/date NWS CLI highs. Rules and forecasts alone do not unlock LLM trading.'}
    except Exception as exc:
        report={'indexed':0,'history_pairs_created':0,'errors':[{'reason':type(exc).__name__+': '+str(exc)[:160]}]}
    (root/'evidence.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    (root/'forecast-archive.json').write_text(json.dumps(forecasts,indent=2),encoding='utf-8')
    (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def verify_settlement(metadata, book, expected, received, evidence_hash):
    m=metadata['market']
    if str(m['id'])!=str(expected['market_id']) or m['slug']!=expected['slug']:
        raise ValueError('Settlement market identity mismatch')
    if hashlib.sha256(m['description'].encode()).hexdigest()!=expected['rules_hash']:
        raise ValueError('Settlement rules changed')
    if m.get('status')!='MARKET_STATUS_RESOLVED' or m.get('closed') is not True or m.get('active') is not False:
        raise ValueError('Market is not explicitly resolved and closed')
    b=book['marketData']
    if b['marketSlug']!=m['slug'] or b['state'] not in ('MARKET_STATE_EXPIRED','MARKET_STATE_CLOSED'):
        raise ValueError('Settlement book identity/state mismatch')
    stats=b['stats'];price=stats['settlementPx']
    if price['currency']!='USD' or number(price['value']) not in (0,1):
        raise ValueError('Only confirmed binary USD payouts are supported; void/partial payouts need review')
    if not stamp(m['endDate']) <= stamp(stats['settlementSetTime']) <= received:
        raise ValueError('Invalid settlement chronology')
    return {'venue':'polymarket_us','slug':m['slug'],'market_id':str(m['id']),
            'rules_hash':expected['rules_hash'],'yes_payout':number(price['value']),
            'received_at':received,'final':True,'evidence_id':'settlement-'+evidence_hash,
            'source_url':'https://gateway.polymarket.us/v1/markets/'+urllib.parse.quote(m['slug'],safe='')+'/book',
            'verification':'Resolved metadata + unchanged rules + explicit book settlementPx and settlementSetTime'}


def collect_settlement(source, expected):
    slug=urllib.parse.quote(expected['slug'],safe='')
    metadata,_,mh=source.get('https://gateway.polymarket.us/v1/market/slug/'+slug)
    book,received,bh=source.get('https://gateway.polymarket.us/v1/markets/'+slug+'/book')
    return verify_settlement(metadata,book,expected,received,digest([mh,bh]))


def reconcile(run, out):
    """Read a completed immutable journal; create a separate settlement-only report."""
    run,out=Path(run),Path(out)
    verify_run(run)
    summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
    if summary['status']!='completed' or summary.get('synthetic'):
        raise ValueError('Reconcile only completed, non-synthetic runs')
    checkpoint=json.loads((run/'checkpoint.json').read_text(encoding='utf-8'))
    account=Account()
    with sqlite3.connect('file:'+run.joinpath('journal.sqlite').as_posix()+'?mode=ro',uri=True) as db:
        last=db.execute("SELECT payload FROM events WHERE kind='account' ORDER BY seq DESC LIMIT 1").fetchone()
    if not last or json.loads(last[0])!=checkpoint['account']:
        raise ValueError('Checkpoint does not match the last verified account journal event')
    account.__dict__.update(copy.deepcopy(checkpoint['account']))
    out.mkdir(parents=True,exist_ok=False)
    source=PublicSource(out/'receipts',max_requests=24)
    expected={}
    for key,p in account.positions.items():
        if p['qty']>0:
            slug=key.rsplit(':',1)[0]
            expected[slug]={'slug':slug,'market_id':p['market_id'],'rules_hash':p['rules_hash']}
    settlements,unresolved=[],[]
    for slug,m in expected.items():
        try:
            s=collect_settlement(source,m)
            account.settle(s,time.time());settlements.append(s)
        except Exception as exc:
            unresolved.append({'slug':slug,'reason':str(exc)[:180]})
    report={'source_run':str(run),'source_journal_tip':summary['journal_tip'],
            'source_summary_hash':digest(summary),'checked_at':time.time(),'settlements':settlements,
            'unresolved':unresolved,'cash':account.cash,'realized_pnl':account.realized,
            'model_cost':account.model_cost,'account':account.__dict__,
            'complete':not unresolved,'profitability_established':False,
            'note':'Settlement-only reconciliation. No inference, new entries, old-run edits, or return/overhead recomputation.'}
    (out/'reconciliation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
