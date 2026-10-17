"""NASA POWER polygon sampling for farm-level assessments, not model training.

Meteorological POWER data are nominally 0.5 latitude x 0.625 longitude;
solar data have coarser grids. Intersecting this nominal grid with the field
polygon identifies weighted *sample locations*, not exact native NASA pixel
boundaries. Sampling multiple locations never creates sub-grid information.

NASA POWER official docs: https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/
"""
from dataclasses import dataclass
from math import ceil, floor, isfinite
from typing import Callable
from shapely.geometry import shape, box
from pyproj import Geod

LAT_STEP = 0.5
LON_STEP = 0.625
DEFAULT_MAX_SAMPLES = 512
_GEOD = Geod(ellps="WGS84")
WEIGHTED_FIELDS = (
    "Apr-Sep temperature, °C",
    "Apr-Sep precipitation, mm",
    "Apr-Sep relative humidity, %",
    "Apr-Sep root-zone wetness",
    "Apr-Sep solar radiation, MJ/m²/day",
)


@dataclass(frozen=True)
class PolygonSample:
    latitude: float
    longitude: float
    area_weight: float


def _geodesic_area(geom):
    area, _ = _GEOD.geometry_area_perimeter(geom)
    return abs(float(area))


def polygon_sample_locations(geometry, *, max_samples=DEFAULT_MAX_SAMPLES):
    """Area-weighted points inside intersecting nominal POWER meteo cells.

    Keep every intersecting cell up to a regional safety bound; never truncate.
    The bound protects against accidental global geometries. Coordinates must be GeoJSON lon/lat (EPSG:4326).
    """
    geom = shape(geometry) if isinstance(geometry, dict) else geometry
    if geom.geom_type not in ("Polygon", "MultiPolygon") or geom.is_empty or not geom.is_valid:
        raise ValueError("A valid GeoJSON Polygon or MultiPolygon is required")
    x0, y0, x1, y1 = geom.bounds
    if not all(isfinite(x) for x in (x0,y0,x1,y1)) or not (-90<=y0<y1<=90 and -180<=x0<x1<=180):
        raise ValueError("Expected WGS84 coordinates inside longitude/latitude bounds")
    if max_samples < 1:
        raise ValueError("max_samples must be >= 1")
    # Fail early for accidental continental geometries. Regional polygons are supported.
    nx = ceil(x1 / LON_STEP + 0.5) - floor(x0 / LON_STEP + 0.5)
    ny = ceil(y1 / LAT_STEP + 0.5) - floor(y0 / LAT_STEP + 0.5)
    if nx * ny > max_samples * 60:
        raise ValueError("Polygon too extensive for farm-level POWER sampling")

    raw = []
    for i in range(floor(x0/LON_STEP + 0.5), ceil(x1/LON_STEP + 0.5)):
        for j in range(floor(y0/LAT_STEP + 0.5), ceil(y1/LAT_STEP + 0.5)):
            cell = box((i-0.5)*LON_STEP, (j-0.5)*LAT_STEP,
                       (i+0.5)*LON_STEP, (j+0.5)*LAT_STEP)
            clipped = geom.intersection(cell)
            if clipped.is_empty:
                continue
            a = _geodesic_area(clipped)
            if a <= 0:
                continue
            # Nominal MERRA meteorology sample centres occur on 0.5/0.625-degree
            # increments; external NASA POWER pixels still require live validation.
            # Sampling nominal cell center instead of field centroid makes every
            # field inside one nominal grid cell use the same POWER location.
            lat = j*LAT_STEP
            lon = i*LON_STEP
            raw.append((lat, lon, a))
    if not raw:
        raise ValueError("No positive-area grid intersection")
    if len(raw) > max_samples:
        raise ValueError(f"Polygon intersects {len(raw)} cells; limit is {max_samples}. Split the polygon or raise the explicit safety bound.")
    total = sum(a for _,_,a in raw)
    return tuple(PolygonSample(round(lat,6),round(lon,6),a/total) for lat,lon,a in raw)


def fetch_polygon_growing_season(geometry, year, *, fetch_point: Callable, max_samples=DEFAULT_MAX_SAMPLES):
    """Combine public POWER point measurements; fail instead of partial averaging."""
    points = polygon_sample_locations(geometry,max_samples=max_samples)
    observations = []
    for pt in points:
        row = fetch_point(pt.latitude,pt.longitude,year)
        if any(row.get(field) is None or not isfinite(float(row[field])) for field in WEIGHTED_FIELDS):
            raise ValueError("Incomplete NASA POWER sample, polygon aggregate not calculated")
        observations.append(row)
    starts = {row.get("period_start") for row in observations}
    ends = {row.get("period_end") for row in observations}
    if len(starts)!=1 or len(ends)!=1:
        raise ValueError("NASA POWER point series have different date coverage")
    out = {k: sum(row[k]*pt.area_weight for row,pt in zip(observations,points)) for k in WEIGHTED_FIELDS}
    n_imputed = sum(int(r.get('interpolated_daily_values', 0)) for r in observations)
    out.update({
        "interpolated_daily_values": n_imputed,
        "quality": "NASA POWER nominal-grid polygon aggregate" + ("; includes labelled interpolations" if n_imputed else ""),
        "source": "NASA POWER polygon grid sampling (area-weighted approximate)",
        "year":year,
        "period_start": observations[0].get("period_start"),
        "period_end": observations[0].get("period_end"),
        "partial_season":any(bool(x.get("partial_season", False)) for x in observations),
        "polygon_sample_count":len(points),
        "polygon_sampling_note": "Nominal meteo grid 0.5° x 0.625°, coarser solar grid; not within-field microclimate mapping",
    })
    return out



def fetch_polygon_daily_weather(geometry, *, start, end, fetch_point, max_samples=DEFAULT_MAX_SAMPLES):
    """NASA POWER daily weather at polygon cells; area-weight each day/variable.

    Ensures the six-/eight-variable daily weather arrays are calendar-aligned.
    Never substitutes the district centre when one cell fails.
    """
    from dataclasses import fields
    from core.soil_water_daily import DailyWeather, _daily_validate
    samples=polygon_sample_locations(geometry,max_samples=max_samples)
    series=[fetch_point(s.latitude,s.longitude,start,end) for s in samples]
    if not series or any(len(x)!=len(series[0]) or not x for x in series):
        raise ValueError('Incomplete daily NASA POWER polygon climate')
    attrs=tuple(f.name for f in fields(DailyWeather) if f.name!='day')
    days=[]
    for i in range(len(series[0])):
        d=series[0][i].day
        if any(s[i].day!=d for s in series):
            raise ValueError('Different NASA sample date coverage within the polygon')
        kw={attr:sum(getattr(s[i],attr)*p.area_weight for s,p in zip(series,samples))
            for attr in attrs}
        days.append(_daily_validate(DailyWeather(day=d,**kw)))
    return tuple(days)
