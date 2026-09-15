"""Matched-contract score differences, clustered by calendar date.

Exploratory bootstrap intervals are descriptive, not automatic hypothesis tests.
"""
import argparse
import json
import random
from pathlib import Path


def compare(a, b, draws=2000, seed=20260915, allow_synthetic=False):
    if not allow_synthetic and (a['synthetic'] or b['synthetic'] or a['inference'] != 'cloud' or b['inference'] != 'cloud'):
        raise ValueError('Paper evaluation requires actual model runs on nonsynthetic data')
    if a['dataset_hash'] != b['dataset_hash']:
        raise ValueError('Cannot compare different input datasets as paired experiments')
    left={s['slug']:s for s in a['forecast_scores']};right={s['slug']:s for s in b['forecast_scores']}
    shared=sorted(set(left)&set(right))
    groups={}
    for slug in shared:
        x,y=left[slug],right[slug]
        if x['y'] != y['y'] or x['station_day'] != y['station_day']:
            raise ValueError('Outcome/identity mismatch')
        day=x['station_day'].split('/')[-1]
        groups.setdefault(day,[]).append(x['brier']-y['brier'])
    values=[sum(v)/len(v) for v in groups.values()]
    result={'left':a['strategy'],'right':b['strategy'],'matched_contracts':len(shared),'calendar_date_clusters':len(values),
            'unmatched_left':len(set(left)-set(right)),'unmatched_right':len(set(right)-set(left)),
            'mean_brier_difference':sum(values)/len(values) if values else None,
            'interpretation':'Negative favors left. Date clusters weight equally; missing forecasts are explicitly excluded, not scored as correct.',
            'bootstrap_95_interval':None,'seed':seed,'draws':draws}
    if len(values)>=10:
        rng=random.Random(seed)
        samples=sorted(sum(rng.choice(values) for _ in values)/len(values) for _ in range(draws))
        result['bootstrap_95_interval']=[samples[int(.025*draws)],samples[min(draws-1,int(.975*draws))]]
    else:
        result['warning']='Fewer than ten date clusters: no interval reported. Collect more prospective evidence.'
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('left');p.add_argument('right');p.add_argument('--out',required=True);p.add_argument('--allow-synthetic',action='store_true')
    args=p.parse_args()
    result=compare(json.loads(Path(args.left).read_text()),json.loads(Path(args.right).read_text()),allow_synthetic=args.allow_synthetic)
    target=Path(args.out)
    with target.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
