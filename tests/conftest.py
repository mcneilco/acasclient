"""
Pytest configuration for acasclient tests.

Provides:
- requires_config marker for config-dependent tests
- Client config fetching from ACAS /conf/conf.js endpoint
"""

import json
import pytest
import requests


# Cached config - fetched once per session
_cached_config = None


def get_nested_value(d, path):
    """
    Get a nested value from a dictionary using dot notation.

    Args:
        d: Dictionary to search
        path: Dot-separated path (e.g., 'cmpdreg.serverSettings.uniqueNotebook')

    Returns:
        The value at the path, or None if not found
    """
    keys = path.split('.')
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def get_client_config(base_url="http://localhost:3000"):
    """
    Fetch client config from ACAS /conf/conf.js endpoint.

    Cached after first call. Returns empty dict on error (tests will skip).
    """
    global _cached_config
    if _cached_config is None:
        try:
            response = requests.get(f"{base_url}/conf/conf.js", timeout=5)
            response.raise_for_status()
            js_content = response.text
            # Strip "window.conf=" prefix and parse JSON
            json_str = js_content.replace("window.conf=", "", 1).rstrip(";")
            _cached_config = json.loads(json_str)
        except Exception as e:
            print(f"Warning: Could not fetch ACAS config from {base_url}/conf/conf.js: {e}")
            print("Tests requiring specific config will be skipped.")
            _cached_config = {}
    return _cached_config


def pytest_configure(config):
    """Register the requires_config marker."""
    config.addinivalue_line(
        "markers",
        "requires_config(**kwargs): skip test unless ACAS config matches requirements. "
        "Use dot notation for nested keys, e.g., "
        "@pytest.mark.requires_config(**{'cmpdreg.serverSettings.uniqueNotebook': True})"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Skip tests whose config requirements are not met."""
    for marker in item.iter_markers(name="requires_config"):
        config = get_client_config()
        for path, expected in marker.kwargs.items():
            actual = get_nested_value(config, path)
            if actual != expected:
                pytest.skip(f"Requires {path}={expected}, got {actual}")
