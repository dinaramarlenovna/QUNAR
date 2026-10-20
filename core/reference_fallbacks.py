"""Evidence-labelled missing value handling for farm resource inputs.

None -> unknown; measured 0 -> zero. Never present a benchmark as a meter reading.
"""
from dataclasses import dataclass
from math import isfinite
import csv
from pathlib import Path
from .water_norms import default_water_requirement, SOURCE_URL, PUMPING_REFERENCE_KWH_PER_M3

FAO_LIVESTOCK_URL = "https://www.fao.org/4/a0701e/a0701e04.pdf"

@dataclass(frozen=True)
class ResolvedReference:
    value: float | None
    source_tier: str
    source: str
    url: str
    boundary: str
    caveat: str = ""


def optional_observation(value, *, measured_zero=False):
    """Use None for absent observations; require an explicit flag to certify zero."""
    if value is None or value == "":
        return None
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError('A measured resource use must be finite and nonnegative')
    return number if number > 0 or measured_zero else None


def irrigation_water_fallback(district, crop, area_ha, irrigation_method='unknown',
                              observed=None, measured_zero=False):
    value = optional_observation(observed, measured_zero=measured_zero)
    if value is not None:
        return ResolvedReference(value, 'user_observed', 'Farm meter / user confirmation', '',
                                 'full crop cycle; field water', 'Confirmed zero is permitted')
    area = float(area_ha)
    if not isfinite(area) or area <= 0:
        raise ValueError('Positive field area is required')
    if not crop:
        return ResolvedReference(None, 'unavailable', 'Crop not specified', '', 'field water')
    # Zero irrigation is physically possible in rain-fed farming. This says
    # nothing about effective precipitation or total crop water use.
    if irrigation_method == 'rainfed':
        return ResolvedReference(0.0, 'technology_configured_zero',
            'Rain-fed technology declared by the farm', '',
            'artificial irrigation only, m³/full crop cycle',
            'The crop still uses rainfall/soil moisture; zero is not total crop water demand')
    # Paddy irrigation needs seepage, percolation, land preparation and standing
    # water; the general Turkestan 8,181.6 fallback would understate demand.
    if crop == 'Rice':
        from .evidence_registry import rice_regional_scenarios
        value_per_ha, evidence = rice_regional_scenarios(irrigation_method)
        if value_per_ha is None:
            return ResolvedReference(None,'unavailable',
                'Rice irrigation technique unspecified: no validated regional norm',
                evidence.url,'paddy irrigation, m³/cycle',
                'Choose flooded or documented drip; FAO rice balance requires percolation and puddling')
        return ResolvedReference(value_per_ha*area,'regional_official_pilot',evidence.name,
            evidence.url,'paddy irrigation scenario, m³/cycle',
            'Local pilot/upper-bound published figure, NOT a universal district mean')
    ref = default_water_requirement(district, crop, irrigation_method)
    return ResolvedReference(ref.m3_ha * area, ref.source_tier, ref.source_label,
                             SOURCE_URL if ref.source_tier != 'regional_fallback' else '',
                             'full crop cycle; benchmark irrigation delivery',
                             'Reference need, NOT measured water; check soil/method and crop mapping')


def livestock_drinking_fallback(species, heads, observed=None, *, measured_zero=False, temperature_c=None):
    observed_value = optional_observation(observed, measured_zero=measured_zero)
    if observed_value is not None:
        return ResolvedReference(observed_value, 'user_observed', 'Farm meter / user confirmation', '',
                                 'total water reported by farm')
    if heads is None or float(heads) <= 0:
        return ResolvedReference(None, 'unavailable', 'No animals counted', FAO_LIVESTOCK_URL,
                                 'livestock drinking water')
    # Read the same versioned FAO table used by core/livestock.py, without
    # requiring a Streamlit runtime for this pure calculation.
    table = Path(__file__).resolve().parents[1] / 'data' / 'livestock_reference_norms.csv'
    with table.open(encoding='utf-8-sig', newline='') as handle:
        row = next((r for r in csv.DictReader(handle) if r['Species'] == species), None)
    if row is None:
        return ResolvedReference(None,'unavailable','No matching species factor', FAO_LIVESTOCK_URL,
                                 'livestock drinking water')
    t = 25.0 if temperature_c is None else float(temperature_c)
    if not isfinite(t):
        raise ValueError('Temperature must be finite')
    tc = min(35.0, max(15.0, t))
    w15 = float(row['Water_L_head_day_15C'])
    w25 = float(row['Water_L_head_day_25C'])
    w35 = float(row['Water_L_head_day_35C'])
    daily = w15 + (w25 - w15) * (tc-15)/10 if tc <= 25 else w25 + (w35-w25)*(tc-25)/10
    amount = daily * float(heads) * 365.0 / 1000.0
    return ResolvedReference(amount, 'international_reference',
                             f"FAO Livestock's Long Shadow (2006), Chapter 4, Table 4.2; {row.get('Reference_condition','')}",
                             FAO_LIVESTOCK_URL, 'drinking water only, m³/year',
                             'Does not include washing, cooling, manure handling and fodder irrigation; temperature reference 25°C if unknown')


def conditional_pumping_energy(water_m3, observed=None, *, measured_zero=False, pumping_confirmed=False,
                               head_m=None, overall_efficiency=None, allow_technology_scenario=False):
    value = optional_observation(observed, measured_zero=measured_zero)
    if value is not None:
        return ResolvedReference(value, 'user_observed', 'User electricity meter', '', 'all farm operations')
    if not pumping_confirmed or water_m3 is None or water_m3 <= 0:
        return ResolvedReference(None, 'unavailable', 'No verified pumping system and head', '',
                                 'electricity use, kWh')
    if head_m is not None and overall_efficiency is not None:
        h, eta = float(head_m), float(overall_efficiency)
        if not isfinite(h) or h <= 0 or not isfinite(eta) or not 0 < eta <= 1:
            raise ValueError("Pumping head and efficiency must be physically valid")
        # 1000 kg/m³ × 9.81 m/s² × H / (3.6e6 J/kWh × efficiency).
        return ResolvedReference(float(water_m3) * (0.002725 * h / eta),
                                 "physical_model", "FAO Pressurized Irrigation Techniques, hydraulic pumping formula",
                                 "https://www.fao.org/4/a1336e/a1336e03d.pdf",
                                 "pumping energy scenario, kWh", "Requires actual head and overall pump/motor efficiency")
    if not allow_technology_scenario:
        return ResolvedReference(None, 'unavailable',
                                 'Pumping reported but head and efficiency are unknown', '',
                                 'pumping energy, kWh',
                                 'Set pump head and overall efficiency, or explicitly accept an illustrative scenario')
    return ResolvedReference(float(water_m3) * PUMPING_REFERENCE_KWH_PER_M3,
                             'technology_scenario', 'QŪNAR editable reference pumping intensity 0.70509 kWh/m³',
                             '', 'pumping scenario only',
                             'Not verified as a universal Kazakhstan standard, no electricity observation')
