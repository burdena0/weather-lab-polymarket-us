"""Reviewed source hypotheses, never automatic policy changes or profit claims."""
from datetime import datetime, timezone
from .core import number

ARTICLE = 'https://www.tradetheoutcome.com/polymarket-weather-strategy/'
TOPICS = [
    ('joint_bins', 'Joint temperature-bin probabilities',
     'Test a calibrated station-day distribution across all contract bins.',
     'A point forecast is insufficient. Fit calibration only on prior data; bins from one day share one outcome.'),
    ('partial_ladders', 'Partial ladder expected payout',
     'Test adjacent-bin baskets using aggregate probability and executable cost.',
     'A partial ladder can lose its entire cost. Cheap baskets and a high hit rate do not establish positive expected profit.'),
    ('release_latency', 'Forecast revision timing',
     'Test repricing after newly received forecast updates.',
     'No fixed stale-price window is assumed. Require receipt timestamps and delayed depth; displayed prices do not prove fills.'),
    ('model_weighting', 'Forecast-source weighting',
     'Test source weights fitted to earlier station-specific forecast errors.',
     'Keep fitting outside evaluation dates. Correlated model errors and small samples can defeat apparent diversification.'),
    ('seasonal_regimes', 'Seasonal generalization',
     'Evaluate performance across different seasonal weather regimes.',
     'Season alone cannot authorize larger positions. Report losing periods and all tested variants; retain reserve limits.'),
]


def seed(now):
    from .sources import STATIONS
    day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    return [dict(evidence_id='outcome-guide-v1-'+station+'-'+ident, kind='strategy_card',
        schema_version=1, strategy_id='outcome_'+ident, revision=1, station=station,
        date=day, venue='polymarket_us', source='NWS_CLI', published_at=now,
        received_at=now, available_at=now, expires_at=now+90*86400, source_url=ARTICLE,
        synthetic=False, status='hypothesis', title=title, text=text,
        limitations=limits, profitability_established=False)
        for station in STATIONS for ident, title, text, limits in TOPICS]


def ladder_scenario(probabilities, costs):
    """One YES share per mutually exclusive chosen bin. Analytical, no fills."""
    if len(probabilities) != len(costs) or not 1 <= len(costs) <= 100:
        raise ValueError('Require matching nonempty lists, at most 100 bins')
    ps, cs = [number(p) for p in probabilities], [number(c) for c in costs]
    if any(not 0 <= p <= 1 for p in ps) or sum(ps) > 1+1e-10 or any(c < 0 for c in cs):
        raise ValueError('Invalid disjoint-bin probabilities or all-in costs')
    probability, cost = min(1, sum(ps)), sum(cs)
    return {'coverage_probability':probability, 'cost':cost,
            'expected_pnl':probability-cost, 'pnl_if_covered':1-cost,
            'pnl_if_outside':-cost, 'guaranteed_profit':False,
            'assumptions':'Disjoint bins, equal one-share quantities, supplied all-in fill costs; no liquidity validation.'}
