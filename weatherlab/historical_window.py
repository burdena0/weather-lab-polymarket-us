"""Bounded IEM archive download for a frozen, weather-only recent-day benchmark."""
import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .core import number
from .historical import bounded_json
from .sources import NoRedirect

# CLI reports use local standard time. This is an explicit weather benchmark,
# not an assertion that any historical venue contract used these same intervals.
STATIONS={'KLAX':(8,'CLILAX','LOS ANGELES'), 'KSFO':(8,'CLISFO','SAN FRANCISCO'),
          'KNYC':(5,'CLINYC','CENTRAL PARK'), 'KMIA':(5,'CLIMIA','MIAMI'),
          'KMDW':(6,'CLIMDW','CHICAGO-MIDWAY')}


def verify_cli(raw, station, day, expected):
    _,product,name=STATIONS[station]
    normalized=' '.join(raw.upper().split())
    if product not in raw or name not in normalized:
        raise ValueError('CLI station/product mismatch')
    label=f"{day.strftime('%B').upper()} {day.day} {day.year}"
    if not re.search(r'CLIMATE SUMMARY FOR '+re.escape(label)+r'\b',normalized):
        raise ValueError('CLI target date mismatch or partial-day report')
    section=raw.split('TEMPERATURE (F)',1)
    if len(section)!=2:raise ValueError('CLI Fahrenheit section absent')
    match=re.search(r'^\s*MAXIMUM\s+(-?\d+)R?(?=\s)',section[1],re.M)
    if not match or int(match[1]) != expected:
        raise ValueError('CLI observed maximum differs from parsed table')
    return {'product':product,'observed_maximum_f':int(match[1]),'date':day.date().isoformat(),
            'validation':'Raw CLI station name, product, date and observed Fahrenheit MAXIMUM matched'}


def build_window(root, station, start, end):
    if station not in STATIONS:raise ValueError('Unsupported station')
    first=datetime.strptime(start,'%Y-%m-%d').replace(tzinfo=timezone.utc)
    last=datetime.strptime(end,'%Y-%m-%d').replace(tzinfo=timezone.utc)
    if not 1 <= (last-first).days+1 <= 31 or last.date()>=datetime.now(timezone.utc).date():
        raise ValueError('Require 1-31 completed test dates')
    begin_train=first-timedelta(days=31)
    root=Path(root);root.mkdir(parents=True,exist_ok=False);receipts=root/'receipts';receipts.mkdir()
    protocol={'station':station,'training_start':begin_train.date().isoformat(),'training_end':(first-timedelta(days=1)).date().isoformat(),
              'test_start':start,'test_end':end,'expected_test_days':(last-first).days+1,'threshold_f':80,
              'availability_verified':False,'historical_book_data':False,'created_at':time.time(),
              'purpose':'Exploratory forecast accuracy; no trades or strategy profitability',
              'availability_policy':'Prior-day 12Z GFS MOS plus assumed six-hour dissemination lag; actual downloads timestamped now'}
    (root/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    training=[];cases=[];labels=[];errors=[];outcomes={};downloads={}
    for year in range(begin_train.year,last.year+1):
        receipt=bounded_json(f'https://mesonet.agron.iastate.edu/json/cli.py?station={station}&year={year}',receipts,f'cli-{year}')
        for row in receipt['data']['results']:
            if row['station']==station and begin_train.date().isoformat()<=row['valid']<=end:
                if row['valid'] in outcomes:raise ValueError('Duplicate CLI date')
                outcomes[row['valid']]=row;downloads[row['valid']]=receipt['downloaded_at']
    for index in range((last-begin_train).days+1):
        day=begin_train+timedelta(days=index);date=day.date().isoformat()
        try:
            runtime=day-timedelta(hours=12);available=(runtime+timedelta(hours=6)).timestamp()
            url='https://mesonet.agron.iastate.edu/api/1/mos.json?'+urllib.parse.urlencode({'station':station,'model':'GFS','runtime':runtime.strftime('%Y-%m-%dT%H:%M:%SZ')})
            receipt=bounded_json(url,receipts,'mos-'+date)
            begin=day+timedelta(hours=STATIONS[station][0]);finish=begin+timedelta(days=1)
            values=[]
            for r in receipt['data']['data']:
                if r['station']!=station or r['model']!='GFS' or datetime.strptime(r['runtime'],'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)!=runtime:
                    raise ValueError('MOS identity mismatch')
                at=datetime.strptime(r['ftime'],'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
                if begin<=at<finish:values.append((at,number(r['tmp'])))
            values.sort()
            if len(values)!=8 or any(b[0]-a[0]!=timedelta(hours=3) for a,b in zip(values,values[1:])):
                raise ValueError('Incomplete MOS three-hour sample coverage')
            high=max(t for _,t in values)
            actual=outcomes[date];observed=number(actual['high'])
            if not -150<=min(high,observed)<=max(high,observed)<=160:raise ValueError('Invalid temperature')
            published=datetime.strptime(actual['product'][:12],'%Y%m%d%H%M').replace(tzinfo=timezone.utc).timestamp()
            if published<finish.timestamp():raise ValueError('CLI predates weather-day end')
            cli_url='https://mesonet.agron.iastate.edu'+actual['link']
            parsed=urllib.parse.urlparse(cli_url)
            if parsed.hostname!='mesonet.agron.iastate.edu' or not parsed.path.startswith('/api/1/nwstext/'):
                raise ValueError('Unexpected CLI URL')
            with urllib.request.build_opener(NoRedirect()).open(cli_url,timeout=10) as response:raw=response.read(100001)
            if len(raw)>100000:raise ValueError('CLI text too large')
            received=time.time();text=raw.decode('utf-8');review=verify_cli(text,station,day,observed)
            (receipts/('cli-'+date+'.json')).write_text(json.dumps({'url':cli_url,'downloaded_at':received,
                'sha256':hashlib.sha256(raw).hexdigest(),'text':text,'review':review}),encoding='utf-8')
            case={'case_id':date,'station':station,'date':date,'forecast_high_f':high,'forecast_runtime':runtime.timestamp(),
                  'decision_at':available,'forecast_available_at':available,'availability_verified':False,
                  'availability_policy':protocol['availability_policy'],'forecast_product':'GFS MOS three-hour sampled maximum over CLI local-standard day; not live NWS grid forecast',
                  'day_start':begin.timestamp(),'day_end':finish.timestamp(),'forecast_evidence_id':'mos-'+receipt['sha256'][:24],
                  'source_url':url,'downloaded_at':receipt['downloaded_at']}
            label={'case_id':date,'actual_high_f':observed,'outcome_published_at':published,'source_url':cli_url,
                   'product_id':actual['product'],'downloaded_at':received,'label_source':'IEM NWS CLI archive; raw text maximum/station/date cross-checked',
                   'raw_cli_hash':hashlib.sha256(raw).hexdigest(),'label_review':review}
            if day<first:training.append({**case,**label})
            else:cases.append(case);labels.append(label)
        except Exception as exc:errors.append({'station':station,'date':date,'reason':type(exc).__name__+': '+str(exc)[:180]})
    for name,rows in [('training.jsonl',training),('cases.jsonl',cases),('labels.jsonl',labels)]:
        (root/name).write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    report={**protocol,'training_days':len(training),'test_days':len(cases),'errors':errors,
            'files':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('training.jsonl','cases.jsonl','labels.jsonl')}}
    (root/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('out','station','start','end'):p.add_argument('--'+field,required=True)
    args=p.parse_args();print(json.dumps(build_window(args.out,args.station,args.start,args.end),indent=2))


if __name__=='__main__':main()
