
import pandas as pd
import streamlit as st
import json
from math import isfinite
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from .config import DATA_DIR

FEATURES_NUM = ["Sown area, th. ha","Apr-Sep temperature, °C","Apr-Sep precipitation, mm",
                "Apr-Sep root-zone wetness","Apr-Sep solar radiation, MJ/m²/day"]
FEATURES_CAT = ["District","Crop"]
TARGET = "Yield, centners/ha"

@st.cache_data(show_spinner=False)
def training_data():
    df = pd.read_csv(DATA_DIR / "analytical_panel.csv")
    if "Use in analytical core" in df.columns:
        df = df[df["Use in analytical core"].astype(str).str.startswith("Yes")].copy()
    return df[FEATURES_CAT + FEATURES_NUM + [TARGET,"Year"]].dropna(subset=[TARGET])

@st.cache_resource(show_spinner=False)
def load_model():
    # Trained once per Streamlit process, then reused across reruns/sessions.
    # We intentionally train from the packaged data rather than shipping a pickle,
    # avoiding scikit-learn version incompatibilities across deployments.
    df = training_data()
    X, y = df[FEATURES_CAT + FEATURES_NUM], df[TARGET]
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), FEATURES_CAT),
        ("num", StandardScaler(), FEATURES_NUM),
    ])
    pipe = Pipeline([("pre", pre), ("model", RandomForestRegressor(
        n_estimators=350, random_state=42, min_samples_leaf=2, n_jobs=-1
    ))])
    pipe.fit(X, y)
    return pipe

@st.cache_data(show_spinner=False)
def validation_summary():
    metrics_file = DATA_DIR / "scientific_validation.json"
    if metrics_file.exists():
        data = json.loads(metrics_file.read_text(encoding="utf-8"))
        m = data.get("groupkfold_by_year", {})
        ds = data.get("dataset", {})
        if m:
            return {"mae":float(m.get("MAE")), "rmse":float(m.get("RMSE")),
                    "r2":float(m.get("R2")), "n":int(ds.get("N",0)),
                    "cv":"GroupKFold by year, precomputed scientific validation"}
    df = training_data()
    X, y = df[FEATURES_CAT + FEATURES_NUM], df[TARGET]
    groups = df["Year"].astype(str)
    n_splits = min(5, groups.nunique())
    if n_splits < 2:
        return {"mae":None,"r2":None,"n":len(df)}
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), FEATURES_CAT),
        ("num", StandardScaler(), FEATURES_NUM),
    ])
    pipe = Pipeline([("pre", pre), ("model", RandomForestRegressor(
        n_estimators=350, random_state=42, min_samples_leaf=2, n_jobs=-1
    ))])
    pred = cross_val_predict(pipe, X, y, cv=GroupKFold(n_splits=n_splits), groups=groups)
    return {"mae":float(mean_absolute_error(y,pred)),
            "rmse":float(mean_squared_error(y,pred) ** 0.5),
            "r2":float(r2_score(y,pred)), "n":int(len(df)),
            "cv":f"GroupKFold by year, {n_splits} folds"}


@st.cache_data(show_spinner=False)
def validation_for_crop(crop):
    """Return time-blocked validation metrics for the selected crop when available."""
    f = DATA_DIR / "model_metrics_by_crop.csv"
    if f.exists():
        df = pd.read_csv(f)
        row = df[df["Crop"].astype(str).eq(str(crop))]
        if not row.empty:
            r = row.iloc[0]
            return {
                "mae": float(r["MAE"]),
                "rmse": float(r["RMSE"]),
                "r2": float(r["R2"]),
                "n": int(r["N"]),
                "cv": "GroupKFold by year, crop-specific",
            }
    return validation_summary()



@st.cache_data(show_spinner=False)
def spatial_validation_summary():
    f = DATA_DIR / "scientific_validation.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    block = data.get("leave_one_district_out", {})
    overall = block.get("overall", {})
    if not overall:
        return None
    return {
        "mae": overall.get("MAE"),
        "rmse": overall.get("RMSE"),
        "r2": overall.get("R2"),
        "n": overall.get("N"),
        "districts": overall.get("districts"),
        "cv": "Leave-one-district-out spatial transferability stress test",
    }


@st.cache_data(show_spinner=False)
def forward_holdout_for_crop(crop):
    """True forward-time test 2021-2025 of full RF pipeline, fitted only through 2020.

    Returns diagnostic evidence, not the error bound of the current app model,
    which is refitted on all bundled historical years.
    """
    path=DATA_DIR / "forecast_holdout_2021_2025_metrics.csv"
    if not path.exists():
        return None
    df=pd.read_csv(path)
    row=df[df["crop"].astype(str).eq(str(crop))]
    if row.empty:
        return None
    r=row.iloc[0]
    metric={"mae":float(r["MAE"]),"rmse":float(r["RMSE"]),
            "r2":float(r["R2"]),"n":int(r["n"]),
            "train_end":int(r["train_end"]),"test_start":int(r["test_start"]),
            "test_end":int(r["test_end"]),"source":"forward-time test, NOT current farm validation"}
    if (metric['n']<=0 or metric['train_end']>=metric['test_start'] or
        not all(isfinite(metric[k]) for k in ('mae','rmse','r2'))):
        raise ValueError('Invalid forward holdout metrics')
    return metric


@st.cache_data(show_spinner=False)
def prediction_interval_for_crop(crop, coverage=0.90):
    """Return *retrospective* interval evidence, not a guaranteed future interval.

    Preferred: earlier-period calibrated 90% error width and genuinely forward
    tested 2021-2025 coverage. Fallback to old GroupKFold residual calibration
    only with explicit in-sample diagnostic label. Does not modify prediction.
    """
    if abs(float(coverage)-0.90) > 1e-9:
        return None
    forward = DATA_DIR / "forecast_interval_backtest_2021_2025.csv"
    if forward.exists():
        df=pd.read_csv(forward)
        row=df[df["crop"].astype(str).eq(str(crop))]
        if not row.empty:
            r=row.iloc[0]
            width=float(r["calibration_halfwidth_centners_ha"])
            observed=float(r["holdout_coverage"])
            n=int(r["holdout_N"])
            c_n=int(r["calibration_N"])
            if not (isfinite(width) and width>=0 and isfinite(observed)
                    and 0<=observed<=1 and n>0 and c_n>0):
                raise ValueError("Invalid forward interval backtest file")
            return {
                "coverage_target":0.90,
                "half_width_centners_ha":width,
                "empirical_coverage":observed,
                "n":n,
                "calibration_n":c_n,
                "is_forward_backtest":True,
                "method":"2011-2020 prior-window calibration; coverage measured on 2021-2025",
            }
    f=DATA_DIR / "scientific_validation.json"
    if not f.exists():
        return None
    data=json.loads(f.read_text(encoding="utf-8"))
    block=data.get("prediction_intervals_90",{})
    row=(block.get("by_crop",{}) or {}).get(str(crop))
    if not row:
        return None
    return {
        "coverage_target":float(row.get("coverage_target",coverage)),
        "half_width_centners_ha":float(row.get("half_width_centners_ha")),
        "empirical_coverage":float(row.get("empirical_coverage")),
        "n":int(row.get("N",0)),
        "calibration_n":int(row.get("N",0)),
        "is_forward_backtest":False,
        "method":"same-residual grouped-CV calibration; independent temporal coverage unavailable",
    }


@st.cache_data(show_spinner=False)
def _medians():
    return training_data().groupby(["District","Crop"])[FEATURES_NUM].median()

def predict_yield(district, crop, area_ha, climate):
    med = _medians()
    key = (district,crop)
    base = med.loc[key].to_dict() if key in med.index else training_data()[FEATURES_NUM].median().to_dict()
    used = {
        "District":district, "Crop":crop,
        "Sown area, th. ha":float(base["Sown area, th. ha"]),
        "Apr-Sep temperature, °C":float(climate.get("Apr-Sep temperature, °C", base["Apr-Sep temperature, °C"])),
        "Apr-Sep precipitation, mm":float(climate.get("Apr-Sep precipitation, mm", base["Apr-Sep precipitation, mm"])),
        "Apr-Sep root-zone wetness":float(climate.get("Apr-Sep root-zone wetness", base["Apr-Sep root-zone wetness"])),
        "Apr-Sep solar radiation, MJ/m²/day":float(climate.get("Apr-Sep solar radiation, MJ/m²/day", base["Apr-Sep solar radiation, MJ/m²/day"])),
    }
    pred = float(load_model().predict(pd.DataFrame([used]))[0])
    return max(0.0,pred), {**used, "User field area, ha":float(area_ha),
                            "Prediction scope":"district-crop baseline",
                            "Field area used by ML":False}

def rank_crops(district, area_ha, climate, crops):
    rows=[]
    for crop in crops:
        pred,_=predict_yield(district,crop,area_ha,climate)
        rows.append({"Crop":crop,"Predicted yield, centners/ha":pred})
    return pd.DataFrame(rows).sort_values("Predicted yield, centners/ha",ascending=False)
