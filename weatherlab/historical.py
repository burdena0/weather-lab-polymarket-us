"""Monthly weather-only benchmark. No invented historical orders, prices, or returns."""
import argparse
import calendar
import hashlib
import json
import math
import time
import tracemalloc
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .core import digest, number, stamp
from .models import CloudModel, load_env, PERSONAS
from .strategies import forecast
from .sources import NoRedirect


def bounded_json(url, receipts, name):
    if urllib.parse.urlparse(url).hostname!='mesonet.agron.iastate.edu':raise ValueError('Historical host not allowed')
    with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(url,headers={'User-Agent':'WeatherLab research github.com/burdena0/weather-lab-polymarket-us'}),timeout=10) as response:
        raw=response.read(4000001)
    if len(raw)>4000000:raise ValueError('Historical response exceeds 4 MB')
    receipt={'url':url,'downloaded_at':time.time(),'sha256':hashlib.sha256(raw).hexdigest(),'data':json.loads(raw)}
    (receipts/(name+'.json')).write_text(json.dumps(receipt),encoding='utf-8')
    return receipt


def build_month(root, month='2026-08'):
    first=datetime.strptime(month+'-01','%Y-%m-%d').replace(tzinfo=timezone.utc)
    if first.year!=2026 or first.month!=8:raise ValueError('This predeclared corpus is KLAX July/August 2026; add other protocols explicitly')
    root=Path(root);root.mkdir(parents=True,exist_ok=False);receipts=root/'receipts';receipts.mkdir()
    cli=bounded_json('https://mesonet.agron.iastate.edu/json/cli.py?station=KLAX&year=2026',receipts,'cli-2026')
    outcomes={}
    for r in cli['data']['results']:
        if r['station']=='KLAX' and r['valid'][:7] in ('2026-07','2026-08'):
            if r['valid'] in outcomes:raise ValueError('Duplicate CLI date; review revisions')
            outcomes[r['valid']]=r
    train=[];cases=[];labels=[];errors=[]
    start=first.replace(month=7)
    for index in range(62):
        day=start+timedelta(days=index);date=day.date().isoformat()
        try:
            # Frozen pre-day 12Z cycle, not hindsight selection of the best model run.
            runtime=day-timedelta(hours=12)
            url='https://mesonet.agron.iastate.edu/api/1/mos.json?'+urllib.parse.urlencode({'station':'KLAX','model':'GFS','runtime':runtime.strftime('%Y-%m-%dT%H:%M:%SZ')})
            receipt=bounded_json(url,receipts,'mos-'+date)
            rows=receipt['data']['data']
            begin=day+timedelta(hours=8);end=begin+timedelta(days=1)
            selected=[]
            for row in rows:
                if row['station']!='KLAX' or datetime.strptime(row['runtime'],'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)!=runtime:
                    raise ValueError('MOS station/runtime mismatch')
                valid=datetime.strptime(row['ftime'],'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
                if begin<=valid<end:selected.append((valid,number(row['tmp'])))
            if len(selected)!=8 or len({x[0] for x in selected})!=8 or any(b[0]-a[0]!=timedelta(hours=3) for a,b in zip(sorted(selected),sorted(selected)[1:])):
                raise ValueError('Incomplete 3-hour MOS forecast samples')
            high=max(t for _,t in selected)
            if not -150<=high<=160:raise ValueError('Invalid MOS temperature')
            actual=outcomes[date];value=number(actual['high'])
            published=datetime.strptime(actual['product'][:12],'%Y%m%d%H%M').replace(tzinfo=timezone.utc).timestamp()
            if published<end.timestamp():raise ValueError('CLI product predates end of target day')
            row={'case_id':date,'station':'KLAX','date':date,'forecast_high_f':high,'forecast_runtime':runtime.timestamp(),
                 'decision_at':(runtime+timedelta(hours=6)).timestamp(),'forecast_available_at':(runtime+timedelta(hours=6)).timestamp(),
                 'availability_verified':False,'availability_policy':'Assumed six-hour MOS dissemination delay; first-seen receipt unavailable',
                 'forecast_product':'GFS MOS 3-hour temperature sample maximum over 08Z-08Z; not NWS hourly grid or true forecast maximum',
                 'day_start':begin.timestamp(),'day_end':end.timestamp(),'forecast_evidence_id':'mos-'+receipt['sha256'][:24],
                 'source_url':url,'downloaded_at':receipt['downloaded_at']}
            label={'case_id':date,'actual_high_f':value,'outcome_published_at':published,
                   'source_url':'https://mesonet.agron.iastate.edu'+actual['link'],'product_id':actual['product'],
                   'downloaded_at':cli['downloaded_at'],'label_source':'IEM parsed NWS CLI; raw product review still required'}
            if day<first:train.append({**row,**label})
            else:cases.append(row);labels.append(label)
        except Exception as exc:errors.append({'date':date,'reason':type(exc).__name__+': '+str(exc)[:180]})
    for name,rows in [('training.jsonl',train),('cases.jsonl',cases),('labels.jsonl',labels)]:
        (root/name).write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    report={'station':'KLAX','test_month':month,'training_month':'2026-07','training_days':len(train),'test_days':len(cases),
            'expected_test_days':31,'errors':errors,'historical_book_data':False,'availability_verified':False,
            'purpose':'Weather forecast benchmark only; no Polymarket strategy P&L claim',
            'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('training.jsonl','cases.jsonl','labels.jsonl')}}
    (root/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def read_rows(path, max_rows=1000):
    with Path(path).open(encoding='utf-8') as f:
        count=0
        while True:
            line=f.readline(100001)
            if not line:break
            if len(line)>100000:raise ValueError('Historical row exceeds 100 KB')
            if line.strip():
                count+=1
                if count>max_rows:raise ValueError('Historical row count exceeds bound')
                yield json.loads(line)


def blind_context(case, training):
    """An allowlist constructs the model payload; labels and future cases never enter."""
    now=number(case['decision_at'])
    if not stamp(case['forecast_runtime'])<=stamp(case['forecast_available_at'])<=now<stamp(case['day_start']):
        raise ValueError('Forecast is not available before the decision and target day')
    history=[]
    for r in training:
        if r['station']==case['station'] and r['date']<case['date'] and stamp(r['outcome_published_at'])<=now and stamp(r['forecast_available_at'])<stamp(r['day_start']):
            history.append({'forecast_high_f':number(r['forecast_high_f']),'actual_high_f':number(r['actual_high_f']),
                            'evidence_id':'calibration-'+digest(r)[:20]})
    history=history[-31:]
    if len(history)<10:raise ValueError('Fewer than 10 strictly prior calibration days')
    high=number(case['forecast_high_f']);threshold=80
    p=(sum(high+r['actual_high_f']-r['forecast_high_f']>=threshold for r in history)+.5)/(len(history)+1)
    # Exact date, station name, URL, raw product text and target outcome are withheld.
    ctx={'as_of':'historical decision','contract':{'id':'blind-case','slug':'blind-case','station':'station-A','date':'held-out day',
         'lower_f':threshold,'upper_f':None,'source':'historical CLI benchmark','rules_hash':'weather-only'},
         'forecast':{'high_f':high,'revision_f':0,'evidence_id':case['forecast_evidence_id'],'product':case['forecast_product']},
         'history':history,'baseline_probability':p,'evidence_ids':[case['forecast_evidence_id']]+[r['evidence_id'] for r in history],
         'limitations':'Weather-only >=80F threshold. No historical contract price, trade or profit calculation. Date/station blinded; pretraining contamination remains possible.'}
    return ctx


def run_month(corpus, out, mode='baseline', allow_assumed=False):
    root=Path(corpus);out=Path(out)
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    for name,h in manifest['files'].items():
        if name not in ('training.jsonl','cases.jsonl','labels.jsonl') or hashlib.sha256((root/name).read_bytes()).hexdigest()!=h:
            raise ValueError('Historical corpus hash mismatch')
    if not allow_assumed and not manifest.get('availability_verified'):
        raise ValueError('Archive first-seen times unverified. Strict replay blocked; exploratory testing requires --allow-assumed-availability.')
    training=list(read_rows(root/'training.jsonl',31))
    if len(training)>31:raise ValueError('Calibration buffer exceeds predeclared month')
    if any(r['date'][:7]!=manifest.get('training_month','2026-07') for r in training):
        raise ValueError('Calibration contains a day outside the frozen training month')
    out.mkdir(parents=True,exist_ok=False)
    model=CloudModel(Path('data/model-budget.sqlite')) if mode=='cloud' else None
    if mode not in ('baseline','cloud'):raise ValueError('Unknown benchmark mode')
    totals={};cases=0;started=time.perf_counter();own_trace=not tracemalloc.is_tracing()
    if own_trace:tracemalloc.start()
    previous='';tip='0'*64
    try:
        # Predictions written and closed before the scorer opens test labels.
        with (out/'predictions.jsonl').open('x',encoding='utf-8') as predictions, (out/'inputs.jsonl').open('x',encoding='utf-8') as inputs:
            for case in read_rows(root/'cases.jsonl',31):
                if not allow_assumed and (case.get('availability_verified') is not True or any(r.get('availability_verified') is not True for r in training)):
                    raise ValueError('Per-record first-seen availability is unverified')
                if case['date'][:7]!=manifest['test_month'] or case['date']<=previous or cases>=31:raise ValueError('Invalid test chronology or month size')
                previous=case['date'];cases+=1;ctx=blind_context(case,training)
                inputs.write(json.dumps({'case_id':case['case_id'],'payload':ctx})+'\n')
                arms=['statistical_baseline'] if model is None else ['fixed_llm','adaptive_llm','polyswarm_weather_ablation']
                for arm in arms:
                    try:
                        if model is None:p=ctx['baseline_probability'];calls=[]
                        elif arm=='polyswarm_weather_ablation':
                            # No invented market prior: standalone weather-persona ablation.
                            votes=[model.predict(ctx,'medium','medium',persona)[0] for persona in PERSONAS]
                            if any(v['abstain'] for v in votes):raise ValueError('Persona abstained')
                            p=sum(v['probability_yes'] for v in votes)/len(votes);calls=list(model.calls)
                        else:
                            prediction,_=forecast(arm,ctx,model,None)
                            if prediction['abstain']:raise ValueError('Model abstained')
                            p=prediction['probability_yes'];calls=list(model.calls)
                        record={'case_id':case['case_id'],'arm':arm,'probability':p,'threshold_f':ctx['contract']['lower_f'],
                                'context_hash':digest(ctx),'calls':calls}
                    except Exception as exc:record={'case_id':case['case_id'],'arm':arm,'error':str(exc)[:180]}
                    tip=digest({'previous':tip,'record':record});record['chain_hash']=tip
                    predictions.write(json.dumps(record)+'\n');predictions.flush()
                    if model:model.calls.clear() # Each response is already persisted; no growing in-memory call history.
        labels={r['case_id']:r for r in read_rows(root/'labels.jsonl',31)}
        if len(labels)>31:raise ValueError('Too many scoring labels')
        with (out/'scores.jsonl').open('x',encoding='utf-8') as scores:
            for r in read_rows(out/'predictions.jsonl'):
                t=totals.setdefault(r['arm'],{'scored':0,'skipped':0,'brier_sum':0.0,'yes_outcomes':0,'no_outcomes':0})
                if 'error' in r:t['skipped']+=1;continue
                label=labels[r['case_id']];y=int(number(label['actual_high_f'])>=r['threshold_f']);brier=(r['probability']-y)**2
                t['scored']+=1;t['brier_sum']+=brier
                t['yes_outcomes']+=y;t['no_outcomes']+=1-y
                scores.write(json.dumps({'case_id':r['case_id'],'arm':r['arm'],'y':y,'p':r['probability'],'brier':brier})+'\n')
        _,peak=tracemalloc.get_traced_memory()
        for t in totals.values():t['mean_brier']=t.pop('brier_sum')/t['scored'] if t['scored'] else None
        result={'mode':mode,'cases':cases,'seconds':time.perf_counter()-started,'python_peak_bytes':peak,'arms':totals,
                'forecast_product': 'GFS MOS 3-hour sample maximum; product differs from live NWS grid forecasts',
                'corpus_hash':digest(manifest),'prediction_chain_tip':tip,'outcomes_read_after_predictions':True,
                'first_seen_availability_verified':manifest['availability_verified'],'pretraining_contamination_excluded':False,
                'historical_trades_simulated':False,'profitability_established':False,'threshold_f':80,
                'development_status':'Exploratory pilot: initial test-period aggregate diagnostics informed harness development. Use a fresh held-out period for confirmatory claims.',
                'controls':'Frozen July calibration; no August outcomes in model inputs; date/station redaction; stateless calls; no simulated-clock sleeps.',
                'limits':'Weather-only experiment. Wallet/arbitrage need historical signals/books. PolySwarm is a persona-only ablation without its market blend. Python peak excludes native runtime memory.'}
        (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
    finally:
        if own_trace:tracemalloc.stop()


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    build=sub.add_parser('download');build.add_argument('--out',required=True)
    run=sub.add_parser('run');run.add_argument('--corpus',required=True);run.add_argument('--out',required=True)
    run.add_argument('--mode',choices=('baseline','cloud'),default='baseline');run.add_argument('--allow-assumed-availability',action='store_true')
    args=p.parse_args();load_env(Path('.env'))
    result=build_month(args.out) if args.cmd=='download' else run_month(args.corpus,args.out,args.mode,args.allow_assumed_availability)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
