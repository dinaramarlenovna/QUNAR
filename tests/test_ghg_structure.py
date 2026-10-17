import pytest
from core.ghg_structure import compare_crop_structures,structure_inventory

BASE={'Cotton':60,'Wheat':40}
PLAN={'Cotton':20,'Wheat':80}
ACT={'Cotton':{'nitrogen_kg_ha':100,'diesel_litres_ha':70,'electricity_kwh_ha':100},
     'Wheat':{'nitrogen_kg_ha':50,'diesel_litres_ha':30,'electricity_kwh_ha':50}}


def test_crop_structure_automatic_aggregation():
    r=compare_crop_structures(baseline_areas=BASE,proposed_areas=PLAN,
        baseline_activity_per_ha=ACT,grid_factor=.7,evidence='user assumptions',confirmed=True)
    assert r['baseline_area_ha']==pytest.approx(100)
    assert r['baseline_activities']['nitrogen_kg_ha']==pytest.approx(8000)
    assert r['proposed_activities']['nitrogen_kg_ha']==pytest.approx(6000)
    assert r['baseline_kgco2e']>r['scenario_kgco2e']
    assert r['intensities_assumption']=='fixed_per_crop'


def test_missing_per_crop_is_not_zero():
    for val in ({'Cotton':ACT['Cotton']}, {'Cotton':ACT['Cotton'],'Wheat':{'diesel_litres_ha':0}}):
        with pytest.raises(ValueError):compare_crop_structures(baseline_areas=BASE,proposed_areas=PLAN,
            baseline_activity_per_ha=val,grid_factor=.7,evidence='source',confirmed=True)


def test_confirmation_and_provenance_required():
    with pytest.raises(ValueError): compare_crop_structures(baseline_areas=BASE,proposed_areas=PLAN,
        baseline_activity_per_ha=ACT,grid_factor=.7,evidence='source',confirmed=False)
    with pytest.raises(ValueError): structure_inventory(BASE,ACT,grid_factor=.7,evidence='',confirmed=True)


def test_no_area_change_without_disclosure():
    with pytest.raises(ValueError):compare_crop_structures(baseline_areas=BASE,proposed_areas={'Wheat':99},
       baseline_activity_per_ha=ACT,grid_factor=.7,evidence='source',confirmed=True)


def test_crop_technology_change_optional():
    new={**ACT,'Wheat':{**ACT['Wheat'],'electricity_kwh_ha':75}}
    r=compare_crop_structures(baseline_areas=BASE,proposed_areas=PLAN,
       baseline_activity_per_ha=ACT,proposed_activity_per_ha=new,
       grid_factor=.7,evidence='source',confirmed=True)
    assert r['intensities_assumption']=='user_scenario_per_crop'


def test_nan_negative_or_missing_for_active_crop_rejected():
    for v in (-1,float('nan'),None):
        bad={**ACT,'Wheat':{**ACT['Wheat'],'nitrogen_kg_ha':v}}
        with pytest.raises(ValueError):structure_inventory(BASE,bad,grid_factor=.7,evidence='source',confirmed=True)
