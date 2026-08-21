
import pandas as pd
import streamlit as st
import json
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
        n_estimators=250, random_state=42, min_samples_leaf=2, n_jobs=-1
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
