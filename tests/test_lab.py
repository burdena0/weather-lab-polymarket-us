import copy
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from weatherlab.core import Account, quote, levels, complete_partition, context, history_asof, stamp
from weatherlab.engine import replay, validate_config
from weatherlab.fixtures import sample, config, WALLET
from weatherlab.models import FixtureModel, CloudModel, validate_prediction
from weatherlab.packages import inspect_package
from weatherlab.rag import EvidenceStore
from weatherlab.strategies import Strategy, leg, route, forecast, STRATEGIES


class LabTests(unittest.TestCase):
    def setUp(self):
        self.dataset, self.history = sample()
        self.m = self.dataset['frames'][0]['markets'][0]
        self.now = self.dataset['frames'][0]['at']
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_risk_profile_changes_entry_gate_and_is_audited(self):
        class Uncertain(FixtureModel):
            def predict(inner, *args, **kwargs):
                p, call = super().predict(*args, **kwargs)
                p.update(probability_yes=.8, lower=.6, upper=.95, confidence=.6)
                return p, call
        for kind in ('fixed_llm', 'adaptive_llm', 'polyswarm'):
            c = config(kind)
            c['risk_profile'] = 'reliable'
            result = Strategy(c, Uncertain(), self.now).decide({self.m['slug']: self.m}, [], Account(), self.now)[0]
            self.assertIn('skip', result)
            self.assertEqual(result['audit']['risk_profile'], 'reliable')
            c['risk_profile'] = 'risky'
            result = Strategy(c, Uncertain(), self.now).decide({self.m['slug']: self.m}, [], Account(), self.now)[0]
            self.assertIn('legs', result)
            self.assertEqual(result['audit']['risk_profile'], 'risky')

    def test_reliable_cap_applies_at_delayed_fill(self):
        with self.assertRaisesRegex(ValueError, 'Station-day'):
            Account().fill([leg(self.m, 'YES', 'BUY', 6, .9)], {self.m['slug']: self.m}, self.now, event_cap=2)

    def test_risk_profiles_persist_without_mutating_old_results(self):
        from weatherlab.server import Lab
        lab = Lab(self.root/'dashboard')
        lab.latest = {'fixed_llm': {'config': {'risk_profile': 'balanced'}}}
        lab.mutate('/api/risk', json.dumps({'strategy':'fixed_llm','profile':'risky'}).encode())
        lab.mutate('/api/settings', b'{"wallet":"","control_mode":"copy"}')
        self.assertEqual(lab.latest['fixed_llm']['config']['risk_profile'], 'balanced')
        self.assertEqual(Lab(self.root/'dashboard').settings['risk_profiles']['fixed_llm'], 'risky')
        for kind, profile in [('wallet_control','risky'), ('fixed_llm','unlimited')]:
            with self.assertRaises(ValueError):
                lab.mutate('/api/risk', json.dumps({'strategy':kind,'profile':profile}).encode())

    def test_invalid_risk_profile_and_missing_data_label_rejected(self):
        c = config('fixed_llm'); c['risk_profile'] = 'unlimited'
        with self.assertRaises(ValueError): validate_config(c)
        self.dataset.pop('synthetic')
        with self.assertRaisesRegex(ValueError, 'synthetic'):
            replay(config('fixed_llm'), self.dataset, self.root/'invalid')

    def test_missing_forecast_abstains_without_crashing(self):
        self.m['forecast'] = None
        result = Strategy(config('fixed_llm'), FixtureModel(), self.now).decide({self.m['slug']:self.m}, [], Account(), self.now)
        self.assertIn('Missing complete forecast', result[0]['skip'])

    def test_streaming_accounts_persist_and_do_not_reset_between_demo_days(self):
        from weatherlab.session import Session
        session = Session(self.root/'sessions', {k:config(k) for k in STRATEGIES}, 'demo', None, self.root/'budget.sqlite')
        streamed = []
        for cycle in (1,2):
            session.cycle = cycle
            streamed.extend(session._demo_frames())
        snapshots=[]
        header={'schema_version':1,'venue':'polymarket_us','synthetic':True,'frames':[],'started_at':self.now}
        c=config('wallet_control');c['reference_wallet']=WALLET
        r=replay(c,header,self.root/'stream',frame_stream=iter(streamed),on_update=snapshots.append)
        self.assertEqual(r['status'],'completed')
        self.assertEqual(r['fills'],2)
        self.assertAlmostEqual(r['cash'],51.2)
        self.assertEqual(len(snapshots),13)
        self.assertTrue(json.loads((self.root/'stream'/'acceptance.json').read_text())['accepted'])
        self.assertEqual(len((self.root/'stream'/'inputs.jsonl').read_text().splitlines()),12)

    def test_background_session_runs_and_stops_all_workers(self):
        import time
        from weatherlab.session import Session
        session=Session(self.root/'sessions',{k:config(k) for k in STRATEGIES},'demo',None,self.root/'budget.sqlite',duration=10)
        session.start()
        deadline=time.monotonic()+5
        while len(session.state()['results'])<4 and time.monotonic()<deadline:
            time.sleep(.02)
        running=session.state()
        self.assertTrue(running['alive'])
        self.assertEqual(sum(running['workers'].values()),4)
        self.assertEqual(len(running['results']),4)
        session.stop.set();session.thread.join(timeout=5)
        self.assertFalse(session.thread.is_alive())
        self.assertEqual(session.state()['phase'],'stopped')
        for key in STRATEGIES:
            self.assertTrue(json.loads((session.root/key/'acceptance.json').read_text())['accepted'])

    def test_stream_rejects_time_reversal(self):
        header={'schema_version':1,'venue':'polymarket_us','synthetic':True,'frames':[],'started_at':self.now}
        r=replay(config('fixed_llm'),header,self.root/'stream',frame_stream=iter([self.dataset['frames'][1],self.dataset['frames'][0]]))
        self.assertEqual(r['status'],'failed')
        self.assertIn('chronological',r['error'])

    def test_stop_prevents_new_cloud_calls(self):
        import threading
        model=CloudModel(self.root/'budget.sqlite')
        model.cancel_event=threading.Event();model.cancel_event.set()
        with patch('urllib.request.urlopen') as http:
            with self.assertRaisesRegex(ValueError,'stopping'):
                model.predict(context(self.m,self.now),'medium','medium')
            http.assert_not_called()

    def test_all_four_complete_with_delayed_fill_and_settlement(self):
        for kind in STRATEGIES:
            with self.subTest(kind=kind):
                c = config(kind)
                c['reference_wallet'] = WALLET
                r = replay(c, self.dataset, self.root/kind)
                self.assertEqual(r['status'], 'completed')
                self.assertEqual(r['fills'], 1)
                self.assertGreater(r['realized_pnl'], 0)
                self.assertLess(r['net_after_costs'], r['realized_pnl'])
                self.assertEqual(r['inference'], 'fixture_not_llm')
                import sqlite3
                with sqlite3.connect(self.root/kind/'journal.sqlite') as db:
                    fill_at = db.execute("SELECT at FROM events WHERE kind='fill'").fetchone()[0]
                    self.assertGreater(fill_at, self.now)

    def test_no_same_frame_or_final_frame_fill(self):
        self.dataset['frames'] = self.dataset['frames'][:1]
        c = config('fixed_llm')
        r = replay(c, self.dataset, self.root/'one')
        self.assertEqual(r['fills'], 0)
        self.assertEqual(r['cash'], 50)

    def test_cash_reserve_and_atomic_rollback(self):
        a = Account()
        a.cash = 41
        intent = leg(self.m, 'YES', 'BUY', 5, .9)
        with self.assertRaisesRegex(ValueError, 'reserve'):
            a.fill([intent], {self.m['slug']: self.m}, self.now)
        self.assertEqual(a.cash, 41)
        self.assertEqual(a.positions, {})

    def test_station_day_cap(self):
        a = Account()
        a.fill([leg(self.m,'YES','BUY',5,.9)], {self.m['slug']:self.m}, self.now)
        other = copy.deepcopy(self.m)
        other['slug']='other';other['id']='other';other['book']['slug']='other'
        a.fill([leg(other,'YES','BUY',5,.9)], {'other':other}, self.now)
        with self.assertRaisesRegex(ValueError,'Station-day'):
            a.fill([leg(other,'YES','BUY',5,.9)], {'other':other}, self.now)

    def test_short_sales_rejected(self):
        with self.assertRaisesRegex(ValueError, 'short'):
            Account().fill([leg(self.m,'YES','SELL',1,0)], {self.m['slug']:self.m}, self.now)

    def test_missing_depth_rejected(self):
        self.m['book']['asks'] = [[.36, .5]]
        with self.assertRaisesRegex(ValueError, 'depth'):
            quote(self.m,'YES','BUY',1,self.now)

    def test_stale_and_future_books_rejected(self):
        for key, value in [('received',self.now-11),('source_at',self.now-121),('source_at',self.now+1)]:
            m=copy.deepcopy(self.m);m['book'][key]=value
            with self.assertRaises(ValueError):quote(m,'YES','BUY',1,self.now)

    def test_crossed_nan_and_off_tick_rejected(self):
        for ask in [.33, float('nan'), .365]:
            m=copy.deepcopy(self.m);m['book']['asks']=[[ask,10]]
            with self.assertRaises(ValueError):quote(m,'YES','BUY',1,self.now)

    def test_no_complement_correct(self):
        bids=levels(self.m,'NO','SELL',self.now)
        asks=levels(self.m,'NO','BUY',self.now)
        self.assertAlmostEqual(bids[0][0], .64)
        self.assertAlmostEqual(asks[0][0], .66)

    def test_changed_rules_rejected(self):
        intent=leg(self.m,'YES','BUY',1,.9)
        self.m['rules_hash']='changed'
        with self.assertRaisesRegex(ValueError,'changed'):
            Account().fill([intent],{self.m['slug']:self.m},self.now)

    def test_signal_dedup_and_start_boundary(self):
        c=config('wallet_control');c['reference_wallet']=WALLET
        s=Strategy(c,FixtureModel(),self.now)
        signals=self.dataset['frames'][0]['signals']
        first=s.decide({self.m['slug']:self.m},signals,Account(),self.now)
        second=s.decide({self.m['slug']:self.m},signals,Account(),self.now)
        self.assertIn('legs',first[0]);self.assertIn('skip',second[0])
        signals[0]['id']='older';signals[0]['trade_at']=self.now-1
        self.assertIn('Pre-start',s.decide({self.m['slug']:self.m},signals,Account(),self.now)[0]['skip'])

    def test_mapping_requires_identical_source(self):
        c=config('wallet_control');c['reference_wallet']=WALLET
        signals=self.dataset['frames'][0]['signals']
        signals[0]['contract_identity']=list(signals[0]['contract_identity']);signals[0]['contract_identity'][-1]='WU'
        d=Strategy(c,FixtureModel(),self.now).decide({self.m['slug']:self.m},signals,Account(),self.now)
        self.assertIn('exact',d[0]['skip'])

    def test_future_history_excluded(self):
        h=copy.deepcopy(self.history);h[0]['available_at']=self.now+1
        self.assertEqual(len(history_asof(h,self.m,self.now)),len(h)-1)

    def test_same_day_and_posthoc_forecast_excluded(self):
        h=copy.deepcopy(self.history);h[0]['date']=self.m['date'];h[1]['forecast_received']=h[1]['day_start']+1
        self.assertEqual(len(history_asof(h,self.m,self.now)),len(h)-2)

    def test_insufficient_history_abstains(self):
        self.m['history']=[]
        with self.assertRaisesRegex(ValueError,'10 causal'):context(self.m,self.now)

    def test_rag_immutable_and_point_in_time(self):
        store=EvidenceStore(self.root/'rag.sqlite')
        self.assertEqual(store.ingest(self.history),35)
        self.assertEqual(store.ingest(self.history),0)
        changed=copy.deepcopy(self.history[0]);changed['actual_high_f']=1
        with self.assertRaisesRegex(ValueError,'immutable'):store.ingest([changed])
        retrieved=store.retrieve(self.m,self.now,allow_synthetic=True)
        self.assertEqual(len(retrieved['history']),30)
        self.assertEqual(len(store.retrieve(self.m,self.now)['history']),0)
        self.assertEqual(len(store.retrieve(self.m,self.history[1]['available_at']-1,allow_synthetic=True)['history']),1)

    def test_rag_full_text_citations_and_future_document(self):
        store=EvidenceStore(self.root/'rag.sqlite')
        doc={'evidence_id':'rules-1','kind':'rules','station':'KNYC','date':'2026-09-15','published_at':self.now-10,
             'received_at':self.now-9,'available_at':self.now-9,'synthetic':True,'text':'KNYC CLI maximum temperature'}
        later=dict(doc,evidence_id='rules-later',published_at=self.now+10,received_at=self.now+11,available_at=self.now+11)
        store.ingest([doc,later])
        out=store.retrieve(self.m,self.now,allow_synthetic=True)
        self.assertEqual(out['audit']['document_ids'],['rules-1'])

    def test_model_citation_and_probability_validation(self):
        ctx=context(self.m,self.now);p,_=FixtureModel().predict(ctx,'medium','medium')
        p['evidence_ids']=['invented']
        with self.assertRaisesRegex(ValueError,'citation'):validate_prediction(p,ctx)
        p['evidence_ids']=ctx['evidence_ids'][:1];p['probability_yes']=float('nan')
        with self.assertRaises(ValueError):validate_prediction(p,ctx)

    def test_cloud_disabled_without_any_network(self):
        ctx=context(self.m,self.now)
        with patch.dict(os.environ,{'WEATHERLAB_ENABLE_CLOUD':'0'}),patch('urllib.request.urlopen') as http:
            with self.assertRaisesRegex(ValueError,'disabled'):CloudModel(self.root/'budget.sqlite').predict(ctx,'medium','medium')
            http.assert_not_called()

    def test_cloud_zero_budget_no_network(self):
        ctx=context(self.m,self.now)
        with patch.dict(os.environ,{'WEATHERLAB_ENABLE_CLOUD':'1','OPENAI_API_KEY':'fixture-key','WEATHERLAB_DAILY_API_BUDGET_USD':'0'}),patch('urllib.request.urlopen') as http:
            with self.assertRaisesRegex(ValueError,'budget'):CloudModel(self.root/'budget.sqlite').predict(ctx,'medium','medium')
            http.assert_not_called()

    def test_adaptive_routes_small_and_large(self):
        ctx=context(self.m,self.now);ctx['forecast']['high_f']=65
        self.assertEqual(route(ctx)[0],'small')
        ctx['history']=ctx['history'][:10];ctx['forecast']['high_f']=76;ctx['forecast']['revision_f']=5
        self.assertEqual(route(ctx)[0],'large')

    def test_swarm_distinct_personas_and_audit(self):
        ctx=context(self.m,self.now);model=FixtureModel()
        p,audit,delay=forecast('polyswarm',ctx,model,.35)
        self.assertEqual(len(audit['persona_predictions']),5)
        self.assertEqual(len(set(c['persona'] for c in model.calls)),5)
        self.assertEqual(delay,5)
        self.assertTrue(p['lower'] <= p['probability_yes'] <= p['upper'])

    def test_partition_rejects_gap_overlap_and_source(self):
        a=copy.deepcopy(self.m);b=copy.deepcopy(self.m)
        a['lower_f']=None;a['upper_f']=74;b['lower_f']=75;b['upper_f']=None
        self.assertTrue(complete_partition([a,b]))
        b['lower_f']=76;self.assertFalse(complete_partition([a,b]))
        b['lower_f']=74;self.assertFalse(complete_partition([a,b]))
        b['lower_f']=75;b['source']='WU';self.assertFalse(complete_partition([a,b]))

    def test_basket_mode_has_no_model_calls(self):
        a=copy.deepcopy(self.m);b=copy.deepcopy(self.m)
        a.update(lower_f=None,upper_f=74);b.update(lower_f=75,upper_f=None,slug='other',id='other')
        b['book']['slug']='other'
        c=config('wallet_control');c['control_mode']='arbitrage';model=FixtureModel()
        d=Strategy(c,model,self.now).decide({a['slug']:a,b['slug']:b},[],Account(),self.now)
        self.assertEqual(len(d[0]['legs']),2);self.assertEqual(model.calls,[])
        account=Account();account.fill(d[0]['legs'],{a['slug']:a,b['slug']:b},self.now,minimum_payout=1)
        self.assertEqual(account.fills,2)

    def test_settlement_idempotent_conflict_rejected(self):
        a=Account();a.fill([leg(self.m,'YES','BUY',1,.9)],{self.m['slug']:self.m},self.now)
        s=self.dataset['frames'][-1]['settlements'][0];now=self.dataset['frames'][-1]['at']
        a.settle(s,now);cash=a.cash;a.settle(s,now);self.assertEqual(a.cash,cash)
        with self.assertRaisesRegex(ValueError,'Conflicting'):a.settle(dict(s,yes_payout=0),now)

    def test_unknown_mark_not_zero_profit(self):
        a=Account();a.fill([leg(self.m,'YES','BUY',1,.9)],{self.m['slug']:self.m},self.now)
        summary=a.summary({},self.now+1000,1000)
        self.assertIsNone(summary['open_value']);self.assertIsNone(summary['net_after_costs'])

    def test_duplicate_time_and_overwrite_rejected(self):
        self.dataset['frames'][1]['at']=self.now
        with self.assertRaisesRegex(ValueError,'chronological'):replay(config('fixed_llm'),self.dataset,self.root/'bad')
        data,_=sample();replay(config('fixed_llm'),data,self.root/'exists')
        with self.assertRaises(FileExistsError):replay(config('fixed_llm'),data,self.root/'exists')

    def test_config_cannot_enable_live_or_lower_reserve(self):
        for patcher in ({'mode':'live'},{'reserve':0},{'initial_capital':500}):
            with self.assertRaises(ValueError):validate_config(dict(config('fixed_llm'),**patcher))

    def test_zip_traversal_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('../escape.py','')
        with self.assertRaisesRegex(ValueError,'Unsafe'):inspect_package(b.getvalue(),self.root)

    def test_nanosecond_venue_timestamp(self):
        self.assertAlmostEqual(stamp('2026-09-15T23:08:17.052852341Z'),stamp('2026-09-15T23:08:17.052852Z'))

    def test_depth_cannot_be_reused_in_same_snapshot(self):
        a=Account();self.m['book']['asks']=[[.36,1]]
        a.fill([leg(self.m,'YES','BUY',1,.9)],{self.m['slug']:self.m},self.now)
        with self.assertRaisesRegex(ValueError,'depth'):
            a.fill([leg(self.m,'YES','BUY',1,.9)],{self.m['slug']:self.m},self.now)

    def test_hash_chain_detects_tampering(self):
        from weatherlab.harness import verify_run
        import sqlite3
        root=self.root/'verified';replay(config('fixed_llm'),self.dataset,root)
        self.assertTrue(verify_run(root)['accepted'])
        with sqlite3.connect(root/'journal.sqlite') as db:db.execute("UPDATE events SET payload='{}' WHERE seq=1")
        with self.assertRaisesRegex(ValueError,'integrity'):verify_run(root)

    def test_mock_cloud_request_usage_and_evidence(self):
        ctx=context(self.m,self.now);prediction,_=FixtureModel().predict(ctx,'medium','medium')
        response={'status':'completed','id':'fixture-response','model':'fixture-model-snapshot','usage':{'input_tokens':10,'output_tokens':20},
                  'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(prediction)}]}]}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return json.dumps(response).encode()
        env={'WEATHERLAB_ENABLE_CLOUD':'1','OPENAI_API_KEY':'fixture-not-a-real-key','WEATHERLAB_DAILY_API_BUDGET_USD':'1','WEATHERLAB_PRICE_MEDIUM':'2,12'}
        with patch.dict(os.environ,env),patch('urllib.request.urlopen',return_value=Response()) as http:
            model=CloudModel(self.root/'budget.sqlite');p,call=model.predict(ctx,'medium','medium')
            self.assertAlmostEqual(model.cost,.00026)
            self.assertEqual(call['model'],'fixture-model-snapshot')
            request=http.call_args[0][0];payload=json.loads(request.data)
            self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
            self.assertFalse(payload['store']);self.assertEqual(payload['reasoning']['effort'],'medium')
            self.assertNotIn('book',payload['input'])

    def test_failed_cloud_call_budget_retained_and_no_retry(self):
        ctx=context(self.m,self.now)
        env={'WEATHERLAB_ENABLE_CLOUD':'1','OPENAI_API_KEY':'fixture-not-a-real-key','WEATHERLAB_DAILY_API_BUDGET_USD':'1','WEATHERLAB_PRICE_MEDIUM':'2,12'}
        with patch.dict(os.environ,env),patch('urllib.request.urlopen',side_effect=TimeoutError()) as http:
            model=CloudModel(self.root/'budget.sqlite')
            with self.assertRaisesRegex(ValueError,'retained'):model.predict(ctx,'medium','medium')
            self.assertGreater(model.cost,0);self.assertEqual(http.call_count,1)

    def test_integer_frame_timestamps_hash_consistent(self):
        from weatherlab.harness import verify_run
        for f in self.dataset['frames']:f['at']=int(f['at'])
        replay(config('fixed_llm'),self.dataset,self.root/'integer')
        self.assertTrue(verify_run(self.root/'integer')['accepted'])

    def test_real_evaluation_rejects_fixture(self):
        from weatherlab.evaluate import compare
        a=replay(config('fixed_llm'),self.dataset,self.root/'left')
        b=replay(config('adaptive_llm'),self.dataset,self.root/'right')
        with self.assertRaisesRegex(ValueError,'actual model'):compare(a,b)
        result=compare(a,b,allow_synthetic=True)
        self.assertEqual(result['matched_contracts'],1)
        self.assertIsNone(result['bootstrap_95_interval'])


if __name__=='__main__':unittest.main()
