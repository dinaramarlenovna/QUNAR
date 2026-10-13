import pytest
from core.irrigation_economics import irrigation_comparison


def args():
    return dict(baseline_yield_centners_ha=100, price_kzt_t=100000,
                other_variable_cost_kzt_ha=500000, baseline_water_m3_ha=7000,
                proposed_water_m3_ha=4000, baseline_energy_kwh_ha=200,
                proposed_energy_kwh_ha=250, water_tariff_kzt_m3=10,
                electricity_tariff_kzt_kwh=30, yield_change_pct=0,
                extra_technology_cost_kzt_ha=15000, evidence='Explicit what-if assumption')


def test_effect_and_stress():
    x = irrigation_comparison(**args())
    assert x['baseline_margin_kzt_ha'] == 424000
    assert x['proposed_margin_kzt_ha'] == 437500
    assert x['margin_change_kzt_ha'] == 13500
    assert x['water_saving_m3_ha'] == 3000
    assert x['stress_margin_change_kzt_ha'] == pytest.approx(14850)


def test_yield_effect_changes_margin():
    a = args(); a['yield_change_pct'] = 10
    x = irrigation_comparison(**a)
    assert x['proposed_yield_centners_ha'] == pytest.approx(110)
    assert x['margin_change_kzt_ha'] == pytest.approx(113500)


def test_source_required():
    a = args(); a['evidence'] = ''
    with pytest.raises(ValueError):
        irrigation_comparison(**a)


def test_invalid_cost_rejected():
    a = args(); a['extra_technology_cost_kzt_ha'] = -10
    with pytest.raises(ValueError):
        irrigation_comparison(**a)
