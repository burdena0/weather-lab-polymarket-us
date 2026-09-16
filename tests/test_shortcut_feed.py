import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from weatherlab.shortcut_feed import ShortcutFeed, validate_export
from weatherlab.disagreement import DisagreementStudy


class ShortcutFeedTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,9,16,12,tzinfo=timezone.utc).timestamp()
        self.payload={'schema_version':1,'source':'apple_shortcuts','station':'KLAX',
            'fetched_at':'2026-09-16T11:59:00+00:00','unit':'F','period':'daily','location':'Los Angeles International Airport',
            'forecasts':[{'date':'2026-09-17','forecast_time':'2026-09-17T00:00:00-07:00','high':77}]}
        self.market={'station':'KLAX','date':'2026-09-17'}

    def test_stale_future_mismatched_units_and_station_rejected(self):
        for field,value in [('fetched_at','2026-09-16T12:01:00Z'),('fetched_at','2026-09-16T10:00:00Z'),
            ('unit','kelvin'),('station','KNYC'),('source','manual'),('period','current')]:
            with self.assertRaises(ValueError):validate_export(dict(self.payload,**{field:value}),'KLAX',self.now)

    def test_duplicate_dates_and_bad_forecast_timestamps_rejected(self):
        raw=copy.deepcopy(self.payload);raw['forecasts']*=2
        with self.assertRaises(ValueError):validate_export(raw,'KLAX',self.now)
        raw=copy.deepcopy(self.payload);raw['forecasts'][0]['forecast_time']='2026-09-18T00:00:00-07:00'
        with self.assertRaises(ValueError):validate_export(raw,'KLAX',self.now)
        raw=copy.deepcopy(self.payload);raw['forecasts'][0]['high']=float('nan')
        with self.assertRaises(ValueError):validate_export(raw,'KLAX',self.now)

    def test_causal_receipt_is_not_refreshed_when_same_file_is_polled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'sync';folder.mkdir();feed=ShortcutFeed(root/'state');feed.configure(str(folder))
            (folder/'KLAX.json').write_text(json.dumps(self.payload),encoding='utf-8')
            (root/'one').mkdir();(root/'two').mkdir()
            with patch('weatherlab.shortcut_feed.time.time',return_value=self.now):a=feed.forecast(self.market,root/'one')
            with patch('weatherlab.shortcut_feed.time.time',return_value=self.now+300):b=feed.forecast(self.market,root/'two')
            self.assertEqual(a['received_at'],self.now)
            self.assertEqual(a['received_at'],b['received_at'])
            self.assertEqual(a['expires_at'],b['expires_at'])
            self.assertEqual(a['high_f'],77)
            self.assertFalse(a['location_verified']);self.assertFalse(a['provenance_authenticated'])
            self.assertEqual(json.loads((root/'two'/'apple-shortcuts.json').read_text())['received_at'],self.now)

    def test_celsius_conversion_missing_day_and_partial_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'sync';folder.mkdir();receipt=root/'receipt';receipt.mkdir()
            feed=ShortcutFeed(root/'state');feed.configure(str(folder));path=folder/'KLAX.json'
            with patch('weatherlab.shortcut_feed.time.time',return_value=self.now):
                with self.assertRaisesRegex(ValueError,'Waiting'):feed.forecast(self.market,receipt)
                path.write_text('{"incomplete":')
                with self.assertRaises(ValueError):feed.forecast(self.market,receipt)
                raw=copy.deepcopy(self.payload);raw['unit']='C';raw['forecasts'][0]['high']=25
                path.write_text(json.dumps(raw))
                with self.assertRaisesRegex(ValueError,'exact daily'):feed.forecast(dict(self.market,date='2026-09-18'),receipt)
                self.assertEqual(feed.forecast(self.market,receipt)['high_f'],77)

    def test_limits_and_folder_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);feed=ShortcutFeed(root/'state')
            with self.assertRaises(ValueError):feed.configure('relative/path')
            with self.assertRaises(ValueError):feed.configure(str(root/'missing'))
            folder=root/'sync';folder.mkdir();feed.configure(str(folder))
            (folder/'KLAX.json').write_bytes(b' '*65537)
            with self.assertRaisesRegex(ValueError,'64 KB'):feed.forecast(self.market,root)

    def test_default_shortcuts_run_never_calls_weatherkit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'sync';folder.mkdir()
            study=DisagreementStudy(root/'study');study.shortcuts.configure(str(folder))
            with patch('weatherlab.disagreement.collect_snapshot',return_value={'apple_mode':'shortcuts','apple':None}) as collect, patch('weatherlab.disagreement.apple_token',side_effect=AssertionError('No WeatherKit permitted')):
                study.start({'station':'KLAX','date':'2026-09-17','duration':1})
                study.thread.join(timeout=3)
                self.assertFalse(study.state()['running'])
                self.assertEqual(collect.call_args.kwargs['apple_mode'],'shortcuts')
                self.assertIs(collect.call_args.kwargs['shortcut_feed'],study.shortcuts)


if __name__=='__main__':unittest.main()
