"""Scientific source guardrails and actual bytes-level PDF/DOCX/XLSX export QA.

No Streamlit browser or live NASA API is claimed from this test.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_evidence_bundle as evidence

from core.fao56_irrigation import MonthlyWeather, evaluate_irrigation_scenario
from core.cmip6_scenarios import load_scenario
from core.reporting import build_excel_report, build_pdf_report, build_word_report


def _power_payload():
    vals = {'T2M':24.0, 'T2M_MAX':33.0, 'T2M_MIN':15.0, 'RH2M':46.,
            'WS2M':2.2, 'PS':98., 'ALLSKY_SFC_SW_DWN':22., 'PRECTOTCORR':.9}
    return {'properties':{'parameter':{k:{f'{y}{m:02d}':v for y in range(1995,2015)
                                  for m in range(4,10)} for k,v in vals.items()}},
            'parameters':{'PS':{'units':'kPa'}, 'PRECTOTCORR':{'units':'mm/day'},
                          'ALLSKY_SFC_SW_DWN':{'units':'MJ/m^2/day'}}}


def test_evidence_without_nasa_has_no_fabricated_water_effect():
    a=evidence.make_report()
    assert a['A3_FAO56']['status']=='blocked_missing_verified_nasa_baseline'
    assert a['A3_NASA_weather_provenance']['status']=='not_attempted'
    assert a['A8_100ha']['stress']['unchanged_baseline_infeasible']
    assert a['CCKP_CMIP6']['SSP5-8.5']['temperature_change_c'] > 2.6
    assert 'НЕ РАССЧИТАН' in evidence.markdown(a)


def test_power_json_runs_both_scenarios_with_explicit_source_caveat(tmp_path):
    path=tmp_path/'nasa-supplied.json'
    path.write_text(json.dumps(_power_payload()))
    a=evidence.make_report(weather_json=path,crop='Corn',sowing_date='2025-04-15')
    assert a['A3_FAO56']['status']=='scenario_calculated'
    assert a['A3_NASA_weather_provenance']['status']=='source_file_parsed'
    assert 'does not authenticate' in a['A3_NASA_weather_provenance']['caveat']
    for x in a['A3_FAO56']['scenario_results'].values():
        assert x['totals']['future_et0_mm']>x['totals']['baseline_et0_mm']
        assert x['totals']['future_gross_irrigation_m3_ha']>0
        assert 'source_file_parsed' in x['evidence']['weather']
        assert len(x['months'])==6


def test_incomplete_or_invalid_power_source_is_rejected(tmp_path):
    payload=_power_payload()
    payload['properties']['parameter']['RH2M']['199904']=-999
    path=tmp_path/'bad.json';path.write_text(json.dumps(payload))
    with pytest.raises(ValueError,match='fill value'):
        evidence.make_report(weather_json=path)


def test_core_weather_not_mislabeled_as_nasa_by_default():
    weather=tuple(MonthlyWeather(m,25,33,17,45,2,98,22,25) for m in range(4,10))
    r=evaluate_irrigation_scenario(weather,load_scenario(ROOT/'data'/'cmip6','SSP2-4.5'),40.75)
    assert 'NOT verified' in r['evidence']['weather']
    assert 'gross_irrigation' not in str(r['totals'])


def test_export_formats_use_real_output_bytes():
    report=evidence.make_report()
    case=report['A8_100ha']
    payload={
        'mode_label':'A8 Scenario — illustrative', 'lang':'en',
        'summary':[
            {'label':'Water delivered, m3', 'value': case['normal']['optimized']['water_field_delivery_m3'],
             'note':'Illustrative A8 irrigation demand, not measured'},
            {'label':'Partial emissions, kg CO2e', 'value': case['normal']['optimized']['partial_ghg_kg_co2e'],
             'note':'Illustrative activities; incomplete GHG inventory'},
        ],
        'inputs':[['Cost evidence','Hypothetical','JSON A8 input assumptions']],
        'table':[
            {'Indicator':'Baseline contribution margin', 'Value': case['normal']['baseline']['contribution_margin_kzt']},
            {'Indicator':'Optimized contribution margin', 'Value': case['normal']['optimized']['contribution_margin_kzt']},
        ],
        'recommendations':[{'title':'Scenario only','text':'No observed savings claimed',
                            'evidence':'Source JSON in evidence package'}],
    }
    xlsx=build_excel_report(payload)
    pdf=build_pdf_report(payload)
    word=build_word_report(payload)
    assert pdf.startswith(b'%PDF-') and len(pdf)>2000
    with ZipFile(BytesIO(xlsx)) as z:
        assert z.testzip() is None
        assert 'xl/workbook.xml' in z.namelist()
    with ZipFile(BytesIO(word)) as z:
        assert z.testzip() is None
        assert 'word/document.xml' in z.namelist()


def test_survey_sensitivity_territorial_comparison_is_reproducible():
    a = evidence.make_report()
    s = a['A7_sensitivity']
    assert s['territories'] == 17
    assert s['same_top1'] == 17
    assert s['same_top3_set'] == 15
    assert set(s['changed_top3_territories']) == {'Zhetysay District', 'Arys City'}
    assert 'not known respondent districts' in s['interpretation'] or 'NOT known respondent districts' in s['interpretation']


def test_cckp_mean_and_anomaly_exports_disagree_so_not_reconciled():
    a=evidence.make_report()
    x=a['CCKP_CMIP6']['SSP2-4.5']
    y=a['CCKP_CMIP6']['SSP5-8.5']
    assert x['projected_mean_minus_historical_mean_mm']==pytest.approx(2.31)
    assert y['projected_mean_minus_historical_mean_mm']==pytest.approx(2.20)
    assert x['mean_minus_anomaly_discrepancy_mm']==pytest.approx(.72)
    assert y['mean_minus_anomaly_discrepancy_mm']==pytest.approx(1.17)
    assert 'do not match' in x['precipitation_aggregation_note']
