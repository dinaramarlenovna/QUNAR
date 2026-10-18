"""Evidence gate for yield predictions. Reporting only: never changes or retrofits RF.

Historical estimates must not be called farm-level reliable forecasts merely
because a pooled across-crop R² appears large. All crops use genuine forward
2021–25 test metrics fitted through 2020, already explored in prior audits.
"""
from dataclasses import dataclass
from pathlib import Path
from math import isfinite
import csv

@dataclass(frozen=True)
class YieldEvidence:
    crop: str
    tested_n: int | None
    r2: float | None
    mae_c_ha: float | None
    wape_pct: float | None
    support: str
    reasons: tuple[str, ...]


def forward_yield_evidence(data_dir, crop, *, minimum_n=30, minimum_r2=0.5,
                           maximum_wape_pct=25.0):
    """Apply predeclared transparent display thresholds to saved forward-year results.

    Thresholds are safeguards, NOT probability calibration or new accuracy.
    Missing data means unvalidated, not high confidence. Do not train on holdout.
    """
    path=Path(data_dir)/'forecast_holdout_2021_2025_metrics.csv'
    if not path.exists():
        return YieldEvidence(str(crop),None,None,None,None,'unverified',('forward-year verification absent',))
    with path.open(encoding='utf-8-sig',newline='') as fp:
        matches=[r for r in csv.DictReader(fp) if r.get('crop')==str(crop)]
    if len(matches)!=1:
        return YieldEvidence(str(crop),None,None,None,None,'unverified',('unique crop-level verification unavailable',))
    row=matches[0]
    try:
        n=int(row['n']); r2=float(row['R2']); mae=float(row['MAE']); wape=float(row['WAPE_percent'])
        start=int(row['test_start']); end=int(row['test_end']); train_end=int(row['train_end'])
    except (ValueError,TypeError,KeyError):
        return YieldEvidence(str(crop),None,None,None,None,'unverified',('invalid holdout metrics',))
    if not (n>0 and isfinite(r2) and isfinite(mae) and isfinite(wape)
            and mae>=0 and wape>=0 and train_end<start<=end and start==2021 and end==2025):
        return YieldEvidence(str(crop),None,None,None,None,'unverified',('invalid chronological holdout',))
    reasons=[]
    if n<minimum_n:reasons.append(f'only {n} forward-tested observations (<{minimum_n})')
    if r2<minimum_r2:reasons.append(f'forward-year R²={r2:.3f} (<{minimum_r2:.2f})')
    if wape>maximum_wape_pct:reasons.append(f'forward-year WAPE={wape:.1f}% (>{maximum_wape_pct:.1f}%)')
    return YieldEvidence(str(crop),n,r2,mae,wape,
                         'limited' if reasons else 'historically_supported',tuple(reasons))


def norm_vs_fao_comparison(norm_m3_ha, gross_fao_m3_ha):
    """State incompatible assumptions, never claim the ratio is saving/error.

    Only compares two per-ha seasonal deliveries when positive finite numbers.
    Norm refers to statutory irrigation category; FAO may use alternative
    weather, crop calendar, rainfall and irrigation efficiencies.
    """
    try:a=float(norm_m3_ha); b=float(gross_fao_m3_ha)
    except (ValueError,TypeError):return None
    if not all(isfinite(v) and v>0 for v in (a,b)):return None
    return {'norm_m3_ha':a,'fao_m3_ha':b,'ratio_fao_to_norm':b/a,
            'material_difference':max(a,b)/min(a,b)>=1.25,
            'comparable_effect':False}
