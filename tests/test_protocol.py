import copy
import tempfile
import unittest
from pathlib import Path
from weatherlab.core import Account, context
from weatherlab.engine import validate_config
from weatherlab.fixtures import sample, config, WALLET
from weatherlab.models import FixtureModel
from weatherlab.protocol import VERSION, AVAILABLE_AT, diagnostics
from weatherlab.strategies import Strategy, STRATEGIES, route
from weatherlab.sources import PublicSource


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        data, _ = sample()
        self.now = AVAILABLE_AT+60
        self.m = copy.deepcopy(data['frames'][0]['markets'][0])
        self.m.update(metadata_received=self.now, day_start=self.now+3600, close_at=self.now+90000)
        self.m['book'].update(received=self.now, source_at=self.now)
        f = self.m['forecast']
        f.update(issued_at=self.now-60, received_at=self.now-30, day_start=self.now+3600, day_end=self.now+90000)
        f['hourly'] = [{'startTime':self.now+(i+1)*3600, 'endTime':self.now+(i+2)*3600,
                        'temperature':75 if i == 0 else 70, 'temperatureUnit':'F',
                        'windSpeed':'5 mph', 'windDirection':'N', 'shortForecast':'Clear'} for i in range(24)]

    def test_all_four_reject_pre_review_without_model_calls(self):
        for kind in STRATEGIES:
            model = FixtureModel()
            c = dict(config(kind), research_protocol=VERSION)
            result = Strategy(c, model, 0).decide({}, [], Account(), AVAILABLE_AT-1)
            self.assertIn('unavailable', result[0]['skip'])
            self.assertEqual(model.calls, [])

    def test_three_llm_arms_receive_and_audit_diagnostics(self):
        class Spy(FixtureModel):
            def predict(inner, ctx, *args):
                self.assertEqual(ctx['research_diagnostics']['version'], VERSION)
                self.assertIsNone(ctx['research_diagnostics']['independent_model_agreement'])
                return super().predict(ctx, *args)
        for kind in ('fixed_llm', 'adaptive_llm', 'polyswarm'):
            result = Strategy(dict(config(kind), research_protocol=VERSION), Spy(), self.now).decide(
                {self.m['slug']:self.m}, [], Account(), self.now)
            self.assertEqual(result[0]['audit']['research_diagnostics']['peak_times'], [self.now+3600])
            self.assertEqual(result[0]['research_protocol'], VERSION)

    def test_bad_path_or_interval_rejected_before_paid_call(self):
        for mutation in ('missing', 'hole', 'wrong_high', 'wrong_interval'):
            m = copy.deepcopy(self.m)
            if mutation == 'missing': m['forecast'].pop('hourly')
            if mutation == 'hole': m['forecast']['hourly'].pop(8)
            if mutation == 'wrong_high': m['forecast']['high_f'] = 76
            if mutation == 'wrong_interval': m['forecast']['day_end'] += 1
            model = FixtureModel()
            result = Strategy(dict(config('fixed_llm'), research_protocol=VERSION), model, self.now).decide(
                {m['slug']:m}, [], Account(), self.now)
            self.assertIn('skip', result[0])
            self.assertEqual(model.calls, [])

    def test_full_day_peak_and_sensitivity_use_existing_residuals(self):
        ctx = context(self.m, self.now)
        d = diagnostics(self.m, ctx, self.now)
        self.assertEqual(d['half_degree_stress_probabilities']['base'], ctx['baseline_probability'])
        self.assertEqual(d['peak_times'], [self.now+3600])
        self.assertEqual(d['largest_hourly_change_f'], 5)
        self.assertEqual(d['distance_to_rounding_boundary_f'], .5)
        self.assertEqual(d['weather_model_families'], ['NWS hourly grid'])

    def test_adaptive_route_responds_to_stress_without_changing_baseline(self):
        ctx = context(self.m, self.now)
        self.assertEqual(route(ctx)[0], 'medium')
        ctx['research_diagnostics'] = dict(diagnostics(self.m, ctx, self.now), half_degree_probability_span=.3)
        self.assertEqual(route(ctx)[0], 'large')

    def test_basket_rejects_different_weather_days_without_forecasts(self):
        a, b = copy.deepcopy(self.m), copy.deepcopy(self.m)
        a.update(lower_f=None, upper_f=75, forecast=None)
        b.update(id='second', slug='second', lower_f=76, upper_f=None, forecast=None,
                 day_start=b['day_start']+3600, close_at=b['close_at']+3600)
        b['book']['slug'] = 'second'
        c = dict(config('wallet_control'), research_protocol=VERSION, control_mode='arbitrage')
        model = FixtureModel()
        result = Strategy(c, model, self.now).decide({a['slug']:a,b['slug']:b}, [], Account(), self.now)
        self.assertIn('different settlement intervals', result[0]['skip'])
        self.assertEqual(model.calls, [])

    def test_control_can_copy_without_forecast_or_model(self):
        data, _ = sample()
        signal = data['frames'][0]['signals'][0]
        signal.update(trade_at=self.now, received_at=self.now)
        self.m['forecast'] = None
        model = FixtureModel()
        c = dict(config('wallet_control'), research_protocol=VERSION, reference_wallet=WALLET)
        result = Strategy(c, model, self.now).decide({self.m['slug']:self.m}, [signal], Account(), self.now)
        self.assertIn('legs', result[0])
        self.assertEqual(result[0]['research_protocol'], VERSION)
        self.assertEqual(model.calls, [])

    def test_collector_retains_hourly_weather_fields(self):
        class Source(PublicSource):
            def get(inner, url):
                if '/stations/' in url:
                    return {'properties':{'stationIdentifier':'KNYC'},'geometry':{'coordinates':[-74,41]}}, self.now, 'a'
                if '/points/' in url:
                    return {'properties':{'forecastHourly':'https://api.weather.gov/gridpoints/test/forecast/hourly'}}, self.now, 'b'
                return {'properties':{'periods':self.m['forecast']['hourly'],'updateTime':self.now-60}}, self.now, 'c'*64
        with tempfile.TemporaryDirectory() as tmp:
            f = Source(Path(tmp)).forecast(self.m)
        self.assertEqual(f['hourly'], self.m['forecast']['hourly'])
        self.assertEqual(f['high_f'], 75)

    def test_unknown_version_refused_and_old_config_preserved(self):
        validate_config(config('fixed_llm'))
        with self.assertRaisesRegex(ValueError, 'Unknown research protocol'):
            validate_config(dict(config('fixed_llm'), research_protocol='future'))


if __name__ == '__main__':
    unittest.main()
