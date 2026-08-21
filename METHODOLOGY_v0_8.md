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

The provisional resource-climate score is:

`QUNAR_resource_climate = 0.60 * Climate + 0.40 * WaterPressure`

The 0.60/0.40 weights are **provisional engineering weights only**. They are isolated in code and must be replaced after Delphi/AHP elicitation. They are not claimed as survey-derived weights.

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

## 6. Delphi/AHP status

The 2026 stakeholder questionnaire supports the selection of major dimensions such as water, climate risk, irrigation and technology adoption. It is not an AHP pairwise-comparison survey and does not identify numerical QŪNAR weights.

The next formal weighting stage should therefore use:

1. Delphi rounds to agree on criterion definitions and remove redundant criteria;
2. AHP pairwise comparisons to derive weights;
3. consistency-ratio testing;
4. sensitivity analysis around the resulting weights.

Until that stage is complete, v0.8 displays and documents provisional weights rather than presenting them as empirically established constants.

## 7. Interpretation boundary

QŪNAR scores are comparative decision coordinates within a specified district, crop set and information state. Their scientific content lies in the transparent composition of evidence, constraints and trade-offs, not in treating a score such as 74.2 as an independently observed physical quantity.
