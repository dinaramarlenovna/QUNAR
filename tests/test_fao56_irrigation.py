"""Offline FAO-56, NASA/CCKP integration and physical-limit regression tests."""
from datetime import date
from dataclasses import replace
from math import isclose, isfinite
from types import SimpleNamespace

import pytest

from core.fao56_irrigation import (
    MonthlyWeather, _payload_climatology, fao56_et0_mm_day,
    extraterrestrial_radiation, effective_rain_fao_training_mm,
    parse_kc_monthly, evaluate_irrigation_scenario,
    fetch_nasa_monthly_climatology, fetch_polygon_monthly_climatology
)
from core.cmip6_scenarios import load_scenario
from pathlib import Path

DATA=Path(__file__).resolve().parents[1]/'data'/'cmip6'

def w(m=4,**kw):
    payload=dict(month=m,tmean_c=24.0,tmax_c=32.0,tmin_c=16.0,
                 rh_pct=45.0,wind_m_s=2.1,pressure_kpa=98.0,
                 solar_mj_m2_day=20.0,rainfall_mm_month=25.0)
    payload.update(kw)
    return MonthlyWeather(**payload)

def synthetic_payload():
    parms={}
    vals={'T2M':24.0,'T2M_MAX':32.0,'T2M_MIN':16.0,'RH2M':45.0,
          'WS2M':2.1,'PS':98.0,'ALLSKY_SFC_SW_DWN':20.0,
          'PRECTOTCORR':1.0}
    for key,v in vals.items():
        parms[key]={f'{year}{m:02d}':v for year in range(1995,2015) for m in range(1,13)}
        parms[key]['199513']=99999 # annual record must never contaminate monthly means
    return {'properties':{'parameter':parms}, 'parameters':{
        'PRECTOTCORR':{'units':'mm/day'},
        'PS':{'units':'kPa'},'ALLSKY_SFC_SW_DWN':{'units':'MJ/m^2/day'}}}

def test_et0_reasonable_in_summer():
    et=fao56_et0_mm_day(w(7),42.0)
    assert 3 < et < 10
    assert isfinite(et)

def test_seasonal_irradiance_positive():
    assert extraterrestrial_radiation(42,6)>extraterrestrial_radiation(42,12)>0

def test_high_temp_raises_eto_when_rh_fixed():
    old=fao56_et0_mm_day(w(7),42)
    new=fao56_et0_mm_day(w(7,tmean_c=26,tmax_c=34,tmin_c=18),42)
    assert new>old

def test_rh_and_wind_sensitivity():
    dry=fao56_et0_mm_day(w(rh_pct=30.0),42)
    wet=fao56_et0_mm_day(w(rh_pct=85.0),42)
    assert dry>wet

def test_invalid_units_no_silent_conversion():
    bad=synthetic_payload()
    bad['parameters']['PRECTOTCORR']['units']='mm/month'
    with pytest.raises(ValueError,match='unit'): _payload_climatology(bad)

def test_nasa_rain_daily_to_monthly():
    ww=_payload_climatology(synthetic_payload())
    assert [x.rainfall_mm_month for x in ww] == [30,31,30,31,31,30]
    assert len(ww)==6

def test_one_missing_interior_nasa_month_is_interpolated_and_labelled():
    payload=synthetic_payload()
    del payload['properties']['parameter']['PS']['200507']
    months=_payload_climatology(payload,allow_single_missing_year=True)
    assert 'PS:200507' in months[3].estimated_values


def test_single_fill_is_imputed_not_silent():
    payload=synthetic_payload()
    payload['properties']['parameter']['T2M']['200507']=-999
    months=_payload_climatology(payload,allow_single_missing_year=True)
    assert 'T2M:200507' in months[3].estimated_values


def test_missing_two_nasa_years_or_endpoint_fails():
    payload=synthetic_payload()
    del payload['properties']['parameter']['PS']['200507']
    del payload['properties']['parameter']['PS']['200607']
    with pytest.raises(ValueError, match='multiple missing'): _payload_climatology(payload,allow_single_missing_year=True)
    payload=synthetic_payload()
    del payload['properties']['parameter']['PS']['199507']
    with pytest.raises(ValueError, match='unfillable'): _payload_climatology(payload,allow_single_missing_year=True)

def test_nasa_api_request_parameterization():
    seen=[]
    class Response:
        def raise_for_status(self): pass
        def json(self): return synthetic_payload()
    def fake_get(url,params,timeout):
        seen.append((url,params,timeout));return Response()
    result=fetch_nasa_monthly_climatology(42.2,68.1,request_get=fake_get)
    assert len(result)==6
    assert seen[0][1]['start']==1995 and seen[0][1]['end']==2014
    assert seen[0][1]['community']=='AG'

def test_kc_requires_six_explicit():
    assert parse_kc_monthly('') is None
    assert parse_kc_monthly('0.5,0.6,0.8,1.15,1,0.5')[3]==1.15
    with pytest.raises(ValueError):parse_kc_monthly('0.5,1.1')
    with pytest.raises(ValueError):parse_kc_monthly('0.5,0.6,0.8,3.0,1,0.5')

def test_fao_empirical_rainfall_bounds():
    for p in (0,4,25,75,100,250):
        assert 0<=effective_rain_fao_training_mm(p)<=p
    assert effective_rain_fao_training_mm(100)==55

def test_cmip6_source_files_present_and_scenarios_differ():
    a=load_scenario(DATA,'SSP2-4.5')
    b=load_scenario(DATA,'SSP5-8.5')
    assert a.temperature_change_c < b.temperature_change_c
    assert len(a.precipitation_change_monthly_mm)==6

def test_no_crop_input_means_no_crop_irrigation_claim():
    r=evaluate_irrigation_scenario(tuple(w(m) for m in range(4,10)),load_scenario(DATA,'SSP2-4.5'),42)
    assert 'future_etc_mm' not in r['totals']
    assert 'future_gross_irrigation_m3_ha' not in r['totals']

def test_et0_etc_and_water_conversion():
    scenario=load_scenario(DATA,'SSP5-8.5')
    r=evaluate_irrigation_scenario(tuple(w(m) for m in range(4,10)),scenario,42,
        kc_monthly=[.3,.6,1.1,1.1,.9,.5],
        effective_rainfall='fao_training',application_efficiency=.8,area_ha=100)
    d=r['totals']
    assert d['future_et0_mm']>d['baseline_et0_mm']
    assert d['future_gross_irrigation_m3']>d['baseline_gross_irrigation_m3']
    assert d['future_gross_irrigation_m3_ha']*100 == pytest.approx(d['future_gross_irrigation_m3'])
    assert len(r['months'])==6
    assert all(z['baseline_net_irrigation_mm']>=0 for z in r['months'])

def test_p_to_zero_clamp():
    scenario=SimpleNamespace(scenario='SSP2-4.5',temperature_change_monthly_c=(1,)*6,
                             precipitation_change_monthly_mm=(-1000,)*6)
    r=evaluate_irrigation_scenario(tuple(w(m) for m in range(4,10)),scenario,42)
    assert all(x['future_rain_mm']==0 for x in r['months'])

def test_missing_month_or_bad_efficiency_fails():
    with pytest.raises(ValueError):evaluate_irrigation_scenario((w(4),),load_scenario(DATA,'SSP2-4.5'),42)
    with pytest.raises(ValueError):evaluate_irrigation_scenario(tuple(w(m) for m in range(4,10)),load_scenario(DATA,'SSP2-4.5'),42,
        kc_monthly=(1,)*6,effective_rainfall='fao_training',application_efficiency=0)

def test_polygon_weighted_monthly_weather():
    square={'type':'Polygon','coordinates':[[[68.01,42.01],[68.7,42.01],[68.7,42.7],[68.01,42.7],[68.01,42.01]]]}
    calls=[]
    def f(lat,lon):
        calls.append((lat,lon))
        return tuple(w(m,tmean_c=20 if lon<68.5 else 30,
                       tmax_c=28 if lon<68.5 else 38,
                       tmin_c=12 if lon<68.5 else 22) for m in range(4,10))
    result=fetch_polygon_monthly_climatology(square,fetch_point=f)
    assert len(calls)>=2
    assert 20<result[0].tmean_c<30
