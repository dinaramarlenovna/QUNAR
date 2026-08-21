from __future__ import annotations

import numpy as np
import pandas as pd

from .clrem import scenario_for_district, registry


def _pareto_mask(df: pd.DataFrame) -> np.ndarray:
    """Non-dominated options on climate, water efficiency and evidence reliability."""
    vals = df[["Climate_score_0_100", "Resource_efficiency_0_100", "Data_reliability_0_100"]].to_numpy(float)
    keep = np.ones(len(vals), dtype=bool)
    for i, v in enumerate(vals):
        dominated = np.all(vals >= v, axis=1) & np.any(vals > v, axis=1)
        dominated[i] = False
        if dominated.any():
            keep[i] = False
    return keep


def _capped_shares(raw: np.ndarray, cap: float) -> np.ndarray:
    raw=np.maximum(np.asarray(raw,float),1e-12)
    free=np.ones(len(raw),dtype=bool); fixed=np.zeros(len(raw),float)
    for _ in range(len(raw)+2):
        rem=1.0-fixed.sum()
        if rem<=1e-12 or not free.any(): break
        idx=np.where(free)[0]
        prop=rem*raw[idx]/raw[idx].sum()
        over=prop>cap+1e-12
        if not over.any():
            fixed[idx]=prop; free[:]=False; break
        cidx=idx[over]; fixed[cidx]=cap; free[cidx]=False
    if fixed.sum()<=0: return np.repeat(1/len(raw),len(raw))
    return fixed/fixed.sum()


def _repair_water(shares, water, cap, limit_m3_ha):
    """Shift land from high-water to low-water candidates until water limit is met."""
    s=np.asarray(shares,float).copy(); w=np.asarray(water,float)
    if limit_m3_ha is None or limit_m3_ha<=0:
        return s, True
    if np.dot(s,w) <= limit_m3_ha + 1e-8:
        return s, True
    order_hi=np.argsort(-w); order_lo=np.argsort(w)
    for _ in range(10000):
        cur=float(np.dot(s,w))
        if cur <= limit_m3_ha + 1e-6: return s, True
        hi=next((i for i in order_hi if s[i]>1e-8),None)
        lo=next((i for i in order_lo if s[i]<cap-1e-8 and w[i]<w[hi]-1e-9),None) if hi is not None else None
        if hi is None or lo is None: break
        need=(cur-limit_m3_ha)/(w[hi]-w[lo])
        move=min(s[hi], cap-s[lo], max(need,1e-6))
        if move<=1e-10: break
        s[hi]-=move; s[lo]+=move
    return s, bool(np.dot(s,w)<=limit_m3_ha+1e-6)


def optimize_structure(district: str, area_ha: float, profile: str = "balanced",
                       max_share: float = 0.40, n_crops: int = 5,
                       available_water_m3: float = 0.0):
    """Allocate land using climate, official water demand and evidence quality.

    Legacy price/revenue proxies are excluded. If available_water_m3 > 0, it is a real
    hard feasibility check for the recommended structure.
    """
    df=scenario_for_district(district).copy()
    req=["Climate_score_0_100","Resource_efficiency_0_100","Data_reliability_0_100",
         "QUNAR_score_0_100","official_water_default_m3_ha"]
    df=df.dropna(subset=req).copy()
    if df.empty: return pd.DataFrame(), {}

    weights={
        "balanced":(0.45,0.40,0.15),
        "climate":(0.65,0.25,0.10),
        "resource":(0.25,0.65,0.10),
    }.get(profile,(0.45,0.40,0.15))
    wc,wr,wd=weights
    df['pareto']=_pareto_mask(df)
    df['utility']=wc*df['Climate_score_0_100']+wr*df['Resource_efficiency_0_100']+wd*df['Data_reliability_0_100']
    cand=df[df.pareto].sort_values('utility',ascending=False).copy()
    if len(cand)<min(n_crops,len(df)):
        cand=pd.concat([cand,df[~df.index.isin(cand.index)].sort_values('utility',ascending=False)])
    cand=cand.head(max(2,min(int(n_crops),len(cand)))).copy()

    u=cand['utility'].to_numpy(float); raw=np.maximum(u-u.min()+5,1)**2
    requested=float(np.clip(max_share,.20,.80)); cap=max(requested,1.0/len(cand))
    shares=_capped_shares(raw,cap)
    limit_per_ha=(float(available_water_m3)/float(area_ha)) if available_water_m3 and area_ha>0 else None
    shares, water_feasible=_repair_water(shares,cand['official_water_default_m3_ha'].to_numpy(float),cap,limit_per_ha)
    cand['share']=shares; cand['area_ha']=shares*float(area_ha)
    cand['modelled_water_m3']=cand['official_water_default_m3_ha']*cand['area_ha']

    reg=registry()[['CLREM_product','RU','KK','EN']].dropna(subset=['CLREM_product']).drop_duplicates('CLREM_product')
    cand=cand.merge(reg,left_on='product',right_on='CLREM_product',how='left')
    summary={
        'weighted_qunar':float(np.average(cand['QUNAR_score_0_100'],weights=shares)),
        'weighted_climate':float(np.average(cand['Climate_score_0_100'],weights=shares)),
        'weighted_resource':float(np.average(cand['Resource_efficiency_0_100'],weights=shares)),
        'weighted_reliability':float(np.average(cand['Data_reliability_0_100'],weights=shares)),
        'weighted_water_m3_ha':float(np.average(cand['official_water_default_m3_ha'],weights=shares)),
        'modelled_total_water_m3':float(cand['modelled_water_m3'].sum()),
        'available_water_m3':float(available_water_m3 or 0.0),
        'water_feasible':bool(water_feasible),
        'pareto_count':int(df['pareto'].sum()),
        'profile':profile,
        'requested_max_share':requested,
        'effective_max_share':cap,
    }
    return cand,summary
