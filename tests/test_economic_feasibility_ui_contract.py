"""Regression for app.py economic_feasibility keyword contract."""

from core.economic_feasibility import economic_feasibility


def test_user_cost_excludes_water_energy_keyword_supported():
    out = economic_feasibility(
        yield_centners_ha=30, selling_price_kzt_t=100000,
        variable_cost_kzt_ha=100000, water_m3_ha=1000,
        water_tariff_kzt_m3=2, energy_kwh_ha=200,
        electricity_tariff_kzt_kwh=25, variable_cost_includes_water_energy=False,
    )
    assert out["contribution_margin_kzt_ha"] == 193000
    assert out["variable_cost_includes_water_energy"] is False


def test_inclusive_costs_not_deducted_twice():
    out = economic_feasibility(
        yield_centners_ha=30, selling_price_kzt_t=100000,
        variable_cost_kzt_ha=107000, water_m3_ha=1000,
        water_tariff_kzt_m3=2, energy_kwh_ha=200,
        electricity_tariff_kzt_kwh=25, variable_cost_includes_water_energy=True,
    )
    assert out["contribution_margin_kzt_ha"] == 193000
    assert out["resource_cost_kzt_ha"] == 7000
