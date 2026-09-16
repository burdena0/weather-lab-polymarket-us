import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from weatherlab.historical_window import verify_cli,build_window
from weatherlab.historical import run_month
from weatherlab.models import FixtureModel
import test_historical


class HistoricalWindowTests(unittest.TestCase):
    def test_cli_record_suffix_and_exact_station_date(self):
        day=datetime(2026,9,10,tzinfo=timezone.utc)
        raw='CLILAX\n...THE LOS ANGELES INTL AIRPORT CA CLIMATE SUMMARY FOR SEPTEMBER 10 2026...\nTEMPERATURE (F)\n YESTERDAY\n  MAXIMUM         92R 11:07 AM 92 1983\n'
        self.assertEqual(verify_cli(raw,'KLAX',day,92)['observed_maximum_f'],92)
        for station,date,high in [('KSFO',day,92),('KLAX',day,91),('KLAX',day.replace(day=11),92)]:
            with self.assertRaises(ValueError):verify_cli(raw,station,date,high)
        with self.assertRaises(ValueError):verify_cli(raw.replace('92R','MM'),'KLAX',day,92)

    def test_chicago_hyphen_is_not_a_city_substitution(self):
        raw='CLIMDW\nTHE CHICAGO-MIDWAY CLIMATE SUMMARY FOR SEPTEMBER 15 2026\nTEMPERATURE (F)\n MAXIMUM 85 2:56 PM\n'
        self.assertEqual(verify_cli(raw,'KMDW',datetime(2026,9,15,tzinfo=timezone.utc),85)['observed_maximum_f'],85)
        with self.assertRaises(ValueError):verify_cli(raw.replace('CHICAGO-MIDWAY','CHICAGO-OHARE'),'KMDW',datetime(2026,9,15),85)

    def test_frozen_window_and_cloud_arms_return_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);test_historical.HistoricalTests().write_corpus(root,80)
            manifest=json.loads((root/'manifest.json').read_text());manifest.update(station='KLAX',training_start='2026-07-01',training_end='2026-07-31',test_start='2026-08-01',test_end='2026-08-01')
            (root/'manifest.json').write_text(json.dumps(manifest))
            with patch('weatherlab.historical.CloudModel',lambda _:FixtureModel()):
                r=run_month(root,root/'cloud',mode='cloud',allow_assumed=True)
            self.assertEqual(r['validated_model_calls'],7)
            self.assertTrue(all(a['scored']==1 for a in r['arms'].values()))
            self.assertFalse(r['historical_trades_simulated'])
            manifest['training_end']='2026-08-01';(root/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'overlap'):run_month(root,root/'bad',allow_assumed=True)

    def test_download_rejects_unbounded_or_incomplete_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):build_window(Path(tmp)/'bad','KLAX','2026-01-01','2026-03-01')
            with self.assertRaises(ValueError):build_window(Path(tmp)/'bad','OTHER','2026-09-06','2026-09-15')

    def test_billing_error_stops_more_requests(self):
        class Blocked(FixtureModel):
            attempts=0
            def predict(self,*args,**kwargs):
                self.attempts+=1
                raise ValueError('Cloud call failed (HTTP 429 / credit_balance_exhausted)')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);test_historical.HistoricalTests().write_corpus(root,80)
            model=Blocked()
            with patch('weatherlab.historical.CloudModel',lambda _:model):
                r=run_month(root,root/'blocked',mode='cloud',allow_assumed=True)
            self.assertEqual(model.attempts,1)
            self.assertEqual(r['validated_model_calls'],0)
            self.assertIn('credit_balance_exhausted',r['provider_block'])
            self.assertTrue(all(a['skipped']==1 for a in r['arms'].values()))


if __name__=='__main__':unittest.main()
