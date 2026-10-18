"""Regression: RU/KK/EN exports share localized payload and never invent pump kWh."""
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from pathlib import Path
import sys
import re
import pytest

from core.report_localization import prepare_report
from core.reporting import (build_excel_report, build_pdf_report, build_word_report,
    build_combined_excel_report,build_combined_pdf_report,build_combined_word_report)


def sample(lang):
    return {
        'lang':lang,'mode_label':{'ru':'Оценить мое хозяйство','kk':'Шаруашылықты бағалау','en':'Assess My Farm'}[lang],
        'generated_label':{'ru':'Создан','kk':'Жасалды','en':'Generated'}[lang],
        'brand_translation':'QŪNAR',
        'summary_title':{'ru':'Результаты','kk':'Нәтижелер','en':'Results'}[lang],
        'recommendations_title':{'ru':'Рекомендации','kk':'Ұсыныстар','en':'Recommendations'}[lang],
        'inputs_title':{'ru':'Исходные данные','kk':'Бастапқы деректер','en':'Inputs'}[lang],
        'summary':[
            {'label':'Integrated field water baseline, m3','value':'670000', 'note':'Scenario result; not an observed effect'},
            {'label':'Integrated known operating cost reduction, KZT','value':'100', 'note':'Only known costs'},
        ],
        'inputs':[['Тариф: electricity','41.06','Documented November 2025 non-household tariff, VAT-removed for comparable costing; NOT independently confirmed for October 2026'],
                  ['Integrated pumping parameters','pumped_fraction=0.0%; before=0, after=0 kWh/m3','Editable engineering assumptions, not instrument measurements']],
        'recommendations':[{'title':'QŪNAR','text':'Scenario only', 'evidence_label':'Основание','evidence':'FAO'}],
    }


def xml_text(buf, name_prefix):
    with ZipFile(BytesIO(buf)) as z:
        assert z.testzip() is None
        paths=[name for name in z.namelist() if name.startswith(name_prefix) and name.endswith('.xml')]
        return ' '.join(' '.join(ET.fromstring(z.read(path)).itertext()) for path in paths)


@pytest.mark.parametrize('lang,expected', [('ru','Единый сценарий: подача воды до изменений'),
                                          ('kk','Біріктірілген сценарий: бастапқы су'),
                                          ('en','Integrated scenario: water before')])
def test_every_document_format_localizes_known_legacy_metadata(lang,expected):
    payload=sample(lang)
    word=xml_text(build_word_report(payload),'word/document')
    xlsx=xml_text(build_excel_report(payload),'xl/')
    assert expected in word and expected in xlsx
    pdf=build_pdf_report(payload)
    assert pdf.startswith(b'%PDF-')
    assert len(pdf)>2000
    from pypdf import PdfReader
    txt=' '.join(page.extract_text() or '' for page in PdfReader(BytesIO(pdf)).pages)
    assert expected in re.sub(r'\s+',' ',txt)
    if lang!='en':
        assert 'Integrated field water baseline' not in word
        assert 'Integrated field water baseline' not in xlsx
        assert 'Integrated field water baseline' not in txt
    assert sample(lang)['summary'][0]['label']=='Integrated field water baseline, m3' # no mutation

@pytest.mark.parametrize('lang', ['ru','kk','en'])
def test_combined_reports_preserve_sources(lang):
    p=sample(lang)
    assert build_combined_pdf_report([p,p]).startswith(b'%PDF-')
    assert 'word/document.xml' in ZipFile(BytesIO(build_combined_word_report([p,p]))).namelist()
    assert 'xl/workbook.xml' in ZipFile(BytesIO(build_combined_excel_report([p,p]))).namelist()


def test_archival_pump_intensity_not_used_in_live_scenario_ui():
    src=(Path(__file__).parents[1]/'core'/'scenario_ui.py').read_text()
    assert 'PUMPING_REFERENCE_KWH_PER_M3' not in src
    assert '0.002725 * float(main_pump_head_m)' in src


def test_main_app_does_not_default_unknown_energy_to_archival_pumping():
    src=(Path(__file__).parents[1]/'app.py').read_text()
    assert 'water*float(PUMPING_REFERENCE_KWH_PER_M3)' not in src
    assert 'energy_kwh=energy_reference.value' in src
    assert "_tariff_water_ref = 'custom'" in src
    assert "{'ru':'самотёк'" in src
