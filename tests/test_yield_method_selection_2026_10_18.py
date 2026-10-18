"""Deterministic guards: ML first only if supported; no future leakage or invented yield."""
from pathlib import Path
import csv
import pandas as pd
from core.yield_method_selection import route_yield, all_method_history
ROOT=Path(__file__).resolve().parents[1]


def test_all_six_trained_crops_fail_predeclared_forward_support():
    for crop in ('Wheat','Corn','Cotton','Rice','Sunflower','Potato'):
        x=route_yield(ROOT/'data','Sauran District',crop,2027,rf_value=30.)
        assert not x.ml_supported
        assert x.rf_value==30.
        assert x.active_method in ('Historical district-crop median','Regional crop median (proxy)','Not verified')
        assert all(y<2027 for y in x.reference_years)


def test_all_other_crops_never_receive_imaginary_ml_prediction():
    d=pd.read_csv(ROOT/'data'/'crop_model_registry.csv')
    for crop in d.Code:
        if crop not in ('Wheat','Corn','Cotton','Rice','Sunflower','Potato'):
            x=route_yield(ROOT/'data','Sauran District',crop,2027,rf_value=None)
            assert x.active_method=='Not verified'
            assert x.active_value is None


def test_verified_rf_can_remain_first(tmp_path):
    (tmp_path/'forecast_holdout_2021_2025_metrics.csv').write_text(
       'crop,n,R2,MAE,WAPE_percent,train_end,test_start,test_end\nWheat,65,0.75,3.2,12,2020,2021,2025\n',encoding='utf-8')
    x=route_yield(tmp_path,'Test district','Wheat',2027,rf_value=21.)
    assert x.ml_supported and x.active_method=='Random Forest' and x.active_value==21.


def test_historic_reference_uses_only_preceding_years(tmp_path):
    (tmp_path/'forecast_holdout_2021_2025_metrics.csv').write_text(
       'crop,n,R2,MAE,WAPE_percent,train_end,test_start,test_end\nWheat,15,-1,5,45,2020,2021,2025\n',encoding='utf-8')
    with (tmp_path/'analytical_panel.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['District','Crop','Year','Yield, centners/ha'])
        for yr,val in [(2019,9),(2020,11),(2021,12),(2025,18),(2026,2000),(2027,9999)]:
            w.writerow(['D','Wheat',yr,val])
    x=route_yield(tmp_path,'D','Wheat',2026,rf_value=35.)
    assert x.active_value==11.5
    assert max(x.reference_years)==2025
    assert x.rf_value==35.


def test_earlier_only_selections_do_not_use_late_holdout():
    rows=all_method_history(ROOT/'examples'/'stage2_evidence','Corn')
    assert len(rows)>=7
    assert all(r['n']>=10 for r in rows)


def test_report_and_interface_have_separate_ml_and_fallback_labels():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert "_original_rf_pred" in app
    assert "_yield_choice = route_yield" in app
    assert "Исторический ориентир (не прогноз)" in app
    assert "Сравнение альтернативных методов прогнозирования" in app
