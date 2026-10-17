"""Pump-energy engineering and mutually exclusive water-tariff accounting."""
from math import isfinite


def pumping_kwh_per_m3(head_m: float, total_efficiency: float) -> float:
    h, eta = float(head_m), float(total_efficiency)
    if not isfinite(h) or not isfinite(eta) or h <= 0 or not 0 < eta <= 1:
        raise ValueError('Pump head and overall efficiency must be physically valid')
    # rho=1000 kg/m3, g=9.81 m/s2; kWh/J=1/3.6e6.
    return (1000.0*9.81/3_600_000.0)*h/eta


def water_and_pumping_cost(*, water_m3, water_tariff_kzt_m3, mode,
                           own_pump_kwh_m3=0.0, own_electricity_tariff_kzt_kwh=0.0):
    if mode not in ('gravity_with_separate_onfarm_pump', 'purchased_mechanized_inclusive'):
        raise ValueError('Choose exactly one known water-service mode')
    values=(water_m3,water_tariff_kzt_m3,own_pump_kwh_m3,own_electricity_tariff_kzt_kwh)
    if any(not isfinite(float(x)) or float(x)<0 for x in values):
        raise ValueError('Invalid water/energy quantities or tariff')
    if mode=='purchased_mechanized_inclusive' and float(own_pump_kwh_m3)!=0:
        raise ValueError('Mechanized supplier tariff contains pumping; do not add the supplier energy bill')
    if mode=='gravity_with_separate_onfarm_pump' and float(own_pump_kwh_m3)<=0:
        raise ValueError('Own pump energy must be documented')
    energy=float(water_m3)*float(own_pump_kwh_m3)
    water=float(water_m3)*float(water_tariff_kzt_m3)
    return {'water_service_kzt':water,'own_pumping_electricity_kwh':energy,
            'own_pumping_electricity_kzt':energy*float(own_electricity_tariff_kzt_kwh),
            'total_kzt':water+energy*float(own_electricity_tariff_kzt_kwh),
            'provenance':'published water service tariff + own pumping' if energy else 'purchased mechanically delivered water, pumping included in supplier tariff'}
