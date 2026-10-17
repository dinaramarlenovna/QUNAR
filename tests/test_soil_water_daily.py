"""FAO daily root-zone ledger QA: no invented field soil or measured savings."""
from datetime import date, timedelta
from math import isclose

import pytest

from core.soil_water_daily import (
    DailyWeather, SOIL_PRESETS, CROP_ROOT_P, _parse_daily,
    fetch_nasa_daily, daily_et0, kc_for_day, daily_soil_balance,
)


def weather(days=20, rain=0.0, t=25.0):
    return tuple(DailyWeather(date(2025,4,1)+timedelta(days=i), t, t+8, t-8,
        48.,2.,99.,20.,rain) for i in range(days))


def baseline(**kwargs):
    args=dict(crop='Corn',sowing_date=date(2025,4,1),latitude_deg=42.2,
        field_efficiency=.75,soil_fc=.31,soil_wp=.15,root_max_m=1.0,
        depletion_p=.55,initial_depletion_fraction=.3,mode='auto',
        assumptions_confirmed=True)
    args.update(kwargs)
    return args


def test_fao_profile_and_crop_examples_not_missing():
    assert SOIL_PRESETS['sandy_loam']==(.22,.10)
    assert CROP_ROOT_P['Cotton']==(1.0,.65)
    assert 'Rice' not in CROP_ROOT_P


def test_daily_et0_positive_and_more_on_hot_day():
    a=weather()[0]
    b=DailyWeather(a.day,27.,35.,19.,a.rh_pct,a.wind_m_s,a.pressure_kpa,a.solar_mj_m2_day,a.rain_mm)
    assert 1<daily_et0(a,42.2)<12
    assert daily_et0(b,42.2)>daily_et0(a,42.2)


def test_growth_reference_boundary():
    assert kc_for_day('Corn',date(2025,4,1),date(2025,3,31))==0.
    assert kc_for_day('Corn',date(2025,4,1),date(2025,4,1))==.4
    assert kc_for_day('Corn',date(2025,4,1),date(2026,4,1))==0.


def test_daily_irrigation_mass_balance():
    r=daily_soil_balance(weather(80,rain=1.3),**baseline())
    t=r['totals']
    # Equation 85 with soil deepening at field capacity and G=0.
    lhs=t['rain_mm']+t['capillary_rise_mm']+t['net_irrigation_mm']
    rhs=t['actual_etc_mm']+t['runoff_mm']+t['deep_percolation_mm'] - t['final_depletion_mm'] + t['initial_depletion_mm']
    assert lhs == pytest.approx(rhs,abs=1e-7)
    assert t['n_days']==80
    assert t['field_delivery_mm']==pytest.approx(t['net_irrigation_mm']/.75)
    assert t['field_delivery_m3_ha']==pytest.approx(10*t['field_delivery_mm'])
    assert all(0<=r0['depletion_end_mm'] <= r0['TAW_mm'] for r0 in r['daily'])


def test_rainfed_stress_and_less_actual_etc():
    watered=daily_soil_balance(weather(95),**baseline())['totals']
    dry=daily_soil_balance(weather(95),**baseline(mode='rainfed'))['totals']
    assert watered['net_irrigation_mm']>0
    assert dry['net_irrigation_mm']==0
    assert dry['days_under_stress']>0
    assert dry['actual_etc_mm'] < watered['actual_etc_mm']


def test_rainfall_reduces_irrigation_demand():
    dry=daily_soil_balance(weather(70,rain=0.),**baseline())['totals']
    wet=daily_soil_balance(weather(70,rain=2.),**baseline())['totals']
    assert wet['net_irrigation_mm'] < dry['net_irrigation_mm']


def test_heavy_rain_creates_deep_percolation():
    heavy=daily_soil_balance(weather(5,rain=60.),**baseline(mode='rainfed'))['totals']
    assert heavy['deep_percolation_mm'] > 50
    assert heavy['net_irrigation_mm']==0


def test_initial_soil_data_required_not_silent():
    with pytest.raises(ValueError,match='Confirm'):
        daily_soil_balance(weather(),**baseline(assumptions_confirmed=False))
    with pytest.raises(ValueError,match='Wilting'):
        daily_soil_balance(weather(),**baseline(soil_wp=.35))
    with pytest.raises(ValueError,match='paddy'):
        daily_soil_balance(weather(),**baseline(crop='Rice'))


def test_missing_day_blocks_model():
    ww=weather(5)
    with pytest.raises(ValueError,match='consecutive'):
        daily_soil_balance(ww[:2]+ww[3:],**baseline())


def test_bad_calendar_blocks_model():
    with pytest.raises(ValueError):
        daily_soil_balance(weather(),**baseline(stage_lengths=[20,0,40,30]))


def test_observed_irrigation_mode_requires_measurements():
    with pytest.raises(ValueError,match='needs known'):
        daily_soil_balance(weather(),**baseline(mode='measured'))
    r=daily_soil_balance(weather(),**baseline(mode='measured',
        measured_net_irrigation_mm={date(2025,4,1):10.}))
    assert r['totals']['net_irrigation_mm']==pytest.approx(10.)


def test_daily_parser_requires_exact_calendar_keys():
    w=weather(3)
    vals={'T2M':'tmean_c','T2M_MAX':'tmax_c','T2M_MIN':'tmin_c','RH2M':'rh_pct',
          'WS2M':'wind_m_s','PS':'pressure_kpa','ALLSKY_SFC_SW_DWN':'solar_mj_m2_day',
          'PRECTOTCORR':'rain_mm'}
    params={k:{r.day.strftime('%Y%m%d'):getattr(r,v) for r in w} for k,v in vals.items()}
    payload={'properties':{'parameter':params},'parameters':{
        'PS':{'units':'kPa'},'PRECTOTCORR':{'units':'mm/day'},
        'ALLSKY_SFC_SW_DWN':{'units':'MJ/m^2/day'}}}
    parsed=_parse_daily(payload,w[0].day,w[-1].day)
    assert len(parsed)==3 and parsed[0].rain_mm==0
    del payload['properties']['parameter']['PS']['20250402']
    with pytest.raises(ValueError,match='Incomplete'):_parse_daily(payload,w[0].day,w[-1].day)


def test_daily_parser_rejects_fill_and_wrong_units():
    vals={k:{'20250401':v} for k,v in {'T2M':25,'T2M_MAX':33,'T2M_MIN':17,'RH2M':48,
        'WS2M':2,'PS':99,'ALLSKY_SFC_SW_DWN':20,'PRECTOTCORR':1}.items()}
    payload={'properties':{'parameter':vals}}
    assert _parse_daily(payload,date(2025,4,1),date(2025,4,1))[0].rain_mm==1
    payload['properties']['parameter']['PS']['20250401']=-999
    with pytest.raises(ValueError):_parse_daily(payload,date(2025,4,1),date(2025,4,1))
    payload['properties']['parameter']['PS']['20250401']=99
    payload['parameters']={'PS':{'units':'hPa'}}
    with pytest.raises(ValueError,match='unit'):_parse_daily(payload,date(2025,4,1),date(2025,4,1))


def test_daily_fetch_has_correct_nasa_params():
    w=weather(2)
    vv={'T2M':'tmean_c','T2M_MAX':'tmax_c','T2M_MIN':'tmin_c','RH2M':'rh_pct',
        'WS2M':'wind_m_s','PS':'pressure_kpa','ALLSKY_SFC_SW_DWN':'solar_mj_m2_day',
        'PRECTOTCORR':'rain_mm'}
    raw={k:{o.day.strftime('%Y%m%d'):getattr(o,v) for o in w} for k,v in vv.items()}
    got=[]
    class Mock:
        def raise_for_status(self): pass
        def json(self): return {'properties':{'parameter':raw}}
    def fake(url,params,timeout):
        got.append((url,params));return Mock()
    out=fetch_nasa_daily(42.2,68.3,start=w[0].day,end=w[-1].day,request_get=fake)
    assert len(out)==2
    assert got[0][1]['time-standard']=='UTC' and got[0][1]['community']=='AG'
    assert 'PRECTOTCORR' in got[0][1]['parameters']


def test_future_dates_rejected():
    with pytest.raises(ValueError,match='Historical'):
        fetch_nasa_daily(42,68,start=date(2027,1,1),end=date(2027,1,2))
