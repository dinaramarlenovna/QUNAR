
import pandas as pd
import streamlit as st
from .config import DATA_DIR

@st.cache_data(show_spinner=False)
def load_panel():
    return pd.read_csv(DATA_DIR / "analytical_panel.csv")

@st.cache_data(show_spinner=False)
def load_centroids():
    # Exact NASA POWER point coordinates used to build the analytical climate panel.
    # Do not replace with generic district-center defaults.
    import json
    raw=json.loads((DATA_DIR / "district_centroids.json").read_text(encoding="utf-8"))
    return {k:(float(v[0]),float(v[1])) for k,v in raw.items()}

@st.cache_data(show_spinner=False)
def load_district_climate_fallback():
    return pd.read_csv(DATA_DIR / "district_climate_fallback.csv")

@st.cache_data(show_spinner=False)
def load_district_crop_context():
    return pd.read_csv(DATA_DIR / "district_crop_context.csv")

def district_climate(district):
    f = load_district_climate_fallback()
    row = f[f["District"] == district]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {
        "Apr-Sep temperature, °C": float(r["Apr-Sep temperature, °C"]),
        "Apr-Sep precipitation, mm": float(r["Apr-Sep precipitation, mm"]),
        "Apr-Sep root-zone wetness": float(r["Apr-Sep root-zone wetness"]),
        "Apr-Sep solar radiation, MJ/m²/day": float(r["Apr-Sep solar radiation, MJ/m²/day"]),
    }

def district_crop_context(district, crop):
    c = load_district_crop_context()
    row = c[(c["District"] == district) & (c["Crop"] == crop)]
    return None if row.empty else row.iloc[0].to_dict()
