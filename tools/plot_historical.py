"""Export the reviewed comparison JSON with Matplotlib (optional, outside core runtime)."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();r=json.loads(Path(args.input).read_text(encoding='utf-8'))
    if r['status']!='complete' or not r['paired_station_days']:raise ValueError('Require completed runs and shared scored cases')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'svg.fonttype':'none'})
    fig,(ax,cov)=plt.subplots(1,2,figsize=(12,6.4),gridspec_kw={'width_ratios':[3.7,1.2]})
    fig.subplots_adjust(left=.24,right=.97,top=.76,bottom=.26,wspace=.45)
    names=[a['name'] for a in r['arms']];values=[a['paired_brier'] for a in r['arms']]
    for i,a in enumerate(r['arms']):
        ax.barh(i,a['paired_brier'],height=.5,color='#8b8b8b' if i==0 else '#344f6f',zorder=2)
        lo,hi=a['paired_interval'];ax.plot([lo,hi],[i,i],color='#111',linewidth=1.4,zorder=3)
        ax.plot([lo,hi],[i,i],linestyle='none',marker='|',color='#111',markersize=9,zorder=3)
        ax.text(hi+.006,i,f"{a['paired_brier']:.4f}",va='center',fontsize=10)
        cov.barh(i,a['scored'],height=.5,color='#8b8b8b' if i==0 else '#344f6f')
        cov.text(a['scored']+1,i,f"{a['scored']}/50",va='center',fontsize=10)
    ax.set_yticks(range(4),names);ax.invert_yaxis();cov.set_yticks(range(4),['']*4);cov.invert_yaxis()
    ax.set_xlim(0,max(a['paired_interval'][1] for a in r['arms'])*1.28)
    ax.set_xlabel('Mean Brier error (lower is better)');cov.set_xlabel('Cases scored');cov.set_xlim(0,65);cov.set_xticks([0,25,50])
    ax.set_title('Identical cases across all models',loc='left',fontsize=11,pad=14)
    cov.set_title('Coverage',loc='left',fontsize=11,pad=14)
    for axis in (ax,cov):
        axis.spines[['top','right','left']].set_visible(False);axis.tick_params(axis='y',length=0)
        axis.grid(axis='x',color='#e4e4e4',zorder=0);axis.set_axisbelow(True)
    fig.text(.04,.94,'Historical weather forecast comparison',fontsize=21,weight='bold')
    fig.text(.04,.887,f"6–15 September 2026  |  Five US stations  |  {r['paired_station_days']} shared station-days / {r['paired_calendar_days']} calendar dates",fontsize=11)
    fig.text(.04,.84,'Fixed threshold: daily high at least 80°F. Forecast accuracy only; no trading-profit estimate.',fontsize=10,color='#444')
    fig.text(.04,.18,'Whiskers: descriptive 95% calendar-day block bootstrap (2,000 draws). Only ten dates; exploratory evidence.',fontsize=9)
    fig.text(.04,.145,'Shared cases exclude abstentions and failed requests. This can bias the comparison; coverage is shown separately.',fontsize=9)
    fig.text(.04,.11,'Wallet / arbitrage control: NOT EVALUATED. Historical depth and verified reference-wallet signals are unavailable.',fontsize=9,weight='bold')
    fig.text(.04,.065,'Sources: IEM archived GFS MOS + raw NWS CLI; immutable Weather Lab prediction audits. Archive availability is assumed.',fontsize=8,color='#555')
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    for ext in ('png','svg','pdf'):fig.savefig(out.with_suffix('.'+ext),dpi=240,facecolor='white')
    plt.close(fig)


if __name__=='__main__':main()
