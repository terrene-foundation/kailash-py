# Issue #354 — Executive Summary

**Severity**: CRITICAL
**Verdict**: The reporter was right to call this "damning". It is worse than the report describes.
**Scope**: `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py` and adjacent wiring in `runtime.py`, `engine.py`, `webhooks.py`

## One-paragraph summary

`DataFlow(redis_url=...)` silently no-ops for fabric product caching. The `redis_url` parameter is plumbed through four layers, ignored at the final layer, and lied about in four docstrings, one README section, and one production-deployment doc. The fabric product cache is a per-process `OrderedDict`. Multi-replica deployments pay for Redis but run with N independent caches and eat the cold-start cost N times per release. On impact-verse this compounded into a Container Apps startup-probe crash loop (4-5 minute serial prewarm exceeding ~4 minute probe). The same file has **eight distinct stubs or lies**, not one — eight. The `DataFlow(redis_url=...)` kwarg doesn't even reach the fabric layer at all (a second dead wiring bug the reporter didn't find). The `multi_tenant` product flag is documented as tenant-partitioned caching but `_cache_key` has no tenant dimension, which means any naive Redis fix becomes a cross-tenant data-leak primitive. Cross-SDK: kailash-rs has the matching absence of any Redis path. Test coverage for `redis_url` in fabric: zero.

## The eight (actually nine) stubs / lies in `pipeline.py`

| #   | Line(s) | What                                                                                                                                                                                                                                                                                                                       | Kind              |
| --- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| 1   | 8       | Module docstring: "Supports both in-memory (dev) and Redis (production) cache"                                                                                                                                                                                                                                             | Docstring lie     |
| 2   | 137     | Class docstring: "redis_url: Optional Redis URL for production caching"                                                                                                                                                                                                                                                    | Docstring lie     |
| 3   | 140     | Class docstring: "dev_mode forces in-memory cache even if redis_url is provided"                                                                                                                                                                                                                                           | Vacuous docstring |
| 4   | 152     | `self._redis_url = redis_url` — stored, never read                                                                                                                                                                                                                                                                         | Dead state        |
| 5   | 154     | `self._dev_mode = dev_mode` — stored, never read                                                                                                                                                                                                                                                                           | Dead state        |
| 6   | 173     | `self._queue: asyncio.Queue = ...` — declared; **one dormant consumer** at `change_detector.py:275` reached via `getattr` fallback, dead-by-accident today because `runtime.py:207` always calls `set_on_change` (corrected by red team finding N1). Paired cleanup: delete both sides atomically, or leave both in place. | Dormant state     |
| 7   | 175     | `# In-memory cache (used when dev_mode or no redis_url)` — implies conditional that doesn't exist                                                                                                                                                                                                                          | Comment lie       |
| 8   | 227     | `# Cache operations (in-memory; Redis is a future extension)` — honest but contradicts #1-#7 90 lines up                                                                                                                                                                                                                   | Self-refuting     |
| 9   | 581     | `InMemoryDebouncer` class — defined, zero instantiations anywhere in fabric                                                                                                                                                                                                                                                | Dead class        |

## The two additional wiring bugs the reporter didn't find

1. **`DataFlow(redis_url=...)` does not reach fabric at all**. `engine.py:116` comment says "Redis URL for Express cache backend" — the kwarg only feeds `ExpressDataFlow` query cache. `engine.py:2015-2019` reads `self._redis_url` but no line in the class ever assigns `self._redis_url`. It is a dead `hasattr` branch. Only users who build `DataFlowConfig(redis_url=...)` explicitly get the value into the fabric runtime — and even then the fabric pipeline ignores it. **Two dead wiring paths stacked.**

2. **`WebhookReceiver` never gets the Redis client**. `webhooks.py:170-188` accepts `redis_client=None`, and `_RedisNonceBackend` at `webhooks.py:73-108` is correctly implemented. But `FabricRuntime.start()` at `runtime.py:211-214` instantiates `WebhookReceiver(sources=..., on_webhook_event=...)` **without `redis_client`**. Every multi-replica deployment has broken webhook nonce deduplication today. Two replicas that both receive the same GitHub webhook delivery both pass HMAC + timestamp + nonce checks and both fire pipelines. Masked today by the per-process cache (each writes to its own dict); becomes visible duplicate work the moment the Redis cache lands.

## The multi-tenant data-leak primitive

`products.py:52, 111` documents `multi_tenant: Whether cache is partitioned per tenant`. Implementation: `pipeline.py:119-124` `_cache_key(product_name, params)` takes only product name and params. **No tenant dimension.** Today this is a low-impact bug because each process has its own in-memory cache. The moment a Redis fix lands without tenant partitioning, product A's cached data for tenant X is served to a tenant Y request using the same key. **Shipping the Redis fix without tenant partitioning is strictly worse than the current bug it replaces.** Tenant partitioning is a BLOCKER, not a nice-to-have.

## What the correct fix must include (all in one PR)

1. **`FabricCacheBackend(ABC)`** in new `fabric/cache.py`, mirroring `LeaderBackend` (`leader.py:35`) and `_NonceBackend` (`webhooks.py:39`) patterns in the same module. Three fabric subsystems, three ABC + two-backend pattern, one consistent architecture.
2. **`InMemoryFabricCacheBackend`** — single `OrderedDict[str, _FabricCacheEntry]` replacing today's three parallel dicts. LRU cap preserved. Async-over-sync methods.
3. **`RedisFabricCacheBackend`** — direct `redis.asyncio.from_url(...)` pattern matching `leader.py:62-72`. Lazy client construction. `close()` on shutdown. One Redis HASH per product with fields `data/hash/cached_at/pipeline_ms/size_bytes/run_id`, TTL = `max(staleness.max_age * 24, 3600)`. **NOT** the `dataflow.cache.auto_detection.AsyncRedisCacheAdapter` — its ThreadPoolExecutor wrapper adds 1-2ms per hot-path operation we don't need.
4. **Tenant-partitioned keys**. `_cache_key` gains a `tenant_id` argument. Keys become `fabric:product:<instance>:<tenant_id>:<product_name>[:<params_hash_16>]`. Products declared `multi_tenant=True` MUST supply a tenant_id or the call raises.
5. **DataFlow kwarg wiring**. `DataFlow.__init__` stores `self._redis_url = redis_url` so the `engine.py:2018` read branch actually works. This is a one-line fix but closes the deepest part of the bug.
6. **WebhookReceiver wiring fix**. Same PR. Extract a helper `_get_or_create_redis_client()` in `FabricRuntime.start()` and pass to both `WebhookReceiver` and the new cache backend. Symmetric with leader and cache.
7. **Leader-side warm-cache on election** (NOT "follower-side lazy prewarm" as the first draft claimed — red team caught this). Followers already skip prewarm today via `runtime.py:185-189 if self._leader.is_leader and prewarm`. The actual impact-verse crash loop is the _leader_ replica dying mid-deploy and the new leader running the full 4-5 minute serial prewarm from scratch. Fix: `_prewarm_products` gains a read-before-execute step — for each materialized product, call `cache.get_metadata(key)`; if `cached_at + staleness.max_age > now`, skip execution; else re-execute. This is the impact-verse regression guard.
8. **Write CAS by `run_started_at`**. Red-team finding: under R3 last-writer-wins, a slow replica A (started T=0, 10s pipeline) can overwrite the fresh write from a fast replica B (started T=5, 2s pipeline) at T=10 — stale data wins. Fix: `RedisFabricCacheBackend.set()` uses a Lua CAS keyed on `run_started_at`. Older writers are blocked. Regression test: two concurrent writers with staggered start times, assert newer one wins.
9. **Redis-outage fallback**. Cache backend catches `(redis.ConnectionError, asyncio.TimeoutError)` on every `get`/`set`, logs WARN with masked URL, returns None (cache miss), increments `fabric_cache_errors_total`, flips `fabric_cache_degraded=1` gauge. Cache miss on outage beats a 500 on every request.
10. **`get_metadata(key)` fast path**. Added to `FabricCacheBackend` ABC. `product_info`, health probes, and leader-election warm-cache check only need `cached_at`/`content_hash`/`size_bytes` — they should not pay for a full `HGETALL` of the payload. 50% latency cut on those paths.
11. **Paired dead-code deletion**. `self._queue` (`pipeline.py:173`) AND `change_detector.py:274-296` fallback consumer block MUST be deleted in the same commit. Red-team verified: `change_detector.py:275` reads `getattr(self._pipeline_executor, "_queue", None)` as a dormant fallback, dead-by-accident today because `runtime.py:207` always calls `set_on_change` — but deleting one without the other leaves a dangling getattr. `InMemoryDebouncer` docstring updated to say "single-worker only"; class stays with follow-up PR 2.
12. **Observability**. Every `get_cached`/`set_cached` logs `product_name`, `params_hash`, `cache_hit`, `mode=real|memory|redis`. Backend selection logged once at INFO in `__init__`. New Prometheus metrics: `fabric_cache_hits_total`, `fabric_cache_misses_total`, `fabric_cache_dedup_skips_total`, `fabric_cache_writes_total`, `fabric_cache_errors_total`, `fabric_cache_backend_info` gauge.
13. **Tier 2 integration tests with real Redis**. No mocking. New `tests/fabric/test_fabric_cache_redis.py` with 10+ scenarios including multi-replica, tenant isolation, TTL, dedup, invalidation, follower-lazy-prewarm.
14. **Every lying docstring corrected**. D1-D11 from the blast-radius report. Any docstring that lies after the fix is a new zero-tolerance Rule 2 violation.
15. **CHANGELOG entry** citing #354 + breaking change note (async API on `FabricRuntime.product_info` / `invalidate` / `invalidate_all`) + version bump to 1.9.0.

## What goes into follow-up PRs

- **PR 2**: `_RedisDebouncer` implementation + cross-replica debounce semantics. Separate because the debouncer test surface and risk profile are different.
- **PR 3**: Cross-SDK Rust issue on `esperie-enterprise/kailash-rs`. Rust `crates/kailash-dataflow/src/executor.rs` has zero Redis support — not even a stubbed parameter. File as `cross-sdk` labelled issue linking to kailash-py#354.
- **PR 4** (future ADR): Unify `dataflow/cache/` (query cache, express cache) with `dataflow/fabric/cache.py` (product cache) into one cache story. Tempting but out of scope for a bug fix.

## Institutional-knowledge fault line

Primary **context amnesia**: the honest comment at `pipeline.py:227` (`# Cache operations (in-memory; Redis is a future extension)`) and the dishonest class docstring at `pipeline.py:137` (`redis_url: Optional Redis URL for production caching`) coexist **ninety lines apart in the same file**. The author knew it was a stub, documented it as a stub, and also wrote the class docstring as if the stub were implemented. One commit, two contradicting claims, ship to PyPI as 1.8.0.

Secondary **security blindness**: `multi_tenant` contract documented, tenant partitioning not implemented. Shipping Redis without catching this would CREATE the data leak.

Tertiary **convention drift**: `.claude/rules/dataflow-pool.md` Rule 3 ("No Deceptive Configuration") already exists and explicitly forbids this exact pattern: "A flag set to True with no consumer is a stub." The reviewer either did not run it against this file, or did not search for `"future extension"` in the diff.

## Proposed guards

1. **Extend `rules/dataflow-pool.md` Rule 3** with: "For every config field named `*_url`, `*_backend`, or `*_client`, there MUST be at least one import or instantiation of the backing client in the class body." Automatable via grep at `/redteam` time.
2. **New test rule**: for any parameter whose docstring contains "production" or "Redis", require a corresponding Tier 2 integration test that passes the parameter and verifies the side effect.
3. **CI grep guard**: fail the build on `"future extension"`, `"not yet implemented"`, `"Redis is a future"` in `src/`.
4. **Docstring-vs-code auditor**: for every parameter whose docstring mentions "Redis", verify the class body contains `from_url` / `redis.asyncio` / `aioredis`. Run at `/redteam`.

## Corrections from red team

- **Reporter's "dataflow/engine.py has zero cache/redis references" claim**: reporter was grepping a non-existent path. The correct file `packages/kailash-dataflow/src/dataflow/core/engine.py` has **230 matches** — but all are for the Express query cache, not fabric. The conclusion stands: **no Express cache reference reaches the fabric product cache**. Only the dead `hasattr(self, '_redis_url')` branch at `engine.py:2015-2019` points fabric-ward, and that branch is always false because `self._redis_url` is never assigned in `DataFlow.__init__`. Framing corrected; severity unchanged.
- **Follower-side lazy prewarm was the wrong framing** for the impact-verse regression guard. Followers already skip prewarm today (`runtime.py:185-189`). The actual crash loop is triggered by leader-replica restart during rolling deploys, where the _new_ leader re-runs the full 4-5 minute serial prewarm. The fix is leader-side warm-cache on election (corrected above in item 7).
- **`_queue` is not zero-consumer**, it is dormant-one-consumer at `change_detector.py:275` via `getattr` fallback. Must be deleted atomically with the consumer block (corrected above in item 11).

## Key file citations

- Bug: `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:137, 152, 175, 227, 230-268, 581`
- Deeper wiring bug: `packages/kailash-dataflow/src/dataflow/core/engine.py:116, 2015-2019`
- Second wiring bug (webhook): `packages/kailash-dataflow/src/dataflow/fabric/runtime.py:211-214` + `webhooks.py:73-108, 170-188`
- Correct pattern to mirror: `packages/kailash-dataflow/src/dataflow/fabric/leader.py:55-105, 131-158`
- Pre-existing (rejected) abstraction: `packages/kailash-dataflow/src/dataflow/cache/async_redis_adapter.py` (thread-pool overhead)
- Cross-SDK parallel bug: `kailash-rs/crates/kailash-dataflow/src/executor.rs:32-54, 94-149`
- `redis` dependency already declared: `packages/kailash-dataflow/pyproject.toml:35`
- Zero test coverage: every `tests/fabric/test_*` passes `dev_mode=True` with no `redis_url`

## Related research files

- `01-analysis/01-research/01-dataflow-specialist-report.md` — full fix design (830 lines, 15 sections)
- `01-analysis/01-research/02-blast-radius-report.md` — failure points, fault lines, observability, blockers (300+ lines)
