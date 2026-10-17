"""Auditable other-variable-cost references and farm itemised budgets (KZT/ha).

Water and purchased electricity are ALWAYS excluded from this field; QUNAR
adds those resource charges separately. An empty catalogue is intentional:
there is no verified, current crop-level Turkestan reference cost in the
sources examined. Never infer production costs from farm-gate prices,
insurance minima, CPI, yields, or the wrong crop category.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_COST_TABLE = Path(__file__).resolve().parents[1] / 'data' / 'crop_variable_cost_references.csv'
COST_FIELDS = ('seeds', 'fertilizer', 'crop_protection', 'diesel', 'labor', 'other')
ACCEPTED_TIERS = frozenset({'verified_regional_observation', 'documented_technology_budget'})


@dataclass(frozen=True)
class CostReference:
    crop_code: str
    year: int
    other_variable_cost_kzt_ha: float
    territory: str
    technology: str
    evidence_tier: str
    source_title: str
    source_url: str
    source_location: str
    as_of_year: int

    @property
    def years_old(self) -> int:
        return self.as_of_year - self.year

    @property
    def source_label(self) -> str:
        return (f'{self.source_title}, {self.year}; {self.source_location}; '
                f'{self.source_url}. {self.evidence_tier}. Other variable '
                f'costs excl. water/electricity; scenario reference, not farm observation.')


def itemized_variable_cost(*, entries: Mapping[str, float | None]) -> float | None:
    """Sum user-supplied KZT/ha inputs. Unknown components cannot be zeroed.

    A zero component is allowed only when the caller explicitly provides 0.
    All items must be known, finite and nonnegative. No water/electricity item.
    """
    if set(entries) != set(COST_FIELDS):
        return None
    values = []
    for k in COST_FIELDS:
        value = entries[k]
        if value is None:
            return None
        v = float(value)
        if not math.isfinite(v) or v < 0:
            raise ValueError(f'Invalid cost component: {k}')
        values.append(v)
    if not any(values):
        return None
    return sum(values)


def reference_variable_cost(crop_code: str, *, as_of_year: int,
                            technology: str = 'unspecified',
                            table_path: Path = DEFAULT_COST_TABLE) -> CostReference | None:
    """Read ONLY evidence-qualified, specific and comparable source costs.

    Dates never exceed as_of_year. No national-to-regional or broad crop
    substitutions; unspecified technology is not silently applied to drip.
    Malformed source rows are ignored, not made into automatic defaults.
    """
    if not Path(table_path).is_file():
        return None
    as_of_year = int(as_of_year)
    candidates = []
    with Path(table_path).open(encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            try:
                if (row['crop_code'] != crop_code
                    or row['territory'] != 'Turkestan Region'
                    or row['technology'] != technology
                    or row['evidence_tier'] not in ACCEPTED_TIERS
                    or row['water_electricity_excluded'].strip().lower() != 'true'
                    or row['unit'] != 'KZT/ha'
                    or row['status'] != 'published'):
                    continue
                year = int(row['year'])
                value = float(row['other_variable_cost_kzt_ha'])
                if not (1900 <= year <= as_of_year and math.isfinite(value) and value > 0):
                    continue
                if not (row['source_title'].strip() and row['source_url'].strip()
                        and row['source_location'].strip()):
                    continue
                candidates.append(CostReference(
                    crop_code=crop_code, year=year,
                    other_variable_cost_kzt_ha=value,
                    territory=row['territory'], technology=technology,
                    evidence_tier=row['evidence_tier'],
                    source_title=row['source_title'],
                    source_url=row['source_url'],
                    source_location=row['source_location'], as_of_year=as_of_year))
            except (KeyError, ValueError, AttributeError):
                continue
    return max(candidates, key=lambda x: x.year) if candidates else None
