"""QŪNAR sixth mode: transparent ex-ante crop/livestock land-use comparisons.

This is scenario accounting, NOT a calibrated inter-sector conversion optimizer.
Resource basis: crop gross seasonal irrigation reference; cattle drinking water annual;
external feed's embedded resources are optional explicit inputs, not silently zero.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from .water_norms import default_water_requirement
from .livestock import reference_requirements
from .evidence_registry import (ENTERIC_CH4_ASIA_KG_HEAD_YEAR,
    N2O_EF1_GENERAL, N2O_MOLECULAR_RATIO, N2O_GWP100_AR6)

_GRID_CO2_KG_KWH = 0.813  # Ember 2025 generation CO2, NOT complete CO2e
_DIESEL_CO2_KG_L = 2.676492  # reference combustion, not lifecycle
_CH4_GWP100 = 27.0  # declared scenario choice, not carbon-neutrality accounting


def _num(value: Any, label: str, *, allow_none: bool = False) -> float | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError(f"Missing required input: {label}")
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid value: {label}") from None
    if not isfinite(n) or n < 0:
        raise ValueError(f"Non-finite or negative value: {label}")
    return n


def compare_mixed_farm(
    *, district: str, crops: list[dict], pasture_ha: float,
    crop_water_limit_m3: float | None, source_crop: str,
    alternatives: list[dict],  # [{label,convert_ha,heads,meat_t_year}]
    crop_water_price: float, electricity_price: float, diesel_price: float,
    cattle_price_kzt_t: float, cattle_other_cost_kzt_head: float,
    dry_fodder_yield_t_ha_year: float | None,
    purchased_feed_price_kzt_t: float | None,
    purchase_feed_allowed: bool,
    allowable_lu_ha: float | None,
    legal_conversion_allowed: bool, pasture_suitable: bool,
    livestock_grid_kwh_per_head_year: float = 0, livestock_diesel_l_per_head_year: float = 0,
    feed_water_footprint_m3_t: float | None = None,
    feed_ghg_footprint_kg_co2e_t: float | None = None,
    manure_ghg_kg_co2e_head_year: float | None = None,
    livestock_water_limit_m3_year: float | None = None,
    gwp_ch4: float = _CH4_GWP100,
) -> dict:
    if not crops or len(crops) > 15:
        raise ValueError("Provide between 1 and 15 crop rows")
    land_pasture = _num(pasture_ha, 'pasture_ha')
    limit = _num(crop_water_limit_m3, 'crop_water_limit_m3', allow_none=True)
    water_unit = _num(crop_water_price, 'crop_water_price')
    power_unit = _num(electricity_price, 'electricity_price')
    diesel_unit = _num(diesel_price, 'diesel_price')
    meat_unit = _num(cattle_price_kzt_t, 'cattle_price_kzt_t')
    cattle_cost = _num(cattle_other_cost_kzt_head, 'cattle_other_cost_kzt_head')
    pasture_yield = _num(dry_fodder_yield_t_ha_year, 'dry_fodder_yield', allow_none=True)
    feed_price = _num(purchased_feed_price_kzt_t, 'purchased_feed_price', allow_none=True)
    lu_cap = _num(allowable_lu_ha, 'allowable_lu_ha', allow_none=True)
    external_water_factor = _num(feed_water_footprint_m3_t, 'feed_water_footprint', allow_none=True)
    external_ghg_factor = _num(feed_ghg_footprint_kg_co2e_t, 'feed_ghg_footprint', allow_none=True)
    manure_factor = _num(manure_ghg_kg_co2e_head_year, 'manure_ghg', allow_none=True)
    herd_power = _num(livestock_grid_kwh_per_head_year, 'livestock_grid_kwh_per_head_year')
    herd_diesel = _num(livestock_diesel_l_per_head_year, 'livestock_diesel_l_per_head_year')
    herd_water_limit = _num(livestock_water_limit_m3_year, 'livestock_water_limit_m3_year', allow_none=True)
    methane_gwp = _num(gwp_ch4, 'gwp_ch4')
    if pasture_yield is None and any(float(a.get('heads',0)) > 0 for a in alternatives):
        # Missing pasture forage yield is a defensible unknown, not automatic zero supply.
        pass
    allowed_crop_codes = set(__import__('core.water_norms', fromlist=['CROP_TO_NORM']).CROP_TO_NORM)
    norm_rows = []
    used = set()
    for row in crops:
        code = str(row.get('crop',''))
        if code not in allowed_crop_codes or code in used:
            raise ValueError(f"Unknown/duplicate crop: {code}")
        used.add(code)
        area = _num(row.get('area_ha'),f'{code} area')
        if area <= 0:
            raise ValueError(f'{code}: crop area must be positive')
        yy = _num(row.get('yield_c_ha'),f'{code} yield')
        pp = _num(row.get('price_kzt_t'),f'{code} price')
        cc = _num(row.get('other_cost_kzt_ha'),f'{code} cost')
        ep = _num(row.get('grid_kwh_ha'),f'{code} electricity')
        dd = _num(row.get('diesel_l_ha'),f'{code} diesel')
        nn = _num(row.get('nitrogen_kg_n_ha'),f'{code} N')
        water_ref = default_water_requirement(district,code,'furrow')
        norm_rows.append({**row, 'crop':code,'area_ha':area,
            'yield_c_ha':yy,'price_kzt_t':pp,'other_cost_kzt_ha':cc,
            'grid_kwh_ha':ep,'diesel_l_ha':dd,'nitrogen_kg_n_ha':nn,
            'water_m3_ha':water_ref.m3_ha,
            'water_reference':water_ref.source_label,
            'norm_tier':water_ref.source_tier})
    if source_crop not in used:
        raise ValueError('Conversion crop not present in the baseline')
    total_crop_ha = sum(r['area_ha'] for r in norm_rows)
    total_farm_ha = total_crop_ha+land_pasture
    conversion_crop_area = next(r['area_ha'] for r in norm_rows if r['crop']==source_crop)
    nitrogen_ghg_kg_per_kg = N2O_EF1_GENERAL*N2O_MOLECULAR_RATIO*N2O_GWP100_AR6

    def calc_one(a):
        label = str(a.get('label') or '')
        convert = _num(a.get('convert_ha'),f'{label} conversion')
        heads = _num(a.get('heads'),f'{label} heads')
        product = _num(a.get('meat_t_year'),f'{label} meat')
        if convert > conversion_crop_area + 1e-6:
            raise ValueError('Conversion exceeds available area of selected crop')
        if convert > 0 and heads == 0 and product > 0:
            raise ValueError('Meat production entered without cattle')
        if heads == 0 and product > 0:
            raise ValueError('Positive meat output with zero herd')
        crop_result = []
        for r in norm_rows:
            area = r['area_ha']-(convert if r['crop']==source_crop else 0)
            if area < -1e-8:
                raise ValueError('Negative remaining crop area')
            water = area*r['water_m3_ha']
            revenue = area*r['yield_c_ha']/10.0*r['price_kzt_t']
            cost = area*(r['other_cost_kzt_ha'] + r['grid_kwh_ha']*power_unit + r['diesel_l_ha']*diesel_unit)+water*water_unit
            emissions = area*(r['grid_kwh_ha']*_GRID_CO2_KG_KWH + r['diesel_l_ha']*_DIESEL_CO2_KG_L + r['nitrogen_kg_n_ha']*nitrogen_ghg_kg_per_kg)
            crop_result.append({'crop':r['crop'],'area_ha':round(max(0,area),5),'water_m3':water,
                                'revenue_kzt':revenue,'cost_kzt':cost,'margin_kzt':revenue-cost,
                                'partial_ghg_kg_co2e':emissions,'norm_m3_ha':r['water_m3_ha']})
        crop_water=sum(r['water_m3'] for r in crop_result)
        crop_margin=sum(r['margin_kzt'] for r in crop_result)
        crop_ghg=sum(r['partial_ghg_kg_co2e'] for r in crop_result)
        current_pasture=land_pasture+convert
        livestock_requirements=reference_requirements('Cattle',heads,25.0) if heads>0 else {}
        drinking=livestock_requirements.get('reference_water_m3_year') or 0.0
        feed_need=livestock_requirements.get('reference_feed_dm_t_year') or 0.0
        lu=livestock_requirements.get('livestock_units') or 0.0
        graze_feed=(current_pasture*pasture_yield) if pasture_yield is not None else None
        feed_deficit=max(0.0,feed_need-graze_feed) if graze_feed is not None else None
        external_feed_cost=feed_deficit*feed_price if feed_deficit is not None and feed_price is not None else None
        herd_cost=heads*cattle_cost+heads*herd_power*power_unit+heads*herd_diesel*diesel_unit+drinking*water_unit
        revenue_herd=product*meat_unit
        margin_herd=revenue_herd-herd_cost-external_feed_cost if external_feed_cost is not None else (0.0 if heads == 0 else None)
        # Only Tier 1 enteric, explicitly entered manure and fossil energy; no lifecycle inference.
        enteric=heads*ENTERIC_CH4_ASIA_KG_HEAD_YEAR['Cattle']*methane_gwp
        herd_ghg=enteric+(manure_factor*heads if manure_factor is not None else 0.0)+heads*(herd_power*_GRID_CO2_KG_KWH+herd_diesel*_DIESEL_CO2_KG_L)
        external_water=(feed_deficit*external_water_factor if feed_deficit is not None and external_water_factor is not None else None)
        external_ghg=(feed_deficit*external_ghg_factor if feed_deficit is not None and external_ghg_factor is not None else None)
        failures=[]
        if convert > 0 and not legal_conversion_allowed: failures.append('land_conversion_not_confirmed')
        if heads > 0 and not pasture_suitable: failures.append('pasture_suitability_not_confirmed')
        if limit is None: failures.append('crop_water_limit_unknown')
        elif crop_water > limit+1e-6: failures.append('crop_water_limit_exceeded')
        if heads>0:
            if herd_water_limit is None: failures.append('livestock_water_limit_unknown')
            elif drinking > herd_water_limit+1e-6: failures.append('livestock_water_limit_exceeded')
            if pasture_yield is None: failures.append('pasture_fodder_yield_unknown')
            elif feed_deficit>1e-9 and not purchase_feed_allowed: failures.append('fodder_deficit_without_purchase')
            elif feed_deficit>1e-9 and feed_price is None: failures.append('purchased_feed_price_unknown')
            if lu_cap is None: failures.append('pasture_capacity_unknown')
            elif current_pasture<=0 or lu/current_pasture>lu_cap+1e-9: failures.append('pasture_capacity_exceeded')
        if margin_herd is None: failures.append('economic_data_incomplete')
        return {
            'name':label,'conversion_ha':convert,'crop_area_ha':total_crop_ha-convert,
            'pasture_ha':current_pasture,'total_farm_ha':total_farm_ha,
            'heads':heads,'meat_t_year':product,'crop_rows':crop_result,
            'crop_water_m3':crop_water,'livestock_drinking_m3_year':drinking,
            'own_fodder_dm_t_year':graze_feed,'fodder_requirement_dm_t_year':feed_need,
            'purchased_fodder_dm_t_year':feed_deficit,
            'animal_units':lu,'stocking_lu_ha':lu/current_pasture if current_pasture>0 else None,
            'crop_margin_kzt':crop_margin,'livestock_margin_kzt':margin_herd,
            'total_margin_kzt':crop_margin+margin_herd if margin_herd is not None else None,
            'partial_onsite_ghg_kg_co2e':crop_ghg+herd_ghg,
            'embedded_feed_water_m3':external_water,'embedded_feed_ghg_kg_co2e':external_ghg,
            'total_water_including_external_feed_m3':crop_water+drinking+external_water if external_water is not None else None,
            'partial_ghg_including_feed_kg_co2e':crop_ghg+herd_ghg+external_ghg if external_ghg is not None else None,
            'full_climate_comparability':bool(heads == 0 or (external_ghg is not None and manure_factor is not None)),
            'feasible':len(failures)==0,'constraints':failures,
        }
    if not alternatives or len(alternatives)>5:
        raise ValueError('Supply between 1 and 5 scenarios')
    results = [calc_one(a) for a in alternatives]
    if abs(results[0]['conversion_ha'])>1e-9 or results[0]['heads'] != 0:
        raise ValueError('First scenario must be unchanged crop-only baseline')
    base = results[0]
    for result in results:
        result['delta_margin_kzt']=(result['total_margin_kzt']-base['total_margin_kzt']
                                 if result['total_margin_kzt'] is not None and base['total_margin_kzt'] is not None else None)
        result['delta_on_site_water_m3']=(result['crop_water_m3']+result['livestock_drinking_m3_year']
                                          -base['crop_water_m3']-base['livestock_drinking_m3_year'])
    return {'district':district,'total_farm_ha':total_farm_ha,'baseline_crops':norm_rows,
            'pasture_base_ha':land_pasture,'crop_water_limit_m3':limit,
            'livestock_water_limit_m3_year':herd_water_limit,'water_basis':'historic official district-zone gross irrigation reference, NOT measured use',
            'year_basis':'crop full production season and livestock full year; not harmonized life-cycle boundaries',
            'emissions_boundary':'direct crop N2O + purchased grid generation CO2 + on-site diesel combustion CO2 + livestock enteric CH4; manure/embedded feed only if supplied, all PARTIAL',
            'feed_purchased_data_complete':bool(pasture_yield is not None and feed_price is not None),
            'scenarios':results}
