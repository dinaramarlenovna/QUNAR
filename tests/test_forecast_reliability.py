from pathlib import Path
from core.forecast_reliability import evaluate_forecast_support
DATA=Path(__file__).resolve().parents[1]/'data'

def test_otyrar_corn_warns_on_transfer_and_crop():
    x=evaluate_forecast_support(DATA,'Otyrar District','Corn')
    assert x.low_confidence and x.district_n==11 and x.district_r2<0

def test_cotton_warns_on_low_crop_r2():
    x=evaluate_forecast_support(DATA,'Sauran District','Cotton')
    assert x.low_confidence and x.crop_r2<0.5

def test_wheat_cv_can_be_acceptable_in_some_territories():
    x=evaluate_forecast_support(DATA,'Tulkibas District','Wheat')
    assert not x.low_confidence


def test_district_moderately_low_r2_also_warns(tmp_path):
    # R²=0.32 is weak even though it is not negative; 25 records exceed sample threshold.
    (tmp_path/'model_metrics_leave_one_district_out.csv').write_text(
        'District,N,MAE,RMSE,R2\nExample District,25,2,3,0.32\n', encoding='utf-8')
    (tmp_path/'model_metrics_by_crop.csv').write_text(
        'Crop,N,MAE,RMSE,R2\nWheat,80,2,3,0.85\n', encoding='utf-8')
    result=evaluate_forecast_support(tmp_path,'Example District','Wheat')
    assert result.low_confidence
    assert any('district transfer R2' in x for x in result.reasons)
