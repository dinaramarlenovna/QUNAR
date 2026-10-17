"""Farm-wide crop structure water ledger (scenario, not measured basin savings).

Each positive-area crop requires an explicit net root-zone irrigation volume in
m³/ha for the SAME season; application/conveyance and recoverable fractions are
independent, user-supported assumptions. Do not substitute official gross
irrigation norms as root-zone demand, and do not infer return flows from method.
"""
from __future__ import annotations
from math import isfinite
from core.water_accounting import irrigation_water_balance


def _positive_finite(value, label, *, allow_zero=False):
    try: val = float(value)
    except (ValueError, TypeError): raise ValueError(f'Invalid or missing {label}') from None
    if not isfinite(val) or val < 0 or (not allow_zero and val == 0):
        raise ValueError(f'Invalid {label}')
    return val


def _inventory(areas, net_by_crop, eta_by_crop, *, conveyance_efficiency,
               recoverable_by_crop, conveyance_recovery, evidence):
    if not isinstance(areas,dict) or not areas:
        raise ValueError('Structure areas must be a nonempty mapping')
    sums = {'root_zone_net_m3':0.0,'field_delivery_m3':0.0,
            'field_losses_m3':0.0,'source_withdrawal_m3':0.0,
            'conveyance_losses_m3':0.0,'recoverable_return_m3':0.0,
            'irrigation_depletion_proxy_m3':0.0}
    all_source = conveyance_efficiency is not None
    all_depletion = recoverable_by_crop is not None and (
        not all_source or conveyance_recovery is not None)
    details = []
    area_total = 0.0
    for rawcrop, rawarea in areas.items():
        crop = str(rawcrop)
        area = _positive_finite(rawarea,f'area {crop}',allow_zero=True)
        if area == 0: continue
        area_total += area
        if crop not in net_by_crop or crop not in eta_by_crop:
            raise ValueError(f'Net irrigation and method efficiency required for crop: {crop}')
        if all_depletion and crop not in recoverable_by_crop:
            raise ValueError(f'Missing recoverable return fraction for crop: {crop}')
        item = irrigation_water_balance(
            net_irrigation_m3_ha=_positive_finite(net_by_crop[crop],f'net root-zone irrigation {crop}',allow_zero=True),
            field_efficiency=eta_by_crop[crop],
            conveyance_efficiency=conveyance_efficiency,
            field_recoverable_fraction=(recoverable_by_crop[crop] if all_depletion else None),
            conveyance_recoverable_fraction=(conveyance_recovery if all_depletion else None),
            evidence=evidence)
        sums['root_zone_net_m3'] += item.net_irrigation_m3_ha*area
        sums['field_delivery_m3'] += item.field_applied_m3_ha*area
        sums['field_losses_m3'] += item.field_loss_m3_ha*area
        if all_source:
            sums['source_withdrawal_m3'] += item.source_withdrawal_m3_ha*area
            sums['conveyance_losses_m3'] += item.conveyance_loss_m3_ha*area
        if all_depletion:
            sums['recoverable_return_m3'] += item.recoverable_return_m3_ha*area
            sums['irrigation_depletion_proxy_m3'] += item.irrigation_attributable_depletion_m3_ha*area
        details.append({'crop':crop,'area_ha':area,'net_irrigation_m3_ha':item.net_irrigation_m3_ha,
                        'field_efficiency':item.field_efficiency,
                        'field_delivery_m3':item.field_applied_m3_ha*area,
                        'source_withdrawal_m3':(item.source_withdrawal_m3_ha*area if all_source else None)})
    if area_total <= 0:
        raise ValueError('At least one crop must have positive area')
    if not all_source:
        sums['source_withdrawal_m3']=None
        sums['conveyance_losses_m3']=None
    if not all_depletion:
        sums['recoverable_return_m3']=None
        sums['irrigation_depletion_proxy_m3']=None
    sums.update({'area_ha':area_total,'per_crop':details})
    return sums


def compare_structure_water(*, baseline_areas:dict, proposed_areas:dict,
                            net_irrigation_m3_ha:dict,
                            baseline_field_efficiency_by_crop:dict,
                            proposed_field_efficiency_by_crop:dict,
                            conveyance_efficiency:float|None=None,
                            baseline_recoverable_by_crop:dict|None=None,
                            proposed_recoverable_by_crop:dict|None=None,
                            baseline_conveyance_recovery:float|None=None,
                            proposed_conveyance_recovery:float|None=None,
                            evidence:str, confirmed:bool=False) -> dict:
    """Crop-mix and irrigation counterfactual, using matched farm & time boundary.

    'Water saving' is only field delivery/withdrawal difference, not verified
    consumptive or catchment saving. For depletion, both structures must have
    complete return-flow assumptions. All reported deltas = baseline-proposed.
    """
    if not confirmed or not isinstance(evidence,str) or not evidence.strip():
        raise ValueError('Data source/scenario assumptions and confirmation required')
    if (baseline_recoverable_by_crop is None) != (proposed_recoverable_by_crop is None):
        raise ValueError('Recoverable fractions must be supplied for both structures or neither')
    if (baseline_conveyance_recovery is None) != (proposed_conveyance_recovery is None):
        raise ValueError('Conveyance return fractions must be paired')
    if conveyance_efficiency is None and (baseline_conveyance_recovery is not None):
        raise ValueError('No conveyance recovery without a conveyance efficiency')
    base = _inventory(baseline_areas,net_irrigation_m3_ha,
                      baseline_field_efficiency_by_crop,conveyance_efficiency=conveyance_efficiency,
                      recoverable_by_crop=baseline_recoverable_by_crop,
                      conveyance_recovery=baseline_conveyance_recovery,evidence=evidence)
    proposed = _inventory(proposed_areas,net_irrigation_m3_ha,
                         proposed_field_efficiency_by_crop,conveyance_efficiency=conveyance_efficiency,
                         recoverable_by_crop=proposed_recoverable_by_crop,
                         conveyance_recovery=proposed_conveyance_recovery,evidence=evidence)
    if abs(base['area_ha']-proposed['area_ha'])>max(1e-6,base['area_ha']*1e-5):
        raise ValueError('Baseline and proposed farm areas must match')
    keys=('root_zone_net_m3','field_delivery_m3','source_withdrawal_m3',
          'recoverable_return_m3','irrigation_depletion_proxy_m3')
    difference = {key+'_reduction':(
        None if base[key] is None or proposed[key] is None else base[key]-proposed[key])
        for key in keys}
    return {
        'baseline':base,'proposed':proposed,'difference':difference,
        'evidence':evidence.strip(), 'period':'same user-documented crop season',
        'scope':'comparative crop-mix and irrigation scenario, not measured real basin saving',
        'warnings':[
            'Net volumes are root-zone irrigation demand, NOT official gross field norms.',
            'Changing the crop mix changes net water demand; do not attribute all differences to irrigation technology.',
            'Return flows, soil-water carryover, water quality, salinity/leaching and downstream reuse require separate evidence.',
            'Without measured basin consumption the depletion proxy is not actual water conservation.'
        ]
    }
