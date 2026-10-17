"""Auditable historical insurance-norm *illustration*, NOT crop production cost.

Never feed results of this module to QUNAR contribution-margin defaults:
- 2015 basis is an EXPIRED crop-insurance norm for a historical climatic zone;
- index is national prices of input purchases, not crop/region-specific costs;
- indexation never corrects technology, input quantity or coverage changes;
- water and purchased electricity may overlap the historical cost boundary.

For research audit only, exact crop/zone/technology match and uninterrupted,
comparable official indices are required. Missing inputs abort the estimate.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import csv
import math

ROOT = Path(__file__).resolve().parents[1]
NORMS_PATH = ROOT / 'data' / 'historical_insurance_norms_2015.csv'
INDICES_PATH = ROOT / 'data' / 'agricultural_input_price_indices_verified.csv'


@dataclass(frozen=True)
class HistoricalNorm:
    crop: str
    zone: str
    technology: str
    nominal_kzt_ha: float
    source_url: str


@dataclass(frozen=True)
class IndexedInsuranceIllustration:
    base_year: int
    target_year: int
    crop: str
    zone: str
    technology: str
    historical_insurance_norm_kzt_ha: float
    input_price_multiplier: float
    indexed_historical_insurance_norm_kzt_ha: float
    evidence_status: str = 'research_only_not_current_production_cost'


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not Path(path).is_file():
        return []
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def historical_norm(crop: str, zone: str, technology: str, *,
                    path: Path = NORMS_PATH) -> HistoricalNorm | None:
    if not all((crop, zone, technology)):
        return None
    match = [r for r in _read_rows(path)
             if r.get('base_year') == '2015'
             and r.get('historic_territory') == 'South Kazakhstan Region'
             and r.get('irrigation') == 'irrigated'
             and r.get('evidence_type') == 'expired_insurance_norm'
             and (r.get('crop'),r.get('climate_zone'),r.get('technology')) == (crop,zone,technology)
             and r.get('source_url', '').startswith('https://adilet.zan.kz/')]
    if len(match) != 1:
        return None
    value = float(match[0]['insurance_norm_kzt_ha'])
    if not (math.isfinite(value) and value > 0):
        return None
    return HistoricalNorm(crop,zone,technology,value,match[0]['source_url'])


def missing_years(target_year: int, *, base_year: int = 2015,
                  path: Path = INDICES_PATH) -> list[int]:
    """Detect missing years; returns all years if a noncomparable duplicate exists."""
    target_year = int(target_year)
    if not 2015 <= base_year <= target_year <= 2100:
        raise ValueError('Invalid base year or target year')
    entries = {}
    for r in _read_rows(path):
        try:
            y=int(r['year'])
        except (ValueError,KeyError):
            continue
        entries.setdefault(y,[]).append(r)
    missing=[]
    for y in range(base_year+1,target_year+1):
        rr=entries.get(y,[])
        if len(rr)!=1:
            missing.append(y)
            continue
        r=rr[0]
        try:
            v=float(r['index_percent'])
        except (ValueError,KeyError):
            missing.append(y)
            continue
        if (not (math.isfinite(v) and v > 0)
            or r.get('index_label') != 'agricultural_input_purchase_index'
            or r.get('territory') != 'Kazakhstan'
            or r.get('basis') != 'dec_to_dec'
            or r.get('verification') != 'verified'
            or not r.get('source_url', '').startswith('https://stat.gov.kz/')
            or not r.get('source_location')):
            missing.append(y)
    return missing


def indexed_historical_insurance_norm(
    crop: str, zone: str, technology: str, *, target_year: int,
    norms_path: Path = NORMS_PATH, indices_path: Path = INDICES_PATH,
) -> IndexedInsuranceIllustration:
    """Compute price-updated INSURANCE NORM for an audit, never as farm cost.

    Raises ValueError rather than generating misleading 2025 estimates when
    part of the source index history is absent or noncomparable.
    """
    record=historical_norm(crop, zone, technology, path=norms_path)
    if record is None:
        raise ValueError('Historical insurance norm for exact crop/zone/technology unavailable')
    bad=missing_years(target_year, base_year=2015, path=indices_path)
    if bad:
        raise ValueError('Missing or noncomparable index years: '+', '.join(map(str,bad)))
    rows={int(r['year']): r for r in _read_rows(indices_path)}
    mult=math.prod(float(rows[year]['index_percent'])/100.0
                   for year in range(2016,int(target_year)+1))
    return IndexedInsuranceIllustration(
        2015,int(target_year),crop,zone,technology,
        record.nominal_kzt_ha,mult,record.nominal_kzt_ha*mult)
