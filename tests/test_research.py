import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from weatherlab.sources import full_day_periods, select_markets
from weatherlab.readiness import readiness, check_models
from weatherlab.research import verify_settlement, reconcile, pair_history
from weatherlab.rag import EvidenceStore
from weatherlab.fixtures import sample, config, WALLET
from weatherlab.engine import replay


class ResearchTests(unittest.TestCase):
    def test_history_pairing_preserves_download_and_review_availability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'forecast.json';outcomes=root/'outcomes.jsonl'
            f={'high_f':70,'day_start':100,'day_end':86500,'issued_at':50,'received_at':60,'evidence_id':'nws-test'}
            archive.write_text(json.dumps([{'market':{'station':'KLAX','date':'2020-01-01'},'forecast':f}]))
            actual={'station':'KLAX','date':'2020-01-01','actual_high_f':71,'reviewed':True,'review_note':'Matched station/date/MAXIMUM',
                    'source_url':'https://api.weather.gov/products/test','product_text':'test CLI','product_sha256':hashlib.sha256(b'test CLI').hexdigest(),
                    'published_at':86600,'received_at':86700}
            outcomes.write_text(json.dumps(actual)+'\n')
            store=EvidenceStore(root/'rag.sqlite')
            report=pair_history(archive,outcomes,root/'history.jsonl',store)
            self.assertEqual(report['history_pairs'],1)
            row=json.loads((root/'history.jsonl').read_text())
            self.assertGreater(row['available_at'],row['received_at'])
            self.assertEqual(row['forecast_received'],60)
            self.assertEqual(row['actual_high_f'],71)

    def test_history_pairing_rejects_unreviewed_or_tampered_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'forecast.json';outcomes=root/'outcomes.jsonl'
            archive.write_text(json.dumps([{'market':{'station':'KLAX','date':'2020-01-01'},'forecast':{'day_start':100,'received_at':60,'issued_at':50}}]))
            outcomes.write_text(json.dumps({'station':'KLAX','date':'2020-01-01','reviewed':False}))
            with self.assertRaisesRegex(ValueError,'review'):pair_history(archive,outcomes,root/'history.jsonl',EvidenceStore(root/'rag.sqlite'))

    def test_forecast_uses_exact_venue_interval(self):
        rows=[{'startTime':i*3600,'endTime':(i+1)*3600,'temperature':70,'temperatureUnit':'F'} for i in range(26)]
        m={'day_start':3600,'close_at':25*3600}
        selected,start,end=full_day_periods(rows,m)
        self.assertEqual(len(selected),24)
        self.assertEqual(selected[0]['startTime'],3600)
        self.assertEqual(end-start,86400)
        for bad in (rows[:24],rows[:4]+rows[5:],rows+[rows[4]]):
            with self.assertRaises(ValueError): full_day_periods(bad,m)

    def test_nonfinite_forecast_rejected(self):
        rows=[{'startTime':i*3600,'endTime':(i+1)*3600,'temperature':70,'temperatureUnit':'F'} for i in range(24)]
        rows[10]['temperature']=float('nan')
        with self.assertRaises(ValueError):full_day_periods(rows,{'day_start':0,'close_at':86400})

    def test_future_selection_excludes_started_days(self):
        base={'date':'2026-09-15','station':'KLAX'}
        rows=[dict(base,slug='started',day_start=10),dict(base,slug='future',day_start=100)]
        self.assertEqual([m['slug'] for m in select_markets(rows,50,4)],['future'])
        self.assertEqual(len(select_markets(rows,50,4,'all_dates')),2)

    def test_readiness_never_leaks_key(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'OPENAI_API_KEY':'private-test-key','WEATHERLAB_ENABLE_CLOUD':'0'},clear=True):
            report=readiness(tmp)
            self.assertFalse(report['cloud_configured'])
            self.assertTrue(report['api_key_present'])
            self.assertNotIn('private-test-key',json.dumps(report))
            self.assertFalse(report['research_ready'])

    def test_model_check_without_key_never_uses_network(self):
        with patch.dict(os.environ,{},clear=True),patch('urllib.request.build_opener') as network:
            self.assertEqual(check_models()['status'],'blocked')
            network.assert_not_called()

    def settlement_fixture(self):
        expected={'slug':'test','market_id':'1','rules_hash':hashlib.sha256(b'rules').hexdigest()}
        metadata={'market':{'id':'1','slug':'test','description':'rules','status':'MARKET_STATUS_RESOLVED','closed':True,'active':False,'endDate':100}}
        book={'marketData':{'marketSlug':'test','state':'MARKET_STATE_EXPIRED','stats':{'settlementPx':{'value':'1','currency':'USD'},'settlementSetTime':150}}}
        return metadata,book,expected

    def test_final_settlement_requires_identity_rules_status_and_timestamp(self):
        m,b,e=self.settlement_fixture()
        self.assertEqual(verify_settlement(m,b,e,200,'hash')['yes_payout'],1)
        for field,value in [('status','MARKET_STATUS_OPEN'),('description','changed'),('id','2'),('closed',False)]:
            bad=copy.deepcopy(m);bad['market'][field]=value
            with self.assertRaises(ValueError):verify_settlement(bad,b,e,200,'hash')
        for payout in ('0.5','NaN'):
            bad=copy.deepcopy(b);bad['marketData']['stats']['settlementPx']['value']=payout
            with self.assertRaises(ValueError):verify_settlement(m,bad,e,200,'hash')
        with self.assertRaises(ValueError):verify_settlement(m,b,e,120,'hash')

    def test_reconciliation_preserves_original_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,_=sample();data['synthetic']=False;data['frames']=data['frames'][:2]
            c=config('wallet_control');c['reference_wallet']=WALLET
            result=replay(c,data,root/'run')
            self.assertEqual(result['status'],'completed')
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'run').iterdir() if p.is_file()}
            def settlement(source,expected):return dict(expected,venue='polymarket_us',yes_payout=1,received_at=1,final=True,evidence_id='mock-test')
            with patch('weatherlab.research.collect_settlement',side_effect=settlement):
                report=reconcile(root/'run',root/'reconciled')
            self.assertTrue(report['complete'])
            self.assertEqual(len(report['settlements']),1)
            after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'run').iterdir() if p.is_file()}
            self.assertEqual(before,after)

    def test_reconciliation_rejects_tampered_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,_=sample();data['synthetic']=False
            replay(config('wallet_control'),data,root/'run')
            p=root/'run/checkpoint.json';checkpoint=json.loads(p.read_text());checkpoint['account']['cash']=999
            p.write_text(json.dumps(checkpoint))
            with self.assertRaisesRegex(ValueError,'Checkpoint'):reconcile(root/'run',root/'out')
