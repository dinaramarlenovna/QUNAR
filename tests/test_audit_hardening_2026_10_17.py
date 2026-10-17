import pytest
from core.economic_feasibility import economic_feasibility
from core.carbon_scenarios import partial_inventory, compare_partial_inventory

@pytest.mark.parametrize("kwargs", [
    {"water_m3_ha":-1}, {"water_tariff_kzt_m3":-1},
    {"energy_kwh_ha":-1}, {"electricity_tariff_kzt_kwh":-1},
    {"yield_centners_ha":float("nan")}, {"selling_price_kzt_t":float("inf")},
    {"variable_cost_kzt_ha":-2},
])
def test_economic_no_invalid_activity(kwargs):
    with pytest.raises(ValueError):
        economic_feasibility(**kwargs)

def test_carbon_increase_cannot_be_called_reduction():
    a=partial_inventory(nitrogen_kg=100,diesel_litres=50,electricity_kwh=100,grid_kg_co2e_kwh=.6)
    b=partial_inventory(nitrogen_kg=200,diesel_litres=50,electricity_kwh=100,grid_kg_co2e_kwh=.6)
    result=compare_partial_inventory(a,b)
    assert result["direction"]=="increase"
    assert result["possible_reduction_kgco2e"]==0
    assert result["possible_increase_kgco2e"]>0
