"""Reproducible *illustrative* A8 100-ha farm case, not an observed outcome.

Sources are explicit: 2025 BNS producer prices, trailing three calendar-year
Maktaaral district crop yields and QUNAR's 2025 irrigation reference. Every
other economic/activity assumption comes from an explicitly labelled JSON
input. Never conflate an infeasible stressed baseline with a feasible choice.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import isclose, isfinite
from pathlib import Path

from .carbon_scenarios import DEFAULT_N2O_N_PER_N, DEFAULT_N2O_GWP100
from .clrem import registry
from .ghg_structure import compare_crop_structures, structure_inventory
from .optimizer import optimize_structure
from .producer_prices import reference_producer_price
from .water_norms import default_water_requirement
from .yield_reference import trailing_three_year_yield

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = PROJECT_ROOT / 'examples' / 'a8_maktaaral_100ha_inputs.json'
PANEL = PROJECT_ROOT / 'data' / 'analytical_panel.csv'


def _amount(value, label, *, allow_zero=False):
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} must be numeric') from None
    if not isfinite(out) or (out < 0 if allow_zero else out <= 0):
        raise ValueError(f'{label} must be finite and {">=" if allow_zero else ">"} 0')
    return out


def _validated_inputs(inputs):
    if inputs.get('district') != 'Maktaaral District':
        raise ValueError('This documented example applies to Maktaaral District')
    if inputs.get('accounting_period') != 'apr_sep':
        raise ValueError('Consistent Apr-Sep activity accounting is required')
    if inputs.get('irrigation_type') != 'furrow' or inputs.get('water_boundary') != 'field_delivery':
        raise ValueError('This benchmark uses furrow, field-delivery reference norms')
    area = _amount(inputs['area_ha'], 'area_ha')
    budget = _amount(inputs['normal_water_budget_m3'], 'normal_water_budget_m3')
    opt = inputs['economic_objective']
    n = int(opt['n_crops']); cap = _amount(opt['max_crop_share'], 'max_crop_share')
    if not 0 < cap <= 1 or n < 2 or n*cap < 1:
        raise ValueError('Invalid land-allocation cap/count')
    shares = inputs['baseline_crop_shares']
    if set(shares) != set(inputs['crop_activities']) or len(shares) != n:
        raise ValueError('Baseline and activity crops must match intended optimizer alternatives')
    if any(_amount(v, 'baseline_share') <= 0 for v in shares.values()) or not isclose(sum(shares.values()),1.0,abs_tol=1e-9):
        raise ValueError('Baseline shares must add to one')
    for crop, vals in inputs['crop_activities'].items():
        for k in ('other_variable_cost_kzt_ha','nitrogen_kg_ha','diesel_litres_ha'):
            if k not in vals:
                raise ValueError(f'Missing {k} for {crop}')
            _amount(vals[k], f'{crop}.{k}', allow_zero=k!='other_variable_cost_kzt_ha')
    for k in ('pump_electricity_kwh_per_m3_field_delivery','water_tariff_kzt_per_m3_field_delivery',
              'electricity_tariff_kzt_per_kwh','grid_kg_co2e_per_kwh',
              'diesel_kg_co2_per_litre','n2o_n_kg_per_kg_n','n2o_gwp100'):
        _amount(inputs['technical_assumptions'][k], k, allow_zero=False)
    # Structure-inventory deliberately fixes the same IPCC factor basis across
    # scenarios; reject config overrides that its API cannot actually apply.
    if not isclose(float(inputs['technical_assumptions']['n2o_n_kg_per_kg_n']), DEFAULT_N2O_N_PER_N, abs_tol=1e-12):
        raise ValueError('This build fixes the direct-N2O emission factor at its documented default')
    if not isclose(float(inputs['technical_assumptions']['n2o_gwp100']), DEFAULT_N2O_GWP100, abs_tol=1e-9):
        raise ValueError('This build fixes the N2O GWP100 at its documented default')
    stress = inputs['stress']
    for key in ('water_budget_change_pct','yield_change_pct','cost_change_pct'):
        v = float(stress[key]);
        if not isfinite(v) or v <= -100:
            raise ValueError(f'Invalid stress {key}')
    if stress['water_budget_change_pct'] >= 0 or stress['yield_change_pct'] >= 0 or stress['cost_change_pct'] <= 0:
        raise ValueError('A8 stress must lower water/yields and raise costs')
    if int(inputs['assessment_year']) != int(inputs['price_reference_year']) + 1:
        raise ValueError('Example requires previous-year prices to avoid future leakage')
    return area, budget


def _crop_records(config):
    t = config['technical_assumptions']
    ppy = int(config['price_reference_year']); ay = int(config['assessment_year'])
    district = config['district']; reg = registry()
    rows = []
    for code in config['baseline_crop_shares']:
        match = reg[reg['Code'].astype(str).eq(code)]
        if len(match) != 1 or not isinstance(match.iloc[0]['CLREM_product'],str):
            raise ValueError(f'Crop {code} not uniquely eligible for optimization')
        product = str(match.iloc[0]['CLREM_product'])
        price = reference_producer_price(code, as_of_year=ppy)
        y = trailing_three_year_yield(PANEL,district,code,ay)
        w = default_water_requirement(district,code,'furrow')
        if price is None or price.year != ppy or y.value_c_ha is None or len(y.years)!=3:
            raise ValueError(f'No complete, same-period official benchmark for {code}')
        if not w.source_tier == 'direct' or w.norm_crop is None or w.m3_ha <= 0:
            raise ValueError(f'No direct zone crop irrigation reference for {code}')
        other = _amount(config['crop_activities'][code]['other_variable_cost_kzt_ha'],f'{code} other costs')
        pump_kwh_ha = w.m3_ha*float(t['pump_electricity_kwh_per_m3_field_delivery'])
        water_cost = w.m3_ha*float(t['water_tariff_kzt_per_m3_field_delivery'])
        energy_cost = pump_kwh_ha*float(t['electricity_tariff_kzt_per_kwh'])
        base_revenue = (y.value_c_ha/10.0)*price.price_kzt_t
        rows.append({'code':code,'product':product,'yield_c_ha':y.value_c_ha,
          'yield_years':list(y.years),'price_kzt_t':price.price_kzt_t,'price_source':price.source_label,
          'other_cost_kzt_ha':other,'water_m3_ha':float(w.m3_ha),
          'water_reference':w.source_label,'water_source_tier':w.source_tier,
          'pump_electricity_kwh_ha':pump_kwh_ha,
          'base_revenue_kzt_ha':base_revenue,'base_water_cost_kzt_ha':water_cost,
          'base_energy_cost_kzt_ha':energy_cost,
          'base_total_variable_cost_kzt_ha':other+water_cost+energy_cost,
          'base_margin_kzt_ha':base_revenue-other-water_cost-energy_cost})
    return rows


def _economics(rows, stress: dict|None):
    yield_multiplier=1+float(stress['yield_change_pct'])/100 if stress else 1.0
    cost_multiplier=1+float(stress['cost_change_pct'])/100 if stress else 1.0
    result={}
    for r in rows:
        revenue=r['base_revenue_kzt_ha']*yield_multiplier
        total_cost=r['base_total_variable_cost_kzt_ha']*cost_multiplier
        result[r['product']]={'revenue_kzt_ha':revenue,'variable_cost_kzt_ha':total_cost,
                              'contribution_margin_kzt_ha':revenue-total_cost}
    return result


def _aggregate(areas, rows, econ, config):
    by_product={r['product']:r for r in rows}
    if set(areas)!=set(by_product):
        raise ValueError('All comparison structures require identical crop coverage')
    t=config['technical_assumptions']; totals={'area_ha':sum(areas.values()),'water_field_delivery_m3':0.0,
       'pump_energy_kwh':0.0,'revenue_kzt':0.0,'variable_cost_kzt':0.0,'contribution_margin_kzt':0.0}
    activity={}
    for product,ha in areas.items():
        r=by_product[product]; d=econ[product]
        totals['water_field_delivery_m3']+=ha*r['water_m3_ha']
        totals['pump_energy_kwh']+=ha*r['pump_electricity_kwh_ha']
        for k, item in [('revenue_kzt','revenue_kzt_ha'),('variable_cost_kzt','variable_cost_kzt_ha'),
                        ('contribution_margin_kzt','contribution_margin_kzt_ha')]:
            totals[k]+=ha*d[item]
        a=config['crop_activities'][r['code']]
        activity[product]={'nitrogen_kg_ha':float(a['nitrogen_kg_ha']),
            'diesel_litres_ha':float(a['diesel_litres_ha']),
            'electricity_kwh_ha':r['pump_electricity_kwh_ha']}
    inv=structure_inventory(areas,activity,grid_factor=float(t['grid_kg_co2e_per_kwh']),
        accounting_period='apr_sep',diesel_factor=float(t['diesel_kg_co2_per_litre']),
        evidence='Explicitly hypothetical activities in a8_maktaaral_100ha_inputs.json',confirmed=True)
    totals['partial_ghg_kg_co2e']=inv['inventory'].known_total_kg_co2e
    totals['partial_ghg_components_kg_co2e']=inv['inventory'].components
    totals['ghg_activity_total']=inv['activities_total']
    return totals,activity


def _allocation_to_areas(df):
    return {str(r['product']):float(r['area_ha']) for _,r in df.iterrows()}


def calculate_case(config: dict) -> dict:
    area, normal_budget = _validated_inputs(config)
    rows=_crop_records(config)
    baseline_areas={r['product']:area*config['baseline_crop_shares'][r['code']] for r in rows}
    normal_economics=_economics(rows,None)
    stressed_economics=_economics(rows,config['stress'])
    stress_budget=normal_budget*(1+config['stress']['water_budget_change_pct']/100)
    normal_margins={p:d['contribution_margin_kzt_ha'] for p,d in normal_economics.items()}
    stress_margins={p:d['contribution_margin_kzt_ha'] for p,d in stressed_economics.items()}
    opt_settings=config['economic_objective']
    common=dict(district=config['district'],area_ha=area,profile=opt_settings['profile'],
        max_share=opt_settings['max_crop_share'],n_crops=opt_settings['n_crops'],
        irrigation_type=config['irrigation_type'],economic_weight=opt_settings['economic_weight'],
        objective_mode=opt_settings['objective_mode'],
        baseline_share_by_product={r['product']:config['baseline_crop_shares'][r['code']]*100 for r in rows})
    normal_alloc, normal_summary=optimize_structure(**common,available_water_m3=normal_budget,
        economic_margin_by_product=normal_margins)
    stress_alloc, stress_summary=optimize_structure(**common,available_water_m3=stress_budget,
        economic_margin_by_product=stress_margins)
    if normal_alloc.empty or stress_alloc.empty:
        raise ValueError('No feasible allocation found for one or both stated A8 scenarios')
    normal_areas=_allocation_to_areas(normal_alloc)
    stress_areas=_allocation_to_areas(stress_alloc)
    b,bact=_aggregate(baseline_areas,rows,normal_economics,config)
    n,nact=_aggregate(normal_areas,rows,normal_economics,config)
    bs,bsact=_aggregate(baseline_areas,rows,stressed_economics,config)
    ss,ssact=_aggregate(stress_areas,rows,stressed_economics,config)
    # Water-balance comparisons use one common period and one field-delivery boundary.
    for obj,budget,feasible in [(b,normal_budget,True),(n,normal_budget,True),
                                (bs,stress_budget,False),(ss,stress_budget,True)]:
        obj['water_budget_m3']=budget
        obj['water_feasible']=obj['water_field_delivery_m3']<=budget+1e-6
        if obj['water_feasible'] != feasible:
            raise ValueError('The stress feasibility assumption is inconsistent with the stated inputs')
    for frame, opt_sum in [(n,normal_summary),(ss,stress_summary)]:
        if not isclose(frame['water_field_delivery_m3'],opt_sum['modelled_total_water_m3'],abs_tol=1e-6):
            raise AssertionError('Independent water result differs from optimizer water accounting')
        if not isclose(frame['contribution_margin_kzt'],opt_sum['optimized_contribution_margin_kzt'],abs_tol=1e-5):
            raise AssertionError('Independent economics differs from optimizer economic result')
    t=config['technical_assumptions']
    comparison_normal=compare_crop_structures(baseline_areas=baseline_areas,proposed_areas=normal_areas,
        baseline_activity_per_ha=bact,proposed_activity_per_ha=nact,
        grid_factor=t['grid_kg_co2e_per_kwh'],diesel_factor=t['diesel_kg_co2_per_litre'],
        evidence='Hypothetical A8 100-ha case; equal reporting period and factors',confirmed=True)
    comparison_stress=compare_crop_structures(baseline_areas=baseline_areas,proposed_areas=stress_areas,
        baseline_activity_per_ha=bsact,proposed_activity_per_ha=ssact,
        grid_factor=t['grid_kg_co2e_per_kwh'],diesel_factor=t['diesel_kg_co2_per_litre'],
        evidence='Hypothetical A8 stressed baseline is water-infeasible; comparison is counterfactual',confirmed=True)
    def areas_to_codes(areas):
        by_p={r['product']:r['code'] for r in rows}
        return {by_p[k]:v for k,v in areas.items()}
    config_sha256=hashlib.sha256(json.dumps(config,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
    return {
      'case_id':'A8_MAKTAARAL_100HA_2026', 'input_sha256':config_sha256,
      'case_type':'illustrative_hypothetical_not_observed_or_policy_impact',
      'area_ha':area,'district':config['district'],'assessment_year':config['assessment_year'],
      'accounting_period':'Apr-Sep','water_boundary':'field delivery; not water-source abstraction',
      'inputs':config,'crop_reference_rows':rows,
      'normal':{'water_budget_m3':normal_budget,'baseline_areas_ha':areas_to_codes(baseline_areas),
                'optimized_areas_ha':areas_to_codes(normal_areas),'baseline':b,'optimized':n,
                'optimizer_status':normal_summary['solver_status'],
                'margin_change_same_conditions_kzt':n['contribution_margin_kzt']-b['contribution_margin_kzt'],
                'water_change_same_conditions_m3':n['water_field_delivery_m3']-b['water_field_delivery_m3'],
                'ghg_difference':comparison_normal},
      'stress':{'water_budget_m3':stress_budget,'baseline_areas_ha':areas_to_codes(baseline_areas),
                'optimized_areas_ha':areas_to_codes(stress_areas),
                'unchanged_baseline_infeasible':not bs['water_feasible'],
                'baseline_counterfactual_water_shortfall_m3':bs['water_field_delivery_m3']-stress_budget,
                'baseline_counterfactual':bs,'optimized':ss,
                'optimizer_status':stress_summary['solver_status'],
                'hypothetical_margin_difference_vs_infeasible_baseline_kzt':ss['contribution_margin_kzt']-bs['contribution_margin_kzt'],
                'field_delivery_change_vs_infeasible_baseline_m3':ss['water_field_delivery_m3']-bs['water_field_delivery_m3'],
                'ghg_difference_vs_infeasible_baseline':comparison_stress,
                'interpretation':'Counterfactual infeasible baseline: not an achievable margin uplift or a field-measured water/GHG saving'},
      'provenance':'Prices: BNS 2025; district yields: 2023–2025; crop water reference: Order 108-NQ, QUNAR implementation; production costs, tariffs, energy/GHG activities, baseline and budgets: explicit hypothetical assumptions. All output is an illustrative scenario.',
      'excluded':'No observed farm profit, no verified farm water quota, no actual basin savings, no out-of-sample yield forecast, no realized emissions reductions, no full life-cycle GHG or capital expenditure.'
    }


def load_case(path=DEFAULT_CASE):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def report_markdown(r:dict) -> str:
    normal=r['normal']; stress=r['stress']; crops=r['crop_reference_rows']
    def num(v,d=0): return f'{v:,.{d}f}'.replace(',',' ')
    lines=[
      '# A8 — Maktaaral district, 100 ha: reproducible illustrative scenario',
      '', '**Status: hypothetical counterfactual, NOT verified farm adoption or actual savings.**',
      f"Input SHA-256: `{r['input_sha256']}`.", '',
      '## Input sources and assumptions',
      '', 'BNS Turkestan producer prices **2025**, district crop yields averaged over **2023–2025**,',
      'irrigation norms from QŪNAR Order No. 108-NQ **2025**, surface irrigation (field delivery).',
      'The 100-ha baseline, 750,000 m³ water budget, variable costs, tariffs, pumping intensity,',
      'fertilizer N, diesel, and grid emission factor are **illustrative assumptions**, NOT observed regional means.',
      'Neither calculated contribution margins nor partial emissions are verified impacts.',
      '', '| Crop | Yield, centners/ha | BNS 2025 price, KZT/t | Water, m³/ha | Assumed other costs, KZT/ha |',
      '|---|---:|---:|---:|---:|'
    ]
    for cr in crops:
        lines.append(f"| {cr['code']} | {num(cr['yield_c_ha'],2)} | {num(cr['price_kzt_t'])} | {num(cr['water_m3_ha'])} | {num(cr['other_cost_kzt_ha'])} |")
    lines+=['','## Allocations and results','','| Parameter | Normal baseline | Normal optimized | Stress baseline (infeasible) | Stress optimized |',
      '|---|---:|---:|---:|---:|']
    parts=[normal['baseline'],normal['optimized'],stress['baseline_counterfactual'],stress['optimized']]
    for k,label,unit in [('water_budget_m3','Water limit','m³'),('water_field_delivery_m3','Irrigation delivery','m³'),
       ('pump_energy_kwh','Pumping electricity','kWh'),('revenue_kzt','Revenue','KZT'),
       ('variable_cost_kzt','Variable costs','KZT'),('contribution_margin_kzt','Contribution margin','KZT'),
       ('partial_ghg_kg_co2e','Partial GHG','kg CO₂e')]:
       lines.append('| '+label+' ('+unit+') | '+' | '.join(num(x[k],1 if k=='partial_ghg_kg_co2e' else 0) for x in parts)+' |')
    lines.append('| Water feasible | '+' | '.join('Yes' if x['water_feasible'] else '**No**' for x in parts)+' |')
    lines+=['','| Crop share (ha) | Normal baseline | Normal optimized | Stress baseline | Stress optimized |',
      '|---|---:|---:|---:|---:|']
    for code in [x['code'] for x in crops]:
        lines.append('| '+code+' | '+' | '.join(num(areas.get(code,0),2) for areas in
          [normal['baseline_areas_ha'],normal['optimized_areas_ha'],stress['baseline_areas_ha'],stress['optimized_areas_ha']])+' |')
    lines+=['','## Interpretation',
      '',f"- In **normal water conditions**, both structures are feasible; scenario margin difference is {num(normal['margin_change_same_conditions_kzt'])} KZT and field-delivery water change is {num(normal['water_change_same_conditions_m3'])} m³.",
      f"- Stress: water limit falls by 20% to {num(stress['water_budget_m3'])} m³; yields fall by 10%; **all variable costs**, including water and electricity, increase by 10%.",
      f"- Unchanged stressed baseline exceeds its limit by {num(stress['baseline_counterfactual_water_shortfall_m3'])} m³. Its margin and GHG numbers are **infeasible counterfactuals**, not an achievable farm outcome.",
      f"- Stress optimized allocation meets the limit; irrigation field delivery differs from the infeasible baseline by {num(stress['field_delivery_change_vs_infeasible_baseline_m3'])} m³, and partial GHG difference is {num(stress['ghg_difference_vs_infeasible_baseline']['change_kgco2e'],1)} kg CO₂e. Both comparisons are **counterfactual vs infeasible baseline**, NOT achieved water or GHG savings.",
      '- Crop mix changes may also alter pumping electricity and partial CO₂e; the result is not a measurement of emissions mitigation.',
      '- The 24.7m / 23.8m KZT claims in earlier dissertation drafts have **not** been reproduced by this separate case and must not be substituted.',
      '- Price reference, costs, yield and climate are not a validated 2026 forecast; stress effects are imposed, **NOT** inferred from CMIP6 or NASA data.',
      '', '## Traceability', '', f"{r['provenance']}", '',f"Excluded: {r['excluded']}",'' ]
    return '\n'.join(lines)
