# Circuit Breaker Pattern Guide

## Overview
The Circuit Breaker pattern protects your database connections from cascading failures. When connections fail repeatedly, the circuit "opens" to prevent further attempts, allowing the system to recover.

## Quick Start

### Basic Setup
```python
from kailash.nodes.data import WorkflowConnectionPool

# Create pool with circuit breaker enabled
pool = WorkflowConnectionPool(
    name="production_pool",
    database_type="postgresql",
    host="localhost",
    port=5432,
    database="myapp",
    # Circuit breaker configuration
    circuit_breaker_enabled=True,
    circuit_breaker_failure_threshold=5,    # Open after 5 failures
    circuit_breaker_recovery_timeout=60,    # Try recovery after 60s
    circuit_breaker_error_rate=0.5          # Open if 50% requests fail
)
```

## Circuit Breaker States

### 1. CLOSED (Normal Operation)
- All requests pass through normally
- Failures are counted
- Transitions to OPEN when threshold exceeded

### 2. OPEN (Circuit Broken)
- All requests fail immediately
- No database connections attempted
- Waits for recovery timeout

### 3. HALF_OPEN (Testing Recovery)
- Limited requests allowed
- Success → CLOSED
- Failure → OPEN

## Configuration Options

### Failure Threshold
```python
# Open circuit after N consecutive failures
circuit_breaker_failure_threshold=5
```

### Error Rate Threshold
```python
# Open circuit if error rate exceeds percentage
circuit_breaker_error_rate=0.5  # 50% failure rate
```

### Recovery Timeout
```python
# Wait N seconds before testing recovery
circuit_breaker_recovery_timeout=60.0
```

### Success Threshold
```python
# Require N successes in HALF_OPEN to close circuit
circuit_breaker_success_threshold=3
```

## Error Categories
The circuit breaker categorizes errors for intelligent handling:

1. **CONNECTION_ERROR**: Network issues → Circuit opens quickly
2. **TIMEOUT_ERROR**: Slow queries → May indicate overload
3. **RESOURCE_ERROR**: Pool exhaustion → Temporary backoff
4. **AUTHENTICATION_ERROR**: Credentials → Won't trigger circuit
5. **DATABASE_ERROR**: DB errors → Evaluate severity
6. **QUERY_ERROR**: Bad SQL → Won't trigger circuit
7. **UNKNOWN_ERROR**: Other → Conservative handling

## Monitoring Circuit State

### Get Current State
```python
status = await pool.get_circuit_breaker_status()
print(f"State: {status['state']}")
print(f"Failure count: {status['failure_count']}")
print(f"Last failure: {status['last_failure_time']}")
```

### Listen for State Changes
```python
def on_state_change(old_state, new_state, reason):
    logger.warning(f"Circuit breaker: {old_state} → {new_state} ({reason})")

pool.circuit_breaker.add_listener(on_state_change)
```

## Best Practices

### 1. Set Appropriate Thresholds
```python
# For critical services - be conservative
circuit_breaker_failure_threshold=10
circuit_breaker_recovery_timeout=120

# For non-critical - fail fast
circuit_breaker_failure_threshold=3
circuit_breaker_recovery_timeout=30
```

### 2. Handle Circuit Open State
```python
try:
    result = await pool.execute_query({
        "query": "SELECT * FROM users WHERE id = $1",
        "parameters": [user_id]
    })
except CircuitBreakerOpenError:
    # Return cached data or degraded response
    return get_cached_user(user_id)
```

### 3. Monitor and Alert
```python
# Export metrics for monitoring
metrics = pool.get_circuit_breaker_metrics()

# Set up alerts
if metrics["open_count"] > 5:
    alert_ops_team("Frequent circuit breaker activations")
```

### 4. Test Recovery Logic
```python
# Force circuit to open (testing only)
await pool.circuit_breaker._transition_to(CircuitState.OPEN)

# Verify your fallback logic works
result = await your_service.get_data()  # Should use fallback
```

## Common Patterns

### Fallback to Cache
```python
async def get_user_data(user_id):
    try:
        # Try database first
        return await pool.execute_query({
            "query": "SELECT * FROM users WHERE id = $1",
            "parameters": [user_id]
        })
    except CircuitBreakerOpenError:
        # Fallback to cache
        cached = await redis.get(f"user:{user_id}")
        if cached:
            return json.loads(cached)
        raise ServiceUnavailableError("Database unavailable")
```

### Gradual Degradation
```python
async def search_products(query, filters):
    try:
        # Full search with filters
        return await pool.execute_query({
            "query": complex_search_query,
            "parameters": [query, filters]
        })
    except CircuitBreakerOpenError:
        try:
            # Simplified search
            return await backup_pool.execute_query({
                "query": simple_search_query,
                "parameters": [query]
            })
        except:
            # Return popular products
            return get_popular_products()
```

### Circuit Breaker Chaining
```python
# Primary and backup pools with circuit breakers
primary_pool = WorkflowConnectionPool(
    name="primary",
    circuit_breaker_failure_threshold=5
)

backup_pool = WorkflowConnectionPool(
    name="backup",
    circuit_breaker_failure_threshold=10  # More tolerant
)

async def execute_with_fallback(query):
    try:
        return await primary_pool.execute_query(query)
    except CircuitBreakerOpenError:
        logger.warning("Primary circuit open, using backup")
        return await backup_pool.execute_query(query)
```

## Troubleshooting

### Circuit Opens Too Frequently
- Increase `failure_threshold`
- Increase `recovery_timeout`
- Check for transient network issues
- Review error categorization

### Circuit Never Recovers
- Check if underlying issue is resolved
- Reduce `success_threshold`
- Manually close circuit if needed:
  ```python
  await pool.circuit_breaker._transition_to(CircuitState.CLOSED)
  ```

### Performance Impact
- Circuit breaker adds <1μs overhead
- Failing fast saves resources
- Monitor metrics to verify

## Production Checklist
- [ ] Configure thresholds based on SLAs
- [ ] Implement fallback strategies
- [ ] Set up monitoring and alerts
- [ ] Test circuit breaker behavior
- [ ] Document recovery procedures
- [ ] Train team on circuit states

## Related Guides
- [Connection Pool Guide](./connection-pool-guide.md)
- [Metrics Guide](./metrics-collection-guide.md)
- [Monitoring Dashboard](./monitoring-dashboard-guide.md)
