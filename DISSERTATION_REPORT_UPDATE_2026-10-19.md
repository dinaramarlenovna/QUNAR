# QŪNAR v0.8.1 - Dissertation report update (2026-10-19)

## Modified files
- `app.py` - retains previous navigation-persistence patch and adds explicit before/after contribution-margin and water comparisons. Includes percentage change. When baseline and optimized emissions are verified in the sustainable-comparison engine, partial GHG is shown. No invented energy or emissions changes: missing evidence is stated explicitly.
- `core/reporting.py` - integrated PDF/Word/Excel reports put input/source assumptions in ONE appendix at the end, separating shared inputs from per-mode differences. Individual reports retain their own source tables.

## Critical finding from the uploaded 2026-10-18 21:13 PDF
- Optimization baseline: **22,550,000 KZT** contribution margin; optimized **26,936,034 KZT**; change **+4,386,034 KZT / +19.45%**. This is conditional annual *contribution margin*, assuming one crop cycle in a year, NOT audited profit.
- With the reported baseline mix (Wheat 30 ha, Sunflower 25 ha, Corn 20 ha, Potato 15 ha, Barley 10 ha) and the report's crop norms (3550, 2675, 6450, 6450, 4050 m3/ha respectively), baseline crop water demand is **439,625 m3**. Optimized demand is **450,000 m3**, therefore demand **INCREASES by 10,375 m3 (+2.36%)**. The original scenario does not demonstrate water savings.
- The -20% water scenario yielded **no feasible allocation** under the stated constraints. No economic gain is defined for that variant.
- The existing 2025 producer price dataset has documented crop prices, but the validated current crop cost catalogue (`data/crop_variable_cost_references.csv`) is empty. Therefore a verified conservative crop contribution margin cannot be derived from the available evidence. The previous 140k/160k/280k/500k/125k inputs must remain labelled hypothetical; never describe them as Bureau of National Statistics production-cost observations.

## Recommended dissertation demonstration
1. Show the existing scenario as an explicit **illustrative economic optimization** with user-entered margin assumptions and the water trade-off correctly disclosed.
2. Show a resource-climate-only optimization with no crop margins as an independent resource constrained run.
3. For a **source-grounded conservative economic scenario**, obtain five 2025/2026 technology budgets (seed, fertilizer, labor, fuel, crop protection, other variable cost) for the same five crops and the same irrigation technology. Document costs in KZT/ha, avoiding double counting water and purchased power. Join to the verified producer prices and field yields before calculating `contribution margin = yield_c_ha / 10 * price_kzt_t - costs_kzt_ha - measured water/energy costs`.
4. Do not label a conservative numerical economic outcome as verified until those cost sources are present. Sensitivity discounts to user-entered margins can be shown as stress tests only, not official profitability evidence.
5. Energy and GHG comparative changes require consistent crop-specific energy and partial emissions coefficients for *both* original and optimized structures. Missing coefficients must produce 'Not quantified'.

## Tests performed
- Python syntax compilation passed for both changed modules.
- Smoke-generated combined PDF, Word and Excel with shared inputs and differing field-area values; confirmed export succeeds.
- Live Streamlit navigation and full run on connected GitHub was not tested. Upload changed files to the repository to deploy.
