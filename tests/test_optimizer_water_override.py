import pytest
from core.optimizer import optimize_structure
from core.optimization_guard import validate_allocation

BASE=dict(district='Saryagash District',area_ha=100,n_crops=2,max_share=.60,available_water_m3=310000)
CROPS={'Картофель':2000.0,'Пшеница':4000.0}

def call(**kwargs):
    return optimize_structure(**BASE,water_requirement_by_product=CROPS,
        water_constraint_definition='field_delivery',
        water_requirement_evidence='User confirmed net irrigation/field-application scenario',
        water_requirement_confirmed=True,**kwargs)


def test_explicit_crop_specific_water_constraint_not_official_norm():
    alloc,info=call()
    assert not alloc.empty
    assert info['water_accounting_basis']=='field_delivery'
    assert set(alloc['product'])==set(CROPS)
    assert all(row['constraint_water_m3_ha']==pytest.approx(CROPS[row['product']]) for _,row in alloc.iterrows())
    assert float(alloc['modelled_water_m3'].sum())<=BASE['available_water_m3']+1e-6
    assert validate_allocation(alloc,info,area_ha=100,available_water_m3=310000,max_share=.60,n_crops=2)['ok']


def test_infeasible_source_vs_field_same_budget():
    d,info=optimize_structure(**BASE,water_requirement_by_product={'Картофель':3500,'Пшеница':4000},
        water_constraint_definition='source_withdrawal',water_requirement_evidence='User scenario',
        water_requirement_confirmed=True)
    assert d.empty
    assert info['water_feasible'] is False


def test_missing_input_crops_not_silently_filled_from_official_reference():
    d,info=optimize_structure(**BASE,water_requirement_by_product={'Картофель':2000},
        water_constraint_definition='field_delivery',water_requirement_evidence='User scenario',
        water_requirement_confirmed=True)
    assert d.empty
    assert info['solver_status']=='infeasible_crop_count_or_cap'


def test_custom_water_without_source_or_confirmation_rejected():
    with pytest.raises(ValueError,match='documented source'):
        optimize_structure(**BASE,water_requirement_by_product=CROPS,
            water_requirement_evidence='',water_requirement_confirmed=True)


def test_water_boundary_cannot_be_unknown():
    with pytest.raises(ValueError,match='field_delivery or source_withdrawal'):
        optimize_structure(**BASE,water_requirement_by_product=CROPS,
            water_constraint_definition='root_zone_net',water_requirement_evidence='Scenario',
            water_requirement_confirmed=True)


def test_negative_and_nonfinite_custom_water_rejected():
    for bad in (-1,float('nan'),float('inf')):
        with pytest.raises(ValueError,match='Invalid water requirement'):
            optimize_structure(**BASE,water_requirement_by_product={'Картофель':bad,'Пшеница':1000},
                water_requirement_evidence='Scenario',water_requirement_confirmed=True)


def test_default_objective_still_labels_reference_norm():
    _,info=optimize_structure('Saryagash District',100,max_share=.25,n_crops=5,available_water_m3=520000)
    assert info['water_accounting_basis']=='official_reference'
