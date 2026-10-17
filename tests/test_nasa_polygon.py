import pytest
from shapely.geometry import Polygon
from core.nasa_polygon import polygon_sample_locations, fetch_polygon_growing_season, WEIGHTED_FIELDS
from core.water_climate import temperature_only_water_sensitivity
from core.carbon_scenarios import partial_inventory, compare_partial_inventory


def test_small_polygon_one_grid_and_conservative_weights():
    g=Polygon([(68.1,42.1),(68.11,42.1),(68.11,42.11),(68.1,42.11)])
    p=polygon_sample_locations(g)
    assert len(p)==1 and p[0].area_weight==pytest.approx(1)


def test_cross_grid_polygon_area_weights_and_fetch():
    g=Polygon([(68.4,42.25),(69.0,42.25),(69.0,42.6),(68.4,42.6)])
    p=polygon_sample_locations(g)
    assert len(p)>1 and sum(x.area_weight for x in p)==pytest.approx(1)
    def get(lat,lon,year):
        return {**{k:1.0 if 'precipitation' not in k else 2.0 for k in WEIGHTED_FIELDS},
                'period_start':'2025-04-01','period_end':'2025-09-30'}
    res=fetch_polygon_growing_season(g,2025,fetch_point=get)
    assert res['Apr-Sep precipitation, mm']==pytest.approx(2.)
    assert res['polygon_sample_count']==len(p)


def test_regional_polygon_preserves_all_cells_and_explicit_limit():
    g=Polygon([(65,40),(70,40),(70,45),(65,45)])
    samples=polygon_sample_locations(g)
    assert len(samples)>16
    assert sum(x.area_weight for x in samples)==pytest.approx(1.)
    with pytest.raises(ValueError,match='intersects|extensive'):
        polygon_sample_locations(g,max_samples=16)


def test_temperature_term_not_full_irrigation():
    z=temperature_only_water_sensitivity(100000,20.0,2)
    assert z.temperature_term_multiplier == pytest.approx((39.8/37.8))
    assert 'NOT' in z.status


def test_partial_emissions_unknown_is_not_zero():
    p=partial_inventory(nitrogen_kg=100,diesel_litres=None,electricity_kwh=0,grid_kg_co2e_kwh=0.8)
    assert 'diesel' in p.missing and not p.complete
    with pytest.raises(ValueError):
        compare_partial_inventory(p,p)


def test_ghg_before_after_full_fields_only():
    a=partial_inventory(nitrogen_kg=10,diesel_litres=20,electricity_kwh=100,grid_kg_co2e_kwh=0.7)
    b=partial_inventory(nitrogen_kg=9,diesel_litres=18,electricity_kwh=80,grid_kg_co2e_kwh=0.7)
    d=compare_partial_inventory(a,b)
    assert d['possible_reduction_kgco2e']>0
