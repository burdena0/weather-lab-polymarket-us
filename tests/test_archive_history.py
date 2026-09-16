import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from weatherlab.archive_history import ArchiveHistory, window
from weatherlab.core import stamp


class ArchiveHistoryTests(unittest.TestCase):
    def test_weeks_use_completed_station_standard_day(self):
        # At 01 UTC LA's local standard date is still the previous day.
        self.assertEqual(window('KLAX',1,stamp('2026-09-16T01:00:00Z')),('2026-09-08','2026-09-14'))
        self.assertEqual(window('KNYC',2,stamp('2026-09-16T20:00:00Z')),('2026-09-02','2026-09-15'))
        for weeks in (0,5,True,1.5):
            with self.assertRaises(ValueError):window('KNYC',weeks,0)

    def test_job_bounded_no_training_no_apple_and_serialized(self):
        done=threading.Event();entered=threading.Event()
        def build(*args,**kwargs):
            self.assertEqual(kwargs,{'training_days':0});entered.set();done.wait(2)
            return {'test_days':6,'errors':[{'date':'one missing day'}]}
        with tempfile.TemporaryDirectory() as d,patch('weatherlab.archive_history.build_window',build):
            a=ArchiveHistory(d);a.start('KNYC',1);self.assertTrue(entered.wait(1))
            with self.assertRaises(ValueError):a.start('KLAX',1)
            done.set();a.thread.join(3);r=a.state()
            self.assertFalse(r['running']);self.assertEqual(r['latest']['status'],'partial')
            self.assertEqual(r['latest']['apple_records'],0);self.assertFalse(r['apple_history_available'])

    def test_restart_reports_interrupted_job(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'latest.json').write_text(json.dumps({'status':'running'}),encoding='utf-8')
            self.assertEqual(ArchiveHistory(d).state()['latest']['status'],'interrupted')
