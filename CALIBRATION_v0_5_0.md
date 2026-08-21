# QÚNAR v0.5.0 - crop calibration status

## Full yield-ML tier
Wheat, corn, rice, cotton, sunflower and potato retain the validated district-crop-year ML model.

## CLREM decision-support calibration
The expanded crop-selection layer imports the user's existing CLREM workbook. It contains 255 district × candidate scenarios (17 territories × 15 crop/product options) and combines district prices, regional yield proxies, relative water/energy coefficients and climate suitability into the existing Potential_score. QÚNAR exposes that score as a 0-100 decision-support score and separately reports climate/resource/economic dimensions.

## Barley
Barley is NOT promoted into yield ML. The supplied Chapter 2.3 analytical panel explicitly flags its yield series as an exact duplicate of wheat across 275 overlapping observations. Barley is therefore available only in the CLREM decision-support tier until the source yield series is corrected.

## Grapes and other berries/fruits
The supplied CLREM workbook contains observed 2023 cooperative evidence for fresh grapes and other berries/fruits but no all-district scenario for these products. They are shown as observed evidence where available and are not given fabricated district forecasts.

## Limits
CLREM scenario yield is a regional yield proxy, not district-specific or field-specific observed yield. Market prices are February 2026 scenario prices; water/energy intensities are relative 1-5 analytical coefficients. These limitations are surfaced in the UI.
