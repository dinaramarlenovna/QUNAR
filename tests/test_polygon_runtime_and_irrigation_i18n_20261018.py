"""Regression for 2026-10-18 shared NameError and untranslated irrigation fields.

Offline syntax/order and UI formatter tests; not a live browser/Streamlit test.
"""
from pathlib import Path
import ast

APP = Path(__file__).resolve().parents[1] / 'app.py'
SOURCE = APP.read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)


def _first_location(needle):
    idx = SOURCE.index(needle)
    return SOURCE[:idx].count('\n') + 1


def test_map_area_declared_at_module_scope_before_report_input():
    # A previous regression used 'if polygon_area' in the report before the
    # variable was first initialized, crashing ALL modes without a map.
    polygon_init = [n for n in TREE.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'polygon_area'
                            for t in n.targets)]
    assert len(polygon_init) == 1
    assert isinstance(polygon_init[0].value, ast.Name)
    assert polygon_init[0].value.id == 'calc_polygon_area'
    assert polygon_init[0].lineno < _first_location('if polygon_area:\n        report_payload')
    assert polygon_init[0].lineno < _first_location('    if polygon_area:\n        comparison_area')


def test_scope_is_selected_before_calculation_and_is_not_overwritten():
    default_scope = [n for n in TREE.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'polygon_scope'
                             for t in n.targets)]
    assert len(default_scope) == 1
    assert isinstance(default_scope[0].value, ast.Constant)
    assert default_scope[0].value.value == 'calculation_plot'
    assert _first_location("key=\"qunar_map_area_scope\"") < _first_location("submitted = st.button(t[\"calculate\"]")
    assert SOURCE.count('qunar_map_area_scope') == 1
    assert default_scope[0].lineno < _first_location('if polygon_area:\n        report_payload')


def _ui_selectbox_formatter(key):
    for node in ast.walk(TREE):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != 'selectbox':
            continue
        key_keywords = [kw.value.value for kw in node.keywords if kw.arg == 'key' and isinstance(kw.value, ast.Constant)]
        if key in key_keywords:
            f = next(kw.value for kw in node.keywords if kw.arg == 'format_func')
            return f
    raise AssertionError(f'No selectbox for {key}')


def test_fao56_method_labels_in_each_language():
    f = _ui_selectbox_formatter('daily_soil_irrigation')
    expr = compile(ast.Expression(f), str(APP), 'eval')
    labels = {
        'ru': ['Бороздовой', 'Дождевальный', 'Капельный'],
        'kk': ['Бороздалы', 'Жаңбырлатып', 'Тамшылатып'],
        'en': ['Furrow', 'Sprinkler', 'Drip'],
    }
    for lang, expected in labels.items():
        fmt = eval(expr, {'lang': lang})
        assert [fmt(k) for k in ['furrow', 'sprinkler', 'drip']] == expected


def test_switch_irrigation_labels_in_each_language():
    node = next(n for n in ast.walk(TREE)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'selectbox' and n.args
                and 'Предлагаемый тип орошения' in ast.unparse(n.args[0]))
    fmt = next(kw.value for kw in node.keywords if kw.arg == 'format_func')
    expr = compile(ast.Expression(fmt), str(APP), 'eval')
    for lang, labels in {
        'ru': ['Бороздовой', 'Дождевальный', 'Капельный', 'Смешанный'],
        'kk': ['Бороздалы', 'Жаңбырлатып', 'Тамшылатып', 'Аралас'],
        'en': ['Furrow', 'Sprinkler', 'Drip', 'Mixed'],
    }.items():
        formatter = eval(expr, {'lang':lang})
        assert [formatter(k) for k in ['furrow','sprinkler','drip','mixed']] == labels


def test_measured_soil_inputs_not_bilingual_or_english_only():
    assert 'Field capacity / Полевая' not in SOURCE
    assert 'Wilting point / Влажность' not in SOURCE
    assert "st.caption(f'FAO AquaCrop scenario" not in SOURCE
    assert "'ru':'Полевая влагоёмкость" in SOURCE
    assert "'kk':'Егістік ылғал сыйымдылығы" in SOURCE
    assert "'en':'Field capacity" in SOURCE
