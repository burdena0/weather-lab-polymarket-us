import unittest
from weatherlab.profitability import fee, quote_pair, signal, simulate, matches, clean_history, contract_context


class ProfitabilityTests(unittest.TestCase):
    def test_exact_bound_context_is_blind_to_test_label_and_prices(self):
        case=dict(station='KLAX',date='2026-09-06',decision_at=100000,forecast_runtime=99000,
                  forecast_available_at=100000,day_start=100001,forecast_high_f=78,
                  forecast_evidence_id='test-mos',forecast_product='GFS MOS',actual_high_f=120)
        training=[dict(station='KLAX',date=f'2026-08-{i+1:02}',outcome_published_at=2000,
                       forecast_available_at=1,day_start=1000,forecast_high_f=60,actual_high_f=61) for i in range(10)]
        ctx=contract_context(case,training,dict(lower_f=78,upper_f=79,price=.01))
        self.assertAlmostEqual(ctx['baseline_probability'],10.5/11)
        self.assertEqual(ctx['contract']['station'],'station-A')
        self.assertEqual(ctx['contract']['lower_f'],78)
        self.assertNotIn('actual_high_f',ctx['forecast'])
        self.assertNotIn('price',ctx['contract'])

    def test_exact_contract_bounds(self):
        self.assertTrue(matches(80,{'lower_f':80,'upper_f':81}))
        self.assertTrue(matches(81,{'lower_f':80,'upper_f':81}))
        self.assertFalse(matches(82,{'lower_f':80,'upper_f':81}))
        self.assertTrue(matches(79,{'lower_f':None,'upper_f':79}))

    def test_quotes_do_not_use_future_for_decision(self):
        point=lambda at:dict(timestamp=at,yes_display_price=.3,no_display_price=.72)
        before,after=quote_pair([point(990),point(1001),point(1300)],1000)
        self.assertEqual(before['timestamp'],990)
        self.assertEqual(after['timestamp'],1300)
        with self.assertRaisesRegex(ValueError,'Missing'): quote_pair([point(699),point(1300)],1000)
        with self.assertRaisesRegex(ValueError,'Missing'): quote_pair([point(990),point(1481)],1000)

    def test_conflicting_same_second_updates_are_omitted(self):
        rows,count=clean_history({'history':[dict(timestamp=1,longPrice=.2,shortPrice=.9),dict(timestamp=1,longPrice=.3,shortPrice=.9),dict(timestamp=2,longPrice=.4,shortPrice=.7)]},0,3)
        self.assertEqual(count,1)
        self.assertEqual([r['timestamp'] for r in rows],[2])

    def test_fee_rounding_and_no_market_mid_edge(self):
        self.assertEqual(fee(1000,.5),15)
        self.assertEqual(fee(1,.5),.02)
        self.assertIsNone(signal(.49,dict(yes_display_price=.5,no_display_price=.52)))

    def test_no_recycling_before_settlement_and_costs(self):
        rows=[]
        for i in range(12):
            rows.append(dict(key=str(i),slug=str(i),decision_at=1000,probability=.99,
                             decision_quote=dict(timestamp=1000,yes_display_price=.3,no_display_price=.72),
                             execution_quote=dict(timestamp=1300,yes_display_price=.3,no_display_price=.72),
                             yes_payout=1,settled_at=2000))
        r=simulate(rows,.02,1,10)
        self.assertEqual(r['trades'],6)
        self.assertEqual(r['skips']['cash_reserve_or_minimum_size'],6)
        self.assertAlmostEqual(r['capital_deployed'],9.68)
        self.assertAlmostEqual(r['trading_pnl'],19.32)
        self.assertAlmostEqual(r['net_after_all_costs'],8.32)
        self.assertEqual(len(r['settled_pnl_curve']),6)

    def test_no_trade_has_zero_pnl_but_nonzero_expense(self):
        r=simulate([],0,2,10)
        self.assertEqual(r['trading_pnl'],0)
        self.assertIsNone(r['win_rate'])
        self.assertEqual(r['net_after_all_costs'],-12)

    def test_losing_account_stops_at_reserve(self):
        rows=[dict(key=str(i),slug=str(i),decision_at=1000+i*1000,probability=.99,
                   decision_quote=dict(timestamp=1000+i*1000,yes_display_price=.3,no_display_price=.72),
                   execution_quote=dict(timestamp=1300+i*1000,yes_display_price=.3,no_display_price=.72),
                   yes_payout=0,settled_at=1500+i*1000) for i in range(20)]
        r=simulate(rows,.02,0,0)
        self.assertGreaterEqual(50+r['trading_pnl'],40)
        self.assertEqual(r['wins'],0)
        self.assertGreater(r['skips']['cash_reserve_or_minimum_size'],0)

    def test_settled_wins_release_capital(self):
        rows=[dict(key=str(i),slug=str(i),decision_at=1000+i*1000,probability=.99,
                   decision_quote=dict(timestamp=1000+i*1000,yes_display_price=.3,no_display_price=.72),
                   execution_quote=dict(timestamp=1300+i*1000,yes_display_price=.3,no_display_price=.72),
                   yes_payout=1,settled_at=1500+i*1000) for i in range(20)]
        r=simulate(rows,.02,0,0)
        self.assertEqual(r['trades'],20)
        self.assertAlmostEqual(r['trading_pnl'],66.6)


if __name__=='__main__': unittest.main()
