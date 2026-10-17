"""Regression checks for A4/A6/A7/A8 batch scientific audit."""
import copy
import json
from pathlib import Path
import pytest
from core.cmip6_scenarios import (load_scenario, weighted_temperature_anomaly,
                                   precipitation_anomaly_pct, cckp_csv_series)
from core.survey_weights import audit_survey_aggregates, survey_proxy_profile
from core.forecast_reliability import evaluate_forecast_support

DATA=Path(__file__).resolve().parents[1]/'data'


def test_actual_cmip6_and_scenario_temperature_consistent():
    middle=load_scenario(DATA/'cmip6','SSP2-4.5')
    high=load_scenario(DATA/'cmip6','SSP5-8.5')
    assert 2.00<middle.temperature_change_c<2.02
    assert 2.67<high.temperature_change_c<2.69
    assert middle.days_over_35_monthly[0]>=middle.days_over_40_monthly[0]>=middle.days_over_45_monthly[0]


def test_cmip6_rejects_invalid_month_count():
    with pytest.raises(ValueError,match='six finite'):
        weighted_temperature_anomaly([1.0,2.0])
    with pytest.raises(ValueError,match='six finite'):
        weighted_temperature_anomaly([1.0,float('nan'),2,3,4,5])
    with pytest.raises(ValueError,match='Invalid or unmatched'):
        precipitation_anomaly_pct([1.,2.],[10.])
    with pytest.raises(ValueError,match='Invalid or unmatched'):
        precipitation_anomaly_pct([1.],[-10.])


def test_cmip6_refuses_duplicate_and_non_finite_csv(tmp_path):
    path=tmp_path/'test.csv'
    header='Category;SSP2-4.5\n'
    lines=''.join(f'{m};2\n' for m in ('Apr','May','Jun','Jul','Aug','Sep'))
    path.write_text(header+lines+'Apr;3\n',encoding='utf-8')
    with pytest.raises(ValueError,match='Duplicate'):
        cckp_csv_series(path,'SSP2-4.5')
    path.write_text(header+lines.replace('May;2','May;NaN'),encoding='utf-8')
    with pytest.raises(ValueError,match='Non-finite'):
        cckp_csv_series(path,'SSP2-4.5')


def test_survey_aggregate_arithmetic_and_proxy():
    status=audit_survey_aggregates()
    assert status['questions_checked']==10
    assert status['n_responses']==208
    assert survey_proxy_profile()['climate']==pytest.approx(93/213)


def test_survey_single_choice_mismatch_refused(tmp_path):
    d=json.loads((DATA/'survey_2026_aggregates.json').read_text())
    d['questions']['Q1']['counts']['Не повлияли']=1
    path=tmp_path/'bad.json';path.write_text(json.dumps(d,ensure_ascii=False))
    with pytest.raises(ValueError,match='Single-choice Q1'):
        audit_survey_aggregates(path)


def test_survey_source_numerators_cross_checked(tmp_path):
    d=json.loads((DATA/'survey_2026_aggregates.json').read_text())
    d['water_resource_q3_n']=118
    path=tmp_path/'bad.json';path.write_text(json.dumps(d,ensure_ascii=False))
    with pytest.raises(ValueError,match='Water count'):
        audit_survey_aggregates(path)


def test_otyrar_caution_and_tulkibas_wheat_safe():
    assert evaluate_forecast_support(DATA,'Otyrar District','Corn').low_confidence
    assert not evaluate_forecast_support(DATA,'Tulkibas District','Wheat').low_confidence


def test_non_positive_validation_n_is_flagged(tmp_path):
    (tmp_path/'model_metrics_leave_one_district_out.csv').write_text(
      'District,N,R2\nOne,0,0.9\n',encoding='utf-8')
    (tmp_path/'model_metrics_by_crop.csv').write_text(
      'Crop,N,R2\nWheat,80,0.85\n',encoding='utf-8')
    result=evaluate_forecast_support(tmp_path,'One','Wheat')
    assert result.low_confidence
    assert any('invalid' in t for t in result.reasons)
