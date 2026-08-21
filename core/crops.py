from pathlib import Path
import pandas as pd
import streamlit as st

CATALOG = Path(__file__).resolve().parents[1] / 'data' / 'crop_expansion_catalog.csv'

def crop_catalog():
    return pd.read_csv(CATALOG)

def candidate_crops(lang='ru'):
    df=crop_catalog()
    df=df[df['Status'].eq('candidate')].copy()
    name_col={'ru':'RU','kk':'KK','en':'Crop'}.get(lang,'RU')
    tier={'ru':'Статистическая калибровка','kk':'Статистикалық калибрлеу','en':'Statistical calibration'}[lang]
    annual={'ru':'Официальный ряд урожайности доступен; нужна районно-годовая калибровка.',
            'kk':'Ресми өнімділік қатары бар; аудан-жыл деңгейінде калибрлеу қажет.',
            'en':'Official yield series is available; district-year calibration is required.'}[lang]
    perennial={'ru':'Официальный региональный ряд доступен; нужен отдельный модуль многолетних культур.',
               'kk':'Ресми өңірлік қатар бар; көпжылдық дақылдарға жеке модуль қажет.',
               'en':'Official regional series is available; a separate perennial-crop module is required.'}[lang]
    out=pd.DataFrame()
    out['Crop']=df[name_col]
    out['Model tier']=tier
    out['Evidence/status']=[perennial if 'perennial' in str(x).lower() else annual for x in df['Evidence/status']]
    return out
