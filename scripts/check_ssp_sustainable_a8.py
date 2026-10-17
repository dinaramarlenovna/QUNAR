import sys, types, json
from pathlib import Path
from importlib.util import find_spec
if find_spec('streamlit') is None:
    s=types.ModuleType('streamlit')
    def identity(*a, **k):
        return lambda f:f
    s.cache_data=identity;s.cache_resource=identity
    sys.modules['streamlit']=s
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.cmip6_scenarios import load_scenario
from core.optimizer import optimize_structure
from core.a8_reproducible_case import load_case,_crop_records,_economics
from core.ghg_structure import structure_inventory
import pandas as pd
c=load_case(); rec=_crop_records(c); econ=_economics(rec,None);tt=c['technical_assumptions']
margins={r['product']:econ[r['product']]['contribution_margin_kzt_ha'] for r in rec}
shares={r['product']:100*c['baseline_crop_shares'][r['code']] for r in rec}
ghg={}
for r in rec:
 a=c['crop_activities'][r['code']]
 inv=structure_inventory({r['product']:1.},{r['product']:{'nitrogen_kg_ha':a['nitrogen_kg_ha'],'diesel_litres_ha':a['diesel_litres_ha'],'electricity_kwh_ha':r['pump_electricity_kwh_ha']}},grid_factor=tt['grid_kg_co2e_per_kwh'],diesel_factor=tt['diesel_kg_co2_per_litre'],accounting_period='apr_sep',evidence='Illustrative A8',confirmed=True)
 ghg[r['product']]=inv['inventory'].known_total_kg_co2e
fallback=pd.read_csv(ROOT/'data'/'district_climate_fallback.csv')
row=fallback.loc[fallback['District'].eq('Maktaaral District')].iloc[0]
baseline={k:float(row[k]) for k in ['Apr-Sep temperature, °C','Apr-Sep precipitation, mm','Apr-Sep root-zone wetness','Apr-Sep solar radiation, MJ/m²/day']}
common=dict(district='Maktaaral District', area_ha=100., profile='balanced', max_share=.6,n_crops=3,available_water_m3=750000.,irrigation_type='furrow',objective_mode='sustainable', economic_margin_by_product=margins,baseline_share_by_product=shares,ghg_kg_co2e_by_product=ghg,sustainable_max_margin_decline_pct=0)
result=[]
for name in ['baseline','SSP2-4.5','SSP5-8.5']:
 climate=dict(baseline);meta={}
 if name!='baseline':
  s=load_scenario(ROOT/'data'/'cmip6',name)
  meta={'Delta_T_c':s.temperature_change_c,'Delta_P_pct':s.precipitation_change_pct}
  climate['Apr-Sep temperature, °C']+=s.temperature_change_c
  climate['Apr-Sep precipitation, mm']*=1+s.precipitation_change_pct/100
 alloc,summ=optimize_structure(**common,climate=climate)
 cmp=summ.get('sustainable_comparison')
 result.append({'scenario':name, 'climate_inputs':climate,'shift':meta,'status':summ.get('solver_status'),'area':{str(row['product']):round(float(row['area_ha']),3) for _,row in alloc.iterrows()}, 'comparison':cmp,'climate_scores':{str(row['product']):round(float(row['Climate_score_0_100']),4) for _,row in alloc.iterrows()}})
print(json.dumps(result,indent=2,ensure_ascii=False,default=float))
(ROOT / 'examples' / 'release_evidence' / 'QUNAR_SSP_SUSTAINABLE_OFFLINE_RESULTS_2026-10-17.json').write_text(json.dumps({'note':'climate-score-only sensitivity with fixed per-crop water/margin/GHG; region-level CCKP anomalies; NOT climate-resilient irrigation/yield confirmation','results':result},indent=2,ensure_ascii=False,default=float),encoding='utf-8')
