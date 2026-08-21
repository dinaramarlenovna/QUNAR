from __future__ import annotations

import json
import math
import sys
import types
from pathlib import Path

import pandas as pd

# The deployed app has Streamlit. This small fallback allows reproducible CLI QA
# in environments where Streamlit is intentionally not installed.
try:
    import streamlit  # noqa: F401
except ModuleNotFoundError:
    class _Cache:
        def __call__(self, *args, **kwargs):
            def deco(fn):
                return fn
            return deco
    sys.modules["streamlit"] = types.SimpleNamespace(cache_data=_Cache(), cache_resource=_Cache())

from core.config import DISTRICT_ORDER
from core.livestock import (
    DEFAULT_PRODUCT,
    SPECIES,
    load_livestock_panel,
    load_region_population,
    load_region_products,
    livestock_resource_metrics,
    reference_requirements,
    train_livestock_forecast_model,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _finite_or_none(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def main():
    panel = load_livestock_panel()
    products = load_region_products()
    population = load_region_population()
    model, metrics = train_livestock_forecast_model()

    by_species = []
    for species, m in sorted(metrics.get("by_species", {}).items()):
        by_species.append({
            "benchmark_species": species,
            "n_validation": int(m.get("n", 0)),
            "r2_log": _finite_or_none(m.get("r2_log")),
            "mae_heads": _finite_or_none(m.get("mae_heads")),
            "median_ape_pct": _finite_or_none(m.get("median_ape_pct")),
            "mape_pct": _finite_or_none(m.get("mape_pct")),
        })
    pd.DataFrame(by_species).to_csv(DATA / "livestock_validation_by_species.csv", index=False)

    errors = []
    checked = 0
    # Avoid refitting on each test case in non-Streamlit CLI mode.
    import core.livestock as lv
    lv.train_livestock_forecast_model = lambda: (model, metrics)

    for district in DISTRICT_ORDER:
        for species in SPECIES:
            try:
                out = livestock_resource_metrics(
                    district=district,
                    species=species,
                    heads=0.0,
                    pasture_ha=100.0,
                    fodder_t=0.0,
                    available_water_m3=0.0,
                    water_used_m3=0.0,
                    energy_kwh=0.0,
                    emission_factor_kgco2_kwh=0.6061,
                    production_amount=0.0,
                    production_kind=DEFAULT_PRODUCT[species],
                    pasture_degraded_share_pct=None,
                    climate=None,
                )
                checked += 1
                if out.get("heads", 0) > 0:
                    assert out.get("reference_water_m3_year") is not None
                    assert out.get("livestock_units") is not None
                if species == "Poultry broilers":
                    assert out.get("reference_feed_dm_t_year") is None
            except Exception as exc:
                errors.append({"district": district, "species": species, "error": repr(exc)})

    pig = metrics.get("by_species", {}).get("Pigs", {})
    pig_guard_expected = (
        _finite_or_none(pig.get("r2_log")) is None
        or float(pig.get("r2_log", 0)) <= 0
        or float(pig.get("median_ape_pct", 999)) > 50
    )

    qa = {
        "version": "0.8.1-livestock-core",
        "raw_district_year_species_observations": int(len(panel)),
        "districts_in_livestock_panel": int(panel["District"].nunique()),
        "benchmark_species_in_panel": sorted(panel["Species"].unique().tolist()),
        "regional_product_years": [int(products["Year"].min()), int(products["Year"].max())],
        "regional_population_years": [int(population["Year"].min()), int(population["Year"].max())],
        "training_n": int(metrics["training_n"]),
        "training_years": [int(metrics["training_year_min"]), int(metrics["training_year_max"])],
        "validation_years": [int(x) for x in metrics["validation_years"]],
        "validation_n": int(metrics["validation_n"]),
        "validation_r2_log_overall": _finite_or_none(metrics["r2_log"]),
        "validation_median_ape_pct_overall": _finite_or_none(metrics["median_ape_pct"]),
        "validation_by_species": by_species,
        "forecast_guard": {
            "rule": "publish only when category R2_log > 0 and median APE <= 50%; validated tier requires R2_log >= 0.50 and median APE <= 30%",
            "pig_guard_expected_from_current_validation": bool(pig_guard_expected),
        },
        "reference_checks": {
            "100_cattle_at_25C": reference_requirements("Cattle", 100, 25),
            "100_poultry_broilers_at_25C": reference_requirements("Poultry broilers", 100, 25),
        },
        "matrix_test_cases": checked,
        "matrix_errors": errors,
        "pass": len(errors) == 0 and checked == len(DISTRICT_ORDER) * len(SPECIES) and pig_guard_expected,
    }
    (ROOT / "QA_LIVESTOCK_V0_8_1.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(qa, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
