"""Exploratory, chronological policy comparisons on committed forecast outputs.

No new cloud calls, trades or parameter changes to running strategies. Cached-call
cost savings are counterfactual; original invoices/reservations are not erased.
"""
import argparse
import copy
import json
import time
from pathlib import Path
from .core import digest
from .profitability import ARMS, NAMES, POLICY, load_verified_rows, simulate, signal, write_json


def candidates():
    variants = []
    for arm, name in zip(ARMS, NAMES):
        variants.append(dict(id=arm+'__original', arm=arm, name=name+' / original',
            threshold=.03, market_weight=0, gate=None, recheck=False))
        if arm == 'market_implied':
            continue
        variants.append(dict(id=arm+'__execution', arm=arm, name=name+' / recheck entry',
            threshold=.03, market_weight=0, gate=None, recheck=True))
        variants.append(dict(id=arm+'__strong_edge', arm=arm, name=name+' / 8pp net edge',
            threshold=.08, market_weight=0, gate=None, recheck=True))
        variants.append(dict(id=arm+'__blend', arm=arm, name=name+' / half market blend',
            threshold=.03, market_weight=.5, gate=None, recheck=True))
        if arm != 'statistical_baseline':
            variants.append(dict(id=arm+'__cheap_gate', arm=arm, name=name+' / cheap pre-call gate',
                threshold=.03, market_weight=0, gate=.08, recheck=True))
            variants.append(dict(id=arm+'__combined', arm=arm, name=name+' / combined',
                threshold=.08, market_weight=.5, gate=.08, recheck=True))
    return variants


def transform(rows, variant, baselines):
    """Gate uses numerical forecast and decision quote, never outcome or future quote."""
    result, paid_cost, consulted, withheld = [], 0., 0, 0
    for original in rows:
        r = copy.deepcopy(original)
        if variant['gate'] is not None and signal(baselines[r['key']], r['decision_quote'], variant['gate']) is None:
            r.pop('probability', None);r['error']='pre_call_gate';withheld += 1
        else:
            paid_cost += r['cost_or_reserved_usd']
            consulted += int(variant['arm'] in ('fixed_llm','adaptive_llm','polyswarm'))
            if 'error' not in r:
                quote=r['decision_quote'];market=(quote['yes_display_price']+1-quote['no_display_price'])/2
                weight=variant['market_weight'];r['probability']=(1-weight)*r['probability']+weight*market
        result.append(r)
    return result, paid_cost, consulted, withheld


def period_result(rows, variant, baselines, overhead):
    changed, cost, consulted, withheld = transform(rows, variant, baselines)
    return {'cases':len(rows), 'model_decisions_consulted':consulted, 'model_decisions_withheld':withheld,
            'modeled_model_cost':cost, 'scenarios':[
                simulate(changed,slip,cost,overhead,minimum_edge=variant['threshold'],recheck_edge=variant['recheck'])
                for slip in POLICY['slippages']]}


def select_on_development(results):
    # Conservative objective and explicit deterministic tie break. Trading volume
    # is never rewarded. The no-trade market benchmark is a legitimate choice.
    def score(r):
        scenarios=r['development']['scenarios']
        worst=min(s['pnl_after_models'] for s in scenarios if s['slippage_per_share'] >= .02)
        return (-worst,r['development']['modeled_model_cost'],r['variant']['id'])
    return min(results,key=score)['variant']['id']


def run(prepared, output):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    plan={'version':'profit-policy-comparison-v1','created_at':time.time(),
          'candidate_count':len(candidates()),'candidates':candidates(),
          'split':'First four target dates for development. Later dates eligible only when every decision follows all development settlements.',
          'selection':'Maximize development worst P&L after models across 2c and 5c scenarios; ties prefer lower cost then ID.',
          'capital':{'initial':50,'reserve':40,'max_entry_cost':2,'max_shares':5,'monthly_overhead':200},
          'new_cloud_calls':0,'external_model_predictions':0,
          'article_rag_used_in_historical_forecasts':False,
          'limitation':'Previously inspected dates and forecasts. Exploratory comparison, not an untouched holdout or future-profit prediction.'}
    write_json(out/'plan.json',plan)
    prep,cases,joined,calls=load_verified_rows(prepared)
    days=sorted({c['market']['date'] for c in cases.values()});dev_days=days[:4]
    dev_keys={k for k,c in cases.items() if c['market']['date'] in dev_days}
    selection_as_of=max(r['settled_at'] for r in joined if r['key'] in dev_keys)
    eval_days=[d for d in days[4:] if all(c['decision_at']>selection_as_of for c in cases.values() if c['market']['date']==d)]
    eval_keys={k for k,c in cases.items() if c['market']['date'] in eval_days}
    if not eval_keys:
        raise ValueError('No evaluation dates after development settlements; collect more data')
    baseline={r['key']:r['probability'] for r in joined if r['arm']=='statistical_baseline' and 'error' not in r}
    if set(baseline)!=set(cases):
        raise ValueError('Missing cheap baseline needed for causal pre-call gating')
    def overhead(keys):
        start=min(cases[k]['decision_at'] for k in keys)
        end=max(r['settled_at'] for r in joined if r['key'] in keys)
        return 200*(end-start)/86400/30
    dev_overhead,eval_overhead=overhead(dev_keys),overhead(eval_keys)
    # Complete development and freeze winner before evaluating any candidate on
    # later returns. Label records exist in memory, but are not passed to selection.
    results=[]
    for v in plan['candidates']:
        rows=[r for r in joined if r['arm']==v['arm'] and r['key'] in dev_keys]
        results.append({'variant':v,'development':period_result(rows,v,baseline,dev_overhead)})
    chosen=select_on_development(results)
    selection={'candidate_id':chosen,'selection_as_of':selection_as_of,'plan_hash':digest(plan),
               'development_hash':digest(results),'development_dates':dev_days,'evaluation_dates':eval_days}
    write_json(out/'selection.json',selection)
    for r in results:
        v=r['variant'];rows=[x for x in joined if x['arm']==v['arm'] and x['key'] in eval_keys]
        r['evaluation']=period_result(rows,v,baseline,eval_overhead)
    report={'status':'complete','created_at':time.time(),'plan':plan,'selection':selection,
            'preparation_hash':digest(prep),'committed_predictions_hash':digest(joined),
            'development_cases':len(dev_keys),'evaluation_cases':len(eval_keys),
            'embargo_dates':[d for d in days if d not in dev_days+eval_days],
            'development_overhead_per_arm':dev_overhead,'evaluation_overhead_per_arm':eval_overhead,
            'variants':results,'profitability_established':False,'fills_verified':False,
            'execution':'Hypothetical full fills at delayed display price plus stress; quantities unavailable.',
            'cost_accounting':'Call costs include recorded errors and uncertain reservations for consulted cases. Skipped costs are hypothetical future savings; original spend is unchanged.',
            'scope':'New policy experiment on existing forecast probabilities. No performance evidence for external model, new RAG cards or partial ladders.'}
    write_json(out/'report.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();r=run(args.prepared,args.out)
    print(json.dumps({k:r[k] for k in ('status','selection','development_cases','evaluation_cases','embargo_dates')},indent=2))


if __name__=='__main__':main()
