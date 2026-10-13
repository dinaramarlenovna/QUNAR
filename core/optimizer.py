from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from itertools import combinations

from .clrem import scenario_for_district, registry


def _normalize_positive_mapping(values: dict | None, *, allow_negative: bool = False) -> dict[str, float]:
    out = {}
    for k, v in (values or {}).items():
        try:
            fv = float(v)
        except Exception:
            continue
        # A negative margin is a legitimate loss, not a missing observation.
        # For historical shares only strictly positive values are meaningful.
        if np.isfinite(fv) and (allow_negative or fv > 0):
            out[str(k)] = fv
    return out


def optimize_structure(district: str, area_ha: float, profile: str = "balanced",
                       max_share: float = 0.40, n_crops: int = 5,
                       available_water_m3: float = 0.0, climate: dict | None = None,
                       irrigation_type: str = "furrow",
                       economic_margin_by_product: dict | None = None,
                       economic_weight: float = 0.35,
                       objective_mode: str = "resource",
                       baseline_share_by_product: dict | None = None):
    """Constrained farm-structure allocation model for QŪNAR v0.8.1.

    objective_mode:
      - ``resource``: resource-climate utility only;
      - ``balanced``: resource-climate utility + verified/scenario crop margins;
      - ``economic``: economic return receives a dominant weight, while resource
        and climate feasibility remain in the objective and hard constraints.

    QŪNAR never fabricates missing crop economics. For balanced/economic modes,
    only alternatives with a positive user/verified contribution margin are compared.
    If fewer than two such alternatives are available, the model falls back to the
    resource-climate objective and reports that fallback in the summary.
    """
    df = scenario_for_district(district, climate, irrigation_type).copy()
    req = [
        'Climate_score_0_100', 'Water_pressure_score_0_100',
        'Confidence_0_100', 'QUNAR_score_0_100',
        'official_water_default_m3_ha'
    ]
    df = df.dropna(subset=req).copy()
    if df.empty:
        return pd.DataFrame(), {}

    weights = {
        'balanced': (0.60, 0.40),
        'climate': (0.78, 0.22),
        'resource': (0.30, 0.70),
    }.get(profile, (0.60, 0.40))
    wc, ww = weights
    df['utility'] = wc * df['Climate_score_0_100'] + ww * df['Water_pressure_score_0_100']

    margins = _normalize_positive_mapping(economic_margin_by_product, allow_negative=True)
    df['economic_margin_kzt_ha'] = df['product'].astype(str).map(margins).fillna(0.0)
    df['economic_data_available'] = df['product'].astype(str).isin(margins)

    requested_mode = str(objective_mode or 'resource').lower()
    if requested_mode not in {'resource', 'balanced', 'economic'}:
        requested_mode = 'resource'

    economic_candidates = int(df['economic_data_available'].sum())
    economic_active = requested_mode in {'balanced', 'economic'} and economic_candidates >= 2
    fallback_reason = None
    if requested_mode in {'balanced', 'economic'} and not economic_active:
        fallback_reason = 'insufficient_user_economic_data'

    if economic_active:
        # Compare all crops with explicitly supplied margins, including zero
        # (break-even) and negative (loss); blanks alone mean unknown.
        pool = df[df['economic_data_available']].copy()
        vals = pool['economic_margin_kzt_ha'].to_numpy(float)
        lo, hi = float(vals.min()), float(vals.max())
        if hi > lo:
            pool['economic_score_0_100'] = (pool['economic_margin_kzt_ha'] - lo) / (hi - lo) * 100.0
        else:
            pool['economic_score_0_100'] = 50.0

        if requested_mode == 'economic':
            ew = float(np.clip(economic_weight if economic_weight is not None else 0.70, 0.50, 0.85))
        else:
            ew = float(np.clip(economic_weight if economic_weight is not None else 0.35, 0.10, 0.60))
        pool['objective_utility'] = (1.0 - ew) * pool['utility'] + ew * pool['economic_score_0_100']
        effective_mode = requested_mode
    else:
        pool = df.copy()
        pool['economic_score_0_100'] = np.nan
        pool['objective_utility'] = pool['utility']
        ew = 0.0
        effective_mode = 'resource'

    # Search combinations rather than choosing the top-ranked crops first: a top-N
    # prefilter can make a feasible water-constrained problem look infeasible.
    target_n = max(2, int(n_crops))
    requested = float(max_share)
    if not (0 < requested <= 1):
        return pd.DataFrame(), {'solver_status':'invalid_max_share', 'water_feasible':False}
    if target_n > len(pool) or requested * target_n < 1 - 1e-9:
        return pd.DataFrame(), {'solver_status':'infeasible_crop_count_or_cap', 'water_feasible':False,
                                'required_max_share':1.0/target_n,
                                'economic_objective_requested':requested_mode,
                                'economic_objective_active':economic_active,
                                'economic_candidates_n':economic_candidates,
                                'eligible_crop_count':len(pool),'requested_crop_count':target_n}
    if area_ha <= 0 or available_water_m3 < 0:
        return pd.DataFrame(), {'solver_status':'invalid_area_or_water', 'water_feasible':False}
    # Only evaluated alternatives participate. Exact N means every selected crop
    # receives at least 3%, and maximum crop share is never silently increased.
    min_share = min(.03, 1.0 / target_n)
    ranked = pool.sort_values('objective_utility', ascending=False)
    # Bound runtime for very large registries; enumerate all alternatives if <= 18.
    search_pool = ranked.head(18).copy()
    best = None
    for ids in combinations(range(len(search_pool)), target_n):
        trial = search_pool.iloc[list(ids)].copy()
        bounds = [(min_share, requested)] * target_n
        water = trial['official_water_default_m3_ha'].to_numpy(float)
        res = linprog(-trial['objective_utility'].to_numpy(float),
                      A_ub=water.reshape(1,-1) if available_water_m3 else None,
                      b_ub=[float(available_water_m3)/float(area_ha)] if available_water_m3 else None,
                      A_eq=np.ones((1,target_n)), b_eq=[1.], bounds=bounds, method='highs')
        if res.success:
            score = float(np.dot(res.x, trial['objective_utility'].to_numpy(float)))
            if best is None or score > best[0]:
                best = (score, trial, np.asarray(res.x,float))
    if best is None:
        return pd.DataFrame(), {
            'solver_status':'infeasible_under_hard_constraints',
            'water_feasible':False, 'available_water_m3':float(available_water_m3),
            'requested_max_share':requested, 'n_crops':target_n,
            'tested_candidate_crops':len(search_pool),
            'minimum_uniform_water_m3':float(area_ha * ranked['official_water_default_m3_ha'].min()),
        }
    _, cand, shares = best
    cand = cand.copy()
    feasible = True
    solver_status = 'optimal_enumerated_candidates'
    cap = requested
    cand['share'] = shares
    cand['area_ha'] = shares * float(area_ha)
    cand['modelled_water_m3'] = cand['official_water_default_m3_ha'] * cand['area_ha']
    cand['economic_result_kzt'] = cand['economic_margin_kzt_ha'] * cand['area_ha']

    reg = registry()[['CLREM_product', 'RU', 'KK', 'EN']].dropna(subset=['CLREM_product']).drop_duplicates('CLREM_product')
    cand = cand.merge(reg, left_on='product', right_on='CLREM_product', how='left')

    optimized_margin_total = None
    optimized_margin_per_m3 = None
    if economic_active:
        optimized_margin_total = float(cand['economic_result_kzt'].sum())
        total_water = float(cand['modelled_water_m3'].sum())
        optimized_margin_per_m3 = optimized_margin_total / total_water if total_water > 0 else None

    # Optional before/after comparison based only on a user-entered current crop structure.
    baseline_map = _normalize_positive_mapping(baseline_share_by_product)
    baseline_status = 'not_entered'
    baseline_available = False
    baseline_margin_total = None
    baseline_water_m3 = None
    baseline_water_feasible = None
    baseline_margin_per_m3 = None
    economic_gain_kzt = None
    economic_gain_pct = None
    water_change_m3 = None
    water_change_pct = None
    if baseline_map:
        total_input = sum(baseline_map.values())
        # A partial entry (e.g. 25%) is not silently reinterpreted as 100%.
        # Accept percentages summing to 100, or fractions summing to one.
        valid_total = abs(total_input - 100.0) <= 0.5 or abs(total_input - 1.0) <= 0.005
        if not valid_total:
            baseline_status = 'shares_do_not_sum_to_100'
        else:
            norm = {k: v / total_input for k, v in baseline_map.items()}
            b = df[df['product'].astype(str).isin(norm)].copy()
            b['baseline_share'] = b['product'].astype(str).map(norm).fillna(0.0)
            coverage = float(b['baseline_share'].sum())
            if coverage < 0.999:
                baseline_status = 'unrecognized_baseline_crops'
            else:
                baseline_available = True
                baseline_water_m3 = float((b['baseline_share'] * float(area_ha) * b['official_water_default_m3_ha']).sum())
                budget_known = float(available_water_m3) > 0
                baseline_water_feasible = (baseline_water_m3 <= float(available_water_m3) + 1e-6) if budget_known else None
                if baseline_water_feasible is False:
                    baseline_status = 'baseline_exceeds_water_limit'
                elif baseline_water_feasible is None:
                    baseline_status = 'water_budget_not_entered'
                elif optimized_margin_total is None or not b['product'].astype(str).isin(margins).all():
                    baseline_status = 'missing_baseline_crop_margins'
                else:
                    baseline_status = 'valid_comparison'
                    baseline_margin_total = float((b['baseline_share'] * float(area_ha) * b['economic_margin_kzt_ha']).sum())
                    baseline_margin_per_m3 = baseline_margin_total / baseline_water_m3 if baseline_water_m3 > 0 else None
                    economic_gain_kzt = optimized_margin_total - baseline_margin_total
                    economic_gain_pct = (economic_gain_kzt / abs(baseline_margin_total) * 100.0) if baseline_margin_total else None
                optimized_water = float(cand['modelled_water_m3'].sum())
                water_change_m3 = optimized_water - baseline_water_m3
                water_change_pct = (water_change_m3 / baseline_water_m3 * 100.0) if baseline_water_m3 > 0 else None

    summary = {
        'weighted_qunar': float(np.average(cand['QUNAR_score_0_100'], weights=shares)),
        'weighted_climate': float(np.average(cand['Climate_score_0_100'], weights=shares)),
        'weighted_resource': float(np.average(cand['Water_pressure_score_0_100'], weights=shares)),
        'weighted_reliability': float(np.average(cand['Confidence_0_100'], weights=shares)),
        'weighted_water_m3_ha': float(np.average(cand['official_water_default_m3_ha'], weights=shares)),
        'modelled_total_water_m3': float(cand['modelled_water_m3'].sum()),
        'available_water_m3': float(available_water_m3 or 0.0),
        # None denotes unverified compliance when the water budget was not supplied.
        'water_feasible': bool(feasible and cand['modelled_water_m3'].sum() <= float(available_water_m3) + 1e-6) if available_water_m3 > 0 else None,
        'water_budget_verified': bool(available_water_m3 > 0),
        'profile': profile,
        'requested_max_share': requested,
        'effective_max_share': cap,
        'solver_status': solver_status,
        'economic_objective_requested': requested_mode,
        'economic_objective_mode': effective_mode,
        'economic_objective_active': economic_active,
        'economic_fallback_reason': fallback_reason,
        'economic_weight': ew,
        'economic_candidates_n': economic_candidates,
        'weighted_economic_margin_kzt_ha': float(np.average(cand['economic_margin_kzt_ha'], weights=shares)) if economic_active else None,
        'optimized_contribution_margin_kzt': optimized_margin_total,
        'optimized_margin_per_m3_kzt': optimized_margin_per_m3,
        'baseline_available': baseline_available,
        'baseline_status': baseline_status,
        'baseline_water_feasible': baseline_water_feasible,
        'baseline_contribution_margin_kzt': baseline_margin_total,
        'baseline_water_m3': baseline_water_m3,
        'baseline_margin_per_m3_kzt': baseline_margin_per_m3,
        'economic_gain_kzt': economic_gain_kzt,
        'economic_gain_pct': economic_gain_pct,
        'water_change_m3': water_change_m3,
        'water_change_pct': water_change_pct,
        'objective': (
            'linear_program_economic_priority' if effective_mode == 'economic' else
            'linear_program_balanced_resource_economic' if effective_mode == 'balanced' else
            'linear_program_resource_climate_utility'
        ),
    }
    return cand, summary
