# ACAS Client Testing Guide

## Overview

This is the Python client library and test suite for ACAS. It provides a programmatic interface to ACAS APIs and comprehensive integration tests for the entire ACAS platform.

## Technology Stack

- **Language**: Python 3.5+
- **Test Framework**: unittest
- **Dependencies**: requests, pandas, openpyxl, xlrd

## Installation

### For Development

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows

# Install in development mode
pip install -e .

# Install development dependencies
pip install -r requirements_dev.txt
```

## Running Tests

### Prerequisites

**CRITICAL**: The ACAS docker-compose stack MUST be running before executing tests.

1. **Start and verify ACAS services** - See [CLAUDE.md in acas repo](https://github.com/mcneilco/acas/blob/master/CLAUDE.md) for complete setup instructions (starting services, waiting for readiness, troubleshooting)

2. **Activate virtual environment** (REQUIRED before running tests):
   ```bash
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate  # On Windows
   ```

3. **Configure credentials** (if needed):
   - Tests use `tests/test_acasclient/test_000_creds_from_file_credentials`
   - Default credentials should work with fresh docker-compose stack

### Running All Tests

```bash
# From the acasclient directory
python -m unittest discover -s . -p "test_*.py" -v
```

### Running Specific Tests

```bash
# Run a specific test file
python -m unittest tests.test_acasclient -v

# Run a specific test class
python -m unittest tests.test_acasclient.TestAcasclient -v

# Run a specific test method
python -m unittest tests.test_acasclient.TestAcasclient.test_006_register_sdf -v
```

### Alternative: Using make

```bash
# Quick test run
make test

# Run with coverage
make test-all
```

## Test Structure

### Key Test Files

- `tests/test_acasclient.py`: Main integration test suite
  - Tests compound registration, bulk loading, experiment data, etc.
  - ~4700+ lines of comprehensive tests
- `tests/test_lsthing.py`: LSThings-specific tests
- `tests/test_acasclient/`: Test data directory
  - SDF files for compound registration tests
  - JSON fixtures for experiment loader tests
  - Credential files

### Test Data Files

Important test SDF files:

| File | Purpose |
|------|---------|
| `test_012_register_sdf.sdf` | Basic 2-compound registration test |
| `test_duplicate_structure_in_file.sdf` | Tests duplicate structure handling within one file |
| `test_047_register_sdf_with_salts.sdf` | Salt form registration |
| `test_simple_mol.sdf` | Single molecule for various tests |

### Test Configuration

Tests connect to:
- **Node API**: `http://localhost:3001` (defined in `ACAS_NODEAPI_BASE_URL`)
- **Roo Backend**: `http://localhost:8080` (via proxy through Node API)

## Common Test Workflows

### After Making Changes to Backend Code

If you've modified code in acas-roo-server:

1. **Rebuild and deploy** - See [CLAUDE.md in acas-roo-server repo](https://github.com/mcneilco/acas-roo-server/blob/master/CLAUDE.md) for build instructions and [CLAUDE.md in acas repo](https://github.com/mcneilco/acas/blob/master/CLAUDE.md) for docker-compose deployment

2. **Run tests** to verify your changes:
   ```bash
   cd acasclient
   source .venv/bin/activate  # Required before running tests
   python -m unittest discover -s . -p "test_*.py" -v
   ```

### Adding New Tests

When adding a new test:

1. **Create test data** if needed (e.g., new SDF file in `tests/test_acasclient/`)
2. **Add test method** to appropriate test class in `tests/test_acasclient.py`
3. **Use decorators** for dependencies:
   - `@requires_basic_cmpd_reg_load`: Test needs basic compounds loaded
   - `@requires_absent_basic_cmpd_reg_load`: Test needs fresh database
4. **Run the specific test** to verify:
   ```bash
   python -m unittest tests.test_acasclient.TestAcasclient.test_YOUR_NEW_TEST -v
   ```

## Test Coverage

The test suite covers:

- **Compound Registration**: SDF bulk loading, salt forms, stereochemistry
- **Parent/Lot Management**: Aliases, searches, structure searches
- **Experiment Data**: Dose-response, generic loaders, protocols
- **Data Export**: SDF export, Excel export, lot/parent queries
- **Edge Cases**: Duplicate structures, case sensitivity, validation errors

## Troubleshooting

### Connection or Service Issues

**Problem**: Tests fail with connection errors, timeouts, or 404s

**Solution**: See [CLAUDE.md in acas repo](https://github.com/mcneilco/acas/blob/master/CLAUDE.md) for troubleshooting docker-compose services

### Database State Issues

**Problem**: Tests fail due to existing data or constraints

**Solution**: Reset database for clean test run (see [acas CLAUDE.md](https://github.com/mcneilco/acas/blob/master/CLAUDE.md) for `docker compose down -v` command)

## Related Documentation

- **Roo Server Build**: [CLAUDE.md in acas-roo-server repo](https://github.com/mcneilco/acas-roo-server/blob/master/CLAUDE.md)
- **Docker Compose Setup**: [CLAUDE.md in acas repo](https://github.com/mcneilco/acas/blob/master/CLAUDE.md)

## Development Tips

### Test Output Verbosity

```bash
# Minimal output
python -m unittest discover -s . -p "test_*.py"

# Verbose output (recommended)
python -m unittest discover -s . -p "test_*.py" -v

# Very verbose with test docstrings
python -m unittest discover -s . -p "test_*.py" -v 2>&1 | less
```
