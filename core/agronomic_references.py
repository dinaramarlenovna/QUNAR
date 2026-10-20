"""Source-audited agronomic *reference* activities for optional scenarios.

Published documents never prove the user's farm inputs. Unknown is None, never 0.
No 2004 or 2010 nominal KZT cost is re-labelled as a 2025 production cost.
"""
from __future__ import annotations
from pathlib import Path
from csv import DictReader
from dataclasses import dataclass
from typing import Optional

TABLE = Path(__file__).resolve().parents[1] / 'data' / 'agronomic_reference_evidence.csv'

@dataclass(frozen=True)
class AgronomicEvidence:
    crop: str
    metric: str
    low: float
    high: float
    unit: str
    year: int
    geography: str
    source_title: str
    source_url: str
    source_location: str
    evidence_level: str
    conditions: str

    @property
    def midpoint(self):
        return (self.low + self.high) / 2

    @property
    def citation(self):
        return f'{self.source_title}, {self.year}, {self.source_location}: {self.source_url}. {self.conditions}'

def crop_references(crop: str, metric: str, *, as_of_year: int = 2026):
    matches = []
    if not TABLE.is_file():
        return matches
    with TABLE.open(encoding='utf-8-sig', newline='') as handle:
        for row in DictReader(handle):
            if row['crop_code'] != crop or row['metric'] != metric:
                continue
            year = int(row['year'])
            if year > int(as_of_year):
                continue
            matches.append(AgronomicEvidence(crop, metric, float(row['low']),
                float(row['high']), row['unit'], year, row['geography'],
                row['source_title'], row['source_url'], row['source_location'],
                row['evidence_level'], row['conditions']))
    return sorted(matches, key=lambda x: (x.evidence_level == 'kazakhstan_condition_specific', x.year), reverse=True)

def suggest_diesel_l_per_ha(crop: str, *, density_kg_l: Optional[float] = None):
    """Return an *optional* reference only with explicit density input."""
    refs = crop_references(crop, 'diesel_kg_ha')
    if not refs or density_kg_l is None:
        return None
    if not 0.8 <= density_kg_l <= 0.9:
        raise ValueError('Check diesel density in kg/L')
    ref = refs[0]
    return ref.midpoint / density_kg_l, ref

def evidence_note(e: AgronomicEvidence):
    return (f'{e.low:g}–{e.high:g} {e.unit}, {e.year}, {e.geography}; '
            f'{e.evidence_level}; {e.conditions}; {e.source_url}')
