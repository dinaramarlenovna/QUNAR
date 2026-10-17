"""Transparent irrigation withdrawals and optional return-flow water accounting.

FAO Training Manual 4: application versus conveyance efficiency.
FAO 2021 cb3844en: distinguish reduced diversion from reduced depletion.

The input net crop irrigation is irrigation-supplied root-zone water (not total ETc).
Assumes unchanged storage, no capillary rise and no third-party withdrawals.
Do not infer recoverable vs non-recoverable water from application efficiency alone.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

FAO_SOURCE = 'https://www.fao.org/4/t7202e/t7202e08.htm'
FAO_WATER_SAVINGS_GUIDANCE = 'https://www.fao.org/documents/card/en/c/cb3844en'


def _number(x, label: str, *, low: float = 0.0, upper: float | None = None) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ValueError(f'Expected numeric {label}') from None
    if not isfinite(v) or v < low or (upper is not None and v > upper):
        raise ValueError(f'Invalid {label}')
    return v


@dataclass(frozen=True)
class WaterBalance:
    net_irrigation_m3_ha: float
    field_applied_m3_ha: float
    source_withdrawal_m3_ha: float | None
    field_loss_m3_ha: float
    conveyance_loss_m3_ha: float | None
    recoverable_return_m3_ha: float | None
    nonrecoverable_loss_m3_ha: float | None
    irrigation_attributable_depletion_m3_ha: float | None
    field_efficiency: float
    conveyance_efficiency: float | None
    evidence: str
    status: str


def irrigation_water_balance(*, net_irrigation_m3_ha: float,
                             field_efficiency: float,
                             conveyance_efficiency: float | None = None,
                             field_recoverable_fraction: float | None = None,
                             conveyance_recoverable_fraction: float | None = None,
                             evidence: str = 'FAO field-application reference scenario') -> WaterBalance:
    """Compute transparent per-ha water fluxes without imaginary recovery shares.

    The paired fractions partition each *loss* into return-to-system (recoverable)
    and non-recoverable (e.g., evaporation, inaccessible aquifer). They must be
    measured or explicitly declared scenario assumptions.  They are not implied
    by irrigation method or FAO efficiency lookup. Only with all fractions does
    the irrigation-attributable depletion proxy become available.
    """
    net = _number(net_irrigation_m3_ha, 'net irrigation')
    eta = _number(field_efficiency, 'field efficiency', low=1e-12, upper=1.0)
    if not str(evidence).strip():
        raise ValueError('Data provenance or scenario assumption is required')
    if conveyance_efficiency is None and conveyance_recoverable_fraction is not None:
        raise ValueError('Conveyance recovery requires conveyance efficiency')
    ec = None if conveyance_efficiency is None else _number(
        conveyance_efficiency, 'conveyance efficiency', low=1e-12, upper=1.0)
    rf = None if field_recoverable_fraction is None else _number(
        field_recoverable_fraction, 'field recoverable fraction', upper=1.0)
    rc = None if conveyance_recoverable_fraction is None else _number(
        conveyance_recoverable_fraction, 'conveyance recoverable fraction', upper=1.0)
    applied = net / eta
    field_loss = applied - net
    withdrawn = None if ec is None else applied / ec
    conv_loss = None if withdrawn is None else withdrawn - applied
    recoverable = nonrecoverable = depletion = None
    if rf is not None and (ec is None or rc is not None):
        recoverable = field_loss * rf + (0.0 if ec is None else conv_loss * rc)
        nonrecoverable = field_loss * (1.0-rf) + (0.0 if ec is None else conv_loss*(1.0-rc))
        depletion = net + nonrecoverable
    status = ('source_withdrawal_and_depletion_proxy' if depletion is not None and ec is not None
              else 'field_delivery_and_depletion_proxy' if depletion is not None
              else 'source_withdrawal_only' if withdrawn is not None
              else 'field_delivery_only')
    return WaterBalance(net, applied, withdrawn, field_loss, conv_loss,
                        recoverable, nonrecoverable, depletion, eta, ec,
                        str(evidence).strip(), status)


def compare_irrigation_balances(baseline: WaterBalance, proposed: WaterBalance, *,
                                area_ha: float = 1.0) -> dict:
    """Source/field comparisons in the same boundary; unknown != zero."""
    area = _number(area_ha, 'area', low=1e-12)
    def comp(key: str):
        a, b = getattr(baseline,key), getattr(proposed,key)
        return None if a is None or b is None else (a-b)*area
    source = comp('source_withdrawal_m3_ha')
    field = comp('field_applied_m3_ha')
    depletion = comp('irrigation_attributable_depletion_m3_ha')
    return {
        'field_delivery_reduction_m3':field,
        'source_withdrawal_reduction_m3':source,
        'depletion_proxy_reduction_m3':depletion,
        'recoverable_return_change_m3': (None if baseline.recoverable_return_m3_ha is None or proposed.recoverable_return_m3_ha is None
                                       else (proposed.recoverable_return_m3_ha-baseline.recoverable_return_m3_ha)*area),
        'scope':'conditional water-flow scenario, not observed catchment-scale saving',
        'warnings': [
            'Depletion is an irrigation-attributable proxy, not a full basin water balance.',
            'Return-flow accessibility, quality, destinations and storage require site evidence.',
            'Crop demand, soil moisture, salinity/leaching and irrigated area may change.'
        ]
    }
