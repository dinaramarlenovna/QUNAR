import pytest
from core.reference_fallbacks import optional_observation, irrigation_water_fallback, conditional_pumping_energy, livestock_drinking_fallback
from core.resources import calculate_resources


def test_missing_and_measured_zero_distinguished():
    assert optional_observation(None) is None
    assert optional_observation(0) is None
    assert optional_observation(0, measured_zero=True) == 0
    assert optional_observation(7) == 7
    with pytest.raises(ValueError): optional_observation(-1)


def test_regulated_crop_water_with_traceable_source():
    r = irrigation_water_fallback('Maktaaral District','Cotton',10,'furrow')
    assert r.value > 0
    assert 'V2500036253' in r.url
    assert 'observ' not in r.source_tier


def test_measured_zero_never_overwritten_by_standard():
    r = irrigation_water_fallback('Maktaaral District','Cotton',10,'furrow',observed=0,measured_zero=True)
    assert r.value == 0
    assert r.source_tier == 'user_observed'


def test_missing_energy_is_not_zero_or_unsupported_pumping():
    assert conditional_pumping_energy(50000).value is None
    assert conditional_pumping_energy(50000,observed=0,measured_zero=True).value == 0
    p=conditional_pumping_energy(50000,pumping_confirmed=True)
    assert p.value is None and p.source_tier == 'unavailable'
    # Explicit scenario opt-in preserves backward-compatible intensity, never automatic.
    tentative=conditional_pumping_energy(50000,pumping_confirmed=True,allow_technology_scenario=True)
    assert tentative.value > 0 and tentative.source_tier == 'technology_scenario'


def test_resources_keep_confirmed_zero():
    r=calculate_resources(5,water_used_m3=0,energy_kwh=0,water_source='user')
    assert r['farm_water_total_m3']==0
    assert r['energy_kwh']==0


def test_physical_pumping_uses_documented_head_efficiency():
    x=conditional_pumping_energy(1000,pumping_confirmed=True,head_m=50,overall_efficiency=.5)
    assert x.value == pytest.approx(272.5)
    assert x.source_tier == 'physical_model'


def test_fao_cattle_drinking_reference_temperature_25():
    r=livestock_drinking_fallback('Cattle',10)
    assert r.value == pytest.approx(73.2*10*365/1000)
    assert 'fao.org' in r.url
    assert r.source_tier == 'international_reference'

def test_livestock_no_herd_is_unknown():
    r=livestock_drinking_fallback('Sheep',0)
    assert r.value is None
