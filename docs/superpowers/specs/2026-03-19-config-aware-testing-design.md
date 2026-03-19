# Config-Aware Testing Design

## Overview

Enable acasclient tests to require specific ACAS configurations and run in CI with multiple config profiles in parallel.

## Problem

Some tests (e.g., `test_019_duplicate_notebook_page`) only work when ACAS is configured with non-default settings (e.g., `uniqueNotebook=true`). Currently:
- No way to mark tests as requiring specific configs
- CI only runs with default config
- Tests requiring alternate configs would fail or need to be skipped manually

## Solution

Two-part solution:
1. **Pytest markers** to declare config requirements on tests
2. **CI matrix** to run parallel jobs with different config profiles

## Migration Strategy

**From unittest to pytest:**
- Add pytest as a dependency (pytest can run existing unittest-style tests unchanged)
- Create `conftest.py` with pytest-native config checking
- No backward compatibility needed - this is the first config-sensitive test
- Existing decorators (`@requires_basic_cmpd_reg_load`, etc.) continue to work under pytest
- CI switches from `python -m unittest discover` to `pytest`

**Reuse from existing code:**
- `get_nested_value()` utility from `config_checker.py` can be reused
- Error handling patterns (graceful fallback when server unreachable) should be preserved

## Design Details

### Config Fetching

Fetch client config from existing endpoint at `/conf/conf.js` (port 3000).

**Why this endpoint:**
- Already exists and serves client configuration to the browser
- No new acas code required
- Client configs are already public (served to browsers), so no security concern

**Note:** A dedicated `/api/systemTest/config` endpoint was considered but doesn't exist in the acas repo. Using the existing JS endpoint avoids requiring acas changes.

**Implementation:**

```python
def fetch_client_config(base_url="http://localhost:3000"):
    response = requests.get(f"{base_url}/conf/conf.js")
    js_content = response.text
    # Strip "window.conf=" prefix and parse JSON
    json_str = js_content.replace("window.conf=", "", 1).rstrip(";")
    return json.loads(json_str)
```

**Session-scoped caching:**

```python
_cached_config = None

def get_client_config(base_url="http://localhost:3000"):
    global _cached_config
    if _cached_config is None:
        try:
            response = requests.get(f"{base_url}/conf/conf.js", timeout=5)
            response.raise_for_status()
            js_content = response.text
            json_str = js_content.replace("window.conf=", "", 1).rstrip(";")
            _cached_config = json.loads(json_str)
        except Exception as e:
            print(f"Warning: Could not fetch ACAS config: {e}")
            print("Tests requiring specific config will be skipped.")
            _cached_config = {}
    return _cached_config
```

**Error handling:**
- If ACAS is unreachable, returns empty dict and tests with config requirements skip
- If config response is malformed, same behavior
- If a config path doesn't exist, `get_nested_value()` returns `None`, causing skip

**Scope limitation:** Only client configs are exposed. Server configs (which may contain secrets) are not accessible. This is intentional for security.

### Pytest Marker

Register custom marker in `conftest.py`:

```python
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_config(**kwargs): skip test unless ACAS config matches requirements"
    )
```

Skip logic via pytest hook:

```python
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    for marker in item.iter_markers(name="requires_config"):
        config = get_client_config()  # cached
        for path, expected in marker.kwargs.items():
            actual = get_nested_value(config, path)
            if actual != expected:
                pytest.skip(f"Requires {path}={expected}, got {actual}")
```

### Test Usage

```python
@pytest.mark.requires_config(**{"cmpdreg.serverSettings.uniqueNotebook": True})
def test_duplicate_notebook_rejected(self):
    ...
```

Path is relative to client config (no `client.` prefix needed).

### CI Workflow

GitHub Actions matrix strategy runs parallel jobs:

```yaml
jobs:
  acas:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - config-profile: default
            compose-files: docker-compose.yml
          - config-profile: unique-notebook
            compose-files: docker-compose.yml -f docker-compose.test-unique-notebook.yml

    steps:
      # ... existing checkout, python setup, install steps ...

      - name: Run docker compose up (${{ matrix.config-profile }})
        working-directory: acas
        run: |
          docker compose -f ${{ matrix.compose-files }} up -d

      # ... existing bob setup steps ...

      - name: Run tests (${{ matrix.config-profile }})
        run: pytest ./acasclient -v
```

Each job:
1. Starts ACAS with its compose files
2. Runs full test suite
3. Tests skip if their config requirements aren't met

**Benefit:** All tests run in all environments. Tests not specific to a config still run everywhere, catching regressions where a config change breaks unrelated functionality.

## File Changes

### New Files

- `acasclient/tests/conftest.py` - pytest configuration, marker registration, skip logic

### Modified Files

- `acasclient/tests/test_acasclient.py` - add marker to `test_019_duplicate_notebook_page`
- `acasclient/requirements_dev.txt` - add pytest dependency
- `acasclient/.github/workflows/run_tests.yml` - add matrix strategy
- `acasclient/tests/TESTING_WITH_CONFIG.md` - update documentation for pytest approach

### Deleted Files

- `acasclient/tests/config_checker.py` - logic moved to conftest.py (reuse `get_nested_value()`)
- `acasclient/tests/test_duplicate_notebook.py` - separate test file no longer needed; `test_019_duplicate_notebook_page` in main test file covers this
- `acasclient/tests/TESTING_WITH_CONFIG.md` - replaced by updated documentation

## Testing Strategy

1. Run tests locally with default config - config-dependent tests skip
2. Run tests locally with `docker-compose.test-unique-notebook.yml` - config-dependent tests run
3. CI runs both profiles in parallel

## Future Considerations

- **Server configs:** If needed later, implement an allowlist-based endpoint that exposes only safe, non-secret server config values, gated behind `RUN_SYSTEM_TEST=true` environment variable
- **Additional profiles:** Add to the CI matrix array (e.g., `strict-stereo`, `sso-auth`)
