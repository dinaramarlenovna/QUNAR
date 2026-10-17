"""Recompute QUNAR two-criterion crop rankings over weight grid.

Preserves agreed baseline 60/40, cross-question survey what-if 93/213 vs 120/213;
no AHP or respondent-level answers are inferred from aggregates.
"""
from __future__ import annotations
import sys,types,csv,json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
try:import streamlit
except ImportError:
    stub=types.ModuleType('streamlit');stub.cache_data=lambda *a,**kw:(lambda f:f);stub.cache_resource=lambda *a,**kw:(lambda f:f)
    sys.modules['streamlit']=stub
from core.clrem import scenario_for_district,DISTRICT_TO_RU
from core.survey_weights import survey_proxy_profile, audit_survey_aggregates
from core.clrem import RESOURCE_CLIMATE_WEIGHTS
OUT=ROOT/'examples'/'stage2_evidence'
WEIGHTS=[round(float(v),2) for v in np.linspace(0,1,101)]

def ranking(data,climate_weight):
    x=data[['product','Climate_score_0_100','Water_pressure_score_0_100']].copy()
    x['score']=climate_weight*x['Climate_score_0_100']+(1-climate_weight)*x['Water_pressure_score_0_100']
    # Original table order + stable sort reproduces pandas rank(method='first').
    return x.sort_values('score',ascending=False,kind='mergesort')

def run(out=OUT):
    audit_survey_aggregates()
    proxy=survey_proxy_profile()
    base=float(RESOURCE_CLIMATE_WEIGHTS['climate'])
    assert abs(base-.6)<1e-12
    test=float(proxy['climate'])
    reported=pd.read_csv(ROOT/'data'/'survey_weight_sensitivity_17_regions.csv')
    rows=[];profiles=[]
    bydistrict={district:scenario_for_district(district) for district in DISTRICT_TO_RU}
    original_rank={district:ranking(data,base) for district,data in bydistrict.items()}
    for district,data in bydistrict.items():
        assert len(data)==15 and data['product'].is_unique
        b=ranking(data,base);s=ranking(data,test)
        btop=b['product'].iloc[:3].tolist();stop=s['product'].iloc[:3].tolist()
        record=reported[reported['Территория'].eq(district)]
        assert len(record)==1
        observed=record.iloc[0]
        prev=(observed['Лидер 60/40']==btop[0] and observed['Лидер 43,7/56,3']==stop[0] and
              (observed['Топ-3 одинаков']=='Да')==(set(btop)==set(stop)))
        snapshots=[ranking(data,w) for w in WEIGHTS]
        leader_switch=sum(p['product'].iloc[0]!=btop[0] for p in snapshots)
        winner_unchanged_range=[w for w,p in zip(WEIGHTS,snapshots) if p['product'].iloc[0]==btop[0]]
        winner_margin=float(b['score'].iloc[0]-b['score'].iloc[1])
        rows.append({'district':district,'baseline_leader':btop[0],'proxy_leader':stop[0],
                     'leaders_same':btop[0]==stop[0],'top3_same_set':set(btop)==set(stop),
                     'baseline_top3':' | '.join(btop),'proxy_top3':' | '.join(stop),
                     'baseline_first_second_gap_pts':winner_margin,
                     'baseline_leader_min_weight_on_grid':min(winner_unchanged_range),
                     'baseline_leader_max_weight_on_grid':max(winner_unchanged_range),
                     'grid_weights_different_leader':leader_switch,
                     'matches_prior_published_sensitivity':prev})
    if not all(r['matches_prior_published_sensitivity'] for r in rows):
        raise ValueError('Regenerated rankings disagree with published sensitivity CSV; investigate inputs before declaring 17/17 stable')
    for w in WEIGHTS:
        top1=top3=0
        for district,dat in bydistrict.items():
            orig=original_rank[district];alt=ranking(dat,w)
            top1+=orig['product'].iloc[0]==alt['product'].iloc[0]
            top3+=set(orig['product'].iloc[:3])==set(alt['product'].iloc[:3])
        profiles.append({'climate_weight':w,'water_weight':round(1-w,2),'same_top1_territories':top1,'same_top3_sets_territories':top3})
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    for filename,tab in [('survey_weight_grid_summary.csv',profiles),('survey_weight_districts_diagnostics.csv',rows)]:
        with (out/filename).open('w',newline='',encoding='utf-8-sig') as fh:
            writer=csv.DictWriter(fh,fieldnames=tab[0].keys());writer.writeheader();writer.writerows(tab)
    res={'base':{'climate':base,'water':1-base},'proxy':{'climate':test,'water':float(proxy['water'])},
         'n':int(proxy['respondents']),'climate_Q7':proxy['climate_mentions'],'water_Q3':proxy['water_mentions'],
         'headline':{'same_first':sum(x['leaders_same'] for x in rows),'same_top3':sum(x['top3_same_set'] for x in rows)},
         'min_baseline_margin':min(x['baseline_first_second_gap_pts'] for x in rows),
         'districts_with_margin_less_1': [x['district'] for x in rows if x['baseline_first_second_gap_pts']<1],
         'source_comparison_all_match':all(x['matches_prior_published_sensitivity'] for x in rows),
         'weight_grid':profiles,'districts':rows,
         'caution':'Grid sweeps are deterministic model-output robustness, not confidence intervals or evidence of elicited questionnaire weights.'}
    (out/'survey_stage2_sensitivity.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
    return res
if __name__=='__main__':
    r=run();print('MATCH',r['source_comparison_all_match'],r['headline']);print('margin<1',r['districts_with_margin_less_1']);print('grid',[(v['climate_weight'],v['same_top1_territories'],v['same_top3_sets_territories']) for v in r['weight_grid'] if v['climate_weight'] in [0.3,0.4,0.5,0.6,0.7]])
