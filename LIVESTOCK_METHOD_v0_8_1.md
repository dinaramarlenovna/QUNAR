# QŪNAR v0.8.1 - Livestock Resource and Forecasting Core

## 1. Scope

The livestock extension adds a second agricultural decision contour to QŪNAR. It integrates district herd dynamics, livestock-production history, growing-season climate, species-specific water/feed references, pasture pressure, farm energy use, operational CO2 and observed production. Crop and livestock calculations retain separate biological and resource equations.

## 2. Statistical evidence base

The statistical layer contains:

- regional livestock output for meat (live weight), cow milk, eggs and sheep wool for 1996-2023;
- regional animal populations for cattle, cows, sheep/goats, pigs, horses, camels and poultry for 1996-2023;
- district animal populations for the current territorial system for 2015-2023, with structural missingness retained for districts created later;
- 926 observed district-year-species records in the harmonised livestock panel;
- district agricultural crop/livestock output structure for 2023.

Administrative chronology is preserved. Zhetysay and Keles enter the panel from 2018 and Sauran from 2021. Pre-creation values remain missing. A dash in the source is retained as unavailable rather than converted automatically to zero.

The official district statistics combine sheep and goats and aggregate poultry. QŪNAR therefore uses `Sheep/goats` and `Poultry` as historical benchmark categories. Species-specific water/feed coefficients remain separate for sheep, goats, layers and broilers.

## 3. Climate coupling

The livestock ML layer uses the same growing-season climate architecture as the crop model:

- April-September temperature;
- April-September precipitation;
- April-September root-zone wetness;
- April-September solar radiation.

District-year climate observations are linked to herd records by district and year. Missing district-year climate values are imputed from the same-year regional median and receive an explicit `climate_imputed` flag. The one-step projection uses the latest available district climate profile as a persistence reference; the reference year is displayed in the output.

## 4. ML specification

The livestock forecasting engine uses `RandomForestRegressor` from scikit-learn. The target is `log(1 + herd size)` and the predictors are:

- district;
- livestock benchmark category;
- calendar year;
- log of previous-year herd size;
- growing-season temperature;
- growing-season precipitation;
- growing-season root-zone wetness;
- growing-season solar radiation;
- climate-imputation flag.

The lagged structure starts after the first observation for each district-species series. The current harmonised training frame contains 529 observations for 2019-2023.

## 5. Out-of-time validation

Validation uses rolling-origin forecasting. Each validation year is predicted using observations from earlier years only. The validation years are 2021, 2022 and 2023, with 318 out-of-time predictions.

Overall validation:

- R2 on the log target: approximately 0.949;
- median absolute percentage error: approximately 11.6%.

Category-level validation is retained because aggregate fit can conceal weak categories:

| Historical benchmark category | Validation n | R2 (log) | Median APE, % |
|---|---:|---:|---:|
| Cattle | 50 | 0.739 | 10.8 |
| Cows | 50 | 0.666 | 14.0 |
| Sheep/goats | 50 | 0.883 | 8.3 |
| Horses | 50 | 0.863 | 5.8 |
| Camels | 44 | 0.893 | 21.6 |
| Poultry | 50 | 0.824 | 12.3 |
| Pigs | 24 | -0.077 | 103.5 |

A forecast-publication guard is embedded in the application. Numerical forecasts are published when category-level validation has positive R2 and median APE at or below 50%. The `validated` tier requires R2 of at least 0.50 and median APE at or below 30%. The current pig series fails this guard, so QŪNAR suppresses its numerical ML projection and retains historical/resource diagnostics. This safeguard prevents the strong pooled model from masking a weak species-specific result.

## 6. Species-specific resource references

Drinking-water reference anchors use FAO Table 4.2 values at 15, 25 and 35 degrees C for cattle, dairy cows, sheep, goats, pigs, camels and poultry. Linear interpolation is applied within the 15-35 degrees C interval and capped at its bounds. Horse water uses the Merck Veterinary Manual maintenance reference for a 500-kg adult horse in minimal work, represented by a 25 L/head/day midpoint within the reported 21-29 L/day range.

Standardised dry-matter intake references are used for categories supported by the FAO feed-resource table. No unsupported dry-matter default is imposed for broilers.

Livestock Units use the FAO Asia coefficients:

- cattle/cows 0.50 LU/head;
- sheep/goats 0.10;
- pigs 0.25;
- horses 0.80;
- camels 1.10;
- poultry 0.01.

These factors create a common resource-pressure scale across heterogeneous livestock categories.

## 7. Farm resource diagnostics

For a selected district and livestock type, QŪNAR calculates the following where the required observations are available:

- head count and data source (`user`, `district_reference`, `unknown`);
- livestock units and LU per pasture hectare;
- heads per pasture hectare;
- reference water requirement per head/day and per year;
- available-water coverage of reference requirement;
- observed water per head and observed/reference water ratio;
- reference feed dry matter per head/day and per year;
- entered feed coverage of reference requirement;
- observed energy per head;
- operational electricity-related CO2;
- observed production per head;
- compatible regional productivity comparison for dairy cows, laying poultry and sheep wool;
- optional degraded-pasture area;
- district livestock-output share and percentile context;
- evidence/input completeness.

Unknown farm observations remain unknown. A missing value is never treated as a confirmed zero. If farm head count is absent, the latest official district value can be used as a clearly labelled reference scenario.

## 8. Interpretation boundaries

District herd history supplies a territorial benchmark and a forecasting target. It does not represent the inventory of an individual farm unless the user enters farm-specific head count.

The water values are biological planning references tied to the stated physiological reference category and temperature. Farm water use can differ with body mass, production level, diet, housing, season and management.

Regional productivity references are applied only where the numerator and denominator are compatible with the statistical series. Cow milk is compared with cows, eggs with aggregate poultry for the laying-poultry interface, and sheep wool with the available sheep/goat population denominator. Species without a defensible product-specific regional denominator receive no artificial productivity benchmark.

## 9. Reproducibility files

- `data/livestock_district_panel_2015_2023.csv`
- `data/livestock_region_products_1996_2023.csv`
- `data/livestock_region_population_1996_2023.csv`
- `data/livestock_reference_norms.csv`
- `data/livestock_validation_by_species.csv`
- `livestock_validation_v0_8_1.py`
- `QA_LIVESTOCK_V0_8_1.json`

## 10. External reference sources

- Bureau of National Statistics of the Republic of Kazakhstan, regional agricultural statistics used for livestock output and animal populations.
- FAO. *Livestock's Long Shadow: Environmental Issues and Options*. Rome, 2006, Table 4.2 (drinking-water requirements).
- FAO. *Compendium of Agricultural-Environmental Indicators* (livestock-unit conversion factors by region).
- FAO. *Animal Feed Resources in Asia and the Pacific*, Technical Appendix Table 1 (standardised dry-matter intake references).
- Merck Veterinary Manual. *Nutritional Requirements of Horses and Other Equids* (maintenance water requirement for adult horses).
