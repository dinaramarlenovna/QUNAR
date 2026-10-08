# QŪNAR v0.8.1 - implemented model improvements

This build keeps the registered visible version label **v0.8.1** and strengthens the model without fabricating missing farm or market data.

## Implemented

- Three optimization objectives: resource-climate, balanced resource-economic, and economic-return priority.
- Economic optimization activates only with positive user/verified contribution-margin data for at least two crops; otherwise it safely falls back to the resource-climate objective.
- Optional user-entered current crop shares enable **before/after** comparison of total contribution margin, water demand, percentage change, and contribution margin per m³ of water.
- Farm resource-saving scenario reports water and pumping-related energy savings, KZT savings, annualized savings and payback when investment is supplied.
- Scenario evidence grade distinguishes observed farm inputs from reference-based calculations.
- Explicit climate/water stress-test controls for temperature, precipitation and available-water budget changes. These are scenario tests, not SSP/CMIP projections.
- Leave-one-district-out spatial transferability validation is packaged alongside year-grouped validation.
- 90% empirical grouped-OOS prediction-uncertainty bands are packaged by crop. They are explicitly not presented as parametric confidence intervals.
- Economic reference values are externalized in `data/economic_reference_values.csv` with source-tier labels. Current entries are general editable reference scenarios, not district averages.
- Within-field crop placement remains a future-development item and is not part of the current operational build because field-level soil/moisture/terrain/infrastructure data are required.

## Still data-dependent, not fabricated

- Complete district × crop market-price database.
- District/provider-specific water and electricity tariffs.
- Technology investment costs by equipment, area and district.
- Verified crop-specific operating-cost database.
- True within-field agronomic spatial optimization.
- Long-term SSP/RCP/CMIP climate projections.

These are not auto-filled because doing so without sourced data would create false precision.
