---
name: dataflow-express-cache
description: "Express API caching with model-scoped invalidation and TTL. Use when asking about 'express cache', 'cache TTL', 'CacheBackendProtocol', 'cache invalidation', 'cache stats', 'Redis cache', or 'model-scoped cache'."
---

# DataFlow Express Cache

Model-scoped caching for Express API reads with automatic write-through invalidation.

## Quick Reference

| Feature      | Details                                     |
| ------------ | ------------------------------------------- |
| Enable       | `DataFlow(..., cache_enabled=True)`         |
| Default TTL  | 300 seconds (5 minutes)                     |
| Backends     | In-memory (default), Redis (via URL)        |
| Invalidation | Automatic on writes to the same model       |
| Stats        | `await db.express.cache_stats()`            |
| Clear        | `await db.express.clear_cache("ModelName")` |

## Configuration

```python
# In-memory cache (default backend)
db = DataFlow(
    "sqlite:///app.db",
    cache_enabled=True,
    cache_ttl=300,        # TTL in seconds
    cache_max_size=1000,  # Max entries per model
)

# Redis cache (shared across workers)
db = DataFlow(
    "postgresql://...",
    cache_enabled=True,
    cache_redis_url="redis://localhost:6379/0",
    cache_ttl=600,
)
```

## Using Cache in Reads

```python
# Cache is transparent -- reads use cache automatically
user = await db.express.read("User", "u1")           # Cache miss -> DB query
user = await db.express.read("User", "u1")           # Cache hit

# Override TTL per-read
user = await db.express.read("User", "u1", cache_ttl=60)  # 1-minute TTL

# Bypass cache (force DB read)
user = await db.express.read("User", "u1", cache_ttl=0)

# Force read from primary (with read replicas)
user = await db.express.read("User", "u1", use_primary=True)

# find_one and count also support caching
user = await db.express.find_one("User", {"email": "alice@example.com"}, cache_ttl=120)
count = await db.express.count("User", {"active": True}, cache_ttl=300)
```

## Automatic Invalidation

When a write operation occurs on a model, the cache for that model is invalidated:

```python
await db.express.create("User", {"name": "Alice"})   # Invalidates User cache
await db.express.update("User", "u1", {"name": "Bob"})  # Invalidates User cache
# Next read will be a cache miss (fresh data from DB)
```

## Cache Stats

```python
stats = await db.express.cache_stats()
# Returns: {"hits": 150, "misses": 30, "backend": "memory"}

# Sync variant
stats = db.express_sync.cache_stats()
```

## Clear Cache

```python
# Clear cache for a specific model
await db.express.clear_cache("User")

# Sync variant
db.express_sync.clear_cache("User")
```

## CacheBackendProtocol

Custom cache backends implement the `CacheBackendProtocol`:

```python
from dataflow.cache.invalidation import CacheBackendProtocol

class MyCustomCache:
    """Must implement the CacheBackendProtocol."""
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: Any, ttl: int) -> None: ...
    async def delete(self, pattern: str) -> None: ...
    async def stats(self) -> dict: ...
```

## Source Code

- the dataflow package (`src/dataflow/features/express.py`) -- Cache integration in Express API
- the dataflow package (`src/dataflow/cache/invalidation.py`) -- CacheBackendProtocol
- the dataflow package (`tests/unit/test_express_cache_wiring.py`) -- Cache wiring tests
