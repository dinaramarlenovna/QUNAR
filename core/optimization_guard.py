"""Independent final feasibility gate for allocation display and reporting."""
from __future__ import annotations

import math
import pandas as pd


def validate_allocation(alloc: pd.DataFrame, info: dict | None, *, area_ha: float,
                        available_water_m3: float, max_share: float, n_crops: int) -> dict:
    info = info or {}
    empty = alloc is None or alloc.empty
    reported_water = info.get('modelled_total_water_m3')
    if empty:
        return {'ok':False, 'reasons':['solver_returned_no_allocation'],
                'modelled_water_m3':float(reported_water) if reported_water is not None else None,
                'water_deficit_m3':None}
    reasons = []
    for col in ('share','area_ha','modelled_water_m3'):
        if col not in alloc.columns:
            reasons.append('missing_'+col)
    if reasons:
        return {'ok':False,'reasons':reasons,'modelled_water_m3':None,'water_deficit_m3':None}
    try:
        shares = pd.to_numeric(alloc['share'],errors='raise')
        areas = pd.to_numeric(alloc['area_ha'],errors='raise')
        water_values = pd.to_numeric(alloc['modelled_water_m3'],errors='raise')
        water = float(water_values.sum())
        if (not math.isfinite(water)) or not all(math.isfinite(float(x)) for x in list(shares)+list(areas)+list(water_values)):
            reasons.append('nonfinite_values')
        if (shares < -1e-7).any() or (areas < -1e-5).any() or (water_values < -1e-5).any():
            reasons.append('negative_values')
        if abs(float(shares.sum()) - 1) > 1e-5: reasons.append('shares_not_one')
        if abs(float(areas.sum()) - float(area_ha)) > max(1e-4,area_ha*1e-6): reasons.append('area_mismatch')
        if float(shares.max()) > float(max_share) + 1e-6: reasons.append('max_share_breached')
        if len(alloc) != int(n_crops): reasons.append('crop_count_mismatch')
        if float(available_water_m3) > 0 and water > float(available_water_m3) + 1e-5:
            reasons.append('water_budget_breached')
        if info.get('water_feasible') is False:
            reasons.append('solver_reports_infeasible')
        deficit = max(0.0, water-float(available_water_m3)) if available_water_m3 > 0 else None
    except (TypeError,ValueError,KeyError,OverflowError):
        reasons.append('non_numeric_values')
        water, deficit = None, None
    return {'ok':not reasons,'reasons':reasons,
            'modelled_water_m3':water,'water_deficit_m3':deficit}
