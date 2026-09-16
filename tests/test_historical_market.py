import unittest
from weatherlab.historical_market import validate_history


class HistoricalMarketTests(unittest.TestCase):
    def test_price_history_preserves_spread_and_filters_future(self):
        rows={'history':[{'timestamp':10,'longPrice':.6,'shortPrice':.45},
                         {'timestamp':20,'longPrice':.7,'shortPrice':.4}]}
        result=validate_history(rows,0,15)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['yes_display_price'],.6)
        self.assertEqual(result[0]['no_display_price'],.45)
        self.assertNotIn('quantity',result[0])

    def test_invalid_price_and_duplicate_time_rejected(self):
        row={'timestamp':10,'longPrice':.6,'shortPrice':.45}
        with self.assertRaises(ValueError):validate_history({'history':[row,row]},0,20)
        for value in (-.1,1.1,float('nan')):
            with self.assertRaises(ValueError):validate_history({'history':[dict(row,longPrice=value)]},0,20)


if __name__=='__main__':unittest.main()
