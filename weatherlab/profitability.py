"""Contract-matched, outcome-blind forecasts and explicitly hypothetical return scenarios."""
import argparse
from collections import Counter
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.parse

from .core import digest, stamp
from .historical import blind_context, read_rows
from .historical_market import validate_history
from .historical_report import STATIONS
from .models import CloudModel, load_env
from .sources import PublicSource
from .strategies import forecast

ARMS = ('statistical_baseline', 'fixed_llm', 'adaptive_llm', 'polyswarm', 'market_implied')
NAMES = ('Statistical baseline', 'Fixed LLM', 'Adaptive LLM', 'PolySwarm', 'Market implied')
POLICY = {'version':'contract-returns-v1', 'selection':'One bin containing the unadjusted MOS high per station-day; no outcome or price ranking',
          'initial_cash':50, 'cash_reserve':40, 'max_entry_cost':2, 'max_quantity':5,
          'minimum_edge':.03, 'primary_slippage':.02, 'slippages':[0,.02,.05],
          'quote_max_age_seconds':300, 'execution_delay_seconds':300, 'execution_window_seconds':180,
          'fee_coefficient':.06, 'monthly_overhead':200, 'month_days':30,
          'limits':'Hypothetical full fills, no historical quantities. Date/station blinded. Assumed MOS availability and retrospective rules. Same previously inspected dates: exploratory, not held out. Common point-probability entry rule, not the full live risk/RAG pipeline.'}


def write_json(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, allow_nan=False)


def verify_files(root, manifest):
    for name, expected in manifest['files'].items():
        if Path(name).name != name or hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Archive checksum mismatch')


def matches(high, market):
    return (market['lower_f'] is None or high >= market['lower_f']) and (market['upper_f'] is None or high <= market['upper_f'])


def contract_context(case, training, market):
    ctx = blind_context(case, training)
    ctx['contract'].update(lower_f=market['lower_f'], upper_f=market['upper_f'], rules_hash='blind-contract-range')
    residual_highs = [case['forecast_high_f']+h['actual_high_f']-h['forecast_high_f'] for h in ctx['history']]
    ctx['baseline_probability'] = (sum(matches(t, market) for t in residual_highs)+.5)/(len(residual_highs)+1)
    ctx['limitations'] = 'Exact inclusive temperature bounds, possibly open-ended. Weather probability only; market prices withheld. Archived forecast availability assumed. Station/date blinded; pretraining contamination cannot be excluded.'
    return ctx


def quote_pair(points, decision):
    before = [p for p in points if 0 <= decision-p['timestamp'] <= POLICY['quote_max_age_seconds']]
    after = [p for p in points if decision+300 <= p['timestamp'] <= decision+480]
    if not before or not after:
        raise ValueError('Missing fresh decision or delayed execution price')
    first, last = max(before, key=lambda p:p['timestamp']), min(after, key=lambda p:p['timestamp'])
    for p in (first, last):
        if not all(.01 <= p[k] <= .99 for k in ('yes_display_price','no_display_price')) or p['yes_display_price']+p['no_display_price'] < 1-1e-9:
            raise ValueError('Invalid or crossed display-price proxy')
    return first, last


def clean_history(data, start, end):
    """Second-resolution updates can conflict; omit ambiguous seconds, never guess order."""
    if not isinstance(data.get('history'),list) or len(data['history'])>20000: raise ValueError('History bound exceeded')
    grouped={}
    for row in data['history']:
        at=stamp(row['timestamp']);values=(float(row['longPrice']),float(row['shortPrice']))
        if not all(math.isfinite(v) and 0<=v<=1 for v in values): raise ValueError('Invalid display prices')
        grouped.setdefault(at,set()).add(values)
    rows=[{'timestamp':at,'longPrice':next(iter(v))[0],'shortPrice':next(iter(v))[1]} for at,v in sorted(grouped.items()) if len(v)==1]
    return validate_history({'history':rows},start,end),sum(len(v)>1 for v in grouped.values())


def prepare(corpus, archive, out):
    corpus, archive, out = map(Path, (corpus, archive, out))
    out.mkdir(exist_ok=False)
    manifest = json.loads((archive/'summary.json').read_text(encoding='utf-8'))
    if (manifest.get('start'),manifest.get('end')) != ('2026-09-06','2026-09-15'):
        raise ValueError('This dated fee protocol requires September 6-15, 2026; declare a new protocol for another period')
    verify_files(archive, manifest)
    # Settlements in this source are deliberately stripped before selection/model files.
    markets = [r['market'] for r in read_rows(archive/'market-history.jsonl')]
    source = PublicSource(out/'receipts', max_requests=55)
    selected, exclusions = [], []
    for station in STATIONS:
        folder = corpus/station
        m = json.loads((folder/'manifest.json').read_text(encoding='utf-8')); verify_files(folder, m)
        if (m.get('test_start'),m.get('test_end')) != ('2026-09-06','2026-09-15'):
            raise ValueError('Weather dates differ from the dated fee protocol')
        training = list(read_rows(folder/'training.jsonl',31))
        for case in read_rows(folder/'cases.jsonl',31):
            group = [r for r in markets if (r['station'],r['date']) == (station,case['date'])]
            candidates = [r for r in group if matches(case['forecast_high_f'],r)]
            if len(candidates) != 1:
                raise ValueError('Expected one disjoint bin containing the forecast')
            market = candidates[0]
            if stamp(market['day_start']) != case['day_start'] or stamp(market['close_at']) != case['day_end']:
                raise ValueError('Settlement day mismatch')
            decision = case['decision_at']
            row = {'station':station, 'date':case['date'], 'key':station+':'+case['date'], 'market':market,
                   'decision_at':decision, 'context':contract_context(case, training, market)}
            try:
                q = {'symbol':market['slug'],'timestamp.startTimestamp':int(decision-900),
                     'timestamp.endTimestamp':int(decision+900),'fidelity':1}
                data, received, hashed = source.get('https://gateway.polymarket.us/v1/price-history?'+urllib.parse.urlencode(q))
                points, ambiguous = clean_history(data, decision-900, decision+900)
                before, after = quote_pair(points, decision)
                row.update(decision_quote=before, execution_quote=after, price_points=len(points), ambiguous_seconds_omitted=ambiguous,
                           prices_received_at=received, prices_receipt_hash=hashed)
            except Exception as exc:
                row['excluded'] = str(exc)[:180]; exclusions.append({'key':row['key'],'reason':row['excluded']})
            selected.append(row)
    write_json(out/'protocol.json', POLICY)
    write_json(out/'cases.json', selected)
    report = {'selected':len(selected), 'eligible':sum('excluded' not in r for r in selected), 'exclusions':exclusions,
              'requests':source.count,'price_points':sum(r.get('price_points',0) for r in selected),
              'cases_hash':digest(selected),'protocol_hash':digest(POLICY),
              'corpus':str(corpus.resolve()),'archive':str(archive.resolve()),'created_at':time.time()}
    write_json(out/'preparation.json', report)
    return report


def run(prepared, station, fixture=False):
    root = Path(prepared)
    cases = json.loads((root/'cases.json').read_text(encoding='utf-8'))
    prep = json.loads((root/'preparation.json').read_text(encoding='utf-8'))
    if digest(cases) != prep['cases_hash'] or digest(POLICY) != prep['protocol_hash']:
        raise ValueError('Frozen inputs/protocol changed')
    if station not in STATIONS: raise ValueError('Unknown station')
    if fixture:
        from .models import FixtureModel
        model = FixtureModel()
    else: model = CloudModel(Path('data/model-budget.sqlite'))
    model.deadline = time.monotonic()+1800
    out = root/('fixture-'+station if fixture else station); out.mkdir(exist_ok=False)
    tip = '0'*64; counts = Counter(); start = time.monotonic(); block = None
    with (out/'predictions.jsonl').open('x', encoding='utf-8') as f:
        for case in cases:
            if case['station'] != station or 'excluded' in case: continue
            ctx = case['context']; q = case['decision_quote']
            mid = (q['yes_display_price']+1-q['no_display_price'])/2
            for arm in ARMS:
                record = {'key':case['key'], 'arm':arm, 'context_hash':digest(ctx)}
                cost_before = model.cost
                try:
                    if arm == 'statistical_baseline': p = ctx['baseline_probability']
                    elif arm == 'market_implied': p = mid
                    else:
                        if block: raise ValueError(block)
                        prediction, routing, _ = forecast(arm, ctx, model, mid)
                        record.update(prediction=prediction, routing=routing)
                        if prediction['abstain']: raise ValueError('Model abstained')
                        p = prediction['probability_yes']
                    record['probability'] = p
                except Exception as exc:
                    reason = str(exc)[:180]; record['error'] = reason
                    if any(s in reason for s in ('HTTP 401','HTTP 403','HTTP 429','budget exhausted','Insufficient remaining')): block = reason
                record.update(calls=list(model.calls), cost_or_reserved_usd=model.cost-cost_before)
                counts['validated_calls'] += len(model.calls); model.calls.clear()
                tip = digest({'previous':tip,'record':record});record['chain_hash'] = tip
                f.write(json.dumps(record,allow_nan=False)+'\n'); f.flush()
                counts[arm] += 1
                print(json.dumps({'station':station,'key':case['key'],'arm':arm,'ok':'error' not in record}),flush=True)
    result = {'station':station,'counts':dict(counts),'prediction_chain_tip':tip,'cases_hash':prep['cases_hash'],
              'protocol_hash':prep['protocol_hash'],'seconds':time.monotonic()-start,'fixture':fixture,
              'cost_or_reserved_usd':model.cost,'code_hash':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    write_json(out/'summary.json', result)
    return result


def fee(qty, price):
    p = Decimal(str(price))
    return float((Decimal('.06')*Decimal(str(qty))*p*(1-p)).quantize(Decimal('.01'),rounding=ROUND_HALF_EVEN))


def signal(probability, quote):
    candidates = []
    for side, p, price in [('YES',probability,quote['yes_display_price']),('NO',1-probability,quote['no_display_price'])]:
        # Primary assumptions choose signals once; sensitivity never selects using outcomes.
        entry = round(price+POLICY['primary_slippage'], 8)
        edge = p-entry-.06*entry*(1-entry)
        if entry <= .99 and edge >= POLICY['minimum_edge']: candidates.append((edge,side))
    return max(candidates)[1] if candidates else None


def simulate(rows, slip, model_cost, overhead):
    cash = 50.; pending = []; trades = []; skips = Counter(); fees = 0.; deployed = 0.; curve = []
    def settle(at):
        nonlocal cash
        due = sorted([p for p in pending if p['settled_at'] <= at],key=lambda p:(p['settled_at'],p['key']))
        for p in due:
            cash += p['payout']; pending.remove(p)
            curve.append({'at':p['settled_at'],'trading_pnl':cash+sum(x['cost'] for x in pending)-50})
    for r in sorted(rows,key=lambda r:(r['execution_quote']['timestamp'],r['key'])):
        settle(r['execution_quote']['timestamp'])
        if 'error' in r: skips['model_failure_or_abstention'] += 1;continue
        side = signal(r['probability'],r['decision_quote'])
        if side is None: skips['insufficient_edge'] += 1;continue
        entry = round(r['execution_quote']['yes_display_price' if side=='YES' else 'no_display_price']+slip,8)
        if entry > .99: skips['price_above_limit'] += 1;continue
        # Price is observed only after committing signal; do not reverse side with hindsight.
        budget = min(2.,cash-40.)
        qty = max((q for q in range(1,6) if q*entry+fee(q,entry) <= budget+1e-9),default=0)
        if not qty: skips['cash_reserve_or_minimum_size'] += 1;continue
        charge = fee(qty,entry); cost = qty*entry+charge
        payout = qty*(r['yes_payout'] if side=='YES' else 1-r['yes_payout'])
        trade = {'key':r['key'],'slug':r['slug'],'side':side,'qty':qty,'entry':entry,'fee':charge,'cost':cost,
                 'payout':payout,'pnl':payout-cost,'entered_at':r['execution_quote']['timestamp'],
                 'settled_at':r['settled_at'],'quote_age_at_decision':r['decision_at']-r['decision_quote']['timestamp']}
        cash -= cost
        if cash < 40-1e-8: raise ValueError('Reserve breach')
        pending.append(trade); trades.append(trade);fees += charge;deployed += cost
    settle(float('inf'))
    trading = cash-50
    return {'slippage_per_share':slip,'trades':len(trades),'wins':sum(t['pnl']>0 for t in trades),
            'win_rate':sum(t['pnl']>0 for t in trades)/len(trades) if trades else None,
            'trading_pnl':trading,'entry_fees':fees,'capital_deployed':deployed,
            'return_on_initial_cash':trading/50,'pnl_after_models':trading-model_cost,
            'net_after_all_costs':trading-model_cost-overhead,'skips':dict(skips),
            'trade_ledger':trades,'settled_pnl_curve':curve}


def report(prepared):
    root = Path(prepared); prep = json.loads((root/'preparation.json').read_text(encoding='utf-8'))
    cases = json.loads((root/'cases.json').read_text(encoding='utf-8'))
    if digest(cases) != prep['cases_hash'] or digest(POLICY) != prep['protocol_hash']: raise ValueError('Frozen inputs changed')
    bykey = {c['key']:c for c in cases if 'excluded' not in c}; predictions = []; calls=[]
    for station in STATIONS:
        s = json.loads((root/station/'summary.json').read_text(encoding='utf-8'))
        if s['fixture'] or s['cases_hash'] != prep['cases_hash'] or s['protocol_hash'] != prep['protocol_hash']:
            raise ValueError('Run identity mismatch')
        tip='0'*64; seen=set()
        for r in read_rows(root/station/'predictions.jsonl'):
            entry=dict(r); recorded=entry.pop('chain_hash')
            tip=digest({'previous':tip,'record':entry})
            if tip!=recorded or (r['key'],r['arm']) in seen: raise ValueError('Prediction chain/duplicate mismatch')
            if r['key'] not in bykey or r['arm'] not in ARMS or r['context_hash']!=digest(bykey[r['key']]['context']): raise ValueError('Prediction input mismatch')
            seen.add((r['key'],r['arm'])); predictions.append(r);calls.extend(r['calls'])
        if tip!=s['prediction_chain_tip']: raise ValueError('Prediction tip mismatch')
        expected={(k,a) for k,c in bykey.items() if c['station']==station for a in ARMS}
        if seen!=expected: raise ValueError('Incomplete arm coverage')
    # Only now open settlement and outcome sources, after verifying committed predictions.
    archive=Path(prep['archive']); verify_files(archive,json.loads((archive/'summary.json').read_text(encoding='utf-8')))
    market_rows={r['market']['slug']:r for r in read_rows(archive/'market-history.jsonl')}
    labels={}
    for station in STATIONS:
        folder=Path(prep['corpus'])/station
        verify_files(folder,json.loads((folder/'manifest.json').read_text(encoding='utf-8')))
        labels.update({station+':'+r['case_id']:r for r in read_rows(folder/'labels.jsonl',31)})
    joined=[]
    for r in predictions:
        c=bykey[r['key']];m=c['market'];settlement=market_rows[m['slug']]['settlement']; y=settlement['yes_payout']
        if y!=int(matches(labels[r['key']]['actual_high_f'],m)) or settlement['published_at']<stamp(m['close_at']): raise ValueError('CLI / settlement mismatch')
        joined.append({**r,**{k:c[k] for k in ('decision_at','decision_quote','execution_quote')},'slug':m['slug'],
                       'yes_payout':y,'settled_at':settlement['published_at']})
    start=min(c['decision_at'] for c in bykey.values());end=max(r['settled_at'] for r in joined)
    overhead_days=(end-start)/86400;overhead=200*overhead_days/30
    arms=[]; paired=set.intersection(*(set(r['key'] for r in joined if r['arm']==a and 'error' not in r) for a in ARMS))
    for arm,name in zip(ARMS,NAMES):
        rows=[r for r in joined if r['arm']==arm];good=[r for r in rows if 'error' not in r]
        cost=sum(r['cost_or_reserved_usd'] for r in rows)
        arms.append({'id':arm,'name':name,'scored':len(good),'eligible':len(bykey),'errors':dict(Counter(r['error'] for r in rows if 'error' in r)),
                     'brier':sum((r['probability']-r['yes_payout'])**2 for r in good)/len(good) if good else None,
                     'paired_brier':sum((r['probability']-r['yes_payout'])**2 for r in good if r['key'] in paired)/len(paired) if paired else None,
                     'model_cost_or_reserved_usd':cost,'scenarios':[simulate(rows,s,cost,overhead) for s in POLICY['slippages']]})
    return {'status':'complete','created_at':time.time(),'policy':POLICY,'preparation':prep,'arms':arms,
            'paired_cases':len(paired),'validated_calls':len(calls),'models':dict(Counter(c['model'] for c in calls)),
            'cost_or_reserved_usd':sum(a['model_cost_or_reserved_usd'] for a in arms),
            'overhead_days':overhead_days,'overhead_per_arm':overhead,'start':start,'settlement_end':end,
            'profitability_established':False,'fills_verified':False,'control_status':'Not evaluated: historical depth and reference-wallet signals unavailable',
            'sources':['https://docs.polymarket.us/fees','https://docs.polymarket.us/api-reference/price-history/get-price-history',
                       'https://mesonet.agron.iastate.edu/api/1/mos.json','https://mesonet.agron.iastate.edu/json/cli.py']}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--corpus',required=True);a.add_argument('--archive',required=True);a.add_argument('--out',required=True)
    a=sub.add_parser('run');a.add_argument('--prepared',required=True);a.add_argument('--station',required=True);a.add_argument('--fixture',action='store_true')
    a=sub.add_parser('report');a.add_argument('--prepared',required=True);a.add_argument('--out',required=True)
    a=p.parse_args();load_env('.env')
    if a.command=='prepare': result=prepare(a.corpus,a.archive,a.out)
    elif a.command=='run': result=run(a.prepared,a.station,a.fixture)
    else: result=report(a.prepared);write_json(a.out,result)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
