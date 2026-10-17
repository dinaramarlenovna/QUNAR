# QŪNAR v0.8.1 - current full source package

This is the current full-source QŪNAR v0.8.1 research-prototype build.

Main strengthened functions:
- resource-climate / balanced / economic-priority farm-structure optimization;
- optional current-structure input and before/after economic-resource comparison;
- water-energy scenario savings and payback when investment is supplied;
- evidence grading and explicit reference-data provenance;
- user-defined climate/water stress tests;
- crop-specific grouped validation, leave-one-district-out spatial stress testing and empirical prediction-uncertainty bands;
- within-field crop placement is not implemented in the current build; it is reserved for future development when field-level spatial evidence is available.

See `MODEL_IMPROVEMENTS_v0_8_1.md` and `ECONOMIC_REFERENCE_DATA_NOTE_v0_8_1.md` for methodological limits.

## Дополнение от 17.10.2026 — единый сценарий ресурсов

Актуальная полная рабочая сборка включает `core/integrated_scenarios.py`, `core/scenario_ui.py` и панель в `app.py`: связанное сравнение «сейчас/после» для воды, насосной электроэнергии, частичного CO₂e и экономической маржи (при полных данных), а также сценарии CH₄ пищеварения и навоза, дизеля, азота и сетевой энергии. Новые сценарии включены в экспортный `report_payload`. Установить весь ZIP достаточно один раз; прежние патчи НЕ нужны. Офлайн QA: 182 теста, браузерный Streamlit/live NASA не проверены. Подробно: `README_ЕДИНЫЕ_СЦЕНАРИИ_2026-10-17.md`.
