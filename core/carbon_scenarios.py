"""Scenario-safe partial GHG inventory (no missing-as-zero substitutions).

Direct fertilizer field N2O, diesel combustion CO2, electricity CO2e, and
optionally enteric CH4. These are *partial* direct and purchased electricity
emissions; fertilizer production, indirect N2O, manure, soil carbon etc. omitted.
No emission reduction is claimed without matched baseline and proposal data.
"""
from dataclasses import dataclass
from math import isfinite

DEFAULT_N2O_N_PER_N=0.01  # 2019 Refinement to the 2006 IPCC Guidelines, generic EF1
DEFAULT_N2O_GWP100=273.0  # AR6 100-year N2O
DEFAULT_CH4_GWP100=27.0  # AR6 biogenic CH4 100-year convention
DEFAULT_DIESEL_CO2_KG_L=2.68  # illustrative combustion factor, must be checked for local fuel spec

@dataclass(frozen=True)
class PartialGHG:
    components:dict
    missing:tuple
    known_total_kg_co2e:float
    complete:bool
    factor_signature:tuple=()
    accounting_period:str="user_defined"


def partial_inventory(*, nitrogen_kg=None, diesel_litres=None,
                      electricity_kwh=None, grid_kg_co2e_kwh=None,
                      enteric_heads=None, enteric_kg_ch4_head_year=None,
                      enteric_year_fraction=None, diesel_factor=DEFAULT_DIESEL_CO2_KG_L,
                      n2o_factor=DEFAULT_N2O_N_PER_N,
                      n2o_gwp=DEFAULT_N2O_GWP100, ch4_gwp=DEFAULT_CH4_GWP100,
                      include_enteric=False, accounting_period="user_defined"):
    if accounting_period not in ('user_defined','apr_sep','calendar_year'):
        raise ValueError('Unrecognized GHG accounting period')
    values={"fertilizer_n2o":nitrogen_kg,"diesel":diesel_litres,
            "electricity":electricity_kwh}
    output={}
    missing=[]
    for key,val in values.items():
        if val is None:
            missing.append(key)
        elif not isfinite(float(val)) or float(val)<0:
            raise ValueError(f"Invalid GHG activity: {key}")
    for fac in (diesel_factor,n2o_factor,n2o_gwp,ch4_gwp):
        if not isfinite(float(fac)) or fac<0:
            raise ValueError('Invalid emission factor')
    if nitrogen_kg is not None and float(nitrogen_kg)>0 and n2o_factor<=0:
        raise ValueError('A positive nitrogen input requires a positive N2O factor')
    if diesel_litres is not None and float(diesel_litres)>0 and diesel_factor<=0:
        raise ValueError('Positive diesel use requires a positive combustion factor')
    if nitrogen_kg is not None:
        output['direct_fertilizer_n2o_kgco2e'] = float(nitrogen_kg)*n2o_factor*(44/28)*n2o_gwp
    if diesel_litres is not None:
        output['diesel_combustion_kgco2'] = float(diesel_litres)*diesel_factor
    if electricity_kwh is not None:
        if grid_kg_co2e_kwh is None:
            missing.append('electricity_factor')
        elif not isfinite(float(grid_kg_co2e_kwh)) or grid_kg_co2e_kwh<0:
            raise ValueError('Invalid grid emission factor')
        else:
            if float(electricity_kwh)>0 and float(grid_kg_co2e_kwh)<=0:
                raise ValueError('Positive electricity use requires a positive grid factor')
            output['electricity_kgco2e'] = float(electricity_kwh)*float(grid_kg_co2e_kwh)
    if include_enteric:
        if any(v is None for v in (enteric_heads,enteric_kg_ch4_head_year,enteric_year_fraction)):
            missing.append('enteric_methane')
        else:
            if any(float(v)<0 or not isfinite(float(v)) for v in (enteric_heads,enteric_kg_ch4_head_year,enteric_year_fraction)) or enteric_year_fraction>1:
                raise ValueError('Invalid enteric data')
            # A blank default emission factor must not turn a real herd into zero CH4.
            if float(enteric_heads) > 0 and float(enteric_year_fraction) > 0 and float(enteric_kg_ch4_head_year) <= 0:
                raise ValueError('Enteric factor must be positive for animals present; enter a sourced factor')
            output['enteric_methane_kgco2e'] = float(enteric_heads)*float(enteric_kg_ch4_head_year)*float(enteric_year_fraction)*ch4_gwp
    total=sum(output.values())
    # Keep method assumptions with the result so before/after comparisons cannot
    # manufacture a difference merely by changing the emission coefficients.
    signature = (float(n2o_factor),float(n2o_gwp),float(diesel_factor),
                 float(grid_kg_co2e_kwh) if grid_kg_co2e_kwh is not None else None,
                 float(ch4_gwp),bool(include_enteric),
                 float(enteric_kg_ch4_head_year) if enteric_kg_ch4_head_year is not None else None,
                 float(enteric_year_fraction) if enteric_year_fraction is not None else None)
    return PartialGHG(output,tuple(missing),total,len(missing)==0,signature,accounting_period)


def compare_partial_inventory(current: PartialGHG, planned: PartialGHG):
    if not current.complete or not planned.complete:
        raise ValueError('Matched complete known activity and factors required for GHG comparison')
    if set(current.components)!=set(planned.components):
        raise ValueError('Incompatible GHG component boundary')
    if current.factor_signature != planned.factor_signature:
        raise ValueError('Incompatible GHG emission-factor assumptions')
    if current.accounting_period != planned.accounting_period:
        raise ValueError('Incompatible GHG accounting periods')
    diff=planned.known_total_kg_co2e-current.known_total_kg_co2e
    return {"baseline_kgco2e":current.known_total_kg_co2e,
            "scenario_kgco2e":planned.known_total_kg_co2e,
            "change_kgco2e":diff,
            "possible_reduction_kgco2e":max(0.0, -diff),
            "possible_increase_kgco2e":max(0.0, diff),
            "direction":"increase" if diff>0 else ("decrease" if diff<0 else "unchanged"),
            "status":"counterfactual scenario, not field-measured achieved saving"}
