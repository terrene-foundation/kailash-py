# Test Sleep Analysis Report

This document analyzes all `sleep()` calls found in integration and E2E tests to identify opportunities for improvement using proper synchronization techniques.

## Summary Statistics

- **Total sleep calls found**: 283
- **Critical (>= 1 second)**: 12 instances
- **Moderate (0.5-0.9s)**: 14 instances  
- **Short (<0.5s)**: 122 instances
- **PostgreSQL pg_sleep**: 11 instances
- **Justified (with comments)**: 124 instances

## Critical Long Sleeps (>= 1 second) - HIGH PRIORITY

These should be replaced with proper synchronization:

### 1. **Gateway Startup Waits** (3 seconds each)
```python
# tests/e2e/test_durable_gateway_real_world.py:484
time.sleep(3)

# tests/e2e/test_transaction_monitoring_e2e.py:319
time.sleep(3.0)

# tests/e2e/test_async_python_code_node_e2e.py:139
time.sleep(3)
```
**Fix**: Use health check endpoint polling instead

### 2. **Docker Service Waits** (up to 15 seconds!)
```python
# tests/integration/middleware/test_api_gateway_docker.py:313
time.sleep(15)  # Waiting for Docker service

# tests/integration/middleware/test_durable_gateway_basic.py:99
time.sleep(2)  # Wait for service startup
```
**Fix**: Implement proper health checks with container.exec_run()

### 3. **Cache TTL/Expiration Tests** (1.1 seconds each)
```python
# tests/integration/nodes/cache/test_cache.py:340
time.sleep(1.1)  # Wait for cache expiration

# tests/integration/mcp_server/utils/test_mcp_cache.py:93
time.sleep(1.1)  # Wait for TTL
```
**Fix**: Use shorter TTLs in tests or mock time

### 4. **Monitoring/Detection Cycles** (2-3 seconds)
```python
# tests/integration/nodes/monitoring/test_transaction_monitoring_integration.py:193
time.sleep(3.0)  # Wait for monitoring cycle

# tests/integration/nodes/monitoring/test_transaction_monitoring_integration.py:259
time.sleep(2.0)  # Wait for detection
```
**Fix**: Use event-based signaling or shorter detection intervals

## Moderate Sleeps (0.5-0.9s) - MEDIUM PRIORITY

### Service Discovery & Health Checks
```python
# tests/integration/mcp_server/test_discovery_docker.py:150
await asyncio.sleep(0.5)

# tests/integration/middleware/test_gateway_integration.py:176
await asyncio.sleep(0.5)  # Allow execution to complete
```
**Fix**: Poll for specific conditions rather than fixed delays

### Performance & Stress Tests
```python
# tests/e2e/test_workflow_builder_real_world_e2e.py:1983
time.sleep(0.5)  # Reduced for E2E timeout

# tests/e2e/scenarios/test_admin_nodes_performance_e2e.py:847
time.sleep(0.5)  # Reduced for E2E timeout
```
**Fix**: These might be justified for performance testing scenarios

## PostgreSQL Sleep Queries

Used for testing timeout handling - these are generally acceptable:

```sql
-- tests/integration/nodes/test_async_sql_functional.py:1353
SELECT pg_sleep(5)  -- Testing query timeout

-- tests/integration/nodes/test_async_sql_retry_integration.py:207
SELECT pg_sleep(2)  -- Testing retry mechanism

-- tests/integration/core/test_bulkhead_integration.py:322
SELECT pg_sleep(0.5), 'slow_operation' as result
```

## Recommended Fixes by Category

### 1. Service Startup Waits
Replace with health check polling:
```python
# Instead of:
time.sleep(3)  # Wait for service

# Use:
await wait_for_condition(
    lambda: check_service_health(),
    timeout=10,
    interval=0.1
)
```

### 2. Cache Expiration Tests
Use shorter TTLs or time mocking:
```python
# Instead of:
cache.set("key", "value", ttl=1)
time.sleep(1.1)

# Use:
cache.set("key", "value", ttl=0.1)
await asyncio.sleep(0.15)
```

### 3. Event Synchronization
Use event-based waiting:
```python
# Instead of:
start_async_operation()
await asyncio.sleep(1)  # Wait for completion

# Use:
event = asyncio.Event()
start_async_operation(on_complete=event.set)
await asyncio.wait_for(event.wait(), timeout=5)
```

### 4. Docker Container Readiness
Use exec_run health checks:
```python
# Instead of:
container.start()
time.sleep(5)  # Wait for container

# Use:
container.start()
await wait_for_container_health(container, timeout=30)
```

## Tests Requiring Special Attention

### 1. **Performance/Stress Tests**
These legitimately need timing controls but should use configurable delays:
- `test_performance_stress.py` - Multiple timing-sensitive operations
- `test_admin_nodes_performance_e2e.py` - Performance benchmarking

### 2. **MCP Stress Testing**
- `test_mcp_stress_testing.py` - Has multiple sleeps for rate limiting
- Consider using a test-specific rate limiter with shorter intervals

### 3. **Transaction Monitoring**
- `test_transaction_monitoring_*.py` - Multiple long sleeps
- Should use event-based detection rather than polling cycles

## Implementation Priority

1. **High Priority** (12 instances): Fix all sleeps >= 1 second
   - Estimated time saved: 2-5 minutes per test run
   
2. **Medium Priority** (14 instances): Fix sleeps 0.5-0.9 seconds  
   - Estimated time saved: 30-60 seconds per test run
   
3. **Low Priority**: Short sleeps < 0.5 seconds
   - Many are justified for simulation purposes
   - Focus on those without explanatory comments

## Automation Recommendations

1. Add a pre-commit hook to flag new sleeps > 0.5 seconds
2. Use pytest markers for legitimately slow tests: `@pytest.mark.slow`
3. Configure test timeouts to catch stuck tests early
4. Add the `fix_test_sleeps.py` script to CI pipeline

## Next Steps

1. Start with the 12 critical long sleeps
2. Create helper functions for common patterns (service health, cache expiry, etc.)
3. Update test guidelines to discourage fixed sleeps
4. Add timing assertions to ensure tests complete quickly