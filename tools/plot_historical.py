"""Export the reviewed comparison JSON with Matplotlib (optional, outside core runtime)."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot_returns(r, out):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'svg.fonttype':'none','text.parse_math':False})
    fig,(ax,net)=plt.subplots(1,2,figsize=(13,7.5),gridspec_kw={'width_ratios':[1.2,1]})
    fig.subplots_adjust(left=.23,right=.97,top=.72,bottom=.32,wspace=.3)
    colors=['#8092a1','#233e5a','#b15340'];marks=['o','s','^']
    for j,(slip,color,mark) in enumerate(zip(r['policy']['slippages'],colors,marks)):
        values=[a['scenarios'][j]['pnl_after_models'] for a in r['arms']]
        ax.scatter(values,[i+(j-1)*.13 for i in range(len(values))],color=color,marker=mark,s=46,label=f'{slip*100:.0f} cents / share',zorder=3)
    for i,a in enumerate(r['arms']):
        primary=a['scenarios'][1]
        ax.annotate(f"${primary['pnl_after_models']:+.2f}",(primary['pnl_after_models'],i),xytext=(7,0),textcoords='offset points',va='center',fontsize=9)
        net.barh(i,primary['net_after_all_costs'],height=.55,color='#b15340' if primary['net_after_all_costs']<0 else '#233e5a')
        net.text(0,i,f"  ${primary['net_after_all_costs']:+.2f}",va='center',fontsize=10)
    names=[f"{a['name']}\n{a['scenarios'][1]['trades']} hypothetical trades / {a['scored']} forecasts" for a in r['arms']]
    ax.set_yticks(range(len(names)),names,fontsize=10);net.set_yticks(range(len(names)),['']*len(names))
    for axis in (ax,net):
        axis.invert_yaxis();axis.axvline(0,color='#555',linewidth=1)
        axis.spines[['top','right','left']].set_visible(False);axis.tick_params(axis='y',length=0)
        axis.grid(axis='x',color='#e4e4e4');axis.set_axisbelow(True)
    ax.margins(x=.35);net.set_xlim(min(a['scenarios'][1]['net_after_all_costs'] for a in r['arms'])*1.12,15)
    ax.set_xlabel('P&L after entry fees and model costs / USD')
    net.set_xlabel('P&L after all costs / USD')
    ax.set_title('Entry-price sensitivity',loc='left',fontsize=12,pad=15)
    net.set_title('Primary scenario + allocated overhead',loc='left',fontsize=12,pad=15)
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.19),ncol=3,fontsize=8,frameon=False)
    fig.text(.04,.94,'Contract return scenarios: hypothetical fills',fontsize=21,weight='bold')
    fig.text(.04,.89,'6-15 September 2026 weather dates | 50 exact contracts | Five US stations',fontsize=11)
    fig.text(.04,.84,'Actual archived display prices and verified payouts; historical quantities and fills are unavailable.',fontsize=10,color='#444')
    fig.text(.04,.80,'Primary entry assumption: displayed price + 2 cents/share. Dots are scenarios, not confidence intervals.',fontsize=10,color='#444')
    fig.text(.04,.17,f"Each arm: $50 initial cash, $40 reserve, at most $2 per entry / 5 shares. Held until recorded settlement.",fontsize=9)
    fig.text(.04,.135,f"Overhead: $200/month prorated over {r['overhead_days']:.2f} days = ${r['overhead_per_arm']:.2f} per arm, reported outside trading cash.",fontsize=9)
    fig.text(.04,.10,'Model costs include failed calls and unresolved reservations. Market-implied baseline abstains when no net edge exists.',fontsize=9)
    fig.text(.04,.065,'Exploratory reused dates and assumed archive availability. Not proof of profitability. Wallet/arbitrage control not evaluated.',fontsize=9,weight='bold')
    for ext in ('png','svg'):fig.savefig(Path(out).with_suffix('.'+ext),dpi=220,facecolor='white')
    plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();r=json.loads(Path(args.input).read_text(encoding='utf-8'))
    if 'policy' in r and r['policy'].get('version')=='contract-returns-v1':
        if r['status']!='complete':raise ValueError('Require complete contract run')
        plot_returns(r,args.out);return
    if r['status']!='complete' or not r['paired_station_days']:raise ValueError('Require completed runs and shared scored cases')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'svg.fonttype':'none'})
    fig,(ax,cov)=plt.subplots(1,2,figsize=(12,7.0),gridspec_kw={'width_ratios':[3.7,1.2]})
    fig.subplots_adjust(left=.24,right=.97,top=.76,bottom=.32,wspace=.45)
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
