"""Headless end-to-end A8 stress, monetary and water/GHG conservation tests."""
import copy
import math
import pytest
from core.a8_reproducible_case import calculate_case, load_case, report_markdown

@pytest.fixture(scope='module')
def example():
    return calculate_case(load_case())

def test_three_crops_reference_are_supported_and_traceable(example):
    assert [row['code'] for row in example['crop_reference_rows']] == ['Cotton','Corn','Wheat']
    for row in example['crop_reference_rows']:
        assert row['yield_years'] == [2023,2024,2025]
        assert row['price_source']
        assert row['water_source_tier'] == 'direct'
        assert row['water_m3_ha'] > 0

def test_area_and_allocation_caps(example):
    for period in ('normal','stress'):
        x=example[period]['optimized_areas_ha']
        assert math.isclose(sum(x.values()),100,abs_tol=1e-6)
        assert len(x)==3
        assert min(x.values()) >= 3-1e-7
        assert max(x.values()) <= 60+1e-7

def test_stress_has_joint_shocks_and_water_constraint(example):
    n=example['normal']; s=example['stress']
    assert n['baseline']['water_feasible'] is True
    assert n['optimized']['water_feasible'] is True
    assert s['unchanged_baseline_infeasible'] is True
    assert s['baseline_counterfactual']['water_feasible'] is False
    assert s['optimized']['water_feasible'] is True
    assert s['water_budget_m3']==600000
    assert math.isclose(s['baseline_counterfactual_water_shortfall_m3'],125500)
    assert s['optimizer_status'] == 'optimal_enumerated_candidates'
    assert s['optimized']['water_field_delivery_m3'] <= 600000+1e-6

def test_normal_margin_change_only_when_both_feasible(example):
    n=example['normal']
    assert math.isclose(n['margin_change_same_conditions_kzt'],
            n['optimized']['contribution_margin_kzt']-n['baseline']['contribution_margin_kzt'])
    assert n['margin_change_same_conditions_kzt']>0
    assert n['water_change_same_conditions_m3']>0 # margin improvement does NOT imply water saving

def test_stress_costs_raise_and_yield_revenue_falls(example):
    n=example['normal']['baseline']; s=example['stress']['baseline_counterfactual']
    assert s['water_field_delivery_m3']==n['water_field_delivery_m3']
    assert s['revenue_kzt']==pytest.approx(.90*n['revenue_kzt'])
    assert s['variable_cost_kzt']==pytest.approx(1.10*n['variable_cost_kzt'])
    assert s['partial_ghg_kg_co2e']==pytest.approx(n['partial_ghg_kg_co2e'])

def test_ghg_is_matched_same_factors_period(example):
    for period in ('normal','stress'):
        key='ghg_difference' if period=='normal' else 'ghg_difference_vs_infeasible_baseline'
        comp=example[period][key]
        assert comp['status'].startswith('counterfactual')
        assert comp['change_kgco2e']==pytest.approx(comp['scenario_kgco2e']-comp['baseline_kgco2e'])

def test_invalid_areas_and_missing_inputs_rejected():
    data=load_case()
    data['baseline_crop_shares']['Cotton']=.60
    with pytest.raises(ValueError, match='add to one'):
        calculate_case(data)
    data=load_case(); del data['crop_activities']['Wheat']['other_variable_cost_kzt_ha']
    with pytest.raises(ValueError, match='Missing'):
        calculate_case(data)

def test_ghg_factors_not_silently_ignored():
    data=load_case()
    data['technical_assumptions']['n2o_gwp100']=200
    with pytest.raises(ValueError, match='GWP100'):
        calculate_case(data)

def test_artifact_text_exposes_limits_and_source(example):
    text=report_markdown(example)
    for required in ('infeasible', 'BNS', '2023–2025', '2025', 'NOT', '125 500', '24.7m'):
        assert required in text

def test_result_hash_is_reproducible():
    a=calculate_case(load_case())
    b=calculate_case(load_case())
    assert a['input_sha256']==b['input_sha256']
    assert a['normal']['optimized_areas_ha']==b['normal']['optimized_areas_ha']
