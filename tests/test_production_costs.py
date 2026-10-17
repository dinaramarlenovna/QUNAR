import csv
from pathlib import Path
import pytest

from core.production_costs import (
    COST_FIELDS, DEFAULT_COST_TABLE, itemized_variable_cost, reference_variable_cost
)


def sample(**updates):
    x = dict(year='2025', crop_code='Cotton', territory='Turkestan Region',
             technology='furrow', other_variable_cost_kzt_ha='170000', unit='KZT/ha',
             water_electricity_excluded='true', evidence_tier='documented_technology_budget',
             status='published', source_title='Verifiable example (test only)',
             source_url='https://example.org/test', source_location='Table A')
    x.update(updates)
    return x


def catalog(tmp_path, *rows):
    p = tmp_path / 'catalog.csv'
    with p.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(sample()))
        writer.writeheader(); writer.writerows(rows)
    return p


def test_no_unverified_default():
    assert reference_variable_cost('Cotton', as_of_year=2025, technology='furrow') is None
    assert DEFAULT_COST_TABLE.exists()


def test_valid_documented_reference(tmp_path):
    p = catalog(tmp_path, sample(), sample(year='2024', other_variable_cost_kzt_ha='130000'))
    out = reference_variable_cost('Cotton', as_of_year=2026, technology='furrow', table_path=p)
    assert (out.year, out.other_variable_cost_kzt_ha) == (2025, 170000)
    assert 'water/electricity' in out.source_label


def test_no_future_leakage(tmp_path):
    p = catalog(tmp_path, sample(year='2025'), sample(year='2024', other_variable_cost_kzt_ha='130000'))
    assert reference_variable_cost('Cotton', as_of_year=2024, technology='furrow', table_path=p).year == 2024
    assert reference_variable_cost('Cotton', as_of_year=2023, technology='furrow', table_path=p) is None


@pytest.mark.parametrize('update', [
    {'water_electricity_excluded':'false'}, {'territory':'Kazakhstan'},
    {'status':'confidential'}, {'evidence_tier':'outdated_insurance_norm'},
    {'source_url':''}, {'other_variable_cost_kzt_ha':'0'},
    {'unit':'KZT/t'}, {'technology':'drip'},
])
def test_excludes_incompatible_source(tmp_path,update):
    p = catalog(tmp_path, sample(**update))
    assert reference_variable_cost('Cotton', as_of_year=2026, technology='furrow', table_path=p) is None


def test_cost_items_all_known():
    v = {k: float(i*1000) for i,k in enumerate(COST_FIELDS,1)}
    assert itemized_variable_cost(entries=v) == 21000
    v['labor'] = None
    assert itemized_variable_cost(entries=v) is None


def test_missing_items_not_assumed_zero():
    assert itemized_variable_cost(entries={'seeds': 5000}) is None
    assert itemized_variable_cost(entries=dict.fromkeys(COST_FIELDS, 0.0)) is None


def test_invalid_costs():
    v=dict.fromkeys(COST_FIELDS,0.0);v['labor']=-1
    with pytest.raises(ValueError):itemized_variable_cost(entries=v)
    v['labor']=float('nan')
    with pytest.raises(ValueError):itemized_variable_cost(entries=v)
