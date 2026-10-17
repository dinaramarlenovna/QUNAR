"""Permit numeric headless regression tests without the Streamlit UI dependency.

This shim replaces cache decorators *only when Streamlit is not installed*.
It does not test or emulate Streamlit widgets and is never deployed as app code.
"""
import importlib.util
import sys
import types

if importlib.util.find_spec('streamlit') is None:
    stub = types.ModuleType('streamlit')
    def identity_cache(*args, **kwargs):
        def decorate(function):
            return function
        return decorate
    stub.cache_data = identity_cache
    stub.cache_resource = identity_cache
    sys.modules['streamlit'] = stub
