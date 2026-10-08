from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from .clrem import scenario_for_district, registry


def _normalize_positive_mapping(values: dict | None) -> dict[str, float]:
    out = {}
    for k, v in (values or {}).items():
        try:
            fv = float(v)
        except Exception:
            continue
        if fv > 0:
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

    margins = _normalize_positive_mapping(economic_margin_by_product)
    df['economic_margin_kzt_ha'] = df['product'].astype(str).map(margins).fillna(0.0)
    df['economic_data_available'] = df['economic_margin_kzt_ha'] > 0

    requested_mode = str(objective_mode or 'resource').lower()
    if requested_mode not in {'resource', 'balanced', 'economic'}:
        requested_mode = 'resource'

    economic_candidates = int(df['economic_data_available'].sum())
    economic_active = requested_mode in {'balanced', 'economic'} and economic_candidates >= 2
    fallback_reason = None
    if requested_mode in {'balanced', 'economic'} and not economic_active:
        fallback_reason = 'insufficient_user_economic_data'

    if economic_active:
        # Fair economic comparison requires economics for every alternative in the
        # economic candidate set; missing alternatives are not assigned proxy prices.
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

    cand = pool.sort_values('objective_utility', ascending=False).head(
        max(2, min(int(n_crops), len(pool)))
    ).copy()
    if cand.empty:
        return pd.DataFrame(), {}

    n = len(cand)
    requested = float(np.clip(max_share, .20, .80))
    cap = max(requested, 1.0 / n)
    min_share = min(0.03, 1.0 / n)
    c = -cand['objective_utility'].to_numpy(float)
    A_ub, b_ub = [], []
    if available_water_m3 and area_ha > 0:
        A_ub.append(cand['official_water_default_m3_ha'].to_numpy(float))
        b_ub.append(float(available_water_m3) / float(area_ha))

    bounds = [(min_share, cap) for _ in range(n)]
    res = linprog(
        c,
        A_ub=np.asarray(A_ub) if A_ub else None,
        b_ub=np.asarray(b_ub) if A_ub else None,
        A_eq=np.ones((1, n)), b_eq=np.array([1.0]),
        bounds=bounds, method='highs'
    )
    if res.success:
        shares = np.asarray(res.x, float)
        feasible = True
        solver_status = 'optimal'
    else:
        bounds2 = [(0.0, cap) for _ in range(n)]
        res2 = linprog(
            c,
            A_ub=np.asarray(A_ub) if A_ub else None,
            b_ub=np.asarray(b_ub) if A_ub else None,
            A_eq=np.ones((1, n)), b_eq=np.array([1.0]),
            bounds=bounds2, method='highs'
        )
        if res2.success:
            shares = np.asarray(res2.x, float)
            feasible = True
            solver_status = 'optimal_relaxed_min_share'
        else:
            shares = np.repeat(1.0 / n, n)
            feasible = False
            solver_status = 'infeasible_fallback_equal_shares'

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
    baseline_available = False
    baseline_margin_total = None
    baseline_water_m3 = None
    baseline_margin_per_m3 = None
    economic_gain_kzt = None
    economic_gain_pct = None
    water_change_m3 = None
    water_change_pct = None
    if baseline_map:
        total_input = sum(baseline_map.values())
        if total_input > 0:
            # Accept either fractions or percentages; normalize in all cases.
            norm = {k: v / total_input for k, v in baseline_map.items()}
            b = df[df['product'].astype(str).isin(norm)].copy()
            if not b.empty:
                b['baseline_share'] = b['product'].astype(str).map(norm).fillna(0.0)
                coverage = float(b['baseline_share'].sum())
                if coverage > 0.999:
                    baseline_available = True
                    baseline_water_m3 = float((b['baseline_share'] * float(area_ha) * b['official_water_default_m3_ha']).sum())
                    # Economic comparison is only valid if every baseline crop has user economics.
                    if (b.loc[b['baseline_share'] > 0, 'economic_margin_kzt_ha'] > 0).all() and optimized_margin_total is not None:
                        baseline_margin_total = float((b['baseline_share'] * float(area_ha) * b['economic_margin_kzt_ha']).sum())
                        baseline_margin_per_m3 = baseline_margin_total / baseline_water_m3 if baseline_water_m3 > 0 else None
                        economic_gain_kzt = optimized_margin_total - baseline_margin_total
                        economic_gain_pct = (economic_gain_kzt / abs(baseline_margin_total) * 100.0) if baseline_margin_total not in (0, None) else None
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
        'water_feasible': bool(feasible and (not available_water_m3 or cand['modelled_water_m3'].sum() <= float(available_water_m3) + 1e-6)),
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
