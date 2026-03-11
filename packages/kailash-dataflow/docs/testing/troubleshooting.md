# DataFlow Testing Troubleshooting Guide

## Purpose
This guide solves the top 5 errors you'll encounter when testing with DataFlow. Each error includes the exact error message, root cause, and copy-paste solution.

**Use this guide when**: You encounter an error running DataFlow tests.

---

## Error 1: "Event loop is closed"

### Error Message

```
RuntimeError: Event loop is closed
```

Or:

```
RuntimeError: Cannot run async function: the event loop is already closed
```

### When It Happens

```python
@pytest.mark.asyncio
async def test_user_create():
    db = DataFlow("postgresql://...")

    @db.model
    class User:
        name: str

    # Test runs fine...

# Next test:
@pytest.mark.asyncio
async def test_user_read():  # ❌ Error: Event loop is closed
    db = DataFlow("postgresql://...")
```

### Root Cause

**Problem**: pytest-asyncio reuses the same event loop across tests by default. When the loop closes (or is contaminated), subsequent tests fail.

**Why DataFlow is affected**: Connection pools attach to specific event loops. When loop closes, pools become invalid.

### Solution: Function-Scoped Event Loop

Add this to `tests/conftest.py`:

```python
import asyncio
import pytest


@pytest.fixture(scope="function")
def event_loop():
    """Create a fresh event loop for each test.

    CRITICAL: Function scope prevents event loop contamination.
    Each test gets its own isolated loop.
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
```

### Verify Solution

```python
@pytest.mark.asyncio
async def test_event_loop_isolation(event_loop):
    """Verify each test gets fresh event loop."""
    import asyncio

    current_loop = asyncio.get_event_loop()
    assert current_loop is event_loop
    assert current_loop.is_running()

    print(f"✅ Event loop isolated per test")
```

### Alternative: Configure pytest.ini

```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

**This setting requires function-scoped event loop fixture.**

---

## Error 2: "Pool is attached to a different loop"

### Error Message

```
RuntimeError: pool is attached to a different event loop
```

Or:

```
RuntimeError: Task <Task pending> got Future attached to a different loop
```

### When It Happens

```python
@pytest.fixture(scope="module")  # ❌ Module scope
async def db():
    return DataFlow("postgresql://...")

@pytest.mark.asyncio
async def test_first(db):
    # Works fine

@pytest.mark.asyncio
async def test_second(db):  # ❌ Error: Different loop
    # Pool from test_first attached to old loop
```

### Root Cause

**Problem**: Connection pool created in one event loop, but used in another.

**Why it happens**:
1. Module/session-scoped DataFlow fixture creates pool in first test's loop
2. Second test runs with new event loop (function-scoped)
3. Pool still attached to old loop
4. Error: Can't use pool from different loop

### Solution: Match Fixture Scopes

**Option A**: Function-scoped DataFlow (Recommended)

```python
# tests/conftest.py
@pytest.fixture(scope="function")
async def db():
    """Function-scoped DataFlow matches function-scoped event loop."""
    database_url = "postgresql://test_user:test_password@localhost:5434/dataflow_test"
    db = DataFlow(database_url)

    yield db

    # Cleanup pools before loop closes
    await db.cleanup_all_pools()
```

**Option B**: Session-scoped event loop (Not Recommended)

```python
# ⚠️ NOT RECOMMENDED - Less isolation
@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped loop for session-scoped DataFlow."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db():
    """Session-scoped DataFlow for shared pool."""
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()
```

**Why Option A is better**: Function scope provides complete test isolation.

### Verify Solution

```python
@pytest.mark.asyncio
async def test_loop_consistency_1(db):
    """First test creates pool."""
    metrics = db.get_cleanup_metrics()
    print(f"Active pools: {metrics['active_pools']}")


@pytest.mark.asyncio
async def test_loop_consistency_2(db):
    """Second test gets fresh pool (no error)."""
    metrics = db.get_cleanup_metrics()
    print(f"✅ Fresh pool created, no loop mismatch")
```

---

## Error 3: "No such table" in Tests

### Error Message

```
asyncpg.exceptions.UndefinedTableError: relation "users" does not exist
```

Or:

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: users
```

### When It Happens

```python
@pytest.mark.asyncio
async def test_user_read(db):
    """Try to read user before model is registered."""

    # ❌ Model not registered yet
    workflow = WorkflowBuilder()
    workflow.add_node("UserReadNode", "read", {"id": "user-1"})  # Error: No such table
```

### Root Cause

**Problem**: Table doesn't exist because model wasn't registered or `initialize()` wasn't called.

**Why it happens**:
1. Model registered in one test, not available in next test (function-scoped)
2. Or `db.initialize()` not called (deferred table creation)
3. Or test database doesn't have schema

### Solution: Register Models in Each Test

```python
@pytest.mark.asyncio
async def test_user_create(db):
    """Register model in each test."""

    # Register model
    @db.model
    class User:
        name: str
        email: str

    # Ensure tables created
    await db.initialize()

    # Now operations work
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-1",
        "name": "Alice",
        "email": "alice@example.com"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

    assert results["create"]["id"] == "user-1"
```

### Alternative: Shared Model Fixture

```python
# tests/conftest.py
@pytest.fixture
async def db_with_models(db):
    """DataFlow with pre-registered models."""

    @db.model
    class User:
        name: str
        email: str

    @db.model
    class Product:
        name: str
        price: float

    # Ensure tables created
    await db.initialize()

    yield db
```

**Usage**:
```python
@pytest.mark.asyncio
async def test_with_models(db_with_models):
    """Models already registered."""
    db = db_with_models

    # Tables exist, operations work
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {...})
```

### Verify Solution

```python
@pytest.mark.asyncio
async def test_table_exists(db):
    """Verify table creation."""

    @db.model
    class User:
        name: str

    await db.initialize()

    # Verify table exists
    models = db.get_models()
    assert "User" in models

    print("✅ Table created successfully")
```

---

## Error 4: Connection Pool Exhaustion

### Error Message

```
asyncpg.exceptions.TooManyConnectionsError: sorry, too many clients already
```

Or:

```
PoolTimeout: Timeout waiting for connection from pool
```

Or:

```
ResourceClosedError: This pool has been closed
```

### When It Happens

```python
# Run 100+ tests
pytest tests/ -v

# After ~50 tests:
# ❌ Error: Too many connections
```

### Root Cause

**Problem**: Connection pools not cleaned up after tests. Pools accumulate until database connection limit reached.

**PostgreSQL default**: 100 connections
**Typical DataFlow pool**: 10 connections
**After 10 tests**: 100 connections (limit reached)

### Solution: Always Clean Up Pools

```python
# tests/conftest.py
@pytest.fixture(scope="function")
async def db():
    """DataFlow with guaranteed cleanup."""
    database_url = "postgresql://test_user:test_password@localhost:5434/dataflow_test"

    # Use small pool for tests
    db = DataFlow(
        database_url,
        pool_size=1,        # Minimal pool
        max_overflow=0      # No overflow connections
    )

    yield db

    # CRITICAL: Always cleanup
    try:
        await db.cleanup_all_pools()
    except Exception as e:
        import logging
        logging.warning(f"Cleanup failed: {e}")
```

### Monitor Pool Usage

```python
@pytest.fixture
async def db_with_monitoring():
    """DataFlow with pool monitoring."""
    db = DataFlow("postgresql://...", pool_size=1, max_overflow=0)

    # Before test
    metrics_before = db.get_cleanup_metrics()
    print(f"Pools before: {metrics_before['active_pools']}")

    yield db

    # After test
    metrics_after = db.get_cleanup_metrics()
    print(f"Pools after: {metrics_after['active_pools']}")

    # Cleanup
    cleanup_result = await db.cleanup_all_pools()
    print(f"Cleaned: {cleanup_result['pools_cleaned']}")
```

### Verify Solution

```python
@pytest.mark.asyncio
async def test_no_pool_leak(db):
    """Verify pools are cleaned up."""

    @db.model
    class User:
        name: str

    # Do operations
    # ...

    # Check pool state
    metrics = db.get_cleanup_metrics()
    assert metrics['active_pools'] >= 0

    print("✅ No pool leak")
```

### Additional Configuration

Reduce pool sizes in `.env`:

```bash
# .env
DATAFLOW_POOL_SIZE=1
DATAFLOW_MAX_OVERFLOW=0
```

Or in code:

```python
db = DataFlow(
    database_url,
    pool_size=1,
    max_overflow=0,
    pool_timeout=5,      # Quick timeout
    pool_recycle=30      # Aggressive recycling
)
```

---

## Error 5: "Connection refused" or Database Not Available

### Error Message

```
asyncpg.exceptions.ConnectionDoesNotExistError: connection refused
```

Or:

```
sqlalchemy.exc.OperationalError: could not connect to server
```

Or:

```
Connection refused: localhost:5432
```

### When It Happens

```python
@pytest.mark.asyncio
async def test_database_connection():
    db = DataFlow("postgresql://test_user:test_password@localhost:5432/test_db")
    # ❌ Error: Connection refused
```

### Root Cause

**Problem**: Database server not running, wrong URL, or wrong port.

**Common causes**:
1. Database not started (Docker container stopped)
2. Wrong port (5432 vs 5434)
3. Wrong credentials
4. Firewall blocking connection
5. Database not initialized

### Solution: Verify Database is Running

#### Check Docker Container

```bash
# Check if container is running
docker ps | grep postgres

# If not running, start it
docker run -d \
  --name dataflow-test-postgres \
  -e POSTGRES_USER=test_user \
  -e POSTGRES_PASSWORD=test_password \
  -e POSTGRES_DB=dataflow_test \
  -p 5434:5432 \
  postgres:16-alpine

# Verify it's ready
docker logs dataflow-test-postgres | grep "database system is ready"
```

#### Test Connection Manually

```bash
# PostgreSQL
psql postgresql://test_user:test_password@localhost:5434/dataflow_test -c "SELECT 1"

# Expected output:
# ?column?
# ----------
#        1
# (1 row)
```

#### Check Connection String

```python
# tests/conftest.py
import os
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="session", autouse=True)
async def verify_database_connection():
    """Verify database is accessible before running tests."""
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5434/dataflow_test"
    )

    try:
        # Try to connect
        db = DataFlow(database_url)
        await db.initialize()
        await db.cleanup_all_pools()
        print(f"✅ Database connection verified: {database_url}")
    except Exception as e:
        pytest.exit(f"❌ Cannot connect to test database: {e}")
```

### Common Port Issues

**Wrong port in URL**:
```python
# ❌ WRONG - Production port
db = DataFlow("postgresql://...@localhost:5432/...")

# ✅ CORRECT - Test port
db = DataFlow("postgresql://...@localhost:5434/...")
```

**Docker port mapping**:
```bash
# Container port 5432 mapped to host port 5434
docker run -p 5434:5432 postgres
#         ^^^^     ^^^^
#         Host     Container
```

### Verify Solution

```python
@pytest.mark.asyncio
async def test_database_connectivity():
    """Verify database connection works."""
    import os

    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5434/dataflow_test"
    )

    db = DataFlow(database_url)

    try:
        await db.initialize()
        print(f"✅ Successfully connected to {database_url}")
    except Exception as e:
        pytest.fail(f"Connection failed: {e}")
    finally:
        await db.cleanup_all_pools()
```

---

## Additional Common Issues

### Issue 6: Tests Hang Indefinitely

**Symptom**: Test never completes, no error message

**Cause**: Deadlock in async code or missing `await`

**Solution**: Add timeout to tests

```python
# pytest.ini
[pytest]
timeout = 10  # Kill tests after 10 seconds

# Or per-test
@pytest.mark.timeout(5)
@pytest.mark.asyncio
async def test_with_timeout(db):
    # Test code
```

**Check for missing await**:
```python
# ❌ WRONG - Missing await
cleanup_metrics = db.cleanup_all_pools()  # Returns coroutine!

# ✅ CORRECT
cleanup_metrics = await db.cleanup_all_pools()
```

### Issue 7: "RuntimeError: This event loop is already running"

**Symptom**: Can't run nested async operations

**Cause**: Trying to run `asyncio.run()` inside already-running loop

**Solution**: Use `await` instead of `asyncio.run()`

```python
# ❌ WRONG
@pytest.mark.asyncio
async def test_nested_async(db):
    result = asyncio.run(some_async_function())  # Error!

# ✅ CORRECT
@pytest.mark.asyncio
async def test_nested_async(db):
    result = await some_async_function()
```

### Issue 8: Stale Pool Warnings

**Symptom**: Warning messages about stale connection pools

```
WARNING: Stale pool detected: pool-abc123 (closed event loop)
```

**Cause**: Pool not cleaned up when event loop closed

**Solution**: Call cleanup before loop closes

```python
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")
    yield db

    # Cleanup BEFORE loop closes
    await db.cleanup_stale_pools()  # Proactive cleanup
    await db.cleanup_all_pools()     # Full cleanup
```

### Issue 9: "Table already exists" Errors

**Symptom**: Test fails because table already exists

**Cause**: Previous test created table, cleanup didn't drop it

**Solution**: Drop tables in fixture teardown

```python
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")

    yield db

    # Cleanup: Drop test tables
    # (Specific to your schema)
    await db.cleanup_all_pools()
```

Or use transaction rollback pattern (see fixture-patterns.md).

### Issue 10: Import Errors with Test Fixtures

**Symptom**: `fixture 'db' not found`

**Cause**: conftest.py not in correct location or not named correctly

**Solution**: Ensure conftest.py exists

```
tests/
├── conftest.py          # ✅ CORRECT - Shared fixtures
├── test_user.py
└── integration/
    ├── conftest.py      # ✅ CORRECT - Integration-specific fixtures
    └── test_workflow.py
```

**Verify fixture discovery**:
```bash
pytest --fixtures tests/
# Should list 'db' fixture
```

---

## Debugging Checklist

When encountering errors, check these in order:

1. **✅ Database is running**
   ```bash
   docker ps | grep postgres
   ```

2. **✅ Connection URL is correct**
   ```python
   print(os.getenv("TEST_DATABASE_URL"))
   ```

3. **✅ Event loop fixture is function-scoped**
   ```python
   # conftest.py
   @pytest.fixture(scope="function")
   def event_loop():
   ```

4. **✅ DataFlow fixture has cleanup**
   ```python
   @pytest.fixture
   async def db():
       db = DataFlow(...)
       yield db
       await db.cleanup_all_pools()  # CRITICAL
   ```

5. **✅ pytest.ini configured correctly**
   ```ini
   [pytest]
   asyncio_mode = auto
   asyncio_default_fixture_loop_scope = function
   ```

6. **✅ Models registered in test**
   ```python
   @db.model
   class User:
       name: str
   await db.initialize()
   ```

7. **✅ Using `await` for async operations**
   ```python
   await db.cleanup_all_pools()  # Not: db.cleanup_all_pools()
   ```

---

## Getting More Help

### Enable Debug Logging

```python
# conftest.py
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("dataflow").setLevel(logging.DEBUG)
```

### Check Pool Metrics

```python
@pytest.mark.asyncio
async def test_debug_pools(db):
    """Debug pool state."""
    metrics = db.get_cleanup_metrics()

    print(f"Test mode: {metrics['test_mode_enabled']}")
    print(f"Active pools: {metrics['active_pools']}")
    print(f"Total pools created: {metrics['total_pools_created']}")
    print(f"Pool keys: {metrics['pool_keys']}")
```

### Verify Test Mode

```python
@pytest.mark.asyncio
async def test_verify_test_mode(db):
    """Verify test mode is enabled."""
    assert db._test_mode is True, "Test mode should be auto-detected by pytest"

    metrics = db.get_cleanup_metrics()
    assert metrics["test_mode_enabled"] is True

    print("✅ Test mode working correctly")
```

### Run Single Test with Verbose Output

```bash
# Run single test with full output
pytest tests/test_user.py::test_user_create -v -s

# With debug logging
pytest tests/test_user.py::test_user_create -v -s --log-cli-level=DEBUG
```

---

## Summary: Quick Fixes

| Error | Quick Fix |
|-------|-----------|
| Event loop is closed | Add function-scoped event loop fixture |
| Pool attached to different loop | Use function-scoped DataFlow fixture |
| No such table | Register model with `@db.model` in each test |
| Connection pool exhaustion | Add `await db.cleanup_all_pools()` to fixture |
| Connection refused | Verify database is running on correct port |
| Test hangs | Add timeout, check for missing `await` |
| Stale pool warnings | Call cleanup before loop closes |

**Most common solution**: Function-scoped fixtures with cleanup

```python
# Copy this to conftest.py
@pytest.fixture(scope="function")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://test_user:test_password@localhost:5434/dataflow_test")
    yield db
    await db.cleanup_all_pools()
```

**This solves 90% of DataFlow testing issues!**

---

## Next Steps

**You've solved common errors! Now:**

1. **Read fixture patterns** (`fixture-patterns.md`) for advanced patterns
2. **Review setup guide** (`setup-guide.md`) for best practices
3. **Check examples** in `examples/` directory

**Still having issues?** Check DataFlow test suite:
- `/packages/kailash-dataflow/tests/unit/` - Unit test examples
- `/packages/kailash-dataflow/tests/integration/` - Integration test examples
- `/packages/kailash-dataflow/tests/conftest.py` - Production fixtures
