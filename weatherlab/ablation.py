"""Matched offline replays of frozen hypothesis configurations, one run at a time."""
import copy
import json
from pathlib import Path
from .core import digest
from .engine import replay, validate_config
from .hypotheses import HYPOTHESES
from .protocol import VERSION, LATEST_VERSION


def run(config, dataset, out, cloud=False, rag=None, budget_path=None):
    if config['strategy']=='wallet_control':
        raise ValueError('Weather hypothesis ablations apply to LLM strategies, not the deterministic control')
    validate_config(config)
    root=Path(out)
    root.mkdir(parents=True,exist_ok=False)
    variants=[('v1_baseline',VERSION,None),('v2_evidence_only',LATEST_VERSION,[]),
              ('v2_all',LATEST_VERSION,list(HYPOTHESES))]
    variants += [('without_'+name,LATEST_VERSION,[h for h in HYPOTHESES if h!=name]) for name in HYPOTHESES]
    plan={'dataset_hash':digest(dataset),'strategy':config['strategy'],'cloud':cloud,
          'variants':[{'name':n,'protocol':v,'hypotheses':h} for n,v,h in variants],
          'limitations':'Unvalidated hypotheses. Test-model results do not measure LLM performance. Correlated station-days and selection/multiple-testing effects require separate evaluation.'}
    (root/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    results=[]
    for name,version,flags in variants:
        c=copy.deepcopy(config)
        c['research_protocol']=version
        c.pop('weather_hypotheses',None)
        if flags is not None: c['weather_hypotheses']=flags
        try:
            r=replay(c,dataset,root/name,cloud=cloud,rag=rag,budget_path=budget_path)
            result={k:r.get(k) for k in ('status','error','synthetic','inference','fills','model_cost','net_after_costs','mean_brier','independent_station_days','validated_model_calls')}
            del r
        except Exception as exc:
            result={'status':'failed','error':type(exc).__name__+': '+str(exc)[:200]}
        results.append(dict(result,variant=name))
        (root/'comparison.json').write_text(json.dumps({'plan':plan,'results':results,'profitability_established':False},indent=2),encoding='utf-8')
        if result['status']=='failed':
            break
    return {'out':str(root),'variants_completed':len(results),'results':results,'profitability_established':False}
