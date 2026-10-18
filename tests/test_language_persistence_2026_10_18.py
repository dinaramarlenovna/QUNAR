"""Offline regression tests for sidebar language/mode selection and actionable error text.

These tests execute only the independent language-selection snippet and inspect
widget defaults; they do NOT represent a live Streamlit/AppTest run.
"""
from pathlib import Path

APP = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')


class MockSidebar:
    def __init__(self, state):
        self.state = state
        self.labels = []
    def markdown(self, label):
        self.labels.append(label)
    def selectbox(self, label, options, **kwargs):
        self.labels.append(label)
        key = kwargs['key']
        if key not in self.state:
            self.state[key] = list(options)[0]
        return self.state[key]


class MockStreamlit:
    def __init__(self):
        self.session_state = {}
        self.sidebar = MockSidebar(self.session_state)


def language_step(fake):
    # Execute exactly the sidebar initialization block without importing the app.
    start = APP.index('# Keep the language selector identity stable across reruns.')
    stop = APP.index('if st.session_state.get("ga_last_language") != lang:', start)
    scope = {'st': fake, 'LANGUAGES': {'Қазақша':'kk','Русский':'ru','English':'en'}}
    exec(compile(APP[start:stop], '<lang-widget>', 'exec'), scope)
    return scope


def test_switch_language_then_mode_preserves_language():
    st = MockStreamlit()
    initial = language_step(st)
    assert initial['lang'] == 'kk'
    st.session_state['qunar_language_selector'] = 'Русский'
    second = language_step(st)
    assert second['lang'] == 'ru'
    # User changes a different widget (mode), which forces full Streamlit rerun.
    st.session_state['qunar_mode_widget'] = 'mode4'
    third = language_step(st)
    assert third['lang'] == 'ru'
    st.session_state['qunar_language_selector'] = 'English'
    fourth = language_step(st)
    assert fourth['lang'] == 'en'
    st.session_state['qunar_user_level_widget'] = 'researcher'
    fifth = language_step(st)
    assert fifth['lang'] == 'en'
    # No changing language widget label: its internal identity remains identical.
    assert {x for x in st.sidebar.labels if 'QUNAR language selector' in x} == {
        'QUNAR language selector - stable internal label'
    }
    assert '**Язык интерфейса**' in st.sidebar.labels
    assert '**Interface language**' in st.sidebar.labels


def test_saved_sidebar_positions_do_not_depend_on_translations():
    fake = MockStreamlit()
    ns = language_step(fake)
    saved_index, remember = ns['_sidebar_saved_index'], ns['_remember_sidebar']
    choices = ['farmer', 'specialist', 'researcher']
    assert saved_index('user_level', choices, 'farmer') == 0
    remember('user_level', 'specialist')
    assert saved_index('user_level', choices, 'farmer') == 1
    remember('mode', 'mode5')
    assert saved_index('mode', ['mode1','mode2','mode3','mode4','mode5'], 'mode1') == 4
    remember('district','Sauran')
    assert saved_index('district', ['Sauran','Maktaaral'], 'Sauran') == 0
    remember('season','completed')
    assert saved_index('season', ['next','current','completed'], 'next') == 2
    for key in ('qunar_user_level_widget','qunar_mode_widget','qunar_district_widget','qunar_season_widget'):
        assert f"key='{key}'" in APP


def test_error_in_all_languages_points_to_required_field_and_position():
    for label in ('Источники энергии и выполнения работ (обязательно)',
                  'Энергия және жұмыс орындалуының көздері (міндетті)',
                  'Operational energy/work sources (required)'):
        assert label in APP
    for snippet in ('прямо над «FAO-56» и кнопкой «Рассчитать»',
                    '«FAO-56» мен «Есептеу» батырмасының үстінде',
                    'immediately above FAO-56 and the Calculate button'):
        assert snippet in APP


def test_code_compiles_and_does_not_change_core_model():
    compile(APP, '<app>', 'exec')
    assert 'from core.ml import predict_yield, rank_crops' in APP


def test_energy_source_codes_are_shadowed_across_translations():
    assert "_remembered_sources = [code for code in st.session_state.get('qunar_saved_operational_energy_sources', [])" in APP
    assert "default=_remembered_sources" in APP
    assert "st.session_state['qunar_saved_operational_energy_sources'] = list(selected_energy_sources)" in APP
