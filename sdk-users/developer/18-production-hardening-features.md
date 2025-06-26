# Production Hardening Features (Phase 3)

This guide covers the advanced production features that make your database connections resilient, observable, and performant at scale.

## Overview

Phase 3 adds four critical production features:
1. **Circuit Breaker** - Prevent cascading failures
2. **Comprehensive Metrics** - Deep observability
3. **Query Pipelining** - Batch execution for performance
4. **Monitoring Dashboard** - Real-time visualization

## Circuit Breaker Protection

### Why Circuit Breakers?

Database failures can cascade through your application:
- Failed queries retry repeatedly
- Connections get stuck waiting
- Thread pools exhaust
- Entire application freezes

Circuit breakers fail fast, giving your database time to recover.

### Basic Usage

```python
from kailash.nodes.data import WorkflowConnectionPool

# Circuit breaker is automatically configured
pool = WorkflowConnectionPool(
    name="protected_pool",
    database_type="postgresql",
    # ... connection details ...

    # Circuit breaker configuration
    circuit_breaker_failure_threshold=5,    # Open after 5 consecutive failures
    circuit_breaker_recovery_timeout=60,    # Try recovery after 60 seconds
    circuit_breaker_error_rate=0.5         # Open if error rate > 50%
)

# Use normally - circuit breaker protects automatically
try:
    result = await pool.process({
        "operation": "acquire"
    })
except CircuitBreakerError as e:
    # Circuit is open - database is failing
    logger.error(f"Database unavailable: {e}")
    # Return cached data or degraded response
```

### Circuit Breaker States

1. **CLOSED** (Normal)
   - All requests pass through
   - Monitoring for failures

2. **OPEN** (Failing)
   - Requests fail immediately
   - No load on failing database
   - Waiting for recovery timeout

3. **HALF_OPEN** (Testing)
   - Limited requests allowed
   - Testing if database recovered
   - Success → CLOSED, Failure → OPEN

### Configuration Strategies

#### Conservative (Financial Systems)
```python
# Open circuit quickly, recover slowly
circuit_breaker_failure_threshold=3
circuit_breaker_recovery_timeout=120
circuit_breaker_error_rate=0.1
```

#### Balanced (E-commerce)
```python
# Default settings work well
circuit_breaker_failure_threshold=5
circuit_breaker_recovery_timeout=60
circuit_breaker_error_rate=0.5
```

#### Tolerant (Analytics)
```python
# Allow more failures before opening
circuit_breaker_failure_threshold=10
circuit_breaker_recovery_timeout=30
circuit_breaker_error_rate=0.7
```

### Manual Control

```python
# Force circuit open (maintenance)
await pool.circuit_breaker.force_open("Database maintenance")

# Force circuit closed (after verification)
await pool.circuit_breaker.force_close("Maintenance complete")

# Check status
status = pool.circuit_breaker.get_status()
print(f"State: {status['state']}")
print(f"Failures: {status['metrics']['consecutive_failures']}")
```

## Comprehensive Metrics Collection

### Automatic Metrics

The pool automatically collects:

- **Connection Metrics**
  - Acquisition time (with percentiles)
  - Creation/release counts
  - Reuse rate
  - Health check results

- **Query Metrics**
  - Execution time by query type
  - Success/failure rates
  - Error categorization
  - Query patterns

- **Pool Metrics**
  - Utilization rate
  - Active/idle counts
  - Queue depth
  - Saturation events

### Accessing Metrics

```python
# Get comprehensive metrics
pool = WorkflowConnectionPool(
    name="metrics_pool",
    metrics_retention_minutes=60,  # Keep 1 hour of detailed metrics
    # ... other config ...
)

# Get all metrics
metrics = await pool.process({
    "operation": "get_comprehensive_status"
})

# Key metrics
print(f"Queries/sec: {metrics['queries_per_second']:.1f}")
print(f"Error rate: {metrics['error_rate']:.2%}")
print(f"P95 latency: {metrics['detailed_metrics']['histograms']['query_execution_ms']['p95']:.1f}ms")
```

### Error Analysis

Errors are automatically categorized:

```python
error_summary = metrics['detailed_metrics']['errors']

# Total errors
print(f"Total errors: {error_summary['total_errors']}")

# Breakdown by category
for category, count in error_summary['errors_by_category'].items():
    print(f"{category}: {count}")

# Categories include:
# - connection_timeout
# - connection_refused
# - authentication_failed
# - query_timeout
# - query_error
# - pool_exhausted
```

### Prometheus Export

```python
# Export metrics in Prometheus format
result = await pool.process({
    "operation": "export_metrics"
})

prometheus_metrics = result["prometheus_metrics"]

# Save to file or serve via HTTP endpoint
with open("/var/lib/prometheus/connection_pool.prom", "w") as f:
    f.write(prometheus_metrics)
```

### Grafana Dashboard

Create alerts based on metrics:

```yaml
# High error rate alert
- alert: DatabaseErrorRateHigh
  expr: connection_pool_error_rate{pool="production"} > 0.05
  for: 5m
  annotations:
    summary: "Database error rate above 5%"

# Slow queries alert
- alert: DatabaseSlowQueries
  expr: connection_pool_query_execution_ms{quantile="0.95"} > 1000
  for: 10m
  annotations:
    summary: "95th percentile query time above 1 second"
```

## Query Pipelining

### When to Use Pipelining

Query pipelining dramatically improves performance for:
- Bulk inserts/updates
- ETL processes
- Data migrations
- Analytics data loading
- Log ingestion

### Basic Usage

```python
from kailash.nodes.data import QueryPipelineNode

# Create pipeline
pipeline = QueryPipelineNode(
    name="bulk_insert",
    connection_pool="main_pool",
    batch_size=100,           # Batch up to 100 queries
    flush_interval=0.1,       # Auto-flush every 100ms
    strategy="best_effort"    # Continue on individual failures
)

# Add queries to pipeline
for record in large_dataset:
    await pipeline.add_query(
        "INSERT INTO events (timestamp, type, data) VALUES ($1, $2, $3)",
        [record.timestamp, record.type, record.data]
    )

# Execute batch
results = await pipeline.flush()

# Check results
success_count = sum(1 for r in results if r.success)
print(f"Inserted {success_count}/{len(results)} records")
```

### Execution Strategies

#### Best Effort (Default)
```python
strategy="best_effort"
# Continue processing even if some queries fail
# Good for: logs, metrics, non-critical data
```

#### Transactional
```python
strategy="transactional"
# All queries succeed or all fail (ACID)
# Good for: financial transactions, critical updates
```

#### Sequential
```python
strategy="sequential"
# Execute in order, stop on first failure
# Good for: dependent queries, migrations
```

#### Parallel
```python
strategy="parallel"
# Execute SELECT queries concurrently
# Good for: analytics, reporting
```

### Performance Example

```python
# Without pipelining - slow
start = time.time()
for i in range(1000):
    await pool.process({
        "operation": "execute",
        "query": "INSERT INTO test VALUES ($1)",
        "params": [i]
    })
individual_time = time.time() - start

# With pipelining - fast!
start = time.time()
for i in range(1000):
    await pipeline.add_query(
        "INSERT INTO test VALUES ($1)",
        [i]
    )
await pipeline.flush()
pipeline_time = time.time() - start

print(f"Speedup: {individual_time / pipeline_time:.1f}x")
# Typical speedup: 5-10x
```

### Advanced Patterns

```python
# Automatic optimization
pipeline = QueryPipelineNode(
    name="optimized_pipeline",
    connection_pool="main_pool",
    enable_optimization=True  # Reorder queries for performance
)

# Mixed operations - optimizer puts SELECTs first
await pipeline.add_query("INSERT INTO audit_log VALUES (...)")
await pipeline.add_query("SELECT * FROM users WHERE active = true")
await pipeline.add_query("UPDATE products SET stock = stock - 1")
await pipeline.add_query("SELECT COUNT(*) FROM orders")

# Optimizer reorders to: SELECT, SELECT, INSERT, UPDATE
results = await pipeline.flush()
```

## Monitoring Dashboard

### Starting the Dashboard

```python
# Enable monitoring in pool configuration
pool = WorkflowConnectionPool(
    name="monitored_pool",
    enable_monitoring=True,
    monitoring_port=8080,  # Dashboard port
    # ... other config ...
)

# Start dashboard
await pool.process({
    "operation": "start_monitoring"
})

# Access at http://localhost:8080
```

### Dashboard Features

1. **Real-time Metrics**
   - Connection pool health scores
   - Active/idle connection counts
   - Query throughput graphs
   - Error rate visualization

2. **Alert System**
   - Configurable thresholds
   - Visual alerts
   - Alert history

3. **Historical Charts**
   - Pool utilization over time
   - Query latency trends
   - Error patterns

### Custom Alerts

```python
# Via API
import aiohttp

async with aiohttp.ClientSession() as session:
    await session.post("http://localhost:8080/api/alerts", json={
        "name": "High Latency Alert",
        "condition": "avg_query_time_ms > 100",
        "threshold": 100,
        "duration_seconds": 60,
        "severity": "warning"
    })
```

### Stopping the Dashboard

```python
await pool.process({
    "operation": "stop_monitoring"
})
```

## Complete Example: Production Configuration

```python
from kailash.nodes.data import WorkflowConnectionPool, QueryPipelineNode
from kailash.nodes.data import QueryRouterNode

# Create fully configured production pool
pool = WorkflowConnectionPool(
    name="production_pool",
    database_type="postgresql",
    host="db.production.internal",
    port=5432,
    database="main_db",
    user="app_user",
    password="secure_password",

    # Connection limits
    min_connections=10,
    max_connections=100,

    # Phase 1: Core features
    health_threshold=70,
    pre_warm=True,

    # Phase 2: Intelligence
    adaptive_sizing=True,
    enable_query_routing=True,

    # Phase 3: Production hardening
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=60,
    circuit_breaker_error_rate=0.5,
    metrics_retention_minutes=60,
    enable_pipelining=True,
    pipeline_batch_size=200,
    enable_monitoring=True,
    monitoring_port=8080
)

# Initialize pool
await pool.process({"operation": "initialize"})

# Create router for intelligent query routing
router = QueryRouterNode(
    name="production_router",
    connection_pool="production_pool",
    enable_read_write_split=True,
    cache_size=1000,
    pattern_learning=True
)

# Create pipeline for bulk operations
pipeline = QueryPipelineNode(
    name="bulk_pipeline",
    connection_pool="production_pool",
    batch_size=200,
    strategy="best_effort"
)

# Start monitoring
await pool.process({"operation": "start_monitoring"})

# Use in production
try:
    # Normal queries through router
    result = await router.process({
        "query": "SELECT * FROM users WHERE active = true",
        "operation": "execute"
    })

    # Bulk operations through pipeline
    for record in bulk_data:
        await pipeline.add_query(
            "INSERT INTO events VALUES ($1, $2, $3)",
            [record.id, record.type, record.data]
        )
    await pipeline.flush()

except CircuitBreakerError:
    # Handle database unavailability
    logger.error("Database circuit breaker open!")
    # Use cache or return degraded response
```

## Monitoring Production Health

```python
# Regular health check
async def monitor_pool_health(pool):
    while True:
        status = await pool.process({
            "operation": "get_comprehensive_status"
        })

        # Check circuit breaker
        if status["circuit_breaker"]["state"] != "closed":
            alert("Circuit breaker is open!")

        # Check error rate
        if status["error_rate"] > 0.05:
            alert(f"High error rate: {status['error_rate']:.2%}")

        # Check pool saturation
        if status["utilization_rate"] > 0.9:
            alert("Pool near saturation!")

        # Check query latency
        p95_latency = status["detailed_metrics"]["histograms"]["query_execution_ms"]["p95"]
        if p95_latency > 1000:
            alert(f"Slow queries detected: P95={p95_latency}ms")

        await asyncio.sleep(60)  # Check every minute
```

## Best Practices

1. **Circuit Breaker Tuning**
   - Start with default settings
   - Adjust based on your SLAs
   - Monitor state transitions

2. **Metrics Collection**
   - Use appropriate retention periods
   - Export to your monitoring system
   - Set up alerts for key metrics

3. **Query Pipelining**
   - Use for bulk operations only
   - Choose appropriate strategy
   - Monitor memory usage

4. **Dashboard Usage**
   - Don't expose to internet
   - Use in development and staging
   - Production: export metrics instead

## Troubleshooting

### Circuit Breaker Opens Frequently
- Increase failure threshold
- Check database health
- Review timeout settings

### High Memory Usage
- Reduce pipeline batch size
- Decrease metrics retention
- Check for query result size

### Dashboard Not Updating
- Check WebSocket connection
- Verify pool is active
- Check browser console

## Next Steps

- Set up Prometheus/Grafana for production monitoring
- Configure alerts based on your SLAs
- Test circuit breaker behavior in staging
- Benchmark pipeline performance with your workload
