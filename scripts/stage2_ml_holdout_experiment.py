"""Exploratory independent 2021-2025 comparison; does not alter production model.

Train on 2004-2020 only. Every preprocessing and baseline statistic is fitted
on the training period, never on held-out 2021-2025 observations.
"""
from pathlib import Path
import csv, json
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'/'analytical_panel.csv'
OUT=ROOT/'examples'/'stage2_evidence'
NUM=['Sown area, th. ha','Apr-Sep temperature, °C','Apr-Sep precipitation, mm','Apr-Sep root-zone wetness','Apr-Sep solar radiation, MJ/m²/day']
CAT=['District','Crop']; TARGET='Yield, centners/ha'

def model(cats=CAT,kind='rf'):
    pre=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore'),cats),('num',StandardScaler(),NUM)])
    estimator=(RandomForestRegressor(n_estimators=350,random_state=42,min_samples_leaf=2,n_jobs=1)
               if kind=='rf' else Ridge(alpha=10.0))
    return Pipeline([('pre',pre),('model',estimator)])

def score(y,p):
    y=np.asarray(y,dtype=float);p=np.asarray(p,dtype=float)
    return {'n':len(y), 'MAE':float(mean_absolute_error(y,p)),
            'RMSE':float(mean_squared_error(y,p)**.5),
            'R2':float(r2_score(y,p)) if len(y)>=2 else None,
            'WAPE_percent':float(np.sum(np.abs(y-p))/np.sum(np.abs(y))*100) if np.sum(np.abs(y))>0 else None}

def run(output_dir=OUT):
    df=pd.read_csv(DATA);df=df[df['Use in 2.3 inference'].astype(str)=='Yes'].copy()
    tr=df[df.Year.between(2004,2020)].copy();te=df[df.Year.between(2021,2025)].copy()
    assert set(tr.Year).isdisjoint(te.Year)
    assert len(tr)+len(te)==len(df)
    pooled=model().fit(tr[CAT+NUM],tr[TARGET])
    ridge=model(kind='ridge').fit(tr[CAT+NUM],tr[TARGET])
    te['Pooled RF']=pooled.predict(te[CAT+NUM]);te['Pooled Ridge']=ridge.predict(te[CAT+NUM])
    dc=tr.groupby(CAT)[TARGET].median(); cm=tr.groupby('Crop')[TARGET].median();gm=tr[TARGET].median()
    te['Historical median']=[dc.get((r.District,r.Crop),cm.get(r.Crop,gm)) for r in te.itertuples(index=False)]
    te['Per-crop RF']=np.nan
    for crop in sorted(te.Crop.unique()):
        ctr=tr[tr.Crop==crop];test_idx=te.index[te.Crop==crop]
        m=model(cats=['District']).fit(ctr[['District']+NUM],ctr[TARGET])
        te.loc[test_idx,'Per-crop RF']=m.predict(te.loc[test_idx,['District']+NUM])
    rows=[];methods=['Pooled RF','Historical median','Per-crop RF','Pooled Ridge']
    for crop,g in [('All',te)]+list(te.groupby('Crop')):
        for method in methods:
            rows.append({'crop':crop,'method':method,'train_end':2020,'test_start':2021,'test_end':2025,
                         **score(g[TARGET],g[method])})
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/'ml_holdout_2021_2025_by_crop.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
    # Small production-readable table: actual forward test of the packaged RF
    # architecture, not an estimate of performance on a newly received farm.
    with (ROOT/'data'/'forecast_holdout_2021_2025_metrics.csv').open('w',newline='',encoding='utf-8-sig') as f:
        selected=[r for r in rows if r['method']=='Pooled RF']
        w=csv.DictWriter(f,fieldnames=list(selected[0]));w.writeheader();w.writerows(selected)
    comparison=[]
    for crop in sorted(te.Crop.unique()):
        rr={x['method']:x for x in rows if x['crop']==crop}
        best=min(methods,key=lambda m:rr[m]['MAE'])
        comparison.append({'crop':crop,'best_on_test_exploratory_only':best,'pooled_rf_mae':rr['Pooled RF']['MAE'],
        'historical_median_mae':rr['Historical median']['MAE'],
        'per_crop_rf_mae':rr['Per-crop RF']['MAE'],
        'ridge_mae':rr['Pooled Ridge']['MAE'],
        'pooled_beats_median':rr['Pooled RF']['MAE']<rr['Historical median']['MAE'],
        'warning':'The best method was identified on this test set and cannot be marketed as independently selected or validated.'})
    detail={'splitting':'strict forward 2004-2020 train, 2021-2025 held out',
            'methods':methods, 'overall':{r['method']:r for r in rows if r['crop']=='All'},
            'by_crop':comparison,'training_observations':len(tr),'heldout_observations':len(te),
            'no_production_model_change':True,
            'limitations':['No farm-level independent evaluation', '2021-2025 used to compare methods; any selection needs a different confirmation set', 'Inputs include reported sown area and measured Apr-Sep conditions (not an advance-season prediction)']}
    (out/'ml_holdout_2021_2025.json').write_text(json.dumps(detail,ensure_ascii=False,indent=2),encoding='utf-8')
    return detail

if __name__=='__main__':
    result=run()
    print('N:',result['training_observations'],result['heldout_observations'])
    print('overall:',{k:round(v['MAE'],3) for k,v in result['overall'].items()})
    for x in result['by_crop']:
        print(x['crop'],*[f"{x[k]:.2f}" for k in ['pooled_rf_mae','historical_median_mae','per_crop_rf_mae','ridge_mae']])
