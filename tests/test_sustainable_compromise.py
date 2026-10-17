"""Reproducible sustainability constraints against hypothetical A8 activities."""
import math
import pytest
from core.optimizer import optimize_structure
from core.a8_reproducible_case import load_case, _crop_records, _economics
from core.ghg_structure import structure_inventory


def _kwargs():
    config=load_case(); rows=_crop_records(config); econ=_economics(rows, None)
    t=config['technical_assumptions']
    margins={r['product']:econ[r['product']]['contribution_margin_kzt_ha'] for r in rows}
    shares={r['product']:100*config['baseline_crop_shares'][r['code']] for r in rows}
    ghg={}
    for r in rows:
        a=config['crop_activities'][r['code']]
        inv=structure_inventory({r['product']:1.}, {r['product']:{
            'nitrogen_kg_ha':a['nitrogen_kg_ha'],
            'diesel_litres_ha':a['diesel_litres_ha'],
            'electricity_kwh_ha':r['pump_electricity_kwh_ha']}},
            grid_factor=t['grid_kg_co2e_per_kwh'],
            diesel_factor=t['diesel_kg_co2_per_litre'],
            accounting_period='apr_sep', evidence='Hypothetical A8', confirmed=True)
        ghg[r['product']]=inv['inventory'].known_total_kg_co2e
    return dict(district='Maktaaral District', area_ha=100., n_crops=3,
        max_share=.60, available_water_m3=750000., objective_mode='sustainable',
        economic_margin_by_product=margins, baseline_share_by_product=shares,
        ghg_kg_co2e_by_product=ghg)

@pytest.mark.parametrize('tolerance',[0.,5.,10.])
def test_all_sustainable_guards(tolerance):
    x=_kwargs(); x['sustainable_max_margin_decline_pct']=tolerance
    alloc, summary=optimize_structure(**x)
    assert summary['solver_status']=='optimal_enumerated_candidates'
    assert len(alloc)==3
    v=summary['sustainable_comparison']
    assert v['all_constraints_met']
    assert math.isclose(alloc['area_ha'].sum(),100,abs_tol=1e-6)
    assert all((alloc['share']>=.03-1e-9)&(alloc['share']<=.60+1e-9))
    assert v['optimized_water_m3']<=v['baseline_water_m3']+1e-6
    assert v['optimized_water_m3']<=750000+1e-6
    assert v['optimized_partial_ghg_kg_co2e']<=v['baseline_partial_ghg_kg_co2e']+1e-6
    assert v['optimized_margin_kzt']>=v['minimum_margin_kzt']-1e-6
    if tolerance==0:
        assert v['optimized_margin_kzt']>=v['baseline_margin_kzt']-1e-6
        assert v['optimized_partial_ghg_kg_co2e']<v['baseline_partial_ghg_kg_co2e']
        assert v['optimized_water_m3']<v['baseline_water_m3']

@pytest.mark.parametrize('field, status',[('baseline_share_by_product','sustainable_needs_complete_baseline'),
    ('ghg_kg_co2e_by_product','sustainable_missing_baseline_ghg'),
    ('economic_margin_by_product','sustainable_missing_baseline_margins')])
def test_incomplete_inputs_fail_closed(field,status):
    x=_kwargs(); x[field]={}
    df,summary=optimize_structure(**x)
    assert df.empty and summary['solver_status']==status

def test_invalid_baseline_total_rejected():
    x=_kwargs(); first=next(iter(x['baseline_share_by_product'])); x['baseline_share_by_product'][first]=0
    df,summary=optimize_structure(**x)
    assert df.empty and summary['solver_status']=='sustainable_needs_complete_baseline'

def test_invalid_ghg_never_treated_as_zero():
    x=_kwargs(); first=next(iter(x['ghg_kg_co2e_by_product'])); x['ghg_kg_co2e_by_product'][first]=None
    df,summary=optimize_structure(**x)
    assert df.empty and summary['solver_status']=='sustainable_missing_baseline_ghg'

def test_margin_floor_not_silently_relaxed():
    x=_kwargs(); x['sustainable_max_margin_decline_pct']=-1
    df,summary=optimize_structure(**x)
    assert df.empty and summary['solver_status']=='invalid_margin_tolerance'

def test_insufficient_water_returns_no_solution():
    x=_kwargs(); x['available_water_m3']=100000
    df,summary=optimize_structure(**x)
    assert df.empty and summary['solver_status']=='infeasible_under_hard_constraints'

def test_existing_economic_mode_unchanged():
    x=_kwargs(); x['objective_mode']='economic'; x['economic_weight']=.70
    df,summary=optimize_structure(**x)
    assert not df.empty and summary['economic_objective_mode']=='economic'
    assert summary['sustainable_comparison'] is None
