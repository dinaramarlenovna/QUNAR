"""Run from the project root: python scripts/generate_a8_case.py"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The runner uses numeric model code. A cache-decorator-only shim is used
# if the Streamlit runtime is absent; it does not emulate widgets or test the UI.
try:
    import streamlit  # noqa: F401
except ImportError:
    from types import ModuleType
    stub = ModuleType('streamlit')
    stub.cache_data=lambda *a,**k: (lambda f:f)
    sys.modules['streamlit']=stub

from core.a8_reproducible_case import calculate_case, load_case, report_markdown

outdir=ROOT/'examples'/'a8_output'
outdir.mkdir(exist_ok=True)
r=calculate_case(load_case())
(outdir/'a8_maktaaral_case_results.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
(outdir/'a8_maktaaral_for_claude.md').write_text(report_markdown(r),encoding='utf-8')
print('Generated',outdir)
print('Normal: baseline',round(r['normal']['baseline']['contribution_margin_kzt']), 'optimized',round(r['normal']['optimized']['contribution_margin_kzt']))
print('Stress: unchanged baseline water feasible?',not r['stress']['unchanged_baseline_infeasible'])
print('Stress: optimized water',round(r['stress']['optimized']['water_field_delivery_m3']))
