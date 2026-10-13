import pytest
from core.optimizer import optimize_structure
from core.economic_feasibility import economic_feasibility
from core.irrigation_economics import irrigation_comparison

DISTRICT = "Saryagash District"

def test_hard_water_limit_does_not_fabricate_allocation():
    alloc, info = optimize_structure(DISTRICT,100,n_crops=5,max_share=.25,available_water_m3=1)
    assert alloc.empty
    assert info['water_feasible'] is False
    assert info['solver_status'] == 'infeasible_under_hard_constraints'
    assert info.get('optimized_contribution_margin_kzt') is None

def test_cap_infeasible_not_relaxed():
    alloc, info = optimize_structure(DISTRICT,100,n_crops=3,max_share=.25)
    assert alloc.empty and info['solver_status'] == 'infeasible_crop_count_or_cap'

def test_feasible_solution_respects_hard_constraints():
    alloc, info = optimize_structure(DISTRICT,100,n_crops=5,max_share=.3,available_water_m3=10000000)
    assert not alloc.empty
    assert info['water_feasible']
    assert abs(alloc['area_ha'].sum()-100)<1e-5
    assert alloc['share'].max() <= .3+1e-7
    assert alloc['modelled_water_m3'].sum() <= 10000000

def test_variable_cost_double_count_prevented():
    args=dict(yield_centners_ha=100,selling_price_kzt_t=100000,variable_cost_kzt_ha=400000,
              water_m3_ha=1000,water_tariff_kzt_m3=2,energy_kwh_ha=100,
              electricity_tariff_kzt_kwh=10)
    a=economic_feasibility(**args)
    b=economic_feasibility(**args,variable_cost_includes_water_energy=True)
    assert b['contribution_margin_kzt_ha'] - a['contribution_margin_kzt_ha'] == 3000

def test_irrigation_scenario_requires_evidence():
    with pytest.raises(ValueError):
        irrigation_comparison(baseline_yield_centners_ha=100,price_kzt_t=100000,
          other_variable_cost_kzt_ha=100000,baseline_water_m3_ha=4000,proposed_water_m3_ha=3000,
          baseline_energy_kwh_ha=100,proposed_energy_kwh_ha=150,water_tariff_kzt_m3=1,
          electricity_tariff_kzt_kwh=40,yield_change_pct=10,extra_technology_cost_kzt_ha=10000,evidence='')

from core.economic_validation import EconomicInput, compare_structures

def test_stress_uses_same_shocks_both_plans():
    x=EconomicInput('Wheat',100,2,100000,100000,3000,'Example assumption')
    y=EconomicInput('Wheat',100,2.2,100000,105000,3100,'Example assumption')
    r=compare_structures([x],[y],350000)
    assert r['valid_comparison']
    assert r['economic_gain_kzt']==pytest.approx(1500000)
    assert r['stress_gain_kzt'] is not None

def test_overbudget_not_reported_as_economic_gain():
    x=EconomicInput('Wheat',100,2,100000,100000,4000,'assumption')
    r=compare_structures([x],[x],350000)
    assert not r['valid_comparison']
    assert r['economic_gain_kzt'] is None
