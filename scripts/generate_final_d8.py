"""Reproduce dated, scenario-only A8 / D.8 from code, no live NASA/Streamlit.

Run from project root: python scripts/generate_final_d8.py
Never silently replace the archival 0.70509 / 0.6061 baseline JSON.
"""
from __future__ import annotations
import csv
import json
import sys
import types
import hashlib
from copy import deepcopy
from importlib.util import find_spec
from pathlib import Path

if find_spec('streamlit') is None:
    stub=types.ModuleType('streamlit')
    stub.cache_data=lambda *args,**kwargs: (lambda f:f)
    stub.cache_resource=stub.cache_data
    sys.modules['streamlit']=stub
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.a8_reproducible_case import load_case
from core.a8_crosscheck import generate_a8_crosscheck
from core.pumping_billing import pumping_kwh_per_m3

OUT=ROOT/'examples'/'final_d8_2026_10_18'
SOURCE_PRICE='https://hearings.ndbecology.gov.kz/Public/PubHearings/LoadFile/245313'
SOURCE_WATER='https://www.gov.kz/memleket/entities/karaganda-tabigat/press/article/details/224741'
SOURCE_288='https://insecure.zan.kz/rus/docs/G26MA000288'
SOURCE_108='https://old.adilet.zan.kz/rus/docs/V2500036253'

MAP={'Cotton':'Хлопчатник','Corn':'Кукуруза','Wheat':'Пшеница'}

def structure(a):
    if a is None: return None
    result={MAP.get(k,k):float(v) for k,v in a.items()}
    if not abs(sum(result.values())-100)<1.e-5: raise AssertionError('Crop areas fail 100 ha mass balance')
    return result

def result_rows(result0,result5):
    case=result0['ordinary_economic_optimum']
    sus=result0['sustainable_current']
    stress=result0['stress']
    current_cap=case['baseline']['partial_ghg_kg_co2e']
    water_cap=case['water_budget_m3']
    rows=[]
    def add(label,areas,metrics,status,limits):
        areas=structure(areas)
        if metrics is not None:
            if metrics['water_field_delivery_m3']<0:raise AssertionError('Invalid water')
            if areas is None:raise AssertionError('No areas for computed totals')
        rows.append({'scenario':label,'areas_ha':areas,
            'water_m3':metrics['water_field_delivery_m3'] if metrics else None,
            'contribution_margin_kzt':metrics['contribution_margin_kzt'] if metrics else None,
            'partial_ghg_kgco2e':metrics['partial_ghg_kg_co2e'] if metrics else None,
            'solver_status':status, 'constraints':limits})
    add('Исходная структура',case['baseline_areas_ha'],case['baseline'],'reference', 'Проверка воды при лимите 750000 м³')
    add('Экономический оптимум',case['optimized_areas_ha'],case['optimized'],case['optimizer_status'],'Только водный лимит, без ограничения CO₂e')
    add('Устойчивый компромисс δ=0',sus['areas_ha'],sus['optimized'],sus['status'],'Вода ≤750000; CO₂e ≤сегодня; маржа ≥исходной')
    add('Комбинированный стресс',stress['optimized_areas_ha'],stress['optimized'],stress['optimizer_status'],'Вода ≤600000; урожай −10%; затраты +10%')
    for ssp in ('SSP2-4.5','SSP5-8.5'):
        for tol, obj in ((0.,result0),(5.,result5)):
            entry=obj['climate_scenarios'][ssp]['reoptimized_with_absolute_present_carbon_cap']
            add(f'{ssp}, δ≤{tol:g}%',entry['areas_ha'],entry['optimized'],entry['status'],
                f'Вода ≤750000; CO₂e ≤{current_cap:.4f} кг; маржа ≥ {100-tol:g}% исходной в будущем; SSP proxy')
    for r in rows:
        if r['areas_ha'] is None:continue
        if r['scenario'].startswith(('SSP','Устойчивый')):
            if r['water_m3']>water_cap+1.e-4 or r['partial_ghg_kgco2e']>current_cap+1.e-4:
                raise AssertionError('Published feasible case violates resource cap')
        if r['scenario']=='Комбинированный стресс' and r['water_m3']>600000.001:
            raise AssertionError('Published stress plan violates water cap')
    return rows


def generate(name='canonical_exVAT_41p06', tariff=41.06, *, save=True):
    case=deepcopy(load_case())
    t=case['technical_assumptions']
    t.update({
        'water_supply_service_mode':'gravity_with_separate_onfarm_pump',
        'pump_electricity_kwh_per_m3_field_delivery':pumping_kwh_per_m3(25,0.65),
        'water_tariff_kzt_per_m3_field_delivery':1.16,
        'electricity_tariff_kzt_per_kwh':tariff,
        'grid_kg_co2e_per_kwh':0.813,
        'diesel_kg_co2_per_litre':2.676492,
    })
    case['evidence_status'].update({
       'water':'Order 108-NQ (2025) historical; for Maktaaral these three rows match Order 288-NQ of 2026 (same soil/surface/50% assumptions). '+SOURCE_288,
       'energy_and_tariffs':'Own pump H=25m overall efficiency=0.65, theoretical kWh/m3; water 1.160 ex VAT national Kazvodkhoz public reference, conditional on provider; electricity '+str(tariff)+' KZT/kWh date-labelled November 2025 commercial reference, NOT independently confirmed for October 2026; '+SOURCE_WATER+'; '+SOURCE_PRICE,
       'emission_factor':'2025 electricity generation average 0.813 kg CO2/kWh (Ember secondary reproduction), not full CO2e or official farm factor',
    })
    out0=generate_a8_crosscheck(case,margin_tolerance_pct=0.0)
    out5=generate_a8_crosscheck(case,margin_tolerance_pct=5.0)
    rows=result_rows(out0,out5)
    record={'scenario_id':name,'as_of_date':'2026-10-18', 'case_type':'illustrative hypothetical not measured',
        'description':'gravity Kazvodkhoz water service + on-farm pump; Apr-Sep; field delivery',
        'input_sha256':hashlib.sha256(json.dumps(case,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        'input':case,'rows':rows,'scenario_proxy':'CCKP SSP anomaly/Hargreaves temperature TERM, not FAO-56 future irrigation',
        'source_links':[SOURCE_PRICE,SOURCE_WATER,SOURCE_288,SOURCE_108]}
    if save:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/f'{name}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        with (OUT/f'{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(['Scenario','Cotton ha','Corn ha','Wheat ha','Water m3','Margin KZT','Partial GHG kg CO2e','Solver status','Constraint note'])
            for r in rows:
                a=r['areas_ha'] or {}
                w.writerow([r['scenario'],a.get('Хлопчатник',''),a.get('Кукуруза',''),a.get('Пшеница',''),r['water_m3'] if r['water_m3'] is not None else '',r['contribution_margin_kzt'] if r['contribution_margin_kzt'] is not None else '',r['partial_ghg_kgco2e'] if r['partial_ghg_kgco2e'] is not None else '',r['solver_status'],r['constraints']])
    return record

if __name__=='__main__':
    for name,tariff in (('canonical_exVAT_41p06',41.06),('historic_2025_inVAT_45p9872',45.9872),('historic_preNov2025_inVAT_44p7552',44.7552)):
        r=generate(name,tariff)
        print(name,[(x['scenario'],round(x['contribution_margin_kzt']/1e6,3) if x['contribution_margin_kzt'] is not None else None) for x in r['rows']])
