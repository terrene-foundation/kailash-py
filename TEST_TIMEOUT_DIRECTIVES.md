# Test Timeout Directives for Claude Code

## Executive Summary

All tests in the Kailash SDK MUST complete within these strict time limits:
- **Unit tests**: 1 second maximum
- **Integration tests**: 5 seconds maximum
- **E2E tests**: 10 seconds maximum

## Required Test Commands

When running tests, ALWAYS use these commands with timeout enforcement:

```bash
# Unit tests (1 second max)
pytest tests/unit/ --forked --timeout=1 --timeout-method=thread

# Integration tests (5 seconds max)
pytest tests/integration/ --timeout=5 --timeout-method=thread

# E2E tests (10 seconds max)
pytest tests/e2e/ --timeout=10 --timeout-method=thread
```

## Systematic Approach to Fix Violations

### 1. Identify Timeout Violations

```bash
# Use the provided script
python scripts/fix_test_timeouts.py

# Or manually check each tier
pytest tests/integration/ --timeout=5 -v | grep -B5 "Timeout"
```

### 2. Common Causes and Fixes

#### Long Sleep Times
```python
# ❌ BAD
await asyncio.sleep(10)
await asyncio.sleep(5)
await asyncio.sleep(2)

# ✅ GOOD
await asyncio.sleep(0.1)   # 100ms is usually enough
await asyncio.sleep(0.01)  # 10ms for quick checks
```

#### Actor/Pool Cleanup Issues
```python
# ✅ GOOD - Proper cleanup pattern
finally:
    try:
        if hasattr(pool, '_supervisor'):
            await pool._supervisor.stop_all_actors()
        pool._closing = True
        await asyncio.wait_for(pool._cleanup(), timeout=1.0)
    except Exception:
        pass  # Ignore cleanup errors
```

#### Database Configuration
```python
# ❌ BAD - Slow intervals for production
config = {
    "health_check_interval": 30.0,    # 30 seconds
    "max_lifetime": 3600.0,           # 1 hour
    "max_idle_time": 600.0            # 10 minutes
}

# ✅ GOOD - Fast intervals for tests
config = {
    "health_check_interval": 0.1,     # 100ms
    "max_lifetime": 60.0,             # 1 minute
    "max_idle_time": 10.0             # 10 seconds
}
```

#### External Service Calls
```python
# ❌ BAD - Real HTTP calls
response = await session.get("http://api.example.com/data")

# ✅ GOOD - Mock the service
with aioresponses() as m:
    m.get('http://api.example.com/data', payload={'result': 'ok'})
    response = await fetch_data()
```

### 3. Verification

After fixing, verify the test completes within timeout:

```bash
# Run specific test with timeout
pytest path/to/test_file.py::test_name --timeout=5 -v

# Run all tests in file
pytest path/to/test_file.py --timeout=5
```

## Why These Limits?

1. **Fast Feedback**: Developers need quick test results to maintain flow
2. **CI/CD Performance**: Slow tests block deployments and waste resources
3. **Good Design**: Tests that need more time are usually testing too much
4. **Resource Efficiency**: Hanging tests consume compute resources unnecessarily

## Enforcement

1. **pytest.ini**: Global timeout of 10 seconds (covers E2E tests)
2. **conftest_timeouts.py**: Automatically applies tier-specific timeouts
3. **CI/CD**: Tests that exceed timeouts will fail the build

## Quick Reference Card

| Test Type | Max Time | Common Issues | Quick Fix |
|-----------|----------|---------------|-----------|
| Unit | 1s | Unmocked I/O | Mock external calls |
| Integration | 5s | Long sleeps | Use 0.1s sleeps |
| E2E | 10s | Real services | Mock slow services |

## Remember

If a test can't complete within these limits, it needs to be:
1. Split into smaller tests
2. Refactored to mock slow operations
3. Moved to a different test tier

There are NO exceptions to these timeout limits.
