from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GroupKFold, cross_val_predict

import sys, types
if "streamlit" not in sys.modules:
    st=types.ModuleType("streamlit")
    def _cache(*args, **kwargs):
        def deco(fn): return fn
        return deco
    st.cache_data=_cache; st.cache_resource=_cache
    sys.modules["streamlit"]=st

from core.clrem import scenario_for_district, DISTRICT_TO_RU
from core.optimizer import optimize_structure
from core.ml import training_data, FEATURES_NUM, FEATURES_CAT, TARGET

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data'
DISTRICTS=list(DISTRICT_TO_RU.keys())
BASE=np.array([.50,.35,.15])
COMP=['Climate_score_0_100','Resource_efficiency_0_100','Data_reliability_0_100']

def rank_for(df,w):
    score=df[COMP].to_numpy(float)@np.asarray(w,float)
    order=np.argsort(-score, kind='stable'); ranks=np.empty(len(score),dtype=int); ranks[order]=np.arange(1,len(score)+1); return ranks

def top_items(df,w,n=3):
    score=df[COMP].to_numpy(float)@np.asarray(w,float)
    ix=np.argsort(-score)[:n]
    return list(df.iloc[ix]['product'])

def spearman(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float);
    if len(a)<2: return 1.0
    return float(np.corrcoef(a,b)[0,1])

def vif_table(df):
    X=df[FEATURES_NUM].dropna().astype(float)
    rows=[]
    for col in X.columns:
        y=X[col].to_numpy(); Z=X.drop(columns=[col]).to_numpy()
        r2=LinearRegression().fit(Z,y).score(Z,y)
        vif=float('inf') if r2>=.999999999 else 1/(1-r2)
        rows.append({'feature':col,'VIF':vif})
    return pd.DataFrame(rows)

def ml_compare(df):
    X=df[FEATURES_CAT+FEATURES_NUM]; y=df[TARGET]; groups=df['Year'].astype(str)
    cv=GroupKFold(n_splits=min(5,groups.nunique()))
    pre=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore'),FEATURES_CAT),('num',StandardScaler(),FEATURES_NUM)])
    rf=Pipeline([('pre',pre),('model',RandomForestRegressor(n_estimators=350,random_state=42,min_samples_leaf=2,n_jobs=-1))])
    lin=Pipeline([('pre',pre),('model',LinearRegression())])
    prf=cross_val_predict(rf,X,y,cv=cv,groups=groups)
    plin=cross_val_predict(lin,X,y,cv=cv,groups=groups)
    def m(p): return {'MAE':float(mean_absolute_error(y,p)),'RMSE':float(mean_squared_error(y,p)**.5),'R2':float(r2_score(y,p))}
    return {'random_forest':m(prf),'linear':m(plin),'delta_R2_RF_minus_linear':float(r2_score(y,prf)-r2_score(y,plin))}

def main():
    # Ranking sensitivity: OAT ±20%, renormalized; leave-one-component-out; MC 5000 draws.
    rows=[]; loo=[]; mc=[]
    rng=np.random.default_rng(42)
    for district in DISTRICTS:
        df=scenario_for_district(district).reset_index(drop=True)
        if df.empty: continue
        rb=rank_for(df,BASE); tb=top_items(df,BASE,3); leader=top_items(df,BASE,1)[0]
        for j,name in enumerate(COMP):
            for pct in (-.20,.20):
                w=BASE.copy(); w[j]*=(1+pct); w=w/w.sum()
                rr=rank_for(df,w); tt=top_items(df,w,3)
                rows.append({'district':district,'component':name,'change':pct,'spearman':spearman(rb,rr),'top1_retained':int(top_items(df,w,1)[0]==leader),'top3_overlap':len(set(tb)&set(tt))/3,'max_rank_shift':int(np.max(np.abs(rb-rr)))})
            w=BASE.copy(); w[j]=0; w=w/w.sum(); rr=rank_for(df,w); tt=top_items(df,w,3)
            loo.append({'district':district,'removed':name,'spearman':spearman(rb,rr),'top1_retained':int(top_items(df,w,1)[0]==leader),'top3_overlap':len(set(tb)&set(tt))/3,'max_rank_shift':int(np.max(np.abs(rb-rr)))})
        # Dirichlet perturbations centered on baseline; vectorized 5,000 draws per district/scenario.
        vals=df[COMP].to_numpy(float)
        base_order=np.argsort(-(vals@BASE), kind='stable')
        base_ranks=np.empty(len(df),dtype=int); base_ranks[base_order]=np.arange(1,len(df)+1)
        base_top3=set(base_order[:3].tolist()); base_leader=int(base_order[0])
        for label,k in [('moderate',100),('stress',25)]:
            ws=rng.dirichlet(BASE*k,size=5000)
            scores=ws@vals.T
            orders=np.argsort(-scores,axis=1,kind='stable')
            ranks=np.empty_like(orders)
            row_ix=np.arange(len(ws))[:,None]
            ranks[row_ix,orders]=np.arange(1,len(df)+1)[None,:]
            top1=float(np.mean(orders[:,0]==base_leader))
            # Spearman of permutations = 1 - 6*sum(d^2)/(n(n^2-1)).
            n=len(df); d2=((ranks-base_ranks[None,:])**2).sum(axis=1)
            sps=1-(6*d2)/(n*(n*n-1)) if n>1 else np.ones(len(ws))
            ov=np.array([len(base_top3 & set(o[:3].tolist()))/3 for o in orders])
            shifts=np.max(np.abs(ranks-base_ranks[None,:]),axis=1)
            mc.append({'district':district,'scenario':label,'top1_retention':top1,'mean_spearman':float(np.mean(sps)),'mean_top3_overlap':float(np.mean(ov)),'max_rank_shift':int(np.max(shifts))})
    pd.DataFrame(rows).to_csv(OUT/'v074_weight_sensitivity.csv',index=False)
    pd.DataFrame(loo).to_csv(OUT/'v074_leave_one_component_out.csv',index=False)
    pd.DataFrame(mc).to_csv(OUT/'v074_monte_carlo_weights.csv',index=False)

    # Optimizer feasibility under water limits based on candidate range.
    orows=[]
    for d in DISTRICTS:
        sdf=scenario_for_district(d)
        if sdf.empty: continue
        lo=float(sdf['official_water_default_m3_ha'].min()); med=float(sdf['official_water_default_m3_ha'].median()); hi=float(sdf['official_water_default_m3_ha'].max())
        for perha in [0, lo*1.05, med, hi]:
            opt,s=optimize_structure(d,100,profile='balanced',max_share=.4,n_crops=5,available_water_m3=(perha*100 if perha else 0))
            orows.append({'district':d,'limit_m3_ha':perha,'weighted_water_m3_ha':s.get('weighted_water_m3_ha'), 'water_feasible':s.get('water_feasible'), 'share_sum':float(opt['share'].sum()) if not opt.empty else np.nan,'area_sum':float(opt['area_ha'].sum()) if not opt.empty else np.nan})
    pd.DataFrame(orows).to_csv(OUT/'v074_optimizer_water_tests.csv',index=False)

    df=training_data()
    vif=vif_table(df); vif.to_csv(OUT/'v074_vif.csv',index=False)
    nonlinear=ml_compare(df)
    summary={
      'ranking_oat':{'mean_spearman':float(pd.DataFrame(rows).spearman.mean()),'min_spearman':float(pd.DataFrame(rows).spearman.min()),'top1_retention':float(pd.DataFrame(rows).top1_retained.mean()),'mean_top3_overlap':float(pd.DataFrame(rows).top3_overlap.mean()),'max_rank_shift':int(pd.DataFrame(rows).max_rank_shift.max())},
      'leave_one_component_out':{'mean_spearman':float(pd.DataFrame(loo).spearman.mean()),'min_spearman':float(pd.DataFrame(loo).spearman.min()),'top1_retention':float(pd.DataFrame(loo).top1_retained.mean()),'mean_top3_overlap':float(pd.DataFrame(loo).top3_overlap.mean()),'max_rank_shift':int(pd.DataFrame(loo).max_rank_shift.max())},
      'monte_carlo':pd.DataFrame(mc).groupby('scenario')[['top1_retention','mean_spearman','mean_top3_overlap','max_rank_shift']].mean().round(6).to_dict('index'),
      'optimizer':{'tests':len(orows),'share_sum_max_error':float((pd.DataFrame(orows).share_sum-1).abs().max()),'area_sum_max_error':float((pd.DataFrame(orows).area_sum-100).abs().max()),'constrained_infeasible_cases':int((~pd.DataFrame(orows).loc[pd.DataFrame(orows).limit_m3_ha>0,'water_feasible'].astype(bool)).sum())},
      'vif':{'max':float(vif.VIF.max()),'values':dict(zip(vif.feature,vif.VIF))},
      'nonlinearity_check':nonlinear,
    }
    (OUT/'validation_v0_7_4.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
