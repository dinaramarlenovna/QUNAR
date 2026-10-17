"""Transparent sensitivity layer for CMIP6 temperature-only reference ETo.

Does NOT compute legally authoritative irrigation norms, crop water requirements,
or full Hargreaves/FAO56 evapotranspiration. The expression is only the
(Tmean+17.8) temperature term ratio with all other Hargreaves components held
fixed (Tmax-Tmin, extraterrestrial radiation). Rainfall change is not converted
straight into crop irrigation change. Use for exploratory sensitivity ONLY.
"""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class WaterStressResult:
    temperature_term_multiplier:float
    reference_only_water_m3:float
    change_m3:float
    status:str = 'temperature-only proxy, NOT a calculated irrigation requirement'


def temperature_only_water_sensitivity(baseline_water_m3, historical_mean_c, temperature_delta_c):
    values=(baseline_water_m3,historical_mean_c,temperature_delta_c)
    if not all(isfinite(float(x)) for x in values) or baseline_water_m3 < 0:
        raise ValueError('Finite temperature and nonnegative baseline water required')
    denominator=float(historical_mean_c)+17.8
    numerator=denominator+float(temperature_delta_c)
    if denominator<=0 or numerator<0:
        raise ValueError('Hargreaves temperature term is outside valid range')
    factor=numerator/denominator
    after=float(baseline_water_m3)*factor
    return WaterStressResult(factor,after,after-float(baseline_water_m3))
