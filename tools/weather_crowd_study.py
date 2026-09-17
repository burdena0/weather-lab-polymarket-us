"""Public, resumable weather-market study; no credentials or trading calls."""
from __future__ import annotations
import argparse, concurrent.futures as cf, datetime as dt, gzip, hashlib, json
import math, pathlib, re, threading, time, urllib.request, urllib.parse, urllib.error

UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
START = dt.datetime(2025, 9, 16, tzinfo=UTC)
END = dt.datetime(2026, 9, 16, tzinfo=UTC)
BASE = ROOT / 'data/crowd-study-20250916-20260915'
LOCK = threading.Lock()
NEXT = 0.0

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Redirect refused', headers, fp)

def gzip_save(path, data):
    tmp=path.with_name(path.name+'.part-'+str(threading.get_ident()))
    with gzip.open(tmp,'wt',encoding='utf-8') as f:json.dump(data,f)
    for retry in range(8):
        try:tmp.replace(path);return
        except PermissionError:
            if retry==7:raise
            time.sleep(.15*(retry+1))

def stamp(s):
    s = str(s).replace('Z', '+00:00')
    s = re.sub(r'([+-]\d\d)$', r'\1:00', s)
    s = re.sub(r'(\.\d{6})\d+', r'\1', s)
    try: return dt.datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError): return None

def unpack(x):
    return json.loads(x) if isinstance(x, str) else x

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=True, indent=2), encoding='utf-8')

def request(url, payload=None):
    global NEXT
    host = urllib.parse.urlparse(url).hostname
    assert host in {'gamma-api.polymarket.com', 'clob.polymarket.com', 'gateway.polymarket.us'}
    assert payload is None or url == 'https://clob.polymarket.com/batch-prices-history'
    body = None if payload is None else json.dumps(payload, sort_keys=True).encode()
    key = hashlib.sha256(url.encode() + (body or b'')).hexdigest()
    path = BASE / 'receipts' / (key + '.json.gz')
    if path.exists():
        with gzip.open(path, 'rt', encoding='utf-8') as f: return json.load(f)['data']
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        with LOCK:
            delay = max(0, NEXT - time.monotonic())
            NEXT = max(NEXT, time.monotonic()) + 0.07
        time.sleep(delay)
        try:
            req = urllib.request.Request(url, data=body, headers={
                'User-Agent':'WeatherLab/1.0 public research', 'Accept':'application/json',
                'Content-Type':'application/json'})
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=25) as r:
                raw = r.read(16_000_001)
            if len(raw) > 16_000_000: raise ValueError('Response exceeds 16 MB cap')
            data = json.loads(raw)
            record = dict(url=url, request=payload, received_at=time.time(),
                          sha256=hashlib.sha256(raw).hexdigest(), data=data)
            gzip_save(path,record)
            return data
        except urllib.error.HTTPError as ex:
            if ex.code not in (429, 500, 502, 503, 504) or attempt == 3: raise
            time.sleep(min(15, float(ex.headers.get('Retry-After', 2 ** attempt))))
        except (TimeoutError, urllib.error.URLError):
            if attempt == 3: raise
            time.sleep(2 ** attempt)

def get(host, path, params):
    return request('https://' + host + path + '?' + urllib.parse.urlencode(params))

def inventory():
    events = {}; coverage = {}
    for platform in ('international', 'us'):
        seen = set(); pages = 0; raw_count = 0; cursor = None
        for offset in range(0, 100000, 100):
            if platform == 'international':
                params = dict(tag_id=84,
                    closed='true', limit=100, order='id', ascending='true',
                    end_date_min=(START-dt.timedelta(days=1)).isoformat(),
                    end_date_max=(END+dt.timedelta(days=2)).isoformat())
                if cursor: params['after_cursor']=cursor
                body = get('gamma-api.polymarket.com', '/events/keyset', params)
                data = body['events']; cursor=body.get('next_cursor')
            else:
                body = get('gateway.polymarket.us', '/v1/markets', dict(categories='climate',
                    closed='true', limit=100, offset=offset,
                    endDateMin=(START-dt.timedelta(days=1)).isoformat(),
                    endDateMax=(END+dt.timedelta(days=2)).isoformat()))
                data = body['markets']
            if not isinstance(data, list): raise ValueError('Unexpected inventory schema')
            if data and all(str(e['id']) in seen for e in data):
                raise ValueError('Repeated inventory page; refusing to claim complete coverage')
            pages += 1; raw_count += len(data)
            for e in data:
                seen.add(str(e['id']))
                title = e.get('title', '') if platform == 'international' else e.get('question', '')
                match = re.match(r'Highest temperature in (.+?) on (.+?)\?$', title, re.I)
                if not match: continue
                city, date_text = match.groups()
                try:
                    day = dt.datetime.strptime(date_text, '%B %d, %Y').replace(tzinfo=UTC)
                except ValueError:
                    # International titles usually omit the year; take it from the event end date.
                    end = stamp(e.get('endDate'))
                    if end is None: continue
                    try: day = dt.datetime.strptime(date_text + ', ' + str(dt.datetime.fromtimestamp(end, UTC).year), '%B %d, %Y').replace(tzinfo=UTC)
                    except ValueError: continue
                if not START <= day < END: continue
                eid = platform + ':' + (str(e['id']) if platform == 'international' else city + ':' + day.date().isoformat())
                event = events.setdefault(eid, dict(id=eid, platform=platform, city=city,
                    day=day.date().isoformat(), title=title, slug=e.get('slug'), markets=[]))
                for m in e.get('markets', []) if platform == 'international' else [e]:
                    row = dict(id=str(m['id']), slug=m.get('slug'), label=m.get('groupItemTitle') or m.get('title') or m.get('question'),
                               start=stamp(m.get('startDate')), end=stamp(m.get('endDate')),
                               closed_at=stamp(m.get('closedTime')), resolved=False, winner=None)
                    if platform == 'international':
                        outcomes=unpack(m.get('outcomes','[]')); prices=unpack(m.get('outcomePrices','[]')); tokens=unpack(m.get('clobTokenIds','[]'))
                        valid = m.get('conditionId') and 'Yes' in outcomes and len(tokens)==len(outcomes)==len(prices)
                        if valid:
                            i=outcomes.index('Yes'); row['token']=tokens[i]; row['condition_id']=m['conditionId']
                            p=float(prices[i]); row['winner']=int(p) if p in (0.,1.) else None
                            row['resolved']=bool(m.get('closed') and m.get('umaResolutionStatus')=='resolved' and row['winner'] is not None)
                        else: row['invalid']='missing condition ID / YES token mapping'
                    else:
                        row['status']=m.get('status'); row['sides']=m.get('marketSides',[])
                    event['markets'].append(row)
            if pages % 10 == 0: print(platform, 'pages', pages, 'raw', raw_count, 'temperature events',sum(e['platform']==platform for e in events.values()), flush=True)
            if len(data)<100 or (platform=='international' and not cursor): break
        else: raise ValueError('Inventory page cap reached')
        coverage[platform]=dict(pages=pages, raw_records=raw_count, pagination_exhausted=True)
        save(BASE/'inventory.json', dict(window=[START.isoformat(),END.isoformat()],coverage=coverage,events=list(events.values())))
        print(platform, coverage[platform], flush=True)

def histories(platform_filter=None):
    inv=json.loads((BASE/'inventory.json').read_text()); events=inv['events']; tasks=[]
    if platform_filter:events=[e for e in events if e['platform']==platform_filter]
    progress=BASE/('collection-progress'+('-'+platform_filter if platform_filter else '')+'.json')
    international=sorted([m for e in events if e['platform']=='international' for m in e['markets'] if 'token' in m],key=lambda m:m['end'] or m['closed_at'] or m['start'] or 0)
    for i in range(0,len(international),20): tasks.append(('international',international[i:i+20]))
    for e in events:
        if e['platform']=='us': tasks.extend(('us',[m]) for m in e['markets'])
    directory=BASE/'histories-v2'; directory.mkdir(exist_ok=True)
    def job(task):
        platform, markets=task
        pending=[m for m in markets if not (directory/(platform+'-'+m['id']+'.json.gz')).exists()]
        if not pending: return 0
        if platform=='international':
            begin=min(m['start'] or ((m['end'] or START.timestamp())-7*86400) for m in pending)-86400
            finish=max(m['closed_at'] or m['end'] or END.timestamp() for m in pending)+86400
            merged={m['token']:{} for m in pending}
            if finish-begin>60*86400: raise ValueError('Market lifetime exceeds 60-day retrieval bound')
            for left in range(int(begin),int(finish),7*86400):
                result=request('https://clob.polymarket.com/batch-prices-history',dict(markets=[m['token'] for m in pending],start_ts=left,end_ts=min(left+7*86400,int(finish)),fidelity=30))
                for token,points in result['history'].items():
                    for point in points: merged[token][point['t']]=point
            for m in pending:
                points=sorted(merged[m['token']].values(),key=lambda p:p['t'])
                gzip_save(directory/(platform+'-'+m['id']+'.json.gz'),dict(history=points))
        else:
            m=pending[0]
            points={}
            begin=int(m['start']); finish=int(m['end'])
            if not 0 < finish-begin <= 7*86400: raise ValueError('Unexpected US market lifetime')
            for start in range(begin,finish,86400):
                result=get('gateway.polymarket.us','/v1/price-history',{'symbol':m['slug'],
                    'timestamp.startTimestamp':start,'timestamp.endTimestamp':min(start+86400,finish),'fidelity':1})
                for point in result.get('history',[]): points[point['timestamp']]=point
            book=request('https://gateway.polymarket.us/v1/markets/'+urllib.parse.quote(m['slug'],safe='')+'/book')
            gzip_save(directory/(platform+'-'+m['id']+'.json.gz'),dict(history=sorted(points.values(),key=lambda p:p['timestamp']),book=book))
        return len(pending)
    errors=[];done=0
    with cf.ThreadPoolExecutor(max_workers=32) as pool:
        for task,result in zip(tasks,pool.map(lambda t: safe(job,t),tasks)):
            done+=1
            if isinstance(result,str): errors.append(dict(platform=task[0],markets=[m['id'] for m in task[1]],error=result))
            if done%100==0: print('history tasks',done,'/',len(tasks),'errors',len(errors),flush=True);save(progress,dict(done=done,total=len(tasks),errors=errors))
    save(progress,dict(done=done,total=len(tasks),errors=errors,finished_at=time.time()))
    print('History collection done',len(tasks),'tasks,',len(errors),'errors',flush=True)

def safe(fn,arg):
    try:return fn(arg)
    except Exception as ex:return type(ex).__name__+': '+str(ex)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['inventory','histories']);p.add_argument('--platform',choices=['international','us']);a=p.parse_args()
    inventory() if a.phase=='inventory' else histories(a.platform)
