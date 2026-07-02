# Cache Module Audit

## Source

`packages/kailash-dataflow/src/dataflow/cache/` (7 files, ~1200 lines total)

## Module Contents

### `__init__.py`

Exports: `CacheBackend`, `RedisCacheManager`, `InMemoryCache`, `AsyncRedisCacheAdapter`, `CacheConfig`, `CacheKeyGenerator`, `CacheInvalidator`, `InvalidationPattern`, `ListNodeCacheIntegration`, `CacheableListNode`, `create_cache_integration`.

### `auto_detection.py` -- `CacheBackend`

Factory class with three methods:

- `CacheBackend.auto_detect(redis_url?, ttl=300, max_size=1000)` -- tests Redis connectivity, falls back to InMemoryCache. Returns `AsyncRedisCacheAdapter` or `InMemoryCache`.
- `CacheBackend.create_redis(redis_url, ttl, **kwargs)` -- explicit Redis backend.
- `CacheBackend.create_memory(ttl, max_size)` -- explicit in-memory backend.

### `redis_manager.py` -- `RedisCacheManager`

Full Redis cache implementation with `CacheConfig` dataclass. Provides:

- `get(key)`, `set(key, value, ttl?)`, `delete(key)`, `clear_pattern(pattern)`
- Pattern-based key deletion (e.g., `"dataflow:User:*"`)
- Sync API (uses `redis` module)

### `async_redis_adapter.py` -- `AsyncRedisCacheAdapter`

Async wrapper around `RedisCacheManager`. Provides identical API with `async` methods.

### `memory_cache.py` -- `InMemoryCache`

LRU + TTL cache. Similar to `ExpressQueryCache` but more capable:

- Supports model-scoped operations
- Thread-safe with `RLock`
- `async get/set` interface for consistency with Redis adapter
- Hit/miss statistics

### `key_generator.py` -- `CacheKeyGenerator`

Structured key generation:

- Format: `"{prefix}:{namespace?}:{model}:{version}:{hash}"`
- Default prefix: `"dataflow"`, version: `"v1"`
- Takes `model_name`, `sql`, `params` as inputs
- SHA-256 hash truncated to 16 chars
- Length-bounded: keys >250 chars get fully hashed

### `invalidation.py` -- `CacheInvalidator` and `InvalidationPattern`

Model-scoped invalidation with pattern matching:

- `InvalidationPattern` dataclass with model, operation, invalidation targets
- `CacheInvalidator` manages patterns and executes invalidation
- Handles both sync and async cache backends (auto-detected)
- Batch mode support for bulk operations
- Pre/post hooks for custom invalidation logic
- Metrics tracking

**Critical finding**: `CacheInvalidator` constructor requires `RedisCacheManager`, not a generic cache interface. The `InMemoryCache` backend is NOT directly compatible with `CacheInvalidator` -- it expects a manager with `clear_pattern()` support.

### `list_node_integration.py` -- `ListNodeCacheIntegration`

Ready-made integration for `ListNode` operations. Has `CacheableListNode` that wraps list queries with caching. Not currently used by Express.

## Verification: NOT Wired to Express

Confirmed. The `cache/` module is completely independent of `features/express.py`. Express uses `ExpressQueryCache` (hand-rolled, in the same file). No import of anything from `cache/` anywhere in `express.py` or `engine.py`.

## Gap Between Cache Module and Express

| Aspect         | ExpressQueryCache               | cache/ Module                           |
| -------------- | ------------------------------- | --------------------------------------- |
| Backend        | In-memory only                  | Redis + InMemory with auto-detection    |
| Invalidation   | Nuclear (clear all)             | Model-scoped pattern matching           |
| Key generation | SHA-256 of model:operation:json | Structured prefix:ns:model:version:hash |
| Statistics     | Basic (hits/misses/evictions)   | Detailed with metrics hooks             |
| Interface      | Sync-only methods               | Both sync and async                     |
| Integration    | Tightly coupled to Express      | Standalone, needs wiring                |

## Risk for TSG-104

The `CacheInvalidator` is typed to `RedisCacheManager`. Wiring it to Express with an `InMemoryCache` backend will require either:

1. An adapter that wraps `InMemoryCache` to match `RedisCacheManager` interface
2. Refactoring `CacheInvalidator` to accept a generic cache interface
3. Using `CacheBackend.auto_detect()` which returns `AsyncRedisCacheAdapter` or `InMemoryCache` -- but `CacheInvalidator` only accepts `RedisCacheManager`

This is a real implementation friction point that the brief doesn't mention.
