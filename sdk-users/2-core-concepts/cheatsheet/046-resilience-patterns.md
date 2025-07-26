# Resilience Patterns Cheatsheet

Quick reference for enterprise resilience patterns: circuit breakers, bulkhead isolation, and health monitoring.

## Circuit Breaker - Quick Start

```python
from kailash.core.resilience.circuit_breaker import get_circuit_breaker

# Basic circuit breaker
breaker = get_circuit_breaker("api_calls", failure_threshold=5)

# Use as decorator
@breaker
async def call_api():
    return await http_client.get("https://api.example.com")

# Use with context manager
async with breaker:
    result = await call_api()
```

## Bulkhead Isolation - Quick Start

```python
from kailash.core.resilience.bulkhead import execute_with_bulkhead

# Execute with resource isolation
result = await execute_with_bulkhead(
    "database",  # Partition name
    lambda: db_operation()
)
```

## Health Monitoring - Quick Start

```python
from kailash.core.resilience.health_monitor import get_health_monitor, DatabaseHealthCheck

# Register health check
monitor = get_health_monitor()
monitor.register_check(
    "primary_db",
    DatabaseHealthCheck("primary_db", connection_string, critical=True)
)

# Check health
health = await monitor.get_health_status("primary_db")
if not health.is_healthy:
    # Use fallback
    pass
```

## Common Patterns

### Pattern 1: Database with Circuit Breaker

```python
from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.core.resilience.circuit_breaker import get_circuit_breaker

db_breaker = get_circuit_breaker("database", failure_threshold=3)

@db_breaker
def query_database(query, params):
    node = SQLDatabaseNode(connection_string=conn_str)
    return node.execute(query=query, params=params)
```

### Pattern 2: API Calls with Bulkhead

```python
from kailash.nodes.api import HTTPRequestNode
from kailash.core.resilience.bulkhead import execute_with_bulkhead

async def call_external_api(url):
    def api_call():
        node = "HTTPRequestNode"
        return node.execute(url=url, method="GET")

    return await execute_with_bulkhead("api", api_call)
```

### Pattern 3: Workflow with Health Checks

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Add health check as first node
workflow.add_node("HealthCheckNode", "health", {
    "services": [
        {"name": "db", "type": "database", "connection_string": db_conn},
        {"name": "cache", "type": "redis", "redis_config": redis_config}
    ]
})

# Route based on health
workflow.add_node("SwitchNode", "router", {
    "condition": "overall_status == 'healthy'"
})

workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
```

### Pattern 4: Complete Resilient Service

```python
from kailash.core.resilience.circuit_breaker import get_circuit_breaker
from kailash.core.resilience.bulkhead import execute_with_bulkhead
from kailash.core.resilience.health_monitor import get_health_monitor

# Setup
db_breaker = get_circuit_breaker("db", failure_threshold=5)
monitor = get_health_monitor()

# Resilient operation
@db_breaker
async def process_order(order_id):
    # Check health first
    health = await monitor.get_health_status("database")
    if not health.is_healthy:
        return {"status": "queued", "reason": "database_unavailable"}

    # Execute with bulkhead
    def db_op():
        node = SQLDatabaseNode(connection_string=conn_str)
        return node.execute(
            query="INSERT INTO orders (id) VALUES (%s)",
            params=[order_id]
        )

    return await execute_with_bulkhead("database", db_op)
```

## Configuration Reference

### Circuit Breaker Settings

```python
# Default thresholds
get_circuit_breaker("service",
    failure_threshold=5,      # Open after 5 failures
    success_threshold=2,      # Close after 2 successes
    timeout=30,              # Reset timeout (seconds)
    half_open_max_calls=3    # Test calls when half-open
)
```

### Bulkhead Partitions

```python
from kailash.core.resilience.bulkhead import PartitionConfig, PartitionType

# Database partition
PartitionConfig(
    name="database",
    partition_type=PartitionType.DATABASE,
    max_concurrent_operations=20,
    max_connections=10,
    timeout=30
)

# API partition
PartitionConfig(
    name="api",
    partition_type=PartitionType.API,
    max_concurrent_operations=50,
    max_threads=25,
    timeout=15
)

# Background tasks
PartitionConfig(
    name="background",
    partition_type=PartitionType.BACKGROUND,
    max_concurrent_operations=10,
    timeout=300
)
```

### Health Check Types

```python
# Database check
DatabaseHealthCheck(
    name="primary_db",
    connection_string="postgresql://...",
    test_query="SELECT 1",
    timeout=5.0,
    critical=True
)

# Redis check
RedisHealthCheck(
    name="cache",
    redis_config={"host": "localhost", "port": 6379},
    timeout=3.0,
    critical=True
)

# HTTP check
HTTPHealthCheck(
    name="api",
    url="https://api.example.com/health",
    expected_status=[200, 204],
    timeout=10.0,
    critical=False
)
```

## Error Handling

### Circuit Breaker States

```python
from kailash.core.resilience.circuit_breaker import CircuitBreakerOpenError

try:
    result = await protected_operation()
except CircuitBreakerOpenError:
    # Circuit is open - use fallback
    result = get_cached_result()
```

### Bulkhead Full

```python
from kailash.core.resilience.bulkhead import BulkheadFullError

try:
    result = await execute_with_bulkhead("api", operation)
except BulkheadFullError:
    # Partition full - queue or reject
    return {"status": "rate_limited"}
```

### Health Degradation

```python
overall = await monitor.get_overall_health()

if overall == HealthStatus.HEALTHY:
    # Normal operation
    pass
elif overall == HealthStatus.DEGRADED:
    # Reduced functionality
    disable_non_critical_features()
elif overall == HealthStatus.UNHEALTHY:
    # Emergency mode
    return maintenance_page()
```

## Testing Patterns

### Test Circuit Breaker

```python
# Force circuit open
breaker = get_circuit_breaker("test", failure_threshold=2)
breaker.record_failure()
breaker.record_failure()
assert breaker.state == CircuitState.OPEN
```

### Test Bulkhead

```python
# Fill partition
partition = manager.get_partition("test")
handles = []
for _ in range(partition.config.max_concurrent_operations):
    handles.append(partition.acquire())

# Verify full
with pytest.raises(BulkheadFullError):
    partition.acquire()

# Release
for handle in handles:
    partition.release(handle)
```

### Test Health Monitor

```python
# Mock unhealthy service
class FailingHealthCheck(HealthCheck):
    async def check_health(self):
        return {"status": "unhealthy", "error": "test"}

monitor.register_check("failing", FailingHealthCheck("failing"))
health = await monitor.get_health_status("failing")
assert not health.is_healthy
```

## Best Practices

1. **Layer defenses** - Use multiple patterns together
2. **Set appropriate thresholds** - Based on SLAs and testing
3. **Monitor metrics** - Track circuit breaker trips, bulkhead rejections
4. **Test failure modes** - Verify graceful degradation
5. **Document dependencies** - Know critical vs non-critical services

## See Also

- [Full Resilience Guide](../enterprise/resilience-patterns.md)
- [Health Check Node](../nodes/monitoring/health-check.md)
- [Production Patterns](../enterprise/production-patterns.md)
