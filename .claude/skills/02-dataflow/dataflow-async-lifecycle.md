# DataFlow Async Lifecycle Methods

## Overview

DataFlow v0.10.7+ provides proper async lifecycle methods for use in async contexts like FastAPI lifespan events, pytest async fixtures, and async main functions.

## The Problem (DF-501 Error)

Sync methods like `create_tables()` and `close()` fail in async contexts with event loop conflicts:

```
RuntimeError: Cannot run sync method in running event loop
RuntimeError: Event loop is closed
```

## Async Methods Reference

| Sync Method | Async Alternative | Usage |
|-------------|-------------------|-------|
| `create_tables()` | `create_tables_async()` | Table creation in async contexts |
| `close()` | `close_async()` | Cleanup in async contexts |
| `_ensure_migration_tables()` | `_ensure_migration_tables_async()` | Internal migration tables |

## When to Use Each

**Use Async Methods When:**
- Inside FastAPI lifespan events (`@asynccontextmanager async def lifespan()`)
- Inside pytest async fixtures (`@pytest.fixture async def db()`)
- Inside async main functions (`async def main()`)
- Any code running in an async context with `asyncio.get_running_loop()`

**Use Sync Methods When:**
- CLI scripts and management commands
- Sync pytest tests (non-async)
- Any code NOT running in an async context

## FastAPI Integration Pattern

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dataflow import DataFlow

db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str
    email: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Use async version
    await db.create_tables_async()
    yield
    # Shutdown: Use async version
    await db.close_async()

app = FastAPI(lifespan=lifespan)

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    return await db.express.read("User", user_id)
```

## Pytest Async Fixture Pattern

```python
import pytest
from dataflow import DataFlow

@pytest.fixture
async def db():
    """Async fixture with proper cleanup."""
    db = DataFlow("postgresql://...", test_mode=True)

    @db.model
    class User:
        id: str
        name: str

    # Use async version in async context
    await db.create_tables_async()

    yield db

    # Use async cleanup
    await db.close_async()

@pytest.mark.asyncio
async def test_user_creation(db):
    # Test with async db fixture
    pass
```

## Sync Context Detection

DataFlow sync methods detect when called from async context and raise clear errors:

```python
# In async context (e.g., async def main())
try:
    db.create_tables()  # Raises RuntimeError
except RuntimeError as e:
    print(e)
    # Output: Cannot use create_tables() in async context - use create_tables_async() instead.
    # See DF-501 for details.
```

## Error Messages

**DF-501 for create_tables():**
```
RuntimeError: Cannot use create_tables() in async context - use create_tables_async() instead.
See DF-501 for details.
```

**DF-501 for _ensure_migration_tables():**
```
RuntimeError: Cannot use _ensure_migration_tables() in async context - use _ensure_migration_tables_async() instead.
See DF-501 for details.
```

## Migration from Sync to Async

**Before (DF-501 Error):**
```python
# WRONG - Causes DF-501 in async context
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = DataFlow("postgresql://...")

    @db.model
    class User:
        id: str
        name: str

    db.create_tables()  # DF-501 ERROR!
    yield
    db.close()  # May fail silently
```

**After (v0.10.7+ Fix):**
```python
# CORRECT - Use async methods in async context
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = DataFlow("postgresql://...")

    @db.model
    class User:
        id: str
        name: str

    await db.create_tables_async()  # Works correctly
    yield
    await db.close_async()  # Proper cleanup
```

## close_async() Method Details

The `close_async()` method properly cleans up all DataFlow resources:

```python
async def close_async(self):
    """Close database connections and clean up resources (async version)."""
    # Closes connection pool manager
    # Closes memory connections (SQLite)
    # Clears internal state
```

**Safe to Call Multiple Times:**
```python
await db.close_async()  # First call - cleans up
await db.close_async()  # Second call - no-op, safe
await db.close_async()  # Third call - no-op, safe
```

## Context Manager Support

DataFlow supports sync context managers for CLI/scripts:

```python
# Sync context manager (for CLI/scripts)
with DataFlow("sqlite:///dev.db") as db:
    @db.model
    class User:
        id: str
        name: str

    db.create_tables()  # OK in sync context
    # Automatic cleanup when exiting context

# For async contexts, use the lifespan pattern above
```

## File References

- **Implementation**: `src/dataflow/core/engine.py:7180-7230` (close_async, close methods)
- **Async Table Creation**: `src/dataflow/core/engine.py:4100-4200` (create_tables_async)
- **Error Messages**: `src/dataflow/platform/errors.py:2757-2783` (DF-501 error codes)
- **Tests**: `tests/integration/test_dataflow_async_lifecycle.py` (16 comprehensive tests)

## Version Requirements

- DataFlow v0.10.7+ for async lifecycle methods
- Python 3.10+
