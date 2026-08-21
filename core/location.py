
from __future__ import annotations
import requests
import streamlit as st

DISTRICT_ALIASES = {
    "сауран": "Sauran District",
    "sauran": "Sauran District",
    "сарыағаш": "Saryagash District",
    "сарыагаш": "Saryagash District",
    "saryagash": "Saryagash District",
    "келес": "Keles District",
    "keles": "Keles District",
    "жетісай": "Zhetysay District",
    "жетысай": "Zhetysay District",
    "zhetysay": "Zhetysay District",
    "мақтаарал": "Maktaaral District",
    "мактаарал": "Maktaaral District",
    "maktaaral": "Maktaaral District",
    "шардара": "Shardara District",
    "shardara": "Shardara District",
    "отырар": "Otyrar District",
    "otyrar": "Otyrar District",
    "ордабасы": "Ordabasy District",
    "ordabasy": "Ordabasy District",
    "сайрам": "Sairam District",
    "sairam": "Sairam District",
    "қазығұрт": "Kazygurt District",
    "казыгурт": "Kazygurt District",
    "kazygurt": "Kazygurt District",
    "төлеби": "Tolebi District",
    "толеби": "Tolebi District",
    "tolebi": "Tolebi District",
    "түлкібас": "Tulkibas District",
    "тюлькубас": "Tulkibas District",
    "tulkibas": "Tulkibas District",
    "бәйдібек": "Baydibek District",
    "байдибек": "Baydibek District",
    "baydibek": "Baydibek District",
    "созақ": "Suzak District",
    "сузак": "Suzak District",
    "suzak": "Suzak District",
    "түркістан": "Turkestan City",
    "туркестан": "Turkestan City",
    "turkistan": "Turkestan City",
    "арыс": "Arys City",
    "arys": "Arys City",
    "кентау": "Kentau City",
    "kentau": "Kentau City",
}

@st.cache_data(ttl=86400, show_spinner=False)
def reverse_geocode(lat: float, lon: float):
    """
    Provisional navigation-only reverse geocoding via OpenStreetMap Nominatim.
    Never used as an authoritative scientific administrative-boundary source.
    """
    headers = {"User-Agent": "QUNAR-research-prototype/0.2.3"}
    r = requests.get(
        "https://nominatim.openstreetmap.org/reverse",
        params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 10, "addressdetails": 1},
        headers=headers, timeout=12
    )
    r.raise_for_status()
    data = r.json()
    address = data.get("address", {})
    candidates = [
        address.get("district"), address.get("county"), address.get("state_district"),
        address.get("city"), address.get("town"), address.get("municipality"),
        data.get("display_name")
    ]
    text = " | ".join([x for x in candidates if x]).lower()
    matched = None
    for alias, code in DISTRICT_ALIASES.items():
        if alias in text:
            matched = code
            break
    return {
        "matched_district": matched,
        "display_name": data.get("display_name"),
        "raw_address": address,
        "source": "OpenStreetMap Nominatim (navigation-only)",
    }

def browser_geolocation():
    """
    Returns browser GPS coordinates when streamlit-geolocation is installed.
    """
    try:
        from streamlit_geolocation import streamlit_geolocation
    except Exception:
        return None, "missing_component"
    try:
        loc = streamlit_geolocation()
        if not loc:
            return None, None
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if lat is None or lon is None:
            return None, None
        return {
            "latitude": float(lat),
            "longitude": float(lon),
            "accuracy_m": loc.get("accuracy"),
            "altitude_m": loc.get("altitude"),
        }, None
    except Exception as e:
        return None, str(e)
