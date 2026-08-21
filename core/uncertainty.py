
def support_score(
    *,
    live_climate=False,
    exact_location=False,
    actual_water=False,
    actual_energy=False,
    emission_factor=False,
    wapor_used=False,
    wapor_pixels=None,
    area_geometry_mismatch=False,
    ml_mae=None,
    historical_yield_median=None,
):
    """
    Transparent support index (0-100), NOT a statistical confidence interval.

    60 points = data support/directness.
    40 points = model validation support.
    Spatial WaPOR penalties are applied only when WaPOR is actually used.
    """
    data_weights = {
        "exact_location": 12,
        "live_climate": 14,
        "actual_water": 14,
        "actual_energy": 10,
        "emission_factor": 10,
    }
    flags = {
        "exact_location": bool(exact_location),
        "live_climate": bool(live_climate),
        "actual_water": bool(actual_water),
        "actual_energy": bool(actual_energy),
        "emission_factor": bool(emission_factor),
    }
    data_score = sum(data_weights[k] for k,v in flags.items() if v)

    # Current validation is global/by-year. Convert relative MAE into a transparent 0-40 support component.
    model_score = 0.0
    relative_mae = None
    if ml_mae is not None and historical_yield_median not in (None, 0):
        relative_mae = abs(float(ml_mae)) / abs(float(historical_yield_median))
        model_score = 40.0 * max(0.0, 1.0 - min(relative_mae, 1.0))

    spatial_penalty = 0
    spatial_class = None
    if wapor_used and wapor_pixels is not None:
        p = int(wapor_pixels)
        if p <= 1:
            spatial_penalty, spatial_class = 12, "very_low"
        elif p <= 3:
            spatial_penalty, spatial_class = 7, "low"
        elif p <= 9:
            spatial_penalty, spatial_class = 3, "moderate"
        else:
            spatial_class = "good"

    geometry_penalty = 8 if area_geometry_mismatch else 0
    total = max(0, min(100, round(data_score + model_score - spatial_penalty - geometry_penalty)))
    level = "high" if total >= 75 else "medium" if total >= 45 else "low"
    return {
        "score": total,
        "level": level,
        "data_score": round(data_score, 1),
        "model_score": round(model_score, 1),
        "relative_mae": relative_mae,
        "components": flags,
        "wapor_pixels": wapor_pixels,
        "wapor_spatial_class": spatial_class,
        "spatial_penalty": spatial_penalty,
        "geometry_penalty": geometry_penalty,
        "area_geometry_mismatch": bool(area_geometry_mismatch),
        "definition": "transparent support index; not a statistical confidence interval",
    }

# backward compatibility
reliability_score = support_score
