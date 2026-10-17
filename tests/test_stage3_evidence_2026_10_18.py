import math
import pytest
from core.economic_feasibility import economic_feasibility
from core.carbon_scenarios import partial_inventory, compare_partial_inventory
from core.ghg_structure import structure_inventory

BASE = dict(yield_centners_ha=30,selling_price_kzt_t=100000,variable_cost_kzt_ha=100000)

def test_missing_water_never_costs_zero():
    r=economic_feasibility(**BASE,water_m3_ha=None,water_tariff_kzt_m3=1,
                           energy_kwh_ha=100,electricity_tariff_kzt_kwh=20)
    assert r['water_cost_kzt_ha'] is None and r['contribution_margin_kzt_ha'] is None
    assert r['status']=='resource_data_required'

def test_known_zero_is_not_missing():
    r=economic_feasibility(**BASE,water_m3_ha=0,water_tariff_kzt_m3=None,
                           energy_kwh_ha=0,electricity_tariff_kzt_kwh=None)
    assert r['resource_cost_kzt_ha']==0 and r['contribution_margin_kzt_ha']==200000

def test_missing_energy_cannot_be_free():
    r=economic_feasibility(**BASE,water_m3_ha=100,water_tariff_kzt_m3=1,
                           energy_kwh_ha=None,electricity_tariff_kzt_kwh=20)
    assert r['energy_cost_kzt_ha'] is None and r['contribution_margin_kzt_ha'] is None

def test_inclusive_verified_cost_does_not_need_tariffs_for_margin():
    r=economic_feasibility(**BASE,variable_cost_includes_water_energy=True)
    assert r['contribution_margin_kzt_ha']==200000
    assert r['resource_cost_kzt_ha'] is None

def test_rice_n2o_uses_ipcc_separate_factor_and_climate_flag():
    c=partial_inventory(nitrogen_kg=0,rice_nitrogen_kg=100,rice_water_regime='continuous_flooding',
                        diesel_litres=0,electricity_kwh=0,grid_kg_co2e_kwh=.7)
    assert math.isclose(c.components['flooded_rice_direct_n2o_kgco2e'], 100*.003*44/28*273)
    with pytest.raises(ValueError):
        partial_inventory(nitrogen_kg=0,rice_nitrogen_kg=100,diesel_litres=0,
                          electricity_kwh=0,grid_kg_co2e_kwh=.7)

def test_crop_mix_rice_requires_regime():
    a={'Rice':10}; activity={'Rice':{'nitrogen_kg_ha':100,'diesel_litres_ha':10,'electricity_kwh_ha':50}}
    with pytest.raises(ValueError):
        structure_inventory(a,activity,grid_factor=.7,evidence='scenario',confirmed=True)
    activity['Rice']['rice_water_regime']='drained_once_or_more'
    r=structure_inventory(a,activity,grid_factor=.7,evidence='scenario',confirmed=True)
    assert r['activities_total']['rice_nitrogen_kg']==1000
    assert r['inventory'].complete

def test_same_rice_regime_required_for_compare():
    kw=dict(nitrogen_kg=0,rice_nitrogen_kg=100,diesel_litres=10,
            electricity_kwh=100,grid_kg_co2e_kwh=.7)
    a=partial_inventory(**kw,rice_water_regime='continuous_flooding')
    b=partial_inventory(**kw,rice_water_regime='drained_once_or_more')
    with pytest.raises(ValueError):
        compare_partial_inventory(a,b)
