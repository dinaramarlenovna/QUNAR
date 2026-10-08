# QŪNAR v0.8.1 - current integrated build

This package keeps the prototype identifier **v0.8.1**.

## Integrated corrections
- transparent actual/reference data hierarchy;
- no invented district market prices or technology costs;
- before/after water and resource-cost scenario;
- pumping-energy estimate is labelled and affects only the pumping component;
- technology payback is calculated only when investment is supplied;
- economic feasibility requires verified selling price and variable-cost input for contribution margin;
- optional economic objective in farm-structure optimization using user-entered crop contribution margins;
- resource-climate optimization remains the fallback when economic evidence is absent;
- water/reference source labels corrected in reports;
- within-field crop placement is retained as a future-development direction and is not implemented in the current build because it requires field-level soil, moisture, terrain and irrigation-infrastructure data.

## 2026-10-08 model-strengthening update
- Added explicit optimization objective modes: resource-climate, balanced resource-economic, economic-return priority.
- Added safe fallback when crop economics are insufficient.
- Added user-entered current crop structure and before/after comparison of contribution margin, water demand and margin per m³.
- Added user-defined temperature, precipitation and available-water stress scenarios (explicitly not SSP/CMIP projections).
- Added leave-one-district-out spatial-transferability validation and empirical 90% grouped-OOS uncertainty bands.
- Externalized packaged economic reference scenarios with evidence-tier metadata.
- Added scenario evidence grade for resource-saving economics.
- Preserved visible version label v0.8.1.
