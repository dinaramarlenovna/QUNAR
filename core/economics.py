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


DEFAULT_EF_KZ_KGCO2_PER_KWH = _reference_value("electricity_emission_factor", 0.6061)
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
    *,
    energy_kwh,
    freshwater_m3,
    electricity_tariff,
    water_tariff,
    emission_factor,
    current_solar_share,
    target_solar_share,
    water_saving_target,
):
    energy_kwh = float(energy_kwh or 0)
    freshwater_m3 = float(freshwater_m3 or 0)
    electricity_tariff = float(electricity_tariff or 0)
    water_tariff = float(water_tariff or 0)
    emission_factor = float(emission_factor or 0)
    current_solar_share = max(0, min(float(current_solar_share or 0), 100)) / 100
    target_solar_share = max(current_solar_share, min(float(target_solar_share or 0), 100) / 100)
    water_saving_target = max(0, min(float(water_saving_target or 0), 100)) / 100

    current_grid_energy = energy_kwh * (1 - current_solar_share)
    target_grid_energy = energy_kwh * (1 - target_solar_share)
    green_energy_added = max(0, current_grid_energy - target_grid_energy)

    current_energy_cost = current_grid_energy * electricity_tariff
    target_energy_cost = target_grid_energy * electricity_tariff
    energy_saving_kzt = max(0, current_energy_cost - target_energy_cost)

    current_co2 = current_grid_energy * emission_factor
    target_co2 = target_grid_energy * emission_factor
    co2_reduction = max(0, current_co2 - target_co2)

    current_water_cost = freshwater_m3 * water_tariff
    target_freshwater = freshwater_m3 * (1 - water_saving_target)
    target_water_cost = target_freshwater * water_tariff
    water_saving_m3 = max(0, freshwater_m3 - target_freshwater)
    water_saving_kzt = max(0, current_water_cost - target_water_cost)

    total_saving_kzt = energy_saving_kzt + water_saving_kzt

    return {
        "current_grid_energy_kwh": current_grid_energy,
        "target_grid_energy_kwh": target_grid_energy,
        "green_energy_added_kwh": green_energy_added,
        "current_energy_cost_kzt": current_energy_cost,
        "target_energy_cost_kzt": target_energy_cost,
        "energy_saving_kzt": energy_saving_kzt,
        "current_co2_kg": current_co2,
        "target_co2_kg": target_co2,
        "co2_reduction_kg": co2_reduction,
        "current_water_cost_kzt": current_water_cost,
        "target_water_cost_kzt": target_water_cost,
        "water_saving_m3": water_saving_m3,
        "water_saving_kzt": water_saving_kzt,
        "total_saving_kzt": total_saving_kzt,
        "current_solar_share_pct": current_solar_share * 100,
        "target_solar_share_pct": target_solar_share * 100,
        "water_saving_target_pct": water_saving_target * 100,
    }

def payback_years(investment_kzt, seasonal_saving_kzt, seasons_per_year=1):
    investment_kzt = float(investment_kzt or 0)
    seasonal_saving_kzt = float(seasonal_saving_kzt or 0)
    seasons_per_year = max(1, float(seasons_per_year or 1))
    annual_saving = seasonal_saving_kzt * seasons_per_year
    if investment_kzt <= 0 or annual_saving <= 0:
        return None
    return investment_kzt / annual_saving
