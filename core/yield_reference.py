"""Leakage-safe reference crop yields for QUNAR's economic planning layer.

A district/crop mean for up to the 3 most recent *calendar years* preceding
an assessment year is a descriptive reference, NOT a validated 2026 forecast.
Never combine future observations, other crops or other districts silently.
"""
from dataclasses import dataclass
from pathlib import Path
import csv
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class YieldReference:
    value_c_ha: Optional[float]
    years: tuple
    requested_years: tuple
    source: str
    warning: str


def _parse_finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) and value > 0 else None


def trailing_three_year_yield(csv_file, district: str, crop: str, assessment_year: int):
    """Use official district/crop data prior to assessment_year, with no leakage.

    A missing calendar year stays missing; earlier years are NOT used as a hidden
    replacement. No cross-district fallback. For <3 values the smaller sample
    is shown explicitly, not mislabelled as a 3-year average.
    """
    year = int(assessment_year)
    if year <= 1900:
        raise ValueError('Invalid assessment year')
    requested = tuple(range(year - 3, year))
    observations = {}
    with Path(csv_file).open(newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if (row.get('District') or '').strip() != district or (row.get('Crop') or '').strip() != crop:
                continue
            try:
                row_year = int(row['Year'])
            except (ValueError, TypeError, KeyError):
                continue
            if row_year not in requested:
                continue
            y = _parse_finite(row.get('Yield, centners/ha'))
            if y is None:
                continue
            if row_year in observations:
                raise ValueError(f'Duplicate district-crop observation for {row_year}')
            observations[row_year] = y
    years = tuple(sorted(observations))
    if not years:
        return YieldReference(None, years, requested, 'official historical district-crop series',
                              'No valid yield observations for the three preceding calendar years')
    value = sum(observations[k] for k in years) / len(years)
    if len(years) == 3:
        warning = 'Historical district reference, not observed farm yield or a validated next-year forecast'
    else:
        warning = f'Only {len(years)} of the previous 3 calendar years have valid observations'
    return YieldReference(value, years, requested, 'official historical district-crop series', warning)
