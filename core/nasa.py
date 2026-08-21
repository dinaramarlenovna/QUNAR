
from datetime import date, timedelta
import requests
import numpy as np
import streamlit as st

NASA_ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = ["T2M", "PRECTOTCORR", "RH2M", "GWETROOT", "ALLSKY_SFC_SW_DWN"]

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_growing_season(latitude, longitude, year=None, timeout=20):
    today = date.today()
    year = int(year or today.year)
    start = date(year, 4, 1)
    nominal_end = date(year, 9, 30)

    if year == today.year:
        end = min(nominal_end, today - timedelta(days=1))
    else:
        end = nominal_end

    if end < start:
        raise ValueError("Current date is before the growing-season start.")

    params = {
        "parameters": ",".join(PARAMS),
        "community": "AG",
        "longitude": longitude,
        "latitude": latitude,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": "UTC",
    }
    r = requests.get(NASA_ENDPOINT, params=params, timeout=timeout)
    r.raise_for_status()
    p = r.json()["properties"]["parameter"]

    def vals(name):
        return np.array(
            [v for v in p[name].values() if v is not None and v > -900],
            dtype=float
        )

    t, pr, rh, gw, sr = map(vals, PARAMS)
    if min(map(len, [t, pr, rh, gw, sr])) == 0:
        raise ValueError("NASA POWER returned an incomplete series.")

    return {
        "Apr-Sep temperature, °C": float(t.mean()),
        "Apr-Sep precipitation, mm": float(pr.sum()),
        "Apr-Sep relative humidity, %": float(rh.mean()),
        "Apr-Sep root-zone wetness": float(gw.mean()),
        "Apr-Sep solar radiation, MJ/m²/day": float(sr.mean()),
        "source": "NASA POWER live API",
        "year": year,
        "period_start": str(start),
        "period_end": str(end),
        "partial_season": end < nominal_end,
    }
