"""Forward-time out-of-sample interval backtest; independent of app runtime.

2011-2020 residuals from prior-only training are used to set nominal 90%
absolute-error widths by crop. Coverage is evaluated on 2021-2025, never
on the same cases used to set widths. Formal exchangeability is NOT assumed.
"""
from pathlib import Path
import csv,json,math
import numpy as np
import pandas as pd
from stage2_ml_holdout_experiment import ROOT,DATA,OUT,NUM,CAT,TARGET,model


def finite_upper_quantile(vals,alpha=.10):
    a=np.sort(np.asarray(vals,float))
    if len(a)==0 or not np.isfinite(a).all():raise ValueError('Calibration residuals missing/invalid')
    rank=math.ceil((len(a)+1)*(1-alpha))
    return float(a[min(rank,len(a))-1])


def run(out=OUT):
    df=pd.read_csv(DATA);df=df[df['Use in 2.3 inference'].eq('Yes')].copy()
    calibrations=[]
    for end_tr,start_test,end_test in ((2010,2011,2015),(2015,2016,2020)):
        train=df[df.Year.between(2004,end_tr)]
        test=df[df.Year.between(start_test,end_test)]
        m=model().fit(train[CAT+NUM],train[TARGET])
        p=m.predict(test[CAT+NUM])
        c=test[['Crop','Year',TARGET]].copy();c['prediction']=p
        c['error_abs']=(c[TARGET]-p).abs()
        calibrations.append(c)
    cal=pd.concat(calibrations,ignore_index=True)
    train=df[df.Year.between(2004,2020)].copy();test=df[df.Year.between(2021,2025)].copy()
    m=model().fit(train[CAT+NUM],train[TARGET]);test['prediction']=m.predict(test[CAT+NUM]);test['error_abs']=(test[TARGET]-test['prediction']).abs()
    rows=[]
    for crop in ['Overall']+sorted(df.Crop.unique()):
        ca=cal if crop=='Overall' else cal[cal.Crop.eq(crop)]
        te=test if crop=='Overall' else test[test.Crop.eq(crop)]
        width=finite_upper_quantile(ca['error_abs'])
        coverage=float((te['error_abs']<=width+1e-12).mean())
        rows.append({'crop':crop,'nominal_coverage':.90,'calibration_N':len(ca),
                     'holdout_N':len(te),'calibration_halfwidth_centners_ha':width,
                     'holdout_coverage':coverage,'holdout_MAE':float(te['error_abs'].mean()),
                     'holdout_90th_abs_error':float(te['error_abs'].quantile(.90)),
                     'meets_nominal_on_heldout':coverage>=.90})
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with (out/'ml_forward_interval_coverage.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={'method':'Prior-window RF OOS abs residual 90% finite-sample quantile, validated forward on 2021-2025',
         'rows':rows,'no_production_interval_change':True,
         'warning':'Forward coverage can be lower than 90%; widths from earlier climate regimes are not guaranteed for a future shift. No theoretical conformal coverage claim under non-exchangeable time periods.'}
    (out/'ml_forward_interval_coverage.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return rows

if __name__=='__main__':
    for r in run():print(r['crop'],r['calibration_N'],r['holdout_N'],round(r['calibration_halfwidth_centners_ha'],2),f"{r['holdout_coverage']:.1%}")
