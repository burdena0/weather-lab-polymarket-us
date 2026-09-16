import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from weatherlab.historical import blind_context, run_month, read_rows


class HistoricalTests(unittest.TestCase):
    def test_reader_bounds_rows_and_line_allocations(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'rows.jsonl';p.write_text('{}\n'*100)
            with self.assertRaisesRegex(ValueError,'count'):list(read_rows(p,31))
            p.write_text('x'*100001)
            with self.assertRaisesRegex(ValueError,'100 KB'):list(read_rows(p))

    def fixture(self):
        case={'case_id':'2026-08-01','station':'KLAX','date':'2026-08-01','forecast_runtime':10,
              'forecast_available_at':20,'decision_at':30,'day_start':40,'forecast_high_f':75,
              'forecast_evidence_id':'test-forecast','forecast_product':'test','availability_verified':False,
              'actual_high_f':999,'future_secret':'NEVER_IN_PROMPT'}
        training=[{'date':f'2026-07-{i:02d}','station':'KLAX','outcome_published_at':15,
                   'forecast_available_at':1,'day_start':2,'forecast_high_f':70,'actual_high_f':71,
                   'availability_verified':False} for i in range(1,12)]
        return case,training

    def test_label_injection_and_future_history_excluded(self):
        case,training=self.fixture()
        training.append(dict(training[0],date='2026-07-31',outcome_published_at=31,actual_high_f=123))
        ctx=blind_context(case,training)
        self.assertEqual(len(ctx['history']),11)
        raw=json.dumps(ctx)
        for forbidden in ('999','NEVER_IN_PROMPT','KLAX','2026-08-01','123'):
            self.assertNotIn(forbidden,raw)

    def test_future_forecast_refused(self):
        case,training=self.fixture();case['forecast_available_at']=31
        with self.assertRaises(ValueError):blind_context(case,training)

    def write_corpus(self,root,label):
        case,training=self.fixture()
        files={'training.jsonl':training,'cases.jsonl':[case],'labels.jsonl':[{'case_id':case['case_id'],'actual_high_f':label}]}
        hashes={}
        for name,rows in files.items():
            p=root/name;p.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8');hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        (root/'manifest.json').write_text(json.dumps({'test_month':'2026-08','availability_verified':False,'files':hashes}),encoding='utf-8')

    def test_changing_test_outcomes_cannot_change_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.write_corpus(root,60)
            a=run_month(root,root/'a',allow_assumed=True)
            self.write_corpus(root,90)
            b=run_month(root,root/'b',allow_assumed=True)
            self.assertEqual((root/'a/predictions.jsonl').read_bytes(),(root/'b/predictions.jsonl').read_bytes())
            self.assertNotEqual(a['arms']['statistical_baseline']['mean_brier'],b['arms']['statistical_baseline']['mean_brier'])
            self.assertTrue(a['outcomes_read_after_predictions'])
            self.assertFalse(a['historical_trades_simulated'])

    def test_strict_mode_refuses_unverified_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.write_corpus(root,60)
            with self.assertRaisesRegex(ValueError,'first-seen'):run_month(root,root/'a')

    def test_corpus_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.write_corpus(root,60)
            (root/'cases.jsonl').write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash'):run_month(root,root/'a',allow_assumed=True)
