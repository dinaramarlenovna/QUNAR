"""Reference-backed field irrigation efficiencies and optional FAO crop-stage Kc.

FAO manuals provide illustrative field application efficiencies, *not* confirmed
farm outcomes or conveyance/withdrawal efficiencies. Kazakhstan's 2026
methodology additionally specifies conditional drip factors of 0.90--0.98;
those depend on local technique, soil and crop and are not silently assigned.

Crop-stage values refer to FAO Crop Water Needs Training Manual 3 Tables 7-8
and are *illustrative*, not crop calendars validated for Turkestan. No rice
presets: paddy flooding and ponded water require a separate field balance.
"""
from __future__ import annotations
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite

FAO_EFFICIENCY_URL = "https://www.fao.org/4/t7202e/t7202e08.htm"
FAO_CROP_KC_URL = "https://www.fao.org/4/S2022E/s2022e07.htm"
KAZAKH_IRRIGATION_METHODOLOGY_URL = "https://adilet.zan.kz/rus/docs/V2500036251"
KAZAKH_2026_AMENDMENT_URL = "https://adilet.zan.kz/rus/docs/V2600039130"

# FAO Irrigation Water Management Training Manual 4, Annex I, Table 8.
# Field-level application only; conveyance losses excluded.
FIELD_EFFICIENCIES = {'furrow': 0.60, 'sprinkler': 0.75, 'drip': 0.90}

# FAO Irrigation Water Management Training Manual 3, Tables 7 and 8.
# Values: four crop-stage coefficients, followed by one *illustrative* stage
# length profile in days (shorter season where Table 7 gives two choices).
# Climate, variety, sowing dates, rain and water management affect the values.
CROP_KC_STAGES = {
    'Wheat': ((0.35,0.75,1.15,0.45),(15,25,50,30)),
    'Barley': ((0.35,0.75,1.15,0.45),(15,25,50,30)),
    'Corn': ((0.40,0.80,1.15,0.70),(20,35,40,30)),
    'Cotton': ((0.45,0.75,1.15,0.75),(30,50,55,45)),
    'Potato': ((0.45,0.75,1.15,0.85),(25,30,30,20)),
    'Sunflower': ((0.35,0.75,1.15,0.55),(20,35,45,25)),
    'Cabbage': ((0.45,0.75,1.05,0.90),(20,25,60,15)),
    'Carrots': ((0.45,0.75,1.05,0.90),(20,30,30,20)),
    'Cucumbers': ((0.45,0.70,0.90,0.75),(20,30,40,15)),
    'Tomatoes': ((0.45,0.75,1.15,0.80),(30,40,40,20)),
    'Melons': ((0.45,0.75,1.00,0.75),(25,35,40,20)),
    'Onion': ((0.50,0.75,1.05,0.85),(15,25,70,40)),
}


def _valid_eta(value):
    try: eta = float(value)
    except (TypeError, ValueError): raise ValueError('Invalid irrigation application efficiency') from None
    if not isfinite(eta) or not 0 < eta <= 1: raise ValueError('Efficiency must be 0 < eta <= 1')
    return eta


def field_efficiency(method: str, *, override: float | None = None) -> float:
    """Return FAO field scenario or user's explicitly measured/assumed value.

    No default for unknown or mixed method. For mixed use mixed_efficiency().
    """
    if override is not None: return _valid_eta(override)
    if method not in FIELD_EFFICIENCIES:
        raise ValueError('No justified single default for unknown or mixed irrigation')
    return FIELD_EFFICIENCIES[method]


def mixed_efficiency(shares: dict[str, float]) -> float:
    """Area-weighted delivery: eta_eff = 1 / sum(area_share / eta_method).

    Assumes each component has the same net irrigation requirement per ha.
    """
    if not isinstance(shares, dict) or set(shares) != set(FIELD_EFFICIENCIES):
        raise ValueError('Provide shares for furrow, sprinkler and drip')
    try: vals = {k:float(v) for k,v in shares.items()}
    except (ValueError, TypeError): raise ValueError('Invalid shares') from None
    if any(not isfinite(v) or v < 0 for v in vals.values()): raise ValueError('Negative/invalid shares')
    total=sum(vals.values())
    if abs(total-1.0)>1e-6: raise ValueError('Mixed area shares must total 1')
    return _valid_eta(1.0/sum(share/FIELD_EFFICIENCIES[k]
                              for k,share in vals.items() if share))


def irrigation_saving(net_irrigation_m3_ha: float, baseline_eff: float,
                       proposed_eff: float, *, area_ha: float=1.0) -> dict:
    """Delivery saving at an unchanged net need, not change in consumptive use."""
    try: net=float(net_irrigation_m3_ha); area=float(area_ha)
    except (ValueError, TypeError): raise ValueError('Invalid net demand/area') from None
    if not isfinite(net) or net<0 or not isfinite(area) or area<=0:
        raise ValueError('Net demand must be >=0 and area >0')
    b=_valid_eta(baseline_eff); p=_valid_eta(proposed_eff)
    base=net/b; new=net/p
    return {'baseline_m3_ha':base,'proposed_m3_ha':new,
            'change_m3_ha':new-base, 'saving_m3_ha':base-new,
            'saving_pct':(100*(base-new)/base) if base>0 else 0.0,
            'saving_m3_field':(base-new)*area,
            'source':FAO_EFFICIENCY_URL,
            'scope':'reference field-application scenario; consumptive savings not established'}


def parse_stage_lengths(value: str) -> tuple[int,int,int,int]:
    pieces=str(value).replace(';',',').split(',')
    if len(pieces)!=4: raise ValueError('Four lengths (initial, development, mid, late) are required')
    vals=[]
    for p in pieces:
        p=p.strip()
        if not p.isdecimal(): raise ValueError('Stage length must be a positive whole number')
        v=int(p)
        if not 1<=v<=365: raise ValueError('Stage length out of supported range')
        vals.append(v)
    if sum(vals)>366: raise ValueError('Season exceeds 366 days')
    return tuple(vals)


def monthly_kc_from_calendar(crop: str, sowing_date: date,
                             stage_lengths: tuple[int,int,int,int] | None = None,
                             *, reference_year: int=2025) -> tuple[float,...]:
    """Apr-Sep daily-weighted stage Kc based on an explicit crop calendar.

    Only sowing/harvest presence is modeled, with Kc=0 outside active growth.
    This is the FAO Training Manual 3 four-stage approximation, not a
    locally calibrated FAO-56 Kc time series; no paddy or perennial crops.
    """
    if crop not in CROP_KC_STAGES: raise ValueError('No stage Kc reference for crop')
    if not isinstance(sowing_date,date): raise ValueError('A sowing date is required')
    stages,ref_lengths=CROP_KC_STAGES[crop]
    lengths=stage_lengths if stage_lengths is not None else ref_lengths
    if len(lengths)!=4 or any(type(x)!=int or x<=0 for x in lengths) or sum(lengths)>366:
        raise ValueError('Four positive stage lengths needed')
    end=sowing_date+timedelta(days=sum(lengths))
    stage_dates=[];cur=sowing_date
    for length in lengths:
        nxt=cur+timedelta(days=length);stage_dates.append((cur,nxt));cur=nxt
    out=[]
    for month in range(4,10):
        days=monthrange(reference_year,month)[1]
        total=0.0
        for day in range(1,days+1):
            when=date(reference_year,month,day)
            if sowing_date<=when<end:
                for k,(a,b) in enumerate(stage_dates):
                    if a<=when<b:
                        total+=stages[k];break
        out.append(round(total/days,6))
    if all(v==0.0 for v in out):
        raise ValueError('Crop is not in the April-September window')
    return tuple(out)
