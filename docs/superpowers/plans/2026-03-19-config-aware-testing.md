# Config-Aware Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable acasclient tests to require specific ACAS configurations and run in CI with multiple config profiles in parallel.

**Architecture:** Pytest marker with runtime config checking. Tests declare config requirements via `@pytest.mark.requires_config()`. A pytest hook fetches client config from `/conf/conf.js` at session start, skipping tests whose requirements aren't met. CI runs parallel matrix jobs with different docker-compose configurations.

**Tech Stack:** Python, pytest, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-03-19-config-aware-testing-design.md`

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `tests/conftest.py` | Create | Pytest config: marker registration, config fetching, skip logic |
| `tests/test_acasclient.py` | Modify | Change decorator import to pytest marker |
| `requirements_dev.txt` | Modify | Add pytest dependency |
| `.github/workflows/run_tests.yml` | Modify | Add matrix strategy for config profiles |
| `tests/config_checker.py` | Delete | Replaced by conftest.py (untracked file) |

**External dependency:** `docker-compose.test-unique-notebook.yml` exists in the `acas` repo (checked out by CI workflow).

---

### Task 1: Add pytest dependency

**Files:**
- Modify: `requirements_dev.txt`

- [ ] **Step 1: Add pytest to requirements_dev.txt**

Add this line at the end of the file:
```
pytest>=7.0.0
```

- [ ] **Step 2: Install pytest locally to verify**

Run: `cd /Users/frost/Projects/ACAS/acasclient && source .venv/bin/activate && pip install pytest>=7.0.0`

Expected: Successfully installed pytest

- [ ] **Step 3: Commit**

```bash
git add requirements_dev.txt
git commit -m "Add pytest dependency for config-aware testing"
```

---

### Task 2: Create conftest.py with config checking

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Create conftest.py with config fetching and marker**

```python
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
```

- [ ] **Step 2: Verify file was created**

Run: `ls -la /Users/frost/Projects/ACAS/acasclient/tests/conftest.py`

Expected: File exists

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "Add pytest conftest.py with requires_config marker"
```

---

### Task 3: Update test_acasclient.py to use pytest marker

**Files:**
- Modify: `tests/test_acasclient.py:26` (import line)
- Modify: `tests/test_acasclient.py:4705` (decorator line)

- [ ] **Step 1: Add pytest import and remove config_checker import**

Remove line 26:
```python
from tests.config_checker import requires_config
```

Add near the other imports (e.g., after line 5):
```python
import pytest
```

- [ ] **Step 2: Update decorator on test_019_duplicate_notebook_page**

Replace line 4705:
```python
    @requires_config(**{'client.cmpdreg.serverSettings.uniqueNotebook': True})
```

With:
```python
    @pytest.mark.requires_config(**{'cmpdreg.serverSettings.uniqueNotebook': True})
```

Note: Remove `client.` prefix since we're now fetching client config directly.

- [ ] **Step 3: Run pytest to verify marker works**

Run: `cd /Users/frost/Projects/ACAS/acasclient && source .venv/bin/activate && pytest tests/test_acasclient.py::TestAcasclient::test_019_duplicate_notebook_page -v`

Expected (depends on ACAS state):
- If ACAS not running or uniqueNotebook=false: `SKIPPED` with "Requires cmpdreg.serverSettings.uniqueNotebook=True, got ..."
- If ACAS running with uniqueNotebook=true: Test runs (may pass or fail based on test logic)

- [ ] **Step 4: Commit**

```bash
git add tests/test_acasclient.py
git commit -m "Switch test_019 to pytest.mark.requires_config marker"
```

---

### Task 4: Update CI workflow with matrix strategy

**Files:**
- Modify: `.github/workflows/run_tests.yml`

- [ ] **Step 1: Add matrix strategy after runs-on**

After line 10 (`runs-on: ubuntu-latest`), add:
```yaml
    strategy:
      fail-fast: false
      matrix:
        include:
          - config-profile: default
            compose-files: docker-compose.yml
          - config-profile: unique-notebook
            compose-files: docker-compose.yml -f docker-compose.test-unique-notebook.yml
```

- [ ] **Step 2: Update docker compose step to use matrix variable**

Replace lines 52-56:
```yaml
      - name: Run docker compose up - assumes racas-oss:${{ env.ACAS_TAG }} and acas-roo-server-oss:${{ env.ACAS_TAG }}-indigo exist and are up to date
        id: dockerComposeUp
        working-directory: acas
        run: |
          docker compose -f "docker-compose.yml" up -d
```

With:
```yaml
      - name: Run docker compose up (${{ matrix.config-profile }}) - assumes racas-oss:${{ env.ACAS_TAG }} and acas-roo-server-oss:${{ env.ACAS_TAG }}-indigo exist and are up to date
        id: dockerComposeUp
        working-directory: acas
        run: |
          docker compose -f ${{ matrix.compose-files }} up -d
```

- [ ] **Step 3: Update test runner from unittest to pytest**

Replace line 68:
```yaml
        run: python -m unittest discover -s ./acasclient -p "test_*.py" -v
```

With:
```yaml
        run: pytest ./acasclient/tests -v
```

- [ ] **Step 4: Update test step name with profile**

Replace line 67:
```yaml
      - name: Run tests
```

With:
```yaml
      - name: Run tests (${{ matrix.config-profile }})
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/run_tests.yml
git commit -m "Add CI matrix for config profiles, switch to pytest"
```

---

### Task 5: Delete obsolete config_checker.py

**Files:**
- Delete: `tests/config_checker.py` (untracked file)

- [ ] **Step 1: Remove config_checker.py**

```bash
cd /Users/frost/Projects/ACAS/acasclient
rm tests/config_checker.py
```

Note: File is untracked, so use `rm` not `git rm`.

- [ ] **Step 2: Verify removal**

```bash
ls tests/config_checker.py
```

Expected: "No such file or directory"

- [ ] **Step 3: No commit needed (file was untracked)**

---

### Task 6: Verify full test suite runs with pytest

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite with pytest**

Run: `cd /Users/frost/Projects/ACAS/acasclient && source .venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | head -100`

Expected: Tests run, config-dependent tests skip (unless ACAS has uniqueNotebook=true)

- [ ] **Step 2: Verify test_019 specifically skips**

Run: `pytest tests/test_acasclient.py -k "test_019" -v`

Expected: `SKIPPED` with config requirement message

- [ ] **Step 3: No commit needed (verification only)**

---

### Task 7: Final commit with all changes

- [ ] **Step 1: Review all changes**

```bash
git log --oneline -5
git status
```

Expected: Clean working tree, 5-6 commits for this feature

- [ ] **Step 2: Tag or note completion**

Feature is complete. Ready for PR or merge.
