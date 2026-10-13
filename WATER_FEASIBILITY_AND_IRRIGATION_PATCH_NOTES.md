# QŪNAR v0.8.1 - water-feasibility report fix and irrigation-check protocol

Visible version label is unchanged (`v0.8.1`). This package contains only changed/new files relative to the prior economic-hardening + margin-disclaimer patches.

## Replace in your deployed project

1. `app.py` - UI/expo final independent allocation guard; refusal to recommend water-infeasible crop mixes or publish their hypothetical margin gains; quantified diagnostics for infeasible cases; Russian/Kazakh/English report text; localized irrigation-stress output.
2. `core/optimizer.py` - uses strict water/crop/share constraints from previous hardening; additionally prevents presenting a gain against a water-infeasible baseline as if it were attainable.
3. `core/optimization_guard.py` (new) - independent final validation of share sum, total area, crop count, max share and water limit BEFORE displaying/printing results. Prevents legacy-solver output from bypassing safety checks.
4. `tests/test_allocation_final_guard.py` (new) - regression tests for report guards, observed 350k/520k scenarios and irrigation economics.

Keep the other project files unchanged; preserve relative paths. Update all three runtime files together, then redeploy. An old PDF is not retroactively updated; rerun and export a NEW report after deployment.

## Known old PDF (2026-10-13 19:13)

Water cap 350,000 m³; proposed demand 511,000 m³; overbudget by 161,000 m³. The old report's recommended 20%×5 allocation and gain 1,455,000 KZT are NOT a feasible recommendation and must not be used as evidence of attainable profit. The patched version returns a no-feasible-plan diagnostic without optimized margin gain, plan chart or recommendations to plant that allocation.

## Valid control (2026-10-13 19:23)

Water cap 520,000 m³; modeled water 508,900 m³. Reported allocated areas 25+25+25+22+3=100 ha, max share 25%. This is a technical test with an expanded water budget, NOT evidence of 520,000 m³ legal/physical availability.

## Irrigation technology UI test (prospective hypothetical scenario)

Sidebar: Russian -> Researcher -> Assess my farm -> Saryagash District -> Next season. Crop: Corn. Inputs: area 20 ha; available seasonal water 107000 m³; used water 107000 m³; energy 8400 kWh; original irrigation furrow. Tariffs default water 0.845 KZT/m³ and electricity 45.9872 KZT/kWh (verify shown defaults before comparing).

Expand Economic contour. Yield 50 centners/ha, price 105000 KZT/t, **other** variable costs 326000 KZT/ha EXCLUDING water & electricity charges. Check irrigation-switch comparison: proposed irrigation Drip; yield change 0%; evidence text `Control scenario: yield effect assumed 0% (not empirically established)`; extra seasonal cost 15000 KZT/ha; energy change 0 kWh/ha. Press Calculate.

Expected under stated tariff defaults: furrow 5350 m³/ha; drip 4280 m³/ha (20% water savings; this is a scenario coefficient, not observed effect); water saving 1070 m³/ha (21400 m³ over 20 ha); before margin ~175165 KZT/ha; after margin ~161069 KZT/ha; scenario margin change ~-14096 KZT/ha; stress before ~40431 KZT/ha; stress after ~24926 KZT/ha; stress change ~-15505 KZT/ha. Changes on other inputs/tariffs can change numbers. The three shocks are automatically applied by the module: price -10%, yield -10%, costs +10%.

For a successful verification save PDFs from BOTH water optimization scenarios and irrigation comparisons; compare feasibility flags, visible charts, and presence/absence of claimed gains. Streamlit browser-based click-through was not run in the build environment. Economic assumptions and field treatment effects remain scenario inputs, not measurements.

## QA

2026-10-13: `python -m py_compile` passed for runtime files; `pytest -q tests` => **22 passed**. Local `build_pdf_report` smoke checks: rejected case excludes recommended crop structure and gain; feasible case retains recommended crop mix and economics. Full hosted-site walkthrough requires redeployment and user/browser testing.
