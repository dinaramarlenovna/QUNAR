"""Regression tests for matched carbon accounting assumptions."""
import pytest
from core.carbon_scenarios import partial_inventory, compare_partial_inventory

BASE = dict(nitrogen_kg=100, diesel_litres=20, electricity_kwh=300,
            grid_kg_co2e_kwh=.6)

def test_changed_grid_factor_cannot_create_fictitious_emission_saving():
    a=partial_inventory(**BASE,accounting_period='apr_sep')
    b=partial_inventory(**(BASE | {'grid_kg_co2e_kwh': .2}),accounting_period='apr_sep')
    with pytest.raises(ValueError, match='factor'):
        compare_partial_inventory(a,b)

def test_different_periods_cannot_be_compared():
    a=partial_inventory(**BASE, accounting_period='apr_sep')
    b=partial_inventory(**BASE, accounting_period='calendar_year')
    with pytest.raises(ValueError, match='period'):
        compare_partial_inventory(a,b)

@pytest.mark.parametrize('key,factor', [('nitrogen_kg','n2o_factor'), ('diesel_litres','diesel_factor'), ('electricity_kwh','grid_kg_co2e_kwh')])
def test_positive_activity_requires_nonzero_factor(key, factor):
    args=BASE | {factor:0}
    with pytest.raises(ValueError, match='positive'):
        partial_inventory(**args)

def test_valid_identical_period_and_factors_compare():
    a=partial_inventory(**BASE,accounting_period='apr_sep')
    b=partial_inventory(**(BASE | {'nitrogen_kg':80}),accounting_period='apr_sep')
    d=compare_partial_inventory(a,b)
    assert d['possible_reduction_kgco2e']>0

def test_seasonal_livestock_methane_is_prorated_when_selected():
    args = BASE | dict(include_enteric=True, enteric_heads=10, enteric_kg_ch4_head_year=50)
    annual=partial_inventory(**args,enteric_year_fraction=1,accounting_period='calendar_year')
    seasonal=partial_inventory(**args,enteric_year_fraction=183/365,accounting_period='apr_sep')
    assert seasonal.components['enteric_methane_kgco2e'] == pytest.approx(annual.components['enteric_methane_kgco2e']*183/365)
