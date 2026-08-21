from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

from .water_norms import PRODUCT_TO_CODE, default_water_requirement
from .climate_score import empirical_climate_score

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SCENARIO = DATA_DIR / "qunar_decision_base.csv"
OBSERVED = DATA_DIR / "qunar_observed_evidence.csv"
REGISTRY = DATA_DIR / "crop_model_registry.csv"

DISTRICT_TO_RU = {
    "Sauran District":"Сауранский", "Turkestan City":"г. Туркестан",
    "Saryagash District":"Сарыагашский", "Keles District":"Келесский",
    "Zhetysay District":"Жетысайский", "Maktaaral District":"Мактааральский",
    "Shardara District":"Шардаринский", "Otyrar District":"Отырарский",
    "Ordabasy District":"Ордабасинский", "Arys City":"г. Арыс",
    "Sairam District":"Сайрамский", "Kazygurt District":"Казыгуртский",
    "Tolebi District":"Толебийский", "Tulkibas District":"Тюлькубасский",
    "Baydibek District":"Байдибекский", "Suzak District":"Сузакский",
    "Kentau City":"г. Кентау",
}

# Provisional methodological weights for the resource-climate contour only.
# They are intentionally isolated here and must be replaced by validated Delphi/AHP weights.
PROVISIONAL_RESOURCE_CLIMATE_WEIGHTS = {"climate": 0.60, "water_pressure": 0.40}

@st.cache_data(show_spinner=False)
def registry(): return pd.read_csv(REGISTRY)
@st.cache_data(show_spinner=False)
def _scenario_data(): return pd.read_csv(SCENARIO)
@st.cache_data(show_spinner=False)
def _observed_data(): return pd.read_csv(OBSERVED)

def check_crop_codes(): return registry()['Code'].tolist()
def label(code, lang='ru'):
    df=registry(); row=df[df.Code.eq(code)]
    if row.empty: return code
    col={'ru':'RU','kk':'KK','en':'EN'}.get(lang,'RU')
    return str(row.iloc[0][col])
def method(code):
    df=registry(); row=df[df.Code.eq(code)]
    return None if row.empty else str(row.iloc[0]['Model_tier'])
def _product(code):
    df=registry(); row=df[df.Code.eq(code)]
    if row.empty: return None
    val=row.iloc[0]['CLREM_product']
    return None if pd.isna(val) else str(val)

def _confidence_score(code: str | None, water_reliability: float, dynamic_climate: bool) -> float:
    if not code: tier = 45.0
    else:
        m = str(method(code) or "")
        if "ML + QŪNAR" in m or "ML + CLREM" in m: tier = 90.0
        elif m == "ML": tier = 85.0
        elif "Observed" in m: tier = 60.0
        else: tier = 70.0
    climate_evidence = 90.0 if dynamic_climate else 55.0
    return 0.45*tier + 0.35*float(water_reliability) + 0.20*climate_evidence

def _recalibrate(district: str, df: pd.DataFrame, climate: dict | None = None,
                 irrigation_type: str = "furrow") -> pd.DataFrame:
    """v0.8: resource-climate suitability separated from evidence confidence.

    Suitability combines climate and relative water pressure only. Confidence is reported
    separately and never makes a crop intrinsically better or worse.
    """
    out=df.copy(); codes=[]; waters=[]; wrel=[]; wsrc=[]; climate_scores=[]; climate_methods=[]
    legacy = pd.to_numeric(out.get('Climate_score_0_100'), errors='coerce').fillna(50.0)
    for idx,p in out['product'].astype(str).items():
        code=PRODUCT_TO_CODE.get(p)
        wd=default_water_requirement(district,code,irrigation_type)
        codes.append(code); waters.append(wd.m3_ha); wrel.append(wd.reliability_0_100); wsrc.append(wd.source_label)
        dyn=empirical_climate_score(district,code,climate) if code else {"score":None}
        if dyn.get('score') is not None:
            climate_scores.append(float(dyn['score'])); climate_methods.append(dyn.get('method','empirical'))
        else:
            climate_scores.append(float(legacy.loc[idx])); climate_methods.append('legacy_proxy_pending_crop_calibration')
    out['crop_code']=codes
    out['official_water_default_m3_ha']=waters
    out['water_default_reliability_0_100']=wrel
    out['water_default_source']=wsrc
    out['Climate_score_0_100']=climate_scores
    out['Climate_method']=climate_methods

    w=pd.Series(waters,index=out.index,dtype=float)
    if len(out)>1 and float(w.max()-w.min())>1e-9:
        out['Water_pressure_score_0_100']=100.0*(w.max()-w)/(w.max()-w.min())
    else: out['Water_pressure_score_0_100']=50.0
    out['Resource_efficiency_0_100']=out['Water_pressure_score_0_100']
    wc=PROVISIONAL_RESOURCE_CLIMATE_WEIGHTS['climate']; ww=PROVISIONAL_RESOURCE_CLIMATE_WEIGHTS['water_pressure']
    out['QUNAR_score_0_100']=(wc*out['Climate_score_0_100']+ww*out['Water_pressure_score_0_100']).clip(0,100)
    out['Data_reliability_0_100']=[_confidence_score(c,wr,m!='legacy_proxy_pending_crop_calibration') for c,wr,m in zip(codes,wrel,climate_methods)]
    out['Confidence_0_100']=out['Data_reliability_0_100']
    out=out.drop(columns=['Economic_score_0_100','gross_revenue_proxy_kzt_ha','price_kzt_t','yield_proxy_t_ha'],errors='ignore')
    out['District_rank']=out['QUNAR_score_0_100'].rank(method='first',ascending=False).astype(int)
    return out.sort_values(['District_rank','product']).copy()

def scenario_for_district(district, climate=None, irrigation_type='furrow'):
    df=_scenario_data(); ru=DISTRICT_TO_RU.get(district,district); base=df[df['district'].eq(ru)].copy()
    return base if base.empty else _recalibrate(district,base,climate,irrigation_type)
def scenario_for_crop(district,code,climate=None,irrigation_type='furrow'):
    product=_product(code)
    if not product:return None
    df=scenario_for_district(district,climate,irrigation_type); row=df[df['product'].eq(product)]
    return None if row.empty else row.iloc[0].to_dict()
def observed_for_crop(district,code):
    product=_product(code)
    if not product:return pd.DataFrame()
    df=_observed_data(); ru=DISTRICT_TO_RU.get(district,district)
    return df[(df['district'].eq(ru))&(df['product'].eq(product))].copy()
def observed_extra_for_district(district):
    df=_observed_data(); ru=DISTRICT_TO_RU.get(district,district); wanted=['Виноград свежий','Ягоды и плоды прочие']
    return df[(df['district'].eq(ru))&(df['product'].isin(wanted))].copy()
def decision_table(district,lang='ru',climate=None,irrigation_type='furrow'):
    df=scenario_for_district(district,climate,irrigation_type).copy()
    names=registry()[['CLREM_product',{'ru':'RU','kk':'KK','en':'EN'}.get(lang,'RU')]].dropna(); names.columns=['product','display']
    df=df.merge(names,on='product',how='left'); df['display']=df['display'].fillna(df['product'])
    cols=['District_rank','display','QUNAR_score_0_100','Climate_score_0_100','Water_pressure_score_0_100','Confidence_0_100','official_water_default_m3_ha','water_default_source','Climate_method']
    return df[cols].sort_values('District_rank')
