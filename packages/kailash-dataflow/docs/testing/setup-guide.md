# DataFlow Testing Setup Guide

## Purpose
This guide gets you from zero to running DataFlow tests in under 5 minutes. Follow these steps to configure pytest, set up your test database, and write your first test.

---

## Prerequisites

**Required**:
- Python 3.9+
- pip or poetry
- PostgreSQL, MySQL, or SQLite

**Recommended**:
- Docker (for PostgreSQL test database)
- pytest-asyncio knowledge (basic async/await understanding)

---

## 1. Install Testing Dependencies

```bash
# Install pytest and async support
pip install pytest pytest-asyncio pytest-dotenv

# Install DataFlow
pip install kailash-dataflow

# Optional: Install database drivers
pip install asyncpg  # PostgreSQL
pip install aiomysql  # MySQL
# SQLite is built-in to Python
```

**Why pytest-dotenv?** Automatically loads `.env` file before tests run, ensuring API keys and database URLs are available.

---

## 2. Configure pytest

Create `pytest.ini` in your project root:

```ini
[pytest]
# Async test configuration
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function

# Test discovery
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Markers
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (real database)
    e2e: End-to-end tests (full workflows)
    slow: Slow tests (>5 seconds)

# Environment variables
env_files = .env

# Output options
addopts =
    -v
    --strict-markers
    --tb=short
    --asyncio-mode=auto
```

**Key Settings**:
- `asyncio_mode = auto` - Automatically detects async tests
- `asyncio_default_fixture_loop_scope = function` - **CRITICAL**: Fresh event loop per test prevents "event loop is closed" errors
- `env_files = .env` - Loads environment variables from `.env`

---

## 3. Set Up Test Database

### Option A: PostgreSQL with Docker (Recommended)

```bash
# Start PostgreSQL test database
docker run -d \
  --name dataflow-test-postgres \
  -e POSTGRES_USER=test_user \
  -e POSTGRES_PASSWORD=test_password \
  -e POSTGRES_DB=dataflow_test \
  -p 5434:5432 \
  postgres:16-alpine

# Verify it's running
docker ps | grep dataflow-test-postgres
```

**Why port 5434?** Avoids conflicts with production PostgreSQL on default port 5432.

### Option B: SQLite (Fastest for Unit Tests)

```python
# No setup needed - use in-memory database
db = DataFlow(":memory:")

# Or file-based for persistence
db = DataFlow("sqlite:///test_database.db")
```

**Trade-offs**:
- SQLite: Fast, no setup, but lacks some PostgreSQL features
- PostgreSQL: Production-like, full features, but requires Docker/server

### Option C: MySQL with Docker

```bash
# Start MySQL test database
docker run -d \
  --name dataflow-test-mysql \
  -e MYSQL_ROOT_PASSWORD=root_password \
  -e MYSQL_DATABASE=dataflow_test \
  -e MYSQL_USER=test_user \
  -e MYSQL_PASSWORD=test_password \
  -p 3307:3306 \
  mysql:8.0

# Verify it's running
docker ps | grep dataflow-test-mysql
```

---

## 4. Configure Environment Variables

Create `.env` in your project root:

```bash
# Test database URLs
TEST_DATABASE_URL=postgresql://test_user:test_password@localhost:5434/dataflow_test
TEST_MYSQL_URL=mysql://test_user:test_password@localhost:3307/dataflow_test
TEST_SQLITE_URL=sqlite:///test_database.db

# Test mode (optional - auto-detected)
DATAFLOW_TEST_MODE=true

# Connection pool settings (reduce for tests)
DATAFLOW_POOL_SIZE=1
DATAFLOW_MAX_OVERFLOW=1
```

**Why small pool sizes?** Tests create many DataFlow instances. Small pools prevent connection exhaustion.

---

## 5. Configure Event Loop Fixture

Create `conftest.py` in your `tests/` directory:

```python
"""Shared pytest fixtures for DataFlow testing."""
import asyncio
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="function")
def event_loop():
    """Create a fresh event loop for each test.

    CRITICAL: Function scope prevents "event loop is closed" errors.
    Each test gets its own isolated event loop.
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)

    yield loop

    # Cleanup: Cancel remaining tasks
    try:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass
    finally:
        loop.close()
        asyncio.set_event_loop(None)


@pytest.fixture(scope="function")
async def db():
    """DataFlow instance with automatic cleanup.

    Use this fixture in your tests for automatic pool cleanup.
    Function scope ensures clean slate for each test.
    """
    database_url = "postgresql://test_user:test_password@localhost:5434/dataflow_test"

    # DataFlow auto-detects pytest and enables test mode
    db = DataFlow(database_url)

    yield db

    # Cleanup: Close all connection pools
    await db.cleanup_all_pools()
```

**Why This Pattern Works**:
1. **Function-scoped event loop** - Fresh loop per test prevents contamination
2. **Function-scoped DataFlow** - Clean database state per test
3. **Automatic cleanup** - `cleanup_all_pools()` prevents pool leaks
4. **Test mode auto-detection** - DataFlow detects pytest and optimizes for testing

---

## 6. Write Your First Test

Create `tests/test_basic_crud.py`:

```python
"""Basic CRUD operations test."""
import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime


@pytest.mark.asyncio
async def test_user_create_read(db):
    """Test creating and reading a user record."""

    # Define model
    @db.model
    class User:
        name: str
        email: str
        active: bool = True

    # Create user
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-1",
        "name": "Alice",
        "email": "alice@example.com"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

    # Verify creation
    assert results["create"]["id"] == "user-1"
    assert results["create"]["name"] == "Alice"
    assert results["create"]["email"] == "alice@example.com"
    assert results["create"]["active"] is True

    # Read user back
    workflow2 = WorkflowBuilder()
    workflow2.add_node("UserReadNode", "read", {
        "id": "user-1"
    })

    results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})

    # Verify read
    assert results2["read"]["id"] == "user-1"
    assert results2["read"]["name"] == "Alice"
```

---

## 7. Run Your Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_basic_crud.py

# Run with output
pytest tests/ -v

# Run only unit tests
pytest tests/ -m unit

# Run with coverage
pytest tests/ --cov=dataflow
```

**Expected Output**:
```
tests/test_basic_crud.py::test_user_create_read PASSED [100%]

================ 1 passed in 0.45s ================
```

---

## 8. Verify Setup is Working

Run this diagnostic test to verify everything is configured correctly:

```python
"""Diagnostic test to verify DataFlow testing setup."""
import pytest
from dataflow import DataFlow


@pytest.mark.asyncio
async def test_dataflow_setup_diagnostic(db):
    """Verify DataFlow testing setup is working correctly."""

    # Check test mode is enabled
    assert db._test_mode is True, "Test mode should be auto-detected"

    # Check database connection
    @db.model
    class DiagnosticModel:
        test_field: str

    # Verify model registration
    models = db.get_models()
    assert "DiagnosticModel" in models, "Model registration failed"

    # Verify cleanup metrics are available
    metrics = db.get_cleanup_metrics()
    assert "test_mode_enabled" in metrics
    assert metrics["test_mode_enabled"] is True

    print("✅ DataFlow testing setup is working correctly!")
```

Run it:
```bash
pytest tests/test_diagnostic.py -v -s
```

---

## Common Setup Issues

### Issue 1: "Event loop is closed"

**Cause**: Event loop fixture is not function-scoped or missing

**Solution**: Add function-scoped event loop fixture to `conftest.py`:
```python
@pytest.fixture(scope="function")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
```

### Issue 2: "Pool is attached to different loop"

**Cause**: Connection pool created in one event loop, used in another

**Solution**: Use function-scoped DataFlow fixture with cleanup:
```python
@pytest.fixture(scope="function")
async def db():
    db = DataFlow(database_url)
    yield db
    await db.cleanup_all_pools()  # CRITICAL
```

### Issue 3: "Connection refused"

**Cause**: Database not running or wrong connection URL

**Solution**: Verify database is running:
```bash
# PostgreSQL
docker ps | grep dataflow-test-postgres

# Test connection
psql postgresql://test_user:test_password@localhost:5434/dataflow_test -c "SELECT 1"
```

### Issue 4: "asyncio_mode" not recognized

**Cause**: Old pytest-asyncio version

**Solution**: Update pytest-asyncio:
```bash
pip install --upgrade pytest-asyncio
```

### Issue 5: Environment variables not loading

**Cause**: pytest-dotenv not installed or `.env` file missing

**Solution**:
```bash
pip install pytest-dotenv

# Create .env file
echo "TEST_DATABASE_URL=postgresql://test_user:test_password@localhost:5434/dataflow_test" > .env
```

---

## Performance Optimization Tips

### 1. Use SQLite for Fast Unit Tests

```python
@pytest.fixture
def fast_db():
    """Ultra-fast in-memory database for unit tests."""
    return DataFlow(":memory:")
```

**Speed**: ~50ms per test (vs ~200ms for PostgreSQL)

### 2. Use Module-Scoped Fixtures for Integration Tests

```python
@pytest.fixture(scope="module")
async def shared_db():
    """Shared database for all tests in this module."""
    db = DataFlow(database_url)
    yield db
    await db.cleanup_all_pools()
```

**Trade-off**: Faster (reuses pools) but less isolation (tests share state)

### 3. Reduce Connection Pool Size

```python
db = DataFlow(
    database_url,
    pool_size=1,           # Minimal pool
    max_overflow=0         # No overflow connections
)
```

**Benefit**: Prevents connection exhaustion in test environments

### 4. Disable Monitoring in Tests

```python
db = DataFlow(database_url, monitoring=False)
```

**Benefit**: Reduces overhead and log noise

---

## Next Steps

**You've completed setup! Now learn:**

1. **Fixture Patterns** (`fixture-patterns.md`) - Function/module/session-scoped cleanup patterns
2. **Troubleshooting** (`troubleshooting.md`) - Solutions for common errors
3. **Transaction Patterns** - Rollback strategies for test isolation

**Quick Reference**:
- All tests should use `async def` with `@pytest.mark.asyncio`
- Always use function-scoped event loop fixture
- Always cleanup pools in fixture teardown (`await db.cleanup_all_pools()`)
- Use SQLite for unit tests, PostgreSQL for integration tests

---

## Complete Example: Production-Ready conftest.py

```python
"""Production-ready pytest configuration for DataFlow testing."""
import asyncio
import os
import pytest
from dataflow import DataFlow


# ============================
# Event Loop Configuration
# ============================

@pytest.fixture(scope="function")
def event_loop():
    """Function-scoped event loop (prevents 'event loop is closed' errors)."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)

    yield loop

    # Cleanup remaining tasks
    try:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ============================
# Database Fixtures
# ============================

@pytest.fixture(scope="function")
async def db_postgresql():
    """PostgreSQL database for integration tests."""
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5434/dataflow_test"
    )

    db = DataFlow(database_url, pool_size=1, max_overflow=0)
    yield db
    await db.cleanup_all_pools()


@pytest.fixture(scope="function")
def db_sqlite():
    """SQLite in-memory database for fast unit tests."""
    db = DataFlow(":memory:")
    yield db
    # SQLite cleanup automatic on close


@pytest.fixture(scope="function")
async def db():
    """Default database fixture (PostgreSQL)."""
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5434/dataflow_test"
    )

    db = DataFlow(database_url, pool_size=1, max_overflow=0)
    yield db
    await db.cleanup_all_pools()


# ============================
# Shared Test Data
# ============================

@pytest.fixture
def sample_users():
    """Sample user data for testing."""
    return [
        {"id": "user-1", "name": "Alice", "email": "alice@example.com"},
        {"id": "user-2", "name": "Bob", "email": "bob@example.com"},
        {"id": "user-3", "name": "Charlie", "email": "charlie@example.com"},
    ]


@pytest.fixture
def sample_products():
    """Sample product data for testing."""
    return [
        {"id": "prod-1", "name": "Laptop", "price": 999.99},
        {"id": "prod-2", "name": "Mouse", "price": 29.99},
        {"id": "prod-3", "name": "Keyboard", "price": 79.99},
    ]
```

**Usage**:
```python
@pytest.mark.asyncio
async def test_with_defaults(db, sample_users):
    """Use default fixtures."""
    # db is PostgreSQL
    # sample_users provides test data
    pass
```

---

## Summary Checklist

Before writing tests, verify:

- ✅ pytest and pytest-asyncio installed
- ✅ pytest.ini configured with `asyncio_mode = auto`
- ✅ Test database running (PostgreSQL/MySQL/SQLite)
- ✅ .env file with TEST_DATABASE_URL
- ✅ conftest.py with function-scoped event loop fixture
- ✅ conftest.py with DataFlow fixture including cleanup
- ✅ Diagnostic test passes

**You're ready to write DataFlow tests!**
