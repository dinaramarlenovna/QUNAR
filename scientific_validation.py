from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, cross_val_predict

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'analytical_panel.csv'
NUM = ['Sown area, th. ha','Apr-Sep temperature, °C','Apr-Sep precipitation, mm','Apr-Sep root-zone wetness','Apr-Sep solar radiation, MJ/m²/day']
CAT = ['District','Crop']
TARGET = 'Yield, centners/ha'

def make_model(min_leaf=2, max_depth=None, max_features=1.0, n_estimators=250):
    pre = ColumnTransformer([
        ('cat', OneHotEncoder(handle_unknown='ignore'), CAT),
        ('num', StandardScaler(), NUM),
    ])
    rf = RandomForestRegressor(n_estimators=n_estimators, random_state=42, min_samples_leaf=min_leaf,
                               max_depth=max_depth, max_features=max_features, n_jobs=-1)
    return Pipeline([('pre', pre), ('model', rf)])

def metrics(y, p):
    return {'MAE': float(mean_absolute_error(y,p)), 'RMSE': float(mean_squared_error(y,p)**0.5), 'R2': float(r2_score(y,p))}

def fold_baseline(df):
    X=df[CAT+NUM]; y=df[TARGET]; groups=df['Year'].astype(str)
    cv=GroupKFold(n_splits=min(5,groups.nunique()))
    out=pd.Series(index=df.index,dtype=float)
    for tridx, teidx in cv.split(X,y,groups):
        tr=df.iloc[tridx]; te=df.iloc[teidx]
        dc=tr.groupby(['District','Crop'])[TARGET].median(); cm=tr.groupby('Crop')[TARGET].median(); gm=tr[TARGET].median()
        out.iloc[teidx]=[dc.get((r.District,r.Crop),cm.get(r.Crop,gm)) for r in te.itertuples(index=False)]
    return out

def main():
    df=pd.read_csv(DATA).dropna(subset=[TARGET]).copy()
    if 'Use in analytical core' in df.columns:
        df=df[df['Use in analytical core'].astype(str).str.startswith('Yes')].copy()
    if 'Use in 2.3 inference' in df.columns:
        df=df[df['Use in 2.3 inference'].astype(str).str.startswith('Yes')].copy()
    X=df[CAT+NUM]; y=df[TARGET]; groups=df['Year'].astype(str)
    cv=GroupKFold(n_splits=min(5,groups.nunique()))
    pred=cross_val_predict(make_model(),X,y,cv=cv,groups=groups)
    overall=metrics(y,pred)
    per_crop={}
    tmp=df[['Crop',TARGET]].copy(); tmp['pred']=pred
    for crop,g in tmp.groupby('Crop'):
        per_crop[crop]={'N':int(len(g)),**metrics(g[TARGET],g['pred'])}

    model=make_model(n_estimators=350); model.fit(X,y); train_pred=model.predict(X)
    train_metrics=metrics(y,train_pred)

    train=df[df.Year<=2020].copy(); test=df[df.Year>=2021].copy()
    hold=make_model(n_estimators=500); hold.fit(train[CAT+NUM],train[TARGET]); hold_pred=hold.predict(test[CAT+NUM])
    holdout=metrics(test[TARGET],hold_pred); holdout.update({'train_N':int(len(train)),'test_N':int(len(test)),'test_years':sorted(map(int,test.Year.unique()))})

    dc=train.groupby(['District','Crop'])[TARGET].median(); cm=train.groupby('Crop')[TARGET].median(); gm=train[TARGET].median()
    base_hold=np.array([dc.get((r.District,r.Crop),cm.get(r.Crop,gm)) for r in test.itertuples(index=False)])
    hold_baseline=metrics(test[TARGET],base_hold)
    cv_base=metrics(y,fold_baseline(df))

    robust=[]
    settings=[('leaf1',1,None,1.0),('leaf2',2,None,1.0),('leaf4',4,None,1.0),('depth12',2,12,1.0),('sqrt',2,None,'sqrt')]
    for name,leaf,depth,mf in settings:
        p=cross_val_predict(make_model(min_leaf=leaf,max_depth=depth,max_features=mf),X,y,cv=cv,groups=groups)
        robust.append({'specification':name,**metrics(y,p)})

    result={
        'dataset':{'N':int(len(df)),'years':int(df.Year.nunique()),'year_min':int(df.Year.min()),'year_max':int(df.Year.max()),'districts':int(df.District.nunique()),'crops':int(df.Crop.nunique())},
        'groupkfold_by_year':overall,
        'training_fit':train_metrics,
        'chronological_holdout_2021_2023':holdout,
        'baseline_groupkfold':cv_base,
        'baseline_holdout_2021_2023':hold_baseline,
        'per_crop_groupkfold':per_crop,
        'hyperparameter_robustness':robust,
    }
    (ROOT/'data'/'scientific_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[{'scheme':'GroupKFold-by-year RF',**overall},{'scheme':'GroupKFold median baseline',**cv_base},{'scheme':'Chronological 2021-2023 RF',**holdout},{'scheme':'Chronological median baseline',**hold_baseline},{'scheme':'Training fit RF',**train_metrics}]
    pd.DataFrame(rows)[['scheme','MAE','RMSE','R2']].to_csv(ROOT/'data'/'model_metrics.csv',index=False)
    pd.DataFrame([{'Crop':k,**v} for k,v in per_crop.items()]).to_csv(ROOT/'data'/'model_metrics_by_crop.csv',index=False)
    return result

if __name__=='__main__':
    r=main(); print(json.dumps(r,ensure_ascii=False,indent=2))
