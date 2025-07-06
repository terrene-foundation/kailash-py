# Test Organization Policy

This document defines the test organization standards for the Kailash SDK. It should be read together with [regression-testing-strategy.md](regression-testing-strategy.md).

## Directory Structure

All tests MUST be organized into the following three-tier structure:

```
tests/
├── unit/           # Tier 1: Fast, isolated tests
├── integration/    # Tier 2: Component interaction tests
├── e2e/           # Tier 3: End-to-end scenarios
├── utils/          # Test utilities (docker_config.py, setup scripts)
├── fixtures/       # Shared test data
├── infrastructure/ # Infrastructure tests (optional, for testing deployments)
└── conftest.py    # Global pytest configuration
```

## Test Classification Rules

### Tier 1: Unit Tests (`tests/unit/`)
- **Execution time**: < 1 second per test
- **Dependencies**: NONE (no Docker, Redis, Ollama, PostgreSQL)
- **Markers**: `@pytest.mark.unit` or no markers
- **Purpose**: Test individual components in isolation
- **CI/CD**: Run on every commit

### Tier 2: Integration Tests (`tests/integration/`)
- **Execution time**: < 30 seconds per test
- **Dependencies**: MUST use REAL Docker services (PostgreSQL, Redis, Ollama)
- **Markers**: `@pytest.mark.integration`
- **Purpose**: Test component interactions with REAL infrastructure
- **CI/CD**: Run on every PR
- **CRITICAL**: NO MOCKING ALLOWED - Use real Docker services via tests/utils/docker_config.py

### Tier 3: E2E Tests (`tests/e2e/`)
- **Execution time**: Any duration
- **Dependencies**: MUST use REAL Docker services (PostgreSQL, Redis, Ollama)
- **Markers**: `@pytest.mark.e2e`, `@pytest.mark.slow`, `@pytest.mark.requires_*`
- **Purpose**: Test complete business scenarios with REAL infrastructure
- **CI/CD**: Run nightly or on release
- **CRITICAL**: NO MOCKING ALLOWED - Use real Docker services via tests/utils/docker_config.py

## File Organization Rules

### 1. NO Scattered Test Files
- ❌ Never place test files directly in `tests/`
- ❌ Never create `test_*` directories outside the tier structure
- ✅ All test files must be in `unit/`, `integration/`, or `e2e/`

### 2. Mirror Source Structure
Tests should mirror the source code structure:
```
src/kailash/nodes/ai/llm_agent.py → tests/unit/nodes/ai/test_llm_agent.py
src/kailash/runtime/local.py      → tests/unit/runtime/test_local.py
```

### 3. Comprehensive Tests
If a test covers multiple components or real-world scenarios:
- Unit version → `tests/unit/component/test_feature.py`
- Integration version → `tests/integration/component/test_feature_comprehensive.py`
- E2E version → `tests/e2e/test_feature_real_world.py`

## Critical Testing Rules

### NO MOCKING IN INTEGRATION AND E2E TESTS

**This is a MANDATORY rule for Tier 2 (Integration) and Tier 3 (E2E) tests:**

1. **Integration Tests (`tests/integration/`)** - MUST use REAL Docker services
   - ✅ Use real PostgreSQL via `tests/utils/docker_config.py`
   - ✅ Use real Redis via `tests/utils/docker_config.py`
   - ✅ Use real Ollama for LLM testing
   - ❌ NEVER mock database connections
   - ❌ NEVER use `unittest.mock` or `patch` for infrastructure
   - ❌ NEVER use fake/in-memory databases

2. **E2E Tests (`tests/e2e/`)** - MUST use REAL Docker services
   - Same rules as integration tests
   - Test complete workflows with real data

3. **Only Unit Tests (`tests/unit/`)** may use mocks
   - This is the ONLY place where mocking is allowed
   - Mock external dependencies to test in isolation

**Example of CORRECT Integration Test:**
```python
# tests/integration/test_admin_nodes.py
from tests.utils.docker_config import get_postgres_connection_string

class TestAdminIntegration:
    def test_user_creation(self):
        # CORRECT: Using real database
        db_config = {
            "connection_string": get_postgres_connection_string(),
            "database_type": "postgresql"
        }
        user_mgmt = UserManagementNode()
        result = user_mgmt.execute(database_config=db_config, ...)
```

**Example of INCORRECT Integration Test:**
```python
# WRONG - Never do this in integration tests!
from unittest.mock import patch

class TestAdminIntegration:
    @patch("database.connect")  # ❌ NO MOCKING!
    def test_user_creation(self, mock_db):
        ...
```

## Prohibited Patterns

### 1. NO SKIPPED TESTS - ZERO TOLERANCE POLICY
**Skipped tests are zombie tests that will never run again. They are strictly forbidden.**

- ❌ NEVER use `pytest.skip()` or `@pytest.mark.skip`
- ❌ NEVER use `@pytest.mark.skipif` conditionally
- ❌ NEVER create tests that check for availability and skip

**Instead:**
- ✅ If a test requires external dependencies (DB, API), put it in `integration/` or `e2e/`
- ✅ If a test is not ready, don't commit it
- ✅ If a feature is removed, remove its tests
- ✅ If a test fails intermittently, fix it or remove it

**Examples of FORBIDDEN patterns:**
```python
# ❌ NEVER DO THIS
def test_mysql_feature(self):
    if not mysql_available:
        pytest.skip("MySQL not available")  # FORBIDDEN!

# ❌ NEVER DO THIS
@pytest.mark.skipif(not has_gpu, reason="GPU not available")  # FORBIDDEN!
def test_gpu_processing():
    pass

# ❌ NEVER DO THIS
@pytest.mark.skip(reason="Not implemented yet")  # FORBIDDEN!
def test_future_feature():
    pass
```

**Correct approach:**
```python
# ✅ Put in integration/ with proper Docker setup
@pytest.mark.integration
@pytest.mark.requires_mysql
def test_mysql_feature(self):
    # Test will only run when MySQL Docker is available
    pass

# ✅ Remove or don't commit unfinished tests
# Don't create placeholder tests
```

### 2. Duplicate Test Directories
Never create these directories:
- `tests/test_*` (e.g., `tests/test_workflow/`)
- `tests/middleware/`, `tests/nodes/`, etc. (use `tests/unit/middleware/`)
- Any test directory outside the three-tier structure

### 3. Misclassified Tests
- Never put slow tests in `unit/`
- Never put Docker-dependent tests in `unit/` or unmarked `integration/`
- Always use appropriate pytest markers

### 4. Scattered Test Support Files
Keep test support files organized:
- Test utilities & configs → `tests/utils/`
- Shared fixtures → `tests/fixtures/`
- Infrastructure tests → `tests/infrastructure/` (if testing deployments)

## Test Markers

Required markers for proper classification:

```python
# Unit test (Tier 1) - no marker needed
def test_simple_function():
    pass

# Integration test (Tier 2)
@pytest.mark.integration
def test_component_interaction():
    pass

# E2E test (Tier 3)
@pytest.mark.e2e
@pytest.mark.requires_docker
def test_full_scenario():
    pass

# Slow test (automatically Tier 3)
@pytest.mark.slow
def test_performance_benchmark():
    pass
```

## Migration Checklist

When adding or moving tests:

1. **Determine the correct tier** based on dependencies and execution time
2. **Use the appropriate directory** (`unit/`, `integration/`, or `e2e/`)
3. **Mirror the source structure** for easy navigation
4. **Add proper markers** for classification
5. **Remove any duplicate** or misplaced versions
6. **Update imports** if moving existing tests

## Essential Files Only

The `tests/` directory should contain ONLY:
- `unit/`, `integration/`, `e2e/` directories
- `conftest.py` - Global pytest configuration
- `utils/` - Test utilities and configuration (docker_config.py, setup scripts)
- `fixtures/` - Shared test fixtures
- `infrastructure/` - Infrastructure tests (optional)
- `README.md` - Test suite documentation
- `CLAUDE.md` - AI assistant instructions

All other files should be removed or properly organized.

## Enforcement

This policy is enforced through:
1. CI/CD checks that fail on misplaced tests
2. Regular test organization audits
3. Code review requirements
4. Automated test discovery based on directory structure
