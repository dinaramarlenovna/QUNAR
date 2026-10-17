# QŪNAR v0.8.1 - additional QA and corrected GHG boundaries (17.10.2026)

## Base / installation
- Base is the user's `QUNAR_v0_8_1_latest(1).zip` (extract its `QUNAR_v0_8_1/` folder).
- This ZIP is a **complete replacement for previous interim change-only ZIP files**, not an addition to them. Copy its paths into the **root of QUNAR_v0_8_1/**, retaining unmodified files.
- Do NOT publish before a local UI check with actual Streamlit and installed requirements.
- Visible version stays `v0.8.1`.

## Added since previous 43-test package
1. `core/carbon_scenarios.py`: forbid artificially reducing emissions by changing factors between scenarios; forbid comparing different accounting periods. Positive nitrogen/diesel/electricity needs positive corresponding factors.
2. `app.py`: explicit accounting-period selector (`Apr-Sep`, `calendar year`), both scenarios share a period. Annual enteric-methane factor is apportioned to Apr-Sep by the **assumption** of 183/365, not by a measured livestock seasonal emission profile; report records period, period fraction, factor and herd numbers.
3. `tests/test_ghg_period_and_factor_consistency.py`: seven regression tests for factors, periods, and prorating.
4. `tests/conftest.py`: testing-only cache-decorator shim when Streamlit is missing, enabling the numerical and report tests to run offline. **This does not test the UI** and is never imported by the deployed Streamlit app.

## Repeated checks
- `python -m pytest -q tests`: **50 passed**. Tests may run with a TEST-ONLY mock of Streamlit's caching decorators if actual Streamlit is not installed; excludes browser widgets.
- `python -m compileall -q app.py core tests`: passed.
- `PYTHONPATH=<test-only-streamlit-cache-shim> python smoke_test.py`: passed core numeric smoke test.
- Static internal import existence check: no missing `core.*` files.
- `data/analytical_panel.csv`, `core/ml.py`, `core/data.py`, `core/reporting.py`, `data/model_metrics_by_crop.csv` byte-identical to user's last full ZIP.

## Unresolved validation before publication
- Actual Streamlit / streamlit-folium UI test is **NOT complete**; packages could not be installed (network unavailable in this environment). Need a local startup and UI walkthrough with the application's required libraries.
- Remote NASA POWER live API calls cannot be performed here; polygon grid and weighted aggregation tested with deterministic fakes, not live remote samples.
- PDF/DOCX/XLSX generation tested programmatically using explicit three-language test payloads; visual inspection of all export layouts and current app paths remains to do.
- This is still a partial GHG inventory and an unvalidated future climate scenario, not proof of realized field emission reductions or farm profits.
- No absolute regional crop prices were supplied (price indices alone are insufficient).

## Safe integration checklist
1. Backup the deployed repository.
2. Start from `QUNAR_v0_8_1_latest(1).zip`, apply this **one** change-only package to project root (not earlier change-only patches).
3. Install requirements, run full pytest + `streamlit run app.py` locally.
4. UI: KK/RU/EN; small/large polygon; both CMIP6 scenarios; absent water limit and binding/infeasible water cap; A9 yield evidence; optional partial GHG season/year with livestock; export PDF, Word, Excel and check numbers match the UI.
5. Only then one deploy to Streamlit Community Cloud.
