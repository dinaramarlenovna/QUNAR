# Mixed Farm Streamlit button-state fix

Base: QUNAR_v0.8.1_REPORT_COMPARISON_AND_COMPACT_EXPORT_2026-10-19.zip.

- Excluded `qmix_calculate` (button key) from navigation snapshots and restoration.
- Cleared any legacy persisted `qmix_calculate` before rendering mode 6.
- Preserved all other changes to app.py, including navigation persistence and compact report export.
- Python syntax checked. End-to-end Streamlit run not executed here.

Replace only root `app.py`; leave `core/reporting.py` from the prior update unchanged.
