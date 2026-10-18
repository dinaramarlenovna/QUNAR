from pathlib import Path

SRC=Path(__file__).resolve().parents[1].joinpath('app.py').read_text(encoding='utf-8')

def test_distinct_crop_area_and_optimization_area():
    assert 'Общая площадь посевов для оптимизации, га' in SRC
    assert "'qunar_saved_area_'+mode_key" in SRC
    assert 'qunar_crop_saved_area' in SRC

def test_all_downloads_are_pdf_word_excel():
    expected="('pdf', 'PDF', _cached_pdf_report"
    assert expected in SRC
    assert SRC.index("('pdf', 'PDF', _cached_pdf_report") < SRC.index("('word', 'Word', _cached_word_report") < SRC.index("('xlsx', 'Excel', _cached_excel_report")
    assert SRC.index("('pdf', 'PDF', _cached_combined_pdf") < SRC.index("('word', 'Word', _cached_combined_word") < SRC.index("('xlsx', 'Excel', _cached_combined_excel")

def test_livestock_annual_production_unit_changes_with_type():
    assert "livestock_production_kind == 'thousand_eggs'" in SRC or 'livestock_production_kind == "thousand_eggs"' in SRC
    assert 'Годовой объём продукции, тыс. шт.' in SRC
    assert 'Годовой объём продукции, т' in SRC

def test_select_and_delete_independently_with_ui():
    assert 'qunar_report_include_' in SRC
    assert 'qunar_report_delete_' in SRC
    assert 'selected_reports(basket, include)' in SRC
    assert 'add_report(basket, report_payload)' in SRC

def test_scroll_buttons_and_floating_report_shortcut():
    for anchor in ['qunar-page-top','qunar-report-workspace','qunar-page-bottom']:
        assert '#'+anchor in SRC and 'id=\\"'+anchor+'\\"' not in SRC or anchor in SRC
    assert 'position:fixed' in SRC
    assert 'qunar-go-top' in SRC and 'qunar-go-bottom' in SRC

def test_fractional_entry_uses_general_float_format():
    assert 'kwargs.setdefault("format", "%.12g")' in SRC
