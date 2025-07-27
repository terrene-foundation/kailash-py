# Enterprise Resilience Patterns

Production-grade fault tolerance patterns for the Kailash SDK.

## Overview

The Kailash SDK provides three core resilience patterns for building fault-tolerant enterprise applications:

1. **Circuit Breaker** - Prevents cascade failures
2. **Bulkhead Isolation** - Resource partitioning by operation type
3. **Health Monitoring** - Real-time infrastructure monitoring with alerts

## Circuit Breaker Pattern

### Basic Usage

```python
from kailash.core.resilience.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig

# Create circuit breaker manager and config
manager = CircuitBreakerManager()
config = CircuitBreakerConfig(
    failure_threshold=5,     # Open after 5 failures
    success_threshold=2      # Close after 2 successes
)

# Get or create a circuit breaker
breaker = manager.get_or_create("database_operations", config)

# Use with decorator
@breaker
async def database_operation():
    # Your database code here
    return result

# Or use with context manager
async with breaker:
    result = await database_operation()
```

### Advanced Configuration

```python
from kailash.core.resilience.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig

# Advanced configuration (note: some parameters like timeout may not be supported)
config = CircuitBreakerConfig(
    failure_threshold=10,
    success_threshold=5
)

manager = CircuitBreakerManager()
breaker = manager.get_or_create("advanced_operations", config)
```

### Integration with Nodes

```python
from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.core.resilience.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig

# Create circuit breaker for database operations
manager = CircuitBreakerManager()
config = CircuitBreakerConfig(failure_threshold=3)
db_breaker = manager.get_or_create("database", config)

# Wrap node execution
@db_breaker
def execute_query(query):
    node = SQLDatabaseNode(connection_string="postgresql://...")
    return node.execute(query=query)
```

## Bulkhead Isolation Pattern

### Basic Usage

```python
from kailash.core.resilience.bulkhead import get_bulkhead_manager, execute_with_bulkhead

# Get bulkhead manager
manager = get_bulkhead_manager()

# Execute operation with bulkhead isolation
# Note: check actual execute_with_bulkhead parameters
async def database_operation():
    return "result"

result = await execute_with_bulkhead("database", database_operation)
```

### Partition Configuration

```python
from kailash.core.resilience.bulkhead import (
    get_bulkhead_manager,
    PartitionConfig,
    PartitionType
)

manager = get_bulkhead_manager()

# Create partition configuration with required parameters
config = PartitionConfig(
    name="database_partition",
    partition_type=PartitionType.IO_BOUND  # For database operations
)

# Configure database partition
manager.configure_partition(PartitionConfig(
    name="database",
    partition_type=PartitionType.DATABASE,
    max_concurrent_operations=20,
    max_connections=10,
    timeout=30,
    priority=1
))

# Configure API partition
manager.configure_partition(PartitionConfig(
    name="api",
    partition_type=PartitionType.API,
    max_concurrent_operations=50,
    max_threads=25,
    timeout=15,
    priority=2
))

# Configure background tasks
manager.configure_partition(PartitionConfig(
    name="background",
    partition_type=PartitionType.BACKGROUND,
    max_concurrent_operations=10,
    timeout=300,
    priority=3
))
```

### Enterprise Integration Example

```python
from kailash.core.resilience.bulkhead import execute_with_bulkhead
from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.nodes.api import HTTPRequestNode

# Database operations isolated in database partition
async def process_order(order_id):
    def db_operation():
        node = SQLDatabaseNode(connection_string=conn_str)
        return node.execute(
            query="INSERT INTO orders VALUES (%s)",
            params=[order_id]
        )

    return await execute_with_bulkhead("database", db_operation)

# API calls isolated in API partition
async def notify_customer(customer_id):
    def api_operation():
        node = "HTTPRequestNode"
        return node.execute(
            url=f"https://api.example.com/notify/{customer_id}",
            method="POST"
        )

    return await execute_with_bulkhead("api", api_operation)

# Background processing isolated
async def generate_report(report_id):
    def bg_operation():
        # Long-running report generation
        return generate_complex_report(report_id)

    return await execute_with_bulkhead("background", bg_operation, priority=3)
```

## Health Monitoring

### Basic Health Checks

```python
from kailash.core.resilience.health_monitor import (
    get_health_monitor,
    DatabaseHealthCheck,
    RedisHealthCheck,
    HTTPHealthCheck
)

# Get global health monitor
monitor = get_health_monitor()

# Register database health check
monitor.register_check(
    "primary_db",
    DatabaseHealthCheck(
        "primary_db",
        connection_string="postgresql://...",
        critical=True
    )
)

# Register Redis health check
monitor.register_check(
    "cache",
    RedisHealthCheck(
        "cache",
        redis_config={"host": "localhost", "port": 6379},
        critical=True
    )
)

# Register HTTP endpoint check
monitor.register_check(
    "api_gateway",
    HTTPHealthCheck(
        "api_gateway",
        url="https://api.example.com/health",
        expected_status=[200, 204],
        critical=True
    )
)

# Check overall health
overall_health = await monitor.get_overall_health()
if overall_health != HealthStatus.HEALTHY:
    # Take corrective action
    pass
```

### Custom Health Checks

```python
from kailash.core.resilience.health_monitor import HealthCheck, HealthStatus

class KafkaHealthCheck(HealthCheck):
    def __init__(self, name: str, kafka_config: dict, **kwargs):
        super().__init__(name, **kwargs)
        self.kafka_config = kafka_config

    async def check_health(self) -> dict:
        try:
            # Check Kafka connectivity
            producer = KafkaProducer(**self.kafka_config)
            producer.send("health-check-topic", b"ping")
            producer.flush(timeout=5)

            return {
                "status": HealthStatus.HEALTHY.value,
                "message": "Kafka is healthy"
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "error": str(e)
            }

# Register custom check
monitor.register_check(
    "kafka",
    KafkaHealthCheck("kafka", kafka_config, critical=True)
)
```

### Alert Configuration

```python
from kailash.core.resilience.health_monitor import AlertLevel

# Register alert callback
def handle_health_alert(alert):
    if alert.level == AlertLevel.CRITICAL:
        # Send to PagerDuty
        notify_oncall(alert)
    elif alert.level == AlertLevel.WARNING:
        # Send to Slack
        send_slack_alert(alert)

    # Log all alerts
    logger.error(f"Health Alert: {alert.service_name} - {alert.message}")

monitor.register_alert_callback(handle_health_alert)

# Configure monitoring
monitor = get_health_monitor(
    check_interval=30.0,    # Check every 30 seconds
    alert_threshold=2       # Alert after 2 consecutive failures
)
```

## Complete Enterprise Example

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.core.resilience.circuit_breaker import get_circuit_breaker
from kailash.core.resilience.bulkhead import execute_with_bulkhead
from kailash.core.resilience.health_monitor import get_health_monitor

# Configure resilience patterns
db_breaker = get_circuit_breaker("database", failure_threshold=5)
monitor = get_health_monitor()

# Create resilient workflow
workflow = WorkflowBuilder()

# Add health check node
workflow.add_node(
    "HealthCheckNode",
    "health_check",
    {
        "services": [
            {
                "name": "database",
                "type": "database",
                "connection_string": db_conn,
                "critical": True
            },
            {
                "name": "cache",
                "type": "redis",
                "redis_config": redis_config,
                "critical": False
            }
        ]
    }
)

# Add database operation with circuit breaker
@db_breaker
async def database_operation(params):
    node = workflow.get_node("database_node")
    return await execute_with_bulkhead(
        "database",
        lambda: node.execute(**params)
    )

# Add workflow logic
workflow.add_node("SwitchNode", "health_switch", {
    "condition": "overall_status == 'healthy'"
})

workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

# Execute with resilience
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Monitor execution health
execution_health = await monitor.get_all_health_status()
if any(not status.is_healthy for status in execution_health.values()):
    logger.warning(f"Degraded health detected during execution {run_id}")
```

## Best Practices

### 1. Layer Your Defenses
- Use circuit breakers for external dependencies
- Apply bulkhead isolation for resource-intensive operations
- Monitor health continuously

### 2. Configure Appropriately
- Set circuit breaker thresholds based on SLAs
- Size bulkhead partitions based on load testing
- Configure health check intervals for timely detection

### 3. Handle Degradation Gracefully
```python
# Check health before critical operations
health = await monitor.get_health_status("primary_db")
if not health.is_healthy:
    # Use fallback or queue for later
    return use_fallback_strategy()

# Execute with protection
try:
    result = await execute_with_bulkhead(
        "database",
        lambda: critical_operation()
    )
except BulkheadFullError:
    # Queue for retry or use alternate path
    return queue_for_retry(operation)
```

### 4. Monitor and Alert
- Set up comprehensive health checks for all critical services
- Configure appropriate alert thresholds
- Use metrics to tune resilience parameters

### 5. Test Failure Scenarios
```python
# Test circuit breaker
breaker = get_circuit_breaker("test", failure_threshold=2)
breaker.record_failure()  # Simulate failures
breaker.record_failure()
assert breaker.state == CircuitState.OPEN

# Test bulkhead isolation
manager = get_bulkhead_manager()
partition = manager.get_partition("database")
# Fill the partition
for _ in range(partition.config.max_concurrent_operations):
    partition.acquire()
# Verify rejection
with pytest.raises(BulkheadFullError):
    partition.acquire()
```

## Performance Considerations

1. **Circuit Breakers**: Minimal overhead (<1ms per call)
2. **Bulkhead Isolation**: Thread pool management adds ~5ms
3. **Health Monitoring**: Async checks minimize impact

## Migration Guide

If migrating from existing error handling:

```python
# Before
try:
    result = database_operation()
except Exception as e:
    logger.error(f"Database error: {e}")
    raise

# After
@get_circuit_breaker("database", failure_threshold=5)
async def resilient_operation():
    return await execute_with_bulkhead(
        "database",
        lambda: database_operation()
    )

# With health monitoring
health = await monitor.get_health_status("database")
if health.is_healthy:
    result = await resilient_operation()
else:
    result = await use_cache_fallback()
```

## See Also

- [Circuit Breaker Implementation](../../src/kailash/core/resilience/circuit_breaker.py)
- [Bulkhead Implementation](../../src/kailash/core/resilience/bulkhead.py)
- [Health Monitor Implementation](../../src/kailash/core/resilience/health_monitor.py)
- [Testing Guide](../developer/12-testing-production-quality.md)
- [Production Patterns](production-patterns.md)
