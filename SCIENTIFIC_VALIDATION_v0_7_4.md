# QŪNAR v0.7.4 - final validation results

## Data integrity corrections
- Active ranking no longer contains market-price, regional yield-proxy or gross-revenue-proxy fields.
- Water defaults are district-crop specific with explicit source/reliability tiers.
- Exact NASA POWER coordinates are used both for live calls and historical fallback construction.
- Historical fallback climate was rebuilt from the same uploaded NASA POWER points for 2004-2023.
- Barley remains excluded from yield ML pending source verification.

## ML validation
Time-blocked GroupKFold by year:
- MAE: 8.45 c/ha
- RMSE: 15.45 c/ha
- R2: 0.928

Chronological holdout 2021-2023:
- MAE: 14.95 c/ha
- RMSE: 27.20 c/ha
- R2: 0.830

Median baseline is slightly better on MAE but worse on RMSE/R2. The application therefore does not claim that RF dominates the baseline on every metric. Crop-specific MAE is used in the support index.

Crop-specific validation:
| Crop      |   N |      MAE |     RMSE |       R2 |
|:----------|----:|---------:|---------:|---------:|
| Corn      | 259 |  7.36649 | 10.6437  | 0.313099 |
| Cotton    | 163 |  3.6292  |  4.90408 | 0.200683 |
| Potato    | 258 | 21.9444  | 30.6469  | 0.372727 |
| Rice      |  45 | 10.8582  | 12.4511  | 0.277856 |
| Sunflower | 233 |  2.52733 |  3.3271  | 0.323508 |
| Wheat     | 265 |  4.13489 |  5.11573 | 0.489527 |

## Multicollinearity
Maximum VIF across the five numeric ML features: 2.85. Values are below common concern thresholds.

## Nonlinearity check
Time-blocked RF R2 = 0.928; linear R2 = 0.896. RF improves R2 by 0.032, supporting retention of a nonlinear learner without claiming universal superiority.

## Ranking robustness
One-at-a-time ±20% weight perturbation across 17 territories:
- mean Spearman = 0.994
- minimum Spearman = 0.971
- top-1 retention = 100.0%
- mean TOP-3 overlap = 98.4%
- maximum rank shift = 3 positions

Monte Carlo, 5,000 weight draws per district/scenario:
- moderate perturbation: top-1 retention 99.8%, mean Spearman 0.992
- stress perturbation: top-1 retention 95.7%, mean Spearman 0.979

Leave-one-component-out is deliberately harsher: top-1 retention 66.7%. This is reported as structural dependence, not hidden.

## Optimizer
68 district/water-limit scenarios were checked. Land shares sum to 1 and areas to the requested farm area to numerical precision. Some deliberately stringent water budgets are infeasible under the crop-share cap; the optimizer reports `water_feasible=False` instead of silently violating the water constraint.
