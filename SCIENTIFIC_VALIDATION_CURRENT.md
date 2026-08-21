# QŪNAR - scientific validation status

## Crop machine-learning sample
- Production estimator: Random Forest regression.
- Current verified district-crop panel: 2004-2025.
- Observations in the calibrated analytical core: 1362.
- Districts represented in the calibrated sample: 17.
- Calibrated crops: 6 (Wheat, Corn, Rice, Cotton, Sunflower, Potato).
- Agricultural outcomes for 2024-2025 are district × crop observations from the official Bureau of National Statistics crop-dynamics workbook, not regional aggregates.
- NASA POWER district climate inputs are available through 2025 and are joined by district and year.
- Production model is fitted on the complete validated 2004-2025 historical panel after validation.

## Primary leakage-safe validation
GroupKFold by year keeps all observations from one calendar year in the same validation fold.
- MAE: 8.840 c/ha
- RMSE: 16.198 c/ha
- R2: 0.926
- Median district-crop baseline R2: 0.914

## Expanding five-year chronological validation
- Train 2004-2010 -> test 2011-2015: MAE=7.141, RMSE=12.276, R2=0.949.
- Train 2004-2015 -> test 2016-2020: MAE=11.942, RMSE=20.794, R2=0.891.
- Train 2004-2020 -> test 2021-2025: MAE=16.699, RMSE=30.538, R2=0.808.

For the same three test blocks, the median district-crop baseline R2 values are 0.942, 0.854 and 0.788 respectively. The Random Forest therefore remains ahead of the non-ML benchmark in all three forward blocks.

## Ten-year stress holdout
- Train 2004-2013 -> test 2014-2023: MAE=13.222, RMSE=24.338, R2=0.850.
- Median district-crop baseline for the same stress holdout: R2=0.821.

## Crop-specific GroupKFold results
- Wheat: N=294, R2=0.516.
- Corn: N=289, R2=0.458.
- Potato: N=290, R2=0.412.
- Sunflower: N=255, R2=0.354.
- Cotton: N=181, R2=0.287.
- Rice: N=53, R2=0.219.

## Hyperparameter robustness
Across the tested Random Forest specifications, grouped R2 ranges from 0.916 to 0.928. The baseline production setting (350 trees, min_samples_leaf=2) gives R2=0.926; changing tree count, leaf size, depth or feature subsampling does not change the overall conclusion.

## Interpretation
The 2021-2025 block is the hardest chronological test because it contains the most recent structural and climatic observations and includes the newly added 2024-2025 district-crop outcomes. The reduction in forward R2 relative to pooled GroupKFold is reported rather than hidden; it defines the realistic temporal-transfer boundary of the model. The production fit is trained only after these validation checks on all 2004-2025 observations.

## Data provenance and missingness rule
Official missing markers (`-`, `..`) are never converted to zero. A district-crop-year row enters the ML core only when district-level sown area and yield are numeric and positive and all required district-year climate inputs are present. The update audit is stored in `data/district_crop_update_2024_2025_audit.csv`.
