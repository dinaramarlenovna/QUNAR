"""Protect experimental MCDA / rolling ML benchmark from leakage and false AHP claims."""
from pathlib import Path
import numpy as np
import pandas as pd
from scripts.stage2_mcda_full_validation import ahp_two_criteria, topsis, entropy_climate_weight, critic_climate_weight
from scripts.stage2_ml_multimodel_rolling import WINDOWS, metric, fit_and_predict, CAT, NUM, TARGET

def test_ahp_weights_reconstruct_but_do_not_claim_elicitation():
    a=ahp_two_criteria(.6)
    assert np.allclose(a['reconstructed_weights'], [.6,.4])
    assert np.allclose(a['matrix'][0][1]*a['matrix'][1][0],1)
    assert 'not elicited' in a['consistency'].lower()

def test_topsis_identical_all_equal():
    arr=np.full((15,2),50.)
    assert np.allclose(topsis(arr,.6), .5)

def test_topsis_single_ideal():
    vals=np.array([[100,100],[0,0],[40,40]],float)
    res=topsis(vals,.6)
    assert np.isclose(res[0],1)
    assert np.isclose(res[1],0)

def test_weighting_alternatives_are_finite():
    vals=np.array([[25,90],[45,75],[90,20]],float)
    for meth in (entropy_climate_weight,critic_climate_weight):
        assert 0<=meth(vals)<=1

def test_chronological_splits_no_future_training():
    for train_end,start,end in WINDOWS:
        assert 2004<train_end<start<=end<=2025

def test_historical_median_only_uses_training():
    tr=pd.DataFrame([{'Crop':'Corn','District':'D','Year':2019,TARGET:10},
                      {'Crop':'Corn','District':'D','Year':2020,TARGET:14}])
    te=pd.DataFrame([{'Crop':'Corn','District':'D','Year':2025,TARGET:1e9}])
    assert np.isclose(fit_and_predict('Historical median',tr,te)[0],12)

def test_metrics_calculated_from_numeric_values():
    m=metric([10,20],[12,18])
    assert m['n'] if 'n' in m else m['MAE']==2
    assert m['RMSE']==2

def test_evidence_contains_all_17_districts_and_15_crops():
    out=Path(__file__).resolve().parents[1]/'examples'/'stage2_evidence'
    d=pd.read_csv(out/'mcda_mc_15crops_17districts.csv')
    assert d.district.nunique()==17
    assert (d.groupby('district').size()==15).all()
    for c in ['mc_weight_only_top1_fraction','mc_weight_plus_3pt_top1_fraction']:
        assert np.allclose(d.groupby('district')[c].sum().to_numpy(), 1, atol=1e-9)
