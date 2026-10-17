"""Read the complete regional NASA download; never average a partial cache.

Extract downloader output into data/nasa_power_region, or set
QUNAR_NASA_CACHE_DIR to the directory containing manifest.json. A configured
cache is authoritative: missing cells/years fail visibly rather than changing
location or quietly switching to a district centre.
"""
from __future__ import annotations
import json
import os
from math import floor
from pathlib import Path

SCHEMA = 'qunar-nasa-regional-cache-v1'
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / 'data' / 'nasa_power_region'


def cache_directory():
    configured = os.environ.get('QUNAR_NASA_CACHE_DIR')
    directory = Path(configured).expanduser() if configured else DEFAULT_DIRECTORY
    if configured or directory.exists():
        return directory
    return None


def _cell(directory, latitude, longitude):
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError('Regional NASA cache manifest is missing or invalid') from exc
    if manifest.get('schema') != SCHEMA:
        raise ValueError('Unsupported regional NASA cache schema')
    # Match the same nominal meteo cell used by polygon intersection.
    latitude = floor(float(latitude) / .5 + .5) * .5
    longitude = floor(float(longitude) / .625 + .5) * .625
    for cell in manifest.get('cells', []):
        if (abs(float(cell['latitude']) - float(latitude)) < 1e-6 and
                abs(float(cell['longitude']) - float(longitude)) < 1e-6):
            return cell
    raise ValueError(f'Regional NASA cache does not cover cell {latitude}, {longitude}')


def monthly_payload(latitude, longitude):
    directory = cache_directory()
    if directory is None:
        return None
    cell = _cell(directory, latitude, longitude)
    # Only trusted relative filenames inside the downloaded directory.
    relative = cell.get('monthly_file', f"monthly/{cell['id']}.json")
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError('Invalid cache filename')
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Regional NASA cache monthly file missing/invalid: {cell['id']}") from exc


def daily_payload(latitude, longitude, start, end):
    directory = cache_directory()
    if directory is None:
        return None
    # A deliberately monthly-only package retains live daily API access.
    # Once daily caching exists, incomplete files fail rather than mix sources.
    if not (directory / 'daily').exists():
        return None
    cell = _cell(directory, latitude, longitude)
    combined = {'properties': {'parameter': {}}}
    for year in range(start.year, end.year + 1):
        path = directory / 'daily' / str(cell['id']) / f'{year}.json'
        try:
            payload = json.loads(path.read_text(encoding='utf-8-sig'))
            if str(payload.get('header', {}).get('time_standard', '')).upper() != 'UTC':
                raise ValueError('Daily regional NASA cache requires declared UTC time standard')
            for name, values in payload['properties']['parameter'].items():
                combined['properties']['parameter'].setdefault(name, {}).update(values)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(f'Regional NASA cache missing/invalid daily cell {cell["id"]}, {year}: {exc}') from exc
    return combined
