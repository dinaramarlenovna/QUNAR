# NEW: sustainable-compromise optimizer mode (17 October 2026)

- Changed: `core/optimizer.py`: `objective_mode='sustainable'` with baseline-relative hard limits on **field-delivery water** and **partial GHG**, plus contribution-margin floor. One common accounting period and boundary is required for all emission inputs. Incomplete values reject the optimization (no silent proxy zeros).
- Changed: `app.py`: trilingual mode selector and columns for partial emission kg CO₂e/ha; adjustable maximum allowed margin decline; source/confirmation; results and report metadata.
- Added: `tests/test_sustainable_compromise.py` with 11 numerical tests, including 100-ha A8 scenario, missing values, infeasibility, and economic-mode regression.

Sustainability is **conditional**, not an empirical claim: the mode proves feasibility against its explicitly specified constraints. It cannot guarantee ecological superiority on unmodelled indicators such as full life-cycle emissions, water depletion or biodiversity. Weighted utility optimization is only over enumerated supported crop sets; avoid claims of global Pareto optimality.

Reference test inputs are in `QUNAR_СЦЕНАРИИ_ПРОВЕРКИ_УСТОЙЧИВОСТИ_2026-10-17.md` (provided separately).

All outputs remain identified `v0.8.1`. Historical RF code and trained data untouched. Public deployment has not been performed. Browser Streamlit is not verified in this sandbox; stage-test before deployment.
