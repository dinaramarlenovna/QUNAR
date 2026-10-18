"""Offline regression: FAO-56 inputs ahead of main submit, SSP comparison stays scenario-only."""
from pathlib import Path
from math import isfinite
from core.fao56_irrigation import MonthlyWeather, evaluate_irrigation_scenario
from core.cmip6_scenarios import load_scenario

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8')


def weather_reference():
    return tuple(MonthlyWeather(
        month=month, tmean_c=23.0, tmax_c=31.0, tmin_c=15.0,
        rh_pct=45.0, wind_m_s=2.0, pressure_kpa=98.0,
        solar_mj_m2_day=20.0, rainfall_mm_month=20.0
    ) for month in range(4, 10))


def test_daily_settings_before_calculate_and_only_output_in_results():
    assert APP.index("_daily_enabled = False") < APP.index('submitted = st.button(t["calculate"]')
    assert APP.index('submitted = st.button(t["calculate"]') < APP.index('st.subheader(t["results"])')
    assert APP.index('st.subheader(t["results"])') < APP.index("'ru':'Итог суточного FAO-56")
    assert APP.count('daily_soil_year') == 1
    assert APP.count("key='daily_soil_run'") == 0


def test_climate_option_available_to_advanced_and_researcher():
    assert 'user_level in ("specialist", "researcher") and mode_key in ("mode1", "mode2")' in APP
    assert "for _ssp_name in ('SSP2-4.5', 'SSP5-8.5')" in APP


def test_both_ssp_share_nasa_baseline_and_only_change_scenario_weather():
    original = weather_reference()
    results = {}
    for scenario in ('SSP2-4.5', 'SSP5-8.5'):
        c = load_scenario(ROOT / 'data' / 'cmip6', scenario)
        result = evaluate_irrigation_scenario(
            original, c, 43.45, kc_monthly=(0.35, 0.75, 1.10, 1.10, 0.75, 0.45),
            effective_rainfall='fao_training', application_efficiency=0.65,
            area_ha=100.0, weather_source='Test NASA historical baseline')
        totals = result['totals']
        assert all(isfinite(v) for v in totals.values())
        assert totals['future_et0_mm'] > totals['baseline_et0_mm']
        assert totals['future_gross_irrigation_m3_ha'] >= 0
        results[scenario] = totals
    assert abs(results['SSP2-4.5']['baseline_et0_mm'] - results['SSP5-8.5']['baseline_et0_mm']) < 1e-7
    assert results['SSP5-8.5']['future_et0_mm'] > results['SSP2-4.5']['future_et0_mm']


def test_current_model_not_retrained_and_historical_daily_not_claimed_as_future():
    assert 'from core.ml import' in APP
    assert '1995–2014' in APP or '1995-2014' in APP
    assert 'Не является прогнозом 2040–2059' in APP
    assert 'not a 2050 weather forecast' in APP
