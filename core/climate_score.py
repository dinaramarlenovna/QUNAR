from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import math
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PANEL = DATA_DIR / "analytical_panel.csv"

CLIMATE_VARS = [
    "Apr-Sep temperature, °C",
    "Apr-Sep precipitation, mm",
    "Apr-Sep root-zone wetness",
    "Apr-Sep solar radiation, MJ/m²/day",
]

@lru_cache(maxsize=1)
def _panel() -> pd.DataFrame:
    df = pd.read_csv(PANEL)
    needed = ["Crop", "District", "Yield, centners/ha", *CLIMATE_VARS]
    return df[needed].dropna(subset=["Crop", "Yield, centners/ha"]).copy()


def _robust_scale(s: pd.Series) -> float:
    q25, q75 = s.quantile([0.25, 0.75])
    iqr = float(q75 - q25)
    if iqr > 1e-9:
        return iqr / 1.349
    sd = float(s.std(ddof=0))
    return sd if sd > 1e-9 else 1.0


def empirical_climate_score(district: str, crop: str, climate: dict | None) -> dict:
    """Yield-conditioned climate similarity for crops supported by the historical panel.

    The reference climate envelope is estimated from the better-performing half of
    historical crop observations. Current NASA/district climate is scored by robust
    distance from that empirical envelope. This is a comparative suitability signal,
    not a causal crop-response function.
    """
    climate = climate or {}
    df = _panel()
    crop_df = df[df["Crop"].astype(str).eq(str(crop))].dropna(subset=CLIMATE_VARS)
    if len(crop_df) < 20:
        return {"score": None, "method": "insufficient_panel", "n": int(len(crop_df))}

    # Prefer district-crop history when enough observations exist; otherwise crop-wide history.
    district_df = crop_df[crop_df["District"].astype(str).eq(str(district))]
    ref_df = district_df if len(district_df) >= 8 else crop_df

    yield_cut = float(ref_df["Yield, centners/ha"].median())
    good = ref_df[ref_df["Yield, centners/ha"] >= yield_cut].copy()
    if len(good) < 5:
        good = ref_df.copy()

    z2 = []
    used = {}
    for var in CLIMATE_VARS:
        if var not in climate or climate.get(var) is None:
            continue
        center = float(good[var].median())
        scale = _robust_scale(good[var])
        val = float(climate[var])
        z = (val - center) / scale
        # Winsorise extreme leverage; preserves ordering while avoiding a single variable collapse.
        z = float(np.clip(z, -4.0, 4.0))
        z2.append(z * z)
        used[var] = {"value": val, "reference_median": center, "robust_scale": scale, "z": z}

    if len(z2) < 3:
        return {"score": None, "method": "insufficient_live_climate", "n": int(len(ref_df)), "used": used}

    distance = math.sqrt(float(np.mean(z2)))

    # Convert distance to an empirical percentile rather than an arbitrary mathematical scale.
    # Historical observations closer to the high-yield climate envelope are treated as more suitable.
    hist_distances = []
    for _, row in ref_df.dropna(subset=list(used.keys())).iterrows():
        hz2 = []
        for var, meta in used.items():
            z = (float(row[var]) - meta["reference_median"]) / meta["robust_scale"]
            z = float(np.clip(z, -4.0, 4.0))
            hz2.append(z*z)
        if hz2:
            hist_distances.append(math.sqrt(float(np.mean(hz2))))
    if hist_distances:
        # Survival percentile: share of comparable historical climates at least as distant.
        score = 100.0 * float(np.mean(np.asarray(hist_distances) >= distance))
    else:
        score = 50.0
    return {
        "score": float(np.clip(score, 0.0, 100.0)),
        "distance": distance,
        "method": "yield_conditioned_empirical_envelope",
        "n": int(len(ref_df)),
        "high_yield_n": int(len(good)),
        "used": used,
    }
