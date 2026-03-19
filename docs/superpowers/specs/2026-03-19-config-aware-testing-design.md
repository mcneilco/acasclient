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

## Design Details

### Config Fetching

Fetch client config from existing endpoint at `/conf/conf.js`:

```python
def fetch_client_config(base_url="http://localhost:3000"):
    response = requests.get(f"{base_url}/conf/conf.js")
    js_content = response.text
    # Strip "window.conf=" prefix and parse JSON
    json_str = js_content.replace("window.conf=", "", 1).rstrip(";")
    return json.loads(json_str)
```

Config is cached at pytest session start via a session-scoped fixture.

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
      matrix:
        config-profile:
          - name: default
            compose-files: docker-compose.yml
          - name: unique-notebook
            compose-files: docker-compose.yml -f docker-compose.test-unique-notebook.yml
      fail-fast: false
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

- `acasclient/tests/config_checker.py` - replaced by conftest.py
- `acasclient/tests/test_duplicate_notebook.py` - consolidated into main test file

## Testing Strategy

1. Run tests locally with default config - config-dependent tests skip
2. Run tests locally with `docker-compose.test-unique-notebook.yml` - config-dependent tests run
3. CI runs both profiles in parallel

## Future Considerations

- **Server configs:** If needed later, implement an allowlist-based endpoint that exposes only safe, non-secret server config values, gated behind `RUN_SYSTEM_TEST=true` environment variable
- **Additional profiles:** Add to the CI matrix array (e.g., `strict-stereo`, `sso-auth`)
