"""Bounded prospective GFS/IFS collection. Provider grids are not station observations."""
import math
import urllib.parse
from datetime import datetime, timezone
from .core import number, stamp, digest

MODELS = {'gfs_global': 'NOAA GFS', 'ecmwf_ifs025': 'ECMWF IFS'}
VARIABLES = {'temperature_2m': ('°F', -150, 160), 'cloud_cover': ('%', 0, 100),
             'wind_speed_10m': ('mp/h', 0, 250), 'wind_direction_10m': ('°', 0, 360)}


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 12742*math.asin(min(1, math.sqrt(h)))


def decode(raw, market, lat, lon, received, hashed, url):
    start, end = stamp(market['day_start']), stamp(market['close_at'])
    received = number(received)
    if end-start not in (82800, 86400, 90000) or received >= start:
        raise ValueError('Comparison requires a complete future venue weather day')
    if raw.get('utc_offset_seconds') != 0:
        raise ValueError('Comparison times must be UTC')
    grid = [number(raw['latitude']), number(raw['longitude'])]
    if not -90 <= grid[0] <= 90 or not -180 <= grid[1] <= 180 or distance_km((lat,lon),grid)>50:
        raise ValueError('Comparison grid is too far from requested station coordinates')
    units, hourly = raw['hourly_units'], raw['hourly']
    times = [number(t) for t in hourly['time']]
    if units.get('time') != 'unixtime' or not 1 <= len(times) <= 72 or any(b-a != 3600 for a,b in zip(times,times[1:])):
        raise ValueError('Malformed or oversized comparison time axis')
    indices = [i for i,t in enumerate(times) if start <= t < end]
    if [times[i] for i in indices] != list(range(int(start),int(end),3600)):
        raise ValueError('Comparison forecast has incomplete venue-day coverage')
    result=[]
    for model, family in MODELS.items():
        values={}
        for variable, (unit, lo, hi) in VARIABLES.items():
            key=variable+'_'+model
            if units.get(key)!=unit or len(hourly[key])!=len(times):
                raise ValueError('Comparison variable unit/length mismatch')
            values[variable]=[number(hourly[key][i]) for i in indices]
            if any(not lo <= x <= hi for x in values[variable]):
                raise ValueError('Comparison variable out of bounds')
        rows=[{'at':times[i],**{k:v[j] for k,v in values.items()}} for j,i in enumerate(indices)]
        result.append({'model':model,'family':family,'provider':'Open-Meteo','station':market['station'],
            'date':market['date'],'day_start':start,'day_end':end,'requested_coordinates':[lat,lon],
            'provider_grid_coordinates':grid,'grid_distance_km':distance_km((lat,lon),grid),
            'issued_at':None,'received_at':received,'available_at':received,
            'availability_policy':'Actual first receipt, latest stitched forecast. Model initialization not provided.',
            'evidence_id':'model-'+digest([hashed,model,market['station'],market['date'],received])[:32],
            'source_url':url,'high_f':max(values['temperature_2m']),'hourly':rows,
            'attribution':'Open-Meteo / NOAA GFS / ECMWF IFS, CC BY 4.0',
            'limitations':'Distinct model families can share observations and errors. Gridded hourly maxima are not final station CLI maxima.'})
    return result


def collect(source, market, lat, lon):
    start,end=stamp(market['day_start']),stamp(market['close_at'])
    query={'latitude':lat,'longitude':lon,'models':','.join(MODELS),'hourly':','.join(VARIABLES),
           'temperature_unit':'fahrenheit','wind_speed_unit':'mph','timeformat':'unixtime','timezone':'GMT',
           'start_date':datetime.fromtimestamp(start,timezone.utc).date().isoformat(),
           'end_date':datetime.fromtimestamp(end-1,timezone.utc).date().isoformat()}
    url='https://api.open-meteo.com/v1/forecast?'+urllib.parse.urlencode(query)
    raw,received,hashed=source.get(url)
    return decode(raw,market,lat,lon,received,hashed,url)
