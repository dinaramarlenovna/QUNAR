"""Rebuild independent QUNAR A4/A6/A7/A8 audit from bundled input tables.

Run from the project root:
  python scripts/audit_remarks_batch_2026_10_17.py
No online requests, imputed observations, re-training, or baseline changes.
"""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.cmip6_scenarios import load_scenario, cckp_csv_series, MONTHS
from core.survey_weights import survey_proxy_profile, audit_survey_aggregates
from core.forecast_reliability import evaluate_forecast_support
# Numerical functions use @streamlit.cache_data for the app. On headless audit
# machines without Streamlit, replace ONLY that decorator with a no-op.
try:
    import streamlit  # noqa: F401
except ImportError:
    from types import ModuleType
    stub=ModuleType('streamlit')
    stub.cache_data=lambda *a, **kw: (lambda fn: fn)
    sys.modules['streamlit']=stub
from core.a8_reproducible_case import load_case, calculate_case


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as fh:
        return list(csv.DictReader(fh))


def audit_cmip():
    root=ROOT/'data/cmip6'; results=[]
    for ssp in ('SSP2-4.5','SSP5-8.5'):
        data=load_scenario(root,ssp)
        projections=cckp_csv_series(root/'precipitation_mean.csv',ssp)
        implied=[a-b for a,b in zip(projections,data.baseline_precip_monthly_mm)]
        differences=[a-b for a,b in zip(implied,data.precipitation_change_monthly_mm)]
        if any(p<0 for p in projections):
            raise ValueError('Projected precipitation climatology cannot be negative')
        results.append({'scenario':ssp,'delta_temperature_c':round(data.temperature_change_c,4),
            'exported_precip_anomaly_mm':round(data.precipitation_change_mm,4),
            'exported_precip_anomaly_pct_of_baseline':round(data.precipitation_change_pct,4),
            'implied_difference_of_climatology_mm':round(sum(implied),4),
            'discrepancy_mm':round(sum(differences),4),
            'monthly_comparison':[{'month':m,'exported_anomaly_mm':a,'climatology_difference_mm':round(b,4),
                                   'difference_mm':round(b-a,4)} for m,a,b in zip(MONTHS,data.precipitation_change_monthly_mm,implied)],
            'projected_days_gt35':sum(data.days_over_35_monthly),
            'projected_days_gt40':sum(data.days_over_40_monthly),
            'projected_days_gt45':sum(data.days_over_45_monthly),
            'validity':'The exported anomaly is the scenario input. Difference-of-climatologies is only a cross-check; do not interchange or sum them.'})
    return {'models':results,'geographical_limit':'CCKP source label Yujno-kazachstanskaya; correspondence to current 17-district Turkestan boundary not independently established.',
            'source':'https://climateknowledgeportal.worldbank.org/index.php/metadata',
            'raw_file_sha256':{f.name:sha(f) for f in root.glob('*.csv')}}


def audit_survey():
    verified=audit_survey_aggregates()
    profile=survey_proxy_profile()
    rows=csv_rows(ROOT/'data/survey_weight_sensitivity_17_regions.csv')
    territories=[r['Территория'] for r in rows]
    if len(rows)!=17 or len(set(territories))!=17:
        raise ValueError('Expected exactly 17 distinct administrative territories')
    if any(r['Лидер совпал'] not in {'Да','Нет'} or r['Топ-3 одинаков'] not in {'Да','Нет'} for r in rows):
        raise ValueError('Invalid yes/no code in sensitivity output')
    return {'question_arithmetic':verified,'respondents':profile['respondents'],
            'survey_profile':{'climate_weight':profile['climate'],'water_weight':profile['water'],
                              'numerators':{'water_Q3':profile['water_mentions'],'climate_Q7':profile['climate_mentions']}},
            'baseline_profile':{'climate_weight':.6,'water_weight':.4},
            'district_comparison':{'territories':len(rows),
               'top1_unchanged':sum(r['Лидер совпал']=='Да' for r in rows),
               'top3_sets_unchanged':sum(r['Топ-3 одинаков']=='Да' for r in rows),
               'changed_top3_territories':[r['Территория'] for r in rows if r['Топ-3 одинаков']!='Да']},
            'limitation':'Exploratory cross-question frequency ratio; not respondent-level AHP, population preference estimate, or district-wise sample distribution.'}


def audit_ml():
    root=ROOT/'data'
    croprows=csv_rows(root/'model_metrics_by_crop.csv')
    districtrows=csv_rows(root/'model_metrics_leave_one_district_out.csv')
    schemes=csv_rows(root/'model_metrics.csv')
    cropnames=[r['Crop'] for r in croprows]; districts=[r['District'] for r in districtrows]
    if len(cropnames)!=len(set(cropnames)) or len(districts)!=len(set(districts)):
        raise ValueError('Duplicate crop or district rows in validation tables')
    matrix=[]
    for district in districts:
        for crop in cropnames:
            ev=evaluate_forecast_support(root,district,crop)
            matrix.append({'district':district,'crop':crop,'warning':ev.low_confidence,'reasons':list(ev.reasons)})
    byscheme={r['scheme']:r for r in schemes}
    comparisons=[]
    for rf_name,baseline_name in (
            ('GroupKFold-by-year RF','GroupKFold median baseline'),
            ('Expanding RF train 2004-2010 test 2011-2015','Expanding median baseline train 2004-2010 test 2011-2015'),
            ('Expanding RF train 2004-2015 test 2016-2020','Expanding median baseline train 2004-2015 test 2016-2020'),
            ('Expanding RF train 2004-2020 test 2021-2025','Expanding median baseline train 2004-2020 test 2021-2025'),
            ('10-year stress RF train 2004-2013 test 2014-2023','10-year stress median baseline train 2004-2013 test 2014-2023')):
        rf=byscheme[rf_name]; base=byscheme[baseline_name]
        comparisons.append({'test':rf_name,'reference':baseline_name,
             'rf_MAE':round(float(rf['MAE']),4),'baseline_MAE':round(float(base['MAE']),4),
             'rf_MAE_lower':float(rf['MAE'])<float(base['MAE']),
             'rf_RMSE':round(float(rf['RMSE']),4),'baseline_RMSE':round(float(base['RMSE']),4),
             'rf_RMSE_lower':float(rf['RMSE'])<float(base['RMSE'])})
    return {'crop_r2_below_0_5':[{'crop':r['Crop'],'n':int(r['N']),'R2':round(float(r['R2']),4)} for r in croprows if float(r['R2'])<.5],
            'district_n_below_20':[{'district':r['District'],'n':int(r['N']),'R2':round(float(r['R2']),4)} for r in districtrows if int(r['N'])<20],
            'district_r2_below_0_5':[r['District'] for r in districtrows if float(r['R2'])<.5],
            'district_crop_pairs_checked':len(matrix),'cautioned_pairs':sum(x['warning'] for x in matrix),
            'district_crop_cautions':matrix,
            'baseline_comparisons':comparisons,
            'limitation':'Validation metrics cover historical groups, not independent observed farm outcomes or a promise of forecast precision; R² threshold is a reporting rule.'}


def audit_a8():
    data=calculate_case(load_case())
    normal=data['normal']; stress=data['stress']
    b=normal['baseline']; a=normal['optimized']; bs=stress['baseline_counterfactual']; ss=stress['optimized']
    if not (b['water_feasible'] and a['water_feasible'] and not bs['water_feasible'] and ss['water_feasible']):
        raise ValueError('A8 feasible/infeasible structure assumptions changed')
    return {'input_sha256':data['input_sha256'],
      'normal':{'margin_change_kzt':round(a['contribution_margin_kzt']-b['contribution_margin_kzt'],2),
                'field_water_change_m3':round(a['water_field_delivery_m3']-b['water_field_delivery_m3'],2),
                'partial_ghg_change_kgco2e':round(a['partial_ghg_kg_co2e']-b['partial_ghg_kg_co2e'],2)},
      'stress':{'water_budget_m3':stress['water_budget_m3'],
                 'baseline_feasible':False, 'optimized_feasible':True,
                 'optimized_margin_kzt':round(ss['contribution_margin_kzt'],2),
                 'water_shortfall_in_infeasible_baseline_m3':stress['baseline_counterfactual_water_shortfall_m3']},
      'source_type':'Example using BNS references plus hypothetical costs, activity and budget; NOT actual farm efficiency observed or implementation impact.',
      'implementation_act_note':'An implementation certificate does not supply a before-after measured effect; do not label a counterfactual as realized impact.'}


def build(out=ROOT/'examples/release_evidence'):
    out=Path(out); out.mkdir(parents=True, exist_ok=True)
    audit={'model_version':'v0.8.1','subject':'Batch A4/A6/A7/A8 consistency audit',
           'CMIP6':audit_cmip(),'survey':audit_survey(),'validation':audit_ml(),'farm_scenario':audit_a8()}
    jsonpath=out/'BATCH_A4_A6_A7_A8_AUDIT_2026-10-17.json'
    jsonpath.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    c=audit['CMIP6']['models']; s=audit['survey']; ml=audit['validation']; a=audit['farm_scenario']
    lines=['# QŪNAR v0.8.1 - сводный аудит замечаний A4/A6/A7/A8','',
           '**Основа:** расчёты из поставляемых CSV/JSON, без переобучения ML и новых наблюдений.','','## A4. CMIP6: климатические аномалии и жара','',
           '| Сценарий | ΔT, °C | Аномалия P, мм | Разность климатологий P, мм | Несовпадение, мм | >35°C, дней | >40°C, дней | >45°C, дней |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for x in c: lines.append(f"| {x['scenario']} | {x['delta_temperature_c']:.3f} | {x['exported_precip_anomaly_mm']:.2f} | {x['implied_difference_of_climatology_mm']:.2f} | {x['discrepancy_mm']:.2f} | {x['projected_days_gt35']:.2f} | {x['projected_days_gt40']:.2f} | {x['projected_days_gt45']:.2f} |")
    lines+=['','Используем именно исходный продукт **Anomaly**, а не разность двух других агрегатов; разность приведена только для контроля. Аномалия по моделям и разность медиан ансамбля математически не обязаны совпадать. Историческое соответствие территории «Yujno-kazachstanskaya» нынешним границам не подтверждено. Число жарких дней относится к CMIP6, не к суточным наблюдениям NASA.',
            'Источник: https://climateknowledgeportal.worldbank.org/index.php/metadata','',
            '## A7. Опрос 208 респондентов и веса','',
            f"Проверено {s['question_arithmetic']['questions_checked']} вопросов. Вода (Q3): 120 упоминаний, климатические риски (Q7): 93. Исследовательский профиль: климат {s['survey_profile']['climate_weight']:.4f}; вода {s['survey_profile']['water_weight']:.4f}. Базовый профиль: 0,60/0,40.",
            f"Рейтинг культур: лидер совпал на {s['district_comparison']['top1_unchanged']} из 17 территорий, топ-3 совпал на {s['district_comparison']['top3_sets_unchanged']} из 17.",
            'Это **проверка чувствительности**; вопросы Q3 и Q7 разные, попарная матрица AHP по этим частотам не восстанавливается. По агрегатам нельзя восстановить районные ответы или доказать репрезентативность.','','## A6. Проверка качества ML','',
            f"Проверено {ml['district_crop_pairs_checked']} сочетаний 17 территорий и 6 культур; предупреждение выводится для {ml['cautioned_pairs']} сочетаний.",
            f"R² < 0,5 у {len(ml['crop_r2_below_0_5'])} из 6 культур: "+', '.join(x['crop'] for x in ml['crop_r2_below_0_5'])+'.',
            'Малочисленные районы (N < 20): '+', '.join(x['district']+' (N='+str(x['n'])+')' for x in ml['district_n_below_20'])+'.','','| Схема | MAE RF | MAE медианы | RF лучше по MAE? | RMSE RF | RMSE медианы | RF лучше по RMSE? |','|---|---:|---:|:---:|---:|---:|:---:|']
    for r in ml['baseline_comparisons']:
        lines.append(f"| {r['test']} | {r['rf_MAE']:.3f} | {r['baseline_MAE']:.3f} | {'Да' if r['rf_MAE_lower'] else 'Нет'} | {r['rf_RMSE']:.3f} | {r['baseline_RMSE']:.3f} | {'Да' if r['rf_RMSE_lower'] else 'Нет'} |")
    lines+=['','RF не превосходит медианную базу по MAE в каждом разбиении. Данные не позволяют заявлять об универсальной точности по культурам и районам. Порог R²<0,5 - защитное правило вывода, не вероятностная доверительная граница.','','## A8. Экономический сценарий и эффект внедрения','',
            '| Величина (обычная оптимизация относительно обычной базы) | Изменение |','|---|---:|',
            f"| Маржинальный доход, тг | {a['normal']['margin_change_kzt']:,.0f} |",
            f"| Подача воды на поле, м³ | {a['normal']['field_water_change_m3']:,.0f} |",
            f"| Частичные выбросы, кг CO₂e | {a['normal']['partial_ghg_change_kgco2e']:,.0f} |",
            '',f"При водном стрессе прежняя структура недопустима (нехватка {a['stress']['water_shortfall_in_infeasible_baseline_m3']:,.0f} м³). Новый допустимый план имеет расчётную маржу {a['stress']['optimized_margin_kzt']:,.0f} тг. Разность с недопустимой базой не является реализованной экономией.",
            'Акт внедрения подтверждает факт передачи/применения по формулировкам акта, но не подтверждает измеренный прирост прибыли или сокращение выбросов без фактических наблюдений.',
            '', '## Готовые формулировки для диссертации',
            '', '1. «Оценка CMIP6 выполнена по ансамблевым региональным аномалиям CCKP за 2040–2059 гг. относительно 1995–2014 гг.; показатели экстремальной жары характеризуют климатический сценарий, а не наблюдения конкретного хозяйства».',
            '2. «Альтернативная система весов 0,4366/0,5634 получена нормализацией частот ответов на два разных вопроса анкеты и применяется исключительно как анализ чувствительности, не как результат AHP».',
            '3. «Историческая RF-модель обладает неоднородной прогнозной надёжностью; для культур и районов с недостаточной точностью выводится предупреждение, решения преимущественно опираются на ресурсно-экономический расчёт».',
            '4. «Экономические и экологические различия между структурами хозяйства отражают контрфактический расчёт при общих допущениях, а не измеренный эффект внедрения».',
            '', '## Происхождение и ограничения','',
            'Проверяются только исходные табличные файлы, поставляемые в проекте. Соответствие тексту окончательной диссертации и достоверность хозяйственных первичных документов проверяются отдельно. Источники климатической методологии: https://worldbank.github.io/climateknowledgeportal/docs/collections/cmip6-x0.25.html и https://climateknowledgeportal.worldbank.org/index.php/metadata.',
            '',f"Хеш входа A8: `{a['input_sha256']}`."]
    mdpath=out/'BATCH_A4_A6_A7_A8_AUDIT_2026-10-17.md'; mdpath.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return jsonpath,mdpath,audit

if __name__=='__main__':
    j,m,a=build()
    print(j);print(m)
    print('Climate:',[(v['scenario'],v['discrepancy_mm']) for v in a['CMIP6']['models']])
    print('ML warnings:',a['validation']['cautioned_pairs'],'/',a['validation']['district_crop_pairs_checked'])
