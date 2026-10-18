"""Cross-format export and scientific-claims safety regression."""
from pathlib import Path
from math import nan
import io
import zipfile
import pytest
from core.reporting import (
    build_excel_report, build_pdf_report, build_word_report,
    build_combined_excel_report, build_combined_pdf_report, build_combined_word_report,
)
from core.report_localization import prepare_report

ROOT=Path(__file__).parents[1]

@pytest.mark.parametrize("lang,missing", [("ru","нет данных"),("kk","дерек жоқ"),("en","not available")])
def test_report_core_cleans_nan_everywhere(lang,missing):
    inp = dict(lang=lang, mode_label="Test", brand_translation="", generated_at="2026-10-18",
       summary=[{'label':'Herd','value':nan}],
       table=[{'Livestock Units':nan,'Zero, verified':0.0}],
       inputs=[['Herd',nan,'unavailable: No animals counted']],
       recommendations=[{'title':'Nutrient','text':'No animals counted'}],
       analysis=['No animals counted'])
    p=prepare_report(inp)
    assert p['summary'][0]['value']==missing
    assert p['inputs'][0][1]==missing
    assert p['table'][0]['Livestock Units']==missing
    assert p['table'][0]['Zero, verified']==0.0
    assert build_pdf_report(inp).startswith(b'%PDF')
    assert build_word_report(inp).startswith(b'PK')
    assert build_excel_report(inp).startswith(b'PK')
    assert build_combined_pdf_report([inp]).startswith(b'%PDF')
    assert build_combined_word_report([inp]).startswith(b'PK')
    assert build_combined_excel_report([inp]).startswith(b'PK')
    # XLSX string table and Word XML should use localized missing value, never literal nan.
    for bytes_ in (build_excel_report(inp),build_word_report(inp),build_combined_excel_report([inp]),build_combined_word_report([inp])):
        with zipfile.ZipFile(io.BytesIO(bytes_)) as z:
            content=' '.join(z.read(n).decode('utf-8','ignore') for n in z.namelist() if n.endswith('.xml'))
        assert missing in content
        assert '>nan<' not in content.lower()


def test_mode2_has_no_inherited_field_intervention():
    s=(ROOT/'app.py').read_text('utf-8')
    assert 'mode_key in ("mode1", "mode5")' in s
    assert 'mode_key in ("mode1", "mode2", "mode5")' not in s
    assert 'qunar_integrated_optin_{mode_key}' in s


def test_missing_herd_is_not_declared_zero():
    s=(ROOT/'app.py').read_text('utf-8')
    assert 'if heads_source == "unknown":' in s
    assert 'livestock.get("heads") if heads_source != "unknown" else None' in s
    assert 'не указано' in s


def test_unverified_margin_not_claimed():
    s=(ROOT/'app.py').read_text('utf-8')
    assert 'Экономический эффект не определён: данные о марже культур отсутствуют' in s
