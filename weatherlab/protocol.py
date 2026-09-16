"""Versioned, bounded weather research diagnostics. No trading or network authority."""
import math
from .core import number, stamp

VERSION = 'weather-methods-20260916-v1'
AVAILABLE_AT = stamp('2026-09-16T17:07:01Z')
MODEL_GUIDANCE = """
For the weather-methods protocol, evaluate the supplied research diagnostics.
Use the exact station, full contract weather-day interval and final NWS CLI source.
An expected afternoon peak is not a settlement window. Grid forecasts are not CLI.
Inspect the hourly temperature path and supplied wind/condition descriptions, without
inventing cloud fractions, fronts, observations or additional forecast models.
Do not estimate front arrival by dividing distance by surface wind speed.
Independent model agreement is not a calibrated probability; websites and LLM personas
are not independent weather models. With one model family, report that limitation.
Consider residual-based bin probability, sampling error, boundary sensitivity and
forecast revisions. The plus/minus 0.5 F sensitivity test is a stress scenario, not
an uncertainty interval. Do not force a 50% probability near a rounding boundary.
Do not use a video's historical winning example or claimed accuracy as evidence of
this forecast's probability. Explain material missing inputs and abstain if needed.
"""


def check_version(version):
    if version not in (None, VERSION):
        raise ValueError('Unknown research protocol version')


def require_available(now):
    if number(now) < AVAILABLE_AT:
        raise ValueError('Research protocol unavailable at decision time; use a separately frozen earlier protocol')


def settlement_window(m):
    start, end = stamp(m['day_start']), stamp(m['close_at'])
    if end-start not in (23*3600, 24*3600, 25*3600):
        raise ValueError('Research protocol requires an explicit full venue weather day')
    return start, end


def diagnostics(m, ctx, now):
    """Computed from the same eligible forecast/history; no market prices or outcomes."""
    require_available(now)
    from .sources import full_day_periods
    f = ctx['forecast']
    settlement_window(m)
    if not 23 <= len(f.get('hourly', [])) <= 25:
        raise ValueError('Research protocol requires 23-25 hourly forecast periods')
    periods, start, end = full_day_periods(f.get('hourly', []), m)
    if stamp(f['day_start']) != start or stamp(f['day_end']) != end:
        raise ValueError('Forecast interval does not match contract interval')
    temps = [number(p['temperature']) for p in periods]
    high = number(f['high_f'])
    if high != max(temps):
        raise ValueError('Forecast high differs from hourly path')
    projected = [high + number(r['actual_high_f'])-number(r['forecast_high_f']) for r in ctx['history']]
    def probability(shift):
        def inside(t):
            rounded = math.floor(t + shift + .5)
            return (m['lower_f'] is None or rounded >= m['lower_f']) and (m['upper_f'] is None or rounded <= m['upper_f'])
        return (sum(inside(t) for t in projected)+.5)/(len(projected)+1)
    ps = [probability(shift) for shift in (-.5, 0, .5)]
    boundaries = [b for b in (None if m['lower_f'] is None else m['lower_f']-.5,
                              None if m['upper_f'] is None else m['upper_f']+.5) if b is not None]
    return {'version': VERSION, 'available_at': AVAILABLE_AT,
            'station': m['station'], 'day_start': start, 'day_end': end,
            'horizon_to_day_start_hours': (start-now)/3600,
            'peak_times': [p['startTime'] for p in periods if number(p['temperature']) == high],
            'hourly_range_f': max(temps)-min(temps),
            'largest_hourly_change_f': max(abs(b-a) for a,b in zip(temps,temps[1:])),
            'distance_to_rounding_boundary_f': min([abs(high-b) for b in boundaries] or [310]),
            'half_degree_stress_probabilities': dict(zip(('minus', 'base', 'plus'), ps)),
            'half_degree_probability_span': max(ps)-min(ps),
            'weather_model_families': ['NWS hourly grid'],
            'independent_model_agreement': None,
            'missing_inputs': ['independent numerical model forecast', 'calibrated ensemble probabilities'],
            'interpretation': 'Heuristic diagnostics only; no accuracy or profit claim. Full venue day retained.'}
