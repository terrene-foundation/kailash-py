# ADR-017: Test Mode API Specification

## Document Purpose
This document provides the **complete API specification** for DataFlow test mode enhancements. It defines method signatures, parameters, return types, usage patterns, and integration points for implementing ADR-017 testing improvements.

---

## 1. API Specification

### 1.1 DataFlow Constructor Enhancement

**Location**: `/packages/kailash-dataflow/src/dataflow/core/engine.py`

**Current Signature** (lines 34-62):
```python
def __init__(
    self,
    database_url: Optional[str] = None,
    config: Optional[DataFlowConfig] = None,
    pool_size: Optional[int] = None,
    # ... existing parameters ...
    tdd_mode: bool = False,
    test_context: Optional[Any] = None,
    **kwargs,
):
```

**Enhanced Signature** (NEW):
```python
def __init__(
    self,
    database_url: Optional[str] = None,
    config: Optional[DataFlowConfig] = None,
    pool_size: Optional[int] = None,
    # ... existing parameters ...
    tdd_mode: bool = False,
    test_context: Optional[Any] = None,
    test_mode: Optional[bool] = None,  # NEW: Explicit test mode control
    test_mode_aggressive_cleanup: bool = True,  # NEW: Enable aggressive pool cleanup in test mode
    **kwargs,
):
    """Initialize DataFlow.

    Args:
        test_mode: Explicitly enable/disable test mode.
                   - True: Force test mode (proactive cleanup, enhanced logging)
                   - False: Disable test mode (production behavior)
                   - None: Auto-detect (checks PYTEST_CURRENT_TEST env var)
        test_mode_aggressive_cleanup: Enable aggressive pool cleanup in test mode.
                   Only effective when test_mode=True or auto-detected.
                   Enables proactive stale pool detection and cleanup.

    Examples:
        # Auto-detect pytest environment (recommended)
        db = DataFlow("postgresql://...")  # test_mode=None (auto)

        # Explicit test mode (manual testing, debugging)
        db = DataFlow("postgresql://...", test_mode=True)

        # Force production mode (disable test mode even in pytest)
        db = DataFlow("postgresql://...", test_mode=False)

        # Custom cleanup behavior
        db = DataFlow("postgresql://...", test_mode=True,
                      test_mode_aggressive_cleanup=False)
    """
```

**Implementation Details**:
```python
# In DataFlow.__init__() after config initialization:

# Test mode detection (ADR-017)
if test_mode is None:
    # Auto-detect pytest environment
    self._test_mode = self._detect_test_environment()
else:
    # Explicit test mode setting
    self._test_mode = test_mode

self._test_mode_aggressive_cleanup = test_mode_aggressive_cleanup

# Log test mode activation
if self._test_mode:
    if test_mode is None:
        logger.info(
            "DataFlow: Test mode enabled (auto-detected pytest environment)"
        )
    else:
        logger.info("DataFlow: Test mode enabled (explicitly set)")

    if self._test_mode_aggressive_cleanup:
        logger.debug(
            "DataFlow: Aggressive pool cleanup enabled for test mode"
        )
```

**Return Value**: DataFlow instance

**Raises**:
- `ValueError`: If database_url is invalid
- `ConnectionError`: If initial connection fails (when applicable)

---

### 1.2 Test Environment Detection (Private Method)

**Location**: `/packages/kailash-dataflow/src/dataflow/core/engine.py`

**Method Signature**:
```python
def _detect_test_environment(self) -> bool:
    """Detect if running in test environment.

    Detection Strategy:
    1. Check PYTEST_CURRENT_TEST environment variable (pytest sets this)
    2. Check if 'pytest' in sys.modules (pytest is imported)
    3. Check if '_' environment variable contains 'pytest'

    Returns:
        bool: True if test environment detected, False otherwise

    Examples:
        >>> import os
        >>> os.environ["PYTEST_CURRENT_TEST"] = "test_example.py::test_func"
        >>> db = DataFlow("postgresql://...")
        >>> db._test_mode
        True
    """
    import sys

    # Strategy 1: Check PYTEST_CURRENT_TEST (most reliable)
    if os.getenv("PYTEST_CURRENT_TEST") is not None:
        return True

    # Strategy 2: Check if pytest is imported
    if "pytest" in sys.modules:
        return True

    # Strategy 3: Check _ environment variable (pytest runner)
    if "pytest" in os.getenv("_", ""):
        return True

    return False
```

**Integration Point**: Called from `DataFlow.__init__()` when `test_mode=None`

---

### 1.3 Global Test Mode Control (Class Methods)

**Location**: `/packages/kailash-dataflow/src/dataflow/core/engine.py`

**Class Attributes**:
```python
class DataFlow:
    """Main DataFlow interface."""

    # Class-level test mode control (ADR-017)
    _global_test_mode: Optional[bool] = None
    _global_test_mode_lock = threading.RLock()
```

**Method: enable_test_mode()**
```python
@classmethod
def enable_test_mode(cls) -> None:
    """Enable test mode for all DataFlow instances globally.

    This class method forces test mode for all new DataFlow instances,
    regardless of environment detection. Useful for:
    - Test setup fixtures (conftest.py)
    - Manual testing scripts
    - Development environments

    Examples:
        # In conftest.py
        @pytest.fixture(scope="session", autouse=True)
        def enable_dataflow_test_mode():
            DataFlow.enable_test_mode()
            yield
            DataFlow.disable_test_mode()

        # Manual testing
        from dataflow import DataFlow
        DataFlow.enable_test_mode()
        db = DataFlow("postgresql://...")  # test_mode=True

    Note:
        - Affects only NEW DataFlow instances created after this call
        - Existing instances retain their test mode setting
        - Thread-safe (uses RLock)
    """
    with cls._global_test_mode_lock:
        cls._global_test_mode = True
        logger.info("DataFlow: Global test mode enabled")
```

**Method: disable_test_mode()**
```python
@classmethod
def disable_test_mode(cls) -> None:
    """Disable global test mode, reverting to auto-detection.

    Examples:
        # Cleanup in fixture
        DataFlow.disable_test_mode()

        # Manual testing cleanup
        DataFlow.disable_test_mode()
    """
    with cls._global_test_mode_lock:
        cls._global_test_mode = None
        logger.info("DataFlow: Global test mode disabled (auto-detection restored)")
```

**Method: is_test_mode_enabled()**
```python
@classmethod
def is_test_mode_enabled(cls) -> Optional[bool]:
    """Get current global test mode setting.

    Returns:
        Optional[bool]:
            - True: Test mode globally enabled
            - False: Test mode globally disabled
            - None: Auto-detection (default)

    Examples:
        >>> DataFlow.enable_test_mode()
        >>> DataFlow.is_test_mode_enabled()
        True
        >>> DataFlow.disable_test_mode()
        >>> DataFlow.is_test_mode_enabled()
        None
    """
    with cls._global_test_mode_lock:
        return cls._global_test_mode
```

**Integration with Constructor**:
```python
# In DataFlow.__init__(), modify test mode detection:

if test_mode is None:
    # Check global test mode first
    with self._global_test_mode_lock:
        if self._global_test_mode is not None:
            self._test_mode = self._global_test_mode
        else:
            # Fall back to auto-detection
            self._test_mode = self._detect_test_environment()
else:
    # Explicit test mode setting overrides global
    self._test_mode = test_mode
```

---

### 1.4 Enhanced Pool Cleanup Methods

**Location**: `/packages/kailash-dataflow/src/dataflow/core/engine.py`

**Method: cleanup_stale_pools()**
```python
async def cleanup_stale_pools(self) -> Dict[str, Any]:
    """Proactively detect and cleanup stale connection pools.

    This method scans for pools associated with closed event loops and
    removes them. Safe to call anytime - won't interfere with active pools.

    Returns:
        Dict[str, Any]: Cleanup metrics with keys:
            - 'stale_pools_found': int - Number of stale pools detected
            - 'stale_pools_cleaned': int - Number successfully cleaned
            - 'cleanup_failures': int - Number of cleanup failures
            - 'cleanup_errors': List[str] - Error messages (if any)
            - 'cleanup_duration_ms': float - Time taken for cleanup

    Examples:
        # Basic usage in pytest fixture
        @pytest.fixture(scope="function")
        async def db():
            db = DataFlow("postgresql://...")
            yield db
            metrics = await db.cleanup_stale_pools()
            print(f"Cleaned {metrics['stale_pools_cleaned']} pools")

        # With error handling
        async def cleanup_with_logging(db: DataFlow):
            metrics = await db.cleanup_stale_pools()
            if metrics['cleanup_failures'] > 0:
                logger.warning(
                    f"Pool cleanup had {metrics['cleanup_failures']} failures"
                )
            return metrics

    Raises:
        None - Gracefully handles all errors, logs warnings
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    start_time = time.time()
    stale_pools_found = 0
    stale_pools_cleaned = 0
    cleanup_failures = 0
    cleanup_errors = []

    try:
        # Call AsyncSQLDatabaseNode's cleanup method
        cleaned = await AsyncSQLDatabaseNode._cleanup_closed_loop_pools()
        stale_pools_found = cleaned
        stale_pools_cleaned = cleaned

        if self._test_mode:
            logger.info(
                f"DataFlow: Cleaned {cleaned} stale connection pools "
                f"(test mode)"
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
```

**Method: cleanup_all_pools()**
```python
async def cleanup_all_pools(self, force: bool = False) -> Dict[str, Any]:
    """Cleanup all connection pools managed by DataFlow.

    WARNING: This is a destructive operation that closes ALL connection pools.
    Use with caution - primarily for test teardown and application shutdown.

    Args:
        force: If True, forcefully close pools even if active connections exist.
               If False, waits for active connections to finish (safer).

    Returns:
        Dict[str, Any]: Cleanup metrics with keys:
            - 'total_pools': int - Total pools found
            - 'pools_cleaned': int - Pools successfully cleaned
            - 'cleanup_failures': int - Cleanup failures
            - 'cleanup_errors': List[str] - Error messages
            - 'cleanup_duration_ms': float - Cleanup duration
            - 'forced': bool - Whether force mode was used

    Examples:
        # Graceful cleanup (recommended)
        @pytest.fixture(scope="function")
        async def db():
            db = DataFlow("postgresql://...")
            yield db
            await db.cleanup_all_pools()

        # Force cleanup (emergency shutdown)
        async def emergency_shutdown(db: DataFlow):
            metrics = await db.cleanup_all_pools(force=True)
            print(f"Force-cleaned {metrics['pools_cleaned']} pools")

        # Module-scoped cleanup
        @pytest.fixture(scope="module")
        async def db_module():
            db = DataFlow("postgresql://...")
            yield db
            metrics = await db.cleanup_all_pools()
            assert metrics['cleanup_failures'] == 0, "Pool cleanup failed"

    Raises:
        None - Gracefully handles all errors, logs warnings
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    start_time = time.time()
    total_pools = len(AsyncSQLDatabaseNode._shared_pools)
    pools_cleaned = 0
    cleanup_failures = 0
    cleanup_errors = []

    try:
        # Clear all shared pools
        await AsyncSQLDatabaseNode.clear_shared_pools()
        pools_cleaned = total_pools

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
```

**Method: get_cleanup_metrics()**
```python
def get_cleanup_metrics(self) -> Dict[str, Any]:
    """Get connection pool lifecycle metrics.

    Provides visibility into pool creation, usage, and cleanup patterns.
    Useful for debugging pool issues and optimizing test performance.

    Returns:
        Dict[str, Any]: Pool lifecycle metrics with keys:
            - 'active_pools': int - Current active pools
            - 'total_pools_created': int - Lifetime pool creations
            - 'test_mode_enabled': bool - Test mode status
            - 'aggressive_cleanup_enabled': bool - Aggressive cleanup status
            - 'pool_keys': List[str] - Active pool identifiers
            - 'event_loop_ids': List[int] - Event loop IDs with pools

    Examples:
        # Monitor pool growth
        db = DataFlow("postgresql://...")
        metrics = db.get_cleanup_metrics()
        print(f"Active pools: {metrics['active_pools']}")

        # Detect pool leaks in tests
        @pytest.fixture(scope="function")
        async def db():
            db = DataFlow("postgresql://...")
            initial_metrics = db.get_cleanup_metrics()
            yield db
            final_metrics = db.get_cleanup_metrics()
            assert final_metrics['active_pools'] <= initial_metrics['active_pools'], \
                "Pool leak detected!"

        # Debug pool issues
        def debug_pool_state(db: DataFlow):
            metrics = db.get_cleanup_metrics()
            print(f"Test mode: {metrics['test_mode_enabled']}")
            print(f"Active pools: {metrics['active_pools']}")
            print(f"Pool keys: {metrics['pool_keys']}")
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    shared_pools = AsyncSQLDatabaseNode._shared_pools

    # Extract unique event loop IDs
    event_loop_ids = set()
    for pool_key in shared_pools.keys():
        # Pool key format: "loop_id|database_url|..."
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

### 1.5 AsyncSQLDatabaseNode Enhancements

**Location**: `/src/kailash/nodes/data/async_sql.py`

**Method: _cleanup_closed_loop_pools() Enhancement**

**Current Implementation** (lines 4034-4072):
```python
@classmethod
def _cleanup_closed_loop_pools(cls) -> int:
    """Remove pools from closed event loops."""
    # ... existing implementation
```

**Enhanced Implementation**:
```python
@classmethod
async def _cleanup_closed_loop_pools(cls) -> int:
    """Proactively remove pools from closed event loops.

    Enhanced with:
    - Async-first design (proper await for pool cleanup)
    - Detailed logging
    - Graceful error handling
    - Metrics tracking

    Returns:
        int: Number of pools cleaned

    Examples:
        # Called internally by DataFlow.cleanup_stale_pools()
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
        cleaned = await AsyncSQLDatabaseNode._cleanup_closed_loop_pools()
        print(f"Cleaned {cleaned} stale pools")
    """
    cleaned_count = 0
    pools_to_remove = []

    try:
        current_loop = asyncio.get_event_loop()
        current_loop_id = id(current_loop)
    except RuntimeError:
        # No event loop in current thread - can't cleanup
        logger.warning(
            "AsyncSQLDatabaseNode: No event loop available for cleanup"
        )
        return 0

    # Phase 1: Identify stale pools
    for pool_key, (adapter, creation_time) in list(cls._shared_pools.items()):
        # Extract loop ID from pool key
        loop_id_str = pool_key.split("|")[0]

        try:
            pool_loop_id = int(loop_id_str)
        except (ValueError, IndexError):
            logger.warning(
                f"AsyncSQLDatabaseNode: Invalid pool key format: {pool_key}"
            )
            continue

        # Check if pool's event loop is closed
        if pool_loop_id != current_loop_id:
            try:
                # Check if the loop is closed (best effort)
                # Note: Can't directly check if loop is closed, so we assume
                # pools from different loops are potentially stale
                pools_to_remove.append(pool_key)
                logger.debug(
                    f"AsyncSQLDatabaseNode: Marked stale pool {pool_key} "
                    f"(loop {pool_loop_id} != current {current_loop_id})"
                )
            except Exception as e:
                logger.warning(
                    f"AsyncSQLDatabaseNode: Error checking pool {pool_key}: {e}"
                )

    # Phase 2: Cleanup stale pools
    for pool_key in pools_to_remove:
        try:
            adapter, creation_time = cls._shared_pools.pop(pool_key)

            # Attempt to close adapter gracefully
            try:
                if hasattr(adapter, "close"):
                    await adapter.close()
            except Exception as close_error:
                logger.debug(
                    f"AsyncSQLDatabaseNode: Could not close adapter for "
                    f"{pool_key}: {close_error}"
                )

            cleaned_count += 1
            logger.info(
                f"AsyncSQLDatabaseNode: Cleaned stale pool {pool_key}"
            )
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

**Method: clear_shared_pools() Enhancement**

**Current Implementation** (lines 4072-4073):
```python
@classmethod
async def clear_shared_pools(cls) -> None:
    """Clear all shared connection pools. Use with caution!"""
```

**Enhanced Implementation**:
```python
@classmethod
async def clear_shared_pools(cls, graceful: bool = True) -> Dict[str, Any]:
    """Clear all shared connection pools with enhanced error handling.

    Args:
        graceful: If True, attempts to close adapters gracefully.
                  If False, immediately removes pools.

    Returns:
        Dict[str, Any]: Cleanup metrics:
            - 'total_pools': int - Total pools found
            - 'pools_cleared': int - Pools successfully cleared
            - 'clear_failures': int - Number of failures
            - 'clear_errors': List[str] - Error messages

    Examples:
        # Graceful cleanup (recommended)
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
        metrics = await AsyncSQLDatabaseNode.clear_shared_pools()
        print(f"Cleared {metrics['pools_cleared']} pools")

        # Force clear (emergency)
        metrics = await AsyncSQLDatabaseNode.clear_shared_pools(graceful=False)
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

    # Create copy of pool keys to avoid modification during iteration
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

---

### 1.6 Test Mode Propagation to Generated Nodes

**Location**: `/packages/kailash-dataflow/src/dataflow/core/nodes.py`

**Node Generation Enhancement**:
```python
class NodeGenerator:
    """Generate workflow nodes from models."""

    def generate_nodes(
        self,
        model_name: str,
        model_class: Type,
        dataflow_instance: "DataFlow"
    ) -> Dict[str, Type]:
        """Generate nodes with test mode awareness.

        Enhancement: Pass test mode to generated nodes for proper behavior.
        """
        # ... existing node generation code ...

        # Inject test mode into node parameters (if node supports it)
        for node_name, node_class in nodes.items():
            # Check if node has test_mode parameter
            if hasattr(node_class, "test_mode"):
                # Bind test mode from DataFlow instance
                node_class.test_mode = dataflow_instance._test_mode

        return nodes
```

---

## 2. Usage Examples

### 2.1 Auto-Detection Pattern (Recommended)

```python
# Test file: tests/test_user_operations.py
import pytest
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.asyncio
async def test_user_crud():
    """Test mode auto-detected from pytest environment."""
    # Test mode automatically enabled (PYTEST_CURRENT_TEST set by pytest)
    db = DataFlow("postgresql://localhost/test_db")

    # Test mode logged automatically:
    # INFO: DataFlow: Test mode enabled (auto-detected pytest environment)

    @db.model
    class User:
        id: str
        name: str

    # Create user
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-1",
        "name": "Alice"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build())

    assert results["create"]["name"] == "Alice"

    # No explicit cleanup needed in simple tests
    # Pool cleanup happens automatically on test exit
```

### 2.2 Explicit Fixture Pattern

```python
# File: tests/conftest.py
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="function")
async def db():
    """Function-scoped database with cleanup."""
    # Explicitly enable test mode
    db = DataFlow(
        "postgresql://localhost/test_db",
        test_mode=True,
        test_mode_aggressive_cleanup=True
    )

    yield db

    # Explicit cleanup
    metrics = await db.cleanup_all_pools()

    # Verify cleanup succeeded
    assert metrics["cleanup_failures"] == 0, \
        f"Pool cleanup failed: {metrics['cleanup_errors']}"


@pytest.fixture(scope="module")
async def db_module():
    """Module-scoped database for performance."""
    db = DataFlow("postgresql://localhost/test_db", test_mode=True)

    yield db

    # Cleanup at module end
    await db.cleanup_all_pools()


# Test file: tests/test_with_fixture.py
@pytest.mark.asyncio
async def test_with_fixture(db):
    """Use fixture-provided database."""
    @db.model
    class Product:
        id: str
        name: str
        price: float

    # Test operations...
    # Cleanup automatic via fixture
```

### 2.3 Global Test Mode Pattern

```python
# File: tests/conftest.py
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="session", autouse=True)
def enable_dataflow_test_mode():
    """Enable test mode globally for all tests."""
    DataFlow.enable_test_mode()

    yield

    # Restore auto-detection
    DataFlow.disable_test_mode()


# File: tests/test_with_global_mode.py
@pytest.mark.asyncio
async def test_global_mode():
    """Test with globally enabled test mode."""
    # Test mode automatically enabled by global setting
    db = DataFlow("postgresql://localhost/test_db")

    # Verify test mode is enabled
    assert db._test_mode == True

    # Test operations...
```

### 2.4 Manual Testing Pattern

```python
# File: scripts/manual_test.py
"""Manual testing script with explicit test mode."""
import asyncio
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


async def main():
    # Enable test mode for manual testing
    DataFlow.enable_test_mode()

    db = DataFlow("postgresql://localhost/dev_db")

    @db.model
    class TestData:
        id: str
        value: str

    # Create test data
    workflow = WorkflowBuilder()
    workflow.add_node("TestDataCreateNode", "create", {
        "id": "test-1",
        "value": "Manual test"
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build())

    print(f"Created: {results['create']}")

    # Check pool metrics
    metrics = db.get_cleanup_metrics()
    print(f"Active pools: {metrics['active_pools']}")

    # Cleanup
    cleanup_metrics = await db.cleanup_all_pools()
    print(f"Cleaned {cleanup_metrics['pools_cleaned']} pools")

    # Disable test mode
    DataFlow.disable_test_mode()


if __name__ == "__main__":
    asyncio.run(main())
```

### 2.5 Cleanup Monitoring Pattern

```python
# File: tests/test_with_monitoring.py
import pytest
from dataflow import DataFlow


@pytest.fixture(scope="function")
async def db():
    """Database with cleanup monitoring."""
    db = DataFlow("postgresql://localhost/test_db", test_mode=True)

    # Record initial metrics
    initial_metrics = db.get_cleanup_metrics()
    print(f"Initial pools: {initial_metrics['active_pools']}")

    yield db

    # Check for stale pools
    stale_metrics = await db.cleanup_stale_pools()
    if stale_metrics['stale_pools_found'] > 0:
        print(f"⚠️ Found {stale_metrics['stale_pools_found']} stale pools")

    # Full cleanup
    cleanup_metrics = await db.cleanup_all_pools()

    # Verify no pool leaks
    final_metrics = db.get_cleanup_metrics()
    assert final_metrics['active_pools'] == 0, \
        f"Pool leak: {final_metrics['active_pools']} pools remaining"


@pytest.mark.asyncio
async def test_with_monitoring(db):
    """Test with pool monitoring."""
    @db.model
    class User:
        id: str
        name: str

    # Test operations...

    # Check metrics during test
    metrics = db.get_cleanup_metrics()
    print(f"Mid-test pools: {metrics['active_pools']}")
```

### 2.6 Error Handling Pattern

```python
# File: tests/test_cleanup_errors.py
import pytest
from dataflow import DataFlow


@pytest.mark.asyncio
async def test_cleanup_error_handling():
    """Test graceful handling of cleanup errors."""
    db = DataFlow("postgresql://localhost/test_db", test_mode=True)

    @db.model
    class Data:
        id: str

    try:
        # Test operations that might fail...
        pass
    finally:
        # Cleanup with error handling
        cleanup_metrics = await db.cleanup_all_pools()

        if cleanup_metrics['cleanup_failures'] > 0:
            # Log errors but don't fail test
            print(f"⚠️ Cleanup failures: {cleanup_metrics['cleanup_failures']}")
            for error in cleanup_metrics['cleanup_errors']:
                print(f"  - {error}")
        else:
            print(f"✓ Successfully cleaned {cleanup_metrics['pools_cleaned']} pools")
```

---

## 3. Integration Points

### 3.1 DataFlow Constructor Integration

**File**: `/packages/kailash-dataflow/src/dataflow/core/engine.py`

**Integration Steps**:
1. Add `test_mode` and `test_mode_aggressive_cleanup` parameters to `__init__`
2. Add `_test_mode` and `_test_mode_aggressive_cleanup` instance attributes
3. Add `_global_test_mode` and `_global_test_mode_lock` class attributes
4. Implement `_detect_test_environment()` private method
5. Add test mode detection logic after config initialization
6. Add logging for test mode activation

**Code Location**: Lines 34-200

### 3.2 AsyncSQLDatabaseNode Integration

**File**: `/src/kailash/nodes/data/async_sql.py`

**Integration Steps**:
1. Enhance `_cleanup_closed_loop_pools()` with async design (lines 4034-4072)
2. Enhance `clear_shared_pools()` with metrics (lines 4072-4073)
3. Add graceful shutdown handling
4. Add detailed logging for cleanup operations

**Code Location**: Lines 4027-4090

### 3.3 Node Generation Integration

**File**: `/packages/kailash-dataflow/src/dataflow/core/nodes.py`

**Integration Steps**:
1. Modify `NodeGenerator.generate_nodes()` to pass test mode
2. Add test mode binding to generated node classes
3. Ensure test mode propagates to all CRUD nodes

### 3.4 Configuration Integration

**File**: `/packages/kailash-dataflow/src/dataflow/core/config.py`

**Integration Steps** (Optional):
1. Add `test_mode_config` section to `DataFlowConfig`
2. Add test mode configuration options
3. Document test mode settings

---

## 4. Backward Compatibility

### 4.1 Zero Breaking Changes

**Guarantees**:
- All existing code works without modifications
- `test_mode=None` (default) maintains auto-detection behavior
- New parameters have sensible defaults
- No API removals or signature changes
- Production code unaffected (test mode changes only)

**Validation**:
```python
# Existing code continues to work
db = DataFlow("postgresql://...")  # ✓ Works exactly as before

# New features are opt-in
db = DataFlow("postgresql://...", test_mode=True)  # ✓ New feature

# Explicit disable works
db = DataFlow("postgresql://...", test_mode=False)  # ✓ New feature
```

### 4.2 Deprecation Policy

**No Deprecations**: This is a pure additive change with no deprecations.

---

## 5. Error Handling

### 5.1 Graceful Degradation

All cleanup methods use graceful degradation:
- Errors are logged, not raised
- Partial cleanup succeeds even if some pools fail
- Metrics capture failure details for debugging

**Example**:
```python
# Even if one pool fails, others are cleaned
metrics = await db.cleanup_all_pools()
# metrics['pools_cleaned'] = 9
# metrics['cleanup_failures'] = 1
# metrics['cleanup_errors'] = ["Failed to close pool X: connection refused"]
```

### 5.2 Error Patterns

**Pattern 1: No Event Loop**
```python
# If no event loop available, cleanup returns early
metrics = await db.cleanup_stale_pools()
# Returns: {'stale_pools_found': 0, 'stale_pools_cleaned': 0, ...}
```

**Pattern 2: Closed Adapter**
```python
# If adapter is already closed, logs warning and continues
# No exception raised, cleanup continues for remaining pools
```

**Pattern 3: Invalid Pool Key**
```python
# If pool key format is invalid, logs warning and skips
# Remaining pools are still processed
```

---

## 6. Test Strategy

### 6.1 Unit Tests

**Location**: `/packages/kailash-dataflow/tests/test_test_mode.py`

**Test Cases**:
```python
# Test 1: Auto-detection works
def test_auto_detect_pytest_environment():
    os.environ["PYTEST_CURRENT_TEST"] = "test.py::test_func"
    db = DataFlow("sqlite:///:memory:")
    assert db._test_mode == True
    del os.environ["PYTEST_CURRENT_TEST"]

# Test 2: Explicit test mode works
def test_explicit_test_mode():
    db = DataFlow("sqlite:///:memory:", test_mode=True)
    assert db._test_mode == True

# Test 3: Global test mode works
def test_global_test_mode():
    DataFlow.enable_test_mode()
    db = DataFlow("sqlite:///:memory:")
    assert db._test_mode == True
    DataFlow.disable_test_mode()

# Test 4: Test mode logging
def test_test_mode_logging(caplog):
    db = DataFlow("sqlite:///:memory:", test_mode=True)
    assert "Test mode enabled" in caplog.text

# Test 5: Cleanup metrics
@pytest.mark.asyncio
async def test_cleanup_metrics():
    db = DataFlow("sqlite:///:memory:", test_mode=True)
    metrics = await db.cleanup_stale_pools()
    assert "stale_pools_found" in metrics
    assert "cleanup_duration_ms" in metrics
```

**Coverage Target**: 95%+ for new code

### 6.2 Integration Tests

**Location**: `/packages/kailash-dataflow/tests/integration/test_test_mode_integration.py`

**Test Cases**:
```python
# Test 1: Fixture pattern works
@pytest.mark.asyncio
async def test_fixture_pattern(db_fixture):
    # Uses fixture with cleanup
    pass

# Test 2: Sequential isolation works
@pytest.mark.asyncio
async def test_sequential_1(db_fixture):
    # Create data
    pass

@pytest.mark.asyncio
async def test_sequential_2(db_fixture):
    # Should not see data from test_sequential_1
    pass

# Test 3: Module-scoped pool reuse
@pytest.mark.asyncio
async def test_pool_reuse(db_module):
    # Verify same pool used within module
    pass
```

### 6.3 End-to-End Tests

**Location**: `/packages/kailash-dataflow/tests/e2e/test_documentation_examples.py`

**Test Cases**:
```python
# Run all documentation examples
@pytest.mark.e2e
def test_all_documentation_examples():
    examples = glob.glob("docs/testing/examples/*.py")
    for example in examples:
        result = subprocess.run(["pytest", example])
        assert result.returncode == 0
```

---

## 7. Performance Characteristics

### 7.1 Overhead

**Test Mode Detection**: <1ms
- Environment variable lookup: ~0.1ms
- sys.modules check: ~0.1ms

**Cleanup Operations**:
- `cleanup_stale_pools()`: <50ms for 10 pools
- `cleanup_all_pools()`: <100ms for 10 pools
- `get_cleanup_metrics()`: <1ms

### 7.2 Optimization

**Connection Pooling**: Maintained
- Test mode doesn't disable connection pooling
- Pools are shared within event loop
- Only stale pools are cleaned

**Lazy Cleanup**: Opt-in
- Aggressive cleanup is opt-in via `test_mode_aggressive_cleanup`
- Default behavior: cleanup on explicit call only

---

## 8. Documentation Requirements

### 8.1 API Documentation

**Location**: `/packages/kailash-dataflow/docs/api/test_mode.md`

**Sections**:
- Test mode overview
- API reference (all methods)
- Usage patterns
- Best practices

### 8.2 Testing Guide

**Location**: `/packages/kailash-dataflow/docs/testing/`

**Files**:
- `README.md` - Overview
- `fixture-patterns.md` - Pytest fixtures (CORE)
- `setup-guide.md` - Initial setup
- `troubleshooting.md` - Common errors

### 8.3 Code Examples

**Location**: `/packages/kailash-dataflow/docs/testing/examples/`

**Files**:
- `basic_test.py` - Simple CRUD test
- `conftest.py` - Fixture definitions
- `transaction_test.py` - Rollback pattern
- `monitoring_test.py` - Cleanup monitoring

---

## 9. Release Plan

### 9.1 Version Target

**Version**: v0.8.0

**Release Type**: Minor (new features, no breaking changes)

### 9.2 Release Checklist

- [ ] All unit tests passing (95%+ coverage)
- [ ] All integration tests passing
- [ ] All documentation examples validated
- [ ] Performance benchmarks green (<5% regression)
- [ ] Documentation complete and reviewed
- [ ] CHANGELOG.md updated
- [ ] Release notes drafted

---

## 10. Approval

**Author**: Claude (API Design Specialist)
**Date**: 2025-10-30
**Status**: Proposed

**Next Steps**:
1. Technical review by DataFlow maintainers
2. API review for consistency
3. Implementation approval
4. Begin Phase 2 implementation
