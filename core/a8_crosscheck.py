"""Single-source A8 + CMIP6 *temperature-only* exploratory crosscheck.

The case JSON is primary. The original ML training and 2025 irrigation norms
are not modified. Under the Hargreaves (T+17.8)-term proxy, pumping activity,
electricity emissions, water and cost are recalculated per crop, and the
constrained allocation is re-run. This is NOT a full FAO56 climatic forecast.
"""
from __future__ import annotations
from copy import deepcopy
from math import isclose
from pathlib import Path
from .a8_reproducible_case import load_case, calculate_case, _crop_records, _economics
from .cmip6_scenarios import load_scenario
from .water_climate import temperature_only_water_sensitivity
from .ghg_structure import structure_inventory
from .optimizer import optimize_structure
from .data import district_climate

CMIP6_DIR=Path(__file__).resolve().parents[1]/'data'/'cmip6'


def _water_margin_ghg_by_product(rows, config, factor=1.0):
    base=_economics(rows,None)
    t=config['technical_assumptions']
    water={}; margin={}; ghg={}
    for r in rows:
        p=r['product']; a=config['crop_activities'][r['code']]
        w=r['water_m3_ha']*factor
        e=w*t['pump_electricity_kwh_per_m3_field_delivery']
        extra=w-r['water_m3_ha']
        water[p]=w
        margin[p]=base[p]['contribution_margin_kzt_ha']-extra*(
            t['water_tariff_kzt_per_m3_field_delivery']+
            t['pump_electricity_kwh_per_m3_field_delivery']*t['electricity_tariff_kzt_per_kwh'])
        inv=structure_inventory({p:1.0},{p:{'nitrogen_kg_ha':a['nitrogen_kg_ha'],
            'diesel_litres_ha':a['diesel_litres_ha'], 'electricity_kwh_ha':e}},
            grid_factor=t['grid_kg_co2e_per_kwh'], diesel_factor=t['diesel_kg_co2_per_litre'],
            accounting_period='apr_sep',evidence='A8 hypothetical activities',confirmed=True)
        ghg[p]=inv['inventory'].known_total_kg_co2e
    return water,margin,ghg


def _structure_totals(shares_or_areas,water,margin,ghg):
    return {
        'water_field_delivery_m3':sum(a*water[p] for p,a in shares_or_areas.items()),
        'contribution_margin_kzt':sum(a*margin[p] for p,a in shares_or_areas.items()),
        'partial_ghg_kg_co2e':sum(a*ghg[p] for p,a in shares_or_areas.items()),
    }


def generate_a8_crosscheck(config=None, *, temp_reference_c=None,
                           margin_tolerance_pct=0.):
    """Re-optimize under consistent assumptions; no fabricated NASA series."""
    cfg=load_case() if config is None else deepcopy(config)
    case=calculate_case(cfg)
    rows=_crop_records(cfg)
    if temp_reference_c is None:
        temp_reference_c=float(district_climate(cfg['district'])['Apr-Sep temperature, °C'])
    area=cfg['area_ha']
    baseline={r['product']:area*cfg['baseline_crop_shares'][r['code']] for r in rows}
    shares={k:100*v/area for k,v in baseline.items()}
    normal_w,normal_m,normal_e=_water_margin_ghg_by_product(rows,cfg)
    common={
        'district':cfg['district'],'area_ha':area,
        'profile':cfg['economic_objective']['profile'],
        'max_share':cfg['economic_objective']['max_crop_share'],
        'n_crops':cfg['economic_objective']['n_crops'],
        'irrigation_type':cfg['irrigation_type'],
        'objective_mode':'sustainable',
        'economic_weight':cfg['economic_objective']['economic_weight'],
        'baseline_share_by_product':shares,
        'sustainable_max_margin_decline_pct':float(margin_tolerance_pct),
        'available_water_m3':cfg['normal_water_budget_m3'],
    }
    current_reference_carbon_cap=_structure_totals(baseline,normal_w,normal_m,normal_e)['partial_ghg_kg_co2e']
    def solve(w,m,e, *, climate=None, reference_ghg_cap=None):
        allocation,summary=optimize_structure(**common,
            climate=climate,
            economic_margin_by_product=m,
            ghg_kg_co2e_by_product=e,
            sustainable_absolute_ghg_cap_kg=reference_ghg_cap,
            water_requirement_by_product=w,
            water_requirement_evidence='Documented QUNAR base water references or explicit Hargreaves temperature-term sensitivity; field delivery; not statutory change',
            water_requirement_confirmed=True,
            water_constraint_definition='field_delivery')
        if allocation.empty:
            return {'status':summary.get('solver_status','no_feasible_allocation'),
                    'baseline':_structure_totals(baseline,w,m,e), 'areas_ha':None,
                    'optimized':None}
        areas={str(x['product']):float(x['area_ha']) for _,x in allocation.iterrows()}
        outcome=_structure_totals(areas,w,m,e)
        if not isclose(outcome['water_field_delivery_m3'],float(summary['modelled_total_water_m3']),abs_tol=1e-5):
            raise AssertionError('Independent scenario water differs from constrained optimizer')
        if not isclose(outcome['contribution_margin_kzt'],float(summary['optimized_contribution_margin_kzt']),abs_tol=1e-5):
            raise AssertionError('Independent scenario margin differs from constrained optimizer')
        return {'status':summary['solver_status'], 'baseline':_structure_totals(baseline,w,m,e),
                'areas_ha':areas,'optimized':outcome,'constraints':summary.get('sustainable_comparison')}

    current=solve(normal_w,normal_m,normal_e)
    scenarios={}
    climate_base=district_climate(cfg['district']) or {}
    for name in ('SSP2-4.5','SSP5-8.5'):
        climate_s=load_scenario(CMIP6_DIR,name)
        multiplier=temperature_only_water_sensitivity(1.,temp_reference_c,
            climate_s.temperature_change_c).temperature_term_multiplier
        w,m,e=_water_margin_ghg_by_product(rows,cfg,multiplier)
        climate_future=dict(climate_base)
        if climate_future.get('Apr-Sep temperature, °C') is not None:
            climate_future['Apr-Sep temperature, °C']+=climate_s.temperature_change_c
        if climate_future.get('Apr-Sep precipitation, mm') is not None:
            climate_future['Apr-Sep precipitation, mm']*=1+climate_s.precipitation_change_pct/100
        result=solve(w,m,e,climate=climate_future)
        strict_reference=solve(w,m,e,climate=climate_future,
                               reference_ghg_cap=current_reference_carbon_cap)
        fixed_current=( _structure_totals(current['areas_ha'],w,m,e)
                       if current['areas_ha'] else None)
        scenarios[name]={
            'temperature_delta_c':climate_s.temperature_change_c,
            'precipitation_delta_pct':climate_s.precipitation_change_pct,
            'water_multiplier':multiplier,
            'method':'Hargreaves (T+17.8) temperature TERM only; constant diurnal range, radiation, no crop ETc or effective-precipitation recalculation',
            'fixed_current_compromise':fixed_current,
            'reoptimized':result,
            'reoptimized_with_absolute_present_carbon_cap':strict_reference,
        }
    return {
        'case_id':case['case_id'], 'input_sha256':case['input_sha256'],
        'technical_assumptions':cfg['technical_assumptions'],
        'temperature_reference_c':temp_reference_c,
        'sustainable_margin_tolerance_pct':float(margin_tolerance_pct),
        'ordinary_economic_optimum':case['normal'],
        'sustainable_current':current,
        'stress':case['stress'],
        'climate_scenarios':scenarios,
        'status':'hypothetical scenario; proxy future water, not FAO-56 or observed field savings',
        'limitations':[
            'Prices official BNS 2025, farm costs/tariffs/N/diesel and input shares hypothetical.',
            'Partial GHG from N2O, diesel, irrigation electricity only.',
            'Soil/transport losses/return flows not included in reference irrigation norm.',
            'SSP impact: temperature-term proxy, adjusted pump energy/cost/GHG, re-optimized climate scores; unchanged crop yield is NOT validated.',
            'Own-pump scenario uses explicitly hypothesized 25 m head, 65% total pump efficiency and E=rho*g*head/(efficiency*3.6e6) kWh/m3; not a measured farm pump. Grid generation-average 2025 Ember 0.813 kg CO2/kWh, not an official emission factor or full life cycle.',
        ],
    }
