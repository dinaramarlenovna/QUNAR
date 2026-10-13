"""Independent scenario-only economics. No invented regional averages or ML claims."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class EconomicInput:
    crop: str
    area_ha: float
    yield_t_ha: float
    price_kzt_t: float
    variable_cost_kzt_ha: float
    water_m3_ha: float
    evidence: str


def compare_structures(baseline: list[EconomicInput], proposed: list[EconomicInput],
                       available_water_m3: float, price_shock_pct: float = -10,
                       yield_shock_pct: float = -10, cost_shock_pct: float = 10) -> dict:
    """Apply IDENTICAL price/yield/cost shocks to both plans.

    Input costs must use identical cost boundaries and units for every crop.
    Only use identical land area and water limits when comparing plans.
    This is sensitivity analysis, not a statistically calibrated prediction.
    """
    if not baseline or not proposed or available_water_m3 < 0:
        raise ValueError('Plans and a nonnegative water limit are required')
    if any(not x.evidence.strip() for x in baseline + proposed):
        raise ValueError('Every economic input needs provenance or explicit assumption')
    if any(min(x.area_ha,x.yield_t_ha,x.price_kzt_t,x.variable_cost_kzt_ha,x.water_m3_ha) < 0 for x in baseline+proposed):
        raise ValueError('All physical and monetary inputs must be nonnegative')
    if price_shock_pct < -100 or yield_shock_pct < -100 or cost_shock_pct < -100:
        raise ValueError('Shock percentages cannot be below -100')
    area_before = sum(x.area_ha for x in baseline)
    area_after = sum(x.area_ha for x in proposed)
    if area_before <= 0 or abs(area_before-area_after) > 1e-6:
        raise ValueError('Baseline and proposed areas must be identical and positive')
    def calc(rows, pshock=0, yshock=0, cshock=0):
        revenue=sum(x.area_ha*x.yield_t_ha*(1+ yshock/100)*x.price_kzt_t*(1+pshock/100) for x in rows)
        cost=sum(x.area_ha*x.variable_cost_kzt_ha*(1+cshock/100) for x in rows)
        water=sum(x.area_ha*x.water_m3_ha for x in rows)
        return {'revenue_kzt':revenue,'variable_cost_kzt':cost,'margin_kzt':revenue-cost,'water_m3':water,
                'margin_kzt_m3':(revenue-cost)/water if water > 0 else None,
                'water_feasible':water <= available_water_m3 + 1e-6}
    b=calc(baseline); a=calc(proposed)
    sb=calc(baseline,price_shock_pct,yield_shock_pct,cost_shock_pct)
    sa=calc(proposed,price_shock_pct,yield_shock_pct,cost_shock_pct)
    admissible = b['water_feasible'] and a['water_feasible']
    return {'baseline':b,'proposed':a,'stress_baseline':sb,'stress_proposed':sa,
            'economic_gain_kzt':a['margin_kzt']-b['margin_kzt'] if admissible else None,
            'stress_gain_kzt':sa['margin_kzt']-sb['margin_kzt'] if admissible else None,
            'valid_comparison':admissible, 'type':'scenario_not_observed_economic_validation',
            'area_ha':area_before, 'water_budget_m3':available_water_m3}
