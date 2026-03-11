# ADR-017: Test Mode API - Quick Reference Card

## API at a Glance

### Constructor Enhancement

```python
from dataflow import DataFlow

# Auto-detect (recommended)
db = DataFlow("postgresql://...")  # test_mode=None

# Explicit enable
db = DataFlow("postgresql://...", test_mode=True)

# Explicit disable
db = DataFlow("postgresql://...", test_mode=False)

# Custom cleanup
db = DataFlow("postgresql://...",
              test_mode=True,
              test_mode_aggressive_cleanup=True)
```

### Global Control (Class Methods)

```python
# Enable globally
DataFlow.enable_test_mode()

# Disable globally
DataFlow.disable_test_mode()

# Check status
status = DataFlow.is_test_mode_enabled()  # True/False/None
```

### Cleanup Methods (Instance, Async)

```python
# Cleanup stale pools
metrics = await db.cleanup_stale_pools()
# Returns: {
#   'stale_pools_found': 2,
#   'stale_pools_cleaned': 2,
#   'cleanup_failures': 0,
#   'cleanup_errors': [],
#   'cleanup_duration_ms': 45.2
# }

# Cleanup all pools
metrics = await db.cleanup_all_pools(force=False)
# Returns: {
#   'total_pools': 5,
#   'pools_cleaned': 5,
#   'cleanup_failures': 0,
#   'cleanup_errors': [],
#   'cleanup_duration_ms': 98.1,
#   'forced': False
# }

# Get metrics (sync)
metrics = db.get_cleanup_metrics()
# Returns: {
#   'active_pools': 3,
#   'total_pools_created': 10,
#   'test_mode_enabled': True,
#   'aggressive_cleanup_enabled': True,
#   'pool_keys': [...],
#   'event_loop_ids': [...]
# }
```

---

## Usage Patterns

### Pattern 1: Auto-Detection (Simplest)

```python
# tests/test_user.py
@pytest.mark.asyncio
async def test_user_create():
    # Test mode auto-detected
    db = DataFlow("postgresql://...")

    @db.model
    class User:
        id: str
        name: str

    # Test operations...
    # No explicit cleanup needed for simple tests
```

**Pros**: Zero configuration, works automatically
**Cons**: No explicit cleanup control
**Best For**: Simple tests, quick prototypes

---

### Pattern 2: Explicit Fixture (Recommended)

```python
# tests/conftest.py
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...", test_mode=True)
    yield db
    await db.cleanup_all_pools()

# tests/test_user.py
@pytest.mark.asyncio
async def test_user_create(db):
    @db.model
    class User:
        id: str
        name: str

    # Test operations...
    # Cleanup automatic via fixture
```

**Pros**: Explicit cleanup, reusable, clean slate per test
**Cons**: Requires fixture definition
**Best For**: Production test suites, team projects

---

### Pattern 3: Global Test Mode (Session-Wide)

```python
# tests/conftest.py
@pytest.fixture(scope="session", autouse=True)
def enable_test_mode():
    DataFlow.enable_test_mode()
    yield
    DataFlow.disable_test_mode()

# tests/test_user.py
@pytest.mark.asyncio
async def test_user_create():
    # Test mode enabled globally
    db = DataFlow("postgresql://...")

    # Test operations...
```

**Pros**: Single configuration point, all tests benefit
**Cons**: Less granular control
**Best For**: Large test suites, organization-wide standards

---

### Pattern 4: Monitoring (Debug Mode)

```python
# tests/test_with_monitoring.py
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...", test_mode=True)

    initial_metrics = db.get_cleanup_metrics()
    print(f"Initial pools: {initial_metrics['active_pools']}")

    yield db

    stale_metrics = await db.cleanup_stale_pools()
    print(f"Stale pools: {stale_metrics['stale_pools_found']}")

    final_metrics = await db.cleanup_all_pools()
    print(f"Cleaned: {final_metrics['pools_cleaned']}")

@pytest.mark.asyncio
async def test_user_operations(db):
    # Monitor pool growth during test
    mid_metrics = db.get_cleanup_metrics()
    print(f"Mid-test pools: {mid_metrics['active_pools']}")

    # Test operations...
```

**Pros**: Full visibility, helps debug pool issues
**Cons**: More verbose
**Best For**: Debugging pool leaks, performance testing

---

## Method Reference

### DataFlow Class

| Method | Type | Returns | Purpose |
|--------|------|---------|---------|
| `__init__(test_mode=None)` | Instance | DataFlow | Create instance with test mode |
| `enable_test_mode()` | Class | None | Enable test mode globally |
| `disable_test_mode()` | Class | None | Disable global test mode |
| `is_test_mode_enabled()` | Class | Optional[bool] | Check global test mode |
| `cleanup_stale_pools()` | Instance (async) | Dict[str, Any] | Remove stale pools |
| `cleanup_all_pools(force=False)` | Instance (async) | Dict[str, Any] | Remove all pools |
| `get_cleanup_metrics()` | Instance (sync) | Dict[str, Any] | Get pool metrics |

### AsyncSQLDatabaseNode Class

| Method | Type | Returns | Purpose |
|--------|------|---------|---------|
| `_cleanup_closed_loop_pools()` | Class (async) | int | Remove closed loop pools |
| `clear_shared_pools(graceful=True)` | Class (async) | Dict[str, Any] | Clear all shared pools |

---

## Return Value Reference

### cleanup_stale_pools() Returns

```python
{
    'stale_pools_found': int,      # Number detected
    'stale_pools_cleaned': int,    # Successfully removed
    'cleanup_failures': int,       # Failed cleanups
    'cleanup_errors': List[str],   # Error messages
    'cleanup_duration_ms': float   # Time taken
}
```

### cleanup_all_pools() Returns

```python
{
    'total_pools': int,            # Total pools found
    'pools_cleaned': int,          # Successfully removed
    'cleanup_failures': int,       # Failed cleanups
    'cleanup_errors': List[str],   # Error messages
    'cleanup_duration_ms': float,  # Time taken
    'forced': bool                 # Was force=True used
}
```

### get_cleanup_metrics() Returns

```python
{
    'active_pools': int,                    # Current active pools
    'total_pools_created': int,             # Lifetime pool count
    'test_mode_enabled': bool,              # Test mode status
    'aggressive_cleanup_enabled': bool,     # Aggressive cleanup status
    'pool_keys': List[str],                 # Pool identifiers
    'event_loop_ids': List[int]             # Event loop IDs
}
```

---

## Common Use Cases

### Use Case 1: Simple Test (No Cleanup Needed)

```python
@pytest.mark.asyncio
async def test_read_only():
    db = DataFlow("postgresql://...")

    @db.model
    class User:
        id: str

    # Read-only operations
    # No cleanup needed
```

### Use Case 2: Test with Explicit Cleanup

```python
@pytest.mark.asyncio
async def test_with_cleanup():
    db = DataFlow("postgresql://...", test_mode=True)

    try:
        # Test operations...
        pass
    finally:
        await db.cleanup_all_pools()
```

### Use Case 3: Fixture with Error Handling

```python
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...", test_mode=True)
    yield db

    metrics = await db.cleanup_all_pools()
    if metrics['cleanup_failures'] > 0:
        print(f"⚠️ Cleanup failures: {metrics['cleanup_failures']}")
```

### Use Case 4: Performance Testing

```python
@pytest.mark.asyncio
async def test_performance():
    db = DataFlow("postgresql://...", test_mode=True)

    initial = db.get_cleanup_metrics()

    # Run 1000 operations
    for i in range(1000):
        # Create records...
        pass

    final = db.get_cleanup_metrics()

    # Verify no pool leak
    assert final['active_pools'] <= initial['active_pools'] + 2
```

---

## Error Handling

### All Cleanup Methods Use Graceful Degradation

```python
# Never raises exceptions
metrics = await db.cleanup_all_pools()

# Check for failures
if metrics['cleanup_failures'] > 0:
    for error in metrics['cleanup_errors']:
        print(f"Error: {error}")
```

### Partial Cleanup Succeeds

```python
# If 1 pool fails, others still cleanup
metrics = await db.cleanup_all_pools()
# metrics['pools_cleaned'] = 9
# metrics['cleanup_failures'] = 1
```

---

## Performance Characteristics

| Operation | Overhead | Frequency |
|-----------|----------|-----------|
| Test mode detection | <1ms | Once per instance |
| `cleanup_stale_pools()` | <50ms | Per fixture |
| `cleanup_all_pools()` | <100ms | Per fixture |
| `get_cleanup_metrics()` | <1ms | As needed |

**Total Impact**: <150ms per test (acceptable)

---

## Testing Commands

```bash
# Run unit tests
pytest packages/kailash-dataflow/tests/test_test_mode.py -v

# Run integration tests
pytest packages/kailash-dataflow/tests/integration/ -v

# Run all tests
pytest packages/kailash-dataflow/tests/ -v

# With coverage
pytest packages/kailash-dataflow/tests/ --cov=dataflow --cov-report=html

# Validate examples
pytest packages/kailash-dataflow/docs/testing/examples/ -v
```

---

## Troubleshooting

### Issue: "pool is closed" Error

**Solution**: Add cleanup fixture

```python
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...", test_mode=True)
    yield db
    await db.cleanup_all_pools()
```

### Issue: Pool Leaks Between Tests

**Solution**: Use function-scoped fixtures

```python
# ✅ CORRECT - function scope
@pytest.fixture(scope="function")
async def db():
    ...

# ❌ WRONG - module scope without cleanup
@pytest.fixture(scope="module")
async def db():
    ...
```

### Issue: Slow Test Execution

**Solution**: Use module-scoped fixture for performance

```python
@pytest.fixture(scope="module")
async def db_module():
    db = DataFlow("postgresql://...", test_mode=True)
    yield db
    await db.cleanup_all_pools()
```

### Issue: Cleanup Failures

**Solution**: Check metrics and log errors

```python
metrics = await db.cleanup_all_pools()
if metrics['cleanup_failures'] > 0:
    print(f"Failures: {metrics['cleanup_failures']}")
    for error in metrics['cleanup_errors']:
        print(f"  - {error}")
```

---

## Migration Guide

### From: No Cleanup (Current)

```python
@pytest.mark.asyncio
async def test_user():
    db = DataFlow("postgresql://...")
    # No cleanup
```

### To: With Cleanup (Recommended)

```python
# Option 1: Fixture (recommended)
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...", test_mode=True)
    yield db
    await db.cleanup_all_pools()

@pytest.mark.asyncio
async def test_user(db):
    # Use fixture
    pass

# Option 2: Explicit (inline)
@pytest.mark.asyncio
async def test_user():
    db = DataFlow("postgresql://...", test_mode=True)
    try:
        # Test operations
        pass
    finally:
        await db.cleanup_all_pools()
```

---

## Version Information

**ADR**: 017
**Target Version**: v0.8.0
**Status**: Proposed
**Created**: 2025-10-30

---

## Related Documents

- **Full Requirements**: `ADR-017-dataflow-testing-improvements.md`
- **API Specification**: `ADR-017-test-mode-api-spec.md`
- **Design Summary**: `ADR-017-api-design-summary.md`
- **Implementation Guide**: `ADR-017-implementation-guide.md`
- **Documentation Index**: `ADR-017-README.md`

---

## Quick Links

- [Main Requirements](./ADR-017-dataflow-testing-improvements.md)
- [API Specification](./ADR-017-test-mode-api-spec.md)
- [Design Summary](./ADR-017-api-design-summary.md)
- [Implementation Guide](./ADR-017-implementation-guide.md)
- [Documentation Index](./ADR-017-README.md)
