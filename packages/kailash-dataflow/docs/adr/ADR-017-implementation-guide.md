# ADR-017: Implementation Guide

## Purpose
This document provides **concrete code changes** needed to implement the test mode API. Each section shows exactly where to add code and what to add.

---

## File 1: DataFlow Engine

**File**: `/packages/kailash-dataflow/src/dataflow/core/engine.py`

### Change 1: Add Class Attributes (After line 31)

```python
class DataFlow:
    """Main DataFlow interface."""

    # ADR-017: Global test mode control
    _global_test_mode: Optional[bool] = None
    _global_test_mode_lock = threading.RLock()

    def __init__(
        self,
        # ... existing parameters ...
```

### Change 2: Add Constructor Parameters (Lines 34-62)

**Before**:
```python
def __init__(
    self,
    database_url: Optional[str] = None,
    config: Optional[DataFlowConfig] = None,
    # ... existing params ...
    tdd_mode: bool = False,
    test_context: Optional[Any] = None,
    migration_lock_timeout: int = 30,
    **kwargs,
):
```

**After**:
```python
def __init__(
    self,
    database_url: Optional[str] = None,
    config: Optional[DataFlowConfig] = None,
    # ... existing params ...
    tdd_mode: bool = False,
    test_context: Optional[Any] = None,
    test_mode: Optional[bool] = None,  # NEW
    test_mode_aggressive_cleanup: bool = True,  # NEW
    migration_lock_timeout: int = 30,
    **kwargs,
):
```

### Change 3: Add Test Mode Detection (After config initialization, ~line 200)

**Add this block after config is initialized but before model registration**:

```python
# ADR-017: Test mode detection and configuration
self._test_mode = self._resolve_test_mode(test_mode)
self._test_mode_aggressive_cleanup = test_mode_aggressive_cleanup

# Log test mode activation
if self._test_mode:
    if test_mode is None:
        if self._global_test_mode is not None:
            logger.info("DataFlow: Test mode enabled (global setting)")
        else:
            logger.info(
                "DataFlow: Test mode enabled (auto-detected pytest environment)"
            )
    else:
        logger.info("DataFlow: Test mode enabled (explicitly set)")

    if self._test_mode_aggressive_cleanup:
        logger.debug("DataFlow: Aggressive pool cleanup enabled for test mode")
```

### Change 4: Add Private Method _resolve_test_mode() (Add to class)

```python
def _resolve_test_mode(self, explicit_test_mode: Optional[bool]) -> bool:
    """Resolve test mode from explicit setting, global setting, or auto-detection.

    Priority:
    1. Explicit test_mode parameter (highest)
    2. Global test mode setting
    3. Auto-detection (lowest)

    Args:
        explicit_test_mode: Explicit test mode setting (None, True, False)

    Returns:
        bool: Resolved test mode
    """
    # Priority 1: Explicit parameter
    if explicit_test_mode is not None:
        return explicit_test_mode

    # Priority 2: Global test mode
    with self._global_test_mode_lock:
        if self._global_test_mode is not None:
            return self._global_test_mode

    # Priority 3: Auto-detection
    return self._detect_test_environment()
```

### Change 5: Add Private Method _detect_test_environment() (Add to class)

```python
def _detect_test_environment(self) -> bool:
    """Detect if running in test environment.

    Detection Strategy:
    1. Check PYTEST_CURRENT_TEST environment variable
    2. Check if 'pytest' in sys.modules
    3. Check if '_' environment variable contains 'pytest'

    Returns:
        bool: True if test environment detected
    """
    import sys

    # Strategy 1: Check PYTEST_CURRENT_TEST (most reliable)
    if os.getenv("PYTEST_CURRENT_TEST") is not None:
        return True

    # Strategy 2: Check if pytest is imported
    if "pytest" in sys.modules:
        return True

    # Strategy 3: Check _ environment variable
    if "pytest" in os.getenv("_", ""):
        return True

    return False
```

### Change 6: Add Class Methods (Add to class)

```python
@classmethod
def enable_test_mode(cls) -> None:
    """Enable test mode globally for all new DataFlow instances."""
    with cls._global_test_mode_lock:
        cls._global_test_mode = True
        logger.info("DataFlow: Global test mode enabled")


@classmethod
def disable_test_mode(cls) -> None:
    """Disable global test mode, reverting to auto-detection."""
    with cls._global_test_mode_lock:
        cls._global_test_mode = None
        logger.info(
            "DataFlow: Global test mode disabled (auto-detection restored)"
        )


@classmethod
def is_test_mode_enabled(cls) -> Optional[bool]:
    """Get current global test mode setting.

    Returns:
        Optional[bool]: True/False if set, None if auto-detection
    """
    with cls._global_test_mode_lock:
        return cls._global_test_mode
```

### Change 7: Add Instance Methods (Add to class)

```python
async def cleanup_stale_pools(self) -> Dict[str, Any]:
    """Proactively detect and cleanup stale connection pools.

    Returns:
        Dict[str, Any]: Cleanup metrics
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    start_time = time.time()
    stale_pools_found = 0
    stale_pools_cleaned = 0
    cleanup_failures = 0
    cleanup_errors = []

    try:
        cleaned = await AsyncSQLDatabaseNode._cleanup_closed_loop_pools()
        stale_pools_found = cleaned
        stale_pools_cleaned = cleaned

        if self._test_mode:
            logger.info(
                f"DataFlow: Cleaned {cleaned} stale connection pools (test mode)"
            )
    except Exception as e:
        cleanup_failures += 1
        error_msg = f"Stale pool cleanup failed: {str(e)}"
        cleanup_errors.append(error_msg)
        logger.warning(f"DataFlow: {error_msg}", exc_info=True)

    duration_ms = (time.time() - start_time) * 1000

    return {
        "stale_pools_found": stale_pools_found,
        "stale_pools_cleaned": stale_pools_cleaned,
        "cleanup_failures": cleanup_failures,
        "cleanup_errors": cleanup_errors,
        "cleanup_duration_ms": duration_ms,
    }


async def cleanup_all_pools(self, force: bool = False) -> Dict[str, Any]:
    """Cleanup all connection pools managed by DataFlow.

    WARNING: Destructive operation - closes ALL pools.

    Args:
        force: If True, forcefully close pools

    Returns:
        Dict[str, Any]: Cleanup metrics
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    start_time = time.time()
    total_pools = len(AsyncSQLDatabaseNode._shared_pools)
    pools_cleaned = 0
    cleanup_failures = 0
    cleanup_errors = []

    try:
        result = await AsyncSQLDatabaseNode.clear_shared_pools(graceful=not force)
        pools_cleaned = result["pools_cleared"]
        cleanup_failures = result["clear_failures"]
        cleanup_errors = result["clear_errors"]

        if self._test_mode:
            logger.info(
                f"DataFlow: Cleared all {pools_cleaned} connection pools "
                f"(test mode, force={force})"
            )
    except Exception as e:
        cleanup_failures = total_pools
        error_msg = f"Pool cleanup failed: {str(e)}"
        cleanup_errors.append(error_msg)
        logger.error(f"DataFlow: {error_msg}", exc_info=True)

    duration_ms = (time.time() - start_time) * 1000

    return {
        "total_pools": total_pools,
        "pools_cleaned": pools_cleaned,
        "cleanup_failures": cleanup_failures,
        "cleanup_errors": cleanup_errors,
        "cleanup_duration_ms": duration_ms,
        "forced": force,
    }


def get_cleanup_metrics(self) -> Dict[str, Any]:
    """Get connection pool lifecycle metrics.

    Returns:
        Dict[str, Any]: Pool metrics
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    shared_pools = AsyncSQLDatabaseNode._shared_pools

    # Extract unique event loop IDs
    event_loop_ids = set()
    for pool_key in shared_pools.keys():
        loop_id = pool_key.split("|")[0]
        try:
            event_loop_ids.add(int(loop_id))
        except (ValueError, IndexError):
            pass

    return {
        "active_pools": len(shared_pools),
        "total_pools_created": getattr(
            AsyncSQLDatabaseNode, "_total_pools_created", len(shared_pools)
        ),
        "test_mode_enabled": self._test_mode,
        "aggressive_cleanup_enabled": self._test_mode_aggressive_cleanup,
        "pool_keys": list(shared_pools.keys()),
        "event_loop_ids": list(event_loop_ids),
    }
```

---

## File 2: AsyncSQLDatabaseNode

**File**: `/src/kailash/nodes/data/async_sql.py`

### Change 1: Enhance _cleanup_closed_loop_pools() (Lines 4034-4072)

**Replace existing method with**:

```python
@classmethod
async def _cleanup_closed_loop_pools(cls) -> int:
    """Proactively remove pools from closed event loops.

    Returns:
        int: Number of pools cleaned
    """
    cleaned_count = 0
    pools_to_remove = []

    try:
        current_loop = asyncio.get_event_loop()
        current_loop_id = id(current_loop)
    except RuntimeError:
        logger.warning(
            "AsyncSQLDatabaseNode: No event loop available for cleanup"
        )
        return 0

    # Phase 1: Identify stale pools
    for pool_key, (adapter, creation_time) in list(cls._shared_pools.items()):
        loop_id_str = pool_key.split("|")[0]

        try:
            pool_loop_id = int(loop_id_str)
        except (ValueError, IndexError):
            logger.warning(
                f"AsyncSQLDatabaseNode: Invalid pool key format: {pool_key}"
            )
            continue

        # Check if pool's event loop differs from current
        if pool_loop_id != current_loop_id:
            pools_to_remove.append(pool_key)
            logger.debug(
                f"AsyncSQLDatabaseNode: Marked stale pool {pool_key} "
                f"(loop {pool_loop_id} != current {current_loop_id})"
            )

    # Phase 2: Cleanup stale pools
    for pool_key in pools_to_remove:
        try:
            adapter, creation_time = cls._shared_pools.pop(pool_key)

            # Attempt graceful close
            try:
                if hasattr(adapter, "close"):
                    await adapter.close()
            except Exception as close_error:
                logger.debug(
                    f"AsyncSQLDatabaseNode: Could not close adapter for "
                    f"{pool_key}: {close_error}"
                )

            cleaned_count += 1
            logger.info(f"AsyncSQLDatabaseNode: Cleaned stale pool {pool_key}")
        except Exception as e:
            logger.warning(
                f"AsyncSQLDatabaseNode: Failed to cleanup pool {pool_key}: {e}"
            )

    if cleaned_count > 0:
        logger.info(
            f"AsyncSQLDatabaseNode: Cleaned {cleaned_count} stale pools"
        )

    return cleaned_count
```

### Change 2: Enhance clear_shared_pools() (Lines 4072-4073)

**Replace existing method with**:

```python
@classmethod
async def clear_shared_pools(cls, graceful: bool = True) -> Dict[str, Any]:
    """Clear all shared connection pools with enhanced error handling.

    Args:
        graceful: If True, attempts graceful close

    Returns:
        Dict[str, Any]: Cleanup metrics
    """
    total_pools = len(cls._shared_pools)
    pools_cleared = 0
    clear_failures = 0
    clear_errors = []

    if total_pools == 0:
        return {
            "total_pools": 0,
            "pools_cleared": 0,
            "clear_failures": 0,
            "clear_errors": [],
        }

    logger.info(
        f"AsyncSQLDatabaseNode: Clearing {total_pools} shared pools "
        f"(graceful={graceful})"
    )

    pool_keys = list(cls._shared_pools.keys())

    for pool_key in pool_keys:
        try:
            adapter, creation_time = cls._shared_pools.pop(pool_key)

            if graceful and hasattr(adapter, "close"):
                try:
                    await adapter.close()
                    logger.debug(
                        f"AsyncSQLDatabaseNode: Gracefully closed pool {pool_key}"
                    )
                except Exception as close_error:
                    logger.warning(
                        f"AsyncSQLDatabaseNode: Error closing pool {pool_key}: "
                        f"{close_error}"
                    )

            pools_cleared += 1
        except Exception as e:
            clear_failures += 1
            error_msg = f"Failed to clear pool {pool_key}: {str(e)}"
            clear_errors.append(error_msg)
            logger.error(f"AsyncSQLDatabaseNode: {error_msg}")

    logger.info(
        f"AsyncSQLDatabaseNode: Cleared {pools_cleared}/{total_pools} pools "
        f"({clear_failures} failures)"
    )

    return {
        "total_pools": total_pools,
        "pools_cleared": pools_cleared,
        "clear_failures": clear_failures,
        "clear_errors": clear_errors,
    }
```

### Change 3: Add Class Attribute (After class definition, ~line 380)

```python
class AsyncSQLDatabaseNode(AsyncNode):
    """Async SQL database operations node."""

    _shared_pools: Dict[str, Tuple[Any, float]] = {}
    _total_pools_created: int = 0  # NEW: Track total pools created

    # ... rest of class
```

### Change 4: Update Pool Creation (In initialize() or connect() method)

**When creating a new pool, increment counter**:

```python
# In the method where pools are created (around line 560)
async def initialize(self) -> None:
    """Initialize the connection pool."""
    async with self._lock:
        if self._adapter is None:
            self._adapter = self.adapter_class(self.database_config)
            await self._adapter.connect()
            self._pool = self._adapter._pool

            # NEW: Increment counter
            AsyncSQLDatabaseNode._total_pools_created += 1

            # ... rest of initialization
```

---

## File 3: Unit Tests

**File**: `/packages/kailash-dataflow/tests/test_test_mode.py` (NEW FILE)

```python
"""Unit tests for test mode API (ADR-017)."""

import os
import pytest
from dataflow import DataFlow


def test_auto_detect_pytest_environment():
    """Test automatic pytest environment detection."""
    # PYTEST_CURRENT_TEST is set by pytest automatically
    db = DataFlow("sqlite:///:memory:")
    assert db._test_mode == True


def test_explicit_test_mode_true():
    """Test explicit test mode enable."""
    db = DataFlow("sqlite:///:memory:", test_mode=True)
    assert db._test_mode == True


def test_explicit_test_mode_false():
    """Test explicit test mode disable."""
    db = DataFlow("sqlite:///:memory:", test_mode=False)
    assert db._test_mode == False


def test_global_test_mode():
    """Test global test mode control."""
    # Enable globally
    DataFlow.enable_test_mode()
    db1 = DataFlow("sqlite:///:memory:")
    assert db1._test_mode == True

    # Disable globally
    DataFlow.disable_test_mode()
    db2 = DataFlow("sqlite:///:memory:")
    # Should fall back to auto-detection (True in pytest)
    assert db2._test_mode == True


def test_explicit_overrides_global():
    """Test explicit setting overrides global."""
    DataFlow.enable_test_mode()
    db = DataFlow("sqlite:///:memory:", test_mode=False)
    assert db._test_mode == False
    DataFlow.disable_test_mode()


def test_test_mode_logging(caplog):
    """Test test mode activation is logged."""
    import logging
    caplog.set_level(logging.INFO)

    db = DataFlow("sqlite:///:memory:", test_mode=True)
    assert "Test mode enabled" in caplog.text


@pytest.mark.asyncio
async def test_cleanup_stale_pools():
    """Test stale pool cleanup."""
    db = DataFlow("sqlite:///:memory:", test_mode=True)

    metrics = await db.cleanup_stale_pools()

    assert "stale_pools_found" in metrics
    assert "stale_pools_cleaned" in metrics
    assert "cleanup_failures" in metrics
    assert "cleanup_errors" in metrics
    assert "cleanup_duration_ms" in metrics
    assert metrics["cleanup_failures"] == 0


@pytest.mark.asyncio
async def test_cleanup_all_pools():
    """Test cleanup all pools."""
    db = DataFlow("sqlite:///:memory:", test_mode=True)

    metrics = await db.cleanup_all_pools()

    assert "total_pools" in metrics
    assert "pools_cleaned" in metrics
    assert "cleanup_failures" in metrics
    assert "cleanup_errors" in metrics
    assert "cleanup_duration_ms" in metrics
    assert "forced" in metrics


def test_get_cleanup_metrics():
    """Test cleanup metrics retrieval."""
    db = DataFlow("sqlite:///:memory:", test_mode=True)

    metrics = db.get_cleanup_metrics()

    assert "active_pools" in metrics
    assert "total_pools_created" in metrics
    assert "test_mode_enabled" in metrics
    assert "aggressive_cleanup_enabled" in metrics
    assert "pool_keys" in metrics
    assert "event_loop_ids" in metrics
    assert metrics["test_mode_enabled"] == True


@pytest.mark.asyncio
async def test_graceful_degradation():
    """Test cleanup gracefully handles errors."""
    db = DataFlow("sqlite:///:memory:", test_mode=True)

    # Should not raise exception even if cleanup fails
    try:
        metrics = await db.cleanup_all_pools()
        # Should succeed (no pools to cleanup)
        assert metrics["cleanup_failures"] == 0
    except Exception as e:
        pytest.fail(f"Cleanup should not raise: {e}")
```

---

## File 4: Integration Tests

**File**: `/packages/kailash-dataflow/tests/integration/test_test_mode_integration.py` (NEW FILE)

```python
"""Integration tests for test mode fixtures (ADR-017)."""

import pytest
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture(scope="function")
async def db():
    """Function-scoped database with cleanup."""
    db = DataFlow("postgresql://localhost/test_db", test_mode=True)
    yield db
    await db.cleanup_all_pools()


@pytest.mark.asyncio
async def test_basic_fixture_pattern(db):
    """Test basic fixture pattern with cleanup."""
    @db.model
    class User:
        id: str
        name: str

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-1",
        "name": "Alice"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build())

    assert results["create"]["name"] == "Alice"

    # Fixture handles cleanup automatically


@pytest.mark.asyncio
async def test_sequential_isolation_1(db):
    """Test 1: Create user."""
    @db.model
    class User:
        id: str
        name: str

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-seq-1",
        "name": "Sequential Test 1"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build())
    assert results["create"]["id"] == "user-seq-1"


@pytest.mark.asyncio
async def test_sequential_isolation_2(db):
    """Test 2: Should not see data from test 1."""
    @db.model
    class User:
        id: str
        name: str

    # Should not see user-seq-1 from previous test
    # (depends on proper fixture cleanup)

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-seq-2",
        "name": "Sequential Test 2"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build())
    assert results["create"]["id"] == "user-seq-2"


@pytest.mark.asyncio
async def test_cleanup_metrics(db):
    """Test cleanup metrics are accurate."""
    initial_metrics = db.get_cleanup_metrics()
    initial_pools = initial_metrics["active_pools"]

    @db.model
    class Data:
        id: str

    # Create some data (may create pool)
    workflow = WorkflowBuilder()
    workflow.add_node("DataCreateNode", "create", {"id": "data-1"})
    runtime = AsyncLocalRuntime()
    await runtime.execute_workflow_async(workflow.build())

    # Check metrics after operations
    final_metrics = db.get_cleanup_metrics()
    # Pools should not grow unbounded
    assert final_metrics["active_pools"] <= initial_pools + 5
```

---

## File 5: Example Fixture

**File**: `/packages/kailash-dataflow/docs/testing/examples/conftest.py` (NEW FILE)

```python
"""Pytest fixtures for DataFlow testing."""

import pytest
from dataflow import DataFlow


@pytest.fixture(scope="function")
async def db():
    """Function-scoped database - clean slate per test.

    Usage:
        @pytest.mark.asyncio
        async def test_something(db):
            @db.model
            class MyModel:
                id: str

            # Test operations...
    """
    db = DataFlow(
        "postgresql://localhost/test_db",
        test_mode=True,
        test_mode_aggressive_cleanup=True
    )

    yield db

    # Cleanup after test
    metrics = await db.cleanup_all_pools()
    if metrics["cleanup_failures"] > 0:
        print(f"⚠️ Pool cleanup had {metrics['cleanup_failures']} failures")


@pytest.fixture(scope="module")
async def db_module():
    """Module-scoped database - shared across module.

    Usage:
        @pytest.mark.asyncio
        async def test_something(db_module):
            # Shared database across all tests in module
    """
    db = DataFlow("postgresql://localhost/test_db", test_mode=True)

    yield db

    # Cleanup at module end
    await db.cleanup_all_pools()


@pytest.fixture(scope="session", autouse=True)
def enable_test_mode():
    """Enable test mode globally for all tests (auto-use)."""
    DataFlow.enable_test_mode()
    yield
    DataFlow.disable_test_mode()
```

---

## File 6: Example Test

**File**: `/packages/kailash-dataflow/docs/testing/examples/basic_test.py` (NEW FILE)

```python
"""Basic CRUD test example."""

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.asyncio
async def test_user_create_and_read(db):
    """Test basic user creation and retrieval."""
    @db.model
    class User:
        id: str
        name: str
        email: str

    # Create user
    create_workflow = WorkflowBuilder()
    create_workflow.add_node("UserCreateNode", "create", {
        "id": "user-001",
        "name": "Alice",
        "email": "alice@example.com"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(create_workflow.build())

    assert results["create"]["id"] == "user-001"
    assert results["create"]["name"] == "Alice"

    # Read user
    read_workflow = WorkflowBuilder()
    read_workflow.add_node("UserReadNode", "read", {
        "id": "user-001"
    })

    results, _ = await runtime.execute_workflow_async(read_workflow.build())
    assert results["read"]["email"] == "alice@example.com"
```

---

## Implementation Checklist

### Phase 1: Core API (Week 1)

- [ ] **File 1, Change 1**: Add class attributes to DataFlow
- [ ] **File 1, Change 2**: Add constructor parameters
- [ ] **File 1, Change 3**: Add test mode detection logic
- [ ] **File 1, Change 4**: Add `_resolve_test_mode()` method
- [ ] **File 1, Change 5**: Add `_detect_test_environment()` method
- [ ] **File 1, Change 6**: Add class methods (enable/disable/is_enabled)
- [ ] **File 3**: Create unit tests file
- [ ] **Run tests**: `pytest packages/kailash-dataflow/tests/test_test_mode.py`

### Phase 2: Cleanup Methods (Week 2)

- [ ] **File 1, Change 7**: Add instance methods (cleanup_stale/cleanup_all/get_metrics)
- [ ] **File 2, Change 1**: Enhance `_cleanup_closed_loop_pools()`
- [ ] **File 2, Change 2**: Enhance `clear_shared_pools()`
- [ ] **File 2, Change 3**: Add `_total_pools_created` attribute
- [ ] **File 2, Change 4**: Update pool creation counter
- [ ] **File 4**: Create integration tests
- [ ] **Run tests**: `pytest packages/kailash-dataflow/tests/integration/`

### Phase 3: Documentation (Week 3)

- [ ] **File 5**: Create example fixtures
- [ ] **File 6**: Create example test
- [ ] Create `/packages/kailash-dataflow/docs/testing/README.md`
- [ ] Create `/packages/kailash-dataflow/docs/testing/fixture-patterns.md`
- [ ] Create `/packages/kailash-dataflow/docs/testing/troubleshooting.md`

### Phase 4: Validation (Week 4)

- [ ] Run full test suite: `pytest packages/kailash-dataflow/`
- [ ] Performance benchmarks: `pytest --benchmark`
- [ ] Documentation validation: `pytest --doctest-modules`
- [ ] User testing: 3+ developers try examples
- [ ] Update CHANGELOG.md
- [ ] Draft release notes

---

## Testing Commands

```bash
# Run unit tests only
pytest packages/kailash-dataflow/tests/test_test_mode.py -v

# Run integration tests
pytest packages/kailash-dataflow/tests/integration/test_test_mode_integration.py -v

# Run all DataFlow tests
pytest packages/kailash-dataflow/tests/ -v

# Run with coverage
pytest packages/kailash-dataflow/tests/ --cov=dataflow --cov-report=html

# Run documentation examples
pytest packages/kailash-dataflow/docs/testing/examples/basic_test.py -v

# Check for regressions (existing tests)
pytest packages/kailash-dataflow/tests/ -k "not test_mode"
```

---

## Verification

After implementation, verify:

1. **All existing tests pass**
   ```bash
   pytest packages/kailash-dataflow/tests/ -v
   ```

2. **New tests pass**
   ```bash
   pytest packages/kailash-dataflow/tests/test_test_mode.py -v
   ```

3. **No breaking changes**
   ```python
   # Old code still works
   db = DataFlow("postgresql://...")
   ```

4. **Test mode auto-detection works**
   ```python
   # In pytest, test mode automatically enabled
   db = DataFlow("postgresql://...")
   assert db._test_mode == True
   ```

5. **Cleanup works**
   ```python
   metrics = await db.cleanup_all_pools()
   assert metrics["cleanup_failures"] == 0
   ```

---

## Approval

**Author**: Claude (Implementation Specialist)
**Date**: 2025-10-30
**Status**: Ready for Implementation

**Implementation Order**:
1. Phase 1 (Week 1) - Core API
2. Phase 2 (Week 2) - Cleanup methods
3. Phase 3 (Week 3) - Documentation
4. Phase 4 (Week 4) - Validation
