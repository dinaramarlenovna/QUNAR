from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from .clrem import scenario_for_district, registry


def optimize_structure(district: str, area_ha: float, profile: str = "balanced",
                       max_share: float = 0.40, n_crops: int = 5,
                       available_water_m3: float = 0.0, climate: dict | None = None,
                       irrigation_type: str = "furrow", economic_margin_by_product: dict | None = None,
                       economic_weight: float = 0.35):
    """Constrained linear allocation model for v0.8.

    Maximise weighted resource-climate utility subject to total land, crop-share and
    optional water constraints. Confidence is excluded from the objective and reported
    separately.
    """
    df=scenario_for_district(district,climate,irrigation_type).copy()
    req=['Climate_score_0_100','Water_pressure_score_0_100','Confidence_0_100','QUNAR_score_0_100','official_water_default_m3_ha']
    df=df.dropna(subset=req).copy()
    if df.empty:return pd.DataFrame(),{}

    weights={
        'balanced':(0.60,0.40),
        'climate':(0.78,0.22),
        'resource':(0.30,0.70),
    }.get(profile,(0.60,0.40))
    wc,ww=weights
    df['utility']=wc*df['Climate_score_0_100']+ww*df['Water_pressure_score_0_100']

    economic_margin_by_product = economic_margin_by_product or {}
    df['economic_margin_kzt_ha'] = df['product'].map(lambda p: float(economic_margin_by_product.get(str(p), 0.0) or 0.0))
    econ_available_all = df['economic_margin_kzt_ha'] > 0
    economic_active = bool(econ_available_all.sum() >= 2)
    ew = float(np.clip(economic_weight,0.0,0.7)) if economic_active else 0.0
    if economic_active:
        vals=df.loc[econ_available_all,'economic_margin_kzt_ha'].to_numpy(float)
        lo,hi=float(vals.min()),float(vals.max())
        if hi>lo:
            df['economic_score_0_100']=np.where(econ_available_all,(df['economic_margin_kzt_ha']-lo)/(hi-lo)*100.0,np.nan)
        else:
            df['economic_score_0_100']=np.where(econ_available_all,50.0,np.nan)
        # Missing economics do not receive invented market values. Their objective remains resource-climate only.
        econ_component=df['economic_score_0_100'].fillna(df['utility'])
        df['objective_utility']=(1.0-ew)*df['utility']+ew*econ_component
    else:
        df['economic_score_0_100']=np.nan
        df['objective_utility']=df['utility']

    cand=df.sort_values('objective_utility',ascending=False).head(max(2,min(int(n_crops),len(df)))).copy()
    econ_available = cand['economic_margin_kzt_ha'] > 0

    n=len(cand); requested=float(np.clip(max_share,.20,.80)); cap=max(requested,1.0/n)
    min_share=min(0.03,1.0/n)
    c=-cand['objective_utility'].to_numpy(float)
    A_ub=[]; b_ub=[]
    if available_water_m3 and area_ha>0:
        # sum share_j * water_j <= available water per ha
        A_ub.append(cand['official_water_default_m3_ha'].to_numpy(float)); b_ub.append(float(available_water_m3)/float(area_ha))
    bounds=[(min_share,cap) for _ in range(n)]
    res=linprog(c,A_ub=np.asarray(A_ub) if A_ub else None,b_ub=np.asarray(b_ub) if b_ub else None,
                A_eq=np.ones((1,n)),b_eq=np.array([1.0]),bounds=bounds,method='highs')
    if res.success:
        shares=np.asarray(res.x,float); feasible=True; solver_status='optimal'
    else:
        # If water makes the chosen shortlist infeasible, solve without minimum shares and allow zeros.
        bounds2=[(0.0,cap) for _ in range(n)]
        res2=linprog(c,A_ub=np.asarray(A_ub) if A_ub else None,b_ub=np.asarray(b_ub) if b_ub else None,
                     A_eq=np.ones((1,n)),b_eq=np.array([1.0]),bounds=bounds2,method='highs')
        if res2.success:
            shares=np.asarray(res2.x,float); feasible=True; solver_status='optimal_relaxed_min_share'
        else:
            shares=np.repeat(1.0/n,n); feasible=False; solver_status='infeasible_fallback_equal_shares'
    cand['share']=shares; cand['area_ha']=shares*float(area_ha); cand['modelled_water_m3']=cand['official_water_default_m3_ha']*cand['area_ha']
    reg=registry()[['CLREM_product','RU','KK','EN']].dropna(subset=['CLREM_product']).drop_duplicates('CLREM_product')
    cand=cand.merge(reg,left_on='product',right_on='CLREM_product',how='left')
    summary={
        'weighted_qunar':float(np.average(cand['QUNAR_score_0_100'],weights=shares)),
        'weighted_climate':float(np.average(cand['Climate_score_0_100'],weights=shares)),
        'weighted_resource':float(np.average(cand['Water_pressure_score_0_100'],weights=shares)),
        'weighted_reliability':float(np.average(cand['Confidence_0_100'],weights=shares)),
        'weighted_water_m3_ha':float(np.average(cand['official_water_default_m3_ha'],weights=shares)),
        'modelled_total_water_m3':float(cand['modelled_water_m3'].sum()),
        'available_water_m3':float(available_water_m3 or 0.0),
        'water_feasible':bool(feasible and (not available_water_m3 or cand['modelled_water_m3'].sum() <= float(available_water_m3)+1e-6)),
        'profile':profile,'requested_max_share':requested,'effective_max_share':cap,
        'solver_status':solver_status,
        'economic_objective_active':economic_active,
        'economic_weight':ew,
        'weighted_economic_margin_kzt_ha':float(np.average(cand['economic_margin_kzt_ha'],weights=shares)) if economic_active else None,
        'economic_coverage_share':float(np.sum(shares[econ_available.to_numpy(bool)])) if economic_active else 0.0,
        'objective':'linear_program_resource_climate_plus_user_economics' if economic_active else 'linear_program_resource_climate_utility'
    }
    return cand,summary
