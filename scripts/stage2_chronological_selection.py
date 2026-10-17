"""Temporal research check for forecast-method routing - NOT yet production routing.

Compares methods on two earlier expanding validation windows; records a
pre-2021-derived choice, then scores that choice on 2021-2025. Since the
researcher has examined the final holdout during development, results remain
exploratory and a new independent dataset is required for a confirmatory claim.
"""
from pathlib import Path
import csv,json
import numpy as np
import pandas as pd
from stage2_ml_holdout_experiment import ROOT,DATA,OUT,NUM,CAT,TARGET,model,score
METHODS=['Pooled RF','Historical median','Per-crop RF','Pooled Ridge']


def predictions(train,test):
    ans={}
    pooled=model().fit(train[CAT+NUM],train[TARGET])
    ans['Pooled RF']=pooled.predict(test[CAT+NUM]);ans['Pooled Ridge']=model(kind='ridge').fit(train[CAT+NUM],train[TARGET]).predict(test[CAT+NUM])
    dc=train.groupby(CAT)[TARGET].median(); cm=train.groupby('Crop')[TARGET].median(); gm=train[TARGET].median()
    ans['Historical median']=np.array([dc.get((r.District,r.Crop),cm.get(r.Crop,gm)) for r in test.itertuples(index=False)])
    crop_pred=np.full(len(test),np.nan)
    for crop in sorted(test.Crop.unique()):
        ctr=train[train.Crop.eq(crop)]
        if len(ctr)<10:continue
        mask=test.Crop.eq(crop).to_numpy()
        m=model(cats=['District']).fit(ctr[['District']+NUM],ctr[TARGET])
        crop_pred[mask]=m.predict(test.loc[mask,['District']+NUM])
    ans['Per-crop RF']=crop_pred
    return ans


def run(out=OUT):
    data=pd.read_csv(DATA)
    data=data[data['Use in 2.3 inference'].eq('Yes')].copy()
    windows=[(2004,2010,2011,2015),(2004,2015,2016,2020)]
    errors={crop:{method:[] for method in METHODS} for crop in sorted(data.Crop.unique())}
    folds=[]
    for lo,hi,st,en in windows:
        tr=data[data.Year.between(lo,hi)].copy();te=data[data.Year.between(st,en)].copy()
        preds=predictions(tr,te)
        for crop in sorted(te.Crop.unique()):
            mask=te.Crop.eq(crop).to_numpy(); y=te.loc[mask,TARGET].to_numpy(dtype=float)
            for method in METHODS:
                p=preds[method][mask]
                if not np.isfinite(p).all():continue
                errors[crop][method].extend(np.abs(y-p).tolist())
                folds.append({'crop':crop,'method':method,'train_end':hi,'test_start':st,'test_end':en,'N':len(y),'MAE':float(np.mean(np.abs(y-p)))})
    select={}
    for crop,arrs in errors.items():
        means={m:float(np.mean(v)) if len(v)>=10 else None for m,v in arrs.items()}
        baseline=means['Pooled RF']
        eligible={m:v for m,v in means.items() if v is not None}
        best=min(eligible,key=eligible.get)
        # Require materially better observed earlier MAE: 10%, otherwise retain default RF.
        chosen=best if best!='Pooled RF' and eligible[best] <= baseline*.90 else 'Pooled RF'
        select[crop]={'earlier_validation_MAE':means,'chosen':chosen,'earlier_best':best,
                      'rule':'alternative only if pooled prior-window MAE improves at least 10%; otherwise pooled RF',
                      'n_prior_validation':len(arrs['Pooled RF'])}
    train=data[data.Year.between(2004,2020)].copy();te=data[data.Year.between(2021,2025)].copy()
    ans=predictions(train,te)
    final=[]
    for crop,g in te.groupby('Crop'):
        mask=te.Crop.eq(crop).to_numpy();method=select[crop]['chosen']
        rr=score(g[TARGET],ans[method][mask]);default=score(g[TARGET],ans['Pooled RF'][mask]);med=score(g[TARGET],ans['Historical median'][mask])
        final.append({'crop':crop,'selected_from_earlier':method,'test_N':len(g),
                      'MAE_selected':rr['MAE'],'MAE_original_RF':default['MAE'],
                      'MAE_median':med['MAE'],'R2_selected':rr['R2'],'R2_original_RF':default['R2']})
    selected=np.array([ans[select[crop]['chosen']][i] for i,crop in enumerate(te.Crop)])
    summary={'selection':select,'test_by_crop':final,
             'test_overall_selected':score(te[TARGET],selected),
             'test_overall_pooled_RF':score(te[TARGET],ans['Pooled RF']),
             'test_overall_median':score(te[TARGET],ans['Historical median']),
             'no_production_model_change':True,
             'caution':'Exploratory temporal selection, not external untouched validation; formal adoption requires confirmatory future/farm data.'}
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'ml_temporal_method_selection.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'ml_temporal_method_selection.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(final[0]));writer.writeheader();writer.writerows(final)
    with (out/'ml_early_validation_folds.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(folds[0]));writer.writeheader();writer.writerows(folds)
    return summary

if __name__=='__main__':
    result=run()
    print('Chosen:',{k:v['chosen'] for k,v in result['selection'].items()})
    print('Overall MAE: select',result['test_overall_selected']['MAE'],'RF',result['test_overall_pooled_RF']['MAE'],'median',result['test_overall_median']['MAE'])
    for x in result['test_by_crop']:
        print(x['crop'],x['selected_from_earlier'],f"MAE {x['MAE_selected']:.2f} vs pooled {x['MAE_original_RF']:.2f}")
