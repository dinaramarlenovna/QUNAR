import sys
import types
try:
    import streamlit
except ImportError:
    mock=types.ModuleType('streamlit')
    mock.cache_data=lambda *a, **k: (lambda f:f)
    mock.cache_resource=lambda *a, **k: (lambda f:f)
    sys.modules['streamlit']=mock
