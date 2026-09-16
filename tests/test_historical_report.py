import json
from pathlib import Path
import tempfile
import unittest
from weatherlab.core import digest
from weatherlab.historical_report import summarize


class HistoricalReportTests(unittest.TestCase):
    def test_shared_case_filter_and_chain_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for mode,folder,arms in [('baseline','baseline-KLAX',['statistical_baseline']),
                                     ('cloud','cloud-KLAX',['fixed_llm','adaptive_llm','polyswarm_weather_ablation'])]:
                p=root/folder;p.mkdir();predictions=[];scores=[];tip='0'*64
                for arm in arms:
                    for day in ['2026-09-06','2026-09-07']:
                        row={'case_id':day,'arm':arm,'calls':[]}
                        if arm=='adaptive_llm' and day.endswith('07'):row['error']='Model abstained'
                        else:
                            row['probability']=.8
                            scores.append({'case_id':day,'arm':arm,'p':.8,'y':1,'brier':.04})
                        tip=digest({'previous':tip,'record':row});row['chain_hash']=tip;predictions.append(row)
                (p/'predictions.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in predictions))
                (p/'scores.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in scores))
                (p/'summary.json').write_text(json.dumps({'mode':mode,'model_cost_or_reserved_usd':0,'arms':{},'prediction_chain_tip':tip,'corpus_hash':'fixture'}))
            report=summarize(root,'cloud-')
            self.assertEqual(report['paired_station_days'],1)
            self.assertEqual(report['status'],'partial')
            self.assertEqual([a['scored'] for a in report['arms']],[2,2,1,2])
            self.assertTrue(all(abs(a['paired_brier']-.04)<1e-9 for a in report['arms']))
            score_path=root/'cloud-KLAX'/'scores.jsonl';original=score_path.read_text()
            score_path.write_text(original.replace('0.8','0.9'))
            with self.assertRaisesRegex(ValueError,'committed prediction'):summarize(root,'cloud-')
            score_path.write_text(original)
            path=root/'cloud-KLAX'/'predictions.jsonl'
            path.write_text(path.read_text().replace('0.8','0.9'))
            with self.assertRaisesRegex(ValueError,'chain'):summarize(root,'cloud-')


if __name__=='__main__':unittest.main()
