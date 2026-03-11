# DataFlow Fixture Patterns

## Purpose
This guide shows you how to write cleanup fixtures that prevent pool leaks and "event loop is closed" errors. These patterns solve the root cause of most DataFlow testing issues.

**When to use this guide**: When writing any DataFlow test that creates database connections.

---

## The Problem

```python
# ❌ WRONG - Causes "pool is closed" errors
@pytest.mark.asyncio
async def test_user_operations():
    db = DataFlow("postgresql://...")

    @db.model
    class User:
        name: str

    # Test operations...
    # Pool never cleaned up!
    # Next test fails with "pool is closed"
```

**What happens**:
1. Test creates DataFlow instance and connection pool
2. Test completes but pool stays open
3. Event loop closes
4. Next test tries to use pool from closed loop
5. Error: "pool is attached to different loop"

**The Solution**: Use cleanup fixtures that close pools after each test.

---

## Pattern 1: Function-Scoped Fixture (Recommended)

**Use this pattern for**: 95% of tests. Provides complete isolation between tests.

### Implementation

```python
# tests/conftest.py
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="function")
async def db():
    """DataFlow instance with automatic cleanup.

    Creates fresh DataFlow instance for each test.
    Ensures complete isolation and no pool leaks.
    """
    database_url = "postgresql://test_user:test_password@localhost:5434/dataflow_test"

    # Create DataFlow instance (auto-detects test mode)
    db = DataFlow(database_url, pool_size=1, max_overflow=0)

    yield db

    # Cleanup: Close all connection pools
    await db.cleanup_all_pools()
```

### Usage

```python
# tests/test_user.py
import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime


@pytest.mark.asyncio
async def test_user_create(db):
    """Test user creation with function-scoped fixture."""

    @db.model
    class User:
        name: str
        email: str

    # Create user
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-1",
        "name": "Alice",
        "email": "alice@example.com"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

    assert results["create"]["id"] == "user-1"
    # Fixture automatically cleans up pools


@pytest.mark.asyncio
async def test_user_read(db):
    """Another test - gets fresh database state."""

    @db.model
    class User:
        name: str
        email: str

    # This test starts with clean slate
    # No data from previous test
```

### Why This Works

1. **Fresh instance per test** - Each test gets new DataFlow instance
2. **Automatic cleanup** - `cleanup_all_pools()` runs after each test
3. **Complete isolation** - No shared state between tests
4. **Prevents pool leaks** - Pools closed before event loop closes

### Trade-offs

**Pros**:
- ✅ Complete test isolation
- ✅ No pool leaks
- ✅ Easy to debug (each test independent)
- ✅ No "pool is closed" errors

**Cons**:
- ⚠️ Slower (new pool per test)
- ⚠️ More database connections

**Performance**: ~200ms per test (PostgreSQL), ~50ms (SQLite)

---

## Pattern 2: Module-Scoped Fixture (Performance Optimization)

**Use this pattern for**: Integration tests where multiple tests share setup. Faster but less isolation.

### Implementation

```python
# tests/conftest.py
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="module")
async def shared_db():
    """Shared DataFlow instance for all tests in module.

    Reuses connection pool across tests for performance.
    Trade-off: Tests share database state.
    """
    database_url = "postgresql://test_user:test_password@localhost:5434/dataflow_test"

    db = DataFlow(database_url, pool_size=2, max_overflow=1)

    yield db

    # Cleanup: Close pools after all module tests complete
    await db.cleanup_all_pools()


@pytest.fixture(scope="function")
async def clean_state(shared_db):
    """Clean database state before each test.

    Use this with module-scoped DataFlow to get isolation
    without creating new pools.
    """
    # Before test: Clean tables
    # (Implementation depends on your schema)

    yield shared_db

    # After test: Clean up test data
    # (Optional: rollback transactions, truncate tables)
```

### Usage

```python
# tests/integration/test_user_workflow.py
import pytest


@pytest.mark.asyncio
async def test_user_registration_workflow(clean_state):
    """Test complete user registration workflow."""
    db = clean_state

    @db.model
    class User:
        name: str
        email: str

    # Test registration workflow
    # Uses shared pool (faster)


@pytest.mark.asyncio
async def test_user_login_workflow(clean_state):
    """Test user login workflow."""
    db = clean_state

    # clean_state fixture ensures no data from previous test
    # But reuses connection pool (faster)
```

### Why This Works

1. **Shared pool** - Connection pool reused across tests
2. **Manual state management** - You control data cleanup
3. **Faster execution** - No pool creation overhead
4. **Controlled isolation** - Clean state fixture manages isolation

### Trade-offs

**Pros**:
- ✅ Faster (reuses pools)
- ✅ Fewer database connections
- ✅ Good for integration tests

**Cons**:
- ⚠️ More complex (manual state management)
- ⚠️ Less isolation (shared pool)
- ⚠️ Harder to debug (shared state bugs)

**Performance**: ~50ms per test (10x faster than function-scoped)

### When to Use

**Good for**:
- Integration tests with expensive setup
- Tests that need shared fixtures (pre-populated tables)
- Test suites with >100 tests

**Bad for**:
- Unit tests (use function-scoped)
- Tests that modify global state
- Tests that need complete isolation

---

## Pattern 3: Session-Scoped Fixture (Global Control)

**Use this pattern for**: One-time setup for entire test session. Enables/disables test mode globally.

### Implementation

```python
# tests/conftest.py
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="session", autouse=True)
def enable_test_mode():
    """Enable DataFlow test mode for entire test session.

    Auto-runs before any tests.
    All DataFlow instances will use test mode.
    """
    DataFlow.enable_test_mode()

    yield

    DataFlow.disable_test_mode()


@pytest.fixture(scope="session")
async def session_db():
    """Session-wide DataFlow instance.

    Use for global setup/teardown only.
    DO NOT use for individual test operations.
    """
    database_url = "postgresql://test_user:test_password@localhost:5434/dataflow_test"

    db = DataFlow(database_url)

    # One-time setup (e.g., create schemas, load fixtures)
    await db.initialize()

    yield db

    # One-time teardown
    await db.cleanup_all_pools()
```

### Usage

```python
# tests/test_user.py
import pytest
from dataflow import DataFlow


@pytest.mark.asyncio
async def test_with_global_test_mode():
    """Test mode is already enabled by session fixture."""

    # This DataFlow instance automatically has test mode enabled
    db = DataFlow("postgresql://...")

    assert db._test_mode is True

    # Your test code...
```

### Why This Works

1. **Global configuration** - Test mode enabled once for all tests
2. **One-time setup** - Expensive operations run once
3. **Automatic** - `autouse=True` runs automatically

### Trade-offs

**Pros**:
- ✅ One-time setup/teardown
- ✅ Global test mode control
- ✅ Simplifies individual test fixtures

**Cons**:
- ⚠️ No isolation (shared state)
- ⚠️ Harder to debug
- ⚠️ Can't disable for specific tests

### When to Use

**Good for**:
- Enabling test mode globally
- Creating test database schemas
- Loading global test fixtures

**Bad for**:
- Individual test operations
- Tests that need isolation
- Tests that modify state

---

## Pattern 4: Transaction Rollback Pattern

**Use this pattern for**: Tests that need complete isolation with fast execution. Wraps each test in transaction that rolls back.

### Implementation

```python
# tests/conftest.py
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="function")
async def db_transaction(db):
    """Wrap each test in a transaction that rolls back.

    Provides complete isolation with performance of module-scoped fixture.
    Best of both worlds for PostgreSQL.
    """
    # Start transaction
    async with db.transaction() as tx:
        yield db

        # Rollback happens automatically when context exits
        # (unless explicitly committed)
```

### Usage

```python
@pytest.mark.asyncio
async def test_user_create_with_rollback(db_transaction):
    """Test that automatically rolls back changes."""
    db = db_transaction

    @db.model
    class User:
        name: str
        email: str

    # Create user
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-1",
        "name": "Alice",
        "email": "alice@example.com"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

    assert results["create"]["id"] == "user-1"

    # Transaction automatically rolls back after test
    # User is not persisted to database
```

### Why This Works

1. **Transaction isolation** - Changes visible within transaction only
2. **Automatic rollback** - No manual cleanup needed
3. **Fast** - No pool recreation overhead
4. **Complete isolation** - Each test starts with clean state

### Trade-offs

**Pros**:
- ✅ Complete isolation
- ✅ Fast execution
- ✅ Automatic cleanup
- ✅ No manual state management

**Cons**:
- ⚠️ PostgreSQL only (SQLite has limited transaction support)
- ⚠️ Doesn't test transaction boundaries in your code
- ⚠️ Complex setup for nested transactions

**Performance**: ~100ms per test (middle ground)

---

## Pattern Comparison Table

| Pattern | Isolation | Speed | Complexity | Use Case |
|---------|-----------|-------|------------|----------|
| **Function-Scoped** | ✅ Complete | ⚠️ Slow (~200ms) | ✅ Simple | Unit tests, default choice |
| **Module-Scoped** | ⚠️ Manual | ✅ Fast (~50ms) | ⚠️ Medium | Integration tests, shared setup |
| **Session-Scoped** | ❌ None | ✅ One-time | ⚠️ Medium | Global config, test mode |
| **Transaction Rollback** | ✅ Complete | ✅ Fast (~100ms) | ⚠️ Complex | PostgreSQL integration tests |

**Recommendation**: Start with function-scoped. Optimize to module-scoped or transaction rollback only if tests are too slow.

---

## Common Mistakes

### Mistake 1: No Cleanup

```python
# ❌ WRONG - No cleanup
@pytest.fixture
def db():
    return DataFlow("postgresql://...")
    # Pool never closed!
```

**Fix**: Add cleanup in teardown:
```python
# ✅ CORRECT
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()  # CRITICAL
```

### Mistake 2: Wrong Scope

```python
# ❌ WRONG - Session scope without cleanup per test
@pytest.fixture(scope="session")
async def db():
    return DataFlow("postgresql://...")
    # Tests contaminate each other!
```

**Fix**: Use function scope for isolation:
```python
# ✅ CORRECT
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()
```

### Mistake 3: Mixing Event Loop Scopes

```python
# ❌ WRONG - Session loop with function DataFlow
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function")
async def db():
    return DataFlow("postgresql://...")  # Uses session loop!
```

**Fix**: Match scopes:
```python
# ✅ CORRECT - Function loop with function DataFlow
@pytest.fixture(scope="function")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
```

### Mistake 4: No Error Handling in Cleanup

```python
# ❌ WRONG - Cleanup can crash test
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()  # May raise exception
```

**Fix**: Graceful error handling:
```python
# ✅ CORRECT
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")
    yield db
    try:
        await db.cleanup_all_pools()
    except Exception as e:
        # Log but don't crash
        import logging
        logging.warning(f"Cleanup failed: {e}")
```

### Mistake 5: Forgetting `await`

```python
# ❌ WRONG - Missing await
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")
    yield db
    db.cleanup_all_pools()  # Missing await!
```

**Fix**: Always `await` async methods:
```python
# ✅ CORRECT
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()  # await required
```

---

## Advanced Patterns

### Pattern: Multiple Database Fixtures

```python
# tests/conftest.py
@pytest.fixture(scope="function")
async def db_postgresql():
    """PostgreSQL database for production-like tests."""
    db = DataFlow("postgresql://test_user:test_password@localhost:5434/dataflow_test")
    yield db
    await db.cleanup_all_pools()


@pytest.fixture(scope="function")
def db_sqlite():
    """SQLite database for fast unit tests."""
    db = DataFlow(":memory:")
    yield db
    # SQLite cleanup automatic


@pytest.fixture(scope="function",
                params=["postgresql", "sqlite"])
async def db_all(request):
    """Parametrized fixture - runs test with both databases."""
    if request.param == "postgresql":
        db = DataFlow("postgresql://test_user:test_password@localhost:5434/dataflow_test")
        yield db
        await db.cleanup_all_pools()
    else:
        db = DataFlow(":memory:")
        yield db
```

**Usage**:
```python
@pytest.mark.asyncio
async def test_cross_database(db_all):
    """This test runs twice - once with PostgreSQL, once with SQLite."""
    @db_all.model
    class User:
        name: str

    # Test runs on both databases automatically
```

### Pattern: Conditional Cleanup

```python
@pytest.fixture
async def db(request):
    """DataFlow with conditional cleanup based on test outcome."""
    database_url = "postgresql://test_user:test_password@localhost:5434/dataflow_test"
    db = DataFlow(database_url)

    yield db

    # Only cleanup if test passed (keep data on failure for debugging)
    if request.node.rep_call.passed:
        await db.cleanup_all_pools()
    else:
        # Leave pools open for post-mortem debugging
        print(f"Test failed - pools left open for debugging")
```

### Pattern: Fixture Chaining

```python
@pytest.fixture
async def db():
    """Base DataFlow fixture."""
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()


@pytest.fixture
async def db_with_users(db):
    """DataFlow with pre-populated users."""
    @db.model
    class User:
        name: str
        email: str

    # Create test users
    # ... (use workflow to create users)

    yield db
    # db fixture handles cleanup


@pytest.fixture
async def db_with_products(db):
    """DataFlow with pre-populated products."""
    @db.model
    class Product:
        name: str
        price: float

    # Create test products
    # ...

    yield db
```

**Usage**:
```python
@pytest.mark.asyncio
async def test_with_users(db_with_users):
    """Test with pre-populated users."""
    # Users already created
    pass


@pytest.mark.asyncio
async def test_with_products(db_with_products):
    """Test with pre-populated products."""
    # Products already created
    pass
```

---

## Debugging Fixtures

### Check Test Mode Status

```python
@pytest.mark.asyncio
async def test_debug_test_mode(db):
    """Verify test mode is enabled."""
    assert db._test_mode is True, "Test mode should be auto-detected"

    metrics = db.get_cleanup_metrics()
    print(f"Test mode: {metrics['test_mode_enabled']}")
    print(f"Active pools: {metrics['active_pools']}")
```

### Monitor Pool Lifecycle

```python
@pytest.fixture
async def db_with_monitoring():
    """DataFlow with pool lifecycle monitoring."""
    db = DataFlow("postgresql://...", debug=True)

    # Before test
    print(f"Pools before: {db.get_cleanup_metrics()['active_pools']}")

    yield db

    # After test
    metrics = db.get_cleanup_metrics()
    print(f"Pools after: {metrics['active_pools']}")
    print(f"Pools cleaned: {metrics.get('pools_cleaned', 0)}")

    await db.cleanup_all_pools()
```

### Verify Cleanup

```python
@pytest.mark.asyncio
async def test_verify_cleanup(db):
    """Verify pools are cleaned up correctly."""

    # Do test operations
    @db.model
    class User:
        name: str

    # Check metrics before cleanup
    metrics_before = db.get_cleanup_metrics()
    print(f"Active pools before cleanup: {metrics_before['active_pools']}")

    # Manually trigger cleanup
    cleanup_metrics = await db.cleanup_all_pools()
    print(f"Cleaned pools: {cleanup_metrics['pools_cleaned']}")

    # Verify cleanup succeeded
    metrics_after = db.get_cleanup_metrics()
    assert metrics_after['active_pools'] == 0
```

---

## Next Steps

**You've learned fixture patterns! Now:**

1. **Use function-scoped fixtures** for 95% of tests
2. **Add cleanup** (`await db.cleanup_all_pools()`) to all fixtures
3. **Match event loop scope** to DataFlow fixture scope
4. **Read troubleshooting guide** for common errors

**Quick Reference**:
- Function-scoped = Complete isolation, slower
- Module-scoped = Faster, manual state management
- Session-scoped = Global config only
- Transaction rollback = Fast + isolated (PostgreSQL only)

**Production-Ready Template** (copy this to `conftest.py`):

```python
import asyncio
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="function")
def event_loop():
    """Function-scoped event loop."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
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
    """Function-scoped DataFlow with automatic cleanup."""
    database_url = "postgresql://test_user:test_password@localhost:5434/dataflow_test"
    db = DataFlow(database_url, pool_size=1, max_overflow=0)

    yield db

    try:
        await db.cleanup_all_pools()
    except Exception as e:
        import logging
        logging.warning(f"Cleanup failed: {e}")
```

**Start with this template and customize as needed!**
