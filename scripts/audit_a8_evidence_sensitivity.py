"""Independent A8 sensitivity run: hypothetical conditions, never achieved farm impact.

Each run recalculates allocations from the same input JSON, with explicit
engineering pump work instead of the unverified fixed 0.70509 kWh/m3.
This script does NOT overwrite the canonical A8 inputs or artifacts.
"""
from pathlib import Path
import copy, csv, json, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
try:
    import streamlit
except ImportError:
    from types import ModuleType
    m=ModuleType('streamlit');m.cache_data=lambda *a,**k: (lambda f:f)
    sys.modules['streamlit']=m
from core.a8_reproducible_case import calculate_case, load_case

OUT = ROOT/'examples'/'stage3_a1_a3_a5_a8_evidence'
OUT.mkdir(parents=True, exist_ok=True)
base=load_case()
rows=[]
# Tariffs illustrate exact selected service classes, NOT farm receipts.
# This example: water supplied by gravity at published Kazvodkhoz reference;
# subsequent on-farm electricity pumping is separate, so no overlap in energy costs.
# Factor 0.813 is a nonofficial published national mix scenario, not site metering.
for cost_scale in (0.8,1.0,1.2):
  for head_m in (10,25,40):
    cfg=copy.deepcopy(base)
    pump_eta=0.65
    kwh_m3=0.002725 * head_m / pump_eta
    t=cfg['technical_assumptions']
    t.update({'pump_electricity_kwh_per_m3_field_delivery':kwh_m3,
              'water_tariff_kzt_per_m3_field_delivery':1.16,
              'electricity_tariff_kzt_per_kwh':44.7552,
              'grid_kg_co2e_per_kwh':0.813,
              'diesel_kg_co2_per_litre':2.676492})
    for row in cfg['crop_activities'].values():
      row['other_variable_cost_kzt_ha'] *= cost_scale
    result=calculate_case(cfg)
    b=result['normal']['baseline']; o=result['normal']['optimized']; s=result['stress']['optimized']
    rows.append({'scenario_id':f'HEAD{head_m}_COST{int(cost_scale*100)}',
         'head_m':head_m, 'pump_total_efficiency':pump_eta,
         'electricity_kwh_per_m3':kwh_m3,'nonwater_cost_scale':cost_scale,
         'water_supplier_reference':'Kazvodkhoz gravity service at supply boundary; separate on-farm pump',
         'water_tariff_kzt_m3':1.16,'energy_tariff_kzt_kwh':44.7552,
         'grid_factor_kg_kwh':0.813,
         'baseline_margin_kzt':b['contribution_margin_kzt'],
         'optimized_margin_kzt':o['contribution_margin_kzt'],
         'optimized_margin_minus_baseline_kzt':o['contribution_margin_kzt']-b['contribution_margin_kzt'],
         'baseline_water_m3':b['water_field_delivery_m3'],
         'optimized_water_m3':o['water_field_delivery_m3'],
         'baseline_partial_ghg_kg':b['partial_ghg_kg_co2e'],
         'optimized_partial_ghg_kg':o['partial_ghg_kg_co2e'],
         'optimized_minus_baseline_ghg_kg':o['partial_ghg_kg_co2e']-b['partial_ghg_kg_co2e'],
         'normal_baseline_feasible':b['water_feasible'],
         'normal_optimized_feasible':o['water_feasible'],
         'stress_optimized_margin_kzt':s['contribution_margin_kzt'],
         'stress_optimized_water_m3':s['water_field_delivery_m3'],
         'status':'illustrative stress test, not verified farm impact'})
with (OUT/'a8_9_scenario_sensitivity.csv').open('w', newline='',encoding='utf-8-sig') as fh:
  w=csv.DictWriter(fh,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(OUT/'a8_assumptions_and_provenance.json').write_text(json.dumps({
  'scope':'Counterfactual research only; not an observed enterprise, cost norm or real emission reduction',
  'parameter_ranges':{'head_m':[10,25,40],'eta':0.65,'other_cost_multiplier':[.8,1.,1.2]},
  'pump_formula':'kWh/m3 = 0.002725 * pump total head (m) / combined electrical/pump efficiency',
  'pump_source':'FAO Pressurized Irrigation Techniques, ch. 3, https://www.fao.org/4/a1336e/a1336e.pdf',
  'water_tariff_source':'Gov.kz published Kazvodkhoz irrigation gravity reference 01.01.2026, 1.160 KZT/m3 excluding VAT; tariff must be verified for each supplier/service',
  'electricity_tariff_source':'EnergyPotok published 2025 commercial tariff 44.7552 KZT/kWh incl VAT; supplier and tariff class matter',
  'grid_factor_source':'0.813 kgCO2/kWh national generation mix estimate published by Ember, not official regional procurement factor; sensitivity only',
  'diesel_factor_source':'IPCC 74.1 tCO2/TJ x NCV 43 MJ/kg x density assumption 0.84 kg/L = 2.676492 kg/L',
  'variable_cost_source':'Prior A8 unverified scenarios scaled ±20%; not a statistical estimate',
  'crop_water_source':'Existing QUNAR 2025 Order 108-NQ row mapping; unverified 2026 application',
  'measured_effect':'absent', 'findings':rows},ensure_ascii=False,indent=2),encoding='utf-8')
print('scenarios',len(rows))
for r in rows:
  if r['scenario_id']=='HEAD25_COST100': print('reference',json.dumps(r,ensure_ascii=False,indent=2))
