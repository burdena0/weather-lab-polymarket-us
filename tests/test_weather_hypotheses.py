import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from weatherlab.core import Account, context
from weatherlab.fixtures import sample, config
from weatherlab.engine import validate_config
from weatherlab.models import FixtureModel
from weatherlab.protocol import VERSION, LATEST_VERSION, V2_AVAILABLE_AT, diagnostics
from weatherlab.hypotheses import HYPOTHESES
from weatherlab.weather_models import decode, MODELS, VARIABLES
from weatherlab.strategies import Strategy, leg
from weatherlab.ablation import run as ablate
from weatherlab.rag import EvidenceStore


def fixture():
    data,_=sample();m=copy.deepcopy(data['frames'][0]['markets'][0])
    now=V2_AVAILABLE_AT+60
    start=(int(now)//86400+1)*86400
    m.update(date=datetime.fromtimestamp(start,timezone.utc).date().isoformat(),day_start=start,close_at=start+86400,metadata_received=now)
    m['book'].update(received=now,source_at=now)
    f=m['forecast'];f.update(date=m['date'],issued_at=now-60,received_at=now-30,day_start=start,day_end=start+86400,station_coordinates=[40.7789,-73.9692])
    f['hourly']=[{'startTime':start+i*3600,'endTime':start+(i+1)*3600,'temperature':75 if i==16 else 71,'temperatureUnit':'F'} for i in range(24)]
    for i,r in enumerate(m['history']):
        at=start-(36-i)*86400
        r.update(date=datetime.fromtimestamp(at,timezone.utc).date().isoformat(),forecast_issued=at-7200,
            forecast_received=at-3600,day_start=at,day_end=at+86400,outcome_received=at+90000,
            published_at=at+89900,received_at=at+90000,available_at=at+90000,actual_high_f=76,forecast_high_f=75)
    raw={'latitude':40.8,'longitude':-73.95,'utc_offset_seconds':0,'hourly_units':{'time':'unixtime'},
         'hourly':{'time':[start+i*3600 for i in range(24)]}}
    for model in MODELS:
        for variable,(unit,_,_) in VARIABLES.items():
            key=variable+'_'+model;raw['hourly_units'][key]=unit
            raw['hourly'][key]=[75 if i==16 else 71 for i in range(24)] if variable=='temperature_2m' else [dict(cloud_cover=20,wind_speed_10m=10,wind_direction_10m=350)[variable]]*24
    f['comparison_models']=decode(raw,m,*f['station_coordinates'],now-10,'a'*64,'https://api.open-meteo.com/v1/forecast')
    return m,now,raw


class WeatherHypothesesTests(unittest.TestCase):
    def setUp(self): self.m,self.now,self.raw=fixture()

    def diag(self,flags=None):
        return diagnostics(self.m,context(self.m,self.now),self.now,LATEST_VERSION,list(HYPOTHESES) if flags is None else flags)['weather_hypotheses']

    def decide(self,flags=None,model=None,account=None):
        c=dict(config('fixed_llm'),research_protocol=LATEST_VERSION,weather_hypotheses=list(HYPOTHESES) if flags is None else flags)
        return Strategy(c,model or FixtureModel(),self.now).decide({self.m['slug']:self.m},[],account or Account(),self.now)[0]

    def test_named_families_exact_day_and_uncalibrated_point_filter(self):
        d=self.diag()
        self.assertEqual(d['entry_policy']['allowed_sides'],['YES'])
        self.assertEqual(d['model_high_spread_f'],0)
        self.assertEqual(d['peak_window_distance_hours'],0)
        self.assertEqual(d['recent_seven_day_mean_f'],76)
        self.assertEqual({m['family'] for m in d['models']},set(MODELS.values()))
        self.assertIn('legs',self.decide())

    def test_model_disagreement_blocks_entry_but_ablation_removes_gate(self):
        model=self.m['forecast']['comparison_models'][0]
        model['high_f']=80;model['hourly'][16]['temperature_2m']=80
        self.assertIn('Model consensus',self.decide()['skip'])
        self.assertIn('legs',self.decide(['peak_timing']))

    def test_peak_window_rule_checks_timing_not_just_same_high(self):
        model=self.m['forecast']['comparison_models'][0]
        model['hourly'][16]['temperature_2m']=71;model['hourly'][8]['temperature_2m']=75
        self.assertEqual(self.diag()['peak_window_distance_hours'],8)
        self.assertIn('Peak timing',self.decide(['peak_timing'])['skip'])
        self.assertIn('legs',self.decide([]))

    def test_regime_rule_reduces_actual_quantity_and_requires_extra_edge(self):
        baseline=self.decide([])['legs'][0]['qty']
        for row in self.m['forecast']['comparison_models'][0]['hourly'][18:]:
            row.update(cloud_cover=80,wind_direction_10m=90)
        result=self.decide(['regime_change'])
        self.assertLessEqual(result['legs'][0]['qty'],baseline/2)
        self.assertEqual(result['audit']['research_diagnostics']['weather_hypotheses']['entry_policy']['extra_edge'],.02)

    def test_circular_wind_direction_does_not_create_false_large_turn(self):
        for row in self.m['forecast']['comparison_models'][0]['hourly'][18:]:
            row.update(cloud_cover=90,wind_direction_10m=10)
        self.assertFalse(self.diag()['regime_change'])

    def test_recent_reference_requires_consecutive_causal_days(self):
        self.m['history'].pop(-3)
        self.assertIsNone(self.diag()['recent_seven_day_mean_f'])
        self.assertIn('Recent trend',self.decide(['recent_trend_break'])['skip'])
        self.assertIn('legs',self.decide([]))

    def test_trend_break_requires_matching_direction(self):
        for r in self.m['history']: r['actual_high_f']=65
        model=self.m['forecast']['comparison_models'][0]
        model['high_f']=64
        for r in model['hourly']:r['temperature_2m']=64
        self.assertIn('lacks directional',self.diag(['recent_trend_break'])['entry_policy']['blocks'][0])

    def test_new_entry_rules_do_not_prevent_owned_inventory_exit(self):
        class ExitModel(FixtureModel):
            def predict(inner,*args):
                p,c=super().predict(*args)
                p.update(probability_yes=.1,lower=.05,upper=.15,confidence=.9,abstain=False)
                return p,c
        self.m['history'].pop(-3)
        account=Account();account.fill([leg(self.m,'YES','BUY',1,.9)],{self.m['slug']:self.m},self.now)
        result=self.decide(model=ExitModel(),account=account)
        self.assertEqual(result['legs'][0]['action'],'SELL')

    def test_invalid_comparison_rejected_before_any_inference(self):
        for defect in ('future','stale','wrong_station','wrong_family','missing_hour','null','duplicate','wrong_location'):
            self.m,self.now,_=fixture();m=self.m['forecast']['comparison_models'][0]
            if defect=='future':m['available_at']=self.now+1
            if defect=='stale':m['received_at']=self.now-901
            if defect=='wrong_station':m['station']='KLAX'
            if defect=='wrong_family':m['family']='ECMWF IFS' if m['family']=='NOAA GFS' else 'NOAA GFS'
            if defect=='missing_hour':m['hourly'].pop()
            if defect=='null':m['hourly'][0]['temperature_2m']=None
            if defect=='duplicate':self.m['forecast']['comparison_models'][1]=copy.deepcopy(m)
            if defect=='wrong_location':m['requested_coordinates']=[0,0]
            model=FixtureModel();self.assertIn('skip',self.decide(model=model));self.assertEqual(model.calls,[])

    def test_decoder_rejects_wrong_units_timezone_coverage_and_location(self):
        for defect in ('units','utc','gap','far','oversized'):
            raw=copy.deepcopy(self.raw)
            if defect=='units':raw['hourly_units']['temperature_2m_gfs_global']='°C'
            if defect=='utc':raw['utc_offset_seconds']=3600
            if defect=='gap':raw['hourly']['time'][8]+=3600
            if defect=='far':raw['latitude']=0
            if defect=='oversized':raw['hourly']['time']=list(range(100))
            with self.assertRaises(ValueError):decode(raw,self.m,40.7789,-73.9692,self.now-10,'h','https://api.open-meteo.com/v1/forecast')

    def test_switch_validation_and_v2_availability(self):
        for flags in (['invented'],['model_consensus']*2,'model_consensus'):
            with self.assertRaises(ValueError):validate_config(dict(config('fixed_llm'),research_protocol=LATEST_VERSION,weather_hypotheses=flags))
        with self.assertRaises(ValueError):validate_config(dict(config('fixed_llm'),research_protocol=VERSION,weather_hypotheses=[]))
        model=FixtureModel();c=dict(config('fixed_llm'),research_protocol=LATEST_VERSION)
        self.assertIn('unavailable',Strategy(c,model,0).decide({},[],Account(),V2_AVAILABLE_AT-1)[0]['skip'])

    def test_seven_ablation_runs_are_isolated_and_inputs_unchanged(self):
        dataset={'schema_version':1,'venue':'polymarket_us','synthetic':True,'frames':[{'at':self.now,'markets':[self.m],'signals':[],'settlements':[]}]}
        original=copy.deepcopy(dataset)
        with tempfile.TemporaryDirectory() as tmp:
            report=ablate(dict(config('fixed_llm'),research_protocol=LATEST_VERSION),dataset,Path(tmp)/'runs')
            self.assertEqual(report['variants_completed'],7)
            self.assertTrue(all(r['status']=='completed' and r['synthetic'] and r['inference']=='fixture_not_llm' for r in report['results']))
            self.assertEqual(len(list((Path(tmp)/'runs').glob('*/journal.sqlite'))),7)
        self.assertEqual(dataset,original)

    def test_v2_retrieval_retains_recent_days_even_when_they_are_poor_analogues(self):
        recent=self.m['history'][-7:]
        for row in recent:row['forecast_high_f']=110
        with tempfile.TemporaryDirectory() as tmp:
            store=EvidenceStore(Path(tmp)/'rag.sqlite');store.ingest(self.m['history'])
            old=store.retrieve(self.m,self.now,allow_synthetic=True)
            new=store.retrieve(self.m,self.now,allow_synthetic=True,include_recent=True)
            ids={r['evidence_id'] for r in recent}
            self.assertFalse(ids <= set(old['audit']['selected_ids']))
            self.assertTrue(ids <= set(new['audit']['selected_ids']))
            self.assertEqual(len(new['history']),30)

    def test_composite_rag_record_cannot_precede_comparison_receipts(self):
        f=self.m['forecast']
        row={'evidence_id':'synthetic-composite','kind':'forecast','station':self.m['station'],'date':self.m['date'],
             'published_at':f['issued_at'],'received_at':f['received_at'],'available_at':f['received_at'],
             'synthetic':True,'text':'Synthetic composite','forecast':f}
        with tempfile.TemporaryDirectory() as tmp:
            store=EvidenceStore(Path(tmp)/'rag.sqlite')
            with self.assertRaisesRegex(ValueError,'before a component'):store.ingest([row])
            row['available_at']=max(c['available_at'] for c in f['comparison_models'])
            self.assertEqual(store.ingest([row]),1)

    def test_all_three_llm_arms_receive_new_evidence_ids(self):
        class Spy(FixtureModel):
            def predict(inner,ctx,*args):
                self.assertIn(self.m['forecast']['comparison_models'][0]['evidence_id'],ctx['evidence_ids'])
                return super().predict(ctx,*args)
        for kind in ('fixed_llm','adaptive_llm','polyswarm'):
            model=Spy();c=dict(config(kind),research_protocol=LATEST_VERSION,weather_hypotheses=[])
            r=Strategy(c,model,self.now).decide({self.m['slug']:self.m},[],Account(),self.now)[0]
            self.assertIn('weather_hypotheses',r['audit']['research_diagnostics'])


if __name__=='__main__':unittest.main()
