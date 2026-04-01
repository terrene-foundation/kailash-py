---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T14:30:00+08:00
author: agent
session_id: red-team-r2
session_turn: 8
project: dataflow-enhancements
topic: Sync/async impedance mismatch between CacheInvalidator, RedisCacheManager, and InMemoryCache
phase: analyze
tags: [cache, async, type-safety, TSG-104, red-team]
---

# Sync/Async Impedance Mismatch in Cache Layer

## Context

Red Team Round 1 identified that `CacheInvalidator.__init__` accepts `cache_manager: RedisCacheManager`, and `InMemoryCache` is not a `RedisCacheManager` (Challenge 3). R1 recommended refactoring to a protocol/ABC. Round 2 discovered the problem is deeper than a typing issue.

## The Risk

The three cache components have fundamentally incompatible interfaces:

| Component           | `delete()`                                   | `clear_pattern()`                                   | `get()`                             | `set()`                                        |
| ------------------- | -------------------------------------------- | --------------------------------------------------- | ----------------------------------- | ---------------------------------------------- |
| `RedisCacheManager` | `def delete(key) -> int` (sync)              | `def clear_pattern(pattern) -> int` (sync)          | `def get(key) -> Any` (sync)        | `def set(key, val, ttl) -> bool` (sync)        |
| `InMemoryCache`     | `async def delete(key) -> int` (async)       | `async def clear_pattern(pattern) -> int` (async)   | `async def get(key) -> Any` (async) | `async def set(key, val, ttl) -> bool` (async) |
| `CacheInvalidator`  | Calls `cache_manager.delete()` synchronously | Calls `cache_manager.clear_pattern()` synchronously | N/A                                 | N/A                                            |

If `CacheInvalidator` receives an `InMemoryCache` instance, calling `self.cache_manager.delete(key)` returns a coroutine object, not an `int`. The delete silently does nothing. The `CacheInvalidator` already has a workaround (`_detect_async_cache()` + `_perform_invalidation_async_safe()`), but this relies on `async_safe_run()` which uses heuristics to detect whether an event loop exists.

## Why This Matters for TSG-104

TSG-104 (Express Cache Wiring) must connect Express to the `cache/` module. Express methods are all `async def`. The `CacheInvalidator` is called from Express after writes. The chain is:

```
Express.create() [async] -> CacheInvalidator.invalidate() [sync] -> cache_manager.delete() [sync or async?]
```

If we wire `InMemoryCache` into `CacheInvalidator`, the sync/async boundary creates a fragile chain of workarounds. If we use `RedisCacheManager`, it works but only for Redis.

## Recommended Resolution

Make the entire invalidation path async:

1. `CacheInvalidator.invalidate()` becomes `async def invalidate()`
2. Express calls `await self._invalidator.invalidate(...)` (Express is already async)
3. `InMemoryCache` works natively (already async)
4. `RedisCacheManager` gets wrapped in `AsyncRedisCacheAdapter` (already exists)
5. Define `CacheBackendProtocol` with async interface as the common type

This eliminates the impedance mismatch entirely. The sync `CacheInvalidator` was designed for a sync-only Redis world. DataFlow's Express API is async-first. The cache layer should match.

## Alternative: Skip CacheInvalidator for Express

A simpler alternative: Express calls `cache_manager.clear_pattern(f"dataflow:{model}:*")` directly, bypassing `CacheInvalidator` entirely. The `CacheInvalidator`'s pattern-matching and group-invalidation features are not needed for Express's model-scoped invalidation. This avoids the sync/async mismatch by sidestepping it.

## For Discussion

1. The `CacheInvalidator` has 529 lines of pattern matching, group invalidation, batch mode, and metrics — features that Express's simple "clear model cache on write" does not need. If Express bypasses `CacheInvalidator`, is there still a consumer for the complex invalidation patterns? Or was `CacheInvalidator` built anticipatorily for a use case that never materialized?

2. If the entire cache layer had been designed async-first (as DataFlow's Express API requires), would `RedisCacheManager` have been async from the start? The sync Redis client was likely chosen for simplicity, but it created a sync/async split that now propagates through the invalidation layer. If TSG-104 had been the first feature built, what would the cache architecture look like?

3. The `async_safe_run()` utility that bridges sync and async contexts is used in 3+ places in the DataFlow codebase as a workaround for sync/async mismatches. Is this a pattern that should be formalized, or a code smell indicating that the async boundary was drawn in the wrong place?
