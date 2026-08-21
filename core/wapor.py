
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import calendar
import re
from typing import Iterable, Optional

import numpy as np
import requests

WAPOR_BASE = "https://data.apps.fao.org/gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets"

# Official WaPOR v3 Level-1 actual evapotranspiration/interception, dekadal.
# Raw COG values use the 0.1 scale documented for the WaPOR v3 AETI band.
AETI_MAPSET = "L1-AETI-D"
AETI_SCALE = 0.1

class WaPORError(RuntimeError):
    pass

def _collect_items(url: str, timeout: int = 30):
    """Follow the FAO API pagination links and return all items."""
    data = {"links": [{"rel": "next", "href": url}]}
    out = []
    while "next" in [x.get("rel") for x in data.get("links", [])]:
        next_url = [x["href"] for x in data["links"] if x.get("rel") == "next"][0]
        r = requests.get(next_url, timeout=timeout)
        r.raise_for_status()
        payload = r.json()
        data = payload["response"]
        out.extend(data.get("items", []))
    return out

def available_rasters(mapset_code: str = AETI_MAPSET, timeout: int = 30):
    url = f"{WAPOR_BASE}/{mapset_code}/rasters"
    items = _collect_items(url, timeout=timeout)
    return [
        {
            "code": x.get("code"),
            "downloadUrl": x.get("downloadUrl"),
            "caption": x.get("caption"),
        }
        for x in items
        if x.get("code") and x.get("downloadUrl")
    ]

_CODE_RE = re.compile(r"\.(\d{4})-(\d{2})-D([123])$")

def parse_dekad(code: str):
    m = _CODE_RE.search(code)
    if not m:
        return None
    y, month, dekad = map(int, m.groups())
    return y, month, dekad

def dekad_days(year: int, month: int, dekad: int) -> int:
    if dekad in (1, 2):
        return 10
    return calendar.monthrange(year, month)[1] - 20

def dekad_start_end(year: int, month: int, dekad: int):
    if dekad == 1:
        return date(year, month, 1), date(year, month, 10)
    if dekad == 2:
        return date(year, month, 11), date(year, month, 20)
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 21), date(year, month, last)

def filter_rasters(rasters, start: date, end: date):
    selected = []
    for item in rasters:
        p = parse_dekad(item["code"])
        if not p:
            continue
        y, m, d = p
        ds, de = dekad_start_end(y, m, d)
        # retain dekads overlapping the requested interval
        if de >= start and ds <= end:
            selected.append({**item, "year": y, "month": m, "dekad": d, "start": ds, "end": de})
    return sorted(selected, key=lambda x: (x["year"], x["month"], x["dekad"]))

def _geometry_stats_from_cog(url: str, geometry_geojson: dict, scale_factor: float = AETI_SCALE):
    """
    Read only the remote COG windows that intersect the field polygon.
    rasterio/GDAL uses HTTP range requests, so the whole global raster is not downloaded.
    """
    try:
        import rasterio
        from rasterio.mask import mask
        from rasterio.warp import transform_geom
    except ImportError as e:
        raise WaPORError("WAPOR_DEPENDENCY_MISSING") from e

    try:
        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
        ):
            with rasterio.open(url) as src:
                geom = transform_geom("EPSG:4326", src.crs, geometry_geojson, precision=7)
                arr, _ = mask(src, [geom], crop=True, filled=False, indexes=1)
                values = arr.compressed().astype("float64")
                if values.size == 0:
                    raise WaPORError("WaPOR raster does not contain valid pixels for the selected field.")
                values *= scale_factor
                return {
                    "mean": float(np.mean(values)),
                    "median": float(np.median(values)),
                    "p10": float(np.quantile(values, 0.10)),
                    "p90": float(np.quantile(values, 0.90)),
                    "pixels": int(values.size),
                }
    except WaPORError:
        raise
    except Exception as e:
        raise WaPORError(f"Unable to read WaPOR COG for the selected field: {e}") from e

def _point_stats_from_cog(url: str, latitude: float, longitude: float, scale_factor: float = AETI_SCALE):
    try:
        import rasterio
        from rasterio.warp import transform
    except ImportError as e:
        raise WaPORError("WAPOR_DEPENDENCY_MISSING") from e

    try:
        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
        ):
            with rasterio.open(url) as src:
                xs, ys = transform("EPSG:4326", src.crs, [longitude], [latitude])
                value = next(src.sample([(xs[0], ys[0])]))[0]
                if src.nodata is not None and value == src.nodata:
                    raise WaPORError("WaPOR returned nodata for the selected point.")
                return float(value) * scale_factor
    except WaPORError:
        raise
    except Exception as e:
        raise WaPORError(f"Unable to sample WaPOR at the selected point: {e}") from e

def seasonal_aeti(
    start: date,
    end: date,
    *,
    geometry_geojson: Optional[dict] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    mapset_code: str = AETI_MAPSET,
    timeout: int = 30,
):
    """
    Return WaPOR actual evapotranspiration + interception accumulated over the requested period.

    The dekadal AETI layer is an average daily rate for each dekad.
    Seasonal mm = sum(mean daily mm/day × number of overlapping days in each dekad).

    If a polygon is supplied, the mean over all intersecting pixels is used.
    If no polygon is supplied, the selected point is sampled.
    """
    if geometry_geojson is None and (latitude is None or longitude is None):
        raise ValueError("Provide either field geometry or latitude/longitude.")

    rasters = filter_rasters(available_rasters(mapset_code, timeout=timeout), start, end)
    if not rasters:
        raise WaPORError("No WaPOR rasters are available for the requested period.")

    rows = []
    total_mm = 0.0
    spatial_p10 = []
    spatial_p90 = []

    for item in rasters:
        overlap_start = max(start, item["start"])
        overlap_end = min(end, item["end"])
        overlap_days = (overlap_end - overlap_start).days + 1
        if overlap_days <= 0:
            continue

        if geometry_geojson is not None:
            s = _geometry_stats_from_cog(item["downloadUrl"], geometry_geojson)
            daily_mm = s["mean"]
            spatial_p10.append(s["p10"])
            spatial_p90.append(s["p90"])
            pixels = s["pixels"]
        else:
            daily_mm = _point_stats_from_cog(
                item["downloadUrl"], float(latitude), float(longitude)
            )
            pixels = 1

        dekad_mm = daily_mm * overlap_days
        total_mm += dekad_mm
        rows.append({
            "raster": item["code"],
            "start": str(overlap_start),
            "end": str(overlap_end),
            "days": overlap_days,
            "mean_daily_aeti_mm": daily_mm,
            "period_aeti_mm": dekad_mm,
            "pixels": pixels,
        })

    if not rows:
        raise WaPORError("WaPOR returned no usable observations for the requested period.")

    return {
        "aeti_mm": float(total_mm),
        "period_start": str(start),
        "period_end": str(end),
        "dekads_used": len(rows),
        "spatial_p10_daily_mm": float(np.mean(spatial_p10)) if spatial_p10 else None,
        "spatial_p90_daily_mm": float(np.mean(spatial_p90)) if spatial_p90 else None,
        "source": "FAO WaPOR v3 L1-AETI-D",
        "details": rows,
    }

def consumptive_water_metrics(aeti_mm: float, area_ha: float, predicted_yield_centners_ha: float | None = None):
    """
    1 mm over 1 ha = 10 m³.
    This is crop/landscape consumptive water use represented by AETI,
    NOT irrigation withdrawal from a canal or well.
    """
    m3_per_ha = float(aeti_mm) * 10.0
    total_m3 = m3_per_ha * float(area_ha)
    out = {
        "aeti_mm": float(aeti_mm),
        "consumptive_water_m3_per_ha": m3_per_ha,
        "consumptive_water_total_m3": total_m3,
    }
    if predicted_yield_centners_ha is not None and aeti_mm > 0:
        # 1 centner = 100 kg
        yield_kg_ha = float(predicted_yield_centners_ha) * 100.0
        out["modelled_water_productivity_kg_m3"] = yield_kg_ha / m3_per_ha
    return out
