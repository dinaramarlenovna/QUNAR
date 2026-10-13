import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.irrigation_report import irrigation_export
from core.irrigation_economics import irrigation_comparison


def scenario():
    return irrigation_comparison(
        baseline_yield_centners_ha=50, price_kzt_t=105000,
        other_variable_cost_kzt_ha=326000,
        baseline_water_m3_ha=5350, proposed_water_m3_ha=4280,
        baseline_energy_kwh_ha=420, proposed_energy_kwh_ha=420,
        water_tariff_kzt_m3=0.845, electricity_tariff_kzt_kwh=45.9872,
        yield_change_pct=0, extra_technology_cost_kzt_ha=15000,
        evidence='Контрольный сценарий: 0% эффект урожайности')


def test_reference_scenario():
    comp=scenario()
    assert round(comp['baseline_margin_kzt_ha']) == 175165
    assert round(comp['proposed_margin_kzt_ha']) == 161069
    assert round(comp['margin_change_kzt_ha']) == -14096
    assert round(comp['stress_margin_change_kzt_ha']) == -15505
    for lang in ('ru','kk','en'):
        rows,rec=irrigation_export(comp,area_ha=20,input_yield_centners_ha=50,
            ml_yield_centners_ha=38.5,selling_price_kzt_t=105000,
            other_variable_cost_kzt_ha=326000,extra_technology_cost_kzt_ha=15000,
            yield_change_pct=0,evidence='Контрольный сценарий',lang=lang)
        values={r['label']:r['value'] for r in rows}
        assert len(rows)>=19
        assert '21,400' in values.values()
        assert '-281,917' in values.values(),values
        assert '-310,109' in values.values(),values
        assert rec['text']
    rurows,rurec=irrigation_export(comp,area_ha=20,input_yield_centners_ha=50,
        ml_yield_centners_ha=38.5,selling_price_kzt_t=105000,
        other_variable_cost_kzt_ha=326000,extra_technology_cost_kzt_ha=15000,
        yield_change_pct=0,evidence='Контрольный сценарий',lang='ru')
    assert 'Не рекомендовать' in rurec['text']
    assert '50.00' in str(rurows)
    assert '38.50' in str(rurows)


def test_positive_switch_statement():
    c=scenario()
    c['margin_change_kzt_ha']=500
    _,rec=irrigation_export(c,area_ha=20,input_yield_centners_ha=50,
        ml_yield_centners_ha=None,selling_price_kzt_t=105000,
        other_variable_cost_kzt_ha=326000,extra_technology_cost_kzt_ha=0,
        yield_change_pct=0,evidence='Assumption',lang='ru')
    assert 'маржу' in rec['text'] and 'увелич' in rec['text']


def test_area_validation():
    try:
        irrigation_export(scenario(),area_ha=0,input_yield_centners_ha=50,
        ml_yield_centners_ha=None,selling_price_kzt_t=105000,
        other_variable_cost_kzt_ha=326000,extra_technology_cost_kzt_ha=0,
        yield_change_pct=0,evidence='Assumption',lang='ru')
    except ValueError:
        return
    raise AssertionError('zero area must fail')
