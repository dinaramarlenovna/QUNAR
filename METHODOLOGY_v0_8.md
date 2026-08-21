# QŪNAR v0.8 - methodological core

## 1. Scientific architecture

QŪNAR v0.8 separates three objects that must not be confused:

1. **Resource-climate suitability** - comparative suitability of a crop within a district/resource environment.
2. **Economic feasibility** - a transparent farm scenario based on yield, verified/user-entered selling price, variable costs, water cost and energy cost.
3. **Assessment confidence** - strength of the evidence supporting the recommendation. Confidence does not enter crop attractiveness.

This separation prevents missing data from making a crop appear intrinsically worse and prevents an accounting interpretation of a comparative decision score.

## 2. Resource-climate suitability

For crops represented in the historical analytical panel, current climate is compared with an empirical crop-specific climate envelope estimated from the better-performing half of historical observations. Variables are:

- April-September temperature;
- April-September precipitation;
- April-September root-zone wetness;
- April-September solar radiation.

The reference centre is the median climate profile of higher-yield observations. Distance is computed after robust scaling. The current climate score is the empirical survival percentile of this distance within the crop's historical climate distribution. This avoids assigning undocumented crop-sensitivity coefficients such as 1-5.

For expanded crops without a sufficient crop-specific historical panel, the legacy district climate layer is temporarily retained and explicitly marked `legacy_proxy_pending_crop_calibration`. Such rows receive a lower evidence-confidence contribution. They must not be described as fully empirically calibrated until crop-specific agronomic thresholds or additional time-series evidence are added.

The water component uses official/default crop water requirements. Lower normative water pressure receives a higher comparative score within the district crop set. The user-facing term is **water pressure / relative water burden**, not physical water-use efficiency.

The baseline resource-climate score is:

`QUNAR_resource_climate = 0.60 * Climate + 0.40 * WaterPressure`

The 0.60/0.40 specification preserves continuity with the preceding three-component architecture. In that architecture, climate and water carried weights of 0.50 and 0.35 while evidence reliability carried 0.15. Reliability is now reported separately because evidence strength describes confidence in a recommendation rather than intrinsic crop suitability. Renormalising the remaining climate/water components gives 0.588/0.412; v0.8 uses the transparent rounded baseline 0.60/0.40. The weights are documented as a baseline model specification and are not claimed as survey-derived or AHP-derived constants.

## 3. Assessment confidence

Confidence combines model/evidence tier, reliability of the water source and whether the climate score is dynamically supported by the historical crop panel. It is shown separately from suitability and never enters the resource-climate objective.

The current confidence formula is itself a transparent provisional metadata index and is not a statistical confidence interval.

## 4. Economic contour

The economic contour does not use hidden district market-price proxies. It activates only when a selling price is explicitly entered. Yield can be user-entered or, where available, supplied by the ML yield model.

- Gross revenue per ha = yield (t/ha) × selling price (KZT/t)
- Water cost per ha = water use (m3/ha) × water tariff
- Energy cost per ha = energy use (kWh/ha) × electricity tariff
- Contribution margin scenario = gross revenue - user-entered variable costs - water cost - energy cost

The result is not labelled net profit. It remains a scenario until the cost field contains a sufficiently complete farm cost definition.

No arbitrary 0-100 economic score is generated in v0.8. A future integrated economic score should be calibrated only after the economic dataset and Delphi/AHP specification are finalized.

## 5. Optimization

The farm-structure module is changed from heuristic share allocation to a constrained linear program.

Objective: maximize weighted resource-climate utility.

Constraints:

- crop shares sum to 1;
- each crop share is bounded by the selected maximum share;
- an optional hard water constraint is imposed when available water is entered;
- a small minimum share is used for the requested shortlist when feasible and relaxed if necessary.

Assessment confidence is not part of the optimization objective.

The optimizer is therefore a genuine constrained allocation problem, although its objective remains a resource-climate objective until a defensible crop-specific economic dataset is added.

## 6. Weight robustness and evidence status

The 2026 stakeholder questionnaire supports the substantive selection of water, climate risk, irrigation and technology dimensions. It is used as an independent validation layer and does not generate numerical weights.

The 0.60/0.40 baseline is therefore interpreted through specification transparency and sensitivity analysis. Alternative weight profiles remain available in the optimizer to show how recommendations respond to stronger climate or resource-saving priorities. Evidence confidence remains outside the objective function.

## 7. Environmental diagnostics

The environmental layer reports variables that have a defensible observation source or an explicit farm input. The current layer includes growing-season heat, precipitation, root-zone wetness, solar radiation, electricity-related operational CO2, pesticide load when entered, and salinized-land share when entered. Missing pesticide or salinity values are not replaced by invented district estimates. The interface explicitly distinguishes **unknown** from an observed value of **zero**. Unknown observations are excluded from environmental-data coverage; a zero value is counted only when the user confirms it as an observed farm value. The same rule is applied to optional pasture-degradation input in the livestock module.

Optimized crop structures also receive concentration/diversification diagnostics using HHI and the effective number of crops. These indicators describe structural diversification and are not labelled as biodiversity measures.

## 8. Livestock resource and forecasting module

The livestock extension is documented in `LIVESTOCK_METHOD_v0_8_1.md`. The harmonised evidence base contains regional livestock production and population histories for 1996-2023 and 926 district-year-species observations for the current territorial system over 2015-2023. Administrative structural missingness is preserved.

The livestock forecasting engine uses Random Forest with district, livestock category, previous-year herd size and the same growing-season climate variables used in the crop architecture: temperature, precipitation, root-zone wetness and solar radiation. Rolling-origin validation covers 2021-2023. The pooled log-scale R2 is approximately 0.949 with a median absolute percentage error of approximately 11.6%. Category-level validation is reported separately and controls whether a numerical forecast is published. The current pig series fails the category reliability guard and its numerical ML projection is suppressed.

The resource layer applies species-specific water references, transparent feed dry-matter references where supported, FAO livestock-unit coefficients, pasture pressure, available-water coverage, observed energy/CO2, production per head, compatible regional productivity benchmarks and optional pasture degradation. Unknown farm observations remain unknown and are never silently converted to zero.

## 9. Interpretation boundary

QŪNAR scores are comparative decision coordinates within a specified district, crop set and information state. Their scientific content lies in the transparent composition of evidence, constraints and trade-offs, not in treating a score such as 74.2 as an independently observed physical quantity.
