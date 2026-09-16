"""Secret-free local readiness checks and optional non-inference API access check."""
import json
import os
from pathlib import Path
import sqlite3
import time
import urllib.error
import urllib.request
from .core import number, stamp, context, levels
from .models import MODEL_NAMES
from .sources import NoRedirect


def check_models():
    key = os.getenv('OPENAI_API_KEY', '')
    if not key:
        return {'status': 'blocked', 'reason': 'OPENAI_API_KEY is missing; enter it in the local .env.'}
    req = urllib.request.Request('https://api.openai.com/v1/models', headers={'Authorization':'Bearer '+key}, method='GET')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=10) as response:
            raw = response.read(2000001)
        if len(raw)>2000000:
            raise ValueError()
        ids = {r['id'] for r in json.loads(raw)['data']}
        models = {tier:os.getenv('WEATHERLAB_MODEL_'+tier.upper(), default) for tier,default in MODEL_NAMES.items()}
        return {'status':'checked', 'checked_at':time.time(), 'models':{
            tier:{'model':model,'listed':model in ids} for tier,model in models.items()},
            'inference_validated':False, 'note':'Model listing checks access only; no inference request or billing test.'}
    except urllib.error.HTTPError as exc:
        return {'status':'error','reason':'OpenAI model listing returned HTTP '+str(exc.code)}
    except Exception:
        return {'status':'error','reason':'Model listing failed; provider error bodies are not logged.'}


def readiness(root, rag=None, dataset=None, settings=None):
    root = Path(root)
    blockers = []
    key_present = bool(os.getenv('OPENAI_API_KEY',''))
    enabled = os.getenv('WEATHERLAB_ENABLE_CLOUD') == '1'
    if not key_present: blockers.append('Add OPENAI_API_KEY to the local .env.')
    if not enabled: blockers.append('Cloud inference is disabled.')
    try:
        cap = number(os.getenv('WEATHERLAB_DAILY_API_BUDGET_USD','0'))
        budget_ok = 0 < cap <= 20
    except ValueError:
        cap, budget_ok = None, False
    if not budget_ok: blockers.append('Choose a daily API budget above $0 and at most $20.')
    tiers = {}
    for tier,default in MODEL_NAMES.items():
        try:
            price = [number(v) for v in os.getenv('WEATHERLAB_PRICE_'+tier.upper(),'').split(',')]
            valid = len(price)==2 and min(price)>0
        except ValueError: valid=False
        tiers[tier] = {'model':os.getenv('WEATHERLAB_MODEL_'+tier.upper(),default),'pricing_configured':valid}
        if not valid: blockers.append('Set the verified '+tier+' input/output token prices.')
    counts, total = {}, 0
    if rag:
        with rag.connect() as db:
            records = db.execute("SELECT payload FROM evidence").fetchall()
        dates = {}
        for (payload,) in records:
            r = json.loads(payload)
            if r.get('synthetic'): continue
            total += 1
            if r['kind']=='history' and r.get('source')=='NWS_CLI' and stamp(r['available_at']) <= time.time():
                dates.setdefault(r['station'],set()).add(r['date'])
        counts = {station:len(days) for station,days in dates.items()}
    if not any(n>=10 for n in counts.values()): blockers.append('Collect/import at least 10 causal CLI forecast/outcome station-days; rules alone do not qualify.')
    market_checks = []
    now=time.time()
    if dataset and dataset.get('frames'):
        for original in dataset['frames'][-1].get('markets',[]):
            m=dict(original)
            try:
                if dataset.get('synthetic'): raise ValueError('Synthetic dataset is not cloud-ready')
                if rag and m.get('forecast'): m['history']=rag.retrieve(m,now)['history']
                context(m,now)
                if not levels(m,'YES','SELL',now) or not levels(m,'YES','BUY',now): raise ValueError('Two-sided book required')
                reason,ok='Eligible input snapshot; no model access validation implied',True
            except (ValueError,KeyError,TypeError) as exc: reason,ok=str(exc)[:160],False
            market_checks.append({'slug':m['slug'],'eligible':ok,'reason':reason})
    settings=settings or {}
    wallet_ready=bool(settings.get('wallet')) and (root/'reference-mappings.json').exists()
    return {'checked_at':now,'cloud_configured':key_present and enabled and budget_ok and all(t['pricing_configured'] for t in tiers.values()),
            'api_key_present':key_present,'cloud_enabled':enabled,'daily_budget_usd':cap,'models':tiers,
            'real_evidence_records':total,'history_station_days':counts,'blockers':blockers,
            'market_checks':market_checks,'wallet_inputs_present':wallet_ready,
            'wallet_note':'A wallet and reviewed exact US rules mapping are required. Presence alone does not validate mapping.',
            'inference_validated':False,'research_ready':False}
