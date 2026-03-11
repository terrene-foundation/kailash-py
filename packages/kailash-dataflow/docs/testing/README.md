# DataFlow Testing Guide

## Overview

This guide provides comprehensive instructions for testing DataFlow applications with pytest. It addresses common async testing challenges and provides copy-paste ready solutions.

**Target Audience**: Developers writing tests for DataFlow applications
**Time to First Test**: 5 minutes with setup guide
**Coverage**: pytest configuration, fixtures, troubleshooting, and best practices

---

## Quick Start (30 Seconds)

### 1. Install Dependencies

```bash
pip install pytest pytest-asyncio pytest-dotenv kailash-dataflow
```

### 2. Create Fixture File

Save this as `tests/conftest.py`:

```python
import asyncio
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="function")
def event_loop():
    """Fresh event loop per test."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db():
    """DataFlow with automatic cleanup."""
    db = DataFlow("postgresql://test_user:test_password@localhost:5434/dataflow_test")
    yield db
    await db.cleanup_all_pools()
```

### 3. Write Your First Test

```python
# tests/test_basic.py
import pytest


@pytest.mark.asyncio
async def test_user_create(db):
    """Test creating a user."""

    @db.model
    class User:
        name: str

    # Your test code here
    assert db._test_mode is True
```

### 4. Run Tests

```bash
pytest tests/ -v
```

**That's it! You're ready to write DataFlow tests.**

---

## Why This Guide Exists

### Common Problems Solved

❌ **"Event loop is closed"** - Tests fail with cryptic async errors
❌ **"Pool attached to different loop"** - Connection pool issues between tests
❌ **"Too many connections"** - Connection pool exhaustion
❌ **"No such table"** - Tables not created in test database
❌ **Tests hang indefinitely** - Missing `await` or deadlocks

✅ **This guide provides solutions for all these issues**

### What Makes This Different

**Other guides**:
- Describe what features exist
- Provide incomplete examples
- Assume pytest expertise

**This guide**:
- Shows you exactly what to do
- Provides complete, working examples
- Solves actual errors you'll encounter
- No pytest expertise required

---

## Documentation Structure

This testing guide consists of four documents:

### 1. Setup Guide (`setup-guide.md`) ⭐ START HERE

**Purpose**: Get pytest configured and write your first test in under 5 minutes

**What's Inside**:
- Installing pytest and dependencies
- Configuring pytest.ini
- Setting up test database (PostgreSQL, MySQL, SQLite)
- Creating event loop fixture
- Writing your first DataFlow test
- Running tests and verifying setup

**When to read**: Before writing any tests. This is your starting point.

**Time**: 10 minutes

---

### 2. Fixture Patterns (`fixture-patterns.md`) ⭐ CORE GUIDE

**Purpose**: Learn how to write cleanup fixtures that prevent pool leaks and errors

**What's Inside**:
- Function-scoped fixtures (recommended for 95% of tests)
- Module-scoped fixtures (performance optimization)
- Session-scoped fixtures (global configuration)
- Transaction rollback patterns (fast + isolated)
- Common mistakes and how to avoid them
- Pattern comparison table
- Production-ready fixture templates

**When to read**: After setup guide. This solves the root cause of most DataFlow testing issues.

**Time**: 15 minutes

**Key Takeaway**: Always use function-scoped fixtures with cleanup (`await db.cleanup_all_pools()`)

---

### 3. Troubleshooting (`troubleshooting.md`) ⭐ WHEN ERRORS OCCUR

**Purpose**: Solve the top 5 errors you'll encounter with exact solutions

**What's Inside**:
1. "Event loop is closed" - Function-scoped loop fixture
2. "Pool attached to different loop" - Match fixture scopes
3. "No such table" - Model registration in tests
4. Connection pool exhaustion - Always cleanup pools
5. "Connection refused" - Database not running

**When to read**: When you encounter an error. Each error has exact error message, cause, and solution.

**Time**: 5 minutes per error

**Key Takeaway**: 90% of errors solved by function-scoped fixtures with cleanup

---

### 4. Advanced Patterns (Future)

**Coming in future versions**:
- Transaction rollback patterns
- Parallel test execution
- Test data factories
- Mocking DataFlow operations
- Performance optimization techniques

---

## Which Guide Should I Read?

### I'm writing my first DataFlow test
👉 **Start with Setup Guide** → Then Fixture Patterns

### My tests are failing with errors
👉 **Go to Troubleshooting** → Find your error message

### I want to optimize test performance
👉 **Read Fixture Patterns** → Module-scoped section

### I need to understand cleanup patterns
👉 **Read Fixture Patterns** → Start with function-scoped

### I'm getting "event loop is closed"
👉 **Go to Troubleshooting** → Error #1

### I'm getting "pool attached to different loop"
👉 **Go to Troubleshooting** → Error #2

---

## Essential Testing Patterns

### Pattern 1: Basic Test (Function-Scoped)

```python
# tests/conftest.py
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()


# tests/test_user.py
@pytest.mark.asyncio
async def test_user_create(db):
    @db.model
    class User:
        name: str
        email: str

    # Test operations
```

**Use for**: 95% of tests. Complete isolation, automatic cleanup.

---

### Pattern 2: Shared Database (Module-Scoped)

```python
# tests/conftest.py
@pytest.fixture(scope="module")
async def shared_db():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()


@pytest.fixture
async def clean_state(shared_db):
    # Clean database before each test
    yield shared_db
    # Clean database after each test
```

**Use for**: Integration tests with expensive setup. Faster but less isolation.

---

### Pattern 3: Multiple Databases

```python
# tests/conftest.py
@pytest.fixture
async def db_postgresql():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()


@pytest.fixture
def db_sqlite():
    return DataFlow(":memory:")


# tests/test_user.py
@pytest.mark.asyncio
async def test_with_postgres(db_postgresql):
    """Integration test with PostgreSQL."""
    pass


def test_with_sqlite(db_sqlite):
    """Unit test with SQLite."""
    pass
```

**Use for**: Testing across multiple databases or fast unit tests.

---

## Critical Rules for DataFlow Testing

### Rule 1: Always Use Function-Scoped Event Loop

```python
# ✅ CORRECT - Function scope
@pytest.fixture(scope="function")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ❌ WRONG - Session scope causes errors
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

**Why**: Function scope provides fresh loop per test, preventing contamination.

---

### Rule 2: Always Cleanup Pools in Fixtures

```python
# ✅ CORRECT - Cleanup in teardown
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()  # CRITICAL


# ❌ WRONG - No cleanup
@pytest.fixture
async def db():
    return DataFlow("postgresql://...")
    # Pool never closed!
```

**Why**: Prevents connection pool exhaustion and "pool attached to different loop" errors.

---

### Rule 3: Match Fixture Scopes

```python
# ✅ CORRECT - Matching scopes
@pytest.fixture(scope="function")
def event_loop():
    ...

@pytest.fixture(scope="function")
async def db():
    ...


# ❌ WRONG - Mismatched scopes
@pytest.fixture(scope="function")
def event_loop():
    ...

@pytest.fixture(scope="module")  # Module scope with function loop!
async def db():
    ...
```

**Why**: Prevents "pool attached to different loop" errors.

---

### Rule 4: Register Models in Each Test

```python
# ✅ CORRECT - Model in test
@pytest.mark.asyncio
async def test_user_create(db):
    @db.model
    class User:
        name: str

    await db.initialize()
    # Now operations work


# ❌ WRONG - Model registered elsewhere
@pytest.mark.asyncio
async def test_user_create(db):
    # Assumes User model exists
    # Error: No such table
```

**Why**: Function-scoped fixtures give fresh database state per test.

---

### Rule 5: Always Use `await` for Async Methods

```python
# ✅ CORRECT
await db.cleanup_all_pools()

# ❌ WRONG - Missing await
db.cleanup_all_pools()  # Returns coroutine, doesn't execute!
```

**Why**: Without `await`, async methods don't execute.

---

## FAQ

### Q: Do I need to change my pytest configuration?

**A**: Yes, add these to `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

This ensures function-scoped event loops.

---

### Q: Can I use SQLite instead of PostgreSQL for tests?

**A**: Yes! SQLite is faster for unit tests:

```python
@pytest.fixture
def db_sqlite():
    return DataFlow(":memory:")  # In-memory database


def test_fast_unit(db_sqlite):
    # ~50ms per test (vs ~200ms PostgreSQL)
```

Use PostgreSQL for integration tests, SQLite for unit tests.

---

### Q: How do I run tests in parallel?

**A**: Use pytest-xdist with isolated databases:

```bash
pip install pytest-xdist
pytest tests/ -n 4  # Run with 4 workers
```

Each worker needs isolated database. See fixture patterns guide.

---

### Q: My tests are slow. How can I optimize?

**A**: Three strategies:

1. **Use SQLite for unit tests** (10x faster)
2. **Use module-scoped fixtures** for integration tests (reuse pools)
3. **Reduce pool sizes** (`pool_size=1, max_overflow=0`)

See fixture patterns guide for details.

---

### Q: Should I use test mode explicitly?

**A**: No, DataFlow auto-detects pytest:

```python
# Auto-detection works
db = DataFlow("postgresql://...")
assert db._test_mode is True  # When running under pytest

# Explicit only if auto-detection fails
db = DataFlow("postgresql://...", test_mode=True)
```

---

### Q: How do I debug failing tests?

**A**: Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check pool metrics:

```python
metrics = db.get_cleanup_metrics()
print(f"Active pools: {metrics['active_pools']}")
```

See troubleshooting guide for more debugging techniques.

---

### Q: Can I use unittest instead of pytest?

**A**: DataFlow is optimized for pytest. Unittest requires manual event loop management:

```python
import unittest
import asyncio


class TestUser(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_user_create(self):
        async def run_test():
            db = DataFlow("postgresql://...")
            # Test code
            await db.cleanup_all_pools()

        self.loop.run_until_complete(run_test())
```

**Recommendation**: Use pytest for simpler, cleaner tests.

---

## Common Pitfalls

### Pitfall 1: Reusing DataFlow Instance Across Tests

```python
# ❌ WRONG - Module-level instance
db = DataFlow("postgresql://...")  # Created once


@pytest.mark.asyncio
async def test_1():
    # Uses shared instance
    pass


@pytest.mark.asyncio
async def test_2():
    # Contaminated by test_1!
    pass
```

**Fix**: Use fixture to create instance per test.

---

### Pitfall 2: Not Awaiting Cleanup

```python
# ❌ WRONG
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")
    yield db
    db.cleanup_all_pools()  # Missing await!
```

**Fix**: Always `await` async methods.

---

### Pitfall 3: Mixing Sync and Async Fixtures

```python
# ❌ WRONG
@pytest.fixture  # Not async!
def db():
    db = DataFlow("postgresql://...")
    yield db
    # Can't await in sync function
```

**Fix**: Make fixture async if it needs `await`:

```python
# ✅ CORRECT
@pytest.fixture
async def db():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()
```

---

## Testing Checklist

Before writing tests, ensure:

- ✅ pytest and pytest-asyncio installed
- ✅ pytest.ini configured with `asyncio_mode = auto`
- ✅ Function-scoped event loop fixture in conftest.py
- ✅ DataFlow fixture with cleanup in conftest.py
- ✅ Test database running and accessible
- ✅ Environment variables configured (.env)

Before running tests, verify:

- ✅ Database is running (`docker ps | grep postgres`)
- ✅ Connection URL is correct
- ✅ All fixtures have proper scope
- ✅ Cleanup methods use `await`

---

## Example Test Suite

Complete example with all best practices:

```python
# tests/conftest.py
"""Shared pytest fixtures for DataFlow testing."""
import asyncio
import os
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
    finally:
        loop.close()
        asyncio.set_event_loop(None)


@pytest.fixture(scope="function")
async def db():
    """Function-scoped DataFlow with cleanup."""
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5434/dataflow_test"
    )

    db = DataFlow(database_url, pool_size=1, max_overflow=0)
    yield db

    try:
        await db.cleanup_all_pools()
    except Exception as e:
        import logging
        logging.warning(f"Cleanup failed: {e}")


@pytest.fixture
def sample_users():
    """Sample user data."""
    return [
        {"id": "user-1", "name": "Alice", "email": "alice@example.com"},
        {"id": "user-2", "name": "Bob", "email": "bob@example.com"},
    ]
```

```python
# tests/test_user.py
"""User model tests."""
import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime


@pytest.mark.asyncio
async def test_user_create(db, sample_users):
    """Test user creation."""

    @db.model
    class User:
        name: str
        email: str

    await db.initialize()

    # Create user
    user_data = sample_users[0]
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", user_data)

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

    assert results["create"]["id"] == user_data["id"]
    assert results["create"]["name"] == user_data["name"]


@pytest.mark.asyncio
async def test_user_read(db, sample_users):
    """Test user read."""

    @db.model
    class User:
        name: str
        email: str

    await db.initialize()

    # Create user first
    user_data = sample_users[0]
    create_workflow = WorkflowBuilder()
    create_workflow.add_node("UserCreateNode", "create", user_data)

    runtime = AsyncLocalRuntime()
    await runtime.execute_workflow_async(create_workflow.build(), inputs={})

    # Read user back
    read_workflow = WorkflowBuilder()
    read_workflow.add_node("UserReadNode", "read", {"id": user_data["id"]})

    results, _ = await runtime.execute_workflow_async(read_workflow.build(), inputs={})

    assert results["read"]["id"] == user_data["id"]
    assert results["read"]["name"] == user_data["name"]
```

---

## Next Steps

### 1. Set Up Your Test Environment
👉 **Read**: `setup-guide.md`
📝 **Do**: Install pytest, configure pytest.ini, create conftest.py
⏱️ **Time**: 10 minutes

### 2. Learn Fixture Patterns
👉 **Read**: `fixture-patterns.md`
📝 **Do**: Implement function-scoped fixtures with cleanup
⏱️ **Time**: 15 minutes

### 3. Write Your First Test
📝 **Do**: Create test file, define model, test CRUD operations
⏱️ **Time**: 5 minutes

### 4. Troubleshoot Issues (If Needed)
👉 **Read**: `troubleshooting.md`
📝 **Do**: Find your error, apply solution
⏱️ **Time**: 5 minutes per error

---

## Additional Resources

### DataFlow Documentation
- **Main CLAUDE.md**: `/packages/kailash-dataflow/CLAUDE.md`
- **User Guide**: `/packages/kailash-dataflow/docs/USER_GUIDE.md`
- **Under the Hood**: `/packages/kailash-dataflow/docs/UNDER_THE_HOOD.md`

### Test Examples
- **Unit Tests**: `/packages/kailash-dataflow/tests/unit/`
- **Integration Tests**: `/packages/kailash-dataflow/tests/integration/`
- **E2E Tests**: `/packages/kailash-dataflow/tests/e2e/`

### pytest Documentation
- **Official Docs**: https://docs.pytest.org/
- **pytest-asyncio**: https://pytest-asyncio.readthedocs.io/
- **Fixtures Guide**: https://docs.pytest.org/en/stable/fixture.html

---

## Getting Help

### Check Documentation First
1. **Setup issues?** → `setup-guide.md`
2. **Errors?** → `troubleshooting.md`
3. **Fixture questions?** → `fixture-patterns.md`

### Still Stuck?
1. **Enable debug logging** (`logging.basicConfig(level=logging.DEBUG)`)
2. **Check pool metrics** (`db.get_cleanup_metrics()`)
3. **Run single test** (`pytest tests/test_user.py::test_specific -v -s`)
4. **Review DataFlow test suite** for working examples

### Report Issues
- Check if error is in troubleshooting guide
- Include exact error message
- Include minimal reproducible example
- Include pytest and DataFlow versions

---

## Summary

**Essential Files**:
- `pytest.ini` - Configure asyncio mode
- `tests/conftest.py` - Event loop and DataFlow fixtures
- `tests/test_*.py` - Your test files

**Essential Pattern**:
```python
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...")
    yield db
    await db.cleanup_all_pools()
```

**Essential Rule**: Function-scoped fixtures with cleanup solve 90% of issues.

**You're ready to write DataFlow tests!** Start with setup-guide.md and you'll be testing in 5 minutes.
