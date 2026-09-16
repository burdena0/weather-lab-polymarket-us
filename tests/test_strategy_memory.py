import copy
import json
import tempfile
import unittest
from pathlib import Path
from weatherlab.strategy_memory import seed, validate, inventory
from weatherlab.rag import EvidenceStore
from weatherlab.fixtures import sample, config
from weatherlab.engine import replay, validate_config


class StrategyMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=EvidenceStore(Path(self.tmp.name)/'evidence.sqlite')
        self.data,self.history=sample()
        self.m=self.data['frames'][0]['markets'][0];self.now=self.data['frames'][0]['at']
        self.rows=[r for r in seed(self.now-10) if r['station']==self.m['station']]

    def get(self, **kwargs):
        return self.store.retrieve(self.m,self.now,include_strategies=True,**kwargs)

    def test_seed_is_untested_bounded_causal_and_opt_in(self):
        self.assertEqual(len(seed(self.now)),50)
        self.store.ingest(self.rows)
        r=self.get()
        self.assertEqual(len(r['documents']),4)
        self.assertLessEqual(r['audit']['strategy_memory']['context_bytes'],8000)
        self.assertTrue(all(d['profitability_established'] is False for d in r['documents']))
        self.assertEqual(self.store.retrieve(self.m,self.now)['documents'],[])
        self.assertEqual(self.store.retrieve(self.m,self.now-11,include_strategies=True)['documents'],[])
        with self.store.connect() as db: self.assertEqual(inventory(db)['total_revisions'],10)

    def test_retired_and_expired_revisions_never_resurrect(self):
        row=self.rows[0];self.store.ingest([row])
        update=dict(row,evidence_id='retired',revision=2,status='retired',available_at=self.now-2,received_at=self.now-2)
        self.store.ingest([update]);self.assertEqual(self.get()['documents'],[])
        old=self.store.retrieve(self.m,self.now-3,include_strategies=True)
        self.assertEqual(old['documents'][0]['revision'],1)
        update=dict(update,evidence_id='expired',revision=3,status='hypothesis',expires_at=self.now-1)
        self.store.ingest([update]);self.assertEqual(self.get()['documents'],[])

    def test_synthetic_wrong_station_and_wrong_source_excluded(self):
        row=dict(self.rows[0],synthetic=True)
        self.store.ingest([row]);self.assertEqual(self.get()['documents'],[])
        self.assertEqual(len(self.get(allow_synthetic=True)['documents']),1)
        other=copy.deepcopy(self.m);other['source']='other'
        self.assertEqual(self.store.retrieve(other,self.now,include_strategies=True,allow_synthetic=True)['documents'],[])

    def test_revision_identity_and_content_immutable(self):
        row=self.rows[0];self.store.ingest([row])
        self.assertEqual(self.store.ingest([row]),0)
        with self.assertRaises(ValueError): self.store.ingest([dict(row,text='Changed')])
        with self.assertRaises(ValueError): self.store.ingest([dict(row,evidence_id='different')])

    def evaluation(self):
        return dict(verification='reported_not_independently_verified',training_end=self.now-100,
            config_frozen_at=self.now-90,test_start=self.now-80,test_end=self.now-20,
            dataset_hash='a'*64,config_hash='b'*64,report_hash='c'*64,report_url='https://example.org/report',
            station_days=30,trades=20,variants_tested=7,fees=1,slippage=1,model_cost=1,overhead=1,
            gross_pnl=-1,net_pnl=-5,max_drawdown=7,limitations='Reported paper fills; no live validation.')

    def test_negative_evaluation_retained_and_money_withheld_from_forecaster(self):
        row=dict(self.rows[0],status='paper_evaluated',evaluation=self.evaluation())
        self.store.ingest([row]);doc=self.get()['documents'][0]
        self.assertEqual(doc['status'],'paper_evaluated')
        self.assertNotIn('net_pnl',json.dumps(doc))
        self.assertEqual(doc['evaluation_context']['variants_tested'],7)

    def test_fabricated_profit_status_bad_costs_and_future_evaluations_rejected(self):
        for field,value in [('net_pnl',100),('test_end',self.now+100),('variants_tested',0),('verification','verified')]:
            e=self.evaluation();e[field]=value
            with self.assertRaises(ValueError): validate(dict(self.rows[0],status='paper_evaluated',evaluation=e))
        with self.assertRaises(ValueError): validate(dict(self.rows[0],profitability_established=True))
        with self.assertRaises(ValueError): validate(dict(self.rows[0],status='profitable'))

    def test_config_control_and_boolean_gate(self):
        with self.assertRaises(ValueError):validate_config(dict(config('wallet_control'),strategy_memory=True))
        with self.assertRaises(ValueError):validate_config(dict(config('fixed_llm'),strategy_memory='true'))

    def test_all_forecasting_arms_retrieve_cards_in_isolated_replays(self):
        self.store.ingest(self.history+self.rows)
        for key in ('fixed_llm','adaptive_llm','polyswarm'):
            out=Path(self.tmp.name)/key
            r=replay(dict(config(key),strategy_memory=True),self.data,out,rag=self.store)
            self.assertEqual(r['status'],'completed')
            import sqlite3
            with sqlite3.connect(out/'journal.sqlite') as db:
                events=[json.loads(x[0]) for x in db.execute("SELECT payload FROM events WHERE kind='retrieval'")]
            self.assertTrue(any(e['strategy_memory']['selected_ids'] for e in events))
            self.assertEqual(r['config']['initial_capital'],50)


if __name__=='__main__':unittest.main()
