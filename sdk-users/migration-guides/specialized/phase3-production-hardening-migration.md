# Migration Guide: Phase 3 Production Hardening

This guide helps you upgrade to Phase 3 production features including circuit breakers, comprehensive metrics, query pipelining, and monitoring dashboards.

## Overview

Phase 3 adds critical production features:
- **Circuit Breaker**: Automatic failure protection
- **Comprehensive Metrics**: Deep observability
- **Query Pipelining**: Batch execution performance
- **Monitoring Dashboard**: Real-time visualization

## Prerequisites

- Kailash SDK with Phase 1 & 2 features
- PostgreSQL 12+ (for pipeline optimization)
- Python 3.8+ (for async features)
- Optional: Prometheus/Grafana for metrics

## Migration Approaches

### Approach 1: Enable All Features (Recommended)

Best for new deployments or major upgrades.

```python
# Before: Basic pool
pool = WorkflowConnectionPool(
    name="app_pool",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    min_connections=5,
    max_connections=20
)

# After: Full Phase 3 features
pool = WorkflowConnectionPool(
    name="app_pool",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    min_connections=5,
    max_connections=20,

    # Phase 2 features (if not already enabled)
    adaptive_sizing=True,
    enable_query_routing=True,

    # Phase 3 features
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=60,
    circuit_breaker_error_rate=0.5,
    metrics_retention_minutes=60,
    enable_pipelining=True,
    pipeline_batch_size=100,
    enable_monitoring=True,
    monitoring_port=8080
)
```

### Approach 2: Gradual Feature Adoption

Enable features one at a time to minimize risk.

#### Step 1: Circuit Breaker Only
```python
pool = WorkflowConnectionPool(
    # ... existing config ...
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=60
)

# Test in staging for a week
# Monitor circuit breaker states
# Adjust thresholds based on your workload
```

#### Step 2: Add Metrics Collection
```python
pool = WorkflowConnectionPool(
    # ... existing config ...
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=60,
    metrics_retention_minutes=60  # Add metrics
)

# Export to your monitoring system
# Set up dashboards and alerts
# Baseline your normal metrics
```

#### Step 3: Enable Pipelining
```python
pool = WorkflowConnectionPool(
    # ... existing config ...
    enable_pipelining=True,
    pipeline_batch_size=100
)

# Identify bulk operations in your code
# Convert to use QueryPipelineNode
# Measure performance improvement
```

#### Step 4: Add Monitoring Dashboard
```python
pool = WorkflowConnectionPool(
    # ... existing config ...
    enable_monitoring=True,
    monitoring_port=8080
)

# Use in development/staging first
# Production: rely on exported metrics
```

## Code Migration Patterns

### Pattern 1: Bulk Insert Migration

**Before: Individual Inserts**
```python
# Slow - one query at a time
async def import_records(pool, records):
    for record in records:
        conn = await pool.acquire()
        try:
            await pool.execute({
                "connection_id": conn["connection_id"],
                "query": "INSERT INTO events (type, data) VALUES ($1, $2)",
                "params": [record.type, record.data]
            })
        finally:
            await pool.release(conn["connection_id"])
```

**After: Pipelined Inserts**
```python
# Fast - batched execution
async def import_records(pool, records):
    pipeline = QueryPipelineNode(
        name="import_pipeline",
        connection_pool=pool.metadata.name,
        batch_size=200,
        strategy="best_effort"
    )

    for record in records:
        await pipeline.add_query(
            "INSERT INTO events (type, data) VALUES ($1, $2)",
            [record.type, record.data]
        )

    results = await pipeline.flush()
    success_count = sum(1 for r in results if r.success)
    logger.info(f"Imported {success_count}/{len(records)} records")
```

### Pattern 2: Circuit Breaker Error Handling

**Before: Unprotected Queries**
```python
async def get_user_data(pool, user_id):
    try:
        result = await router.process({
            "query": "SELECT * FROM users WHERE id = $1",
            "parameters": [user_id]
        })
        return result["data"][0]
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise
```

**After: Circuit Breaker Aware**
```python
from kailash.core.resilience import CircuitBreakerError

async def get_user_data(pool, user_id):
    try:
        result = await router.process({
            "query": "SELECT * FROM users WHERE id = $1",
            "parameters": [user_id]
        })
        return result["data"][0]
    except CircuitBreakerError:
        # Database is down - use cache
        logger.warning("Using cached data - circuit breaker open")
        return get_from_cache(f"user:{user_id}")
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise
```

### Pattern 3: Metrics Integration

**Before: No Metrics**
```python
async def process_batch(pool, items):
    for item in items:
        await process_item(pool, item)
```

**After: With Metrics**
```python
async def process_batch(pool, items):
    # Get metrics before
    status_before = await pool.process({
        "operation": "get_comprehensive_status"
    })
    queries_before = status_before["detailed_metrics"]["counters"]["queries_total"]

    # Process items
    start_time = time.time()
    for item in items:
        await process_item(pool, item)
    duration = time.time() - start_time

    # Get metrics after
    status_after = await pool.process({
        "operation": "get_comprehensive_status"
    })
    queries_after = status_after["detailed_metrics"]["counters"]["queries_total"]

    # Log performance
    queries_executed = queries_after - queries_before
    qps = queries_executed / duration
    logger.info(f"Processed {len(items)} items: {queries_executed} queries at {qps:.1f} qps")
```

## Configuration Tuning

### Circuit Breaker Tuning

Start conservative and relax based on experience:

```python
# Week 1: Conservative
circuit_breaker_failure_threshold=3
circuit_breaker_recovery_timeout=120

# Week 2: Balanced (if stable)
circuit_breaker_failure_threshold=5
circuit_breaker_recovery_timeout=60

# Week 3: Optimized for your workload
circuit_breaker_failure_threshold=8
circuit_breaker_recovery_timeout=45
```

### Pipeline Batch Sizes

Optimal batch size depends on query type:

```python
# Small, simple queries (logs, events)
pipeline_batch_size=500

# Medium complexity (user data)
pipeline_batch_size=200

# Complex queries (joins, aggregations)
pipeline_batch_size=50

# Transactional updates
pipeline_batch_size=20
```

### Metrics Retention

Balance detail vs memory usage:

```python
# Development: Keep more detail
metrics_retention_minutes=120  # 2 hours

# Production: Optimize memory
metrics_retention_minutes=30   # 30 minutes

# High-traffic: Reduce further
metrics_retention_minutes=15   # 15 minutes
```

## Monitoring Setup

### Prometheus Configuration

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'kailash_pools'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:9090']
```

### Export Endpoint

```python
from aiohttp import web

async def metrics_endpoint(request):
    pool = request.app["pool"]
    result = await pool.process({"operation": "export_metrics"})
    return web.Response(
        text=result["prometheus_metrics"],
        content_type="text/plain"
    )

app = web.Application()
app["pool"] = pool
app.router.add_get("/metrics", metrics_endpoint)
```

### Grafana Dashboard

Import the provided dashboard JSON:

```json
{
  "dashboard": {
    "title": "Kailash Connection Pool",
    "panels": [
      {
        "title": "Query Rate",
        "targets": [{
          "expr": "rate(connection_pool_queries_total[5m])"
        }]
      },
      {
        "title": "Error Rate",
        "targets": [{
          "expr": "rate(connection_pool_query_errors_total[5m]) / rate(connection_pool_queries_total[5m])"
        }]
      },
      {
        "title": "Circuit Breaker State",
        "targets": [{
          "expr": "connection_pool_circuit_breaker_state"
        }]
      }
    ]
  }
}
```

## Rollback Plan

If issues arise, you can disable features individually:

```python
# Disable circuit breaker
circuit_breaker_failure_threshold=999999  # Never open

# Disable metrics (set retention to 0)
metrics_retention_minutes=0

# Disable pipelining
enable_pipelining=False

# Disable monitoring
enable_monitoring=False
```

## Testing Checklist

Before production deployment:

- [ ] Circuit breaker tested with database failure simulation
- [ ] Metrics exported successfully to monitoring system
- [ ] Pipeline performance validated with your query patterns
- [ ] Dashboard accessible (if using)
- [ ] Error handling updated for CircuitBreakerError
- [ ] Batch operations converted to use pipelining
- [ ] Monitoring alerts configured
- [ ] Rollback plan tested

## Common Issues

### Issue: Circuit breaker opens immediately
**Solution**: Increase failure threshold or check database health

### Issue: High memory usage from metrics
**Solution**: Reduce retention period or metrics collection frequency

### Issue: Pipeline queries failing
**Solution**: Check query syntax and parameter binding, reduce batch size

### Issue: Dashboard not loading
**Solution**: Check port availability and WebSocket connectivity

## Performance Expectations

After migration, expect:

- **Query throughput**: 2-10x improvement with pipelining
- **Error recovery**: 10-30 second recovery vs minutes
- **Observability**: Complete visibility into pool behavior
- **Resource usage**: 20-30% better utilization

## Next Steps

1. Enable features in staging environment
2. Run load tests with failure scenarios
3. Establish baseline metrics
4. Create runbooks for circuit breaker events
5. Train team on new monitoring capabilities
