"""QA for user polygon -> NASA provenance, ISRIC soil, and A8 canonical case."""
from datetime import date,timedelta
from math import isclose
from pathlib import Path
import json
import pytest
from shapely.geometry import Polygon
from core.nasa import _parse_growing_season,PARAMS
from core.nasa_polygon import polygon_sample_locations,fetch_polygon_daily_weather
from core.field_climate import fetch_farm_climate_normal,fetch_rootzone_wetness_climatology
from core.fao56_irrigation import MonthlyWeather
from core.soil_water_daily import DailyWeather
from core.soilgrids_reference import (parse_soilgrids_response,indicative_texture_from_soilgrids,
    fetch_soilgrids_reference,PROPERTIES,DEPTHS)
from core.a8_crosscheck import generate_a8_crosscheck
from core.water_norms import PUMPING_REFERENCE_KWH_PER_M3
from core.economics import DEFAULT_EF_KZ_KGCO2_PER_KWH


def _payload(start,end):
    days=[];d=start
    while d<=end:days.append(d.strftime('%Y%m%d'));d+=timedelta(days=1)
    vals={'T2M':25.,'PRECTOTCORR':2.,'RH2M':50.,'GWETROOT':.25,
          'ALLSKY_SFC_SW_DWN':20.}
    return {'properties':{'parameter':{key:{day:value for day in days}
                      for key,value in vals.items()}}}


def test_daily_nasa_date_aligned_and_single_gap_labeled():
    start=date(2025,4,1);end=date(2025,4,3)
    p=_payload(start,end)
    p['properties']['parameter']['PRECTOTCORR'].pop('20250402')
    r=_parse_growing_season(p,start,end)
    assert r['Apr-Sep precipitation, mm']==pytest.approx(6.0)
    assert r['interpolated_daily_values']==1
    assert 'PRECTOTCORR 20250402' in r['imputation_log']


def test_nasa_missing_two_consecutive_or_boundary_fails():
    start=date(2025,4,1);end=date(2025,4,6)
    p=_payload(start,end)
    del p['properties']['parameter']['T2M']['20250403']
    del p['properties']['parameter']['T2M']['20250404']
    with pytest.raises(ValueError,match='gap'):_parse_growing_season(p,start,end)
    p=_payload(start,end)
    del p['properties']['parameter']['PRECTOTCORR']['20250401']
    with pytest.raises(ValueError,match='gap'):_parse_growing_season(p,start,end)


def test_small_field_one_nasa_cell_but_far_apart_fields_differ():
    poly1=Polygon([(68.10,42.10),(68.11,42.10),(68.11,42.11),(68.10,42.11)])
    poly2=Polygon([(68.10,43.10),(68.11,43.10),(68.11,43.11),(68.10,43.11)])
    a=polygon_sample_locations(poly1);b=polygon_sample_locations(poly2)
    assert len(a)==len(b)==1
    assert a[0].latitude!=b[0].latitude


def test_nominal_centres_and_area_conservation():
    p=Polygon([(68.38,42.19),(68.55,42.19),(68.55,42.4),(68.38,42.4)])
    samples=polygon_sample_locations(p)
    assert len(samples)>1
    assert sum(s.area_weight for s in samples)==pytest.approx(1.)
    assert all((s.latitude/.5).is_integer() and (s.longitude/.625).is_integer() for s in samples)


def _month(month,temp):
    return MonthlyWeather(month, temp, temp+5, temp-5,50.,2.,99.,20.,30.)


def test_future_season_climate_from_selected_polygon_not_district():
    calls=[]
    def f(lat,lon):
        calls.append((lat,lon))
        return tuple(_month(m,lat-20) for m in range(4,10))
    def wet(lat,lon):return lat/100
    p=Polygon([(68.1,42.1),(68.11,42.1),(68.11,42.11),(68.1,42.11)])
    a=fetch_farm_climate_normal(42.1,68.1,geometry=p,fetch_point=f,fetch_wetness=wet)
    b=fetch_farm_climate_normal(43.1,68.1,
       geometry=Polygon([(68.1,43.1),(68.11,43.1),(68.11,43.11),(68.1,43.11)]),
       fetch_point=f,fetch_wetness=wet)
    assert a['Apr-Sep temperature, °C']!=b['Apr-Sep temperature, °C']
    assert a['Apr-Sep root-zone wetness']!=b['Apr-Sep root-zone wetness']
    assert a['polygon_sample_count']==1
    assert 'NASA POWER' in a['source']


def test_future_normal_rejects_incomplete_source():
    with pytest.raises(ValueError,match='Incomplete'):
        fetch_farm_climate_normal(42,68,fetch_point=lambda lat,lon:(),
            fetch_wetness=lambda lat,lon:.25)


def test_polygon_daily_weather_real_dates_and_bad_series():
    p=Polygon([(68.35,42.22),(68.6,42.22),(68.6,42.33),(68.35,42.33)])
    start=date(2025,4,1);end=date(2025,4,2)
    def fetch(lat,lon,start,end):
        return tuple(DailyWeather(start+timedelta(days=i),26.,30.,22.,40.,2.,99.,18.,3.)
                     for i in range(2))
    out=fetch_polygon_daily_weather(p,start=start,end=end,fetch_point=fetch)
    assert len(out)==2 and out[0].rain_mm==3.
    count=0
    def bad(lat,lon,start,end):
        nonlocal count
        count+=1
        arr=fetch(lat,lon,start,end)
        return arr if count==1 else arr[:1]
    with pytest.raises(ValueError,match='Incomplete'):
        fetch_polygon_daily_weather(p,start=start,end=end,fetch_point=bad)


def _soil_json():
    props=[]
    for name in PROPERTIES:
        val=20 if name=='clay' else 40 if name=='sand' else 40 if name=='silt' else 7
        props.append({'name':name,'unit_measure':{'d_factor':10},'depths':[
            {'label':z,'values':{'mean':val*10}} for z in DEPTHS]})
    return {'properties':{'layers':props}}


def test_soil_properties_are_indicative_not_fertility_measurement():
    data=parse_soilgrids_response(_soil_json())
    assert data['values']['clay']['0-5cm']==20
    result=indicative_texture_from_soilgrids(data)
    assert result['faopreset']=='loam'
    assert 'not measured' in result['status']


def test_soil_none_is_unknown_not_zero():
    d=_soil_json();d['properties']['layers'][0]['depths'][0]['values']={'mean':None}
    p=parse_soilgrids_response(d)
    assert '0-5cm' not in p['values']['clay']
    with pytest.raises(ValueError):indicative_texture_from_soilgrids(p)


def test_a8_uses_canonical_app_reference_not_old_illustration():
    data=json.loads((Path(__file__).resolve().parents[1]/'examples'/'a8_maktaaral_100ha_inputs.json').read_text())
    t=data['technical_assumptions']
    assert t['pump_electricity_kwh_per_m3_field_delivery']==PUMPING_REFERENCE_KWH_PER_M3
    assert t['grid_kg_co2e_per_kwh']==DEFAULT_EF_KZ_KGCO2_PER_KWH
    assert t['pump_electricity_kwh_per_m3_field_delivery']!=.35


def test_a8_2026_recalculation_stress_and_temperature_only_ssp():
    r=generate_a8_crosscheck()
    assert r['ordinary_economic_optimum']['baseline']['contribution_margin_kzt']==pytest.approx(7222216.71667,abs=.01)
    assert r['ordinary_economic_optimum']['optimized']['contribution_margin_kzt']==pytest.approx(8130941.405,abs=.01)
    assert r['stress']['optimized']['contribution_margin_kzt']==pytest.approx(-3188622.569,abs=.01)
    for name in ['SSP2-4.5','SSP5-8.5']:
        s=r['climate_scenarios'][name]
        assert 1<s['water_multiplier']<1.1
        assert 'temperature TERM only' in s['method']
        assert s['reoptimized']['status']=='optimal_enumerated_candidates'
        assert s['reoptimized']['optimized']['water_field_delivery_m3']<=750000+1e-6
        assert s['reoptimized']['optimized']['contribution_margin_kzt']>0
