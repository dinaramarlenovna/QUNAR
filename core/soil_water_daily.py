"""Historical daily FAO-56 root-zone soil water ledger (optional QUNAR scenario).

FAO-56 Chapter 8 Eq.82-88: TAW, RAW, Ks, adjusted ETc, root zone depletion.
NASA POWER daily point weather, historical dates only. Soil texture from FAO
AquaCrop indicative profiles, not measured field soil or spatial SoilGrids.

This is a simplified single-Kc daily management scenario with uniform soil,
explicit runoff/capillary assumptions, a stage-based Kc curve and optional
root development. It does not represent paddy fields, salinity/leaching, soil
layers, future daily CMIP6 downscaling, basin depletion or observed savings.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import acos, cos, exp, isfinite, pi, sin, sqrt, tan
from typing import Mapping, Sequence

import requests

from core.fao56_irrigation import MonthlyWeather, _es, validate_weather
from core.irrigation_evidence import CROP_KC_STAGES

FAO_DAILY_SOURCE = 'https://www.fao.org/4/X0490E/x0490e0e.htm'
FAO_SOIL_PROFILE_SOURCE = 'https://www.fao.org/fileadmin/user_upload/faowater/docs/AquaCropChapter2.pdf'
NASA_DAILY_SOURCE = 'https://power.larc.nasa.gov/docs/services/api/temporal/daily/'
NASA_DAILY_ENDPOINT = 'https://power.larc.nasa.gov/api/temporal/daily/point'
PARAMS = ('T2M','T2M_MAX','T2M_MIN','RH2M','WS2M','PS','ALLSKY_SFC_SW_DWN','PRECTOTCORR')

# FAO AquaCrop manual Table 2.13a, soil properties are GLOBAL typical soil
# profiles, not Turkestan-district measurements. Volume fraction m³/m³.
SOIL_PRESETS = {
    'sand': (0.13, 0.06),
    'sandy_loam': (0.22, 0.10),
    'loam': (0.31, 0.15),
    'silt_loam': (0.33, 0.13),
    'clay_loam': (0.39, 0.23),
}
# FAO-56 Chapter 8, Table 22: low end of maximum rooting depth range chosen
# for illustrative irrigation scheduling and p for ETc ~5 mm/day.
CROP_ROOT_P = {
    'Wheat': (1.0, .55), 'Barley': (1.0, .55),
    'Corn': (1.0, .55), 'Cotton': (1.0, .65),
    'Potato': (.4, .35), 'Sunflower': (.8, .45),
    'Cabbage': (.5, .45), 'Carrots': (.5, .35),
    'Cucumbers': (.7, .50), 'Tomatoes': (.7, .40),
    'Melons': (.8, .40), 'Onion': (.3, .30),
}


@dataclass(frozen=True)
class DailyWeather:
    day: date
    tmean_c: float
    tmax_c: float
    tmin_c: float
    rh_pct: float
    wind_m_s: float
    pressure_kpa: float
    solar_mj_m2_day: float
    rain_mm: float


def _real(value, label: str, *, lower=None, upper=None) -> float:
    try: x = float(value)
    except (TypeError, ValueError): raise ValueError(f'Invalid {label}') from None
    if not isfinite(x) or (lower is not None and x < lower) or (upper is not None and x > upper):
        raise ValueError(f'Out of bounds {label}: {value}')
    return x


def _daily_validate(w: DailyWeather) -> DailyWeather:
    if not isinstance(w.day, date): raise ValueError('Day must be a date')
    validate_weather(MonthlyWeather(w.day.month,w.tmean_c,w.tmax_c,w.tmin_c,w.rh_pct,
                                    w.wind_m_s,w.pressure_kpa,w.solar_mj_m2_day,w.rain_mm))
    return w


def _parse_daily(payload: Mapping, start: date, end: date) -> tuple[DailyWeather,...]:
    try: raw=payload['properties']['parameter']
    except (TypeError, KeyError): raise ValueError('Malformed NASA daily response') from None
    if not isinstance(raw, Mapping) or set(PARAMS)-set(raw):
        raise ValueError('Missing NASA daily variables')
    units=payload.get('parameters') or {}
    accepted = {'PS':{'kpa'},'PRECTOTCORR':{'mm/day','mm/d'},
                'ALLSKY_SFC_SW_DWN':{'mj/m^2/day','mj/m2/day','mj/m²/day'}}
    for name, allowed in accepted.items():
        unit_info=units.get(name,{})
        unit=str(unit_info.get('units','')).strip().lower().replace(' ','') if isinstance(unit_info,dict) else ''
        if unit and unit not in allowed: raise ValueError(f'Unexpected NASA unit for {name}: {unit}')
    mapping={'T2M':'tmean_c','T2M_MAX':'tmax_c','T2M_MIN':'tmin_c',
             'RH2M':'rh_pct','WS2M':'wind_m_s','PS':'pressure_kpa',
             'ALLSKY_SFC_SW_DWN':'solar_mj_m2_day','PRECTOTCORR':'rain_mm'}
    days=[];d=start
    while d<=end:
        key=d.strftime('%Y%m%d'); params={}
        for name,field in mapping.items():
            try: x=_real(raw[name][key],f'{name} {key}')
            except KeyError: raise ValueError(f'Incomplete NASA daily weather: {name} {key}') from None
            if x<=-900: raise ValueError(f'NASA missing/fill value: {name} {key}')
            params[field]=x
        days.append(_daily_validate(DailyWeather(d,**params)))
        d+=timedelta(days=1)
    return tuple(days)


def fetch_nasa_daily(latitude:float, longitude:float, *, start:date, end:date,
                     request_get=None, timeout=45) -> tuple[DailyWeather,...]:
    lat=_real(latitude,'latitude',lower=-70,upper=70)
    lon=_real(longitude,'longitude',lower=-180,upper=180)
    if not isinstance(start,date) or not isinstance(end,date) or start>end:
        raise ValueError('Invalid daily weather date range')
    if start < date(1981,1,1) or end >= date.today() or (end-start).days>366:
        raise ValueError('Historical completed dates only, maximum 367 days')
    from .regional_climate_cache import daily_payload
    cached = daily_payload(latitude, longitude, start, end) if request_get is None else None
    if cached is not None:
        return _parse_daily(cached, start, end)
    get=request_get or requests.get
    response=get(NASA_DAILY_ENDPOINT,params={'parameters':','.join(PARAMS),'community':'AG',
        'latitude':lat,'longitude':lon,'start':start.strftime('%Y%m%d'),
        'end':end.strftime('%Y%m%d'),'format':'JSON','time-standard':'UTC'},timeout=timeout)
    response.raise_for_status()
    return _parse_daily(response.json(),start,end)


def daily_et0(w:DailyWeather, latitude_deg:float) -> float:
    """FAO-56 daily reference ET0; G=0; incoming wind WS2M at 2m."""
    _daily_validate(w)
    lat=_real(latitude_deg,'latitude',lower=-70,upper=70)*pi/180
    j=w.day.timetuple().tm_yday
    dr=1+.033*cos(2*pi*j/365)
    solar_dec=.409*sin(2*pi*j/365-1.39)
    ws=acos(max(-1.,min(1.,-tan(lat)*tan(solar_dec))))
    ra=(24*60/pi)*.0820*dr*(ws*sin(lat)*sin(solar_dec)+cos(lat)*cos(solar_dec)*sin(ws))
    es=(_es(w.tmax_c)+_es(w.tmin_c))/2
    ea=es*w.rh_pct/100  # FAO-56 approximate RHmean assumption
    slope=4098*_es(w.tmean_c)/(w.tmean_c+237.3)**2
    gamma=.000665*w.pressure_kpa
    elevation=(1-(w.pressure_kpa/101.3)**(1/5.26))*293/.0065
    rso=(.75+2e-5*elevation)*ra
    if rso<=0: raise ValueError('Invalid daily clear-sky radiation')
    solar_ratio=max(.3,min(1.,w.solar_mj_m2_day/rso))
    net_short=.77*w.solar_mj_m2_day
    net_long=4.903e-9*((w.tmax_c+273.16)**4+(w.tmin_c+273.16)**4)/2 * (
        .34-.14*sqrt(max(ea,0)))*(1.35*solar_ratio-.35)
    rn=net_short-net_long
    eto=(.408*slope*rn + gamma*(900/(w.tmean_c+273))*w.wind_m_s*max(es-ea,0))/(
        slope+gamma*(1+.34*w.wind_m_s))
    return max(0.,eto)


def kc_for_day(crop:str, sowing:date, day:date, stage_lengths:Sequence[int] | None=None)->float:
    """FAO stage reference: piecewise Kc, scenario, no unsupported crop calendar."""
    if crop not in CROP_KC_STAGES: raise ValueError('Unsupported stage reference crop')
    coeffs,lengths_ref=CROP_KC_STAGES[crop]
    lengths=stage_lengths if stage_lengths is not None else lengths_ref
    if len(lengths)!=4 or any(type(x)!=int or x<1 for x in lengths) or sum(lengths)>366:
        raise ValueError('Invalid crop stage lengths')
    offset=(day-sowing).days
    if offset<0 or offset>=sum(lengths): return 0.
    for k,n in zip(coeffs,lengths):
        if offset<n: return float(k)
        offset-=n
    return 0.


def daily_soil_balance(weather:Sequence[DailyWeather], *, crop:str, sowing_date:date,
                       latitude_deg:float, field_efficiency:float,
                       soil_fc:float, soil_wp:float, root_max_m:float, depletion_p:float,
                       initial_depletion_fraction:float, stage_lengths=None,
                       mode:str='auto', runoff_fraction:float=0., capillary_rise_mm_day:float=0.,
                       measured_net_irrigation_mm:Mapping[date,float] | None=None,
                       dynamic_root:bool=True, assumptions_confirmed:bool=False)->dict:
    """Daily FAO-56 Ch8 root-zone ledger, simple Kc scheduling scenario.

    1-mm rain is assumed to enter root zone unless user runoff fraction states
    otherwise. CR=0 default is an explicit scenario (not groundwater evidence).
    No irrigation without choice 'auto' or provided measured schedule. Estimated
    field deliveries do not prove basin savings. One soil layer, no salinity.
    """
    if not assumptions_confirmed: raise ValueError('Confirm soil and hydrology scenario assumptions')
    if mode not in {'auto','rainfed','measured'}: raise ValueError('Unknown scheduling mode')
    if crop=='Rice' or crop not in CROP_ROOT_P: raise ValueError('No non-paddy balance for this crop')
    if mode=='measured' and measured_net_irrigation_mm is None:
        raise ValueError('Measured mode needs known daily net irrigation')
    if not isinstance(sowing_date,date): raise ValueError('Sowing date required')
    eta=_real(field_efficiency,'field efficiency',lower=.01,upper=1)
    fc=_real(soil_fc,'field capacity',lower=.01,upper=.75)
    wp=_real(soil_wp,'wilting point',lower=0,upper=.7)
    if wp>=fc: raise ValueError('Wilting point must be below field capacity')
    root_max=_real(root_max_m,'root depth',lower=.1,upper=3.)
    p=_real(depletion_p,'depletion fraction',lower=.1,upper=.8)
    init=_real(initial_depletion_fraction,'initial depletion fraction',lower=0.,upper=1.)
    runoff=_real(runoff_fraction,'runoff fraction',lower=0.,upper=1.)
    capillary=_real(capillary_rise_mm_day,'capillary rise',lower=0.,upper=20.)
    if not weather: raise ValueError('Daily weather required')
    days=tuple(weather)
    if days[0].day>sowing_date:
        raise ValueError('Historical weather must cover crop sowing date')
    if days[-1].day< sowing_date:
        raise ValueError('Crop season outside weather interval')
    if any((days[i].day-days[i-1].day).days!=1 for i in range(1,len(days))):
        raise ValueError('Daily weather must be consecutive without missing dates')
    lengths=stage_lengths or CROP_KC_STAGES[crop][1]
    if len(lengths)!=4 or any(type(x)!=int or x<1 for x in lengths) or sum(lengths)>366:
        raise ValueError('Invalid crop calendar')
    root_min=min(.3,root_max)
    effective_stages=max(1,lengths[0]+lengths[1])
    taw_initial=1000*(fc-wp)*root_min
    dr=taw_initial*init
    rows=[]
    totals={'rain_mm':0., 'net_irrigation_mm':0.,'field_delivery_mm':0.,
            'eto_mm':0., 'potential_etc_mm':0.,'actual_etc_mm':0.,
            'deep_percolation_mm':0.,'runoff_mm':0.,'capillary_rise_mm':0.,
            'days_under_stress':0,'irrigation_events':0}
    for w in days:
        _daily_validate(w)
        offset=(w.day-sowing_date).days
        if offset<0 or offset>=sum(lengths):
            # Treat outside crop season as excluded rather than resetting D.
            continue
        k=kc_for_day(crop,sowing_date,w.day,lengths)
        root=root_max if not dynamic_root else root_min+(root_max-root_min)*min(1.,max(0.,offset/effective_stages))
        taw=1000*(fc-wp)*root
        dr=min(dr,taw) # deeper rooting soil assumed at field capacity
        et0=daily_et0(w,latitude_deg)
        potential=k*et0
        p_adjust=max(.1,min(.8,p + .04*(5.-potential)))
        raw=taw*p_adjust
        rain=w.rain_mm
        ro=rain*runoff
        useful_rain=rain-ro
        cr=capillary
        start_dr=dr
        wet_dr=max(0.,dr-useful_rain-cr)
        rain_dp=max(0.,useful_rain+cr-dr)
        if mode=='auto':
            # Apply at beginning of day if today's expected demand would cross RAW.
            irrigation=wet_dr if wet_dr+potential>=raw and wet_dr>0 else 0.
        elif mode=='measured':
            irrigation=_real(measured_net_irrigation_mm.get(w.day,0.),'measured net irrigation',lower=0.,upper=200.)
        else: irrigation=0.
        post_irrig=max(0.,wet_dr-irrigation)
        extra_irrig=max(0.,irrigation-wet_dr)
        ks=1. if post_irrig<=raw or taw<=raw else max(0.,min(1.,(taw-post_irrig)/(taw-raw)))
        actual=min(ks*potential, max(0.,taw-post_irrig))
        dr=min(taw,max(0.,post_irrig+actual))
        dp=rain_dp+extra_irrig
        delivered=irrigation/eta
        rows.append({'date':w.day.isoformat(),'root_m':root,'TAW_mm':taw,'RAW_mm':raw,
            'depletion_start_mm':start_dr,'rain_mm':rain,'runoff_mm':ro,
            'net_irrigation_mm':irrigation,'field_delivery_mm':delivered,
            'eto_mm':et0,'Kc':k,'Ks':ks,'potential_etc_mm':potential,
            'actual_etc_mm':actual,'deep_percolation_mm':dp,
            'depletion_end_mm':dr,'stress': bool(ks < 1.-1e-9)})
        for field in ('rain_mm','runoff_mm','net_irrigation_mm','field_delivery_mm',
                      'eto_mm','potential_etc_mm','actual_etc_mm','deep_percolation_mm'):
            totals[field]+=rows[-1][field]
        totals['capillary_rise_mm']+=cr
        totals['days_under_stress']+=int(ks < 1.-1e-9)
        totals['irrigation_events']+=int(irrigation > 1e-9)
    if not rows: raise ValueError('No crop-growing dates in weather period')
    totals.update({'initial_depletion_mm': taw_initial*init, 'final_depletion_mm':dr,
                   'net_irrigation_m3_ha':totals['net_irrigation_mm']*10,
                   'field_delivery_m3_ha':totals['field_delivery_mm']*10,
                   'mean_Ks':sum(x['Ks'] for x in rows)/len(rows),
                   'n_days':len(rows)})
    return {'daily':rows,'totals':totals, 'status':'historical data, indicative FAO-56 daily single-Kc soil-water scenario',
      'inputs':{'crop':crop,'soil_theta_fc':fc,'soil_theta_wp':wp,'root_max_m':root_max,'p':p,
        'initial_depletion_fraction':init,'dynamic_root':dynamic_root,'mode':mode,
        'runoff_fraction':runoff,'capillary_mm_day':capillary,'field_efficiency':eta,
        'sowing_date':sowing_date.isoformat(),'stage_lengths':list(lengths)},
      'scope':'historical daily weather; assumed soil and runoff; not actual farmer measurements or climate projections',
      'sources':[FAO_DAILY_SOURCE,FAO_SOIL_PROFILE_SOURCE,NASA_DAILY_SOURCE]}
