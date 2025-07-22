# Query Pipeline Guide

## Overview
Query pipelining dramatically improves database throughput by batching multiple queries together, reducing network round-trips and connection overhead. Perfect for bulk operations, ETL pipelines, and high-volume data processing.

## Quick Start

### Basic Pipeline Setup
```python
from kailash.nodes.data import QueryPipelineNode

# Create pipeline for bulk operations
pipeline = QueryPipelineNode(
    name="data_pipeline",
    connection_pool="my_pool",
    batch_size=100,          # Batch up to 100 queries
    flush_interval=0.1,      # Auto-flush every 100ms
    strategy="best_effort"   # Continue on errors
)

# Add queries - they're automatically batched
for user_data in users:
    await pipeline.add_query(
        "INSERT INTO users (name, email) VALUES ($1, $2)",
        [user_data['name'], user_data['email']]
    )

# Force flush and get results
results = await pipeline.flush()
```

## Execution Strategies

### 1. SEQUENTIAL (Order Preserving)
```python
pipeline = QueryPipelineNode(
    strategy="sequential"  # Execute in order, stop on error
)

# Use for dependent operations
await pipeline.add_query("INSERT INTO orders ...")
await pipeline.add_query("UPDATE inventory ...")  # Depends on order
await pipeline.add_query("INSERT INTO order_items ...")
```

### 2. PARALLEL (Maximum Throughput)
```python
pipeline = QueryPipelineNode(
    strategy="parallel"  # Execute concurrently
)

# Use for independent operations
await pipeline.add_query("UPDATE users SET last_seen = NOW() WHERE id = 1")
await pipeline.add_query("UPDATE users SET last_seen = NOW() WHERE id = 2")
await pipeline.add_query("UPDATE users SET last_seen = NOW() WHERE id = 3")
```

### 3. TRANSACTIONAL (All or Nothing)
```python
pipeline = QueryPipelineNode(
    strategy="transactional"  # Single transaction
)

# Use for atomic operations
await pipeline.add_query("UPDATE accounts SET balance = balance - 100 WHERE id = 1")
await pipeline.add_query("UPDATE accounts SET balance = balance + 100 WHERE id = 2")
await pipeline.add_query("INSERT INTO transfers ...")
```

### 4. BEST_EFFORT (Maximum Completion)
```python
pipeline = QueryPipelineNode(
    strategy="best_effort"  # Continue despite failures
)

# Use for non-critical bulk operations
for record in large_dataset:
    await pipeline.add_query(
        "INSERT INTO analytics_events ...",
        record
    )
```

## Performance Optimization

### Batch Size Tuning
```python
# High-throughput bulk loading
bulk_pipeline = QueryPipelineNode(
    batch_size=500,        # Large batches
    flush_interval=1.0     # Flush every second
)

# Low-latency operations
realtime_pipeline = QueryPipelineNode(
    batch_size=10,         # Small batches
    flush_interval=0.01    # Flush every 10ms
)

# Adaptive batching
adaptive_pipeline = QueryPipelineNode(
    batch_size=100,
    flush_interval=0.1,
    enable_optimization=True  # Auto-optimize batch size
)
```

### Query Optimization
The pipeline automatically optimizes queries:

1. **Deduplication**: Removes duplicate queries
2. **Reordering**: Groups reads before writes
3. **Merging**: Combines compatible operations

```python
# These queries will be optimized
await pipeline.add_query("SELECT * FROM users WHERE id = 1", [])
await pipeline.add_query("SELECT * FROM users WHERE id = 1", [])  # Duplicate removed
await pipeline.add_query("INSERT INTO logs ...", [...])
await pipeline.add_query("SELECT * FROM products ...", [])  # Reordered before INSERT
```

## Common Patterns

### Bulk Insert with Progress
```python
async def bulk_insert_with_progress(records, callback=None):
    pipeline = QueryPipelineNode(
        batch_size=1000,
        strategy="best_effort"
    )

    total = len(records)
    processed = 0

    for i, record in enumerate(records):
        query_id = await pipeline.add_query(
            "INSERT INTO records (data) VALUES ($1)",
            [json.dumps(record)]
        )

        # Check if batch is about to flush
        if (i + 1) % 1000 == 0:
            results = await pipeline.flush()
            processed += len(results)

            if callback:
                callback(processed, total)

    # Final flush
    results = await pipeline.flush()
    processed += len(results)

    return processed
```

### ETL Pipeline
```python
async def etl_pipeline(source_table, target_table, transform_func):
    # Read pipeline
    read_pipeline = QueryPipelineNode(
        batch_size=500,
        strategy="parallel"
    )

    # Write pipeline
    write_pipeline = QueryPipelineNode(
        batch_size=1000,
        strategy="best_effort"
    )

    # Extract
    offset = 0
    while True:
        await read_pipeline.add_query(
            f"SELECT * FROM {source_table} LIMIT 500 OFFSET $1",
            [offset]
        )

        results = await read_pipeline.flush()
        if not results[0].result:
            break

        # Transform and Load
        for row in results[0].result:
            transformed = transform_func(row)
            await write_pipeline.add_query(
                f"INSERT INTO {target_table} VALUES ($1)",
                [transformed]
            )

        offset += 500

    # Final flush
    await write_pipeline.flush()
```

### Cached Bulk Operations
```python
class CachedPipeline:
    def __init__(self, pipeline, cache):
        self.pipeline = pipeline
        self.cache = cache
        self.pending = {}

    async def get_or_fetch(self, key, query, params):
        # Check cache first
        cached = await self.cache.get(key)
        if cached:
            return cached

        # Queue for pipeline
        query_id = await self.pipeline.add_query(query, params)
        self.pending[query_id] = key

        return None  # Will be available after flush

    async def flush_and_cache(self):
        results = await self.pipeline.flush()

        for result in results:
            if result.success and result.query_id in self.pending:
                key = self.pending[result.query_id]
                await self.cache.set(key, result.result)

        self.pending.clear()
        return results
```

## Error Handling

### Handle Partial Failures
```python
results = await pipeline.flush()

successful = []
failed = []

for result in results:
    if result.success:
        successful.append(result)
    else:
        failed.append({
            'query_id': result.query_id,
            'error': str(result.error),
            'retry_count': result.retry_count
        })

print(f"Success: {len(successful)}, Failed: {len(failed)}")

# Retry failed queries
if failed and strategy == "best_effort":
    retry_pipeline = QueryPipelineNode(batch_size=len(failed))
    for fail in failed:
        # Re-add with exponential backoff
        await asyncio.sleep(2 ** fail['retry_count'])
        await retry_pipeline.add_query(...)
```

### Transaction Rollback
```python
try:
    # Transactional pipeline
    results = await transactional_pipeline.flush()

    # Check all succeeded
    if not all(r.success for r in results):
        raise Exception("Transaction failed")

except Exception as e:
    # Transaction automatically rolled back
    logger.error(f"Transaction failed: {e}")

    # Implement compensation logic
    await compensate_failed_transaction(results)
```

## Monitoring and Metrics

### Pipeline Statistics
```python
stats = pipeline.get_status()

print(f"Queries queued: {stats['queue_size']}")
print(f"Total processed: {stats['total_queries']}")
print(f"Total batches: {stats['total_batches']}")
print(f"Success rate: {stats['success_rate']:.2%}")
print(f"Avg batch size: {stats['avg_batch_size']}")
print(f"Avg execution time: {stats['avg_execution_time_ms']}ms")
```

### Performance Tracking
```python
# Track throughput
start_time = time.time()
initial_count = pipeline.get_status()['total_queries']

# ... run operations ...

elapsed = time.time() - start_time
final_count = pipeline.get_status()['total_queries']
qps = (final_count - initial_count) / elapsed

print(f"Throughput: {qps:.1f} queries/second")
```

## Best Practices

### 1. Choose the Right Strategy
- **SEQUENTIAL**: When order matters
- **PARALLEL**: For independent operations
- **TRANSACTIONAL**: For atomic consistency
- **BEST_EFFORT**: For analytics/logging

### 2. Tune Batch Sizes
```python
# CPU-bound queries: smaller batches
cpu_pipeline = QueryPipelineNode(batch_size=50)

# I/O-bound queries: larger batches
io_pipeline = QueryPipelineNode(batch_size=500)

# Mixed workload: adaptive
mixed_pipeline = QueryPipelineNode(
    batch_size=100,
    enable_optimization=True
)
```

### 3. Handle Back-Pressure
```python
# Monitor queue depth
while has_more_data():
    stats = pipeline.get_status()

    # Wait if queue is too deep
    if stats['queue_size'] > 10000:
        await pipeline.flush()
        await asyncio.sleep(0.1)

    await pipeline.add_query(...)
```

### 4. Use Callbacks for Long Operations
```python
# Add callback for result handling
async def handle_result(result):
    if result.success:
        await update_progress(result.query_id)
    else:
        await log_error(result.error)

await pipeline.add_query(
    query="INSERT INTO large_table ...",
    parameters=[...],
    callback_id="import_123"
)

# Process results with callbacks
results = await pipeline.flush()
for result in results:
    if result.callback_id:
        await handle_result(result)
```

## Performance Benchmarks

Typical improvements with pipelining:

| Operation | Without Pipeline | With Pipeline | Improvement |
|-----------|-----------------|---------------|-------------|
| Bulk Insert (10k rows) | 45s | 3s | 15x |
| Batch Update (5k rows) | 23s | 2s | 11x |
| Multi-Get (1k queries) | 12s | 1.5s | 8x |
| ETL Pipeline (100k rows) | 10min | 45s | 13x |

## Troubleshooting

### Queries Not Executing
- Check if flush interval elapsed
- Manually call `flush()`
- Verify batch size not too large

### Memory Usage
- Reduce batch size
- Flush more frequently
- Enable streaming mode

### Deadlocks
- Use SEQUENTIAL strategy
- Add proper ordering
- Reduce parallelism

## Related Guides
- [Connection Pool Guide](./connection-pool-guide.md)
- [Circuit Breaker Guide](./circuit-breaker-guide.md)
- [Performance Tuning](./performance-tuning-guide.md)
