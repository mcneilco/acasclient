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

1. **Start ACAS services** (see [CLAUDE.md in acas repo](https://github.com/mcneilco/acas/blob/master/CLAUDE.md)):
   ```bash
   cd ../acas
   docker-compose up -d
   ```

2. **Wait for services to be ready** (the acas container waits for roo to finish starting):
   ```bash
   # Wait up to 120 seconds for ACAS API (POSIX-safe one-liner)
   counter=0; wait=120; while ! curl --output /dev/null --silent --head --fail http://localhost:3001/api/authors && [ "$counter" -lt "$wait" ]; do sleep 1; counter=$((counter+1)); done; if [ "$counter" -ge "$wait" ]; then echo "ACAS failed to start"; exit 1; else echo "ACAS started!"; fi
   ```

3. **Activate virtual environment** (REQUIRED before running tests):
   ```bash
   cd ../acasclient
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate  # On Windows
   ```

4. **Verify services are healthy** (optional):
   ```bash
   # Check all services are running
   docker-compose ps

   # Test Node API endpoint (default: http://localhost:3001)
   curl http://localhost:3001/api/healthcheck

   # Test Roo backend (default: http://localhost:8080)
   curl http://localhost:8080/acas/api/healthcheck
   ```

5. **Configure credentials** (if needed):
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

### After Making Changes to Roo Server

This is the typical workflow when you've modified Java code in acas-roo-server:

1. **Build new roo Docker image**:
   ```bash
   cd ../acas-roo-server
   docker build --build-arg CHEMISTRY_PACKAGE=indigo -t mcneilco/acas-roo-server-oss:dev -f Dockerfile-multistage .
   ```

   **Note**: The `--build-arg CHEMISTRY_PACKAGE=indigo` is required for local development to match docker-compose configuration.

2. **Update docker-compose to use new image**:
   ```bash
   cd ../acas
   # Edit docker-compose.yml to change roo service image to :dev
   # OR create docker-compose.override.yml (preferred)
   ```

3. **Restart services**:
   ```bash
   # Quick restart (preserves database)
   docker-compose restart roo

   # Full restart (preserves database)
   docker-compose down && docker-compose up -d

   # Clean restart with fresh database (DESTRUCTIVE - loses all data)
   docker-compose down -v && docker-compose up -d
   ```

4. **Wait for services to be ready**:
   ```bash
   # Wait for ACAS API (POSIX-safe one-liner, up to 120 seconds)
   counter=0; wait=120; while ! curl --output /dev/null --silent --head --fail http://localhost:3001/api/authors && [ "$counter" -lt "$wait" ]; do sleep 1; counter=$((counter+1)); done; if [ "$counter" -ge "$wait" ]; then echo "ACAS failed to start"; exit 1; else echo "ACAS started!"; fi
   ```

5. **Activate virtual environment and run tests**:
   ```bash
   cd ../acasclient
   source .venv/bin/activate  # Required before running tests
   python -m unittest discover -s . -p "test_*.py" -v
   ```

### Testing Specific Bulk Loader Changes

If you've changed bulk loader code (like the summary reporting):

```bash
# Run tests related to SDF registration and bulk loading
python -m unittest tests.test_acasclient.TestAcasclient.test_006_register_sdf -v
python -m unittest tests.test_acasclient.TestCmpdReg.test_013_unique_parent_alias_tests -v
python -m unittest tests.test_acasclient.TestCmpdReg.test_015_duplicate_structure_within_file -v
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

### Tests Fail Immediately

**Problem**: Connection refused or 404 errors

**Solution**: Ensure docker-compose services are running
```bash
cd ../acas
docker-compose ps  # All services should be "Up"
docker-compose logs roo  # Check for startup errors
```

### Tests Timeout

**Problem**: Tests hang or timeout after ~30 seconds

**Solution**: Services may be overloaded or still starting
```bash
# Check service health
curl http://localhost:3001/api/healthcheck
curl http://localhost:8080/acas

# Restart services with more memory
docker-compose down
# Edit docker-compose.yml to increase CATALINA_OPTS memory settings
docker-compose up -d
```

### Database State Issues

**Problem**: Tests fail due to existing data or constraints

**Solution**: Reset database (DESTRUCTIVE - loses all data)
```bash
cd ../acas
docker-compose down -v  # Removes volumes
docker-compose up -d
# Wait for services to initialize
cd ../acasclient
python -m unittest discover -s . -p "test_*.py" -v
```

### Specific Test Failures

**Problem**: Only certain tests fail (e.g., bulk loader tests)

**Solution**: Check if your roo changes are properly deployed
```bash
# Verify you're using the correct image
cd ../acas
docker-compose images | grep roo

# Check roo logs for Java exceptions
docker-compose logs roo | grep -i exception

# Rebuild and redeploy
cd ../acas-roo-server
docker build -t mcneilco/acas-roo-server-oss:dev -f Dockerfile-multistage .
cd ../acas
docker-compose restart roo
```

## Related Documentation

- **Roo Server Build**: [CLAUDE.md in acas-roo-server repo](https://github.com/mcneilco/acas-roo-server/blob/master/CLAUDE.md)
- **Docker Compose Setup**: [CLAUDE.md in acas repo](https://github.com/mcneilco/acas/blob/master/CLAUDE.md)

## Development Tips

### Fast Iteration Loop

For rapid testing during development:

```bash
# Terminal 1: Watch roo logs
cd ../acas && docker-compose logs -f roo

# Terminal 2: Rebuild and restart roo after code changes
cd ../acas-roo-server && \
  docker build --build-arg CHEMISTRY_PACKAGE=indigo -t mcneilco/acas-roo-server-oss:dev -f Dockerfile-multistage . && \
  cd ../acas && \
  docker-compose restart roo

# Terminal 3: Run tests
cd ../acasclient && \
  python -m unittest tests.test_acasclient.TestCmpdReg.test_YOUR_TEST -v
```

### Test Output Verbosity

```bash
# Minimal output
python -m unittest discover -s . -p "test_*.py"

# Verbose output (recommended)
python -m unittest discover -s . -p "test_*.py" -v

# Very verbose with test docstrings
python -m unittest discover -s . -p "test_*.py" -v 2>&1 | less
```
