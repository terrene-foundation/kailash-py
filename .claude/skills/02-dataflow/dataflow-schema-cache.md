# DataFlow Schema Cache

## Overview

The schema cache is a thread-safe table existence cache that eliminates redundant migration checks, providing **91-99% performance improvement** for multi-operation workflows.

## Key Features

- **Thread-safe**: RLock protection for multi-threaded apps (FastAPI, Flask, Gunicorn)
- **Configurable**: TTL, size limits, and validation
- **Automatic invalidation**: Cache cleared on schema changes
- **Low overhead**: <1KB per cached table

## Performance Characteristics

| Operation | Time |
|-----------|------|
| Cache miss (first check) | ~1500ms |
| Cache hit (subsequent) | ~1ms |
| Improvement | 91-99% faster |

## Configuration

```python
from dataflow import DataFlow

# Default (cache enabled, no TTL)
db = DataFlow("postgresql://...")

# Custom configuration
db = DataFlow(
    "postgresql://...",
    schema_cache_enabled=True,      # Enable/disable cache
    schema_cache_ttl=300,            # TTL in seconds (None = no expiration)
    schema_cache_max_size=10000,    # Max cached tables
    schema_cache_validation=False,  # Schema checksum validation
)

# Disable cache (for debugging)
db = DataFlow("postgresql://...", schema_cache_enabled=False)
```

## Automatic Usage

Cache works automatically - no code changes needed:

```python
db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str

# First operation: Cache miss (~1500ms)
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice"
})
runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

# Subsequent operations: Cache hit (~1ms)
workflow2 = WorkflowBuilder()
workflow2.add_node("UserCreateNode", "create2", {
    "id": "user-2",
    "name": "Bob"
})
results2, _ = runtime.execute(workflow2.build())  # 99% faster!
```

## Cache Methods (Advanced)

```python
# Clear all cache entries
db._schema_cache.clear()

# Get cache performance statistics
metrics = db._schema_cache.get_metrics()
print(f"Hits: {metrics['hits']}")
print(f"Misses: {metrics['misses']}")
print(f"Hit rate: {metrics['hit_rate']:.2%}")
print(f"Cached tables: {metrics['cached_tables']}")
```

## Thread Safety

The schema cache is fully thread-safe for multi-threaded applications:

```python
from dataflow import DataFlow
from concurrent.futures import ThreadPoolExecutor

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str

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
```

All cache operations are protected by RLock, ensuring safe concurrent access from FastAPI endpoints, Flask workers, or Gunicorn processes.

## Performance Impact Summary

| Metric | Before v0.4.7 | After v0.4.7 |
|--------|---------------|--------------|
| Instance creation | ~700ms | <50ms (14x faster) |
| First operation | ~1500ms | ~1500ms (cache miss) |
| Subsequent operations | ~1500ms | ~1ms (99% faster) |
| Memory per table | N/A | <1KB |

## Version Requirements

- DataFlow v0.7.3+ for schema cache
