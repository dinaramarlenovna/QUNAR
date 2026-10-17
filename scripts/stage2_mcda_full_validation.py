"""Independent experimental robustness study for QŪNAR v0.8.1 crop ranking.

No new preference judgments are asserted, no production weights changed.
Monte Carlo uncertainties are declared sensitivity scenarios, NOT confidence intervals.
"""
from __future__ import annotations
import json, sys, types
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
try: import streamlit
except ImportError:
    s=types.ModuleType('streamlit'); s.cache_data=lambda *a,**kw:(lambda f:f);s.cache_resource=lambda *a,**kw:(lambda f:f);sys.modules['streamlit']=s
from core.clrem import DISTRICT_TO_RU,scenario_for_district
OUT=ROOT/'examples'/'stage2_evidence'

def ahp_two_criteria(climate_weight=.6):
    ratio=climate_weight/(1-climate_weight)
    matrix=np.array([[1.,ratio],[1./ratio,1.]])
    ev,vec=np.linalg.eig(matrix)
    p=np.abs(vec[:,np.argmax(ev.real)].real);p=p/p.sum()
    return {'matrix':matrix.tolist(),'reconstructed_weights':p.tolist(),'lambda_max':float(max(ev.real)),
       'consistency':'Not independently testable for 2 criteria; ratio is imposed, not elicited from experts.'}

def entropy_climate_weight(scores):
    # Dispersion weights: reflect variation across alternatives, NOT decision-maker priority.
    x=np.maximum(np.asarray(scores,float),0)+1e-12
    p=x/x.sum(axis=0,keepdims=True)
    n=len(x); ent=-np.sum(p*np.log(p),axis=0)/np.log(n)
    contrast=np.maximum(0,1-ent)
    return float(contrast[0]/contrast.sum()) if contrast.sum()>1e-12 else .5

def critic_climate_weight(scores):
    # With two criteria, standard CRITIC contrasts cancel in normalized weights,
    # effectively weighting by cross-crop standard deviation only.
    x=np.asarray(scores,float)/100.
    s=np.std(x,axis=0,ddof=0)
    return float(s[0]/s.sum()) if s.sum()>1e-12 else .5

def topsis(scores,weight):
    x=np.asarray(scores,dtype=float)
    denom=np.linalg.norm(x,axis=0)
    v=x/np.where(denom>1.e-12,denom,1)*np.array([weight,1-weight])
    best=v.max(axis=0);worst=v.min(axis=0)
    db=np.sqrt(np.square(v-best).sum(axis=1));dw=np.sqrt(np.square(v-worst).sum(axis=1))
    return np.divide(dw,db+dw,out=np.full(len(dw),.5),where=(db+dw)>1.e-12)

def run(out=OUT,n_sim=10000,seed=20261018):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(seed)
    rows=[];leaders=[];weights=rng.uniform(.3,.7,size=n_sim)
    for district in DISTRICT_TO_RU:
        d=scenario_for_district(district).copy().reset_index(drop=True)
        assert len(d)==15 and d['product'].is_unique
        cols=['Climate_score_0_100','Water_pressure_score_0_100']
        assert d[cols].notna().all().all()
        x=d[cols].to_numpy(float); names=d['product'].to_numpy()
        ref=.6*x[:,0]+.4*x[:,1];idx=np.argsort(-ref,kind='stable')
        alt=topsis(x,.6);ti=np.argsort(-alt,kind='stable')
        ent_w=entropy_climate_weight(x);crit_w=critic_climate_weight(x)
        entropy_idx=np.argsort(-(ent_w*x[:,0]+(1-ent_w)*x[:,1]),kind='stable')
        critic_idx=np.argsort(-(crit_w*x[:,0]+(1-crit_w)*x[:,1]),kind='stable')
        # Monte Carlo 1: weight uncertainty only, uniform [0.30, 0.70]
        simulated=weights[:,None]*x[:,0]+(1-weights[:,None])*x[:,1]
        win=np.argmax(simulated,axis=1)
        # Monte Carlo 2: illustrative, bounded random score perturbation SD = 3 points
        noise=rng.normal(loc=0,scale=3,size=(n_sim,len(d),2))
        pert=np.clip(x[None,:,:]+noise,0,100)
        simulated2=weights[:,None]*pert[:,:,0]+(1-weights[:,None])*pert[:,:,1]
        win2=np.argmax(simulated2,axis=1)
        wc=np.bincount(win,minlength=len(d))/n_sim
        nc=np.bincount(win2,minlength=len(d))/n_sim
        rref=np.empty(len(idx),int);rref[idx]=np.arange(1,len(idx)+1)
        rt=np.empty(len(ti),int);rt[ti]=np.arange(1,len(ti)+1)
        rows.append({'district':district,'baseline_top1':str(names[idx[0]]),'topsis_top1':str(names[ti[0]]),
          'same_top1':bool(idx[0]==ti[0]),'same_top3_set':bool(set(idx[:3])==set(ti[:3])),
          'entropy_climate_weight':ent_w,'critic_climate_weight':crit_w,
          'entropy_same_top1':bool(idx[0]==entropy_idx[0]),
          'critic_same_top1':bool(idx[0]==critic_idx[0]),
          'kendall_tau':float(kendalltau(rref,rt).statistic), 'spearman_rho':float(spearmanr(rref,rt).statistic),
          'mc_weight_only_baseline_winner_share':float(wc[idx[0]]),
          'mc_weight_plus_3pt_baseline_winner_share':float(nc[idx[0]]),
          'mc_weight_only_most_likely_winner':str(names[np.argmax(wc)]),
          'mc_perturbed_most_likely_winner':str(names[np.argmax(nc)]),
          'score_gap_top1_to_top2':float(ref[idx[0]]-ref[idx[1]])})
        for j,name in enumerate(names):
            leaders.append({'district':district,'crop':str(name),'baseline_rank':int(rref[j]),
            'topsis_rank':int(rt[j]),'mc_weight_only_top1_fraction':float(wc[j]),
            'mc_weight_plus_3pt_top1_fraction':float(nc[j])})
    tab=pd.DataFrame(rows)
    tab.to_csv(out/'mcda_topsis_by_district.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(leaders).to_csv(out/'mcda_mc_15crops_17districts.csv',index=False,encoding='utf-8-sig')
    res={'n_districts':len(tab),'n_crops_per_district':15,'topsis_same_top1':int(tab.same_top1.sum()),
         'topsis_same_top3_set':int(tab.same_top3_set.sum()),'topsis_mean_kendall_tau':float(tab.kendall_tau.mean()),
         'entropy_same_top1':int(tab.entropy_same_top1.sum()),'critic_same_top1':int(tab.critic_same_top1.sum()),
         'entropy_weight_climate_mean':float(tab.entropy_climate_weight.mean()),
         'critic_weight_climate_mean':float(tab.critic_climate_weight.mean()),
         'monte_carlo_n_per_district':n_sim, 'seed':seed,
         'weight_distribution':'uniform 0.30..0.70, illustrative epistemic sensitivity',
         'perturbation':'independent normal SD=3 score points clipped 0..100 (hypothetical; not empirical error distribution)',
         'mean_weight_only_baseline_winner_share':float(tab.mc_weight_only_baseline_winner_share.mean()),
         'mean_weight_and_3pt_baseline_winner_share':float(tab.mc_weight_plus_3pt_baseline_winner_share.mean()),
         'districts_weight_only_baseline_winner_share_below_half':tab.loc[tab.mc_weight_only_baseline_winner_share<.5,'district'].tolist(),
         'ahp_reconstruction':ahp_two_criteria(),
         'cautions':['Two-criterion AHP simply reconstructs preselected 60/40, NOT expert elicitation.',
                     'Entropy and CRITIC measure criterion dispersion across 15 crop alternatives, NOT farmer preferences or validated optimal policy weights.',
                     'TOPSIS provides method triangulation but no proof that recommendations are agronomically optimal.',
                     'Scores include legacy climate proxies; MC simulation does not validate these scores.',
                     'Risk/confidence kept separate from preference score to avoid rewarding unreliable data.'],
         'districts':rows}
    (out/'mcda_robustness_2026_10_18.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
    return res
if __name__=='__main__':
    r=run();print('TOPSIS leaders',r['topsis_same_top1'],'of 17','top3',r['topsis_same_top3_set']);print('MC means',r['mean_weight_only_baseline_winner_share'],r['mean_weight_and_3pt_baseline_winner_share'])
