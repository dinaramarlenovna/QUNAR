from .water_norms import default_pumping_energy_kwh


def calculate_resources(
    area_ha,
    water_used_m3=None,
    reuse_percent=None,
    energy_kwh=None,
    electricity_ef=None,
    wapor_consumptive_water_m3=None,
    predicted_yield_centners_ha=None,
    water_source="user",
):
    out = {}

    if water_used_m3 is not None and water_used_m3 > 0:
        reuse = max(0.0, min(float(reuse_percent or 0.0), 100.0)) / 100.0
        total = float(water_used_m3)
        reused = total * reuse
        freshwater = total - reused
        out.update({
            "farm_water_total_m3": total,
            "farm_water_reused_m3": reused,
            "farm_freshwater_m3": freshwater,
            "farm_water_m3_per_ha": total / float(area_ha),
            "farm_freshwater_m3_per_ha": freshwater / float(area_ha),
            "farm_water_source": water_source,
            # Scenario only: if this entire volume were pumped at the official
            # Kazvodkhoz reference intensity. Never labelled as actual farm energy.
            "reference_pumping_energy_kwh": default_pumping_energy_kwh(total),
            "reference_pumping_energy_kwh_per_ha": default_pumping_energy_kwh(total) / float(area_ha),
        })

    if wapor_consumptive_water_m3 is not None and wapor_consumptive_water_m3 > 0:
        cw = float(wapor_consumptive_water_m3)
        out["wapor_consumptive_water_total_m3"] = cw
        out["wapor_consumptive_water_m3_per_ha"] = cw / float(area_ha)
        if predicted_yield_centners_ha is not None:
            production_kg = float(predicted_yield_centners_ha) * 100.0 * float(area_ha)
            out["modelled_water_productivity_kg_m3"] = production_kg / cw

    if energy_kwh is not None and energy_kwh > 0:
        out["energy_kwh"] = float(energy_kwh)
        out["energy_kwh_per_ha"] = float(energy_kwh) / float(area_ha)
        if electricity_ef is not None and electricity_ef > 0:
            out["operational_co2e_kg"] = float(energy_kwh) * float(electricity_ef)
            out["operational_co2e_kg_per_ha"] = out["operational_co2e_kg"] / float(area_ha)
    return out
