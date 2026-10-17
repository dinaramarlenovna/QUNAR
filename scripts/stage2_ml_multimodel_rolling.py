"""Exploratory fixed-parameter, forward-year benchmark; NEVER auto-replaces production RF.
Comparison time windows intentionally avoid future-year training leakage.
2021-25 already examined in earlier audits so it is not a pristine confirmatory holdout.
"""
from __future__ import annotations
import os, time, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from catboost import CatBoostRegressor
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'/'analytical_panel.csv'
OUT=ROOT/'examples'/'stage2_evidence'
NUM=['Sown area, th. ha','Apr-Sep temperature, °C','Apr-Sep precipitation, mm','Apr-Sep root-zone wetness','Apr-Sep solar radiation, MJ/m²/day']
CAT=['District','Crop'];TARGET='Yield, centners/ha'
WINDOWS=[(2010,2011,2015),(2015,2016,2020),(2020,2021,2025)]
SEED=42

def model(kind):
    pre=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CAT),('num',StandardScaler(),NUM)])
    kinds={
        'Pooled RF':RandomForestRegressor(n_estimators=250,min_samples_leaf=2,random_state=SEED,n_jobs=2),
        'ExtraTrees':ExtraTreesRegressor(n_estimators=250,min_samples_leaf=2,random_state=SEED,n_jobs=2),
        'Ridge':Ridge(alpha=10),
        'HistGradientBoosting':HistGradientBoostingRegressor(max_iter=120,max_leaf_nodes=15,l2_regularization=10,random_state=SEED),
    }
    return Pipeline([('pre',pre),('model',kinds[kind])])

def metric(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float)
    return {'MAE':float(mean_absolute_error(y,p)),'RMSE':float(np.sqrt(mean_squared_error(y,p))),
            'R2':float(r2_score(y,p)) if len(y)>1 else None,
            'WAPE_percent':float(100*np.abs(y-p).sum()/np.abs(y).sum()) if np.abs(y).sum()>1.e-10 else None}

def fit_and_predict(kind,tr,te):
    if kind=='Historical median':
        dc=tr.groupby(CAT)[TARGET].median(); cm=tr.groupby('Crop')[TARGET].median();gm=tr[TARGET].median()
        return np.array([dc.get((r.District,r.Crop),cm.get(r.Crop,gm)) for r in te.itertuples(index=False)])
    if kind=='Per-crop RF':
        preds=np.full(len(te),np.nan)
        for crop in te.Crop.unique():
            ct=tr[tr.Crop.eq(crop)]
            mask=te.Crop.eq(crop).to_numpy()
            pre=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['District']),('num',StandardScaler(),NUM)])
            estimator=Pipeline([('pre',pre),('model',RandomForestRegressor(n_estimators=250,min_samples_leaf=2,random_state=SEED,n_jobs=2))])
            estimator.fit(ct[['District']+NUM],ct[TARGET])
            preds[mask]=estimator.predict(te.loc[mask,['District']+NUM])
        assert np.isfinite(preds).all()
        return preds
    if kind=='CatBoost':
        cats=CAT+NUM
        estimator=CatBoostRegressor(iterations=300,depth=5,learning_rate=.05,l2_leaf_reg=6,
                loss_function='RMSE',random_seed=SEED,verbose=False,thread_count=2,
                cat_features=CAT,allow_writing_files=False)
        estimator.fit(tr[cats],tr[TARGET]);return estimator.predict(te[cats])
    estimator=model(kind)
    estimator.fit(tr[CAT+NUM],tr[TARGET]);return estimator.predict(te[CAT+NUM])

def run(out=OUT):
    started=time.time();d=pd.read_csv(DATA)
    d=d[d['Use in 2.3 inference'].astype(str)=='Yes'].copy()
    assert not d[CAT+NUM+[TARGET]].isna().any().any()
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    kinds=['Historical median','Pooled RF','Per-crop RF','Ridge','ExtraTrees','HistGradientBoosting','CatBoost']
    rows=[];preds=[];windows=[]
    for train_end,test_start,test_end in WINDOWS:
        tr=d[d.Year.between(2004,train_end)].copy();te=d[d.Year.between(test_start,test_end)].copy()
        assert tr.Year.max()<te.Year.min()
        windows.append({'train_start':2004,'train_end':train_end,'test_start':test_start,'test_end':test_end,'n_train':len(tr),'n_test':len(te)})
        for kind in kinds:
            p=fit_and_predict(kind,tr,te)
            score=metric(te[TARGET],p)
            rows.append({'model':kind,'crop':'ALL','district':'ALL','train_end':train_end,'test_start':test_start,'test_end':test_end,'n':len(te),**score})
            for crop,grp in te.groupby('Crop'):
                ix=te.index.get_indexer(grp.index)
                rows.append({'model':kind,'crop':crop,'district':'ALL','train_end':train_end,'test_start':test_start,'test_end':test_end,'n':len(grp),**metric(grp[TARGET],p[ix])})
            for district,grp in te.groupby('District'):
                ix=te.index.get_indexer(grp.index)
                rows.append({'model':kind,'crop':'ALL','district':district,'train_end':train_end,'test_start':test_start,'test_end':test_end,'n':len(grp),**metric(grp[TARGET],p[ix])})
            preds.extend({'model':kind,'crop':str(row.Crop),'district':str(row.District),'year':int(row.Year),
                      'observed_yield':float(y),'predicted_yield':float(pp),'train_end':train_end}
                     for row,y,pp in zip(te.itertuples(index=False),te[TARGET].to_numpy(),p))
        print('Finished window',train_end,test_start,test_end,'time_s',int(time.time()-started),flush=True)
    scores=pd.DataFrame(rows);raw=pd.DataFrame(preds)
    scores.to_csv(out/'ml_rolling_models_by_crop_district.csv',index=False,encoding='utf-8-sig')
    raw.to_csv(out/'ml_rolling_predictions_all.csv',index=False,encoding='utf-8-sig')
    totals=[];crops=[];dists=[]
    for model_name,g in raw.groupby('model'):
        for period, group in [('earlier_only',g[g.year<=2020]),('late_exploratory',g[g.year>=2021]),('all_three',g)]:
            totals.append({'model':model_name,'period':period,'n':len(group),**metric(group.observed_yield,group.predicted_yield)})
            for crop,gg in group.groupby('crop'):
                crops.append({'model':model_name,'period':period,'crop':crop,'n':len(gg),**metric(gg.observed_yield,gg.predicted_yield)})
            for district,gg in group.groupby('district'):
                dists.append({'model':model_name,'period':period,'district':district,'n':len(gg),**metric(gg.observed_yield,gg.predicted_yield)})
    totals=pd.DataFrame(totals);crops=pd.DataFrame(crops);dists=pd.DataFrame(dists)
    for name,tab in [('ml_rolling_overall.csv',totals),('ml_rolling_by_crop.csv',crops),('ml_rolling_by_district.csv',dists)]:
        tab.to_csv(out/name,index=False,encoding='utf-8-sig')
    e=totals[totals.period=='earlier_only'].sort_values('MAE')
    best=str(e.iloc[0]['model']);late=totals[totals.period=='late_exploratory'].sort_values('MAE')
    summary={'methods':kinds,'windows':windows,'hyperparameters_fixed_no_test_tuning':True,
      'best_pooled_MAE_earlier_windows':best,'selection_from_earlier_only':True,
      'earlier_metrics':e.to_dict(orient='records'),'late_metrics':late.to_dict(orient='records'),
      'caveats':['Late window already analyzed in previous audits: this is a retrospective comparison not independent confirmatory verification.',
        'Preprocessing fitted only on earlier training years; historical median avoids any future-year leakage.',
        'Inputs use contemporaneous sowing area and full Apr–Sep climate, so outputs are not pre-season forecasts.',
        'Different crops have different yields; pooled MAE/R2 can mask deterioration in individual crops.',
        'No hyperparameter search or deployment selection, no refit of the packaged model.'],
      'runtime_seconds':round(time.time()-started,1)}
    (out/'ml_multimodel_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary
if __name__=='__main__':
    r=run();print('EARLIER',[(x['model'],round(x['MAE'],2)) for x in r['earlier_metrics']]);print('LATE',[(x['model'],round(x['MAE'],2)) for x in r['late_metrics']])
