from pathlib import Path
import sys,json,csv,copy
import numpy as np
from scipy.optimize import linprog
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import types,importlib.util
if importlib.util.find_spec("streamlit") is None:
 st=types.ModuleType("streamlit");st.cache_data=lambda *a,**k:(lambda f:f);st.cache_resource=st.cache_data;sys.modules["streamlit"]=st
from core.a8_reproducible_case import _crop_records
from core.pumping_billing import pumping_kwh_per_m3
cfg=json.loads((root/'examples/final_d8_2026_10_18/canonical_exVAT_41p06.json').read_text())['input']
# substitute a transparent historic subset of costs, rather than pretend current farm-wide variable cost
hist={}
with (root/'data/south_kazakhstan_crop_cost_norms_2004.csv').open() as f:
 for row in csv.DictReader(f):
  if row['agrozone']=='VIII subtropical desert' and row['technology']=='scientific' and row['water_regime']=='irrigated':
   hist[row['crop_code']]=row
for c in ('Cotton','Corn','Wheat'):
 cfg['crop_activities'][c]['other_variable_cost_kzt_ha']=float(hist[c]['wages_fuel_seeds_kzt_ha_2004'])
# only sources whose group classification is justified
cfg['crop_activities']['Corn']['diesel_litres_ha']=31.06/0.84
cfg['crop_activities']['Wheat']['diesel_litres_ha']=31.06/0.84
# retain cotton diesel assumed: no verified RK crop-level activity
cfg['crop_activities']['Corn']['nitrogen_kg_ha']=90.0
rows=_crop_records(cfg)
from core.a8_crosscheck import _water_margin_ghg_by_product
water,margin,ghg=_water_margin_ghg_by_product(rows,cfg)
products=[r['product'] for r in rows]
W=np.array([water[p] for p in products]); M=np.array([margin[p] for p in products]); G=np.array([ghg[p] for p in products]);
U=np.array([29.29246376811594,41.699710144927536,74.92]);E=100*(M-M.min())/(M.max()-M.min())
share=np.array([50.,30.,20.]);bds=[(3,60)]*3
# linear programming for area allocation (3 crop total 100 ha)
def sol(coeff,water_budget=750000,extra=None):
 A=[W];b=[water_budget]
 if extra:
  for ar,cap in extra:A.append(ar);b.append(cap)
 res=linprog(-coeff,A_ub=np.array(A),b_ub=np.array(b),A_eq=np.ones((1,3)),b_eq=[100],bounds=bds,method='highs');return None if not res.success else res.x
baseline=lambda x:{'Cotton ha':x[0],'Corn ha':x[1],'Wheat ha':x[2],'margin_million_kzt':x@M/1e6,'water_1000_m3':x@W/1000,'partial_ghg_t_co2e':x@G/1000}
opt=sol(M);minimum=sol(-W);
# sustainable as constrained maximum margin with baseline margin and G cap
sus=sol(M,extra=[(G,share@G)])
# λ based on composite normalized crop-wise scores
a=[]
for l in [0,.25,.35,.5,.7,1]:
 x=sol((1-l)*U+l*E)
 a.append({'lambda':l,**(baseline(x) if x is not None else {}),'status':'feasible' if x is not None else 'infeasible','basis':'2004 partial cost lower bound; KZ diesel 2023 wheat/corn; N90 corn; other data canonical'})
out=root/'examples'/'a8_historical_reference_sensitivity_2026_10_20';out.mkdir(parents=True,exist_ok=True)
def dump(name,arr):
 with (out/name).open('w',newline='',encoding='utf-8-sig') as f:
  wr=csv.DictWriter(f,fieldnames=list(arr[0]));wr.writeheader();wr.writerows(arr)
dump('E9_lambda_historical_reference.csv',a)
strats=[('Baseline original 50/30/20',share),('Maximum margin',opt),('Minimum irrigation water',minimum),('GHG-capped compromise',sus)]
b=[]
for name,x in strats:
 if x is None: continue
 d=baseline(x);d['strategy']=name
 # fixed structure, -10% yields; +10% on cost: isolate product revenue as M+water tariff+ pumping + other cost
 other=np.array([cfg['crop_activities'][c]['other_variable_cost_kzt_ha'] for c in ('Cotton','Corn','Wheat')]); resource=W*(1.16+pumping_kwh_per_m3(25,.65)*41.06);rev=M+other+resource
 d['stress_fixed_margin_million_kzt']=x@(0.9*rev-1.1*(other+resource))/1e6
 d['stress_water_feasible_600k']=bool(x@W<=600000+1e-7)
 d['SSP2_4_5_fixed_margin_million_kzt']=x@(M-0.046*resource)/1e6
 d['SSP2_4_5_water_feasible_750k']=bool(1.046*x@W<=750000+1e-7)
 b.append(d)
dump('E10_strategies_fixed_stress_historical_reference.csv',b)
old=json.loads((root/'examples/final_d8_2026_10_18/canonical_exVAT_41p06.json').read_text())
changes=[]
for c in ('Cotton','Corn','Wheat'):
 for field in ('other_variable_cost_kzt_ha','nitrogen_kg_ha','diesel_litres_ha'):
  changes.append({'crop':c,'parameter':field,'before':old['input']['crop_activities'][c][field],'historical_reference_scenario':cfg['crop_activities'][c][field], 'source':('RK 2004 Vlll zone scientific technology wage-fuel-seed subset' if field=='other_variable_cost_kzt_ha' else ('RK diesel 2023 Annex 2; conversion with assumed 0.84 kg/L' if field=='diesel_litres_ha' and c!='Cotton' else ('KZ Agronomy 2022 corn N90 conditional soil and yield' if field=='nitrogen_kg_ha' and c=='Corn' else 'unchanged A8 assumption'))),'evidence_note':'NOT contemporaneous 2025 costs or observed farm values'})
dump('D8_parameters_before_after.csv',changes)
(out/'ASSUMPTIONS_AND_LIMITS.json').write_text(json.dumps({'warning':'2004 partial cost amounts are a historical nominal LOWER-BOUND scenario, not valid modern variable costs; no evidence prices unchanged','water_m3_per_ha':W.tolist(),'margin_kzt_ha':M.tolist(),'partial_ghg_kg_co2e_per_ha':G.tolist(),'products':products,'historic_zone':'VIII subtropical desert irrigated scientific','cost_basis':'wages_fuel_seeds_kzt_ha_2004; incomplete costs; excludes water and pump electricity as separate model cost','diesel_density_kg_l':0.84,'canonical_d8_unchanged':True,'baseline_2025_district_structure_not_used':'unverified total crop areas; 50/30/20 remains illustrative','lambda_math':'linear weighted sum normalized utility and margin score; independent LP with hard min 3 max 60 area and water 750k; not native optimizer lambda'},ensure_ascii=False,indent=2),encoding='utf-8')
print('rows',len(a),len(b),'baseline',baseline(share),'optimized',baseline(opt),'sustainable',baseline(sus),'files',list(out.glob('*')))
