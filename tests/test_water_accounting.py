import pytest
from core.water_accounting import irrigation_water_balance, compare_irrigation_balances


def test_no_conveyance_or_recovery_assumed():
    x=irrigation_water_balance(net_irrigation_m3_ha=3000,field_efficiency=.6)
    assert x.field_applied_m3_ha==pytest.approx(5000)
    assert x.source_withdrawal_m3_ha is None
    assert x.irrigation_attributable_depletion_m3_ha is None
    assert x.field_loss_m3_ha==pytest.approx(2000)


def test_conveyance_source_volume_and_balance():
    x=irrigation_water_balance(net_irrigation_m3_ha=3000,field_efficiency=.6,
        conveyance_efficiency=.8,field_recoverable_fraction=.75,
        conveyance_recoverable_fraction=.5,evidence='hypothetical fractions')
    assert x.source_withdrawal_m3_ha==pytest.approx(6250)
    assert x.conveyance_loss_m3_ha==pytest.approx(1250)
    assert x.recoverable_return_m3_ha==pytest.approx(2125)
    assert x.nonrecoverable_loss_m3_ha==pytest.approx(1125)
    assert x.irrigation_attributable_depletion_m3_ha==pytest.approx(4125)
    assert x.source_withdrawal_m3_ha==pytest.approx(x.irrigation_attributable_depletion_m3_ha+x.recoverable_return_m3_ha)


def test_reduced_applied_water_not_necessarily_lower_depletion():
    a=irrigation_water_balance(net_irrigation_m3_ha=3000,field_efficiency=.6,
                                field_recoverable_fraction=1, evidence='assumed')
    b=irrigation_water_balance(net_irrigation_m3_ha=3000,field_efficiency=.9,
                                field_recoverable_fraction=1,evidence='assumed')
    compare=compare_irrigation_balances(a,b,area_ha=100)
    assert compare['field_delivery_reduction_m3']==pytest.approx(166666.666667)
    assert compare['depletion_proxy_reduction_m3']==pytest.approx(0.0)
    assert compare['source_withdrawal_reduction_m3'] is None
    assert compare['recoverable_return_change_m3']==pytest.approx(-166666.666667)


def test_unrecoverable_losses_may_be_saving_if_assumed():
    a=irrigation_water_balance(net_irrigation_m3_ha=3000,field_efficiency=.6,
        field_recoverable_fraction=0,evidence='assumed')
    b=irrigation_water_balance(net_irrigation_m3_ha=3000,field_efficiency=.9,
        field_recoverable_fraction=0,evidence='assumed')
    assert compare_irrigation_balances(a,b)['depletion_proxy_reduction_m3']==pytest.approx(1666.6666667)


def test_unknown_recovery_never_assumed_zero():
    a=irrigation_water_balance(net_irrigation_m3_ha=3000,field_efficiency=.6,conveyance_efficiency=.8)
    b=irrigation_water_balance(net_irrigation_m3_ha=3000,field_efficiency=.9,conveyance_efficiency=.8)
    res=compare_irrigation_balances(a,b)
    assert res['source_withdrawal_reduction_m3']==pytest.approx((5000-3000/.9)/.8)
    assert res['depletion_proxy_reduction_m3'] is None


@pytest.mark.parametrize('kwargs',[
    {'field_efficiency':0}, {'field_efficiency':1.01},
    {'field_efficiency':float('nan')}, {'net_irrigation_m3_ha':-1},
    {'conveyance_recoverable_fraction':.4},
    {'conveyance_efficiency':0},
    {'field_recoverable_fraction':-0.01},
    {'field_recoverable_fraction':1.1},
    {'evidence':' '},
])
def test_invalid_water_data(kwargs):
    d={'net_irrigation_m3_ha':3000,'field_efficiency':0.6}
    d.update(kwargs)
    with pytest.raises(ValueError):irrigation_water_balance(**d)
