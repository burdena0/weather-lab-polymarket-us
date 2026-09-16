import copy
import unittest
from weatherlab.profitability import simulate
from weatherlab.profitability_research import candidates, transform, select_on_development


class ProfitPolicyTests(unittest.TestCase):
    def row(self):
        return dict(key='A',slug='a',probability=.9,decision_at=100,
            decision_quote=dict(timestamp=99,yes_display_price=.4,no_display_price=.62),
            execution_quote=dict(timestamp=400,yes_display_price=.89,no_display_price=.12),
            settled_at=1000,yes_payout=1,cost_or_reserved_usd=.12)

    def test_entry_recheck_cancels_stale_edge_and_respects_reserve(self):
        row=self.row()
        old=simulate([row],.02,.12,0)
        new=simulate([row],.02,.12,0,recheck_edge=True)
        self.assertEqual(old['trades'],1);self.assertEqual(new['trades'],0)
        self.assertEqual(new['skips']['edge_lost_before_execution'],1)
        self.assertEqual(new['pnl_after_models'],-.12)

    def test_gate_never_uses_final_label_or_delayed_price(self):
        v=next(x for x in candidates() if x['id']=='fixed_llm__cheap_gate')
        row=self.row();baseline={'A':.4}
        first=transform([row],v,baseline)
        changed=copy.deepcopy(row);changed['yes_payout']=0;changed['execution_quote']['yes_display_price']=.01
        second=transform([changed],v,baseline)
        self.assertEqual(first[1:],second[1:]);self.assertEqual(first[1:],(0.,0,1))
        self.assertEqual(first[0][0]['error'],second[0][0]['error'])
        self.assertIn('probability',row)

    def test_consulted_failures_keep_cost_and_failed_calls_not_resurrected(self):
        v=next(x for x in candidates() if x['id']=='fixed_llm__cheap_gate')
        row=self.row();row['error']='model_failed';row.pop('probability')
        rows,cost,consulted,withheld=transform([row],v,{'A':.9})
        self.assertEqual(cost,.12);self.assertEqual(consulted,1);self.assertEqual(withheld,0)
        self.assertIn('error',rows[0]);self.assertNotIn('probability',rows[0])

    def test_selection_ignores_evaluation_and_uses_stressed_development(self):
        def r(ident,pnl):
            return dict(variant={'id':ident},development={'modeled_model_cost':0,
                'scenarios':[dict(slippage_per_share=.02,pnl_after_models=pnl),
                             dict(slippage_per_share=.05,pnl_after_models=pnl)]},evaluation={'pnl':999})
        rows=[r('cash',0),r('losing',-1)]
        self.assertEqual(select_on_development(rows),'cash')
        rows[1]['evaluation']['pnl']=1e9
        self.assertEqual(select_on_development(rows),'cash')

    def test_blend_is_bounded_and_controls_capital_not_changed(self):
        v=next(x for x in candidates() if x['id']=='fixed_llm__blend')
        rows,cost,_,_=transform([self.row()],v,{'A':.9})
        self.assertAlmostEqual(rows[0]['probability'],.645)
        self.assertEqual(cost,.12)
        self.assertEqual(len({v['id'] for v in candidates()}),len(candidates()))
