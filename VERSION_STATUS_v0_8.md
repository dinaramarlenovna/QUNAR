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

- Delphi/AHP elicitation and replacement of provisional 0.60/0.40 resource-climate weights;
- crop-specific climate calibration for expanded crops not present in the historical panel;
- verified crop-specific price/cost dataset if an economic criterion is to enter cross-crop ranking/optimization;
- renewed robustness/sensitivity tests after final Delphi/AHP weights;
- final UI/report redesign for the new three-layer architecture.
