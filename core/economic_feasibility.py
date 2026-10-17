from __future__ import annotations


def economic_feasibility(*, yield_centners_ha=None, selling_price_kzt_t=None,
                         variable_cost_kzt_ha=None, water_m3_ha=None,
                         water_tariff_kzt_m3=None, energy_kwh_ha=None,
                         electricity_tariff_kzt_kwh=None,
                         variable_cost_includes_water_energy=False):
    """Transparent farm-level economic contour.

    No hidden market-price proxy is used. Revenue requires a user/verified price.
    Profit is never reported unless the supplied variable-cost field is intended to
    cover the relevant variable production costs. The returned margin is therefore
    explicitly labelled a contribution/gross-margin scenario.
    """
    y = None if yield_centners_ha is None else float(yield_centners_ha)
    p = None if selling_price_kzt_t is None else float(selling_price_kzt_t)
    vc = None if variable_cost_kzt_ha is None else float(variable_cost_kzt_ha)
    wm = float(water_m3_ha or 0.0)
    wt = float(water_tariff_kzt_m3 or 0.0)
    ek = float(energy_kwh_ha or 0.0)
    et = float(electricity_tariff_kzt_kwh or 0.0)

    from math import isfinite
    for name, value in (("yield_centners_ha", y), ("selling_price_kzt_t", p),
                        ("variable_cost_kzt_ha", vc), ("water_m3_ha", wm),
                        ("water_tariff_kzt_m3", wt), ("energy_kwh_ha", ek),
                        ("electricity_tariff_kzt_kwh", et)):
        if value is not None and (not isfinite(value) or value < 0):
            raise ValueError(f"{name} must be finite and nonnegative")
    if not isinstance(variable_cost_includes_water_energy, bool):
        raise ValueError("variable_cost_includes_water_energy must be boolean")

    water_cost = wm * wt
    energy_cost = ek * et
    resource_cost = water_cost + energy_cost

    out = {
        "water_cost_kzt_ha": water_cost,
        "energy_cost_kzt_ha": energy_cost,
        "resource_cost_kzt_ha": resource_cost,
        "price_available": bool(p is not None and p > 0),
    }
    if y is None or y < 0 or p is None or p <= 0:
        out.update({"gross_revenue_kzt_ha": None, "contribution_margin_kzt_ha": None,
                    "economic_score_0_100": None, "status": "price_required"})
        return out

    yield_t_ha = y / 10.0
    revenue = yield_t_ha * p
    if vc is None or vc <= 0:
        out.update({
            "yield_t_ha": yield_t_ha,
            "gross_revenue_kzt_ha": revenue,
            "variable_cost_kzt_ha": None,
            "contribution_margin_kzt_ha": None,
            "margin_ratio": None,
            "economic_score_0_100": None,
            "status": "variable_cost_required",
        })
        return out
    if not isinstance(variable_cost_includes_water_energy, bool):
        raise ValueError("variable_cost_includes_water_energy must be boolean")
    # The user-facing app explicitly excludes water/electricity from other costs.
    # If a different caller supplies an inclusive cost, never deduct twice.
    margin = revenue - vc - (0.0 if variable_cost_includes_water_energy else resource_cost)
    ratio = margin / revenue if revenue > 0 else None
    out.update({
        "yield_t_ha": yield_t_ha,
        "gross_revenue_kzt_ha": revenue,
        "variable_cost_kzt_ha": vc,
        "variable_cost_includes_water_energy": variable_cost_includes_water_energy,
        "contribution_margin_kzt_ha": margin,
        "margin_ratio": ratio,
        "economic_score_0_100": None,
        "status": "scenario",
    })
    return out
