# QŪNAR v0.8 status

Implemented in this branch:

- dynamic empirical NASA-compatible climate scoring for crops with a historical panel;
- explicit fallback flag for crops not yet climate-calibrated;
- separation of confidence from crop suitability;
- renamed water component to relative water pressure/burden;
- transparent optional economic contour using user/verified prices instead of hidden market proxies;
- constrained linear-programming crop allocation;
- irrigation type propagated into water norms used by ranking and optimization;
- v0.7.4 water-used hotfix retained;
- syntax checks passed;
- 17-district score-bound, share-sum and optimization-cap QA passed (`QA_V0_8.json`).

Still pending before dissertation freeze:

- crop-specific climate calibration for expanded crops not present in the historical panel;
- verified crop-specific price/cost dataset if an economic criterion is to enter cross-crop ranking/optimization;
- continued calibration of expanded crops when harmonised district-year yield/area data become available.

Added in the current update:

- documented baseline 0.60/0.40 weight origin from the previous 0.50/0.35 suitability components after separating the 0.15 confidence component;
- environmental diagnostics for heat, precipitation, root-zone wetness, solar radiation, operational CO2, optional pesticide load and optional salinity;
- HHI/effective-number diversification diagnostics for optimized crop structures;
- livestock resource module using observed 2023 district crop-livestock structure plus farm-entered pasture, feed, water, energy and production data;
- fifth user mode for livestock-resource assessment.

- optional environmental inputs now distinguish `unknown / no data` from a confirmed observed zero; missing values are excluded from coverage rather than silently treated as zero.

## v0.8.1 livestock-core validation

- integrated official regional livestock-output and population histories for 1996-2023;
- harmonised district livestock panel: 926 district-year-species observations over 2015-2023, preserving administrative structural missingness;
- added cattle, cows, sheep/goats, pigs, horses, camels and poultry historical benchmark categories;
- added species-specific user modes for cattle, dairy cows, sheep, goats, pigs, horses, camels, layers and broilers;
- added Random Forest livestock forecasting with lagged herd size plus growing-season NASA-compatible climate variables;
- rolling-origin validation for 2021-2023: overall log-scale R2 approximately 0.949, median APE approximately 11.6%, n=318;
- added category-level validation and a forecast-publication guard; the current pig model is withheld because category-level validation is weak;
- added FAO/Merck resource-reference layer for water, feed where supported, and livestock-unit conversion;
- livestock reports distinguish farm observations, district reference scenarios and unknown values;
- full livestock matrix QA passed for 17 territories x 9 user livestock types (153 cases);
- reproducibility outputs: `LIVESTOCK_METHOD_v0_8_1.md`, `livestock_validation_v0_8_1.py`, `QA_LIVESTOCK_V0_8_1.json`, and `data/livestock_validation_by_species.csv`.

- deployment hotfix: mode labels now have an app-level fallback, preventing a KeyError during mixed-version Streamlit/GitHub redeploys.

Localization hotfix v0.8.1:
- audited all user-facing Kazakh, Russian and English labels in `app.py` and `core/config.py`;
- removed cross-language UI leakage such as `поголовье`, `benchmark`, `CAGR`, `LU`, `ML-болжам`, `utility`, `fallback` and `proxy` from Kazakh/Russian display text;
- localized units, report/export labels, model-tier labels and safe fallback labels;
- calculation logic, datasets, 0.60/0.40 weights and livestock forecasting were not changed.
