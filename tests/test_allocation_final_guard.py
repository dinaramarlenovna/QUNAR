import pandas as pd
import pytest
from core.optimization_guard import validate_allocation
from core.optimizer import optimize_structure
from core.irrigation_economics import irrigation_comparison
from core.water_norms import default_water_requirement

def _candidate(water=(107000,128000,107000,59000,110000)):
    return pd.DataFrame({'share':[.2]*5, 'area_ha':[20.]*5,'modelled_water_m3':water})

def test_report_guard_rejects_water_deficit():
    check=validate_allocation(_candidate(), {'water_feasible':True}, area_ha=100,
        available_water_m3=350000,max_share=.25,n_crops=5)
    assert not check['ok']
    assert check['water_deficit_m3']==pytest.approx(161000)
    assert 'water_budget_breached' in check['reasons']

def test_report_guard_rejects_cap_violation():
    df=_candidate((107000,128000,107000,59000,110000))
    df['share']=[.30,.20,.20,.20,.10]
    df['area_ha']=df['share']*100
    res=validate_allocation(df,{},area_ha=100,available_water_m3=600000,max_share=.25,n_crops=5)
    assert not res['ok'] and 'max_share_breached' in res['reasons']

def test_report_guard_accepts_reconciled_scenario():
    df=pd.DataFrame({'share':[.25,.25,.25,.22,.03], 'area_ha':[25,25,25,22,3],
         'modelled_water_m3':[133750,160000,133750,64900,16500]})
    check=validate_allocation(df,{'water_feasible':True},area_ha=100,
        available_water_m3=520000,max_share=.25,n_crops=5)
    assert check['ok']
    assert check['modelled_water_m3']==pytest.approx(508900)

def test_optimizer_350k_no_claimed_gain():
    margins={'Картофель':300000, 'Помидоры':500000,'Кукуруза (маис)':175000,
             'Пшеница':9000,'Хлопок, очищенный или не очищенный от семян':92700}
    baseline={'Картофель':15,'Помидоры':20,'Кукуруза (маис)':20,
              'Пшеница':25,'Хлопок, очищенный или не очищенный от семян':20}
    a,s=optimize_structure('Saryagash District',100,max_share=.25,n_crops=5,
        available_water_m3=350000,economic_margin_by_product=margins,
        objective_mode='balanced',baseline_share_by_product=baseline)
    assert a.empty and not s['water_feasible']
    assert s.get('economic_gain_kzt') is None

def test_optimizer_valid_plan_520k():
    margins={'Картофель':300000,'Помидоры':500000,'Кукуруза (маис)':175000,
             'Пшеница':9000,'Хлопок, очищенный или не очищенный от семян':92700}
    baseline={'Картофель':15,'Помидоры':20,'Кукуруза (маис)':20,
              'Пшеница':25,'Хлопок, очищенный или не очищенный от семян':20}
    a,s=optimize_structure('Saryagash District',100,max_share=.25,n_crops=5,
        available_water_m3=520000,economic_margin_by_product=margins,
        objective_mode='balanced',baseline_share_by_product=baseline)
    assert not a.empty and s['water_feasible'] and a['modelled_water_m3'].sum() <= 520000+1e-5
    assert validate_allocation(a,s,area_ha=100,available_water_m3=520000,max_share=.25,n_crops=5)['ok']

def test_irrigation_numbers_current_treatment():
    orig=default_water_requirement('Saryagash District','Corn','furrow').m3_ha
    drip=default_water_requirement('Saryagash District','Corn','drip').m3_ha
    assert orig==5350 and drip==4280
    x=irrigation_comparison(baseline_yield_centners_ha=50, price_kzt_t=105000,
        other_variable_cost_kzt_ha=326000, baseline_water_m3_ha=orig,
        proposed_water_m3_ha=drip, baseline_energy_kwh_ha=420,
        proposed_energy_kwh_ha=420, water_tariff_kzt_m3=.845,
        electricity_tariff_kzt_kwh=45.9872,yield_change_pct=0,
        extra_technology_cost_kzt_ha=15000,
        evidence='Scenario: no validated yield effect; 0%')
    assert x['water_saving_m3_ha']==1070
    assert x['margin_change_kzt_ha']==pytest.approx(-14095.85)
