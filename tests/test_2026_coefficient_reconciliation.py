import copy
import pytest
from core.economics import DEFAULT_EF_KZ_KGCO2_PER_KWH
from core.pumping_billing import pumping_kwh_per_m3, water_and_pumping_cost
from core.a8_reproducible_case import _validated_inputs, load_case


def test_new_grid_factor_is_default_reference():
    assert DEFAULT_EF_KZ_KGCO2_PER_KWH == pytest.approx(.813)


def test_engineering_pump_work():
    assert pumping_kwh_per_m3(25,.65) == pytest.approx(.10480769230769231)
    with pytest.raises(ValueError): pumping_kwh_per_m3(25,0)


def test_mechanized_supplier_fee_prevents_pump_double_count():
    fee=water_and_pumping_cost(water_m3=100,water_tariff_kzt_m3=44.12,
        mode='purchased_mechanized_inclusive')
    assert fee['total_kzt']==pytest.approx(4412)
    assert fee['own_pumping_electricity_kwh']==0
    with pytest.raises(ValueError,match='pumping'):
        water_and_pumping_cost(water_m3=100,water_tariff_kzt_m3=44.12,
            mode='purchased_mechanized_inclusive',own_pump_kwh_m3=.1)


def test_gravity_plus_own_pump_counts_both_distinct_services():
    result=water_and_pumping_cost(water_m3=100,water_tariff_kzt_m3=1.16,
        mode='gravity_with_separate_onfarm_pump',own_pump_kwh_m3=.1,
        own_electricity_tariff_kzt_kwh=40)
    assert result['total_kzt']==pytest.approx(516)


def test_a8_requires_nonoverlapping_billing_boundary():
    cfg=load_case()
    cfg['technical_assumptions']['water_supply_service_mode']='purchased_mechanized_inclusive'
    with pytest.raises(ValueError,match='includes provider pumping'):
        _validated_inputs(cfg)
    cfg['technical_assumptions']['pump_electricity_kwh_per_m3_field_delivery']=0.0
    _validated_inputs(cfg)
    cfg['technical_assumptions']['water_supply_service_mode']='gravity_with_separate_onfarm_pump'
    with pytest.raises(ValueError): _validated_inputs(cfg)
