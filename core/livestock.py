from __future__ import annotations

from pathlib import Path
import math
import numpy as np
import pandas as pd
import streamlit as st

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .environment import climate_environment_profile

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DISTRICT_STRUCTURE = DATA_DIR / "district_ag_structure_2023.csv"
DISTRICT_PANEL = DATA_DIR / "livestock_district_panel_2015_2023.csv"
REGION_PRODUCTS = DATA_DIR / "livestock_region_products_1996_2023.csv"
REGION_POPULATION = DATA_DIR / "livestock_region_population_1996_2023.csv"
REFERENCE_NORMS = DATA_DIR / "livestock_reference_norms.csv"
CLIMATE_PANEL = DATA_DIR / "analytical_panel.csv"

SPECIES = [
    "Cattle",
    "Dairy cows",
    "Sheep",
    "Goats",
    "Pigs",
    "Horses",
    "Camels",
    "Poultry layers",
    "Poultry broilers",
]

SPECIES_LABELS = {
    "ru": {
        "Cattle": "Крупный рогатый скот",
        "Dairy cows": "Молочные коровы",
        "Sheep": "Овцы",
        "Goats": "Козы",
        "Pigs": "Свиньи",
        "Horses": "Лошади",
        "Camels": "Верблюды",
        "Poultry layers": "Птица - яичное направление",
        "Poultry broilers": "Птица - мясное направление",
    },
    "kk": {
        "Cattle": "Ірі қара мал",
        "Dairy cows": "Сауын сиырлар",
        "Sheep": "Қой",
        "Goats": "Ешкі",
        "Pigs": "Шошқа",
        "Horses": "Жылқы",
        "Camels": "Түйе",
        "Poultry layers": "Құс - жұмыртқа бағыты",
        "Poultry broilers": "Құс - ет бағыты",
    },
    "en": {
        "Cattle": "Cattle",
        "Dairy cows": "Dairy cows",
        "Sheep": "Sheep",
        "Goats": "Goats",
        "Pigs": "Pigs",
        "Horses": "Horses",
        "Camels": "Camels",
        "Poultry layers": "Poultry - layers",
        "Poultry broilers": "Poultry - broilers",
    },
}

PRODUCT_TYPES = ["meat_tonnes", "milk_tonnes", "wool_tonnes", "thousand_eggs", "other_tonnes"]
PRODUCT_LABELS = {
    "ru": {
        "meat_tonnes": "Мясо в живом весе, т",
        "milk_tonnes": "Молоко, т",
        "wool_tonnes": "Шерсть, т",
        "thousand_eggs": "Яйца, тыс. шт.",
        "other_tonnes": "Другая продукция, т",
    },
    "kk": {
        "meat_tonnes": "Тірі салмақтағы ет, т",
        "milk_tonnes": "Сүт, т",
        "wool_tonnes": "Жүн, т",
        "thousand_eggs": "Жұмыртқа, мың дана",
        "other_tonnes": "Басқа өнім, т",
    },
    "en": {
        "meat_tonnes": "Meat, live weight, t",
        "milk_tonnes": "Milk, t",
        "wool_tonnes": "Wool, t",
        "thousand_eggs": "Eggs, thousand",
        "other_tonnes": "Other output, t",
    },
}

DEFAULT_PRODUCT = {
    "Cattle": "meat_tonnes",
    "Dairy cows": "milk_tonnes",
    "Sheep": "wool_tonnes",
    "Goats": "milk_tonnes",
    "Pigs": "meat_tonnes",
    "Horses": "meat_tonnes",
    "Camels": "milk_tonnes",
    "Poultry layers": "thousand_eggs",
    "Poultry broilers": "meat_tonnes",
}

GRAZING_SPECIES = {"Cattle", "Dairy cows", "Sheep", "Goats", "Horses", "Camels"}


@st.cache_data(show_spinner=False)
def load_district_structure() -> pd.DataFrame:
    return pd.read_csv(DISTRICT_STRUCTURE)


@st.cache_data(show_spinner=False)
def load_livestock_panel() -> pd.DataFrame:
    df = pd.read_csv(DISTRICT_PANEL)
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
    df["Heads"] = pd.to_numeric(df["Heads"], errors="coerce")
    return df.dropna(subset=["District", "Year", "Species", "Heads"]).copy()


@st.cache_data(show_spinner=False)
def load_region_products() -> pd.DataFrame:
    return pd.read_csv(REGION_PRODUCTS)


@st.cache_data(show_spinner=False)
def load_region_population() -> pd.DataFrame:
    return pd.read_csv(REGION_POPULATION)


@st.cache_data(show_spinner=False)
def load_reference_norms() -> pd.DataFrame:
    return pd.read_csv(REFERENCE_NORMS)


@st.cache_data(show_spinner=False)
def load_livestock_climate_panel() -> pd.DataFrame:
    """Unique district-year growing-season climate extracted from the QŪNAR analytical panel."""
    df = pd.read_csv(CLIMATE_PANEL, encoding="utf-8-sig")
    cols = [
        "District", "Year", "Apr-Sep temperature, °C", "Apr-Sep precipitation, mm",
        "Apr-Sep root-zone wetness", "Apr-Sep solar radiation, MJ/m²/day",
    ]
    out = df[cols].copy()
    out["Year"] = pd.to_numeric(out["Year"], errors="coerce")
    for c in cols[2:]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.dropna(subset=["District", "Year"]).drop_duplicates(["District", "Year"])


def species_norm(species: str) -> dict:
    df = load_reference_norms()
    row = df[df["Species"].astype(str).eq(str(species))]
    if row.empty:
        return {}
    r = row.iloc[0]
    dm_raw = pd.to_numeric(pd.Series([r.get("DM_kg_head_day")]), errors="coerce").iloc[0]
    return {
        "species": str(r["Species"]),
        "benchmark_species": str(r["Benchmark_species"]),
        "lu_factor": float(r["LU_factor_Asia"]),
        "dm_kg_head_day": float(dm_raw) if pd.notna(dm_raw) else None,
        "water_l_day_15c": float(r["Water_L_head_day_15C"]),
        "water_l_day_25c": float(r["Water_L_head_day_25C"]),
        "water_l_day_35c": float(r["Water_L_head_day_35C"]),
        "reference_condition": str(r.get("Reference_condition", "")),
        "source_short": str(r["Source_short"]),
    }


def _interp_water(temp_c: float | None, w15: float, w25: float, w35: float) -> tuple[float, float]:
    """Return reference L/head/day and temperature actually used for the reference.

    FAO provides anchors at 15, 25 and 35 C for most species. Values outside that
    interval are capped at the nearest anchor, avoiding undocumented extrapolation.
    """
    t = 25.0 if temp_c is None or not np.isfinite(float(temp_c)) else float(temp_c)
    tc = min(35.0, max(15.0, t))
    if tc <= 25.0:
        val = w15 + (w25 - w15) * (tc - 15.0) / 10.0
    else:
        val = w25 + (w35 - w25) * (tc - 25.0) / 10.0
    return float(val), float(tc)


def reference_requirements(species: str, heads: float, temperature_c: float | None = None) -> dict:
    norm = species_norm(species)
    n = max(float(heads or 0.0), 0.0)
    if not norm or n <= 0:
        return {
            "reference_water_l_head_day": None,
            "reference_water_m3_year": None,
            "reference_feed_dm_t_year": None,
            "livestock_units": None,
            "lu_factor": norm.get("lu_factor") if norm else None,
        }
    water_l_day, temp_used = _interp_water(
        temperature_c,
        norm["water_l_day_15c"],
        norm["water_l_day_25c"],
        norm["water_l_day_35c"],
    )
    return {
        "reference_temperature_c": temp_used,
        "reference_water_l_head_day": water_l_day,
        "reference_water_m3_year": water_l_day * n * 365.0 / 1000.0,
        "reference_feed_dm_kg_head_day": norm["dm_kg_head_day"],
        "reference_feed_dm_t_year": (
            norm["dm_kg_head_day"] * n * 365.0 / 1000.0
            if norm.get("dm_kg_head_day") is not None else None
        ),
        "lu_factor": norm["lu_factor"],
        "livestock_units": norm["lu_factor"] * n,
        "reference_source": norm["source_short"],
        "reference_condition": norm.get("reference_condition"),
        "benchmark_species": norm["benchmark_species"],
    }


def district_livestock_profile(district: str) -> dict:
    df = load_district_structure()
    row = df[df["District"].astype(str).eq(str(district))]
    if row.empty:
        return {}
    r = row.iloc[0]
    share = float(r["Livestock_share_pct"])
    ref = pd.to_numeric(df["Livestock_share_pct"], errors="coerce").dropna()
    pct = float((ref <= share).mean() * 100.0) if not ref.empty else None
    return {
        "gross_output_mln_kzt": float(r["Gross_output_mln_KZT"]),
        "livestock_output_mln_kzt": float(r["Livestock_output_mln_KZT"]),
        "crop_output_mln_kzt": float(r["Crop_output_mln_KZT"]),
        "livestock_share_pct": share,
        "livestock_share_percentile": pct,
        "sown_area_th_ha": float(r["Sown_area_th_ha"]),
    }


def district_species_history(district: str, species: str) -> pd.DataFrame:
    norm = species_norm(species)
    benchmark_species = norm.get("benchmark_species", species)
    df = load_livestock_panel()
    out = df[
        df["District"].astype(str).eq(str(district))
        & df["Species"].astype(str).eq(str(benchmark_species))
    ][["Year", "Heads"]].sort_values("Year")
    return out.reset_index(drop=True)


def district_species_benchmark(district: str, species: str) -> dict:
    norm = species_norm(species)
    benchmark_species = norm.get("benchmark_species", species)
    df = load_livestock_panel()
    hist = district_species_history(district, species)
    if hist.empty:
        return {"benchmark_species": benchmark_species}
    latest = hist.iloc[-1]
    year = int(latest["Year"])
    heads = float(latest["Heads"])
    cross = df[
        (df["Year"] == year)
        & df["Species"].astype(str).eq(str(benchmark_species))
    ]["Heads"].astype(float)
    percentile = float((cross <= heads).mean() * 100.0) if len(cross) else None
    first = hist.iloc[0]
    years = max(int(latest["Year"]) - int(first["Year"]), 0)
    cagr = None
    if years > 0 and float(first["Heads"]) > 0 and heads > 0:
        cagr = ((heads / float(first["Heads"])) ** (1.0 / years) - 1.0) * 100.0
    if len(hist) >= 3:
        x = hist["Year"].astype(float).to_numpy()
        y = np.log1p(hist["Heads"].astype(float).to_numpy())
        slope = float(np.polyfit(x, y, 1)[0])
        annual_trend = (math.exp(slope) - 1.0) * 100.0
    else:
        annual_trend = cagr
    return {
        "benchmark_species": benchmark_species,
        "latest_year": year,
        "latest_district_heads": heads,
        "district_percentile": percentile,
        "history_start_year": int(first["Year"]),
        "history_start_heads": float(first["Heads"]),
        "cagr_pct": cagr,
        "log_trend_pct_year": annual_trend,
        "observations": int(len(hist)),
    }


def regional_productivity_benchmarks(year: int = 2023) -> dict:
    prod = load_region_products()
    pop = load_region_population()
    p = prod[prod["Year"] == year]
    h = pop[pop["Year"] == year]
    if p.empty or h.empty:
        return {}
    p = p.iloc[0]
    h = h.iloc[0]
    lu_total = (
        float(h["Cattle"]) * 0.50
        + float(h["Sheep_goats"]) * 0.10
        + float(h["Pigs"]) * 0.25
        + float(h["Horses"]) * 0.80
        + float(h["Camels"]) * 1.10
        + float(h["Poultry"]) * 0.01
    )
    return {
        "year": int(year),
        "milk_kg_per_cow": float(p["Cow_milk_t"]) * 1000.0 / float(h["Cows"]) if float(h["Cows"]) > 0 else None,
        "eggs_per_bird": float(p["Eggs_thousand"]) * 1000.0 / float(h["Poultry"]) if float(h["Poultry"]) > 0 else None,
        "wool_kg_per_sheep_goat": float(p["Wool_t"]) * 1000.0 / float(h["Sheep_goats"]) if float(h["Sheep_goats"]) > 0 else None,
        "aggregate_meat_kg_per_lu": float(p["Meat_live_t"]) * 1000.0 / lu_total if lu_total > 0 else None,
        "meat_live_t": float(p["Meat_live_t"]),
        "cow_milk_t": float(p["Cow_milk_t"]),
        "eggs_thousand": float(p["Eggs_thousand"]),
        "wool_t": float(p["Wool_t"]),
    }


def regional_product_trend(product_kind: str, start_year: int = 2015, end_year: int = 2023) -> dict:
    col = {
        "meat_tonnes": "Meat_live_t",
        "milk_tonnes": "Cow_milk_t",
        "thousand_eggs": "Eggs_thousand",
        "wool_tonnes": "Wool_t",
    }.get(product_kind)
    if col is None:
        return {}
    df = load_region_products()
    d = df[(df["Year"] >= start_year) & (df["Year"] <= end_year)][["Year", col]].dropna()
    if d.empty:
        return {}
    first, last = d.iloc[0], d.iloc[-1]
    years = int(last["Year"] - first["Year"])
    cagr = None
    if years > 0 and float(first[col]) > 0 and float(last[col]) > 0:
        cagr = ((float(last[col]) / float(first[col])) ** (1.0 / years) - 1.0) * 100.0
    return {
        "start_year": int(first["Year"]),
        "end_year": int(last["Year"]),
        "start_value": float(first[col]),
        "end_value": float(last[col]),
        "cagr_pct": cagr,
        "series": d.rename(columns={col: "Value"}).to_dict("records"),
    }


def _forecast_training_frame() -> pd.DataFrame:
    df = load_livestock_panel().copy()
    # Current-administration period is used to reduce artificial pre-reform discontinuity.
    df = df[df["Year"] >= 2018].sort_values(["District", "Species", "Year"])
    df["Lag_heads"] = df.groupby(["District", "Species"])["Heads"].shift(1)
    df = df.dropna(subset=["Lag_heads", "Heads"])

    climate = load_livestock_climate_panel().copy()
    rename = {
        "Apr-Sep temperature, °C": "clim_temp",
        "Apr-Sep precipitation, mm": "clim_precip",
        "Apr-Sep root-zone wetness": "clim_root_wetness",
        "Apr-Sep solar radiation, MJ/m²/day": "clim_solar",
    }
    climate = climate.rename(columns=rename)
    df = df.merge(climate, on=["District", "Year"], how="left")

    climate_cols = list(rename.values())
    # Missing district-year climate is kept visible through an imputation flag.
    df["climate_imputed"] = df[climate_cols].isna().any(axis=1).astype(int)
    for c in climate_cols:
        year_median = df.groupby("Year")[c].transform("median")
        df[c] = df[c].fillna(year_median).fillna(df[c].median())

    df["log_lag_heads"] = np.log1p(df["Lag_heads"].astype(float))
    df["log_heads"] = np.log1p(df["Heads"].astype(float))
    return df

def _new_forecast_pipeline() -> Pipeline:
    categorical = ["District", "Species"]
    numeric = ["Year", "log_lag_heads", "clim_temp", "clim_precip", "clim_root_wetness", "clim_solar", "climate_imputed"]
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
        ("num", "passthrough", numeric),
    ])
    model = RandomForestRegressor(
        n_estimators=350,
        max_depth=12,
        min_samples_leaf=2,
        max_features=0.75,
        random_state=42,
        n_jobs=-1,
    )
    return Pipeline([("pre", pre), ("model", model)])


_cache_resource = getattr(st, "cache_resource", st.cache_data)

@_cache_resource(show_spinner=False)
def train_livestock_forecast_model():
    df = _forecast_training_frame()
    features = ["District", "Species", "Year", "log_lag_heads", "clim_temp", "clim_precip", "clim_root_wetness", "clim_solar", "climate_imputed"]
    pred_parts = []
    # Rolling-origin validation: each validation year is forecast only from earlier years.
    for year in sorted(int(y) for y in df["Year"].unique() if int(y) >= 2021):
        train = df[df["Year"] < year]
        test = df[df["Year"] == year]
        if len(train) < 80 or len(test) < 10:
            continue
        pipe = _new_forecast_pipeline()
        pipe.fit(train[features], train["log_heads"])
        pred_log = pipe.predict(test[features])
        tmp = test[["District", "Species", "Year", "Heads"]].copy()
        tmp["pred_log"] = pred_log
        tmp["pred_heads"] = np.expm1(pred_log).clip(min=0)
        pred_parts.append(tmp)

    if pred_parts:
        val = pd.concat(pred_parts, ignore_index=True)
        y_log = np.log1p(val["Heads"].astype(float).to_numpy())
        p_log = val["pred_log"].astype(float).to_numpy()
        r2_log = float(r2_score(y_log, p_log))
        mae_heads = float(mean_absolute_error(val["Heads"], val["pred_heads"]))
        denom = np.maximum(val["Heads"].astype(float).to_numpy(), 1.0)
        mape = float(np.mean(np.abs(val["pred_heads"].to_numpy() - val["Heads"].to_numpy()) / denom) * 100.0)
        median_ape = float(np.median(np.abs(val["pred_heads"].to_numpy() - val["Heads"].to_numpy()) / denom) * 100.0)
        validation_n = int(len(val))
        validation_years = sorted(int(x) for x in val["Year"].unique())
        by_species = {}
        for sp, g in val.groupby("Species"):
            actual = g["Heads"].astype(float).to_numpy()
            pred = g["pred_heads"].astype(float).to_numpy()
            actual_log = np.log1p(actual)
            pred_log_sp = g["pred_log"].astype(float).to_numpy()
            r2_sp = float(r2_score(actual_log, pred_log_sp)) if len(g) >= 3 and np.nanstd(actual_log) > 0 else float("nan")
            denom_sp = np.maximum(actual, 1.0)
            ape_sp = np.abs(pred - actual) / denom_sp * 100.0
            by_species[str(sp)] = {
                "n": int(len(g)),
                "r2_log": r2_sp,
                "mae_heads": float(mean_absolute_error(actual, pred)),
                "median_ape_pct": float(np.median(ape_sp)),
                "mape_pct": float(np.mean(ape_sp)),
            }
    else:
        r2_log = float("nan")
        mae_heads = float("nan")
        mape = float("nan")
        median_ape = float("nan")
        validation_n = 0
        validation_years = []
        by_species = {}

    final = _new_forecast_pipeline()
    final.fit(df[features], df["log_heads"])
    metrics = {
        "r2_log": r2_log,
        "mae_heads": mae_heads,
        "mape_pct": mape,
        "median_ape_pct": median_ape,
        "validation_n": validation_n,
        "validation_years": validation_years,
        "by_species": by_species,
        "training_n": int(len(df)),
        "training_year_min": int(df["Year"].min()),
        "training_year_max": int(df["Year"].max()),
        "method": "Random Forest with lagged herd size, district, species and growing-season climate; rolling-origin validation",
    }
    return final, metrics


def livestock_forecast(district: str, species: str, target_year: int = 2024) -> dict:
    norm = species_norm(species)
    benchmark_species = norm.get("benchmark_species", species)
    hist = district_species_history(district, species)
    if hist.empty:
        return {"available": False, "benchmark_species": benchmark_species}
    latest = hist.iloc[-1]
    latest_year = int(latest["Year"])
    if target_year != latest_year + 1:
        target_year = latest_year + 1
    model, metrics = train_livestock_forecast_model()
    climate = load_livestock_climate_panel()
    dcl = climate[climate["District"].astype(str).eq(str(district))].sort_values("Year")
    climate_imputed = 0
    if dcl.empty:
        # Otyrar and any future missing district use the latest regional median climate,
        # with the imputation flag exposed in the result.
        last_year = int(climate["Year"].max())
        csrc = climate[climate["Year"] == last_year].median(numeric_only=True)
        climate_imputed = 1
        clim_temp = float(csrc["Apr-Sep temperature, °C"])
        clim_precip = float(csrc["Apr-Sep precipitation, mm"])
        clim_root = float(csrc["Apr-Sep root-zone wetness"])
        clim_solar = float(csrc["Apr-Sep solar radiation, MJ/m²/day"])
        climate_reference_year = last_year
    else:
        csrc = dcl.iloc[-1]
        clim_temp = float(csrc["Apr-Sep temperature, °C"])
        clim_precip = float(csrc["Apr-Sep precipitation, mm"])
        clim_root = float(csrc["Apr-Sep root-zone wetness"])
        clim_solar = float(csrc["Apr-Sep solar radiation, MJ/m²/day"])
        climate_reference_year = int(csrc["Year"])
    x = pd.DataFrame([{
        "District": district,
        "Species": benchmark_species,
        "Year": int(target_year),
        "log_lag_heads": math.log1p(float(latest["Heads"])),
        "clim_temp": clim_temp,
        "clim_precip": clim_precip,
        "clim_root_wetness": clim_root,
        "clim_solar": clim_solar,
        "climate_imputed": climate_imputed,
    }])
    pred = max(float(np.expm1(model.predict(x)[0])), 0.0)
    change = (pred / float(latest["Heads"]) - 1.0) * 100.0 if float(latest["Heads"]) > 0 else None

    species_validation = dict(metrics.get("by_species", {}).get(str(benchmark_species), {}) or {})
    sp_r2 = species_validation.get("r2_log")
    sp_medape = species_validation.get("median_ape_pct")
    if sp_r2 is None or not np.isfinite(float(sp_r2)) or sp_medape is None or not np.isfinite(float(sp_medape)):
        forecast_tier = "insufficient_validation"
        publish_forecast = False
    elif float(sp_r2) >= 0.50 and float(sp_medape) <= 30.0:
        forecast_tier = "validated"
        publish_forecast = True
    elif float(sp_r2) > 0.0 and float(sp_medape) <= 50.0:
        forecast_tier = "exploratory"
        publish_forecast = True
    else:
        forecast_tier = "not_reliable"
        publish_forecast = False

    return {
        "available": True,
        "publish_forecast": publish_forecast,
        "forecast_tier": forecast_tier,
        "benchmark_species": benchmark_species,
        "forecast_year": int(target_year),
        "forecast_heads": pred,
        "previous_year": latest_year,
        "previous_heads": float(latest["Heads"]),
        "forecast_change_pct": change,
        "climate_reference_year": climate_reference_year,
        "climate_imputed": bool(climate_imputed),
        "species_validation": species_validation,
        **metrics,
    }


def livestock_resource_metrics(
    district: str,
    species: str,
    heads: float,
    pasture_ha: float,
    fodder_t: float,
    available_water_m3: float,
    water_used_m3: float,
    energy_kwh: float,
    emission_factor_kgco2_kwh: float,
    production_amount: float,
    production_kind: str,
    pasture_degraded_share_pct: float | None = None,
    climate: dict | None = None,
    use_district_reference_if_missing: bool = True,
) -> dict:
    benchmark = district_species_benchmark(district, species)
    entered_heads = max(float(heads or 0.0), 0.0)
    if entered_heads > 0:
        effective_heads = entered_heads
        heads_source = "user"
    elif use_district_reference_if_missing and benchmark.get("latest_district_heads") is not None:
        effective_heads = float(benchmark["latest_district_heads"])
        heads_source = "district_reference"
    else:
        effective_heads = 0.0
        heads_source = "unknown"

    pasture = max(float(pasture_ha or 0.0), 0.0)
    fodder = max(float(fodder_t or 0.0), 0.0)
    available = max(float(available_water_m3 or 0.0), 0.0)
    water = max(float(water_used_m3 or 0.0), 0.0)
    energy = max(float(energy_kwh or 0.0), 0.0)
    ef = max(float(emission_factor_kgco2_kwh or 0.0), 0.0)
    production = max(float(production_amount or 0.0), 0.0)
    degraded_observed = pasture_degraded_share_pct is not None
    degraded = min(max(float(pasture_degraded_share_pct), 0.0), 100.0) if degraded_observed else None

    climate_profile = climate_environment_profile(district, climate)
    requirements = reference_requirements(species, effective_heads, climate_profile.get("temperature_c"))
    forecast = livestock_forecast(district, species)
    regional_bench = regional_productivity_benchmarks()
    product_trend = regional_product_trend(production_kind)

    out = {
        "district": district,
        "species": species,
        "entered_heads": entered_heads,
        "heads": effective_heads,
        "heads_source": heads_source,
        "pasture_ha": pasture,
        "fodder_t_dm": fodder,
        "available_water_m3": available,
        "water_used_m3": water,
        "energy_kwh": energy,
        "production_amount": production,
        "production_kind": production_kind,
        "pasture_degraded_share_pct": degraded,
        "pasture_degradation_observed": degraded_observed,
        **district_livestock_profile(district),
        **climate_profile,
        **requirements,
        "district_benchmark": benchmark,
        "forecast": forecast,
        "regional_productivity": regional_bench,
        "regional_product_trend": product_trend,
    }

    if effective_heads > 0:
        if pasture > 0 and species in GRAZING_SPECIES:
            out["heads_per_pasture_ha"] = effective_heads / pasture
            if requirements.get("livestock_units") is not None:
                out["lu_per_pasture_ha"] = requirements["livestock_units"] / pasture
        if fodder > 0:
            out["fodder_kg_dm_per_head"] = fodder * 1000.0 / effective_heads
        if water > 0:
            out["water_m3_per_head"] = water / effective_heads
        if energy > 0:
            out["energy_kwh_per_head"] = energy / effective_heads
        if production > 0:
            if production_kind == "thousand_eggs":
                out["eggs_per_head"] = production * 1000.0 / effective_heads
            else:
                out["production_kg_per_head"] = production * 1000.0 / effective_heads
            if requirements.get("livestock_units") and production_kind == "meat_tonnes":
                out["meat_kg_per_lu"] = production * 1000.0 / requirements["livestock_units"]

    ref_water = requirements.get("reference_water_m3_year")
    if ref_water and water > 0:
        out["water_vs_reference_pct"] = water / ref_water * 100.0
    if ref_water and available > 0:
        out["reference_water_coverage_pct"] = available / ref_water * 100.0
    if available > 0 and water > 0:
        out["water_capacity_used_pct"] = water / available * 100.0

    ref_feed = requirements.get("reference_feed_dm_t_year")
    if ref_feed and fodder > 0:
        out["feed_reference_coverage_pct"] = fodder / ref_feed * 100.0

    if energy > 0 and ef > 0:
        co2 = energy * ef
        out["operational_co2e_kg"] = co2
        if effective_heads > 0:
            out["operational_co2e_kg_per_head"] = co2 / effective_heads

    if degraded_observed and pasture > 0:
        out["degraded_pasture_ha"] = pasture * degraded / 100.0

    # Product-specific benchmark comparisons use only compatible regional denominators.
    if production > 0 and effective_heads > 0:
        if species == "Dairy cows" and production_kind == "milk_tonnes" and regional_bench.get("milk_kg_per_cow"):
            own = production * 1000.0 / effective_heads
            out["productivity_reference_value"] = regional_bench["milk_kg_per_cow"]
            out["productivity_reference_ratio_pct"] = own / regional_bench["milk_kg_per_cow"] * 100.0
            out["productivity_reference_kind"] = "milk_kg_per_cow"
        elif species == "Poultry layers" and production_kind == "thousand_eggs" and regional_bench.get("eggs_per_bird"):
            own = production * 1000.0 / effective_heads
            out["productivity_reference_value"] = regional_bench["eggs_per_bird"]
            out["productivity_reference_ratio_pct"] = own / regional_bench["eggs_per_bird"] * 100.0
            out["productivity_reference_kind"] = "eggs_per_bird"
        elif species == "Sheep" and production_kind == "wool_tonnes" and regional_bench.get("wool_kg_per_sheep_goat"):
            own = production * 1000.0 / effective_heads
            out["productivity_reference_value"] = regional_bench["wool_kg_per_sheep_goat"]
            out["productivity_reference_ratio_pct"] = own / regional_bench["wool_kg_per_sheep_goat"] * 100.0
            out["productivity_reference_kind"] = "wool_kg_per_sheep_goat_proxy_denominator"

    observed = [
        entered_heads > 0,
        pasture > 0,
        fodder > 0,
        water > 0,
        energy > 0,
        production > 0,
        degraded_observed,
    ]
    out["input_completeness_pct"] = sum(observed) / len(observed) * 100.0
    out["reference_layers_available"] = sum([
        benchmark.get("latest_district_heads") is not None,
        requirements.get("reference_water_m3_year") is not None,
        requirements.get("reference_feed_dm_t_year") is not None,
        forecast.get("available", False),
        bool(regional_bench),
    ])
    out["reference_layers_max"] = 5
    return out
