"""Independent, conservative labels for previously computed ML validation data.

Thresholds are *display rules*, not newly estimated model confidence probabilities.
They do not edit the trained model, historical values or validation tables.
"""
from dataclasses import dataclass
from pathlib import Path
import csv
from math import isfinite

@dataclass(frozen=True)
class ForecastCaution:
    low_confidence:bool
    reasons:tuple
    district_n:int|None
    district_r2:float|None
    crop_n:int|None
    crop_r2:float|None
    source:str = 'historical crop-group CV and leave-one-district-out tables'


def _row_for(path, key, name):
    with Path(path).open(newline='',encoding='utf-8-sig') as f:
        match=[r for r in csv.DictReader(f) if r.get(key)==name]
    if not match:
        return None
    if len(match)>1:
        raise ValueError(f'Duplicate validation record: {key}={name}')
    return match[0]


def evaluate_forecast_support(data_dir,district,crop,*,min_district_n=20,
                              min_crop_n=20,crop_r2_threshold=0.5,district_r2_threshold=0.5):
    root=Path(data_dir)
    dr=_row_for(root/'model_metrics_leave_one_district_out.csv','District',district)
    cr=_row_for(root/'model_metrics_by_crop.csv','Crop',crop)
    reasons=[]
    dn,dr2,cn,cr2=None,None,None,None
    if dr is None:
        reasons.append('district validation unavailable')
    else:
        dn=int(float(dr['N']));dr2=float(dr['R2'])
        if dn <= 0 or not isfinite(dr2) or float(dr['N']) != dn:
            reasons.append('district validation metric invalid or undefined')
        if dn<min_district_n:
            reasons.append(f'district transfer test uses only {dn} records (<{min_district_n})')
        if not isfinite(dr2) or dr2<district_r2_threshold:
            reasons.append(f'district transfer R2 < {district_r2_threshold:.2f} or undefined')
    if cr is None:
        reasons.append('crop validation unavailable')
    else:
        cn=int(float(cr['N']));cr2=float(cr['R2'])
        if cn <= 0 or not isfinite(cr2) or float(cr['N']) != cn:
            reasons.append('crop validation metric invalid or undefined')
        if cn<min_crop_n:
            reasons.append(f'crop validation uses only {cn} records (<{min_crop_n})')
        if not isfinite(cr2) or cr2<crop_r2_threshold:
            reasons.append(f'crop time-block R2 < {crop_r2_threshold:.2f}')
    return ForecastCaution(bool(reasons),tuple(reasons),dn,dr2,cn,cr2)
