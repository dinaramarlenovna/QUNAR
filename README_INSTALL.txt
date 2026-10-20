QUNAR v0.8.1 - DARK THEME + AGRONOMIC DEPENDENCY REPAIR

Install all four files into the GitHub repository preserving directories:
app.py
core/agronomic_references.py
data/agronomic_reference_evidence.csv
data/agronomic_17_territories_audit.csv

Do not upload only app.py. The app imports core.agronomic_references and it requires the CSV data.

This patch builds on the last published dark-theme app.py and adds missing dependencies; it does not claim full Streamlit functional QA.
