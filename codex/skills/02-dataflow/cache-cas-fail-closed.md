---
name: Cache CAS fail-closed pattern
description: When a CAS (compare-and-swap) primitive can only be satisfied by one backend, reject at the API boundary instead of silently degrading across backends.
---

# Cache CAS Fail-Closed Pattern

When a cache primitive offers compare-and-swap semantics but the CAS tracking state lives in-process, the operation is ONLY correct on the in-process memory backend. For Redis, Memcached, or hybrid backends, the in-process version tag has no atomicity guarantee — two processes sharing the Redis instance each maintain independent version dicts, and the CAS check becomes meaningless.

The fail-closed pattern: reject the CAS request at the outer API boundary when the backend cannot satisfy it atomically. Do NOT allow the request to proceed, silently ignore `expected_version`, or produce misleading success on a non-atomic write.

## The Pattern

```python
async def async_run(self, **kwargs) -> Dict[str, Any]:
    operation = kwargs["operation"].lower()
    backend = CacheBackend(kwargs.get("backend", "memory"))

    # Fail-closed guard BEFORE any backend init.
    # CAS (expected_version) is only supported with memory backend.
    if (
        operation == "set"
        and kwargs.get("expected_version") is not None
        and backend != CacheBackend.MEMORY
    ):
        return {
            "success": False,
            "cas_failed": True,
            "error": (
                "CAS (expected_version) is only supported with "
                "backend='memory'. Redis and hybrid backends require "
                "server-side CAS (e.g., Redis WATCH/MULTI)."
            ),
        }
    # ... rest of execution
```

## Key points

1. **Reject at the outer boundary** — before backend initialization, so we don't even attempt to connect to a Redis we can't correctly serve. This keeps error paths cheap and fails fast.

2. **Return structured error, not exception** — the caller gets `success=False`, `cas_failed=True`, and an error message directing them to server-side CAS. The existing error-handling contract (not a new exception class) is preserved.

3. **Direct the caller to the correct API** — the error message names the alternative (Redis WATCH/MULTI). This converts the failure into actionable guidance, not a dead-end.

4. **Test both directions** — a regression test must verify (a) CAS works correctly on memory backend, (b) CAS is rejected with a clear error on every other backend. See `tests/regression/test_cache_cas_tenant.py::TestCacheCASRace::test_cas_rejected_on_redis_backend`.

## When to use

This pattern applies any time a primitive's correctness depends on state that only one backend can provide:

- **CAS / optimistic locking** — in-process version tags only work for in-process backends
- **Transactional multi-key writes** — local transaction only applies to local backend
- **Last-writer-wins timestamps** — local clock only authoritative for local backend
- **Structural guarantees** — e.g. "exactly-once delivery" that relies on an in-process dedup set

## When NOT to use (false positives)

- **Backend-agnostic primitives** — `get`, `set`, `delete`, `exists` work identically across backends; don't reject them.
- **Primitives with a correct multi-backend implementation** — if you can implement CAS correctly on Redis via WATCH/MULTI, implement it; don't just reject.

## Anti-patterns

```python
# BLOCKED — silently ignore expected_version on non-memory backends
async def _set(self, kwargs):
    expected_version = kwargs.get("expected_version")
    if expected_version is not None:
        current = self._version_tags.get(key)  # empty dict for Redis
        if current != expected_version:
            return {"cas_failed": True}
    # write to Redis without CAS check at all
    await self._redis_set(...)
# ↑ for Redis: _version_tags is empty, current is always None,
# CAS check passes when expected_version is None, silently bypasses guarantee

# BLOCKED — raise NotImplementedError deep in the call stack
async def _set(self, kwargs):
    expected_version = kwargs.get("expected_version")
    backend = kwargs["backend"]
    if expected_version is not None and backend != "memory":
        raise NotImplementedError("CAS only works with memory")
# ↑ by the time this fires, the caller is deep in a workflow and
# the error surfaces as an uncaught exception, not an API contract

# BLOCKED — fall back to non-CAS write when backend can't support it
if expected_version is not None and backend != "memory":
    logger.warning("CAS not supported on this backend, ignoring")
    # fall through to regular write
# ↑ the caller thinks their CAS succeeded; concurrent writer clobbers them
```

## Origin

PR #430 red team review (2026-04-12) surfaced the silent-degradation pattern in `src/kailash/nodes/cache/cache.py::CacheNode._set`. Fixed in commits bd411c44 and 62d64ac7. Tests in `tests/regression/test_cache_cas_tenant.py`.
