# Schema Cache Guide

## Table of Contents
1. [What is Schema Cache?](#what-is-schema-cache)
2. [How It Works](#how-it-works)
3. [Configuration](#configuration)
4. [Basic Usage](#basic-usage)
5. [Cache Methods (Advanced)](#cache-methods-advanced)
6. [Thread Safety](#thread-safety)
7. [When to Clear Cache](#when-to-clear-cache)
8. [Best Practices](#best-practices)
9. [Performance Metrics](#performance-metrics)
10. [Troubleshooting](#troubleshooting)

## What is Schema Cache?

The schema cache is a thread-safe table existence cache that eliminates redundant migration checks, providing **91-99% performance improvement** for multi-operation workflows.

### Key Features

- **Thread-safe**: RLock protection for multi-threaded applications (FastAPI, Flask, Gunicorn)
- **Configurable**: TTL, size limits, and validation options
- **Automatic invalidation**: Cache clears on schema changes
- **Low overhead**: <1KB memory per cached table
- **Enabled by default**: Transparent performance boost (v0.7.3+)

### Performance Characteristics

| Metric | First Check (Cache Miss) | Subsequent Checks (Cache Hit) | Improvement |
|--------|---------------------------|-------------------------------|-------------|
| Time | ~1500ms | ~1ms | 99% faster |
| Database queries | 1-3 queries | 0 queries | 100% reduction |
| Memory overhead | - | <1KB per table | Negligible |

**Real-world example** (10-operation workflow):
- **Without cache**: 10 × 1500ms = 15 seconds
- **With cache**: 1500ms + (9 × 1ms) = 1.5 seconds
- **Result**: **90% faster workflow execution**

## How It Works

### Cache Lifecycle

1. **First operation** (cache miss):
   - DataFlow checks if table exists in database (~1500ms)
   - Result cached in memory
   - Operation proceeds

2. **Subsequent operations** (cache hit):
   - DataFlow checks cache first (<1ms)
   - Table existence confirmed instantly
   - No database query needed

3. **Cache invalidation**:
   - Automatic: On schema modifications (migrations, DROP TABLE)
   - Manual: `db._schema_cache.clear()` or `clear_table()`

### What Gets Cached

- **Table existence**: Whether table has been created
- **Database URL**: Keyed by `(model_name, database_url)`
- **Timestamp**: When cache entry was created
- **State**: Whether table schema is ensured

## Configuration

### Default Configuration (Recommended)

```python
from dataflow import DataFlow

# Default: Cache enabled, no TTL, max 10,000 tables
db = DataFlow("postgresql://localhost/mydb")

await db.initialize()
# Cache automatically enabled
```

### Custom Configuration

```python
db = DataFlow(
    "postgresql://localhost/mydb",
    schema_cache_enabled=True,        # Enable/disable cache
    schema_cache_ttl=300,              # TTL in seconds (None = no expiration)
    schema_cache_max_size=10000,      # Max cached tables
    schema_cache_validation=False,    # Schema checksum validation
)
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `schema_cache_enabled` | bool | `True` | Enable/disable caching |
| `schema_cache_ttl` | int \| None | `None` | Cache entry expiration (seconds) |
| `schema_cache_max_size` | int | `10000` | Maximum cached tables |
| `schema_cache_validation` | bool | `False` | Enable schema checksum validation |

### When to Use Custom Configuration

**Enable TTL** for:
- ✅ Long-running applications (days/weeks)
- ✅ Dynamic schemas (frequent CREATE/DROP TABLE)
- ✅ Development environments

**Increase max_size** for:
- ✅ Large number of models (>1000)
- ✅ Multi-tenant applications with many databases

**Enable validation** for:
- ✅ Critical production systems
- ✅ Manual schema modifications possible
- ⚠️ Adds ~10ms overhead per check

**Disable cache** for:
- ✅ Testing/debugging schema issues
- ✅ Temporary troubleshooting
- ❌ **Not recommended** for production

## Basic Usage

### Automatic Usage (No Code Changes)

The cache works transparently - **no code changes needed**:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str

await db.initialize()

# First operation: Cache miss (~1500ms)
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
# Database check: ~1500ms, result cached

# Subsequent operations: Cache hit (~1ms)
workflow2 = WorkflowBuilder()
workflow2.add_node("UserCreateNode", "create2", {
    "id": "user-2",
    "name": "Bob"
})

results2, _ = runtime.execute(workflow2.build())
# Cache check: ~1ms (99% faster!)
```

### Multi-Operation Workflow Performance

```python
# Workflow with 10 operations
workflow = WorkflowBuilder()

for i in range(10):
    workflow.add_node("UserCreateNode", f"create_{i}", {
        "id": f"user-{i}",
        "name": f"User {i}"
    })

# Without cache: 10 × 1500ms = 15 seconds
# With cache: 1500ms + (9 × 1ms) = ~1.5 seconds
# 90% performance improvement!

results, _ = runtime.execute(workflow.build())
```

## Cache Methods (Advanced)

### Get Cache Performance Statistics

```python
# Get cache hit/miss statistics
metrics = db._schema_cache.get_metrics()

print(f"Cache hits: {metrics['hits']}")
print(f"Cache misses: {metrics['misses']}")
print(f"Hit rate: {metrics['hit_rate']:.2%}")
print(f"Cached tables: {metrics['cached_tables']}")

# Example output:
# Cache hits: 847
# Cache misses: 3
# Hit rate: 99.65%
# Cached tables: 5
```

### Check if Table is Cached

```python
# Check if specific table is cached
is_cached = db._schema_cache.is_table_ensured("User", database_url)

if is_cached:
    print("Table existence is cached")
else:
    print("Table will be checked on next operation")
```

### Get All Cached Tables

```python
# Get all cached tables with their states
cached = db._schema_cache.get_cached_tables()

for key, state in cached.items():
    print(f"{key}:")
    print(f"  Ensured: {state['ensured']}")
    print(f"  Timestamp: {state['timestamp']}")

# Example output:
# ('User', 'postgresql://localhost/mydb'):
#   Ensured: True
#   Timestamp: 2025-11-03 10:15:30
# ('Order', 'postgresql://localhost/mydb'):
#   Ensured: True
#   Timestamp: 2025-11-03 10:15:31
```

### Clear Entire Cache

```python
# Clear all cache entries
db._schema_cache.clear()

print("Cache cleared - next operations will recheck database")
```

### Clear Specific Table Cache

```python
# Clear cache for specific table
db._schema_cache.clear_table("User", database_url)

print("User table cache cleared")
```

### Manually Mark Table as Ensured

```python
# Rarely needed - cache automatically manages this
db._schema_cache.mark_table_ensured("User", database_url)

# Use case: After manual schema operations outside DataFlow
```

### Cache Methods Reference

| Method | Description | Returns |
|--------|-------------|---------|
| `get_metrics()` | Get cache performance statistics | `dict` with hits, misses, hit_rate, cached_tables |
| `get_cached_tables()` | Get all cached tables with states | `dict` mapping `(model_name, url)` to state |
| `is_table_ensured(model, url)` | Check if table is cached | `bool` |
| `clear()` | Clear all cache entries | `None` |
| `clear_table(model, url)` | Clear specific table cache | `None` |
| `mark_table_ensured(model, url)` | Mark table as ensured (rarely needed) | `None` |

## Thread Safety

The schema cache is fully thread-safe for multi-threaded applications using RLock (reentrant lock).

### FastAPI Example

```python
from fastapi import FastAPI
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

app = FastAPI()

# Single DataFlow instance shared across threads
db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str

await db.initialize()

@app.post("/users")
async def create_user(user_data: dict):
    """Thread-safe: Cache protected by RLock"""
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", user_data)

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["create"]

# Multiple requests handled concurrently - cache is thread-safe
```

### Gunicorn/Multi-Worker Example

```python
# gunicorn_app.py
from dataflow import DataFlow

# Each worker process has its own cache
db = DataFlow("postgresql://localhost/mydb")

# Cache is thread-safe within each worker
# Different workers have separate cache instances
```

### Thread Safety Guarantees

- **RLock protection**: All cache operations are atomic
- **No race conditions**: Safe for concurrent access
- **Reentrant**: Same thread can acquire lock multiple times
- **Per-process**: Each process has separate cache instance

**Example concurrent operations**:

```python
from concurrent.futures import ThreadPoolExecutor

def create_user(user_id: str):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": user_id,
        "name": f"User {user_id}"
    })

    runtime = LocalRuntime()
    return runtime.execute(workflow.build())

# Safe for concurrent execution
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(create_user, f"user-{i}") for i in range(100)]
    results = [f.result() for f in futures]

# All operations safely share the same cache
```

## When to Clear Cache

### Automatic Clearing (No Action Needed)

Cache automatically clears when DataFlow performs schema operations:

```python
# Cache cleared automatically
await db.initialize()  # Tables created
await db.migrate()     # Schema modified

# Cache invalidated for modified tables
```

### Manual Clearing Required

Clear cache after **external schema modifications**:

```python
# After manual schema changes
import asyncpg

conn = await asyncpg.connect("postgresql://localhost/mydb")
await conn.execute("DROP TABLE users")  # Manual modification
await conn.close()

# Clear cache to reflect changes
db._schema_cache.clear()
```

### When to Clear

| Scenario | Action | Command |
|----------|--------|---------|
| External migrations | Clear all | `db._schema_cache.clear()` |
| Manual DDL (DROP, ALTER) | Clear affected | `db._schema_cache.clear_table("Model", url)` |
| Schema debugging | Clear all | `db._schema_cache.clear()` |
| Cache corruption suspected | Clear all | `db._schema_cache.clear()` |
| Application restart | No action | Cache empty on startup |

### Example: After External Migration

```python
# 1. Run external migration
import subprocess
subprocess.run(["alembic", "upgrade", "head"])

# 2. Clear DataFlow cache
db._schema_cache.clear()

# 3. Next operations will recheck schema
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {...})
runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
# Database checked, cache updated
```

## Best Practices

### 1. Use Default Configuration for Most Cases

```python
# ✅ BEST PRACTICE
db = DataFlow("postgresql://localhost/mydb")
# Cache enabled with sensible defaults
```

### 2. Enable TTL for Long-Running Applications

```python
# ✅ BEST PRACTICE - Long-running apps
db = DataFlow(
    "postgresql://localhost/mydb",
    schema_cache_ttl=3600  # 1 hour TTL
)

# Prevents stale cache in dynamic schemas
```

### 3. Monitor Cache Metrics in Production

```python
# ✅ BEST PRACTICE - Production monitoring
import logging

def log_cache_metrics():
    metrics = db._schema_cache.get_metrics()
    logging.info(
        f"Schema cache: {metrics['hits']} hits, "
        f"{metrics['misses']} misses, "
        f"{metrics['hit_rate']:.2%} hit rate, "
        f"{metrics['cached_tables']} tables"
    )

# Log metrics periodically
import schedule
schedule.every(1).hour.do(log_cache_metrics)
```

### 4. Clear Cache After External Changes

```python
# ✅ BEST PRACTICE
# After manual schema modifications
db._schema_cache.clear()

# After external migration tools
subprocess.run(["alembic", "upgrade", "head"])
db._schema_cache.clear()
```

### 5. Use schema_validation for Critical Systems

```python
# ✅ BEST PRACTICE - Critical production
db = DataFlow(
    "postgresql://localhost/mydb",
    schema_cache_validation=True  # Adds checksum validation
)

# Adds ~10ms overhead but ensures schema integrity
```

### 6. Don't Disable Cache in Production

```python
# ❌ BAD PRACTICE
db = DataFlow(
    "postgresql://localhost/mydb",
    schema_cache_enabled=False  # Don't do this in production!
)

# Only disable for debugging/testing
```

## Performance Metrics

### Single Operation

| Phase | Time | Description |
|-------|------|-------------|
| Cache miss | ~1500ms | First check, query database |
| Cache hit | ~1ms | Subsequent checks, use cache |

### Multi-Operation Workflow

**10-operation workflow**:
- Without cache: 10 × 1500ms = **15 seconds**
- With cache: 1500ms + (9 × 1ms) = **1.5 seconds**
- **Improvement**: 90% faster

**100-operation workflow**:
- Without cache: 100 × 1500ms = **150 seconds** (2.5 minutes)
- With cache: 1500ms + (99 × 1ms) = **1.6 seconds**
- **Improvement**: 99% faster

### Memory Overhead

| Metric | Value |
|--------|-------|
| Empty cache | ~1KB |
| Per cached table | <1KB |
| 100 tables | ~100KB |
| 1000 tables | ~1MB |

### Real-World Scenarios

**API Endpoint** (FastAPI):
- Request 1: 1500ms (cache miss)
- Requests 2-1000: ~1ms each (cache hits)
- **Average latency**: ~2.5ms (99.8% improvement)

**Batch Job** (100 inserts):
- Without cache: 150 seconds
- With cache: 1.6 seconds
- **Improvement**: 98.9% faster

**Multi-Tenant SaaS** (100 tenants, 10 models each):
- Without cache: 1500ms × 1000 = **25 minutes** startup
- With cache: 1500ms × 10 + 990ms = **16 seconds** startup
- **Improvement**: 99.4% faster

## Troubleshooting

### Issue: Cache Not Improving Performance

**Symptom**: Operations still taking ~1500ms each.

**Possible Causes**:

1. **Cache disabled**:
```python
# Check configuration
print(db._schema_cache._enabled)  # Should be True

# Fix: Enable cache
db = DataFlow("postgresql://...", schema_cache_enabled=True)
```

2. **Cache cleared between operations**:
```python
# Check if something is clearing cache
metrics = db._schema_cache.get_metrics()
print(f"Hit rate: {metrics['hit_rate']:.2%}")
# Should be >90% after warmup
```

3. **Different database URLs**:
```python
# Cache is keyed by (model_name, database_url)
# Ensure same URL is used
db1 = DataFlow("postgresql://localhost/mydb")
db2 = DataFlow("postgresql://127.0.0.1/mydb")  # Different URL!

# Use same URL for cache sharing
```

### Issue: Stale Cache After Schema Changes

**Symptom**: Table not found errors after external schema modifications.

**Solution**: Clear cache after external changes:

```python
# After manual DDL
db._schema_cache.clear()

# Or clear specific table
db._schema_cache.clear_table("User", database_url)
```

### Issue: Cache Growing Too Large

**Symptom**: Memory usage increasing over time.

**Solution**: Set max_size or enable TTL:

```python
db = DataFlow(
    "postgresql://...",
    schema_cache_max_size=1000,   # Limit cache size
    schema_cache_ttl=3600          # 1 hour TTL
)

# Or manually clear cache periodically
import schedule

def clear_cache():
    db._schema_cache.clear()

schedule.every(1).hour.do(clear_cache)
```

### Issue: Thread Safety Concerns

**Symptom**: Intermittent errors in multi-threaded application.

**Verification**: Schema cache is thread-safe by design (RLock protected).

**If you still see issues**:

```python
# 1. Check if using multiple DataFlow instances per thread
# ❌ WRONG - Creating instance per request
@app.post("/users")
async def create_user(data: dict):
    db = DataFlow("postgresql://...")  # New instance each time!

# ✅ CORRECT - Reuse single instance
db = DataFlow("postgresql://...")  # Created once

@app.post("/users")
async def create_user(data: dict):
    # Use shared instance
    pass
```

### Issue: Debugging Schema Issues

**Symptom**: Need to verify cache behavior.

**Debug Steps**:

1. **Check cache metrics**:
```python
metrics = db._schema_cache.get_metrics()
print(f"Hits: {metrics['hits']}, Misses: {metrics['misses']}")
print(f"Hit rate: {metrics['hit_rate']:.2%}")
```

2. **Inspect cached tables**:
```python
cached = db._schema_cache.get_cached_tables()
for key, state in cached.items():
    print(f"{key}: {state}")
```

3. **Temporarily disable cache**:
```python
# For debugging only - not production!
db = DataFlow("postgresql://...", schema_cache_enabled=False)
```

4. **Clear cache and retry**:
```python
db._schema_cache.clear()
# Retry operation
```

## Related Documentation

- **Performance Guide**: `sdk-users/apps/dataflow/docs/advanced/performance.md`
- **Migration Guide**: `sdk-users/apps/dataflow/guides/migrations.md`
- **Error Handling Guide**: `sdk-users/apps/dataflow/guides/error-handling.md`

## Version History

- **v0.7.3**: Schema cache introduced with thread-safe RLock implementation
- **Pre-v0.7.3**: No caching, every operation checked database existence
