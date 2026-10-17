"""Offline audit of integrated water → pumping → partial GHG → costs scenario."""
import math
import pytest
from core.integrated_scenarios import (
    FIELD_ETA, irrigation_reference, linked_pump_electricity, compare_farm_scenario,
)


def test_fao_irrigation_reference_furrow_drip_and_no_real_saving_claim():
    x=irrigation_reference(net_m3_ha=3000,area_ha=100,
                           before_method='furrow',after_method='drip')
    assert x['baseline_field_m3']==pytest.approx(500000)
    assert x['scenario_field_m3']==pytest.approx(333333.333333)
    assert (x['baseline_field_m3']-x['scenario_field_m3'])/x['baseline_field_m3']==pytest.approx(1/3)
    assert x['real_basin_saving_m3'] is None
    assert x['baseline_withdrawal_m3'] is None


def test_optional_conveyance_uses_same_boundary():
    x=irrigation_reference(net_m3_ha=2000,area_ha=10,before_method='furrow',
                           after_method='sprinkler',conveyance_efficiency=.8)
    assert x['baseline_withdrawal_m3']==pytest.approx(20000/.6/.8)
    assert x['scenario_withdrawal_m3']==pytest.approx(20000/.75/.8)


@pytest.mark.parametrize('method',('unknown','mixed','rice'))
def test_unknown_efficiency_never_assumed(method):
    with pytest.raises(ValueError):
        irrigation_reference(net_m3_ha=2000,area_ha=10,
                             before_method=method,after_method='drip')


def test_no_doubling_observed_pump_electricity():
    r=linked_pump_electricity(baseline_total_kwh=600000,
                            baseline_water_m3=500000,scenario_water_m3=333333.3333,
                            before_kwh_m3=.7,after_kwh_m3=.9)
    assert r['nonpump_kwh']==pytest.approx(250000)
    assert r['baseline_kwh']==pytest.approx(600000)
    assert r['scenario_kwh']==pytest.approx(550000,abs=1e-2)


def test_drip_pressure_can_increase_pump_energy():
    r=linked_pump_electricity(baseline_water_m3=500000,
                            scenario_water_m3=333333.3333,
                            before_kwh_m3=.7,after_kwh_m3=1.2)
    assert r['scenario_kwh'] > r['baseline_kwh']


def test_incompatible_meter_and_pump_is_rejected():
    with pytest.raises(ValueError, match='smaller'):
        linked_pump_electricity(baseline_total_kwh=100,
                                baseline_water_m3=500,scenario_water_m3=400,
                                before_kwh_m3=.7,after_kwh_m3=.8)


def test_unknown_energy_not_treated_as_zero():
    r=compare_farm_scenario(farm_kind='crop',period='one season', evidence='FAO scenario',
                            water_before_m3=5000,water_after_m3=3500,
                            electricity_before_kwh=None,electricity_after_kwh=None,
                            water_tariff_kzt_m3=10)
    assert r['energy_before_kwh'] is None
    assert r['ghg_before_kgco2e'] is None
    assert r['margin_before_kzt'] is None
    assert r['known_cost_reduction_kzt']==15000


def test_partial_scope2_green_grid_and_cost():
    r=compare_farm_scenario(farm_kind='crop',period='season',evidence='engineering scenario',
                            electricity_before_kwh=20000,electricity_after_kwh=20000,
                            grid_fraction_before=1,grid_fraction_after=.5,
                            grid_emission_kgco2e_kwh=.7,
                            electricity_tariff_kzt_kwh=30,
                            renewable_operating_kzt_kwh=10)
    assert r['energy_reduction_kwh']==0
    assert r['partial_ghg_reduction_kgco2e']==pytest.approx(7000)
    assert r['known_cost_reduction_kzt']==pytest.approx(200000)
    assert r['margin_increase_kzt'] is None


def test_no_free_solar_saving_when_renewable_running_cost_missing():
    r=compare_farm_scenario(farm_kind='crop',period='season', evidence='testing',
                            electricity_before_kwh=100,electricity_after_kwh=100,
                            grid_fraction_before=1.,grid_fraction_after=.1,
                            electricity_tariff_kzt_kwh=100,
                            renewable_operating_kzt_kwh=None)
    assert 'electricity_kzt' not in r['known_cost_components_kzt']
    assert 'electricity_or_renewable_tariff' in r['missing']


def test_all_known_crop_margin_and_changes_consistent():
    r=compare_farm_scenario(farm_kind='crop',period='season',evidence='study assumptions',
                            water_before_m3=10000,water_after_m3=7500,
                            electricity_before_kwh=5000,electricity_after_kwh=4000,
                            water_tariff_kzt_m3=5,electricity_tariff_kzt_kwh=35,
                            grid_emission_kgco2e_kwh=.75,
                            revenue_before_kzt=2e6,revenue_after_kzt=2e6,
                            other_cost_before_kzt=1e6,other_cost_after_kzt=1e6,
                            costs_complete=True)
    assert r['margin_before_kzt']==pytest.approx(2e6-1e6-50000-175000)
    assert r['margin_after_kzt']==pytest.approx(2e6-1e6-37500-140000)
    assert r['margin_increase_kzt']==pytest.approx(47500)
    assert r['partial_ghg_reduction_kgco2e']==pytest.approx(750)


def test_costs_incomplete_means_no_margin_even_with_revenue():
    r=compare_farm_scenario(farm_kind='crop',period='season',evidence='scenario',
                            water_before_m3=100,water_after_m3=80,
                            electricity_before_kwh=20,electricity_after_kwh=12,
                            water_tariff_kzt_m3=10,electricity_tariff_kzt_kwh=30,
                            revenue_before_kzt=1000,revenue_after_kzt=1000,
                            other_cost_before_kzt=500,other_cost_after_kzt=500)
    assert r['margin_increase_kzt'] is None
    assert r['known_cost_reduction_kzt']==pytest.approx(20*10+8*30)


def test_missing_only_one_side_rejected():
    with pytest.raises(ValueError,match='Matched'):
        compare_farm_scenario(farm_kind='crop',period='season',evidence='scenario',
                              n_before_kg=50,n_after_kg=None)


def test_livestock_enteric_evidence_needed_for_factor_change():
    kw=dict(farm_kind='livestock',period='one year',evidence='feed scenario',
            enteric_heads=100,include_enteric=True,
            enteric_ch4_before_kg_head_year=70,
            enteric_ch4_after_kg_head_year=60)
    with pytest.raises(ValueError,match='requires'):
        compare_farm_scenario(**kw)
    r=compare_farm_scenario(**kw,methane_change_evidence='Conditional published factor scenario')
    assert r['partial_ghg_reduction_kgco2e']==pytest.approx(100*10*27)
    assert r['margin_increase_kzt'] is None


def test_n2o_and_diesel_emissions_increase_if_activity_increases():
    r=compare_farm_scenario(farm_kind='crop',period='season',evidence='recorded inputs',
                            n_before_kg=100,n_after_kg=150,
                            diesel_before_l=40,diesel_after_l=100)
    assert r['partial_ghg_reduction_kgco2e']<0
    assert len(r['ghg_components_kgco2e'])==2


def test_non_finite_inputs_and_negative_rejected():
    for v in (-1,float('nan'),float('inf')):
        with pytest.raises(ValueError):
            compare_farm_scenario(farm_kind='crop',period='season',evidence='scenario',
                                  water_before_m3=v,water_after_m3=5)


def test_period_and_kind_required():
    with pytest.raises(ValueError):
        compare_farm_scenario(farm_kind='livestock',period='',evidence='s')
    with pytest.raises(ValueError):
        compare_farm_scenario(farm_kind='weird',period='season',evidence='s')


def test_gas_boundary_is_partial_even_with_complete_costs():
    r=compare_farm_scenario(farm_kind='livestock',period='one year',evidence='farm input',
                            water_before_m3=100,water_after_m3=80,
                            electricity_before_kwh=300,electricity_after_kwh=250,
                            grid_emission_kgco2e_kwh=.8,
                            water_tariff_kzt_m3=20,electricity_tariff_kzt_kwh=30,
                            other_cost_before_kzt=30000,other_cost_after_kzt=30000,
                            revenue_before_kzt=100000,revenue_after_kzt=100000,
                            costs_complete=True)
    assert r['margin_increase_kzt']==pytest.approx(20*20+50*30)
    assert r['partial_ghg_reduction_kgco2e']==pytest.approx(40)
    assert 'partial' in r['ghg_boundary']

def test_mixed_irrigation_uses_area_weighted_harmonic_eta():
    eta=1/(.5/.6+.5/.9)
    r=irrigation_reference(net_m3_ha=1000,area_ha=10,
                           before_method='mixed',after_method='drip',
                           before_efficiency=eta)
    assert r['baseline_field_m3']==pytest.approx(10000/eta)
    assert r['scenario_field_m3']==pytest.approx(10000/.9)


def test_mixed_requires_explicit_valid_efficiency():
    with pytest.raises(ValueError):
        irrigation_reference(net_m3_ha=1000,area_ha=10,
                             before_method='mixed',after_method='drip')
    with pytest.raises(ValueError):
        irrigation_reference(net_m3_ha=1000,area_ha=10,
                             before_method='drip',after_method='mixed',after_efficiency=0)

def test_manure_methane_independent_of_enteric_and_evidence_required():
    kw=dict(farm_kind='livestock',period='year',evidence='feed/manure scenario',
            include_manure=True,enteric_heads=50,
            manure_ch4_before_kg_head_year=10,manure_ch4_after_kg_head_year=6)
    with pytest.raises(ValueError,match='manure'):
        compare_farm_scenario(**kw)
    r=compare_farm_scenario(**kw,manure_change_evidence='Different manure storage, hypothetical')
    assert r['partial_ghg_reduction_kgco2e']==pytest.approx(50*4*27)
    assert 'enteric_methane_kgco2e' not in r['ghg_components_kgco2e']


def test_livestock_no_automatic_methane_reduction_from_water_cut():
    r=compare_farm_scenario(farm_kind='livestock',period='year',evidence='water intervention',
                            water_before_m3=1000,water_after_m3=800,
                            include_enteric=True,enteric_heads=20,
                            enteric_ch4_before_kg_head_year=45,enteric_ch4_after_kg_head_year=45)
    assert r['partial_ghg_reduction_kgco2e']==pytest.approx(0)
    assert r['water_reduction_m3']==200

def test_diesel_already_in_other_cost_is_not_double_charged():
    r=compare_farm_scenario(farm_kind='crop',period='one season',evidence='farm budget',
                            water_before_m3=100,water_after_m3=100,
                            electricity_before_kwh=100,electricity_after_kwh=100,
                            water_tariff_kzt_m3=1,electricity_tariff_kzt_kwh=2,
                            diesel_before_l=20,diesel_after_l=10,diesel_kzt_l=300,
                            diesel_in_other_cost=True,
                            revenue_before_kzt=100000,revenue_after_kzt=100000,
                            other_cost_before_kzt=50000,other_cost_after_kzt=45000,
                            costs_complete=True)
    assert 'diesel_kzt' not in r['known_cost_components_kzt']
    assert r['margin_increase_kzt']==5000
    assert r['partial_ghg_reduction_kgco2e']==pytest.approx(10*2.68)


def test_missing_diesel_price_does_not_allow_complete_margin_unless_in_other_cost():
    r=compare_farm_scenario(farm_kind='crop',period='season',evidence='farm',
                            water_before_m3=100,water_after_m3=90,
                            electricity_before_kwh=50,electricity_after_kwh=40,
                            water_tariff_kzt_m3=1,electricity_tariff_kzt_kwh=2,
                            diesel_before_l=20,diesel_after_l=10,
                            revenue_before_kzt=1000,revenue_after_kzt=1000,
                            other_cost_before_kzt=100,other_cost_after_kzt=100,
                            costs_complete=True)
    assert r['margin_increase_kzt'] is None
