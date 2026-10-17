"""Geolocated NASA POWER climatic normal for a user-drawn farm polygon.

Applied to *future-season planning* (historical normals), independent of the
unchanged district-centric ML training. No fake future observations.
"""
from __future__ import annotations
import calendar
import requests
from math import isfinite
from .fao56_irrigation import fetch_nasa_monthly_climatology
from .nasa_polygon import polygon_sample_locations, DEFAULT_MAX_SAMPLES
from .regional_climate_cache import monthly_payload


def _season_normal_from_six(months, *, start_year, end_year):
    if len(months) != 6 or [x.month for x in months] != [4,5,6,7,8,9]:
        raise ValueError('Incomplete April–September NASA reference series')
    days = [calendar.monthrange(2001, m.month)[1] for m in months]
    denominator = sum(days)
    return {
        'Apr-Sep temperature, °C':sum(m.tmean_c*n for m,n in zip(months,days))/denominator,
        'Apr-Sep precipitation, mm':sum(m.rainfall_mm_month for m in months),
        'Apr-Sep relative humidity, %':sum(m.rh_pct*n for m,n in zip(months,days))/denominator,
        'Apr-Sep solar radiation, MJ/m²/day':sum(m.solar_mj_m2_day*n for m,n in zip(months,days))/denominator,
        'source':f'NASA POWER Monthly API, climatological normal {start_year}–{end_year}',
        'year':end_year+1,
        'period_start':f'{start_year}-04-01',
        'period_end':f'{end_year}-09-30',
        'partial_season':False,
        'climate_period':'historical climatology for prospective planning',
        'soil_moisture_source':'NASA POWER modelled root-zone wetness; not fertility or soil chemistry',
    }


def fetch_rootzone_wetness_climatology(latitude,longitude,*,start_year=1995,end_year=2025,
                                       request_get=None,timeout=35):
    """NASA monthly GWETROOT for exact climate-grid coordinate, Apr-Sep normal."""
    get=request_get or requests.get
    cached = monthly_payload(latitude, longitude) if request_get is None else None
    if cached is not None:
        return _rootzone_from_payload(cached, start_year=start_year, end_year=end_year)
    response=get('https://power.larc.nasa.gov/api/temporal/monthly/point',
        params={'parameters':'GWETROOT','community':'AG','latitude':latitude,
                'longitude':longitude,'start':start_year,'end':end_year,'format':'JSON'},
        timeout=timeout)
    response.raise_for_status()
    return _rootzone_from_payload(response.json(), start_year=start_year, end_year=end_year)


def _rootzone_from_payload(payload, *, start_year, end_year):
    try:raw=payload['properties']['parameter']['GWETROOT']
    except (KeyError,TypeError) as exc:raise ValueError('Missing NASA POWER GWETROOT climatology') from exc
    months=[]
    for month in range(4,10):
        row=[]
        for year in range(start_year,end_year+1):
            x=raw.get(f'{year}{month:02d}')
            try:x=float(x)
            except (ValueError,TypeError):x=float('nan')
            row.append(x if isfinite(x) and 0<=x<=1 else None)
        missing=[i for i,x in enumerate(row) if x is None]
        if len(missing)>1:raise ValueError('Too many missing NASA root-zone wetness months')
        if missing:
            i=missing[0]
            if i==0 or i==len(row)-1 or row[i-1] is None or row[i+1] is None:
                raise ValueError('NASA root-zone wetness incomplete at endpoints')
            row[i]=(row[i-1]+row[i+1])/2
        months.append(sum(row)/len(row))
    days=[calendar.monthrange(2001,month)[1] for month in range(4,10)]
    return sum(x*d for x,d in zip(months,days))/sum(days)


def fetch_farm_climate_normal(latitude, longitude, *, geometry=None,
                              start_year=1995,end_year=2025,
                              fetch_point=None,fetch_wetness=None,max_samples=DEFAULT_MAX_SAMPLES):
    """Official NASA POWER monthly series from exact user location/polygon.

    For polygon use nominal overlapping cells, area weights and full-coverage
    rule; NEVER fall back to a district centroid or silently drop failed cells.
    """
    if fetch_point is None:
        fetch_point=lambda lat,lon: fetch_nasa_monthly_climatology(
            lat,lon,start_year=start_year,end_year=end_year)
    if fetch_wetness is None:
        fetch_wetness=lambda lat,lon:fetch_rootzone_wetness_climatology(lat,lon,
            start_year=start_year,end_year=end_year)
    if geometry is None:
        coords=[(float(latitude),float(longitude),1.0)]
    else:
        coords=[(p.latitude,p.longitude,p.area_weight) for p in
                polygon_sample_locations(geometry,max_samples=max_samples)]
    rows=[]
    for lat,lon,weight in coords:
        months=fetch_point(lat,lon)
        data=_season_normal_from_six(months,start_year=start_year,end_year=end_year)
        data['Apr-Sep root-zone wetness']=fetch_wetness(lat,lon)
        data['estimated_monthly_values']=[z for x in months for z in x.estimated_values]
        rows.append((data,weight))
    keys=('Apr-Sep temperature, °C','Apr-Sep precipitation, mm',
          'Apr-Sep relative humidity, %','Apr-Sep solar radiation, MJ/m²/day',
          'Apr-Sep root-zone wetness')
    if any(not all(isfinite(float(row[k])) for k in keys) for row,_ in rows):
        raise ValueError('Incomplete NASA POWER climate normal')
    result=dict(rows[0][0])
    for key in keys:
        result[key]=sum(row[key]*weight for row,weight in rows)
    result.update({'estimated_monthly_values':[
        imputed for row,_ in rows for imputed in row.get('estimated_monthly_values',[])],
        'polygon_sample_count':len(coords),
        'polygon_sampling_note':'Nominal NASA meteo grid, area-weighted field footprint; not measured microclimate',
        'source':f'NASA POWER Monthly API, {start_year}–{end_year}, '+
            ('polygon-weighted grid' if geometry is not None else 'user coordinate')})
    return result
