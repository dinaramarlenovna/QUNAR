"""Environmental guard: economic uplift must not silently endorse more water/GHG."""
import pytest
from core.green_guard import evaluate_green_guard as assess, alert_text


def test_more_margin_water_and_ghg_triggers_red():
    a = assess(water_before_m3=725500, water_after_m3=750000,
               ghg_before_kgco2e=364441.9, ghg_after_kgco2e=376780.4,
               margin_before_kzt=7222217, margin_after_kzt=8130941)
    assert a['status']=='red'
    assert a['water_change_m3']==24500
    assert a['partial_ghg_change_kgco2e']==pytest.approx(12338.5)
    assert a['full_footprint_certified'] is False
    assert a['legally_noncompliant'] is None
    assert 'Маржа увеличивается' in alert_text(a,'ru')[1]


def test_more_margin_one_resource_increase_still_red():
    a = assess(water_before_m3=100,water_after_m3=110,
               ghg_before_kgco2e=100,ghg_after_kgco2e=80,
               margin_before_kzt=50,margin_after_kzt=100)
    assert a['status']=='red'
    assert a['ghg_increase'] is False


def test_more_ghg_with_margin_drop_still_red():
    a = assess(water_before_m3=100,water_after_m3=80,
               ghg_before_kgco2e=100,ghg_after_kgco2e=120,
               margin_before_kzt=100,margin_after_kzt=90)
    assert a['status']=='red'


def test_water_and_emission_reduction_is_conditionally_positive_not_certificate():
    a = assess(water_before_m3=100,water_after_m3=70,
               ghg_before_kgco2e=100,ghg_after_kgco2e=80)
    assert a['status']=='green_conditional'
    assert not a['full_footprint_certified']


def test_missing_emissions_is_not_zero_or_green():
    a = assess(water_before_m3=100,water_after_m3=70)
    assert a['status']=='incomplete'
    assert 'GHG' in a['unknown_comparisons']
    assert a['partial_ghg_change_kgco2e'] is None


def test_missing_emissions_and_water_increase_warns():
    a = assess(water_before_m3=100,water_after_m3=110,
               margin_before_kzt=100, margin_after_kzt=110)
    assert a['status']=='red'
    assert a['partial_ghg_change_kgco2e'] is None


def test_statutory_breach_not_inferred_from_optional_user_limit():
    a = assess(water_before_m3=100,water_after_m3=90,water_cap_m3=85,
               ghg_before_kgco2e=100, ghg_after_kgco2e=80)
    assert a['status']=='red' and a['explicit_water_cap_breached']
    assert a['legally_noncompliant'] is None


def test_infeasible_baseline_not_a_real_green_gain():
    a = assess(water_before_m3=150,water_after_m3=90,
               ghg_before_kgco2e=200,ghg_after_kgco2e=150,comparable=False)
    assert a['status']=='noncomparable'


@pytest.mark.parametrize('bad',[-1,float('nan'),float('inf'),'nothing'])
def test_invalid_water_rejected(bad):
    with pytest.raises(ValueError):
        assess(water_before_m3=bad,water_after_m3=1)


def test_negative_margin_allowed_as_loss():
    a = assess(water_before_m3=100,water_after_m3=120,
               ghg_before_kgco2e=100,ghg_after_kgco2e=120,
               margin_before_kzt=-100,margin_after_kzt=-50)
    assert a['status']=='red' and a['margin_change_kzt']==50


def test_zero_zero_not_a_certificate():
    a = assess(water_before_m3=0, water_after_m3=0,
               ghg_before_kgco2e=0, ghg_after_kgco2e=0)
    assert a['status']=='neutral'


def test_language_has_no_mixed_text_in_heading():
    d=assess(water_before_m3=100,water_after_m3=120,
             ghg_before_kgco2e=100,ghg_after_kgco2e=120)
    for lang in ['ru','kk','en']:
        heading, msg, action=alert_text(d,lang)
        assert all(isinstance(x,str) and x for x in (heading,msg,action))


def test_integrated_engine_carries_guard_into_results():
    from core.integrated_scenarios import compare_farm_scenario
    r = compare_farm_scenario(
        farm_kind='crop', period='one season', evidence='hypothetical matched season',
        water_before_m3=100, water_after_m3=120,
        electricity_before_kwh=100, electricity_after_kwh=130,
        grid_emission_kgco2e_kwh=0.7,
        water_tariff_kzt_m3=5, electricity_tariff_kzt_kwh=20,
        revenue_before_kzt=20000, revenue_after_kzt=30000,
        other_cost_before_kzt=10000, other_cost_after_kzt=10000,
        costs_complete=True)
    assert r['green_guard']['status']=='red'
    assert r['green_guard']['water_change_m3']==20
    assert r['green_guard']['partial_ghg_change_kgco2e']==pytest.approx(21)


def test_a8_case_contains_warning_and_stress_counterfactual():
    from core.a8_reproducible_case import calculate_case, load_case, report_markdown
    r = calculate_case(load_case())
    assert r['normal_environmental_guard']['status']=='red'
    assert r['stress_environmental_guard']['status']=='noncomparable'
    report=report_markdown(r)
    assert 'ENVIRONMENTAL WARNING' in report
    assert 'financial outcome is retained' in report


def test_water_only_increase_without_known_margin_is_amber():
    a = assess(water_before_m3=100,water_after_m3=110,
               ghg_before_kgco2e=80, ghg_after_kgco2e=70)
    assert a['status']=='amber'
