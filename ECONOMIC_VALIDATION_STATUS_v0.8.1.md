# QŪNAR economic validation status (visible version v0.8.1)

## Verified in code
- LP infeasibility now returns **no allocation / no claimed optimized gain**, instead of equal shares.
- Maximum crop share and exact crop count are hard constraints. Feasible crop sets are enumerated from the top 18 utility-scored options; optimization is over this **restricted set**, not proven global over a larger catalog.
- Unit consistency: yield in c/ha is divided by 10 to obtain t/ha for sales prices in KZT/t.
- Explicit variable cost boundary prevents double deduction of water/electricity.
- Irrigation yield response remains an **assumption requiring provenance**; not part of trained ML unless training has that feature.
- Common-shock stress scenarios compare the same market change for both plans; they are not estimated probabilities.

## Not established from the supplied archive
- A verified district/crop/year dataset of farm-gate prices and *production costs* 2023-2025.
- Out-of-sample economic forecasting metrics, unless matching historical yield, costs and prices are provided.
- Irrigation yield treatment-effects by crop/soil/irrigation technology, supported by comparable experiments.
- A realistic prediction interval or probability of loss (requires calibrated distributions and historical outcomes).
- Actual realized gains from farmer adoption, which require before/after field observations.
- Complete Streamlit browser integration test (runtime Streamlit dependency not installed in this environment).

## Sources and terminology
Water norms: https://adilet.zan.kz/rus/docs/V2500036253 (Order 108-NQ, 2025); crop/year/area-specific baseline must be verified against the precise table and field conditions.
Economic scenario outputs must be labelled 'potential contribution margin, model scenario' and must never be called observed profit, empirically validated economic effect, or calibrated forecast.

## Recommended decision report
For each crop, state land share (ha), norm and consumption (m³), potential margin (KZT/ha), cost accounting convention, source, then feasibility and *only if feasible* compare before/after. Add three common-shock scenarios and explicit implementation conditions.
