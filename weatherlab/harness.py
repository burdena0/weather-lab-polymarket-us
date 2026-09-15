"""Evidence-based completion and integrity checks, independent of model opinion."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from .core import digest


def code_hash():
    root=Path(__file__).resolve().parent
    return digest({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))})


def classify(reason):
    text=reason.lower()
    for words,category,next_job in [
        (('budget','cloud disabled','api_key','tariff','price_medium'),'configuration','Configure local credentials and an explicit budget; do not retry automatically.'),
        (('future','chronolog','pre-start'),'temporal_validation','Inspect source and receipt timestamps; never backdate availability.'),
        (('history','forecast','source','mapping','station'),'evidence_gap','Collect missing source evidence or review exact contract mapping.'),
        (('depth','price moved','reserve','cap','stale','book'),'execution_guard','Wait for a fresh eligible observation; expired opportunities stay expired.'),
        (('schema','citation','probability','response'),'model_validation','Inspect the recorded schema/citation failure and add a regression test.'),
    ]:
        if any(word in text for word in words):return {'class':category,'next_job':next_job}
    return {'class':'unclassified','next_job':'Inspect journal evidence before any retry.'}


def verify_run(root):
    root=Path(root)
    summary=json.loads((root/'summary.json').read_text())
    previous='0'*64
    count=0
    with sqlite3.connect(root/'journal.sqlite') as db:
        for seq,at,kind,payload,prev_hash,event_hash in db.execute('SELECT seq,at,kind,payload,prev_hash,event_hash FROM events ORDER BY seq'):
            expected=digest({'seq':seq,'at':at,'kind':kind,'payload':json.loads(payload),'previous':previous})
            if previous!=prev_hash or expected!=event_hash:
                raise ValueError('Journal integrity mismatch at event '+str(seq))
            previous=event_hash;count+=1
    checkpoint=json.loads((root/'checkpoint.json').read_text())
    account=checkpoint['account']
    open_cost=sum(p['cost'] for p in account['positions'].values())
    checks={
        'journal_hash_chain':True,
        'journal_tip_matches':summary['journal_tip']==previous,
        'paper_only':summary['execution']=='paper_only',
        'reserve_preserved':account['cash']>=40-1e-7,
        'ledger_reconciles':abs(account['cash']+open_cost-50-account['realized'])<1e-6,
        'summary_cash_matches':abs(summary['cash']-account['cash'])<1e-5,
        'summary_model_cost_matches':abs(summary['model_cost']-account['model_cost'])<1e-5,
        'run_completed':summary['status']=='completed',
        'pending_intents_cancelled':checkpoint['pending']==[],
    }
    return {'accepted':all(checks.values()),'checks':checks,'event_count':count,'journal_tip':previous,
            'code_hash':summary['code_hash'],'config_hash':summary['config_hash'],'dataset_hash':summary['dataset_hash'],
            'evidence_class':'synthetic_software_validation' if summary['synthetic'] else 'retrospective_cloud_replay' if summary['inference']=='cloud' else 'test_model_on_recorded_data',
            'proves':'Ledger and trace consistency for this run only. Does not prove forecast skill, fills or profitability.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_directory');args=p.parse_args()
    result=verify_run(args.run_directory);print(json.dumps(result,indent=2))
    if not result['accepted']:raise SystemExit(1)


if __name__=='__main__':main()
