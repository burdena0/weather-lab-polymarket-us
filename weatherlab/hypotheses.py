"""Predeclared weather-entry hypotheses, separate from probability estimation and exits."""
import math
import statistics
from datetime import date, timedelta
from .core import number, stamp
from .weather_models import MODELS, VARIABLES

HYPOTHESES = ('model_consensus', 'peak_timing', 'regime_change', 'recent_trend_break')
GUIDANCE = """
This run also supplies distinct NOAA GFS and ECMWF IFS forecast series via Open-Meteo.
Their errors can be correlated, and their initialization timestamps are unavailable.
Use their actual receipt times, exact requested station coordinates and full venue day.
They are gridded, possibly interpolated forecasts, not station CLI observations.
Inspect model high-temperature spread, peak-window disagreement and cloud/wind changes.
A recent seven-day temperature mean is a persistence reference, not a climate normal.
Do not infer calibrated probability or win rate from model agreement. The NWS residual
baseline does not calibrate GFS/IFS errors. Hypothesis thresholds are unvalidated.
Entry filters and position reductions are enforced outside the model. Do not override them.
"""


def selected(config):
    flags = config.get('weather_hypotheses', list(HYPOTHESES))
    if not isinstance(flags, list) or any(not isinstance(f,str) or f not in HYPOTHESES for f in flags) or len(flags)!=len(set(flags)):
        raise ValueError('weather_hypotheses must be a unique list of supported hypothesis names')
    return flags


def compare(m, ctx, now, flags):
    f = ctx['forecast']
    models = f.get('comparison_models', [])
    if len(models)!=2 or {r.get('model') for r in models} != set(MODELS):
        raise ValueError('V2 requires both GFS and ECMWF forecasts, no silent single-model fallback')
    start,end=stamp(m['day_start']),stamp(m['close_at'])
    if not 0 < (start-now)/3600 <= 120:
        raise ValueError('V2 forecast horizon must be before the weather day and within 120 hours')
    expected=list(range(int(start),int(end),3600))
    summaries=[]
    for model in sorted(models,key=lambda r:r['model']):
        if (model['station'], model['date'], stamp(model['day_start']), stamp(model['day_end'])) != (m['station'], m['date'], start, end):
            raise ValueError('Comparison station/day/interval mismatch')
        if model['family'] != MODELS[model['model']] or model['provider']!='Open-Meteo':
            raise ValueError('Unknown comparison family/provider')
        if model['requested_coordinates'] != f['station_coordinates']:
            raise ValueError('Comparison requested location differs from NWS station coordinates')
        received,available=stamp(model['received_at']),stamp(model['available_at'])
        if not received <= available <= now or now-received > 900 or received >= start:
            raise ValueError('Stale, future or post-day comparison receipt')
        if model.get('issued_at') is not None and stamp(model['issued_at'])>received:
            raise ValueError('Comparison received before issuance')
        rows=model['hourly']
        if len(rows)!=len(expected) or [number(r['at']) for r in rows]!=expected:
            raise ValueError('Incomplete or unordered comparison hourly path')
        for r in rows:
            for k,(_,lo,hi) in VARIABLES.items():
                if r[k] is None or not lo <= number(r[k]) <= hi:
                    raise ValueError('Invalid comparison weather value')
        temps=[number(r['temperature_2m']) for r in rows]
        high=max(temps)
        if high!=number(model['high_f']) or not model.get('evidence_id'):
            raise ValueError('Comparison maximum/evidence mismatch')
        peak=[r['at'] for r in rows if high-number(r['temperature_2m']) <= .5]
        changes=[]
        for a,b in zip(rows,rows[3:]):
            turn=abs(number(b['wind_direction_10m'])-number(a['wind_direction_10m']))%360
            turn=min(turn,360-turn) if min(number(a['wind_speed_10m']),number(b['wind_speed_10m']))>=5 else 0
            changes.append((abs(number(b['temperature_2m'])-number(a['temperature_2m'])),
                            abs(number(b['cloud_cover'])-number(a['cloud_cover'])),turn))
        regime=any(temp>=6 or (cloud>=40 and turn>=60) for temp,cloud,turn in changes)
        rounded=math.floor(high+.5)
        inside=(m['lower_f'] is None or rounded>=m['lower_f']) and (m['upper_f'] is None or rounded<=m['upper_f'])
        summaries.append({'model':model['model'],'family':model['family'],'high_f':high,'point_forecast_side':'YES' if inside else 'NO',
            'peak_window':peak,'regime_change':regime,'max_3h_temperature_change_f':max(c[0] for c in changes),
            'max_3h_cloud_change_pp':max(c[1] for c in changes),'max_3h_wind_turn_deg':max(c[2] for c in changes),
            'evidence_id':model['evidence_id'],'received_at':received,'issued_at':model.get('issued_at')})
    a,b=summaries
    # Symmetric maximum distance between peak-window sets, in hours.
    peak_gap=max(max(min(abs(x-y) for y in b['peak_window']) for x in a['peak_window']),
                 max(min(abs(y-x) for x in a['peak_window']) for y in b['peak_window']))/3600
    spread=abs(a['high_f']-b['high_f'])
    recent=sorted(ctx['history'],key=lambda r:r['date'])[-7:]
    reference=None
    if len(recent)==7:
        last=date.fromisoformat(recent[-1]['date'])
        if 1 <= (date.fromisoformat(m['date'])-last).days <= 3 and [r['date'] for r in recent] == [(last-timedelta(days=i)).isoformat() for i in range(6,-1,-1)]:
            reference=statistics.mean(number(r['actual_high_f']) for r in recent)
    delta=None if reference is None else number(f['high_f'])-reference
    regime=any(r['regime_change'] for r in summaries)
    blocks=[];sides=['YES','NO'];margin=0.;factor=1.
    if 'model_consensus' in flags:
        if spread>3 or a['point_forecast_side']!=b['point_forecast_side']:
            blocks.append('Model consensus: spread above 3 F or opposing point-forecast sides')
        else:
            sides=[a['point_forecast_side']]
    if 'peak_timing' in flags and peak_gap>3:
        blocks.append('Peak timing: forecast peak windows differ by more than 3 hours')
    if 'regime_change' in flags and regime:
        margin=.02;factor=.5
    if 'recent_trend_break' in flags:
        if reference is None:
            blocks.append('Recent trend: need seven consecutive causal station days ending within three days of target')
        elif abs(delta)>=5 and not all((r['high_f']-reference)*delta>0 for r in summaries):
            blocks.append('Recent trend: NWS shift of at least 5 F lacks directional model agreement')
    if blocks: sides=[]
    return {'selected_hypotheses':list(flags),'models':summaries,'model_high_spread_f':spread,
            'peak_window_distance_hours':peak_gap,'regime_change':regime,
            'recent_seven_day_mean_f':reference,'nws_minus_recent_mean_f':delta,
            'recent_reference_ids':[r['evidence_id'] for r in recent] if reference is not None else [],
            'entry_policy':{'allowed_sides':sides,'extra_edge':margin,'size_factor':factor,'blocks':blocks},
            'threshold_status':'Frozen, uncalibrated research hypotheses. Agreement is not probability.',
            'independence':'Two distinct model families, shared provider and potentially correlated errors'}
