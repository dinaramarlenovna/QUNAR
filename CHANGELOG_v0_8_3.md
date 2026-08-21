# QŪNAR v0.8.3 - district-crop 2024-2025 update

## Main correction
The crop Random Forest production training panel has been extended from 2004-2023 to 2004-2025 using district × crop observations. Regional aggregates were not used as substitutes for district training rows.

## Data update
- Previous crop ML panel: 1,223 rows.
- Added: 139 verified district-crop rows.
- 2024: 68 rows.
- 2025: 71 rows.
- Final panel: 1,362 rows.
- Coverage: 17 districts, 6 calibrated crops, 2004-2025.
- Missing BNS symbols remain missing and are excluded rather than converted to zero.
- 2024-2025 district outcomes are joined to April-September NASA POWER climate variables at district-year level.

## Validation after update
- GroupKFold by year: MAE 8.840 c/ha; RMSE 16.198 c/ha; R2 0.926.
- Train 2004-2010 -> test 2011-2015: R2 0.949.
- Train 2004-2015 -> test 2016-2020: R2 0.891.
- Train 2004-2020 -> test 2021-2025: R2 0.808; median district-crop baseline R2 0.788.
- Ten-year stress test 2004-2013 -> 2014-2023: R2 0.850.
- Hyperparameter robustness grouped R2 range: 0.916-0.928.

## Production behavior
The production Random Forest architecture is unchanged. `core/ml.py` trains from `data/analytical_panel.csv`; therefore the deployed model now fits on the complete verified 2004-2025 crop panel.

## Files changed / added
- data/analytical_panel.csv
- data/district_crop_update_2024_2025_audit.csv
- data/district_crop_context.csv
- data/district_climate_fallback.csv
- data/crop_expansion_catalog.csv
- data/scientific_validation.json
- data/model_metrics.csv
- data/model_metrics_by_crop.csv
- scientific_validation.py
- SCIENTIFIC_VALIDATION_CURRENT.md
- DATA_UPDATE_2024_2025.md
- QA_V0_8_3.md
- BUILD_CHECKS_v0_8_3.json
- verification.json
- CURRENT_VERSION.txt
