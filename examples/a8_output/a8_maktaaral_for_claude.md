# A8 — Maktaaral district, 100 ha: reproducible illustrative scenario

**Status: hypothetical counterfactual, NOT verified farm adoption or actual savings.**
Input SHA-256: `fffd384358faaeaf3dcc4ae3099f20fb004a421f3b55a4d8d68c0820fa884f9a`.

## Input sources and assumptions

BNS Turkestan producer prices **2025**, district crop yields averaged over **2023–2025**,
irrigation norms from QŪNAR Order No. 108-NQ **2025**, surface irrigation (field delivery).
The 100-ha baseline, 750,000 m³ water budget, variable costs, tariffs, pumping intensity,
fertilizer N, diesel, and grid emission factor are **illustrative assumptions**, NOT observed regional means.
Neither calculated contribution margins nor partial emissions are verified impacts.

| Crop | Yield, centners/ha | BNS 2025 price, KZT/t | Water, m³/ha | Assumed other costs, KZT/ha |
|---|---:|---:|---:|---:|
| Cotton | 26.03 | 255 373 | 8 400 | 350 000 |
| Corn | 44.07 | 99 844 | 7 450 | 210 000 |
| Wheat | 20.70 | 100 044 | 4 100 | 120 000 |

## Allocations and results

| Parameter | Normal baseline | Normal optimized | Stress baseline (infeasible) | Stress optimized |
|---|---:|---:|---:|---:|
| Water limit (m³) | 750 000 | 750 000 | 600 000 | 600 000 |
| Irrigation delivery (m³) | 725 500 | 750 000 | 725 500 | 600 000 |
| Pumping electricity (kWh) | 511 543 | 528 818 | 511 543 | 423 054 |
| Revenue (KZT) | 50 582 251 | 53 873 451 | 45 524 026 | 36 506 915 |
| Variable costs (KZT) | 43 360 034 | 45 742 510 | 47 696 037 | 39 695 538 |
| Contribution margin (KZT) | 7 222 217 | 8 130 941 | -2 172 012 | -3 188 623 |
| Partial GHG (kg CO₂e) | 364 441.9 | 376 780.4 | 364 441.9 | 303 120.8 |
| Water feasible | Yes | Yes | **No** | Yes |

| Crop share (ha) | Normal baseline | Normal optimized | Stress baseline | Stress optimized |
|---|---:|---:|---:|---:|
| Cotton | 50.00 | 60.00 | 50.00 | 41.85 |
| Corn | 30.00 | 24.48 | 30.00 | 3.00 |
| Wheat | 20.00 | 15.52 | 20.00 | 55.15 |

## Interpretation

- In **normal water conditions**, both structures are feasible; scenario margin difference is 908 725 KZT and field-delivery water change is 24 500 m³.
- Stress: water limit falls by 20% to 600 000 m³; yields fall by 10%; **all variable costs**, including water and electricity, increase by 10%.
- Unchanged stressed baseline exceeds its limit by 125 500 m³. Its margin and GHG numbers are **infeasible counterfactuals**, not an achievable farm outcome.
- Stress optimized allocation meets the limit; irrigation field delivery differs from the infeasible baseline by -125 500 m³, and partial GHG difference is -61 321.1 kg CO₂e. Both comparisons are **counterfactual vs infeasible baseline**, NOT achieved water or GHG savings.
- Crop mix changes may also alter pumping electricity and partial CO₂e; the result is not a measurement of emissions mitigation.
- The 24.7m / 23.8m KZT claims in earlier dissertation drafts have **not** been reproduced by this separate case and must not be substituted.
- Price reference, costs, yield and climate are not a validated 2026 forecast; stress effects are imposed, **NOT** inferred from CMIP6 or NASA data.

## Traceability

Prices: BNS 2025; district yields: 2023–2025; crop water reference: Order 108-NQ, QUNAR implementation; production costs, tariffs, energy/GHG activities, baseline and budgets: explicit hypothetical assumptions. All output is an illustrative scenario.

Excluded: No observed farm profit, no verified farm water quota, no actual basin savings, no out-of-sample yield forecast, no realized emissions reductions, no full life-cycle GHG or capital expenditure.
