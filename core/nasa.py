"""NASA POWER growing-season retrieval with strict daily alignment and provenance.

Observed April--September climate, not a native 10-ha grid.  A single missing
internal day may be linearly interpolated, if *both* adjacent days exist;
missing boundary days or longer gaps invalidate the season.  Precipitation
interpolation is explicitly labelled an estimate, not an observation.
"""
from datetime import date, timedelta
from math import isfinite
import requests
import streamlit as st

NASA_ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = ["T2M", "PRECTOTCORR", "RH2M", "GWETROOT", "ALLSKY_SFC_SW_DWN"]
FIELDS = ("Apr-Sep temperature, °C", "Apr-Sep precipitation, mm",
          "Apr-Sep relative humidity, %", "Apr-Sep root-zone wetness",
          "Apr-Sep solar radiation, MJ/m²/day")


def _parse_growing_season(payload, start, end, *, allow_single_day_interpolation=True):
    """Daily dates must align for all parameters; missing != zero."""
    try:
        parameters = payload["properties"]["parameter"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed NASA POWER JSON response") from exc
    if any(name not in parameters or not isinstance(parameters[name], dict) for name in PARAMS):
        raise ValueError("NASA POWER missing required climate parameter")
    if end < start:
        raise ValueError("Invalid seasonal date range")
    sequence = []
    day = start
    while day <= end:
        sequence.append(day.strftime('%Y%m%d'))
        day += timedelta(days=1)
    values = {name: [] for name in PARAMS}
    interpolations = []
    for param in PARAMS:
        raw = parameters[param]
        for key in sequence:
            try:
                value = float(raw.get(key))
            except (ValueError, TypeError):
                value = float('nan')
            values[param].append(value if isfinite(value) and value > -900 else None)
        missing = [i for i, val in enumerate(values[param]) if val is None]
        for index in missing:
            if (not allow_single_day_interpolation or index == 0 or index == len(sequence)-1
                or values[param][index-1] is None or values[param][index+1] is None):
                raise ValueError(f"NASA POWER has non-interpolable gap: {param} {sequence[index]}")
            values[param][index] = (values[param][index-1] + values[param][index+1])/2
            interpolations.append(f"{param} {sequence[index]}")
    t, rain, rh, root, solar = (values[p] for p in PARAMS)
    if not all(-65 <= x <= 65 for x in t): raise ValueError('Out-of-range air temperature')
    if not all(0 <= x <= 2000 for x in rain): raise ValueError('Invalid daily precipitation')
    if not all(0 <= x <= 100 for x in rh): raise ValueError('Invalid relative humidity')
    if not all(0 <= x <= 1 for x in root): raise ValueError('Invalid NASA root-zone wetness')
    if not all(0 <= x <= 50 for x in solar): raise ValueError('Invalid shortwave radiation')
    return {
        FIELDS[0]: sum(t)/len(t), FIELDS[1]: sum(rain),
        FIELDS[2]: sum(rh)/len(rh), FIELDS[3]: sum(root)/len(root),
        FIELDS[4]: sum(solar)/len(solar),
        'source':'NASA POWER Daily API', 'period_start':str(start),'period_end':str(end),
        'daily_observation_count':len(sequence),
        'interpolated_daily_values':len(interpolations),
        'imputation_log':interpolations,
        'quality':'observed/modelled NASA grid values' if not interpolations else
            'NASA grid values with limited one-day temporal interpolation (estimated)',
    }


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_growing_season(latitude, longitude, year=None, timeout=30):
    today=date.today(); year=int(year or today.year)
    if not -90 <= float(latitude) <= 90 or not -180 <= float(longitude) <= 180:
        raise ValueError('Coordinates are not valid WGS84 degrees')
    start=date(year,4,1); nominal_end=date(year,9,30)
    end=min(nominal_end,today-timedelta(days=1)) if year==today.year else nominal_end
    if year>today.year or end<start:
        raise ValueError('Future NASA observations do not exist; use historical climatology')
    request={'parameters':','.join(PARAMS),'community':'AG',
             'longitude':longitude,'latitude':latitude,
             'start':start.strftime('%Y%m%d'),'end':end.strftime('%Y%m%d'),
             'format':'JSON','time-standard':'UTC'}
    from .regional_climate_cache import daily_payload
    cached = daily_payload(latitude, longitude, start, end)
    if cached is not None:
        parsed = _parse_growing_season(cached, start, end)
        parsed.update({'year':year,'partial_season':end<nominal_end,
                       'source':'NASA POWER Daily API; regional offline cache'})
        return parsed
    result=requests.get(NASA_ENDPOINT,params=request,timeout=timeout)
    result.raise_for_status()
    parsed=_parse_growing_season(result.json(),start,end)
    parsed.update({'year':year,'partial_season':end<nominal_end})
    return parsed
