import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.irrigation_economics import irrigation_comparison
from core.irrigation_report import irrigation_export


def make_comp(gross1=6450, gross2=5160):
    return irrigation_comparison(
        baseline_yield_centners_ha=50,
        price_kzt_t=105000,
        other_variable_cost_kzt_ha=326000,
        baseline_water_m3_ha=gross1,
        proposed_water_m3_ha=gross2,
        baseline_energy_kwh_ha=420,
        proposed_energy_kwh_ha=420,
        water_tariff_kzt_m3=.845,
        electricity_tariff_kzt_kwh=45.9872,
        yield_change_pct=0,
        extra_technology_cost_kzt_ha=15000,
        evidence='0% for test')


def render(available=107000, reuse=0, lang='ru', comp=None):
    return irrigation_export(comp or make_comp(),
        area_ha=20, input_yield_centners_ha=50,
        ml_yield_centners_ha=63.94,
        selling_price_kzt_t=105000,
        other_variable_cost_kzt_ha=326000,
        extra_technology_cost_kzt_ha=15000,
        yield_change_pct=0, evidence='0% test',
        available_water_m3=available, reuse_pct=reuse, lang=lang)


def test_water_cap_deficit_before_and_within_after():
    rows,rec=render()
    d={r['label']:r['value'] for r in rows}
    assert d['Смена полива: потребность исходной технологии, м³ за сезон']=='129,000'
    assert d['Смена полива: потребность новой технологии, м³ за сезон']=='103,200'
    assert d['Водный лимит: исходная технология']=='превышен'
    assert d['Водный лимит: новая технология']=='соблюдён'
    assert 'маржа уменьшается' in rec['text']
    assert rec['evidence_label']=='Основание'
    assert not rec['evidence'].startswith('Основание:')


def test_irrigation_feasible_with_reuse():
    rows,rec=render(reuse=20)
    d={r['label']:r['value'] for r in rows}
    assert d['Смена полива: забор свежей воды исходной технологии, м³']=='103,200'
    assert d['Водный лимит: исходная технология']=='соблюдён'
    assert d['Водный лимит: новая технология']=='соблюдён'


def test_both_not_feasible():
    rows,rec=render(available=50000)
    d={r['label']:r['value'] for r in rows}
    assert d['Водный лимит: новая технология']=='превышен'
    assert 'нельзя рекомендовать' in rec['text']


def test_languages_and_unknown():
    for l in ['ru','kk','en']:
        rows,rec=render(available=0,lang=l)
        assert any('107' not in r['value'] and 'budget not entered' in r['value'] for r in rows) if l=='en' else rec['effect_label']


def test_negative_budget_rejected():
    try:
        render(available=-5)
    except ValueError:
        return
    raise AssertionError('negative budget should be rejected')
