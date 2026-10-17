"""Regressions for cross-module reconciliation before QŪNAR v0.8.1 delivery."""
import sys
from importlib.util import find_spec
import types
import pytest
from core.economics import economic_climate_effect
from core.resources import calculate_resources
from core.reference_fallbacks import conditional_pumping_energy, irrigation_water_fallback, optional_observation
from core.pumping_billing import pumping_kwh_per_m3, water_and_pumping_cost
from core.regional_tariffs import REGIONAL_TARIFF_REFERENCES
from core.water_norms import default_water_requirement, DISTRICT_ZONE

BASE_ARGS=dict(electricity_tariff=41.06, water_tariff=1.16, emission_factor=.813,
               current_solar_share=0.,target_solar_share=25.,water_saving_target=10.)

def test_unknown_energy_does_not_produce_zero_cost_or_bogus_joint_saving():
    d=economic_climate_effect(energy_kwh=None,freshwater_m3=2000.,**BASE_ARGS)
    assert d['current_grid_energy_kwh'] is None
    assert d['current_energy_cost_kzt'] is None and d['current_co2_kg'] is None
    assert d['co2_reduction_kg'] is None and d['total_saving_kzt'] is None
    assert d['water_saving_kzt']==pytest.approx(232.)
    assert d['missing_components']==['electricity']

def test_unknown_water_does_not_produce_zero_cost_or_joint_saving():
    d=economic_climate_effect(energy_kwh=1000.,freshwater_m3=None,**BASE_ARGS)
    assert d['current_water_cost_kzt'] is None
    assert d['water_saving_kzt'] is None and d['total_saving_kzt'] is None
    assert d['energy_saving_kzt']==pytest.approx(10265.)

def test_confirmed_zero_is_different_from_missing():
    missing=optional_observation(0,measured_zero=False)
    real_zero=optional_observation(0,measured_zero=True)
    assert missing is None and real_zero==0
    d=economic_climate_effect(energy_kwh=0.,freshwater_m3=0.,**BASE_ARGS)
    assert d['total_saving_kzt']==0 and d['data_completeness_status']=='complete'

def test_undeclared_energy_remains_unknown_in_resource_module():
    d=calculate_resources(area_ha=10,water_used_m3=80000.,energy_kwh=None)
    assert 'reference_pumping_energy_kwh' not in d
    assert 'operational_co2e_kg' not in d and 'energy_kwh' not in d

@pytest.mark.parametrize('district',list(DISTRICT_ZONE))
def test_17_territory_water_reference_finite_and_positive_for_cotton(district):
    x=default_water_requirement(district,'Cotton','furrow')
    assert x.m3_ha>0
    assert x.source_tier in ('direct','zone_fallback','regional_fallback')

@pytest.mark.parametrize('crop,norm', [('Cotton',8400.),('Corn',7450.),('Wheat',4100.)])
def test_maktaaral_water_same_2025_2026_norm_excerpts(crop,norm):
    assert default_water_requirement('Maktaaral District',crop,'furrow').m3_ha==pytest.approx(norm)

def test_pump_physical_factor_and_no_double_charge():
    energy=pumping_kwh_per_m3(25,.65)
    assert energy==pytest.approx(.10480769230769231)
    a=water_and_pumping_cost(water_m3=1000., water_tariff_kzt_m3=1.16,
        mode='gravity_with_separate_onfarm_pump',own_pump_kwh_m3=energy,
        own_electricity_tariff_kzt_kwh=41.06)
    assert a['total_kzt']==pytest.approx(1160+1000*energy*41.06)
    b=water_and_pumping_cost(water_m3=1000., water_tariff_kzt_m3=44.12,
        mode='purchased_mechanized_inclusive')
    assert b['own_pumping_electricity_kwh']==0
    with pytest.raises(ValueError):
        water_and_pumping_cost(water_m3=1000., water_tariff_kzt_m3=44.12,
            mode='purchased_mechanized_inclusive', own_pump_kwh_m3=energy)

def test_water_and_electricity_rates_are_dated_separately():
    e=REGIONAL_TARIFF_REFERENCES['electric_retail_commercial_2025_11_exvat']
    assert e.value_kzt_unit==41.06 and '2025' in str(e.source_date)
    assert e.tax_basis.startswith('excl VAT') and e.user_confirmation_required
    a=REGIONAL_TARIFF_REFERENCES['kazvodkhoz_irrigation_gravity_2026']
    assert a.value_kzt_unit==1.16 and a.tax_basis=='excl VAT'

def test_irrigation_rainfed_is_not_zero_crop_water():
    r=irrigation_water_fallback('Saryagash District','Wheat',10.,'rainfed')
    assert r.value==0 and r.source_tier=='technology_configured_zero'
    assert 'not total crop water demand' in r.caveat

def test_complete_d8_recomputes_correctly_with_separate_carbon_cap():
    from pathlib import Path
    import json
    p=Path(__file__).resolve().parents[1]/'examples'/'final_d8_2026_10_18'/'canonical_exVAT_41p06.json'
    d=json.loads(p.read_text())
    assert d['input']['technical_assumptions']['grid_kg_co2e_per_kwh']==.813
    assert d['input']['technical_assumptions']['pump_electricity_kwh_per_m3_field_delivery']==pytest.approx(pumping_kwh_per_m3(25,.65))
    assert len(d['rows'])==8
    assert d['rows'][4]['areas_ha'] is None and d['rows'][6]['areas_ha'] is None
    for i in (2,5,7):
        r=d['rows'][i]
        assert r['water_m3']<=750000.001
        assert r['partial_ghg_kgco2e']<=d['rows'][0]['partial_ghg_kgco2e']+.001
