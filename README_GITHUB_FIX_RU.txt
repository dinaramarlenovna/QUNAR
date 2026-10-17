QUNAR v0.8.1 - GitHub fix for ImportError on app.py line 24

Likely reason: new app.py imports forward_holdout_for_crop, but the
previous core/ml.py does not define that function.

1. On GitHub, in the SAME repository as app.py, open core/ml.py.
2. Replace core/ml.py with the file included in this patch.
   Do NOT upload ml.py into the repository root. Keep the core/ folder.
3. Optionally add scripts/verify_deployment_imports.py.
   From repository root run: python scripts/verify_deployment_imports.py
4. Commit changes to the branch that Streamlit deploys.
5. Wait for deployment/reboot in Streamlit Cloud and reload your app.
6. If ImportError remains, copy complete traceback from Streamlit Cloud
   logs including the LAST line ('cannot import name ...' or similar).

The code in this package comes from the last integrated v0.8.1 ZIP.
It does NOT change the mathematical model or coefficients.
No live GitHub repository or Streamlit logs were accessible to verify
whether the remote core/ml.py has an older version.
