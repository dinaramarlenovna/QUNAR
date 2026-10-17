"""Crop-mix partial greenhouse-gas scenario: no hidden activity imputation.

N input kg N/ha, diesel L/ha, electricity kWh/ha for one specified period.
Only per-crop activities explicitly provided and confirmed may be compared.
Changes in technology, irrigation and yield require changed per-ha scenarios.
"""
from __future__ import annotations
from math import isfinite
from core.carbon_scenarios import partial_inventory, compare_partial_inventory

ACTIVITY_FIELDS = ('nitrogen_kg_ha', 'diesel_litres_ha', 'electricity_kwh_ha')


def _finite_nonnegative(v, name):
    try: f = float(v)
    except (TypeError, ValueError): raise ValueError(f'Incomplete GHG data: {name}') from None
    if not isfinite(f) or f < 0: raise ValueError(f'Invalid GHG data: {name}')
    return f


def structure_inventory(areas_by_crop: dict, activity_per_ha: dict, *,
                        grid_factor: float, accounting_period: str = 'apr_sep',
                        diesel_factor: float = 2.68, evidence: str,
                        confirmed: bool = False) -> dict:
    """Aggregate activities for all planted crops; missing inputs block total.

    An explicit zero is permitted only with the user's confirmation of amounts.
    """
    if not confirmed or not str(evidence).strip():
        raise ValueError('Confirm complete crop activities and document their source/assumption')
    grid_factor = _finite_nonnegative(grid_factor,'grid factor')
    diesel_factor = _finite_nonnegative(diesel_factor,'diesel factor')
    totals = {f: 0.0 for f in ACTIVITY_FIELDS}
    rice_nitrogen_total = None
    rice_regime = None
    areas = {}
    for crop, area_value in areas_by_crop.items():
        area = _finite_nonnegative(area_value,f'area of {crop}')
        if area == 0: continue
        if crop not in activity_per_ha:
            raise ValueError(f'Missing crop-specific GHG activity: {crop}')
        activity = activity_per_ha[crop]
        if not isinstance(activity,dict):
            raise ValueError(f'Invalid crop activity: {crop}')
        is_rice = str(crop).strip().lower() in ('rice', 'рис')
        if is_rice:
            regime = activity.get('rice_water_regime')
            if regime not in ('unspecified_flooded','continuous_flooding','drained_once_or_more'):
                raise ValueError('Rice crop requires flooding/drainage regime for IPCC EF1FR')
            if rice_regime is not None and rice_regime != regime:
                raise ValueError('Mixed rice flooding regimes require separate inventories')
            rice_regime = regime
        for f in ACTIVITY_FIELDS:
            if f not in activity: raise ValueError(f'Missing {f} for crop {crop}')
            activity_total = area * _finite_nonnegative(activity[f],f'{crop}: {f}')
            if is_rice and f == 'nitrogen_kg_ha':
                rice_nitrogen_total = (rice_nitrogen_total or 0.0) + activity_total
            else:
                totals[f] += activity_total
        areas[crop] = area
    if not areas: raise ValueError('At least one crop area required')
    inv = partial_inventory(nitrogen_kg=totals['nitrogen_kg_ha'],
                            rice_nitrogen_kg=rice_nitrogen_total, rice_water_regime=rice_regime,
                            diesel_litres=totals['diesel_litres_ha'],
                            electricity_kwh=totals['electricity_kwh_ha'],
                            grid_kg_co2e_kwh=grid_factor,
                            accounting_period=accounting_period,
                            diesel_factor=diesel_factor)
    if not inv.complete: raise ValueError('Incomplete partial GHG factor/activity boundary')
    if rice_nitrogen_total is not None:
        totals['rice_nitrogen_kg'] = rice_nitrogen_total
    return {'inventory':inv,'crop_areas_ha':areas,'activities_total':totals,
            'evidence':evidence,'total_area_ha':sum(areas.values())}


def compare_crop_structures(*, baseline_areas: dict, proposed_areas: dict,
                            baseline_activity_per_ha: dict, grid_factor: float,
                            proposed_activity_per_ha: dict | None = None,
                            accounting_period: str = 'apr_sep', diesel_factor: float = 2.68,
                            evidence: str, confirmed: bool = False) -> dict:
    """Compare matched crop-mix emissions; fixed-intensity assumption if no proposed data."""
    a = structure_inventory(baseline_areas, baseline_activity_per_ha,
                           grid_factor=grid_factor, accounting_period=accounting_period,
                           diesel_factor=diesel_factor, evidence=evidence, confirmed=confirmed)
    b = structure_inventory(proposed_areas,
                           baseline_activity_per_ha if proposed_activity_per_ha is None else proposed_activity_per_ha,
                           grid_factor=grid_factor, accounting_period=accounting_period,
                           diesel_factor=diesel_factor, evidence=evidence, confirmed=confirmed)
    if abs(a['total_area_ha']-b['total_area_ha'])>max(1e-6,a['total_area_ha']*1e-5):
        raise ValueError('Baseline and proposed areas must cover same farm size')
    out=compare_partial_inventory(a['inventory'],b['inventory'])
    out.update({'baseline_activities':a['activities_total'],
                'proposed_activities':b['activities_total'],
                'baseline_area_ha':a['total_area_ha'], 'proposed_area_ha':b['total_area_ha'],
                'intensities_assumption':'fixed_per_crop' if proposed_activity_per_ha is None else 'user_scenario_per_crop',
                'evidence':evidence,
                'boundary':'partial N2O from applied N, diesel combustion, grid electricity; no lifecycle or all sources',
                'interpretation':'modeled crop-mix difference, not measured mitigation outcome'})
    return out
