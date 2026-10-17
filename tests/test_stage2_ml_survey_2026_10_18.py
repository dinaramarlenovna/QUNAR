"""Regression guards for Stage 2 retrospective quality / survey sensitivity audit."""
import json
from pathlib import Path
import pytest
from core.ml import prediction_interval_for_crop, forward_holdout_for_crop

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'examples/stage2_evidence'


def test_true_temporal_interval_coverage_is_not_claimed_as_nominal_90():
    corn=prediction_interval_for_crop('Corn')
    assert corn['is_forward_backtest'] is True
    assert corn['coverage_target']==pytest.approx(.90)
    assert .65 < corn['empirical_coverage'] < .68
    assert corn['n']==75 and corn['calibration_n']==130
    all_rows=json.loads((EVIDENCE/'ml_forward_interval_coverage.json').read_text())['rows']
    overall=next(row for row in all_rows if row['crop']=='Overall')
    assert overall['holdout_coverage']<.9
    assert overall['holdout_N']==326


def test_earlier_only_method_selection_is_not_passed_off_as_improvement():
    x=json.loads((EVIDENCE/'ml_temporal_method_selection.json').read_text())
    assert x['no_production_model_change'] is True
    assert all(v['chosen']=='Pooled RF' for v in x['selection'].values())
    assert x['test_overall_selected']['MAE']==pytest.approx(x['test_overall_pooled_RF']['MAE'])
    assert 'confirmatory' in x['caution']


def test_survey_agreed_profiles_and_all_17_districts_recomputed():
    x=json.loads((EVIDENCE/'survey_stage2_sensitivity.json').read_text())
    assert x['n']==208 and (x['water_Q3'],x['climate_Q7'])==(120,93)
    assert x['base']=={'climate':.6,'water':.4}
    assert x['proxy']['climate']==pytest.approx(93/213)
    assert x['headline']=={'same_first':17,'same_top3':15}
    assert x['source_comparison_all_match'] is True
    assert len(x['districts'])==17
    assert len(x['weight_grid'])==101
    assert any(p['climate_weight']==.7 and p['same_top1_territories']==11 for p in x['weight_grid'])


def test_report_notifies_historical_interval_limits_in_three_languages():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'Историческое покрытие ML-интервала 2021–2025' in app
    assert 'ML аралығының 2021–2025 жж. тарихи қамтуы' in app
    assert 'ML interval historical coverage 2021–2025' in app
    assert 'Это не гарантия для нового прогноза' in app


def test_future_year_r2_is_reported_by_crop_not_pooled_only():
    rice=forward_holdout_for_crop('Rice')
    wheat=forward_holdout_for_crop('Wheat')
    assert rice['test_start']==2021 and rice['test_end']==2025
    assert rice['train_end']==2020 and rice['n']==17
    assert rice['r2'] < -3.0
    assert wheat['r2'] < .5
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'ML: R² при прогнозе 2021–2025' in app
    assert 'ML: 2021–2025 жж. болжамының R² көрсеткіші' in app
    assert 'ML: forward R² for 2021–2025' in app
