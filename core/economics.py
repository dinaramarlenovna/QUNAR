from pathlib import Path
import csv

_REF_FILE = Path(__file__).resolve().parents[1] / "data" / "economic_reference_values.csv"

def _reference_value(indicator: str, fallback: float) -> float:
    try:
        with _REF_FILE.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("indicator") == indicator:
                    return float(row.get("value"))
    except Exception:
        pass
    return float(fallback)


DEFAULT_EF_KZ_KGCO2_PER_KWH = _reference_value("electricity_emission_factor", 0.813)
DEFAULT_ELECTRICITY_TARIFF_KZT_KWH = _reference_value("electricity_tariff", 45.9872)
DEFAULT_IRRIGATION_WATER_TARIFF_KZT_M3 = _reference_value("irrigation_water_tariff", 0.845)
DEFAULT_GREEN_SHARE_TARGET = 30.0
DEFAULT_WATER_SAVING_TARGET = 20.0

IRRIGATION_FACTORS = {
    "furrow": {"water_score": 0.0, "label": "Furrow / бороздовое"},
    "sprinkler": {"water_score": 0.1, "label": "Sprinkler / дождевание"},
    "drip": {"water_score": 0.25, "label": "Drip / капельное"},
    "mixed": {"water_score": 0.12, "label": "Mixed / смешанное"},
    "unknown": {"water_score": 0.0, "label": "Unknown / неизвестно"},
}

def economic_climate_effect(
    *, energy_kwh, freshwater_m3, electricity_tariff, water_tariff,
    emission_factor, current_solar_share, target_solar_share, water_saving_target,
):
    """Counterfactual savings with explicit missingness (None != measured zero).

    Unknown electricity excludes energy cost, electricity emissions, and joint
    savings from publication. Water-only savings remain reportable if known.
    """
    from math import isfinite
    def available_nonnegative(v, label):
        if v is None or v == '':
            return None
        x = float(v)
        if not isfinite(x) or x < 0:
            raise ValueError(f'{label} must be finite and nonnegative')
        return x
    energy = available_nonnegative(energy_kwh, 'energy_kwh')
    water = available_nonnegative(freshwater_m3, 'freshwater_m3')
    electricity_price = available_nonnegative(electricity_tariff,'electricity_tariff')
    water_price = available_nonnegative(water_tariff,'water_tariff')
    ef = available_nonnegative(emission_factor,'emission_factor')
    current_pct = available_nonnegative(current_solar_share,'current_solar_share')
    target_pct = available_nonnegative(target_solar_share,'target_solar_share')
    water_saving_pct = available_nonnegative(water_saving_target,'water_saving_target')
    current_share = min(current_pct or 0.,100.)/100.
    target_share = max(current_share, min(target_pct or 0.,100.)/100.)
    target_water_fraction = min(water_saving_pct or 0.,100.)/100.
    grid_now = energy*(1-current_share) if energy is not None else None
    grid_future = energy*(1-target_share) if energy is not None else None
    green_added = max(0.,grid_now-grid_future) if grid_now is not None else None
    energy_cost_now = grid_now*electricity_price if grid_now is not None and electricity_price is not None else None
    energy_cost_future = grid_future*electricity_price if grid_future is not None and electricity_price is not None else None
    energy_saving = max(0.,energy_cost_now-energy_cost_future) if energy_cost_now is not None else None
    co2_now = grid_now*ef if grid_now is not None and ef is not None else None
    co2_future = grid_future*ef if grid_future is not None and ef is not None else None
    co2_reduction = max(0.,co2_now-co2_future) if co2_now is not None else None
    water_target = water*(1-target_water_fraction) if water is not None else None
    water_cost_now = water*water_price if water is not None and water_price is not None else None
    water_cost_future = water_target*water_price if water_target is not None and water_price is not None else None
    water_saving = max(0.,water-water_target) if water is not None else None
    water_saving_money = max(0.,water_cost_now-water_cost_future) if water_cost_now is not None else None
    total_saving = (energy_saving+water_saving_money
                    if energy_saving is not None and water_saving_money is not None else None)
    return {
        'current_grid_energy_kwh':grid_now,'target_grid_energy_kwh':grid_future,
        'green_energy_added_kwh':green_added,
        'current_energy_cost_kzt':energy_cost_now,'target_energy_cost_kzt':energy_cost_future,
        'energy_saving_kzt':energy_saving,'current_co2_kg':co2_now,
        'target_co2_kg':co2_future,'co2_reduction_kg':co2_reduction,
        'current_water_cost_kzt':water_cost_now,'target_water_cost_kzt':water_cost_future,
        'water_saving_m3':water_saving,'water_saving_kzt':water_saving_money,
        'total_saving_kzt':total_saving,'current_solar_share_pct':100*current_share,
        'target_solar_share_pct':100*target_share,'water_saving_target_pct':100*target_water_fraction,
        'data_completeness_status':'complete' if total_saving is not None else 'partial_unknown',
        'missing_components':[k for k,v in [('electricity',energy_saving),('water',water_saving_money)] if v is None],
    }

def payback_years(investment_kzt, seasonal_saving_kzt, seasons_per_year=1):
    investment_kzt = float(investment_kzt or 0)
    seasonal_saving_kzt = float(seasonal_saving_kzt or 0)
    seasons_per_year = max(1, float(seasons_per_year or 1))
    annual_saving = seasonal_saving_kzt * seasons_per_year
    if investment_kzt <= 0 or annual_saving <= 0:
        return None
    return investment_kzt / annual_saving
