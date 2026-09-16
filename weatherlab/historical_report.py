"""Compare immutable weather runs on identical cases, with explicit coverage."""
import argparse
from collections import Counter
import json
import random
import time
from pathlib import Path
from .core import digest
from .historical import read_rows

STATIONS=('KLAX','KMDW','KMIA','KNYC','KSFO')
ARMS=('statistical_baseline','fixed_llm','adaptive_llm','polyswarm_weather_ablation')
NAMES=('Statistical baseline','Fixed LLM','Adaptive LLM','PolySwarm weather only')


def summarize(root, prefix, suffix=''):
    root=Path(root); scores={a:{} for a in ARMS}; errors={a:Counter() for a in ARMS}
    completed=[]; calls=[]; accounted=0; sources=[]; station_results={}
    for station in STATIONS:
        for folder in (root/('baseline-'+station),root/(prefix+station+suffix)):
            summary_path=folder/'summary.json'
            if not summary_path.exists():continue
            summary=json.loads(summary_path.read_text())
            if summary['mode']=='cloud':
                completed.append(station);accounted+=summary['model_cost_or_reserved_usd']
                station_results[station]=summary['arms']
            previous='0'*64
            for prediction in read_rows(folder/'predictions.jsonl'):
                record=dict(prediction);tip=record.pop('chain_hash')
                if digest({'previous':previous,'record':record})!=tip:raise ValueError('Prediction chain mismatch')
                previous=tip
                if record.get('error'):errors[record['arm']][record['error']]+=1
                calls.extend(record['calls'])
            if previous!=summary['prediction_chain_tip']:raise ValueError('Summary chain tip mismatch')
            for row in read_rows(folder/'scores.jsonl'):
                key=(station,row['case_id']);arm=row['arm']
                if key in scores[arm]:raise ValueError('Duplicate scored station-day')
                if abs(row['brier']-(row['p']-row['y'])**2)>1e-12:raise ValueError('Score calculation mismatch')
                scores[arm][key]=row
            sources.append({'path':str(folder),'corpus_hash':summary['corpus_hash'],'prediction_chain_tip':previous})
    paired=set.intersection(*(set(scores[a]) for a in ARMS))
    keys=sorted(paired); dates=sorted({day for _,day in keys})
    # Calendar-day blocks preserve same-day dependence across stations.
    rng=random.Random(20260916)
    resamples=[rng.choices(dates,k=len(dates)) for _ in range(2000)] if dates else []
    arms=[]
    for arm,name in zip(ARMS,NAMES):
        all_rows=list(scores[arm].values());rows=[scores[arm][k] for k in keys]
        mean=lambda xs:sum(xs)/len(xs) if xs else None
        boot=[]
        for draw in resamples:
            boot.append(mean([scores[arm][k]['brier'] for day in draw for k in keys if k[1]==day]))
        boot.sort()
        arms.append({'id':arm,'name':name,'scored':len(all_rows),'expected':50,'errors':dict(errors[arm]),
                     'mean_brier_all':mean([r['brier'] for r in all_rows]),'paired_brier':mean([r['brier'] for r in rows]),
                     'paired_correct':sum((r['p']>=.5)==bool(r['y']) for r in rows),
                     'paired_accuracy':mean([int((r['p']>=.5)==bool(r['y'])) for r in rows]),
                     'paired_interval':([boot[49],boot[1949]] if boot else None)})
    return {'created_at':time.time(),'period':'2026-09-06 through 2026-09-15','completed_stations':completed,
            'status':'complete' if len(completed)==5 else 'partial','expected_station_days':50,
            'paired_station_days':len(keys),'paired_calendar_days':len(dates),'paired_keys':[list(k) for k in keys],
            'arms':arms,'station_results':station_results,'validated_calls':len(calls),
            'models':dict(Counter(c['model'] for c in calls)),
            'token_priced_validated_usd':sum(c['cost'] for c in calls),'cost_or_reserved_usd':accounted,
            'sources':sources,'control_status':'Not evaluated: no historical depth or verified reference-wallet signals',
            'uncertainty':'Descriptive 95% calendar-day block bootstrap, 2000 draws, seed 20260916; at most 10 day blocks, not confirmatory inference.',
            'limits':'Weather accuracy only, fixed >=80 F threshold. Pairwise chart uses intersection across baseline and all three cloud arms. Abstentions/timeouts are excluded, so selection bias remains. Assumed archive availability. No trading returns or full PolySwarm market blend.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--prefix',required=True);p.add_argument('--suffix',default='');p.add_argument('--out',required=True)
    a=p.parse_args();result=summarize(a.root,a.prefix,a.suffix)
    with Path(a.out).open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
