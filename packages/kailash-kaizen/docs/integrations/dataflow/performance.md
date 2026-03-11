# Kaizen-DataFlow Performance Guide

Comprehensive guide to optimizing performance for combined AI-database workflows.

## Performance Characteristics

### Query Performance

| Operation | Target | Typical | Notes |
|-----------|--------|---------|-------|
| **NL to SQL** | <500ms | 300-500ms | Includes LLM call + SQL generation |
| **Direct Queries** | <50ms | 10-50ms | Database network latency |
| **Cached Queries** | <5ms | 1-5ms | In-memory cache hit |
| **Complex Joins** | <200ms | 100-200ms | Depends on table size |

### Bulk Operations

| Operation | Target | Typical | Notes |
|-----------|--------|---------|-------|
| **Transformation** | >1,000 rec/sec | 1,000-5,000 rec/sec | AI transformation overhead |
| **Batch Insert** | >5,000 rec/sec | 5,000-10,000 rec/sec | Optimized batching |
| **Training Data Fetch** | >10,000 rec/sec | 10,000-50,000 rec/sec | Bulk read operations |
| **Batch Update** | >3,000 rec/sec | 3,000-8,000 rec/sec | Update overhead |

### ML Operations

| Operation | Target | Typical | Notes |
|-----------|--------|---------|-------|
| **Model Training** | <60s | 10-60s | Depends on data size |
| **Inference** | <100ms | 50-100ms | Per prediction |
| **Batch Inference** | >100 pred/sec | 100-500 pred/sec | Batched predictions |
| **Pipeline Orchestration** | <5min | 1-5min | Complete workflow |

## Optimization Strategies

### 1. Connection Pooling

Reuse database connections across multiple operations.

**Configuration:**

```python
from kaizen.integrations.dataflow import DataFlowConnection

# Configure connection pool
connection = DataFlowConnection(
    db=db,
    pool_size=10,  # Max concurrent connections
    lazy_init=True  # Delay initialization until needed
)

# Multiple agents share the pool
nl_agent = NLToSQLAgent(config=config, db=db)
transform_agent = DataTransformAgent(config=config, db=db)
quality_agent = DataQualityAgent(config=config, db=db)

# Monitor pool usage
stats = connection.get_pool_stats()
print(f"Pool hit rate: {stats['hit_rate']:.2f}%")
print(f"Active connections: {stats['in_use']}/{stats['max_size']}")
```

**Best Practices:**
- Use pool size = 2× expected concurrent operations
- Monitor hit rate (target: >90%)
- Close connections when done: `connection.close()`

**Performance Impact:**
- ✅ 50-70% reduction in connection overhead
- ✅ Handles 3-5× more concurrent agents
- ✅ Prevents connection exhaustion

### 2. Query Caching

Cache frequently accessed query results with TTL.

**Configuration:**

```python
from kaizen.integrations.dataflow import QueryCache

# Setup cache
cache = QueryCache(
    max_size=100,      # Max cached queries
    ttl_seconds=300    # 5-minute expiration
)

# Use with agents
def cached_query(table, filter):
    # Generate cache key
    key = QueryCache.create_key(table, filter)

    # Check cache
    cached_result = cache.get(key)
    if cached_result:
        return cached_result

    # Execute query
    result = agent.query(...)

    # Cache result
    cache.set(key, result)
    return result

# Monitor cache performance
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2f}%")
print(f"Cache size: {stats['size']}/{stats['max_size']}")
```

**Best Practices:**
- Cache read-heavy queries only
- Set TTL based on data freshness needs
- Invalidate on writes: `cache.invalidate(pattern="users_")`
- Monitor hit rate (target: >70%)

**Performance Impact:**
- ✅ 100-200× faster for cache hits
- ✅ Reduces database load by 60-80%
- ✅ Improves response time for repeated queries

### 3. Batch Operations

Process data in batches for optimal throughput.

**Configuration:**

```python
from kaizen.integrations.dataflow import BatchOptimizer, BatchConfig

# Configure batch optimizer
config = BatchConfig(
    batch_size=1000,        # Records per batch
    max_retries=3,          # Retry failed batches
    timeout_seconds=30,     # Per-batch timeout
    continue_on_error=True  # Keep going on failures
)

optimizer = BatchOptimizer(config)

# Batch insert
result = optimizer.batch_insert(
    data=large_dataset,
    insert_fn=lambda batch: transform_agent.transform_data(
        source_data=batch,
        target_table="CleanData"
    ),
    progress_callback=lambda current, total:
        print(f"Progress: {current}/{total}")
)

print(f"Throughput: {result['throughput']:.2f} rec/sec")
print(f"Success rate: {result['success_rate']:.2f}%")
```

**Best Practices:**
- Batch size 500-2000 for most workloads
- Larger batches (5000+) for simple transformations
- Smaller batches (100-500) for complex AI operations
- Monitor throughput and adjust

**Performance Impact:**
- ✅ 10-50× faster than individual operations
- ✅ Reduces transaction overhead
- ✅ Better database resource utilization

### 4. Async Execution

Use async agents for concurrent operations.

**Configuration:**

```python
import asyncio
from kaizen.integrations.dataflow import NLToSQLAgent

async def concurrent_queries():
    """Execute multiple queries concurrently."""

    # Create agents
    agents = [
        NLToSQLAgent(config=config, db=db)
        for _ in range(5)
    ]

    # Execute concurrently
    queries = [
        "Show me sales from last month",
        "Find top customers by revenue",
        "List products by category",
        "Get recent orders",
        "Show inventory status"
    ]

    # Run in parallel
    results = await asyncio.gather(*[
        agent.query(query)
        for agent, query in zip(agents, queries)
    ])

    return results

# Run concurrent operations
results = asyncio.run(concurrent_queries())
```

**Best Practices:**
- Use for I/O-bound operations (queries, API calls)
- Limit concurrency to avoid overwhelming database
- Use connection pooling with async operations
- Monitor concurrent connection usage

**Performance Impact:**
- ✅ 5-10× faster for multiple independent operations
- ✅ Better resource utilization
- ✅ Reduced overall latency

## Performance Monitoring

### Built-in Metrics

**Connection Pool Metrics:**

```python
stats = connection.get_pool_stats()
# {
#     'connections': 7,           # Active connections
#     'max_size': 10,            # Pool limit
#     'in_use': 5,               # Currently in use
#     'total_requests': 1247,    # Total requests
#     'cache_hits': 1180,        # Cache hits
#     'hit_rate': 94.63          # Hit rate %
# }
```

**Cache Metrics:**

```python
stats = cache.get_stats()
# {
#     'size': 73,                # Cached entries
#     'max_size': 100,           # Cache limit
#     'hits': 892,               # Cache hits
#     'misses': 156,             # Cache misses
#     'hit_rate': 85.11,         # Hit rate %
#     'evictions': 12,           # LRU evictions
#     'expirations': 45          # TTL expirations
# }
```

**Batch Optimizer Metrics:**

```python
stats = optimizer.get_stats()
# {
#     'total_operations': 15,    # Batch operations
#     'total_records': 45000,    # Records processed
#     'total_duration': 18.5,    # Total time (sec)
#     'avg_throughput': 2432.43, # Avg rec/sec
#     'retry_count': 3,          # Retries attempted
#     'error_count': 1           # Failed batches
# }
```

### Custom Performance Tracking

```python
import time

class PerformanceMonitor:
    """Track operation performance."""

    def __init__(self):
        self.metrics = []

    def track(self, operation_name):
        """Context manager for tracking operations."""
        class Tracker:
            def __init__(self, name, metrics):
                self.name = name
                self.metrics = metrics
                self.start = None

            def __enter__(self):
                self.start = time.time()
                return self

            def __exit__(self, *args):
                duration = time.time() - self.start
                self.metrics.append({
                    'operation': self.name,
                    'duration': duration
                })

        return Tracker(operation_name, self.metrics)

    def report(self):
        """Generate performance report."""
        if not self.metrics:
            return "No metrics recorded"

        operations = {}
        for metric in self.metrics:
            op = metric['operation']
            if op not in operations:
                operations[op] = []
            operations[op].append(metric['duration'])

        report = []
        for op, durations in operations.items():
            avg = sum(durations) / len(durations)
            min_d = min(durations)
            max_d = max(durations)
            report.append(
                f"{op}: avg={avg:.2f}s, min={min_d:.2f}s, max={max_d:.2f}s"
            )

        return "\n".join(report)

# Usage
monitor = PerformanceMonitor()

with monitor.track("NL Query"):
    result = nl_agent.query("Show me all users")

with monitor.track("Transformation"):
    transform_agent.transform_data(...)

print(monitor.report())
```

## Best Practices Summary

### For Read-Heavy Workloads
1. ✅ Enable query caching (TTL: 5-15 minutes)
2. ✅ Use connection pooling (pool_size: 5-10)
3. ✅ Cache frequently accessed queries
4. ✅ Monitor cache hit rate (target: >70%)

### For Write-Heavy Workloads
1. ✅ Use batch operations (batch_size: 1000-5000)
2. ✅ Increase connection pool (pool_size: 10-20)
3. ✅ Enable async execution for concurrent writes
4. ✅ Monitor throughput (target: >1000 rec/sec)

### For Mixed Workloads
1. ✅ Combine caching + batching
2. ✅ Moderate pool size (pool_size: 10)
3. ✅ Use async for independent operations
4. ✅ Monitor both hit rate and throughput

### For Long-Running Pipelines
1. ✅ Enable progress callbacks
2. ✅ Configure retry logic (max_retries: 3-5)
3. ✅ Use continue_on_error for resilience
4. ✅ Monitor memory usage over time

## Troubleshooting Performance Issues

### Slow Queries
**Symptom:** Queries taking >1s

**Solutions:**
1. Check query cache hit rate (should be >70%)
2. Optimize database indexes
3. Reduce result set size (use filters)
4. Enable query caching

### Low Throughput
**Symptom:** Batch operations <500 rec/sec

**Solutions:**
1. Increase batch size (try 2000-5000)
2. Check network latency to database
3. Enable connection pooling
4. Use async execution

### Connection Exhaustion
**Symptom:** "Too many connections" errors

**Solutions:**
1. Increase pool_size
2. Close unused connections: `connection.close()`
3. Reduce concurrent operations
4. Monitor pool usage

### Memory Issues
**Symptom:** High memory usage over time

**Solutions:**
1. Reduce cache max_size
2. Lower batch_size for large records
3. Clear cache periodically: `cache.clear()`
4. Monitor cache evictions

## Performance Benchmarks

Based on Phase 4 testing with real infrastructure:

| Scenario | Records | Time | Throughput | Notes |
|----------|---------|------|------------|-------|
| **Simple Insert** | 10,000 | 2.1s | 4,762 rec/sec | No transformation |
| **AI Transform** | 10,000 | 8.5s | 1,176 rec/sec | With LLM calls |
| **Cached Query** | 1,000 | 0.003s | N/A | In-memory cache |
| **Uncached Query** | 1,000 | 0.12s | N/A | Database query |
| **Model Training** | 50,000 | 45s | N/A | Full pipeline |
| **Batch Inference** | 1,000 | 12s | 83 pred/sec | With DB context |

## Next Steps

1. **Implement Optimizations** - Add caching, batching, pooling to your workflows
2. **Monitor Performance** - Track metrics and identify bottlenecks
3. **Tune Configuration** - Adjust based on your workload
4. **Test at Scale** - Validate with production data volumes

## Related Documentation

- [Best Practices Guide](best-practices.md)
- [API Reference](api-reference.md)
- [Complete Pipeline Example](../../examples/6-dataflow-integration/complete-pipeline/)
