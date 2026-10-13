"""Transparent irrigation-switch what-if. Not an ML treatment-effect estimate.

Yield effect must be supplied with an evidence/provenance label. Resource costs
are accounted separately from other variable costs, avoiding double counting.
"""
from __future__ import annotations


def irrigation_comparison(*, baseline_yield_centners_ha: float, price_kzt_t: float,
                          other_variable_cost_kzt_ha: float,
                          baseline_water_m3_ha: float, proposed_water_m3_ha: float,
                          baseline_energy_kwh_ha: float, proposed_energy_kwh_ha: float,
                          water_tariff_kzt_m3: float, electricity_tariff_kzt_kwh: float,
                          yield_change_pct: float, extra_technology_cost_kzt_ha: float,
                          evidence: str, price_risk_pct: float = -10,
                          yield_risk_pct: float = -10, cost_risk_pct: float = 10):
    if not str(evidence).strip():
        raise ValueError('Document the source or assumption for irrigation yield change')
    values = [baseline_yield_centners_ha, price_kzt_t, other_variable_cost_kzt_ha,
              baseline_water_m3_ha, proposed_water_m3_ha, baseline_energy_kwh_ha,
              proposed_energy_kwh_ha, water_tariff_kzt_m3, electricity_tariff_kzt_kwh,
              extra_technology_cost_kzt_ha]
    if any(v < 0 for v in values):
        raise ValueError('Amounts must be nonnegative')
    if yield_change_pct < -100 or yield_risk_pct < -100 or price_risk_pct < -100 or cost_risk_pct < -100:
        raise ValueError('Percentage changes must not be below -100%')
    def margin(y, p, water, energy, extra, cost_scale=1):
        revenue = (y / 10) * p
        costs = (other_variable_cost_kzt_ha + extra + water * water_tariff_kzt_m3
                 + energy * electricity_tariff_kzt_kwh) * cost_scale
        return revenue - costs
    base = margin(baseline_yield_centners_ha, price_kzt_t, baseline_water_m3_ha,
                  baseline_energy_kwh_ha, 0)
    new_yield = baseline_yield_centners_ha * (1 + yield_change_pct / 100)
    proposed = margin(new_yield, price_kzt_t, proposed_water_m3_ha,
                      proposed_energy_kwh_ha, extra_technology_cost_kzt_ha)
    stressed_base = margin(baseline_yield_centners_ha * (1 + yield_risk_pct / 100),
                           price_kzt_t * (1 + price_risk_pct / 100), baseline_water_m3_ha,
                           baseline_energy_kwh_ha, 0, 1 + cost_risk_pct / 100)
    stressed_new = margin(new_yield * (1 + yield_risk_pct / 100),
                          price_kzt_t * (1 + price_risk_pct / 100), proposed_water_m3_ha,
                          proposed_energy_kwh_ha, extra_technology_cost_kzt_ha,
                          1 + cost_risk_pct / 100)
    return {
        'baseline_margin_kzt_ha': base, 'proposed_margin_kzt_ha': proposed,
        'margin_change_kzt_ha': proposed - base,
        'baseline_water_m3_ha': baseline_water_m3_ha, 'proposed_water_m3_ha': proposed_water_m3_ha,
        'water_saving_m3_ha': baseline_water_m3_ha - proposed_water_m3_ha,
        'proposed_yield_centners_ha': new_yield,
        'stress_baseline_margin_kzt_ha': stressed_base,
        'stress_proposed_margin_kzt_ha': stressed_new,
        'stress_margin_change_kzt_ha': stressed_new - stressed_base,
        'evidence': evidence, 'status': 'user_scenario_not_ml_validation',
    }
