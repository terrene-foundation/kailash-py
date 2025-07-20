# Sleep Pattern Fix Implementation Guide

Based on the successful synchronization approach used in edge coordination tests, this guide provides concrete implementation patterns for replacing fixed sleep times across the test suite.

## Executive Summary

The edge coordination tests demonstrate best practices:
- Replaced fixed sleeps with polling loops checking specific conditions
- Used `datetime.now()` for timeout tracking
- Small polling intervals (0.05s) for responsive detection
- Clear condition checks with early exit on success

## Implementation Patterns by Category

### 1. Service Startup Waits (CRITICAL - 3+ seconds)

**Current Pattern:**
```python
# tests/e2e/test_durable_gateway_real_world.py:484
server_thread.start()
time.sleep(3)
# Verify gateway is running
response = await client.get(f"http://localhost:{port}/health")
```

**Fixed Pattern:**
```python
from tests.utils.wait_conditions import wait_for_http_health_sync

server_thread.start()

# Wait for gateway to be healthy
wait_for_http_health_sync(
    url=f"http://localhost:{port}/health",
    timeout=10.0,
    interval=0.1
)
```

### 2. Docker Container Waits (CRITICAL - 15 seconds!)

**Current Pattern:**
```python
# tests/integration/middleware/test_api_gateway_docker.py:313
with DockerCompose(...) as compose:
    # Wait for services to be healthy
    time.sleep(15)
```

**Fixed Pattern:**
```python
from tests.utils.wait_conditions import wait_for_container_health, wait_for_port

with DockerCompose(...) as compose:
    # Wait for specific services to be ready
    wait_for_condition_sync(
        lambda: compose.get_service("redis").is_healthy(),
        timeout=30.0,
        error_message="Redis service failed to start"
    )
    
    # Or wait for ports
    await wait_for_port("localhost", 6379, timeout=30.0)
    await wait_for_port("localhost", 5432, timeout=30.0)
```

### 3. Cache Expiration Tests (CRITICAL - 1.1 seconds)

**Current Pattern:**
```python
# tests/integration/nodes/cache/test_cache.py:340
cache.set("key", "value", ttl=1)
time.sleep(1.1)  # Wait for cache expiration
assert cache.get("key") is None
```

**Fixed Pattern:**
```python
from tests.utils.wait_conditions import CacheTestHelper

cache_helper = CacheTestHelper(cache)

# Use shorter TTL for tests
await cache_helper.set_with_short_ttl("key", "value", ttl=0.1)

# Wait for expiration with condition
await cache_helper.wait_for_expiration("key", timeout=0.5)
```

### 4. Monitoring Cycles (CRITICAL - 2-3 seconds)

**Current Pattern:**
```python
# tests/integration/nodes/monitoring/test_transaction_monitoring_integration.py:193
monitor.start_monitoring()
time.sleep(3.0)  # Wait for monitoring cycle
```

**Fixed Pattern (Edge Coordination Style):**
```python
monitor.start_monitoring()

# Wait for monitoring to detect transactions
start_time = datetime.now()
while (datetime.now() - start_time).total_seconds() < 5.0:
    if monitor.get_detected_count() > 0:
        break
    await asyncio.sleep(0.05)

assert monitor.get_detected_count() > 0
```

### 5. Workflow Completion Waits

**Current Pattern:**
```python
# Various files
runtime.execute(workflow)
await asyncio.sleep(0.5)  # Allow execution to complete
```

**Fixed Pattern:**
```python
from tests.utils.wait_conditions import wait_for_workflow_completion

result, run_id = runtime.execute(workflow)

# Wait for specific completion
await wait_for_workflow_completion(runtime, run_id, timeout=5)
```

## Edge Coordination Pattern (Gold Standard)

The edge coordination tests show the ideal pattern:

```python
# Wait for leader election with timeout
start_time = datetime.now()
while (datetime.now() - start_time).total_seconds() < 1.0:
    leaders = [n for n in nodes.values() if n.state == RaftState.LEADER]
    if len(leaders) == 1:
        break
    await asyncio.sleep(0.05)

# Verify condition met
assert len(leaders) == 1
```

**Key elements:**
1. Clear timeout using `datetime.now()`
2. Specific condition check
3. Early exit on success
4. Small polling interval (0.05s)
5. Assertion after loop

## Implementation Strategy

### Phase 1: Critical Fixes (31 instances)
Fix all sleeps >= 1 second using the patterns above.

**Files to prioritize:**
1. `test_api_gateway_docker.py` (15s sleep!)
2. `test_durable_gateway_real_world.py` (3s sleeps)
3. `test_transaction_monitoring_*.py` (2-3s sleeps)
4. `test_cache*.py` (1.1s TTL waits)

### Phase 2: Moderate Fixes (24 instances)
Replace 0.5-0.9s sleeps with condition-based waiting.

### Phase 3: Low Priority
Evaluate short sleeps (<0.5s) - many are justified for timing simulations.

## Testing the Fixes

After implementing fixes:

```bash
# Verify timeouts are respected
pytest tests/integration/ --timeout=5 -v

# Run specific fixed test
pytest tests/e2e/test_durable_gateway_real_world.py::test_health_check --timeout=10 -v

# Check for regression
python tests/utils/fix_test_sleeps.py --check
```

## Example PR Structure

```
fix: Replace fixed sleeps with condition-based waiting in tests

- Replace 15s Docker wait with health check polling
- Replace 3s gateway startup waits with HTTP health checks  
- Replace 1.1s cache TTL waits with 0.1s + condition check
- Use edge coordination polling pattern throughout

Reduces test execution time by 2-5 minutes per run.
```

## Verification Checklist

- [ ] All critical sleeps (>= 1s) replaced
- [ ] Tests pass with timeout enforcement
- [ ] No new sleeps added (CI check)
- [ ] Performance improvement measured