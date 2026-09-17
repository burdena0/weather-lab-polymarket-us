"""Reproduce the reference video's descriptive study, with causal confirmation."""
from __future__ import annotations
import collections, csv, gzip, html, json, math, pathlib, sys, re
import datetime as dt
import concurrent.futures as cf
from weather_crowd_study import BASE, ROOT, START, END, stamp, save
sys.path.insert(0,str(ROOT/'data/tools/plotting'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages

OUT=BASE/'graphs'

def complete_partition(markets):
    intervals=[]
    for market in markets:
        label=(market.get('label') or '').replace('\u2212','-')
        label=re.sub(r'[\u00b0CF]', '', label).strip()
        match=re.fullmatch(r'(-?\d+)\s*(?:(?:to|[-\u2013\u2014])\s*(-?\d+))?\s*(or below|or higher|or above)?',label)
        if not match:return False
        first,last,tail=match.groups();first=int(first);last=int(last) if last is not None else first
        intervals.append((-math.inf,last) if tail=='or below' else (first,math.inf) if tail else (first,last))
    intervals.sort()
    return (len(intervals)>=2 and intervals[0][0]==-math.inf and intervals[-1][1]==math.inf
            and all(lo<=hi for lo,hi in intervals)
            and all(intervals[j][0]==intervals[j-1][1]+1 for j in range(1,len(intervals))))

def load_event(e):
    if not complete_partition(e['markets']):return None,'incomplete_or_unparsed_temperature_partition'
    arrays=[]; winners=[]; raw_count=0; duplicate_count=0; opening=[]
    for m in e['markets']:
        if e['platform']=='international' and (m.get('invalid') or not m.get('resolved')):
            return None,'unverified_resolution_or_placeholder'
        path=BASE/'histories-v2'/(e['platform']+'-'+m['id']+'.json.gz')
        if not path.exists(): return None,'missing_history'
        with gzip.open(path,'rt',encoding='utf-8') as f:d=json.load(f)
        if e['platform']=='international':
            winner=m['winner']; points=[(int(p['t']),float(p['p'])) for p in d['history']]
        else:
            try:
                book=d['book']['marketData'];stats=book['stats'];settlement=stats['settlementPx']
                winner=float(settlement['value']);at=stamp(stats['settlementSetTime'])
                assert book['marketSlug']==m['slug'] and settlement['currency']=='USD'
                assert book['state'] in ('MARKET_STATE_EXPIRED','MARKET_STATE_CLOSED','MARKET_STATE_TERMINATED')
                assert winner in (0,1) and at and at >= m['end']
            except (KeyError,AssertionError,TypeError,ValueError): return None,'unverified_resolution_or_placeholder'
            points=[(int(p['timestamp']),float(p['longPrice'])) for p in d['history']]
        if not points:return None,'empty_history'
        if any(not math.isfinite(p) or not 0<=p<=1 for _,p in points):return None,'invalid_price'
        raw_count+=len(points)
        unique=dict(points);duplicate_count+=len(points)-len(unique)
        points=sorted(unique.items())
        opening.append(float(points[0][1]))
        # A sample becomes usable only at the first grid endpoint AT OR AFTER its timestamp.
        buckets={}
        for t,p in points:
            grid=((t+1799)//1800)*1800
            buckets[grid]=(t,p)
        arrays.append((np.array([v[0] for v in buckets.values()],dtype=np.int64),np.array([v[1] for v in buckets.values()],dtype=float)))
        winners.append(int(winner))
    if len(arrays)<2 or sum(winners)!=1:return None,'not_exactly_one_winner'
    if len({m['id'] for m in e['markets']})!=len(arrays):return None,'duplicate_contract'
    first=max(a[0][0] for a in arrays);last=min(a[0][-1] for a in arrays)
    start=((first+1799)//1800)*1800
    if last<start:return None,'no_common_history'
    if last-start>60*86400:return None,'lifetime_over_60_days'
    grid=np.arange(start,last+1,1800,dtype=np.int64)
    matrix=[];ages=[]
    for t,p in arrays:
        ids=np.searchsorted(t,grid,side='right')-1
        assert np.all(ids>=0)
        matrix.append(p[ids]);ages.append(grid-t[ids])
    matrix=np.array(matrix).T;ages=np.array(ages).T;winning=np.array(winners)
    maximum=matrix.max(axis=1);prob_sum=matrix.sum(axis=1)
    # Never label a post-outcome/near-certain board as an early crowd signal.
    cutoff=np.where(maximum>=.95)[0];stop=int(cutoff[0]) if len(cutoff) else len(grid)
    valid=(prob_sum>=.9-1e-12)&(prob_sum<=1.1+1e-12);valid[stop:]=False
    def detect(mask):
        count=0
        for j,ok in enumerate(mask):
            count=count+1 if ok else 0
            if count==6:return j
        return None
    confirm=detect(valid);fresh=detect(valid & (ages.max(axis=1)<=3600))
    record=dict(id=e['id'],platform=e['platform'],city=e['city'],day=e['day'],title=e['title'],
                buckets=len(arrays),raw_points=raw_count,duplicate_timestamps=duplicate_count,
                opening_sum=sum(opening),opening_mean=float(np.mean(opening)),
                common_grid_points=len(grid),max_carry_minutes=float(ages.max()/60),
                converged=confirm is not None,fresh_converged=fresh is not None)
    def result(j):
        p=matrix[j];favorites=np.flatnonzero(p==p.max());hit=float(winning[favorites].mean())
        return dict(timestamp=int(grid[j]),prices=p.tolist(),winners=winners,
                    favorite_hit=hit,tied_favorites=len(favorites),favorite_price=float(p.max()),
                    random_hit=1/len(p),brier=float(np.mean((p-winning)**2)),
                    uniform_brier=float(np.mean((1/len(p)-winning)**2)),
                    normalized_brier=float(np.mean((p/p.sum()-winning)**2)),
                    price_sum=float(p.sum()),max_carry_minutes=float(ages[j].max()/60))
    if confirm is not None:
        record['confirmation']=result(confirm)
        record['retrospective_start']=result(confirm-5)
    if fresh is not None:record['fresh_confirmation']=result(fresh)
    return (record,dict(grid=grid,prices=matrix,prob_sum=prob_sum,confirm=confirm,stop=stop)),None

def stats(rows,method='confirmation'):
    chosen=[r for r in rows if method in r]
    if not chosen:return dict(n=0)
    values=[r[method] for r in chosen]
    prices=np.concatenate([v['prices'] for v in values]);wins=np.concatenate([v['winners'] for v in values])
    indices=np.minimum((prices*10).astype(int),9)
    cal=[]
    days=sorted({r['day'] for r in chosen});dayidx={d:i for i,d in enumerate(days)}
    counts=np.zeros((len(days),10));hits=counts.copy();totalp=counts.copy()
    favorite=np.zeros((len(days),2))
    for r in chosen:
        v=r[method];j=dayidx[r['day']];favorite[j]+=[v['favorite_hit'],1]
        for p,w in zip(v['prices'],v['winners']):
            b=min(int(p*10),9);counts[j,b]+=1;hits[j,b]+=w;totalp[j,b]+=p
    rng=np.random.default_rng(20260916);boot=[];favboot=[]
    for _ in range(500):
        sample=rng.integers(0,len(days),len(days));c=counts[sample].sum(axis=0);h=hits[sample].sum(axis=0)
        boot.append(np.divide(h,c,out=np.full(10,np.nan),where=c>0))
        f=favorite[sample].sum(axis=0);favboot.append(f[0]/f[1])
    boot=np.array(boot)
    for b in range(10):
        mask=indices==b;n=int(mask.sum())
        if n:
            interval=np.nanquantile(boot[:,b],[.025,.975])
            contributing_days=int(np.count_nonzero(counts[:,b]))
            cal.append(dict(bin=b,n=n,mean_price=float(prices[mask].mean()),win_rate=float(wins[mask].mean()),
                            weather_dates=contributing_days,
                            lower=float(interval[0]) if contributing_days>=10 else None,
                            upper=float(interval[1]) if contributing_days>=10 else None))
    return dict(n=len(chosen),buckets=len(prices),weather_dates=len(days),
                favorite_hit=float(np.mean([v['favorite_hit'] for v in values])),
                favorite_ci=np.quantile(favboot,[.025,.975]).tolist() if len(days)>=10 else None,
                random_hit=float(np.mean([v['random_hit'] for v in values])),
                bucket_brier=float(np.mean((prices-wins)**2)),
                event_mean_brier=float(np.mean([v['brier'] for v in values])),
                event_uniform_brier=float(np.mean([v['uniform_brier'] for v in values])),
                event_normalized_brier=float(np.mean([v['normalized_brier'] for v in values])),
                calibration=cal)

def graph(rows,summary,label,path,pdf=None):
    fig,axes=plt.subplots(2,3,figsize=(16,9.5),layout='constrained')
    fig.suptitle(label+' | Daily temperature crowd study',fontsize=19,fontweight='bold')
    ax=axes[0,0]
    ax.hist([r['opening_sum'] for r in rows],bins=40,color='#53788f',edgecolor='white')
    ax.axvline(1,color='#b34a43',linestyle='--');ax.set(title='Sum of first observed bucket prices',xlabel='Sum of YES prices (not simultaneous)',ylabel='Events')
    ax=axes[0,1];ax.scatter([r['buckets'] for r in rows],[r['opening_mean'] for r in rows],s=12,alpha=.18,color='#53788f',rasterized=True)
    if rows:
        x=np.linspace(max(2,min(r['buckets'] for r in rows)-.5),max(r['buckets'] for r in rows)+.5,100);ax.plot(x,1/x,color='#b34a43',label='1 / number of buckets');ax.legend()
        ax.set_xticks(sorted({r['buckets'] for r in rows}))
    ax.set(title='Opening prices versus number of buckets',xlabel='Buckets per event',ylabel='Mean first YES price')
    ax.set_ylim(0,1)
    ax=axes[0,2]
    stages=[len(rows),sum(r['converged'] for r in rows),sum(r['fresh_converged'] for r in rows)]
    ax.bar(['Clean\nwith history','Confirmed','Confirmed\nfresh <=1 h'],stages,color=['#929da6','#315973','#789a85'])
    for j,n in enumerate(stages):ax.text(j,n,str(n),ha='center',va='bottom')
    ax.set(title='Coverage through the method',ylabel='Events');ax.margins(y=.18)
    ax=axes[1,0]
    if summary['n']:
        vals=[summary['favorite_hit'],summary['random_hit']]
        ax.bar(['Favorite','Uniform random'],vals,color=['#315973','#a3adb5'])
        if summary['favorite_ci']:
            lo,hi=summary['favorite_ci'];ax.errorbar([0],[vals[0]],yerr=[[max(0,vals[0]-lo)],[max(0,hi-vals[0])]],fmt='none',color='black',capsize=5)
        for j,v in enumerate(vals):ax.text(j,v+.025,f'{v:.1%}',ha='center')
    ax.set(title='Winner accuracy at the sixth reading',ylabel='Fraction of events',ylim=(0,1))
    if not summary['n']:ax.text(.5,.5,'No eligible confirmed events',transform=ax.transAxes,ha='center')
    ax=axes[1,1];ax.plot([0,1],[0,1],'--',color='#888',label='Calibrated')
    for b in summary.get('calibration',[]):
        err=None if b['lower'] is None else [[max(0,b['win_rate']-b['lower'])],[max(0,b['upper']-b['win_rate'])]]
        ax.errorbar(b['mean_price'],b['win_rate'],yerr=err,fmt='o',color='#315973',capsize=3)
        ax.annotate(f"n={b['n']}",(b['mean_price'],b['win_rate']),xytext=(3,7 if b['win_rate']<.9 else -15),textcoords='offset points',fontsize=7)
    ax.set(title='Calibration: all buckets at confirmation',xlabel='Mean YES price',ylabel='Observed win frequency',xlim=(0,1),ylim=(0,1));ax.legend(loc='upper left')
    if not summary['n']:ax.text(.5,.35,'No eligible confirmed events',transform=ax.transAxes,ha='center')
    ax=axes[1,2]
    if summary['n']:
        vals=[summary['event_mean_brier'],summary['event_uniform_brier']]
        ax.bar(['Observed prices','Uniform 1 / buckets'],vals,color=['#315973','#a3adb5'])
        for j,v in enumerate(vals):ax.text(j,v,f'{v:.4f}',ha='center',va='bottom')
    ax.set(title='Brier error: lower is better',ylabel='Mean squared error, equal event weight');ax.margins(y=.25)
    if not summary['n']:ax.text(.5,.5,'No eligible confirmed events',transform=ax.transAxes,ha='center')
    for ax in axes.flat:
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.14);ax.set_axisbelow(True)
    fig.supxlabel('Sep 16, 2025–Sep 15, 2026 | 30-minute as-of grid; 6 checks in [0.9, 1.1], before any bucket reaches 0.95.\n95% intervals: bootstrap by weather date (omitted below 10 dates). Accuracy and calibration are not trading returns.',fontsize=10)
    fig.savefig(path,dpi=145)
    if pdf:pdf.savefig(fig)
    plt.close(fig)

def timeline(e,detail,path):
    fig,(ax,bx)=plt.subplots(2,1,figsize=(14,8),sharex=True,gridspec_kw={'height_ratios':[3,1]},layout='constrained')
    dates=[dt.datetime.fromtimestamp(int(t),dt.timezone.utc) for t in detail['grid']]
    for j,m in enumerate(e['markets']):ax.plot(dates,detail['prices'][:,j],label=m['label'],linewidth=1)
    ax.set(title=e['platform'].upper()+' | '+e['title'],ylabel='YES price',ylim=(0,1.03));ax.legend(loc='upper left',bbox_to_anchor=(1,1),fontsize=8)
    bx.plot(dates,detail['prob_sum'],color='#315973');bx.axhspan(.9,1.1,color='#97b6a0',alpha=.4);bx.set(ylabel='Price sum',xlabel='UTC; carried prices use only earlier samples')
    if detail['confirm'] is not None:
        j=detail['confirm']
        for a in (ax,bx):
            a.axvline(dates[j],color='#b34a43',label='Sixth check');a.axvline(dates[j-5],color='#b34a43',linestyle=':',alpha=.7)
    bx.xaxis.set_major_formatter(mdates.DateFormatter('%b %d\n%H:%M',tz=dt.timezone.utc))
    fig.supxlabel('Solid red: confirmation available. Dotted red: retrospective run start. No order execution or P&L.',fontsize=10)
    fig.savefig(path,dpi=140);plt.close(fig)

def coverage_figure(inv,rows,path,pdf):
    months=[];date=START.replace(day=1)
    while date<END:
        months.append(date.strftime('%Y-%m'));date=(date.replace(day=28)+dt.timedelta(days=4)).replace(day=1)
    fig,axes=plt.subplots(2,1,figsize=(15,8),layout='constrained')
    for ax,platform in zip(axes,('international','us')):
        allrows=[e for e in inv['events'] if e['platform']==platform]
        elig=[r for r in rows if r['platform']==platform and r['converged']]
        counts=collections.Counter(e['day'][:7] for e in allrows);selected=collections.Counter(r['day'][:7] for r in elig)
        x=np.arange(len(months));ax.bar(x-.2,[counts[m] for m in months],width=.4,label='Inventory events',color='#a3adb5');ax.bar(x+.2,[selected[m] for m in months],width=.4,label='Confirmed events',color='#315973')
        ax.set(title=platform.upper()+' | Returned events by weather month',ylabel='Daily-high events',xticks=x,xticklabels=months);ax.tick_params(axis='x',rotation=35);ax.legend();ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.supxlabel('Requested window: Sep 16, 2025–Sep 15, 2026. First and last calendar months are partial.\nZero U.S. inventory before April 22 means no matching returned records, not an imputed trading history.',fontsize=10)
    fig.savefig(path,dpi=145);pdf.savefig(fig);plt.close(fig)

def method_figure(summary,platform,path,pdf):
    fig,axes=plt.subplots(1,2,figsize=(14,5.5),layout='constrained')
    variants=[('Retrospective start\n(uses later confirmation)','retrospective'),('Sixth check\n(confirmation available)','causal'),('Sixth check\n(quotes <=1 hour old)','fresh')]
    for j,(label,key) in enumerate(variants):
        v=summary[key]
        if v['n']:
            axes[0].bar(j-.17,v['favorite_hit'],width=.34,color='#315973',label='Favorite' if j==0 else None)
            axes[0].bar(j+.17,v['random_hit'],width=.34,color='#a3adb5',label='Uniform random' if j==0 else None)
            axes[0].text(j,max(v['favorite_hit'],v['random_hit'])+.03,f"n={v['n']}",ha='center')
        else:axes[0].text(j,.1,'No eligible\nevents',ha='center')
        if key in ('retrospective','causal') and v['n']:
            cal=v['calibration'];axes[1].plot([b['mean_price'] for b in cal],[b['win_rate'] for b in cal],marker='o',label='Run start (retrospective)' if key=='retrospective' else 'Sixth-check confirmation')
    axes[0].set(xticks=range(3),xticklabels=[v[0] for v in variants],ylim=(0,1),ylabel='Winner frequency',title='Favorite accuracy at different signal times')
    if summary['retrospective']['n']:axes[0].legend()
    axes[1].plot([0,1],[0,1],'--',color='#888',label='Calibrated');axes[1].set(xlim=(0,1),ylim=(0,1),xlabel='Mean YES price',ylabel='Win frequency',title='Calibration at run start versus confirmation');axes[1].legend()
    for ax in axes:ax.grid(alpha=.15);ax.set_axisbelow(True)
    fig.suptitle(platform.upper()+' | Timing and quote-freshness sensitivity',fontsize=18,fontweight='bold')
    fig.supxlabel('Retrospective start is descriptive, not an available real-time signal. Freshness sensitivity may select a different event subset.\nSep 16, 2025–Sep 15, 2026; accuracy does not establish profitability.',fontsize=10)
    fig.savefig(path,dpi=145);pdf.savefig(fig);plt.close(fig)

def loaded_events(events):
    def work(item):
        j,e=item
        try:loaded,error=load_event(e)
        except Exception as ex:loaded,error=None,'load_error:'+type(ex).__name__+':'+str(ex)
        return j,e,loaded,error
    source=iter(enumerate(events))
    # Bound outstanding event matrices; do not submit the whole archive at once.
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        queue=collections.deque()
        for _ in range(16):
            item=next(source,None)
            if item is not None:queue.append(pool.submit(work,item))
        while queue:
            yield queue.popleft().result()
            item=next(source,None)
            if item is not None:queue.append(pool.submit(work,item))

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    inv=json.loads((BASE/'inventory.json').read_text(encoding='utf-8'));rows=[];excluded=[];examples={}
    render_only='--render-only' in sys.argv
    if render_only:
        byid={e['id']:e for e in inv['events']}
        with gzip.open(OUT/'event-results.jsonl.gz','rt',encoding='utf-8') as f:cached=[json.loads(line) for line in f]
        excluded=json.loads((OUT/'excluded-events.json').read_text(encoding='utf-8'))
        source=((j,byid[r['id']],(r,{'confirm':0 if r['converged'] else None}),None) for j,r in enumerate(cached))
    else:source=loaded_events(inv['events'])
    for j,e,loaded,error in source:
        if error:excluded.append(dict(id=e['id'],platform=e['platform'],city=e['city'],day=e['day'],reason=error));continue
        record,detail=loaded;rows.append(record)
        key=(e['platform'],e['city'])
        if key not in examples or (record['converged'] and examples[key][1]['confirm'] is None):examples[key]=(e,detail)
        if j%1000==0:print('analyzed',j,'/',len(inv['events']),flush=True)
    summary={}
    for platform in ('international','us'):
        subset=[r for r in rows if r['platform']==platform]
        universe=[e for e in inv['events'] if e['platform']==platform]
        summary[platform]=dict(inventory_events=len(universe),inventory_contracts=sum(len(e['markets']) for e in universe),
            inventory_first_date=min(e['day'] for e in universe),inventory_last_date=max(e['day'] for e in universe),
            inventory_cities=len({e['city'] for e in universe}),inventory_weather_dates=len({e['day'] for e in universe}),
            clean_events=len(subset),raw_price_points_in_clean_events=sum(r['raw_points'] for r in subset),
            duplicate_timestamps_in_clean_events=sum(r['duplicate_timestamps'] for r in subset),
            exclusions=dict(collections.Counter(e['reason'] for e in excluded if e['platform']==platform)),
            causal=stats(subset),retrospective=stats(subset,'retrospective_start'),fresh=stats(subset,'fresh_confirmation'))
    save(OUT/'summary.json',summary);save(OUT/'excluded-events.json',excluded)
    with gzip.open(OUT/'event-results.jsonl.gz','wt',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row)+'\n')
    with (OUT/'event-results.csv').open('w',newline='',encoding='utf-8') as f:
        fields=['id','platform','city','day','buckets','opening_sum','converged','fresh_converged','favorite_hit','favorite_price','random_hit','brier','signal_timestamp','max_carry_minutes']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:
            v=r.get('confirmation',{});line={k:r.get(k) for k in fields};line.update({k:v.get(k) for k in ['favorite_hit','favorite_price','random_hit','brier','max_carry_minutes']});line['signal_timestamp']=v.get('timestamp');w.writerow(line)
    links=[];city_rows=[]
    with PdfPages(OUT/'weather-crowd-study.pdf') as pdf:
        coverage_figure(inv,rows,OUT/'coverage.png',pdf);links.append(('Date coverage','coverage.png'))
        for platform in ('international','us'):
            subset=[r for r in rows if r['platform']==platform];path=OUT/(platform+'.png')
            graph(subset,summary[platform]['causal'],platform.upper(),path,pdf);links.append((platform.upper(),path.name))
            method_figure(summary[platform],platform,OUT/(platform+'-timing.png'),pdf);links.append((platform.upper()+' timing comparison',platform+'-timing.png'))
        for platform,city in sorted({(e['platform'],e['city']) for e in inv['events']}):
            subset=[r for r in rows if r['platform']==platform and r['city']==city]
            metrics=stats(subset);slug=re_slug(platform+'-'+city)
            graph(subset,metrics,platform.upper()+' / '+city,OUT/(slug+'.png'),pdf)
            city_rows.append(dict(platform=platform,city=city,clean_events=len(subset),**metrics));links.append((platform.upper()+' / '+city,slug+'.png'))
            if (platform,city) in examples:
                e,detail=examples[(platform,city)]
                if not render_only:timeline(e,detail,OUT/(slug+'-timeline.png'))
                links.append((city+' example: '+e['day'],slug+'-timeline.png'))
    save(OUT/'cities.json',city_rows)
    # Static figure gallery; no changes to the trading dashboard.
    body=''.join('<li><a href="'+html.escape(file)+'">'+html.escape(label)+'</a></li>' for label,file in links)
    thumbs=''.join('<h2>'+html.escape(p.upper())+'</h2><a href="'+p+'.png"><img alt="'+p+' crowd study graphs" src="'+p+'.png" style="width:100%"></a>' for p in ('international','us'))
    page='<!doctype html><meta charset="utf-8"><title>Weather crowd study</title><style>body{font:16px Arial;margin:40px auto;max-width:1250px;padding:20px;color:#18232c;background:#fafafa}a{color:#24546c}li{margin:6px}pre{white-space:pre-wrap}</style><h1>Weather crowd study</h1><p>September 16, 2025–September 15, 2026. Daily-high temperature events. Independent reproduction of <a href="https://youtu.be/-qWlCNF57BE">Ivan0x1’s analysis</a>.</p><p>U.S. coverage begins April 22, 2026. International includes U.S. cities on the international platform. No simulated fills or profit claims. 30-minute samples are not tick data. Price-sum convergence does not identify human traders.</p><p><a href="weather-crowd-study.pdf">Download all platform and city figures (PDF)</a> · <a href="event-results.csv">Event results CSV</a> · <a href="summary.json">Metrics and exclusions</a></p>'+thumbs+'<h2>Every city and example timelines</h2><ul>'+body+'</ul>'
    page=page.replace('<p><a href="weather-crowd-study.pdf">','<p><a href="methodology.md">Methodology</a> · <a href="weather-crowd-study.pdf">')
    (OUT/'index.html').write_text(page,encoding='utf-8')
    method=(ROOT/'docs/CROWD-CALIBRATION-STUDY.md').read_text(encoding='utf-8')
    method=method.replace('(ARCHITECTURE-UML.md#weather-crowd-calibration-study)','(https://github.com/burdena0/weather-lab-polymarket-us/blob/main/docs/ARCHITECTURE-UML.md#weather-crowd-calibration-study)').replace('(../research/crowd-study-20260916)','(index.html)')
    (OUT/'methodology.md').write_text(method,encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)

def re_slug(s):
    import re
    return re.sub('[^a-z0-9]+','-',s.lower()).strip('-')

if __name__=='__main__':main()
