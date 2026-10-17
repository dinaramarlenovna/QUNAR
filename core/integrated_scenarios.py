"""Integrated counterfactual farm resource / partial GHG / economic scenarios.

This is a *decision support* calculator, not a verified causal treatment-effect
estimator. All baseline/proposal values refer to the same farm, product, and
production period. Missing is never interpreted as zero. Irrigation savings
at field are not equated with catchment depletion reductions.

References: FAO Irrigation Efficiencies (Table 8), FAO cb3844en real water
savings, IPCC 2006 Guidelines + 2019 Refinement Vol 4 (emissions).
"""
from __future__ import annotations
from .green_guard import evaluate_green_guard
from math import isfinite

FAO_IRRIGATION = 'https://www.fao.org/4/t7202e/t7202e08.htm'
FAO_WATER_ACCOUNTING = 'https://www.fao.org/documents/card/en/c/cb3844en'
IPCC_AFOLU = 'https://www.ipcc-tfi.iges.or.jp/public/2019rf/index.html'
FIELD_ETA = {'furrow': .60, 'sprinkler': .75, 'drip': .90}
N2O_N_FRACTION = 0.01
GWP_N2O = 273.0
GWP_BIOGENIC_CH4 = 27.0
DIESEL_KGCO2_L = 2.68  # operational illustrative factor; not verified for KZ fuel composition


def num(value, name, *, required=False, maximum=None):
    if value is None or value == '':
        if required:
            raise ValueError(f'Missing {name}')
        return None
    try:
        v = float(value)
    except (TypeError, ValueError) as ex:
        raise ValueError(f'Invalid {name}') from ex
    if not isfinite(v) or v < 0 or (maximum is not None and v > maximum):
        raise ValueError(f'Invalid {name}')
    return v


def irrigation_reference(*, net_m3_ha, area_ha, before_method, after_method,
                         conveyance_efficiency=None, before_efficiency=None,
                         after_efficiency=None, water_reference='FAO-56 net crop demand',
                         evidence='FAO reference efficiencies'):
    """Reference *field* delivery. Withdrawal is optional; catchment saving absent.

    Net irrigation must be independently obtained (FAO-56 or a stated inference),
    not an official gross field irrigation norm treated as net.
    """
    net = num(net_m3_ha, 'net irrigation', required=True)
    area = num(area_ha, 'area', required=True)
    if area <= 0:
        raise ValueError('Area must be positive')
    if before_method not in FIELD_ETA and before_method != 'mixed':
        raise ValueError('Unknown baseline irrigation technique')
    if after_method not in FIELD_ETA and after_method != 'mixed':
        raise ValueError('Unknown proposed irrigation technique')
    eta_b = (num(before_efficiency,'baseline application efficiency',required=True,maximum=1.)
             if before_method == 'mixed' else FIELD_ETA[before_method])
    eta_p = (num(after_efficiency,'proposed application efficiency',required=True,maximum=1.)
             if after_method == 'mixed' else FIELD_ETA[after_method])
    if eta_b <= 0 or eta_p <= 0:
        raise ValueError('Irrigation application efficiency must be positive')
    if not str(water_reference).strip() or not str(evidence).strip():
        raise ValueError('Water calculation provenance required')
    b = net * area / eta_b
    p = net * area / eta_p
    ec = num(conveyance_efficiency, 'conveyance efficiency', maximum=1.0)
    if ec is not None and ec <= 0:
        raise ValueError('Conveyance efficiency must be positive')
    return {'baseline_field_m3':b, 'scenario_field_m3':p,
            'baseline_withdrawal_m3':b/ec if ec is not None else None,
            'scenario_withdrawal_m3':p/ec if ec is not None else None,
            'boundary':'source_withdrawal' if ec is not None else 'field_delivery',
            'evidence':f'{water_reference}; {evidence}; baseline eta={eta_b:.3f}; proposed eta={eta_p:.3f}',
            'real_basin_saving_m3':None,
            'note':'FAO indicative application efficiency, not observed actual conservation.'}


def linked_pump_electricity(*, baseline_total_kwh=None, baseline_water_m3, scenario_water_m3,
                            before_kwh_m3, after_kwh_m3, other_energy_reduction_pct=0.0):
    """Avoid stacking a pumping proxy on top of observed total electricity.

    When measured total is supplied, infer non-pumping remainder from measured
    total minus the *explicitly modelled* pumping component. A contradiction
    must be fixed rather than clipped to zero.
    """
    bwater = num(baseline_water_m3,'baseline pumped water',required=True)
    pwater = num(scenario_water_m3,'scenario pumped water',required=True)
    kb = num(before_kwh_m3,'baseline pump intensity',required=True)
    kp = num(after_kwh_m3,'scenario pump intensity',required=True)
    pct = num(other_energy_reduction_pct,'other energy reduction',required=True,maximum=100)
    total = num(baseline_total_kwh,'observed total electricity')
    bp = bwater * kb
    pp = pwater * kp
    if total is None:
        return {'baseline_kwh':bp,'scenario_kwh':pp,'boundary':'pumping_only',
                'source':'pump electricity calculated from field water x intensity',
                'nonpump_kwh':None}
    rest = total-bp
    if rest < -1e-6:
        raise ValueError('Observed total electricity smaller than estimated pumping; revise pump intensity or input')
    rest = max(0.,rest)
    return {'baseline_kwh':total, 'scenario_kwh':pp+rest*(1-pct/100),
            'boundary':'farm_electricity_with_modelled_pump_split',
            'source':'observed electricity; pump split is a scenario assumption',
            'nonpump_kwh':rest}


def _pair(before, after, label):
    b=num(before,f'baseline {label}'); a=num(after,f'scenario {label}')
    if (b is None) != (a is None):
        raise ValueError(f'Matched baseline/after {label} required')
    return b,a


def compare_farm_scenario(*, farm_kind, period, evidence,
                          water_before_m3=None, water_after_m3=None, water_boundary='field_delivery',
                          electricity_before_kwh=None, electricity_after_kwh=None,
                          electricity_boundary='farm_total',
                          grid_fraction_before=1.0, grid_fraction_after=1.0,
                          grid_emission_kgco2e_kwh=None,
                          water_tariff_kzt_m3=None, electricity_tariff_kzt_kwh=None,
                          renewable_operating_kzt_kwh=None,
                          diesel_before_l=None, diesel_after_l=None, diesel_kzt_l=None,
                          diesel_in_other_cost=False,
                          n_before_kg=None, n_after_kg=None,
                          enteric_heads=None, enteric_ch4_before_kg_head_year=None,
                          enteric_ch4_after_kg_head_year=None, enteric_period_years=1.,
                          methane_change_evidence=None,
                          manure_ch4_before_kg_head_year=None, manure_ch4_after_kg_head_year=None,
                          manure_change_evidence=None, include_manure=False,
                          revenue_before_kzt=None, revenue_after_kzt=None,
                          other_cost_before_kzt=None, other_cost_after_kzt=None,
                          costs_complete=False, include_nitrogen=True, include_enteric=False,
                          extra_cost_after_kzt=0.0, extra_cost_before_kzt=0.0):
    """Comparison under one coherent activity boundary, without saving double counts.

    other_cost excludes water, electricity, diesel when diesel separately priced,
    and renewable operation. It includes any production inputs (incl fertiliser)
    not priced separately by this routine. Fertilizer kg N is GHG activity only.

    'margin' is only present when revenue, cost boundary and all *priced* active
    resource costs are complete. Otherwise a transparent operating-cost delta
    for known components is returned, but NOT a fabricated margin.
    """
    if farm_kind not in ('crop','livestock') or not str(period).strip() or not str(evidence).strip():
        raise ValueError('Document farm type, common period and assumptions')
    if water_boundary not in ('field_delivery','source_withdrawal','metered_total'):
        raise ValueError('Unknown water boundary')
    bw,pw=_pair(water_before_m3,water_after_m3,'water')
    be,pe=_pair(electricity_before_kwh,electricity_after_kwh,'electricity')
    bd,pd=_pair(diesel_before_l,diesel_after_l,'diesel')
    bn,pn=_pair(n_before_kg,n_after_kg,'N')
    br,pr=_pair(revenue_before_kzt,revenue_after_kzt,'revenue')
    bc,pc=_pair(other_cost_before_kzt,other_cost_after_kzt,'other costs')
    extb=num(extra_cost_before_kzt,'baseline additional costs',required=True)
    extp=num(extra_cost_after_kzt,'scenario additional costs',required=True)
    gf_b=num(grid_fraction_before,'baseline grid fraction',required=True,maximum=1.)
    gf_p=num(grid_fraction_after,'scenario grid fraction',required=True,maximum=1.)
    ef=num(grid_emission_kgco2e_kwh,'grid emission coefficient')
    wt=num(water_tariff_kzt_m3,'water tariff'); et=num(electricity_tariff_kzt_kwh,'electricity tariff')
    rt=num(renewable_operating_kzt_kwh,'renewable electricity operating cost')
    dt=num(diesel_kzt_l,'diesel price')
    if (gf_b < 1 or gf_p < 1) and be is not None and rt is None:
        # Do not assume renewables are costless (and thus create fictitious margin).
        renewables_price_unknown=True
    else:
        renewables_price_unknown=False
    if (include_enteric or include_manure) and farm_kind!='livestock':
        raise ValueError('Livestock methane belongs to livestock scenario')
    partial={}; missing=[]
    if be is not None:
        if ef is not None and ef > 0:
            partial['grid_electricity_kgco2e']=(be*gf_b*ef,pe*gf_p*ef)
        else:
            missing.append('grid_emission_factor')
    if bd is not None:
        partial['diesel_combustion_kgco2']=(bd*DIESEL_KGCO2_L,pd*DIESEL_KGCO2_L)
    if include_nitrogen and bn is not None:
        scale=N2O_N_FRACTION*44/28*GWP_N2O
        partial['direct_fertilizer_n2o_kgco2e']=(bn*scale,pn*scale)
    if include_enteric:
        h=num(enteric_heads,'herd size',required=True)
        y=num(enteric_period_years,'years of livestock emissions',required=True)
        eb,ep=_pair(enteric_ch4_before_kg_head_year,enteric_ch4_after_kg_head_year,'enteric methane coefficient')
        if h <= 0 or y <= 0 or y > 1:
            raise ValueError('Positive herd and period up to one year required')
        if eb is None or eb <= 0 or ep is None or ep <= 0:
            missing.append('enteric_methane_coefficient')
        elif abs(eb-ep)>1e-9 and not str(methane_change_evidence or '').strip():
            raise ValueError('A reduction in livestock methane factor requires stated source or scenario assumption')
        else:
            partial['enteric_methane_kgco2e']=(h*y*eb*GWP_BIOGENIC_CH4,
                                                 h*y*ep*GWP_BIOGENIC_CH4)
    if include_manure:
        h=num(enteric_heads,'herd size',required=True)
        y=num(enteric_period_years,'years of livestock emissions',required=True)
        mb,mp=_pair(manure_ch4_before_kg_head_year,manure_ch4_after_kg_head_year,
                    'manure methane coefficient')
        if h <= 0 or y <= 0 or y > 1:
            raise ValueError('Positive herd and period up to one year required')
        if mb is None or mb <= 0 or mp is None or mp <= 0:
            missing.append('manure_ch4_coefficient')
        elif abs(mb-mp)>1e-9 and not str(manure_change_evidence or '').strip():
            raise ValueError('Changing manure methane factor requires stated evidence/assumption')
        else:
            partial['manure_ch4_kgco2e']=(h*y*mb*GWP_BIOGENIC_CH4,h*y*mp*GWP_BIOGENIC_CH4)
    base_ghg=sum(a for a,_ in partial.values()) if partial else None
    next_ghg=sum(b for _,b in partial.values()) if partial else None
    cost_components={}
    if bw is not None:
        if wt is not None:
            cost_components['water_kzt']=(bw*wt,pw*wt)
        else: missing.append('water_tariff')
    if be is not None:
        if et is not None and not renewables_price_unknown:
            rt=0.0 if rt is None else rt
            cost_components['electricity_kzt']=(be*(gf_b*et+(1-gf_b)*rt),
                                                 pe*(gf_p*et+(1-gf_p)*rt))
        else: missing.append('electricity_or_renewable_tariff')
    if bd is not None:
        if diesel_in_other_cost:
            if bc is None: missing.append('other_costs_including_diesel')
        elif dt is not None: cost_components['diesel_kzt']=(bd*dt,pd*dt)
        else: missing.append('diesel_price')
    if bc is not None: cost_components['other_production_kzt']=(bc,pc)
    if extb or extp: cost_components['additional_scenario_kzt']=(extb,extp)
    cost_b=sum(a for a,_ in cost_components.values())
    cost_p=sum(b for _,b in cost_components.values())
    missing_costs = ((bw is not None and wt is None) or
                     (be is not None and (et is None or renewables_price_unknown)) or
                     (bd is not None and dt is None and not diesel_in_other_cost))
    margin_allowed = bool(costs_complete and br is not None and bc is not None and
                          not missing_costs and bw is not None and be is not None and
                          (bd is not None or diesel_kzt_l is None))
    mb=br-cost_b if margin_allowed else None
    mp=pr-cost_p if margin_allowed else None
    # Deterministic stress sensitivity, not a probabilistic confidence interval.
    stress_mb=(br*0.90-cost_b*1.10) if margin_allowed else None
    stress_mp=(pr*0.90-cost_p*1.10) if margin_allowed else None
    def change(b,a): return None if b is None else b-a
    green_guard = evaluate_green_guard(
        water_before_m3=bw, water_after_m3=pw,
        ghg_before_kgco2e=base_ghg, ghg_after_kgco2e=next_ghg,
        margin_before_kzt=mb, margin_after_kzt=mp, evidence=evidence,
        emissions_scope='partial N2O / diesel / electricity / optional livestock, as entered')
    return {'scope':f'{farm_kind}: {period}', 'evidence':str(evidence).strip(),
            'green_guard':green_guard,
            'water_boundary':water_boundary, 'electricity_boundary':electricity_boundary,
            'water_before_m3':bw,'water_after_m3':pw,'water_reduction_m3':change(bw,pw),
            'energy_before_kwh':be,'energy_after_kwh':pe,'energy_reduction_kwh':change(be,pe),
            'ghg_components_kgco2e':partial,'ghg_before_kgco2e':base_ghg,
            'ghg_after_kgco2e':next_ghg,'partial_ghg_reduction_kgco2e':change(base_ghg,next_ghg),
            'ghg_boundary':'partial inventoried components only, not full footprint',
            'known_cost_components_kzt':cost_components,'known_cost_reduction_kzt':cost_b-cost_p,
            'margin_before_kzt':mb,'margin_after_kzt':mp,'margin_increase_kzt':change(mp,mb) if mb is not None else None,
            'stress_margin_before_kzt':stress_mb,'stress_margin_after_kzt':stress_mp,
            'stress_margin_increase_kzt':change(stress_mp,stress_mb) if stress_mb is not None else None,
            'missing':tuple(dict.fromkeys(missing)),
            'warnings':[
                'Modeled reductions are conditional scenarios, not achieved observed effects.',
                'Water reduction at field/source is not proof of real basin water savings.',
                'Net energy change depends on pump electricity intensity, which may increase under pressurized drip.',
                'Electricity emissions refer only to grid electricity and exclude renewable lifecycle emissions.',
                'Livestock enteric methane changes only with an explicit factor and methodological justification.',
                'Contribution margin excludes any unmodelled investment or fixed costs; no investment payback is claimed.',
            ]}
