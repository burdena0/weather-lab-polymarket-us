"""Plot an exploratory policy comparison from its immutable result JSON."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot(report, out):
    selected=report['selection']['candidate_id']
    rows=[r for r in report['variants'] if r['variant']['id'].endswith('__original') or r['variant']['id']==selected]
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'text.parse_math':False,'svg.fonttype':'none'})
    fig,(ax,net)=plt.subplots(1,2,figsize=(13,8),gridspec_kw={'width_ratios':[1.2,1]})
    fig.subplots_adjust(left=.24,right=.95,top=.75,bottom=.32,wspace=.30)
    labels=[]
    for i,row in enumerate(rows):
        primary=row['evaluation']['scenarios'][1];stress=row['evaluation']['scenarios'][2]
        label=row['variant']['name'].replace(' / ','\n')
        if row['variant']['id']==selected:label+=' *'
        labels.append(label)
        ax.scatter(primary['pnl_after_models'],i-.09,marker='o',s=44,color='#244c67',label='2 cents/share' if i==0 else None,zorder=3)
        ax.scatter(stress['pnl_after_models'],i+.09,marker='^',s=44,color='#b25443',label='5 cents/share' if i==0 else None,zorder=3)
        net.barh(i,primary['net_after_all_costs'],height=.5,color='#b25443')
        net.text(0,i,f"  ${primary['net_after_all_costs']:+.2f}",va='center')
    ax.set_yticks(range(len(rows)),labels);net.set_yticks(range(len(rows)),['']*len(rows))
    for a in (ax,net):
        a.invert_yaxis();a.axvline(0,color='#555',linewidth=1)
        a.spines[['top','right','left']].set_visible(False);a.tick_params(axis='y',length=0)
        a.grid(axis='x',color='#ddd');a.set_axisbelow(True)
    ax.margins(x=.17);net.set_xlim(-50,14)
    ax.set_xlabel('After trading fees and model costs / USD');net.set_xlabel('Including overhead at 2 cents / USD')
    fig.legend(*ax.get_legend_handles_labels(),loc='upper left',bbox_to_anchor=(.24,.245),ncol=2,frameon=False)
    fig.text(.04,.94,'Policy changes improved some returns; total profit remains negative',fontsize=18,weight='bold')
    fig.text(.04,.89,'Evaluation: 11-15 September 2026 | 25 contracts | Five stations | Exploratory reused dates',fontsize=11)
    fig.text(.04,.84,'* Fixed LLM + 50% market blend was selected on September 6-9 development results only.',fontsize=10)
    fig.text(.04,.80,'All 23 tested variants are retained in the report. Displayed-price scenarios assume full fills; quantities are unavailable.',fontsize=9)
    fig.text(.04,.19,'Each alternative: $50 starting cash, $40 reserve, maximum $2 per entry / five shares. No extra cloud calls.',fontsize=10)
    fig.text(.04,.145,f"Overhead: ${report['evaluation_overhead_per_arm']:.2f} per alternative at $200/month through settlement; separate from trading cash.",fontsize=10)
    fig.text(.04,.10,'Scenarios are not confidence intervals. Entry rechecks can cancel different trades at different price stresses.',fontsize=9)
    fig.text(.04,.055,'Not an untouched holdout or forecast of future profit. No Apple Weather or private reinforcement-model inputs.',fontsize=10,weight='bold')
    for ext in ('png','svg'):fig.savefig(Path(out).with_suffix('.'+ext),dpi=180,facecolor='white')
    plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();plot(json.loads(Path(args.input).read_text(encoding='utf-8')),args.out)
