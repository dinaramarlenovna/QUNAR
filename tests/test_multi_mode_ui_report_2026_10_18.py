"""Regression coverage for QA defects reported on 18 Oct 2026."""
from pathlib import Path
from math import nan
import pytest
from core.report_localization import prepare_report

APP = Path(__file__).parents[1] / 'app.py'


def test_energy_source_is_required_even_in_basic():
    source=APP.read_text(encoding='utf-8')
    assert 'selected_energy_sources = st.multiselect(' in source
    assert 'if not selected_energy_sources:' in source
    assert source.index('selected_energy_sources = st.multiselect(') < source.index('if not selected_energy_sources:')


def test_economic_electricity_is_defined_before_all_mode_results():
    source=APP.read_text(encoding='utf-8')
    assert source.index('economic_energy_kwh = (float(observed_energy)') < source.index('elif mode_key == "mode1":')
    assert 'economic_energy_kwh is not None and area_ha > 0' in source
    assert 'if irrigation_compare_enabled and economic_energy_kwh is None:' in source


def test_optional_scenario_is_input_only_and_mode_scoped():
    source=APP.read_text(encoding='utf-8')
    assert source.index('_scenario_inputs_slot = st.container()') < source.index('submitted = st.button(t["calculate"]')
    assert 'mode_key in ("mode1", "mode2", "mode5")' in source
    assert 'with _scenario_inputs_slot:' in source
    assert 'qunar_calculated_mode' in source


def test_no_district_herd_is_used_as_farm_herd():
    source=APP.read_text(encoding='utf-8')
    assert 'use_district_reference_if_missing=False' in source
    assert 'if heads_source == "unknown":' in source


@pytest.mark.parametrize('lang,expected', [('ru','нет данных'),('kk','дерек жоқ'),('en','not available')])
def test_missing_values_not_output_as_nan(lang, expected):
    payload={'lang':lang, 'summary':[{'label':'Water','value':nan}],
             'table':[{'Heads':nan,'Rate':123.456789}],
             'inputs':[['Herd','nan','unavailable: No animals counted']]}
    localized=prepare_report(payload)
    assert localized['summary'][0]['value']==expected
    assert localized['table'][0]['Heads']==expected
    assert localized['table'][0]['Rate']==123.457
    assert localized['inputs'][0][1]==expected


def test_zero_is_kept_as_valid_measurement():
    payload={'lang':'ru','table':[{'Energy':0,'Water':0.0}]}
    r=prepare_report(payload)
    assert r['table'][0]['Energy']==0 and r['table'][0]['Water']==0
