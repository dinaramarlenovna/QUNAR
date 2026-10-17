"""Indexed expired insurance norms are research-only and fail closed."""
import csv
import pytest
from pathlib import Path
from core.indexed_insurance_norms import (
    historical_norm, missing_years, indexed_historical_insurance_norm, INDICES_PATH
)
from core.production_costs import reference_variable_cost

ZONE = 'VII subtropical desert'

def test_historical_source_exact_match():
    assert historical_norm('cotton', ZONE, 'science_based').nominal_kzt_ha == 26039
    assert historical_norm('rice', ZONE, 'science_based').nominal_kzt_ha == 36762
    assert historical_norm('winter_wheat', ZONE, 'simplified').nominal_kzt_ha == 7822
    assert historical_norm('cotton', 'unknown', 'science_based') is None
    assert historical_norm('wheat', ZONE, 'science_based') is None


def test_verified_partial_index_chain():
    assert missing_years(2017) == []
    x=indexed_historical_insurance_norm('cotton',ZONE,'science_based',target_year=2017)
    assert x.input_price_multiplier == pytest.approx(1.191*1.079)
    assert x.indexed_historical_insurance_norm_kzt_ha == pytest.approx(26039*1.191*1.079)
    assert x.evidence_status == 'research_only_not_current_production_cost'


def test_2025_chain_is_incomplete_no_automatic_estimate():
    assert missing_years(2025)==list(range(2018,2026))
    with pytest.raises(ValueError,match='2018'):
        indexed_historical_insurance_norm('cotton',ZONE,'science_based',target_year=2025)
    # Production-costs module never accepts expired insurance minima as margin defaults.
    assert reference_variable_cost('Cotton',as_of_year=2025,technology='furrow') is None


def test_rejects_wrong_or_duplicate_index(tmp_path):
    p=tmp_path/'idx.csv'
    r=list(csv.DictReader(INDICES_PATH.open(encoding='utf-8')))
    r[-1]['basis']='annual_average_vs_previous_year'
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(r[0]));w.writeheader();w.writerows(r)
    assert missing_years(2017,path=p)==[2017]
    r[-1]['basis']='dec_to_dec'; r.append(dict(r[-1]))
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(r[0]));w.writeheader();w.writerows(r)
    assert missing_years(2017,path=p)==[2017]


def test_rejects_missing_years_and_future():
    with pytest.raises(ValueError): missing_years(2014)
    with pytest.raises(ValueError): missing_years(2101)
    with pytest.raises(ValueError): indexed_historical_insurance_norm('cotton','unknown','science_based',target_year=2017)
