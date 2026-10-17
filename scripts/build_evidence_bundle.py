"""Build a source-labeled scientific evidence package from QUNAR's current models.

Usage (from project root):
  python scripts/build_evidence_bundle.py --out examples/release_evidence
  python scripts/build_evidence_bundle.py --weather-json official_nasa_power_monthly.json --crop Corn --sowing-date 2025-04-15
  python scripts/build_evidence_bundle.py --fetch-nasa --crop Corn --sowing-date 2025-04-15

No NASA weather data means A3 stays unavailable. Never generate fake climate data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Only data-model functions are evaluated by this CLI; browser widgets are not
# faked or tested. Registry uses cache_data decorator but not Streamlit widgets.
try:
    import streamlit  # noqa: F401
except ImportError:
    from types import ModuleType
    stub = ModuleType('streamlit')
    stub.cache_data = lambda *args, **kwargs: (lambda function: function)
    sys.modules['streamlit'] = stub

from core.a8_reproducible_case import calculate_case, load_case
from core.cmip6_scenarios import load_scenario, cckp_csv_series
from core.fao56_irrigation import (
    _payload_climatology, fetch_nasa_monthly_climatology,
    evaluate_irrigation_scenario,
)
from core.irrigation_evidence import field_efficiency, monthly_kc_from_calendar
from core.survey_weights import survey_proxy_profile

CMIP6 = ROOT / 'data' / 'cmip6'
COORDS = (40.75, 68.49)  # Maktaaral reference district centroid, not sampled farm GPS


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_weather(source_file: Path | None, fetch_nasa: bool):
    if source_file:
        response = json.loads(source_file.read_text(encoding='utf-8-sig'))
        series = _payload_climatology(response, start_year=1995, end_year=2014)
        return series, {'status': 'source_file_parsed', 'source': 'NASA-format payload supplied for verification',
                        'file_name': source_file.name, 'sha256': file_sha(source_file),
                        'coverage': '1995-2014, Apr-Sep', 'reference_position': COORDS,
                        'caveat': 'Schema validation does not authenticate the origin of a supplied JSON file.'}
    if fetch_nasa:
        try:
            series = fetch_nasa_monthly_climatology(*COORDS, start_year=1995, end_year=2014)
        except Exception as exc:
            return None, {'status': 'unavailable', 'source': 'NASA POWER monthly API',
                          'reason': type(exc).__name__ + ': ' + str(exc)[:300],
                          'reference_position': COORDS}
        return series, {'status': 'api_retrieved', 'source': 'NASA POWER monthly point API',
                        'coverage': '1995-2014, Apr-Sep', 'reference_position': COORDS,
                        'scope': 'district-centroid weather, not measured farm polygon'}
    return None, {'status': 'not_attempted', 'reason': 'No NASA weather payload supplied; no online request asked for',
                  'reference_position': COORDS}


def make_report(*, weather_json=None, fetch_nasa=False, crop=None, sowing_date=None):
    case_input = load_case()
    case = calculate_case(case_input)
    scenarios = {name: load_scenario(CMIP6, name).as_dict() for name in ('SSP2-4.5', 'SSP5-8.5')}
    # Check the two CCKP exported quantities independently. Ensemble monthly
    # means minus historical means need not equal the separately supplied Anomaly.
    # Record the discrepancy instead of selecting whichever result looks better.
    for name in scenarios:
        src = load_scenario(CMIP6, name)
        means = cckp_csv_series(CMIP6/'precipitation_mean.csv', name)
        implied = sum(means) - sum(src.baseline_precip_monthly_mm)
        scenarios[name]['projected_mean_minus_historical_mean_mm'] = round(implied, 6)
        scenarios[name]['mean_minus_anomaly_discrepancy_mm'] = round(implied-src.precipitation_change_mm, 6)
        scenarios[name]['precipitation_aggregation_note'] = (
            'Use exported CCKP Anomaly for scenario delta; independently exported mean differences do not match. '
            'Exact ensemble aggregation method must be checked before claiming equivalence.')
    weights = survey_proxy_profile()
    sensitivity_path = ROOT / 'data' / 'survey_weight_sensitivity_17_regions.csv'
    with sensitivity_path.open(encoding='utf-8-sig', newline='') as fd:
        sensitivity_rows = list(csv.DictReader(fd))
    if len(sensitivity_rows) != 17 or len(set(r['Территория'] for r in sensitivity_rows)) != 17:
        raise ValueError('A7 sensitivity table must cover 17 distinct territories')
    sensitivity = {
        'territories':len(sensitivity_rows),
        'same_top1':sum(r['Лидер совпал'] == 'Да' for r in sensitivity_rows),
        'same_top3_set':sum(r['Топ-3 одинаков'] == 'Да' for r in sensitivity_rows),
        'changed_top3_territories':[r['Территория'] for r in sensitivity_rows if r['Топ-3 одинаков'] != 'Да'],
        'source': sensitivity_path.name,
        'interpretation':'Ranking perturbation with survey proxy, NOT farming area allocation, and NOT known respondent districts',
    }
    weather, weather_meta = get_weather(weather_json, fetch_nasa)
    climate_irrigation = {'status': 'blocked_missing_verified_nasa_baseline',
                          'reason': 'FAO-56 ET0 needs NASA historical monthly Tmax,Tmin,Tmean,RH,wind,pressure,solar,precipitation; CMIP6 delta T/P alone is insufficient.'}
    if weather is not None:
        kc = None
        if crop and sowing_date:
            kc = monthly_kc_from_calendar(crop, date.fromisoformat(sowing_date),reference_year=2025)
        elif crop or sowing_date:
            raise ValueError('Crop and sowing date must be supplied together')
        scenarios_water = {}
        for name in scenarios:
            r = evaluate_irrigation_scenario(
                weather, load_scenario(CMIP6, name), COORDS[0],
                kc_monthly=kc,
                effective_rainfall='fao_training' if kc is not None else None,
                application_efficiency=field_efficiency('furrow') if kc is not None else None,
                area_ha=100 if kc is not None else None,
                weather_source=weather_meta['source'] + ', ' + weather_meta['status'],
            )
            scenarios_water[name] = r
        climate_irrigation = {'status': 'scenario_calculated', 'crop':crop,
                              'sowing_date':sowing_date,
                              'kc_status':'FAO reference, illustrative local planting date' if kc else 'not supplied: ET0 only',
                              'field_irrigation_efficiency_reference':0.6 if kc is not None else None,
                              'weather_meta': weather_meta,
                              'scenario_results':scenarios_water,
                              'scope':'Apr-Sep monthly climatology; 2050 anomalies. Not measured farm saving or official water limit'}
    return {
        'project_version':'v0.8.1',
        'description':'Reproducible A1/A3/A4/A7/A8 evidence; all A5 production costs hypothetical',
        'historical_model_unchanged':True,
        'CCKP_CMIP6':scenarios,
        'A7_survey':weights,
        'A7_sensitivity':sensitivity,
        'A8_100ha':case,
        'A3_FAO56':climate_irrigation,
        'A3_NASA_weather_provenance':weather_meta,
        'methods_and_sources':{
            'CCKP':'World Bank CCKP CSV 2040-2059 / 1995-2014, historical former South Kazakhstan administrative area',
            'FAO56':'https://www.fao.org/4/x0490e/x0490e06.htm',
            'NASA':'https://power.larc.nasa.gov/docs/services/api/temporal/monthly/',
            'FAO_Kc':'https://www.fao.org/4/S2022E/s2022e07.htm',
            'Kazakhstan_irrigation_norms':'https://adilet.zan.kz/rus/docs/V2500036253',
            'BNS_prices':'Source spreadsheets and source-cell references in data/producer_prices_turkestan_2022_2025.csv',
            'GHG':'IPCC EF1 reference; illustrative nitrogen, diesel, grid factors in the A8 input JSON',
        },
        'data_file_sha256':{
            'a8_inputs': file_sha(ROOT / 'examples' / 'a8_maktaaral_100ha_inputs.json'),
            'cckp_temp': file_sha(CMIP6 / 'temperature_anomaly.csv'),
            'cckp_precip': file_sha(CMIP6 / 'precipitation_anomaly.csv'),
            'survey_aggregate': file_sha(ROOT / 'data' / 'survey_2026_aggregates.json'),
            'survey_sensitivity':file_sha(sensitivity_path),
        },
        'limitations':[
            'A1: Partial emissions inventory, not measured net climate mitigation or full lifecycle accounting.',
            'A3: No FAO56 field-water estimates without real NASA weather and crop phenology.',
            'A5: A8 production costs and tariffs are research assumptions; no verified regional cost mean.',
            'A8: 100-ha farm, baseline, cap, N/diesel intensities and technology assumptions are hypothetical.',
            'Existing Appendix D 24.7/23.8 million KZT case was not reconstructed by this separate A8 demonstration.',
            'A7: Survey proxy weights are sensitivity tests, not inferred respondent priority weights.',
            'A2: Spatial sampling unit tests cannot confirm real NASA meteorological response.',
            'Browser Streamlit and NASA/WaPOR production integration still require live testing.',
        ],
    }


def markdown(bundle):
    a=bundle['A8_100ha']; n=a['normal']; s=a['stress']; c=bundle['CCKP_CMIP6']; sen=bundle['A7_sensitivity']
    f=lambda x:f'{x:,.2f}'.replace(',',' ')
    lines=[
        '# QŪNAR v0.8.1 — расчётные результаты для Claude',
        '', 'Все значения А8 — условный пример хозяйства, НЕ подтверждённые результаты внедрения.',
        '', '## А4 — исходные региональные аномалии CCKP (апрель–сентябрь)',
        '', '| Сценарий | Потепление, °C | Δ осадков, мм | Δ осадков, % | Дней > 35°C | Дней > 40°C | Дней > 45°C |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for key, v in c.items():
        lines.append(f"| {key} | +{f(v['temperature_change_c'])} | +{f(v['precipitation_change_mm'])} | +{f(v['precipitation_change_pct'])} | {f(v['days_over_35'])} | {f(v['days_over_40'])} | {f(v['days_over_45'])} |")
    lines += [
        '', 'Значения основаны на среднем сезонном потеплении с весами по дням месяца и суммарной аномалии осадков из CCKP `Anomaly`.',
        'Регионы CCKP и нынешняя Туркестанская область могут не совпадать. Эти климатические изменения не гарантируют соответствующее изменение урожая.',
        f"Проверка источника: разность сезонных средних осадков даёт +{f(c['SSP2-4.5']['projected_mean_minus_historical_mean_mm'])} мм и +{f(c['SSP5-8.5']['projected_mean_minus_historical_mean_mm'])} мм, что НЕ совпадает с отдельными рядами CCKP Anomaly (+1,59 и +1,03 мм). До установления причины используем именно Anomaly, не смешиваем два метода.", 
        '', '## А7 — опрос и чувствительность',
        '', '208 респондентов, Q3 вода 120/208, Q7 климатические риски 93/208; только экспериментальный профиль климат 43,66% / вода 56,34%.',
        f"На вычисленной таблице {sen['territories']} территорий: топ-1 совпал в {sen['same_top1']}/{sen['territories']}, состав тройки совпал в {sen['same_top3_set']}/{sen['territories']}; изменение топ-3: {', '.join(sen['changed_top3_territories'])}. Это ранги, не площади посевов и не районы респондентов.",
        '', '## А8, А1 — одинаковая структура и период сравнения (100 га, Мактаарал)',
        '', '| Показатель | Базовая структура | Оптимизированная структура |',
        '|---|---:|---:|',
    ]
    for key, label, divisor in [('water_field_delivery_m3','Вода на поле, м³',1),
                               ('contribution_margin_kzt','Потенциальная маржа, млн тг',1e6),
                               ('partial_ghg_kg_co2e','Частичные выбросы, т CO₂e',1000)]:
        lines.append(f"| {label} | {f(n['baseline'][key]/divisor)} | {f(n['optimized'][key]/divisor)} |")
    lines += [
        '', f"В стандартном случае прирост условной маржи: {f(n['margin_change_same_conditions_kzt']/1e6)} млн тг; вода меняется на {f(n['water_change_same_conditions_m3'])} м³.",
        '', '### Комбинированный стресс (вода −20%, урожайность −10%, расходы +10%)',
        '', f"Лимит воды: {f(s['water_budget_m3'])} м³. Неизменная базовая структура — недопустима: превышение {f(s['baseline_counterfactual_water_shortfall_m3'])} м³.",
        f"Сценарная маржа новой допустимой структуры: {f(s['optimized']['contribution_margin_kzt']/1e6)} млн тг.",
        f"Сценарное снижение частичных выбросов относительно НЕДОПУСТИМОЙ исходной структуры: {f((s['baseline_counterfactual']['partial_ghg_kg_co2e']-s['optimized']['partial_ghg_kg_co2e'])/1000)} т CO₂e.",
        'Нельзя трактовать это сокращение как реализованную выгоду по отношению к действующей допустимой альтернативе.',
        '', '## А3 — изменение потребности в воде при потеплении',
        '', f"Статус: `{bundle['A3_FAO56']['status']}`.",
    ]
    if bundle['A3_FAO56']['status'] == 'scenario_calculated':
        x=bundle['A3_FAO56'];
        lines.append(f"Погода: `{bundle['A3_NASA_weather_provenance']['status']}`; культура: {x.get('crop') or 'не указана'}.")
        for scen, d in x['scenario_results'].items():
            t=d['totals']
            lines.append(f"{scen}: ET₀ {f(t['baseline_et0_mm'])} → {f(t['future_et0_mm'])} мм; " + (f"подача на поле {f(t['baseline_gross_irrigation_m3_ha'])} → {f(t['future_gross_irrigation_m3_ha'])} м³/га" if 'future_gross_irrigation_m3_ha' in t else 'данных Kc/полива недостаточно для м³/га') + '.')
    else:
        lines.append('Показатель в м³/га НЕ РАССЧИТАН: без полной метеосерии NASA и параметров выращивания численное изменение нельзя подтвердить.')
    lines += ['', '## Запреты на интерпретацию',
              '', '- Исходные затраты хозяйства, тарифы, нормы N и дизеля А8 — явные исследовательские допущения.',
              '- Показатели А8 и А3 нельзя представлять как фактически достигнутую экономию или сокращение выбросов.',
              '- Индексированные страховые нормативы 2015 года не заменяют производственную себестоимость 2025 года.',
              '- Историческая модель Random Forest и её показатели не переобучались.',
              '', 'См. полный JSON для проверяемых исходных данных, SHA-256 и отдельных границ учёта.', '']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT/'examples'/'release_evidence')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--weather-json', type=Path, help='Original NASA-format 1995-2014 monthly JSON')
    group.add_argument('--fetch-nasa', action='store_true', help='Attempt live NASA API; leave A3 missing if inaccessible')
    parser.add_argument('--crop', help='One Kc crop, e.g. Corn, Cotton, Potato')
    parser.add_argument('--sowing-date', help='Explicit research scenario YYYY-MM-DD (e.g. 2025-04-15)')
    args=parser.parse_args()
    result=make_report(weather_json=args.weather_json, fetch_nasa=args.fetch_nasa,
                       crop=args.crop, sowing_date=args.sowing_date)
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'EVIDENCE_A1_A3_A4_A7_A8.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.out/'EVIDENCE_FOR_CLAUDE.md').write_text(markdown(result),encoding='utf-8')
    print('Saved',args.out,'A3 status:',result['A3_FAO56']['status'])

if __name__=='__main__':
    main()
