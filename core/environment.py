from __future__ import annotations

import math
import pandas as pd

from .data import load_district_climate_fallback, district_climate


def _percentile(series: pd.Series, value: float, higher_is_higher: bool = True) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    if s.empty:
        return float("nan")
    pct = float((s <= float(value)).mean() * 100.0)
    return pct if higher_is_higher else 100.0 - pct


def climate_environment_profile(district: str, climate: dict | None = None) -> dict:
    """Describe district climate exposure relative to the 17-territory reference set.

    This is a descriptive percentile profile, not an ecosystem-health score. Higher heat
    percentile means warmer growing-season conditions; higher dryness percentiles mean
    lower precipitation / lower root-zone wetness relative to other territorial points.
    """
    ref = load_district_climate_fallback().copy()
    current = dict(district_climate(district) or {})
    current.update(climate or {})

    t = current.get("Apr-Sep temperature, °C")
    p = current.get("Apr-Sep precipitation, mm")
    w = current.get("Apr-Sep root-zone wetness")
    s = current.get("Apr-Sep solar radiation, MJ/m²/day")

    out = {
        "temperature_c": float(t) if t is not None else None,
        "precipitation_mm": float(p) if p is not None else None,
        "root_zone_wetness": float(w) if w is not None else None,
        "solar_radiation_mj_m2_day": float(s) if s is not None else None,
    }
    if t is not None:
        out["heat_exposure_percentile"] = _percentile(ref["Apr-Sep temperature, °C"], float(t), True)
    if p is not None:
        out["low_precipitation_percentile"] = _percentile(ref["Apr-Sep precipitation, mm"], float(p), False)
    if w is not None:
        out["low_soil_moisture_percentile"] = _percentile(ref["Apr-Sep root-zone wetness"], float(w), False)
    if s is not None:
        out["solar_radiation_percentile"] = _percentile(ref["Apr-Sep solar radiation, MJ/m²/day"], float(s), True)
    return out


def environmental_diagnostics(
    district: str,
    climate: dict | None,
    area_ha: float,
    energy_kwh: float = 0.0,
    emission_factor_kgco2_kwh: float = 0.0,
    pesticide_kg_ha: float | None = None,
    salinized_share_pct: float | None = None,
) -> dict:
    """Environmental diagnostics with explicit evidence boundaries.

    Climate comes from the district/NASA climate layer. Energy, pesticide and salinity
    are calculated only when the user supplies those observations. No missing value is
    silently replaced by a fabricated district estimate.
    """
    area = max(float(area_ha or 0.0), 0.0)
    profile = climate_environment_profile(district, climate)
    out = dict(profile)
    out["area_ha"] = area

    energy = max(float(energy_kwh or 0.0), 0.0)
    ef = max(float(emission_factor_kgco2_kwh or 0.0), 0.0)
    energy_observed = bool(energy > 0 and ef > 0)
    out["energy_observed"] = energy_observed
    if energy_observed:
        co2 = energy * ef
        out["operational_co2e_kg"] = co2
        out["operational_co2e_kg_ha"] = co2 / area if area > 0 else None

    pesticide_observed = pesticide_kg_ha is not None
    out["pesticide_observed"] = pesticide_observed
    if pesticide_observed:
        pesticide = max(float(pesticide_kg_ha), 0.0)
        out["pesticide_kg_ha"] = pesticide
        out["pesticide_total_kg"] = pesticide * area if area > 0 else None

    salinity_observed = salinized_share_pct is not None
    out["salinity_observed"] = salinity_observed
    if salinity_observed:
        salinity = min(max(float(salinized_share_pct), 0.0), 100.0)
        out["salinized_share_pct"] = salinity
        out["salinized_area_ha"] = area * salinity / 100.0 if area > 0 else None

    # Four district climate observations are automatic: temperature, precipitation,
    # root-zone wetness and solar radiation. Optional layers are counted only when
    # they are supported by explicit observations. Missing is never treated as zero.
    climate_layers = sum(out.get(k) is not None for k in (
        "temperature_c", "precipitation_mm", "root_zone_wetness", "solar_radiation_mj_m2_day"
    ))
    optional_layers = int(energy_observed) + int(pesticide_observed) + int(salinity_observed)
    out["evidence_layers_available"] = climate_layers + optional_layers
    out["evidence_layers_max"] = 7
    return out


def diversification_metrics(shares) -> dict:
    """Concentration/diversification metrics for an optimized crop structure."""
    vals = [max(float(x), 0.0) for x in shares if x is not None and not math.isnan(float(x))]
    total = sum(vals)
    if total <= 0:
        return {"hhi": None, "effective_number_of_crops": None, "diversification_0_100": None}
    p = [x / total for x in vals if x > 0]
    n = len(p)
    hhi = sum(x * x for x in p)
    effective = 1.0 / hhi if hhi > 0 else None
    if n <= 1:
        div = 0.0
    else:
        div = 100.0 * (1.0 - hhi) / (1.0 - 1.0 / n)
    return {"hhi": hhi, "effective_number_of_crops": effective, "diversification_0_100": max(0.0, min(100.0, div))}
