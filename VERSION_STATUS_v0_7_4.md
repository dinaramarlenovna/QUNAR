# QŪNAR v0.7.4 - data-audit recalibration

## Scientific corrections
- Removed the legacy market-price / gross-revenue proxy from QŪNAR ranking and structure optimization. Raw legacy columns remain only in the packaged source CSV for audit traceability and are dropped from the active decision layer.
- Rebuilt the decision score from climate suitability (50%), district-crop water efficiency (35%), and evidence reliability (15%).
- Added district-crop default irrigation requirements based on the official Kazakhstan water-use norms (Order No. 108-NQ, 04.06.2025, Table 3), with explicit zone/regional fallbacks where a direct mapping is unavailable.
- Farmer-entered actual water use overrides the default norm. Water availability is a hard feasibility constraint in structure optimization.
- Added an official reference pumping scenario of 0.70509 kWh/m3; it is labelled as a scenario and never presented as observed farm electricity use.
- Live NASA POWER now requests GWETROOT together with temperature, precipitation, relative humidity and solar radiation, matching the historical climate feature set.
- ML support now uses crop-specific time-blocked validation MAE where available instead of one global MAE for every crop.
- Barley remains excluded from yield ML until its duplicated source yield series is independently verified.
- Latest uploaded Kazakhstan district GeoJSON was reduced to 17 unique Turkestan Region territories and integrated into the administrative boundary layer; duplicate Kentau geometry was de-duplicated by coderayon.

## Validation rerun
- Time-blocked GroupKFold ML validation and chronological holdout were rerun.
- VIF was recalculated for the five numeric ML features.
- Nonlinearity was checked by comparing time-blocked Random Forest and linear models.
- QŪNAR ranking robustness was rerun with one-at-a-time ±20% weight changes, leave-one-component-out tests and Monte Carlo weight perturbation across all 17 territories.
- Structure optimizer was tested under multiple water limits for all 17 territories. Infeasible limits are explicitly reported rather than silently violated.

## Interpretation rule
Default values are not labelled as farm observations. Provenance hierarchy is:
1. user-entered farm measurement;
2. direct official district/crop norm;
3. explicit official-zone fallback;
4. regional calibration fallback;
5. modelled scenario/proxy, clearly labelled.
- Corrected a hidden coordinate inconsistency: `core/data.py` no longer uses hard-coded generic district centers. It loads the exact 17 NASA POWER coordinates packaged in `data/district_centroids.json`.
- Rebuilt `district_climate_fallback.csv` directly from the uploaded NASA POWER monthly files at those exact coordinates for the 2004-2023 ML reference period. This prevents fallback climate from silently using a different point than the training panel.
