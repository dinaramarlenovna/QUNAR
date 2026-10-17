"""FAO-56 monthly ET0, ETc and optional irrigation scenario for QUNAR.

This is a *supplemental* water-balance scenario, not an official Kazakh
irrigation norm, a prediction of farm water withdrawals, or a replacement for
108-NQ. A complete crop calculation requires user-specified six monthly Kc
coefficients (phenology), an explicitly chosen effective-rainfall assumption
and an application efficiency. If any are absent, report ET0 only.

Sources: FAO Irrigation and Drainage Paper 56 chapters 2-6;
FAO Irrigation Water Management Training Manual 3, chapter 4;
NASA POWER monthly point API (meteorology and solar data).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, replace
from datetime import date
from math import acos, cos, exp, isfinite, pi, sin, sqrt, tan
from typing import Mapping

import requests

FAO_56_URL = 'https://www.fao.org/4/x0490e/x0490e06.htm'
FAO_RAIN_URL = 'https://www.fao.org/4/S2022E/s2022e08.htm'
NASA_MONTHLY_URL = 'https://power.larc.nasa.gov/api/temporal/monthly/point'
NASA_VARS = ('T2M', 'T2M_MAX', 'T2M_MIN', 'RH2M', 'WS2M', 'PS',
             'ALLSKY_SFC_SW_DWN', 'PRECTOTCORR')
SEASON = (4, 5, 6, 7, 8, 9)
MONTH_NAMES = ('Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep')

@dataclass(frozen=True)
class MonthlyWeather:
    month: int
    tmean_c: float
    tmax_c: float
    tmin_c: float
    rh_pct: float
    wind_m_s: float
    pressure_kpa: float
    solar_mj_m2_day: float
    rainfall_mm_month: float
    estimated_values: tuple[str, ...] = ()


def _finite(v, label):
    try: x = float(v)
    except (ValueError, TypeError): raise ValueError(f'Invalid {label}') from None
    if not isfinite(x): raise ValueError(f'Non-finite {label}')
    return x


def validate_weather(w: MonthlyWeather):
    if w.month not in range(1, 13): raise ValueError('Invalid month')
    for k in ('tmean_c','tmax_c','tmin_c','rh_pct','wind_m_s','pressure_kpa',
              'solar_mj_m2_day','rainfall_mm_month'):
        _finite(getattr(w,k), k)
    if not (w.tmin_c <= w.tmean_c <= w.tmax_c): raise ValueError('Invalid Tmax/Tmin/Tmean order')
    if not 0 <= w.rh_pct <= 100: raise ValueError('Relative humidity out of bounds')
    if not 0 <= w.wind_m_s <= 80: raise ValueError('Invalid wind')
    if not 60 <= w.pressure_kpa <= 110: raise ValueError('Pressure must be kPa')
    if not 0 < w.solar_mj_m2_day < 50: raise ValueError('Solar radiation must be MJ/m²/day')
    if not 0 <= w.rainfall_mm_month < 2000: raise ValueError('Invalid monthly precipitation')
    return w


def _es(temp_c):
    return 0.6108 * exp(17.27 * temp_c / (temp_c + 237.3))


def extraterrestrial_radiation(latitude_deg: float, month: int) -> float:
    """FAO-56 Eq. 21 on representative mid-month day, MJ m^-2 day^-1."""
    lat = _finite(latitude_deg,'latitude')
    if not -70 <= lat <= 70: raise ValueError('Latitude outside monthly FAO calculation support')
    j = date(2001, month, 15).timetuple().tm_yday
    phi = lat*pi/180
    dr = 1 + 0.033*cos(2*pi*j/365)
    delta = 0.409*sin(2*pi*j/365-1.39)
    arg = min(1.0, max(-1.0,-tan(phi)*tan(delta)))
    ws = acos(arg)
    return (24*60/pi)*0.0820*dr*(ws*sin(phi)*sin(delta)+cos(phi)*cos(delta)*sin(ws))


def fao56_et0_mm_day(w: MonthlyWeather, latitude_deg: float, *, soil_heat_mj_m2_day: float = 0.0) -> float:
    """FAO-56 Penman-Monteith reference ET0, monthly soil heat flux if given."""
    validate_weather(w)
    g = _finite(soil_heat_mj_m2_day, "soil heat flux")
    t = w.tmean_c
    es = (_es(w.tmax_c)+_es(w.tmin_c))/2
    ea = es * w.rh_pct / 100.0  # RHmean approximation, FAO-56 Ch.3 Eq.19
    slope = 4098*_es(t)/(t+237.3)**2
    gamma = 0.000665*w.pressure_kpa
    ra = extraterrestrial_radiation(latitude_deg,w.month)
    # For net clear sky radiation FAO requires site elevation. Approximate it
    # from observed surface pressure, not an invented fixed altitude.
    elevation = (1-(w.pressure_kpa/101.3)**(1/5.26))*293/0.0065
    rso = (0.75+2e-5*elevation)*ra
    if rso <= 0: raise ValueError('Invalid clear-sky radiation')
    solar_ratio = min(1.0,max(0.3,w.solar_mj_m2_day/rso))
    rns = 0.77*w.solar_mj_m2_day
    sigma = 4.903e-9
    rnl = sigma*(((w.tmax_c+273.16)**4+(w.tmin_c+273.16)**4)/2)*(
        0.34-0.14*sqrt(max(0.0,ea)))*(1.35*solar_ratio-0.35)
    rn = rns-rnl
    vpd = max(0.0,es-ea)
    et = (0.408*slope*(rn-g)+gamma*(900/(t+273))*w.wind_m_s*vpd)/(
        slope+gamma*(1+0.34*w.wind_m_s))
    return max(0.0,et)


def effective_rain_fao_training_mm(p_mm):
    """FAO training manual empirical monthly Pe, assumes mild slopes, no storage."""
    p = _finite(p_mm, 'rainfall')
    if p < 0: raise ValueError('Negative precipitation')
    return min(p,max(0.0, 0.6*p-10 if p<=75 else 0.8*p-25))


def _payload_climatology(payload: Mapping, *, start_year=1995, end_year=2014,
                         allow_single_missing_year=False):
    """Strictly parse NASA POWER monthly keys YYYYMM; exclude 13 = annual means.

    Monthly PRECTOTCORR is mean daily mm/day, converted to mm per calendar
    month *before* averaging across years. Interpolate at most one internal
    missing year per month/parameter from adjacent same-month years, explicitly
    mark imputed values. Never silently interpolate longer gaps or endpoints.
    """
    if not (1981 <= int(start_year) <= int(end_year) <= 2025):
        raise ValueError('Invalid historical monthly period')
    try: raw = payload['properties']['parameter']
    except (KeyError,TypeError) as e: raise ValueError('Invalid NASA POWER response') from e
    missing = set(NASA_VARS)-set(raw)
    if missing: raise ValueError(f'Missing NASA POWER variables: {sorted(missing)}')
    # The API has unit declarations in the top-level 'parameters' mapping, when provided.
    aliases = {'PRECTOTCORR': ('mm/day','mm/d'),
               'ALLSKY_SFC_SW_DWN': ('mj/m^2/day','mj/m2/day','mj/m²/day'),
               'PS': ('kpa',)}
    declared = payload.get('parameters') or {}
    for name, allowed in aliases.items():
        entry = declared.get(name, {})
        unit = str(entry.get('units','')).lower().replace(' ','') if isinstance(entry,dict) else ''
        if unit and unit not in allowed:
            raise ValueError(f'NASA POWER {name} unexpected unit: {unit}')
    mapping = {'T2M':'tmean_c','T2M_MAX':'tmax_c','T2M_MIN':'tmin_c',
               'RH2M':'rh_pct','WS2M':'wind_m_s','PS':'pressure_kpa',
               'ALLSKY_SFC_SW_DWN':'solar_mj_m2_day',
               'PRECTOTCORR':'rainfall_mm_month'}
    result=[]
    for month in SEASON:
        points={v:[] for v in NASA_VARS}
        imputed=[]
        years=list(range(start_year,end_year+1))
        for v in NASA_VARS:
            row=[]
            for year in years:
                key=f'{year}{month:02d}'
                try: x=float(raw[v].get(key))
                except (ValueError,TypeError,AttributeError): x=float('nan')
                row.append(x if isfinite(x) and x > -900 else None)
            missing=[i for i,x in enumerate(row) if x is None]
            if missing and not allow_single_missing_year:
                index=missing[0]
                key=f'{years[index]}{month:02d}'
                if key in raw[v] and raw[v][key] is not None:
                    raise ValueError(f'NASA POWER fill value for {v} {key}')
                raise ValueError(f'NASA POWER missing {v} for {key}')
            # One INTERNAL missing year/month may be interpolated between the
            # same calendar month in adjacent years, preserving climatology.
            # Never interpolate missing endpoints or two consecutive years.
            if len(missing)>1:
                raise ValueError(f'NASA POWER climatology has multiple missing years for {v} month={month}')
            if missing:
                i=missing[0]
                if i==0 or i==len(row)-1 or row[i-1] is None or row[i+1] is None:
                    raise ValueError(f'NASA POWER climatology missing unfillable {v} {years[i]}{month:02d}')
                row[i]=(row[i-1]+row[i+1])/2
                imputed.append(f'{v}:{years[i]}{month:02d}')
            for year,x in zip(years,row):
                if v=='PRECTOTCORR':x*=calendar.monthrange(year,month)[1]
                points[v].append(x)
        kw={mapping[v]:sum(points[v])/len(points[v]) for v in NASA_VARS}
        result.append(validate_weather(MonthlyWeather(month=month,estimated_values=tuple(imputed),**kw)))
    return tuple(result)


def fetch_nasa_monthly_climatology(lat, lon, *, start_year=1995, end_year=2014,
                                   request_get=None, timeout=40):
    """Fetch historical field-point monthly conditions once, no fabricated fallback."""
    if not -90 <= _finite(lat,'latitude') <= 90 or not -180 <= _finite(lon,'longitude') <= 180:
        raise ValueError('Coordinates out of bounds')
    from .regional_climate_cache import monthly_payload
    cached = monthly_payload(lat, lon) if request_get is None else None
    if cached is not None:
        return _payload_climatology(cached, start_year=start_year, end_year=end_year,
                                    allow_single_missing_year=True)
    get = requests.get if request_get is None else request_get
    response = get(NASA_MONTHLY_URL, params={
        'parameters':','.join(NASA_VARS), 'community':'AG',
        'longitude':float(lon), 'latitude':float(lat),
        'start':int(start_year),'end':int(end_year),'format':'JSON'},
        timeout=timeout)
    response.raise_for_status()
    return _payload_climatology(response.json(),start_year=start_year,end_year=end_year,
                                allow_single_missing_year=True)


def fetch_polygon_monthly_climatology(geometry, *, fetch_point=None, max_samples=512):
    """Area-weighted nominal NASA meteo cell samples with all-cell success rule."""
    from core.nasa_polygon import polygon_sample_locations
    samples=polygon_sample_locations(geometry,max_samples=max_samples)
    fetch_point = fetch_point or fetch_nasa_monthly_climatology
    series=[fetch_point(p.latitude,p.longitude) for p in samples]
    if any(len(s)!=6 for s in series): raise ValueError('Incomplete NASA POWER polygon series')
    fields=('tmean_c','tmax_c','tmin_c','rh_pct','wind_m_s','pressure_kpa',
            'solar_mj_m2_day','rainfall_mm_month')
    return tuple(validate_weather(MonthlyWeather(month=m,
        estimated_values=tuple(f'cell{j}:{value}' for j,arr in enumerate(series)
                               for value in arr[i].estimated_values),**{
        k:sum(getattr(arr[i],k)*p.area_weight for arr,p in zip(series,samples))
        for k in fields})) for i,m in enumerate(SEASON))


def parse_kc_monthly(value):
    """Six explicit crop coefficients; never invent crop calendar or phenology."""
    if value is None or not str(value).strip(): return None
    pieces=[p.strip() for p in str(value).replace(';',',').split(',')]
    if len(pieces)!=6: raise ValueError('Enter six monthly Kc: Apr, May, Jun, Jul, Aug, Sep')
    vals=tuple(_finite(p,'Kc') for p in pieces)
    if any(not 0<=v<=2.5 for v in vals): raise ValueError('Kc must be between 0 and 2.5')
    return vals


def evaluate_irrigation_scenario(weather, scenario, latitude_deg, *,
                                 kc_monthly=None, effective_rainfall=None,
                                 application_efficiency=None, area_ha=None, weather_source=None):
    """Produce baseline and SSP monthly ET0; ETc/irrigation only if documented.

    scenario must include .temperature_change_monthly_c and
    .precipitation_change_monthly_mm, as loaded from original CCKP CSV.
    All non-temperature weather variables are held fixed (explicit assumption).
    """
    if len(weather)!=6 or tuple(w.month for w in weather)!=SEASON:
        raise ValueError('Six Apr-Sep climatology months required')
    if len(scenario.temperature_change_monthly_c)!=6 or len(scenario.precipitation_change_monthly_mm)!=6:
        raise ValueError('Six monthly CMIP6 anomalies required')
    if kc_monthly is not None:
        if len(kc_monthly)!=6 or any(not 0<=_finite(k,'Kc')<=2.5 for k in kc_monthly):
            raise ValueError('Six valid Kc coefficients required')
    if effective_rainfall not in (None,'fao_training'):
        raise ValueError('Unknown effective-rainfall method')
    if application_efficiency is not None:
        if not 0 < _finite(application_efficiency,'efficiency') <= 1:
            raise ValueError('Efficiency must be in (0,1]')
    if area_ha is not None and _finite(area_ha,'area_ha')<=0:
        raise ValueError('Area must be positive')
    results=[]
    for i,base in enumerate(weather):
        delta_t=_finite(scenario.temperature_change_monthly_c[i],'delta T')
        delta_p=_finite(scenario.precipitation_change_monthly_mm[i],'delta P')
        future=replace(base,tmean_c=base.tmean_c+delta_t,
                       tmax_c=base.tmax_c+delta_t,tmin_c=base.tmin_c+delta_t,
                       rainfall_mm_month=max(0.0,base.rainfall_mm_month+delta_p))
        # FAO-56 monthly soil heat approximation G = 0.14 (T_i - T_(i-1)).
        # March is not included in the 6-month input: April G=0 is an
        # explicit approximation. Other months use adjacent monthly means.
        g_baseline=0.14*(base.tmean_c-weather[i-1].tmean_c) if i else 0.0
        g_future=(0.14*(future.tmean_c-weather[i-1].tmean_c-
                  float(scenario.temperature_change_monthly_c[i-1])) if i else 0.0)
        et0base=fao56_et0_mm_day(base,latitude_deg,soil_heat_mj_m2_day=g_baseline)
        et0future=fao56_et0_mm_day(future,latitude_deg,soil_heat_mj_m2_day=g_future)
        days=calendar.monthrange(2001,base.month)[1]
        row={'month':MONTH_NAMES[i],
             'baseline_rain_mm':round(base.rainfall_mm_month,4),
             'future_rain_mm':round(future.rainfall_mm_month,4),
             'baseline_et0_mm':round(et0base*days,4),
             'future_et0_mm':round(et0future*days,4)}
        if kc_monthly is not None:
            k=float(kc_monthly[i]); etb=et0base*days*k; etf=et0future*days*k
            row.update({'kc':k,'baseline_etc_mm':round(etb,4),'future_etc_mm':round(etf,4)})
            if effective_rainfall == 'fao_training':
                pb=effective_rain_fao_training_mm(base.rainfall_mm_month)
                pf=effective_rain_fao_training_mm(future.rainfall_mm_month)
                nb=max(0.0,etb-pb);nf=max(0.0,etf-pf)
                row.update({'baseline_effective_rain_mm':round(pb,4),
                            'future_effective_rain_mm':round(pf,4),
                            'baseline_net_irrigation_mm':round(nb,4),
                            'future_net_irrigation_mm':round(nf,4)})
                if application_efficiency is not None:
                    row.update({'baseline_gross_irrigation_m3_ha':round(nb*10/application_efficiency,3),
                                'future_gross_irrigation_m3_ha':round(nf*10/application_efficiency,3)})
        results.append(row)
    totals={key:sum(row[key] for row in results) for key in (
        'baseline_et0_mm','future_et0_mm',
        'baseline_etc_mm','future_etc_mm',
        'baseline_net_irrigation_mm','future_net_irrigation_mm',
        'baseline_gross_irrigation_m3_ha','future_gross_irrigation_m3_ha')
        if key in results[0]}
    if area_ha is not None and 'baseline_gross_irrigation_m3_ha' in totals:
        totals['baseline_gross_irrigation_m3']=totals['baseline_gross_irrigation_m3_ha']*float(area_ha)
        totals['future_gross_irrigation_m3']=totals['future_gross_irrigation_m3_ha']*float(area_ha)
    return {'months':results,'totals':totals,
            'status':'scenario only: FAO-56 ETo, crop Kc supplied by user',
            'evidence':{'weather':weather_source or 'User/synthetic weather supplied to calculation; NASA origin NOT verified',
                        'anomaly':f'World Bank CCKP CMIP6 {scenario.scenario} 2040-2059',
                        'humidity_wind_radiation':'held at historic monthly climatology',
                        'kc':'user-defined / unverified' if kc_monthly is not None else 'not supplied',
                        'rainfall_method':effective_rainfall or 'not supplied',
                        'soil_moisture_change':'not modeled',
                        'soil_heat_flux':'monthly FAO-56 gradient for May-Sep; April G=0 (March not supplied)',
                        'official_water_norm':'not replaced'}}
