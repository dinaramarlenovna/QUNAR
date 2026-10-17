import pytest
from core.structure_water_scenarios import compare_structure_water

KW = dict(baseline_areas={'Wheat':60,'Cotton':40},
          proposed_areas={'Wheat':40,'Cotton':60},
          net_irrigation_m3_ha={'Wheat':2000,'Cotton':4000},
          baseline_field_efficiency_by_crop={'Wheat':.6,'Cotton':.6},
          proposed_field_efficiency_by_crop={'Wheat':.9,'Cotton':.9},
          evidence='Explicit hypothetical illustration',confirmed=True)


def test_mixed_crop_structure_totals():
    r=compare_structure_water(**KW)
    assert r['baseline']['root_zone_net_m3']==pytest.approx(280000)
    assert r['proposed']['root_zone_net_m3']==pytest.approx(320000)
    assert r['baseline']['field_delivery_m3']==pytest.approx(280000/.6)
    assert r['proposed']['field_delivery_m3']==pytest.approx(320000/.9)
    assert r['difference']['field_delivery_m3_reduction']==pytest.approx(111111.111111)
    assert r['difference']['source_withdrawal_m3_reduction'] is None
    assert r['difference']['irrigation_depletion_proxy_m3_reduction'] is None


def test_source_withdrawal_conditional():
    r=compare_structure_water(**KW,conveyance_efficiency=.8)
    assert r['difference']['source_withdrawal_m3_reduction']==pytest.approx(111111.111111/.8)


def test_full_return_recovery_can_result_in_increased_depletion_despite_lower_delivery():
    extras=dict(baseline_recoverable_by_crop={'Wheat':1,'Cotton':1},
                proposed_recoverable_by_crop={'Wheat':1,'Cotton':1})
    r=compare_structure_water(**KW,**extras)
    assert r['difference']['field_delivery_m3_reduction']>0
    assert r['difference']['irrigation_depletion_proxy_m3_reduction']==pytest.approx(-40000)


def test_returns_and_conveyance_balance():
    r=compare_structure_water(**KW,conveyance_efficiency=.8,
        baseline_recoverable_by_crop={'Wheat':.5,'Cotton':.5},
        proposed_recoverable_by_crop={'Wheat':.5,'Cotton':.5},
        baseline_conveyance_recovery=.25,proposed_conveyance_recovery=.25)
    for item in (r['baseline'],r['proposed']):
        assert item['source_withdrawal_m3']==pytest.approx(
          item['irrigation_depletion_proxy_m3']+item['recoverable_return_m3'])


def test_missing_crop_fails_not_zero():
    with pytest.raises(ValueError,match='required for crop'):
        compare_structure_water(**{**KW, 'net_irrigation_m3_ha':{'Wheat':2000}})


def test_cannot_fabricate_unobserved_baseline():
    with pytest.raises(ValueError,match='farm areas'):
        compare_structure_water(**{**KW, 'baseline_areas':{'Wheat':60}})


def test_bad_fraction_rejected():
    with pytest.raises(ValueError,match='field efficiency'):
        compare_structure_water(**{**KW, 'proposed_field_efficiency_by_crop':{'Wheat':1.2,'Cotton':.9}})


def test_no_evidence_no_calc():
    with pytest.raises(ValueError,match='confirmation required'):
        compare_structure_water(**{**KW,'evidence':''})


def test_zero_net_is_valid_if_explicit():
    r=compare_structure_water(**{**KW,'net_irrigation_m3_ha':{'Wheat':0,'Cotton':4000}})
    assert r['baseline']['root_zone_net_m3']==pytest.approx(160000)


def test_nan_fails():
    with pytest.raises(ValueError,match='Invalid'):
        compare_structure_water(**{**KW,'net_irrigation_m3_ha':{'Wheat':float('nan'),'Cotton':4000}})
