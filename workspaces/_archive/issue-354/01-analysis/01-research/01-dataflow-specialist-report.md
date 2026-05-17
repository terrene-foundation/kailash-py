# Issue #354 — DataFlow Specialist Analysis

**Author**: dataflow-specialist
**Phase**: 01-analysis / research
**Source of truth**: `packages/kailash-dataflow/src/dataflow/fabric/` at branch `feat/platform-architecture-convergence`
**Severity**: CRITICAL — docstring lies, parameter is plumbed through three layers and never used, multi-replica deployments of `db.fabric` silently run in per-process cache mode while paying for a Redis that does nothing.

---

## 0. TL;DR for reviewers who only read one section

`PipelineExecutor.__init__` at `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:144-188` accepts `redis_url` and assigns it to `self._redis_url` at line 152. The value is **never read again**. The actual cache is `self._cache_data` (a `collections.OrderedDict[str, bytes]` at line 177) wired into `get_cached`, `set_cached`, `_get_cached_hash`, `invalidate`, and `invalidate_all` (lines 230-516). Every cache operation is synchronous, per-process, and unshared across replicas. The module-level docstring at `pipeline.py:8` and the class docstring at `pipeline.py:137` both promise Redis. Neither is delivered.

Three additional, worse findings the issue reporter did not list:

1. **`_RedisDebouncer` does not exist** — only `InMemoryDebouncer` at `pipeline.py:581`. Same class of lie (docstring at `pipeline.py:582` says "fallback ... when Redis is not available", implying a Redis primary that is not present).
2. **Webhook nonce dedup is silently in-memory in every current deployment**: `WebhookReceiver.__init__` in `fabric/webhooks.py:170-188` accepts a `redis_client` parameter, but `FabricRuntime.start()` at `fabric/runtime.py:211-214` instantiates `WebhookReceiver(sources=..., on_webhook_event=...)` **without passing `redis_client`**. So the one place in fabric that IS capable of Redis nonce storage is also being fed in-memory in production. Multi-replica webhook deduplication is broken today.
3. **A `CacheBackend` abstraction already exists** at `dataflow/cache/auto_detection.py` (`CacheBackend.auto_detect()` returning `AsyncRedisCacheAdapter | InMemoryCache`, with a matching async surface). The fabric pipeline hand-rolls its own in-memory cache instead of reusing it. This is the framework-first rule being violated inside the framework itself.

Root cause: the `redis_url` parameter was added cosmetically — likely during the initial TODO-11 implementation — and nobody ever came back to wire the backend. There is zero test coverage of `PipelineExecutor(redis_url=...)` in `packages/kailash-dataflow/tests/fabric/`: every fabric test constructs the executor with `dev_mode=True` and no `redis_url`, so the parameter has literally never been exercised since it was introduced.

---

## 1. Root cause classification

This is not a single-rule violation. It is a clean sweep of the zero-tolerance and framework-first axes.

### 1.1 `.claude/rules/zero-tolerance.md` Rule 2 — Stubs and placeholders

Rule 2 prohibits `TODO`, `FIXME`, `NotImplementedError`, and "`return {"status": "ok"}` as placeholder for real logic". It does not explicitly enumerate "parameter accepted and ignored" but the intent is unambiguous: production code must not pretend to have implemented a feature it has not implemented.

Specific violations:

- `pipeline.py:8` — module docstring: `"Supports both in-memory (dev) and Redis (production) cache."` False at the module level.
- `pipeline.py:137-141` — class docstring: `redis_url: Optional Redis URL for production caching. When None, an in-memory cache is used (suitable for development). ... dev_mode: When True, forces in-memory cache even if redis_url is provided.` Both sentences describe a feature that does not exist. The second sentence is the tell — there is no "force in-memory" branch because there is no alternative to in-memory.
- `pipeline.py:152` — `self._redis_url = redis_url` stores a value that is never read.
- `pipeline.py:175-176` — comment: `# In-memory cache (used when dev_mode or no redis_url)`. The parenthetical implies conditional selection. There is none.
- `pipeline.py:227` — section banner: `# Cache operations (in-memory; Redis is a future extension)`. This is the one honest line in the file, and it contradicts every other comment and docstring above it. The presence of "future extension" inside a class whose public docstring promises "production" Redis is the textbook definition of a stub that has been documented rather than implemented.
- `pipeline.py:581-586` — `InMemoryDebouncer` docstring: `"Fallback debouncer for dev mode when Redis is not available."` The word "fallback" implies a primary. There is no `RedisDebouncer` in this file or anywhere in the fabric package. Verified: `grep -rn "RedisDebouncer" packages/kailash-dataflow/` returns zero.

### 1.2 `.claude/rules/zero-tolerance.md` Rule 3 — Silent fallbacks

Rule 3 prohibits "silent fallbacks or error hiding". In the current code, there is no `try: import redis` / `except ImportError: fall back to memory` pattern — that would at least be visible. What exists is worse: `redis_url` is accepted, acknowledged, and silently discarded. The user gets the same behavior whether they pass a Redis URL or `None`. A silent fallback is at least detectable by reading the fallback code; a silent no-op is invisible until an operator checks Redis `MONITOR` output and sees zero fabric cache traffic.

### 1.3 `.claude/rules/dataflow-pool.md` Rule 3 — No Deceptive Configuration

Verbatim from the rule file: "Config flags MUST have backing implementation. A flag set to True with no consumer is a stub (`zero-tolerance.md` Rule 2)."

`redis_url` is not a flag; it is a string. The rule clearly applies — a configuration parameter that changes the user's mental model ("I'm now running with Redis") without changing behavior is exactly the class of deception this rule exists to prevent. `redis_url` is plumbed through:

1. `core/engine.py:2015-2019` — `DataFlow.start()` resolves `redis_url` from `self.config.redis_url`, `self.config.database.redis_url`, and `self._redis_url`, then passes to `FabricRuntime`.
2. `fabric/runtime.py:69, 81, 172` — `FabricRuntime` accepts, stores, and forwards to `PipelineExecutor`.
3. `fabric/runtime.py:178` — `FabricRuntime` also forwards to `LeaderElector`, which **does** use it correctly (`fabric/leader.py:155-158`).
4. `fabric/pipeline.py:147-152` — `PipelineExecutor` accepts, stores, and **discards**.

The operator sees the value propagating through three layers and reasonably concludes it is being used. Deception is maximal precisely because the plumbing is real.

### 1.4 `.claude/rules/framework-first.md` — Raw primitives when Engine exists

This is the bitterest finding. The framework-first rule mandates that if an Engine/Primitive exists for a use case, raw re-implementation is BLOCKED. The fabric pipeline re-implements a bounded LRU cache with serialized values, TTL-less, in-process — when the same package ships `dataflow/cache/auto_detection.py:92` `CacheBackend.auto_detect()` returning either `AsyncRedisCacheAdapter` or `InMemoryCache` with a unified async interface. It is framework-first violation inside a framework package. The pipeline is simultaneously:

- a "raw" LRU re-implementation (`collections.OrderedDict` + manual eviction at `pipeline.py:257-261`)
- a broken Redis promise
- a reason someone will eventually file an issue saying "why are there two cache systems in kailash-dataflow?"

### 1.5 `.claude/rules/observability.md` MUST Rule 3 — Log levels

`pipeline.py` logs at DEBUG for cache writes (`set_cached` has no log line at all) and INFO for nothing cache-related. A cache backend selection — the single most important runtime characteristic of the pipeline executor — is not logged at all. Operators cannot verify from logs whether fabric is using the cache they provisioned. Compare to `fabric/leader.py:177`, which logs `"Leader elected: %s (TTL=%ds)"` at DEBUG, and `fabric/webhooks.py:182`, which logs `"Webhook nonce storage: Redis (cross-worker)"` at DEBUG. Leader and webhook subsystems announce their backend; pipeline executor is silent because there is nothing to announce.

### 1.6 `.claude/rules/autonomous-execution.md` — Throughput tax

Every replica re-executing every product on every cold start — which is the current state on impact-verse — is the opposite of the 10x throughput model COC assumes. The rule is not directly violated (the rule governs deliberation framing) but it is relevant as a motivating force: the institutional knowledge that `db.start(prewarm=True)` "just works" is wrong in production, and every user who runs into this will spend a session diagnosing it.

---

## 2. Full code-level inventory of `pipeline.py`

File has 633 lines. Key structures, with every caller.

### 2.1 Constructor state (lines 144-188)

```
self._dataflow         = dataflow               # passed through
self._redis_url        = redis_url              # DEAD. line 152.
self._max_concurrent   = max_concurrent
self._dev_mode         = dev_mode               # DEAD. line 154.
                                                # never read by any cache branch
                                                # (there is no cache branch)
self._exec_semaphore   = asyncio.Semaphore(...)
self._db_semaphore     = asyncio.Semaphore(...) # F5 budget, correct
self._queue            = asyncio.Queue(100)     # unused in current code
self._cache_data       : OrderedDict[str,bytes] # line 177 — the real cache
self._cache_hash       : Dict[str,str]          # line 180 — parallel dict
self._cache_metadata   : Dict[str,Dict[str,Any]] # line 181 — parallel dict
self._max_cache_entries = 10_000                # line 182 — bound
self._traces           = deque(maxlen=20)       # bounded trace storage
self._max_result_bytes = 10*1024*1024           # RT-6 size limit
```

Three parallel dicts keyed on the same `_cache_key(...)` string is a correctness and memory-footprint red flag. Any backend replacement must either preserve all three or fold them into a single entry type.

Note on `self._dev_mode`: stored at line 154, never read in the class body. It is also DEAD from the pipeline's perspective. The `dev_mode` branch semantics the docstring promises — "forces in-memory cache even if redis_url is provided" — do not exist because there is no non-in-memory path to force out of.

### 2.2 Cache operations (lines 230-268)

| Method                                                                              | Lines   | Signature | Sync/async                                        |
| ----------------------------------------------------------------------------------- | ------- | --------- | ------------------------------------------------- |
| `get_cached(product_name, params=None) -> Optional[Tuple[bytes, Dict]]`             | 230-239 | sync      | sync                                              |
| `set_cached(product_name, data_bytes, content_hash, metadata, params=None) -> None` | 241-261 | sync      | sync                                              |
| `_get_cached_hash(product_name, params=None) -> Optional[str]`                      | 263-268 | sync      | sync (private)                                    |
| `get_product_from_cache(product_name, params=None) -> Optional[PipelineResult]`     | 448-475 | sync      | sync (delegates to `get_cached` + `_deserialize`) |
| `invalidate(product_name, params=None) -> bool`                                     | 481-502 | sync      | sync                                              |
| `invalidate_all() -> int`                                                           | 504-516 | sync      | sync                                              |

Every cache operation is synchronous. This is the most important API fact in the report. Moving to Redis makes every one of these async — meaning every call site up the stack either becomes async itself or goes through an executor.

### 2.3 Call sites (exhaustive)

Produced by grep across `packages/kailash-dataflow/src/dataflow/fabric/`:

**`pipeline.py` internal callers** (must also migrate when signatures change):

- `pipeline.py:393` `existing_hash = self._get_cached_hash(product_name, params)` — inside `execute_product`, already `async`, so no caller surgery needed. Just add `await`.
- `pipeline.py:407` `self.set_cached(product_name, data_bytes, new_hash, metadata, params)` — inside `execute_product`, already `async`. Add `await`.
- `pipeline.py:455` `cached = self.get_cached(product_name, params)` — inside `get_product_from_cache`. `get_product_from_cache` is **currently sync** and therefore transitively becomes async.

**`pipeline.py` internal callers that currently sync and must become async**:

- `pipeline.py:448-475` `get_product_from_cache` — called by `runtime.py:511`, `runtime.py:566`, `fabric/serving.py:276`, `fabric/serving.py:393`. All are already inside `async` handlers, so the transition is `await`-insertion not architectural surgery.

**`fabric/runtime.py`**:

- `runtime.py:479` `cached = self._pipeline.get_cached(name)` — inside `_get_products_cache`, which is a **synchronous** method called from **synchronous** context during product context construction (lines 342, 385, 416). This is the one hard call site. The current code does synchronous cache reads during pipeline context setup. If `get_cached` becomes async, `_get_products_cache` must become async, and so must every `PipelineContext(products_cache=...)` call site.
  - `runtime.py:342` in `_prewarm_products` — already inside `async def`, fixable
  - `runtime.py:385` in `_prewarm_products_serial` — already async, fixable
  - `runtime.py:418` in `_on_source_change` — already async, fixable
- `runtime.py:493-514` `get_cached_product` — **already async**, delegates to the sync `get_product_from_cache`. Becomes `await self._pipeline.get_product_from_cache(...)`.
- `runtime.py:566` `cached = self._pipeline.get_cached(name)` — inside `product_info`, which is currently a **synchronous** public method (`def product_info`). This call appears twice in `product_info` (it checks `cached is not None` and then reads `cached[1]`). `product_info` is part of the `db.fabric.*` public API documented as the programmatic status endpoint (`runtime.py:520-538` similar shape). Making it async is a **public API break** unless we keep the sync method and cache the last-known-metadata.
- `runtime.py:575-599` `invalidate`, `invalidate_all` — currently synchronous public methods (`def invalidate`, `def invalidate_all`). Same API break concern as `product_info`.

**`fabric/serving.py`**:

- `serving.py:276` `cached = self._pipeline.get_cached(name)` — inside `async def handler`, fixable with `await`.
- `serving.py:393` `cached = self._pipeline.get_cached(name)` — inside `async def handler` (batch), fixable with `await`.

**`fabric/health.py`**:

- `health.py:85` `cached = self._pipeline.get_cached(name) if self._pipeline else None` — need to inspect enclosing function. If sync, another API break. (I will call this out as an unknown-sync in the fix outline; the pipeline specialist report mandate is not to write code but to flag all call sites. This one is the last sync callsite to verify.)

**`fabric/products.py`**:

- `products.py:261` `result = await self._fabric_runtime.get_cached_product(...)` — goes through `runtime.get_cached_product` which is already async. No change needed.

### 2.4 10MB size check, msgpack serialization, LRU eviction, `_cache_hash` dedup

Line-by-line of the behaviors that must survive any backend swap:

- **Size check** (`pipeline.py:361-379`): `if len(data_bytes) > self._max_result_bytes`, raises `ValueError`. Enforced **before** caching. This is a pipeline concern (RT-6), not a cache concern. It MUST stay in `execute_product`, not migrate into a cache backend. A backend must not silently accept larger payloads, and the backend should not re-check (double-check would mask a pipeline bug).
- **msgpack serialization** (`pipeline.py:79-104`): `_serialize`/`_deserialize` are module-level helpers. They convert Python objects to bytes and back. The backend's contract is `bytes in, bytes out`; serialization stays in `execute_product` / `get_product_from_cache`. This keeps the backend payload-format-agnostic and reusable.
- **Content hash** (`pipeline.py:107-109`): `_content_hash(data_bytes) -> str` is also module-level and pure. Stays where it is. Both backends receive the already-hashed string in `set_cached`.
- **LRU eviction** (`pipeline.py:257-261`): strictly in-memory concern. When using Redis, eviction is Redis's job (TTL or `maxmemory-policy`), not DataFlow's. The 10_000-entry cap is an OOM guardrail for the OrderedDict; on Redis, it becomes a TTL per key. The in-memory backend keeps the cap; the Redis backend does not need it.
- **`_cache_hash` dedup** (`pipeline.py:263-268, 393-416`): the critical semantic. `execute_product` reads the pre-existing hash, compares to the new hash, and **skips the cache write if they match** (`pipeline.py:415-416` `cache_action = "skip_unchanged"`). The purpose is to avoid re-serializing and re-writing identical content into the cache — which matters more for Redis than for the in-memory backend because (a) the serialized bytes are already in hand, and (b) avoiding a Redis round-trip is a meaningful latency win for the common no-op refresh case. Any backend replacement MUST expose a cheap `get_hash(key) -> Optional[str]` operation that does not transfer the full payload, otherwise the dedup optimization degenerates into "fetch entire payload to compare hashes" which is strictly worse than just writing every time.

### 2.5 Thread safety and asyncio safety of current code

The current code has **none** of either. `OrderedDict`, `dict`, and the parallel `_cache_hash` / `_cache_metadata` dicts are modified without any lock. This is technically safe under single-threaded asyncio as long as no `await` happens between the read of `_cache_data` and any subsequent reads from `_cache_hash`/`_cache_metadata` for the same key (because there is no interleaving). Inspecting `get_cached` (lines 230-239) — no `await`. `set_cached` (241-261) — no `await`. `execute_product` (274-442) — there are `await`s, and cache reads/writes happen at lines 393 and 407 (inside the same `async with self._exec_semaphore` block but with awaits between them on the product function, serialization, etc.).

The current single-dict safety argument breaks with Redis: once the backend is async, you can have another coroutine executing for the same product_name between `_get_cached_hash` and `set_cached`. This creates the **write-skew** scenario from section 6: two pipelines for the same product, one sees hash X, other sees hash X, both execute, both write, and the cache state is non-deterministic. Mitigation: either the dedup becomes "write if current hash in Redis differs at write time" (check-and-set via `WATCH`/`MULTI` or Lua script), or the semaphore is per-product-name (coalescing concurrent pipelines for the same product into one execution), or we accept last-writer-wins and document it. Recommendation in section 6.

### 2.6 Prewarm interaction (the impact-verse symptom)

`FabricRuntime.start()` at `runtime.py:317-350` calls `_prewarm_products` which iterates materialized products serially in a `for` loop (line 330) and `await`s `_pipeline.execute_product` on each. Each execution runs the full product function, serializes, checks size, hashes, and writes to the in-memory cache.

With 26 products over 6,481 participants × 3,545 orgs × 14 clusters and per-product DB queries, each pipeline takes on the order of 10-15s, so the whole `_prewarm_products` loop takes 4-6 minutes. Container Apps' default startup probe fires after ~4 minutes and the replica is killed. On restart the new replica starts from zero (per-process cache) and the crash loop is established.

The critical insight: **Redis backing does not fix this directly**. Prewarm is a leader-only operation, it still runs the pipelines, it still takes the same wall clock. What Redis backing fixes is everything after the first successful prewarm — replica 2, 3, 4, and every subsequent cold start benefits from the leader's cached results. Prewarm on non-leader replicas should become **lazy cache warming from Redis**, not pipeline re-execution. In the current code there is no such concept because there is no shared cache to warm from.

This changes the architecture of section 9's fix: prewarm on non-leader replicas should be "fetch existing Redis entries and validate staleness", not "re-execute pipelines". That is a different code path from anything currently in `runtime.py` and is worth calling out as a separate todo.

---

## 3. Architectural options

Four (not three — the fourth is critical and missing from the issue's framing).

### Option A: Minimal shim — `RedisBackedCache` alongside `InMemoryCache`, select in `__init__`

**What it is**: Introduce two new classes in `pipeline.py` (or a new sibling file `fabric/cache.py`): `_InMemoryFabricCache` and `_RedisFabricCache`, both exposing async `get_cached`, `set_cached`, `get_hash`, `invalidate`, `invalidate_all`. `PipelineExecutor.__init__` picks one based on `(dev_mode, redis_url)`. The existing `_cache_data`, `_cache_hash`, `_cache_metadata` dicts move behind `_InMemoryFabricCache`. `execute_product` stops calling `self.set_cached`/`self._get_cached_hash` and calls `self._cache.set`/`self._cache.get_hash` via `await`.

**Migration cost**:

- `pipeline.py`: ~150 lines of net change. New classes, rewrite of cache methods to delegate, `async` conversion of `get_product_from_cache`.
- `runtime.py`: 3 call sites become `await`. `product_info` / `invalidate` / `invalidate_all` public methods become async — breaking change.
- `serving.py`: 2 call sites become `await`.
- `health.py`: 1 call site, may need async conversion.
- Tests: every test in `tests/fabric/` that does `pipeline.get_cached(...)` synchronously has to be updated (~15 sites).

**API break risk**: **HIGH**. `db.fabric.product_info()`, `db.fabric.invalidate()`, `db.fabric.invalidate_all()` become async. Any downstream user calling these from sync context breaks. The documented programmatic API pattern is `runtime.py:520-538` `status()` which is sync; if we make peers async we fragment the API surface.

**Backward compatibility**: **Fragile**. We can keep sync wrappers on the outer public methods by storing a shadow copy of the metadata (not the data) in a local `dict[str, dict]` on `PipelineExecutor`, refreshed on every write. But that is two sources of truth and violates framework-first.

**Alignment with `leader.py`/`webhooks.py`**: Moderate. `leader.py` has `LeaderBackend` ABC with `RedisLeaderBackend` and `InMemoryLeaderBackend`. This Option A mirrors that pattern inside `pipeline.py` but does NOT share code with it. Separate classes, separate Redis client, separate connection pool.

**Cross-SDK symmetry**: Low. Rust `executor.rs` has a single `LruCache` struct with no trait abstraction. Cross-SDK parity requires the Rust side to be refactored to a trait-object cache.

**Verdict**: Fastest fix. Ships what the issue asks for. Does not address the framework-first violation (two cache systems in kailash-dataflow). **Not recommended as the terminal state.**

### Option B: Full backend abstraction — `FabricCacheBackend` ABC + pluggable injection

**What it is**: Define `FabricCacheBackend` ABC in `fabric/cache.py` with the exact async surface needed by `execute_product` and callers. Ship `InMemoryFabricCacheBackend` and `RedisFabricCacheBackend`. `PipelineExecutor` takes a `cache_backend: FabricCacheBackend` in `__init__` and does no construction logic itself. `FabricRuntime` constructs the backend based on `redis_url`/`dev_mode` and injects it. Tests can inject a `FakeFabricCacheBackend`. The `redis_url` parameter stays on `PipelineExecutor` only for backward compatibility with existing test constructors (deprecated alias that constructs the backend internally and logs a deprecation warning).

**Migration cost**: Same line count as Option A plus the ABC (~30 lines). Tests benefit — fake backend beats the real OrderedDict for isolation. Constructor-injected means `PipelineExecutor` has one fewer responsibility and one more constructor parameter.

**API break risk**: Same as Option A for the public `db.fabric.*` methods (unavoidable without shadow state). Additional risk: `PipelineExecutor(dataflow, redis_url=...)` existing constructor signature stays but emits a DeprecationWarning. Downstream users of `PipelineExecutor` directly (there are none outside tests as of this repo grep) are unaffected.

**Backward compatibility**: Better than A because the ABC gives us a stable surface to target. The sync public methods on `FabricRuntime` are still an unsolved problem.

**Alignment with `leader.py`/`webhooks.py`**: **HIGH**. `fabric/leader.py:35` already has `class LeaderBackend(ABC)` with `try_acquire`, `renew`, `release`, `get_leader`. `fabric/webhooks.py:39` already has `class _NonceBackend(ABC)` with `contains`, `add`. A `FabricCacheBackend(ABC)` is the third in a series and the fabric module finally becomes consistent: every cross-replica state store goes through an ABC with an in-memory and a Redis implementation.

**Cross-SDK symmetry**: High if the Rust side adopts a matching `trait FabricCacheBackend` with `InMemoryCacheBackend` and `RedisCacheBackend` implementations. Rust already has trait-object support in `crates/kailash-dataflow/src/executor.rs` via generics; the swap is more invasive than Python but produces the same architecture.

**Verdict**: Correct fix. Respects the existing fabric ABC patterns. Still fragments the cache story across `dataflow/cache/` (query cache, express cache) and `dataflow/fabric/` (product cache). **Recommended as the pragmatic terminal state for this issue** given Option D's blast radius.

### Option C: Engine-layer caching — move caching OUT of `PipelineExecutor` into `DataFlowEngine`

**What it is**: Extract fabric-product caching into `DataFlowEngine` so it applies uniformly to any DataFlow consumer, not just fabric products. `PipelineExecutor` receives a cache reference from the engine. The engine picks the backend.

**Migration cost**: Very high. `DataFlowEngine` currently has zero cache awareness (`dataflow/engine.py` grep returns zero matches for `cache`/`Cache`/`redis`/`Redis`; verified above). Adding it requires:

- New `engine.with_product_cache(...)` builder method.
- `DataFlow.start()` pulls the cache off the engine, passes to `FabricRuntime`, passes to `PipelineExecutor`.
- The express cache (`dataflow/cache/auto_detection.py`) and the fabric product cache converge into one concept. That has its own migration implications for anyone using `db.express.list(..., cache=...)` semantics today.

**API break risk**: Highest. Engine builder API grows. The `DataFlow(redis_url=...)` constructor parameter must route to the engine, not `FabricRuntime`.

**Backward compatibility**: Hard. The express cache and fabric cache have different TTL semantics (query TTL vs content-hash dedup), different invalidation semantics (query pattern-based vs per-product), and different keys (query fingerprint vs product_name+params). Unifying them in one Engine requires either two cache namespaces under one connection or two separate backends.

**Alignment with `leader.py`/`webhooks.py`**: Zero — those live in `fabric/`, the cache would live in the engine. That is the opposite of architectural consistency within fabric.

**Cross-SDK symmetry**: `kailash-rs` has `src/engine.rs`, `src/query_cache.rs`, and `src/fabric.rs` as separate concerns. Unification at the engine layer would be an equally large Rust refactor.

**Verdict**: **Architecturally tempting but wrong scope for this issue**. Issue #354 is about a broken fabric parameter. Option C is a unification of all caching in DataFlow. That is a design session (and probably an ADR), not a bug fix. Record it in section 8 as a future consideration but do not ship it as the fix for this issue.

### Option D (MISSING FROM ISSUE): Reuse `dataflow/cache/` directly

**What it is**: The issue reporter's Option A mental model is "add a Redis backend". The reality is that `dataflow/cache/auto_detection.py` already has `CacheBackend.auto_detect(redis_url=..., ttl=..., max_size=...)` returning either `AsyncRedisCacheAdapter` or `InMemoryCache`, both exposing an async surface (`get`, `set`, `delete`, `exists`, `clear_pattern`, `invalidate_model`). The fabric pipeline could drop its OrderedDict and parallel dicts entirely, store a single cache entry per product as `{bytes, hash, metadata}`, and delegate to the existing `CacheBackend`.

**Pros**:

- Framework-first compliance: one cache system in kailash-dataflow, not two.
- Zero new Redis code — reuses the already-tested `AsyncRedisCacheAdapter` / `RedisCacheManager`.
- TTL semantics come for free (`CacheBackend.auto_detect(ttl=product.staleness.max_age.total_seconds() * N)`).
- Invalidation comes for free (`await cache.delete(key)`, `await cache.clear_pattern("fabric:*")`).
- Same `InMemoryCache` fallback behavior — dev mode continues to work.

**Cons**:

- `AsyncRedisCacheAdapter` uses a `ThreadPoolExecutor` (`async_redis_adapter.py:72`) to wrap the sync `RedisCacheManager`. That is technically correct but adds a thread-pool hop that `redis.asyncio` would avoid. Performance overhead "1-2ms per operation" per the adapter's own docstring at line 42.
- The `AsyncRedisCacheAdapter` interface is `get(key) -> Any`, not `get_bytes(key) -> bytes + metadata`. The fabric cache needs to store three things per key (bytes, hash, metadata) and the existing `CacheBackend` stores one. Either we cram them into a dict and serialize with pickle (bad — opens pickle-deserialize-of-external-cache attack surface), or we store three keys per product (three round-trips per cache hit — bad latency), or we use msgpack-encoded triples and serialize the whole entry (fine, matches the current msgpack approach).
- Thread-pool overhead is acceptable for a cache that lives behind a pipeline that is already doing DB fan-out.

**Migration cost**: Same surface as Option B, but the "write a Redis backend" work is already done. The actual change is: `PipelineExecutor.__init__` takes a `CacheBackend` (from `dataflow.cache.auto_detection`) or constructs one from `redis_url`, and `get_cached`/`set_cached`/`_get_cached_hash`/`invalidate`/`invalidate_all` delegate.

**API break risk**: Same as Option B — sync public methods become async. Unavoidable.

**Cross-SDK symmetry**: Unclear. `kailash-rs` does not have an equivalent `CacheBackend` abstraction at the crate level (grep for `CacheBackend` in `kailash-rs/crates/` returns nothing). The Rust side must define one to achieve parity, which is a larger Rust refactor.

**Verdict**: **RECOMMENDED as the terminal Python-side fix**. Combine Option B's ABC discipline (for test injection and fabric-module consistency) with Option D's reuse of `dataflow/cache/` as the concrete Redis implementation. Specifically: `FabricCacheBackend(ABC)` in `fabric/cache.py` with one implementation (`CacheBackendFabricAdapter`) that wraps `dataflow.cache.auto_detection.CacheBackend`. Tests can substitute an in-memory `FabricCacheBackend` directly. Production uses the wrapper around the existing Redis infrastructure.

### Option selection matrix

| Criterion                              | A: shim | B: ABC | C: engine | D: reuse cache/ |
| -------------------------------------- | ------- | ------ | --------- | --------------- |
| Fixes the reported bug                 | ✓       | ✓      | ✓         | ✓               |
| Framework-first compliant              | no      | no     | ✓         | ✓               |
| Aligned with `leader.py`/`webhooks.py` | partial | ✓      | no        | ✓               |
| Reuses existing `dataflow/cache/`      | no      | no     | partial   | ✓               |
| Test injectability                     | no      | ✓      | ✓         | ✓               |
| Rust parity straightforward            | partial | ✓      | no        | partial         |
| Scope matches issue                    | ✓       | ✓      | no        | ✓               |
| Migration cost                         | low     | medium | high      | medium          |

**Recommendation: Option D (wrapping the existing `CacheBackend`) inside an Option B ABC (`FabricCacheBackend`)**. One implementation class bridges fabric to the existing cache layer; one test fake implements the ABC directly.

---

## 4. Cross-SDK inspection (MANDATORY per `rules/cross-sdk-inspection.md`)

### 4.1 Does kailash-rs have the same bug?

**YES**, identically, with the additional indignity that the Rust side does not even pretend.

Evidence (`/Users/esperie/repos/loom/kailash-rs/crates/kailash-dataflow/src/executor.rs`):

- Lines 32-54: `ExecutorConfig` has `max_concurrency`, `max_cache_entries`, `max_result_bytes`, `max_traces`. **No `redis_url` field, no Redis option of any kind.**
- Lines 102-149: `LruCache` struct backed by `HashMap<String, CacheEntry>` + `VecDeque<String>`. 100% in-process.
- Lines 94-99: `PipelineExecutor` owns `cache: Arc<Mutex<LruCache>>`. No trait abstraction, no backend injection.
- Verified: `grep -rn "redis\|Redis" crates/kailash-dataflow/src/` returns **zero matches**.

Semantic divergence from Python:

- Python: `redis_url` exists as a parameter and is silently ignored. User expects Redis; gets in-memory.
- Rust: there is no `redis_url` parameter at all. User cannot even request Redis. Behavior is honestly in-memory.

Neither is correct. Python has the docstring-lies variety of stub; Rust has the missing-feature variety. Per EATP D6 (matching semantics), this divergence is itself a violation: a fabric product workflow ported from Python to Rust changes behavior (from broken-in-memory to intentionally-in-memory) without any notification.

### 4.2 Cross-SDK issue required

**YES**. File `esperie-enterprise/kailash-rs#<new>` with:

- Title: `feat(dataflow-fabric): add Redis-backed PipelineExecutor cache (cross-SDK alignment)`
- Label: `cross-sdk`
- Body: "Cross-SDK alignment with terrene-foundation/kailash-py#354. The Rust `PipelineExecutor` in `crates/kailash-dataflow/src/executor.rs` is pure in-memory with no configuration path to request Redis. When kailash-py#354 lands, kailash-rs must gain an equivalent `CacheBackend` trait with `InMemoryCacheBackend` + `RedisCacheBackend` implementations and an `ExecutorConfig.cache_backend` field."

Do NOT file the Rust issue until Python lands — per `artifact-flow.md`, BUILD repos must not sync directly; coordination goes through `loom/`. The Rust issue is **a follow-up** to the Python fix, not a parallel.

### 4.3 Blast radius in kailash-rs

Once the Rust side adopts the trait, the affected crates are:

- `kailash-dataflow/src/executor.rs` — new trait, two impls, swap `cache: Arc<Mutex<LruCache>>` for `cache: Arc<dyn CacheBackend>`.
- `kailash-dataflow/src/fabric.rs:168,687,884,1481` — `executor: Arc<PipelineExecutor>` construction sites need the new config.
- `kailash-dataflow/Cargo.toml` — add `redis = { version = "0.27", features = ["tokio-comp"] }` as an optional feature.
- Rust tests for fabric — add a `RedisCacheBackend` integration test under `crates/kailash-dataflow/tests/`.

---

## 5. TTL and invalidation semantics

### 5.1 How staleness works today

`StalenessPolicy` (`fabric/config.py:167-172`):

```
max_age: timedelta = field(default_factory=lambda: timedelta(minutes=5))
on_stale: str = "serve"      # "serve" | "error"
on_source_error: str = "serve_stale"  # "serve_stale" | "error"
```

Current behavior in `serving.py:292-306`:

1. On GET `/fabric/<product>`, check `pipeline.get_cached(name)`.
2. Parse `cached_at` from metadata.
3. Compute `age_seconds = now - cached_at`.
4. If `age_seconds <= max_age.total_seconds()`, freshness = `"fresh"`.
5. Otherwise freshness = `"stale"`.
6. On stale, the policy says `serve` (current default) — return the data with a `_HEADER_FRESHNESS: stale` header and let the caller decide.

**Key observation**: the cache does NOT expire entries. It holds them indefinitely (up to `_max_cache_entries = 10_000`). Staleness is a **query-time** computation on the metadata, not a **storage-time** eviction. This is important because it means TTL semantics in Redis are an ADDITIVE constraint, not a replacement.

### 5.2 Relationship to `_cache_hash` dedup

The content-hash dedup (`pipeline.py:392-416`) does two things:

1. Compute the SHA-256 of the new serialized bytes.
2. Compare to the stored hash.
3. If unchanged, skip the cache write but still record a trace (`cache_action = "skip_unchanged"`, `content_changed = False`).

The reason this matters for Redis: if the new payload is byte-identical to the cached payload, writing it to Redis is pointless network traffic AND the `cached_at` timestamp **should not refresh** — otherwise a stable product that never changes would appear to refresh every staleness window, which is a lie to downstream consumers. Rust actually handles this correctly at `executor.rs:244-260`: `old_hash_matches` branch updates `entry.cached_at = Instant::now()` on dedup hit — which is the OPPOSITE of Python. Python leaves `cached_at` as-is on dedup (pipeline.py:415-416 `cache_action = "skip_unchanged"`, no write). Rust refreshes the timestamp. **This is a cross-SDK semantic divergence independent of issue #354 and should be called out separately** — but not fixed in this issue because it's a distinct concern.

**For the fix**: the Redis backend MUST preserve Python's current semantics (hash-unchanged = no-op), which means:

- The backend needs a cheap `get_hash(key) -> Optional[str]` method that does NOT fetch the payload.
- Implementation: store each product's hash in a parallel Redis key `fabric:product:hash:{key}` or `HGET` a hash field. `HGET` is the cheaper option because it avoids a second Redis key.
- Schema recommendation in section 7.

### 5.3 Reporter's `max_age * N` proposal

The reporter suggests Redis TTL = `product.staleness.max_age * N` (where N is a "safety factor"). Analysis:

**Pros of TTL-at-backend**:

- Prevents stale-forever entries when a product is removed or the DataFlow instance is renamed.
- Lets Redis do the eviction work instead of depending on the single-replica `_max_cache_entries` cap.

**Cons of making TTL = max_age**:

- Current Python semantics serve STALE data with a `freshness: stale` header. If the Redis TTL expires the entry outright, the serving layer can no longer serve stale — it has to cold-start the pipeline. **That is a behavior regression**.
- Some products have `on_stale = "serve"` (the default) which is a contract that stale data is ALWAYS available. Redis TTL shorter than "forever" breaks this contract.

**Recommendation**: TTL = `max(staleness.max_age * N, _FABRIC_MIN_TTL_SECONDS)` where N defaults to 24 (so a 5-minute max_age gives a 2-hour Redis TTL), and `_FABRIC_MIN_TTL_SECONDS = 3600` (1 hour). Rationale:

- N=24 preserves the "stale data is available on request" contract for at least 24 staleness windows.
- 1-hour floor ensures that even a product with `max_age = 1 second` doesn't churn Redis for no reason.
- Document in the product registration that `on_stale = "serve"` is best-effort beyond `max_age * N` — after that the entry is evicted and the next request warms lazily.
- The Redis TTL is NOT the fabric staleness. The fabric staleness stays a metadata computation at serving time. Redis TTL is a **garbage collection window**, not a freshness signal.

### 5.4 Content-hash dedup across replicas

Can be preserved in Redis. The dedup key lookup becomes:

```
old_hash = await cache.get_hash(key)   # Redis HGET fabric:product:<key> hash
if old_hash == new_hash: skip write
```

Replica B executing the same product with the same data reads the same Redis hash and skips. This is actually **better** than current in-memory dedup — today each replica has its own `_cache_hash` dict and each replica performs its own dedup locally, so if replica A just wrote the product and replica B's change detector fires a second later, replica B will serialize and hash independently. Both will reach dedup-hit independently. The wire traffic is duplicated; with shared Redis, replica B's dedup check is a single `HGET` before serialization. But read on — the leader-only-writes strategy in section 6 is even better.

---

## 6. Multi-replica correctness

Shared Redis fixes the per-process-cache bug. It introduces new race conditions that must be accounted for.

### 6.1 Two replicas running pipelines for the same product concurrently

Today this is not a concern because change-detector polls only run on the leader (`runtime.py:195-208`). But:

- Webhook events are accepted by **all workers** (`runtime.py:210-214`, RT-2), and the current code forwards them via `_on_source_change` which calls `self._pipeline.execute_product` directly (`runtime.py:401-427`). With redis-backed cache, replica A and replica B can both receive webhooks for the same source (e.g., duplicate delivery), both dedup by nonce, both fire pipelines, both write to Redis. Last write wins.
- Model-write events (`_on_model_write` at `runtime.py:452-470`) also fire `_on_source_change` on any replica that has the write, not just the leader.

So "leader-only writes" is NOT currently the case for webhook-triggered and event-bus-triggered refreshes. Making it so would require either:

**Option R1: Leader-only pipeline execution**. All non-leader replicas forward triggers to the leader via a Redis pub-sub channel. The leader is the single writer. This aligns with how leader election is used elsewhere in fabric. Downside: leader becomes the single point of pipeline throughput; losing leader costs a full failover window of pipeline refreshes.

**Option R2: Per-product distributed lock**. Before executing `execute_product`, acquire a short-lived Redis lock keyed on `fabric:lock:product:<key>`. First winner runs, others get the cached result after the winner writes. Downside: adds a lock round-trip to the hot path. Upside: any replica can write.

**Option R3: Last-writer-wins with content-hash dedup as the drift detector**. Let both replicas run; the one that finishes last overwrites. If the product is deterministic, the results are identical and content-hash dedup catches it (no actual Redis write on the second one). If the product is non-deterministic (e.g., timestamp-based), the state reflects the latest execution — which is what the user probably wants anyway. This is the simplest option. Downside: wasted CPU on duplicate executions. Upside: zero new infrastructure.

**Recommendation**: **R3 (last-writer-wins with hash-based dedup)** for this fix, with a note in the docstring that replica-level pipeline deduplication is a future improvement. Rationale: the semaphore at `pipeline.py:304` already caps concurrent execution per replica; the content-hash dedup already catches duplicate-deterministic work; the operational cost of duplicate executions for the rare case of concurrent webhooks-on-the-same-event is low. R1 introduces leader-chokepoint risk; R2 introduces lock-wait latency on every cache write. Neither is worth it for a bug fix whose primary goal is "stop lying about Redis".

Document this decision explicitly in the fix. Operators who hit the duplicate-execution case will see `cache_action = "write"` on replica A and `cache_action = "skip_unchanged"` on replica B (because A wrote first and B computed the same hash). That's a legible trace.

### 6.2 Content-hash dedup across replicas

Covered in 5.4. Works as long as the backend exposes `get_hash(key)`.

### 6.3 `_RedisDebouncer` interaction

`_RedisDebouncer` does not exist. `InMemoryDebouncer` at `pipeline.py:581-633` uses `asyncio.TimerHandle` per product name. Cross-replica debounce does not exist today — each replica debounces its own observed events. This is not in scope for issue #354 (which is about the cache) but IS a distinct stub in the same file (same class of problem), and the fix design should acknowledge it so the next person doesn't re-open the same file and find another broken promise.

For multi-replica debounce to be correct, the debouncer state needs Redis too, using a pattern like: `SET fabric:debounce:<product_name> <replica_id> EX <window> NX`. First replica to SET within the window wins. Others' SET fails and they short-circuit. This is a **separate issue**. The dataflow-specialist report recommends filing a follow-up issue for `_RedisDebouncer` and NOT fixing both in the same PR — the test surface and the risk budget are different.

### 6.4 Leader-only writes vs all-replica reads

**Reads**: all replicas MUST be able to read the Redis cache. This is the whole point.
**Writes**: all replicas currently write (webhook, event bus, prewarm-on-leader). See 6.1. Recommendation: keep write-everywhere with R3.

### 6.5 Startup race: prewarm on leader vs read on followers

The timing window:

1. Replica A starts, elects leader, starts `_prewarm_products` (5+ minutes).
2. Replica B starts 30s later, does NOT elect leader, skips prewarm, moves directly to serving.
3. A request hits replica B before replica A's prewarm finishes. Replica B's `get_cached` returns None. With the current Container Apps crash loop, replica B serves cold-start 202 "warming" responses for the 5-minute prewarm window.

With Redis backing, replica B's prewarm does NOT need to re-execute pipelines. Replica B's prewarm should become: "ask Redis for the entry; if present and non-stale, record the metadata locally for traces; otherwise defer". That means prewarm is **effectively free** on non-leader replicas, which is what the reporter needs to escape the crash loop.

**Concrete: `FabricRuntime.start()` must be aware of leader-vs-follower prewarm semantics**:

- Leader: execute pipelines to populate Redis, same as today.
- Follower: check Redis for each materialized product; if present, record in local trace storage; otherwise no-op (the serving layer will return 202 on a miss, same as today).

This is the architectural insight section 2.6 called out. It is NOT part of the minimum fix. But the operator experience of "Container Apps startup probe no longer kills followers" depends on it. The fix should include it OR explicitly document that follower startup still costs a 202 window.

**Recommendation**: include follower-side lazy cache warmup in the fix. It is low-risk because it only adds a Redis-read path that didn't exist before.

---

## 7. Redis key schema proposal

Precise schema. Every Redis operation in the fabric-product cache uses these keys.

### 7.1 Key layout

```
Prefix:  fabric:product:<instance_name>:

Per product entry (Redis HASH, one key):
    fabric:product:<instance_name>:<product_name>[:<params_hash>]
        field: data        -> msgpack bytes (serialized product result)
        field: hash        -> str (hex SHA-256 of data bytes)
        field: cached_at   -> ISO-8601 UTC timestamp
        field: pipeline_ms -> int (pipeline duration)
        field: size_bytes  -> int (len of data)
        field: run_id      -> str (pipeline run id)
    TTL: max(max_age * N, _FABRIC_MIN_TTL_SECONDS), see section 5.3.
```

Rationale for one HASH per product:

- Single `HGETALL` returns everything the serving layer needs (data + metadata).
- Single `HGET fabric:product:...:<name> hash` for the dedup fast path — **no payload transfer**.
- Single `HMSET` on writes, one TTL on the whole entry.
- Invalidate all: `SCAN MATCH fabric:product:<instance_name>:* + DEL`. Avoid `KEYS`.
- Cross-product enumeration for `_get_products_cache`: same `SCAN MATCH` pattern. One `MGET` does not work because each is a hash, so it's `SCAN` + `HGETALL`. Accept the N-round-trip cost for status/trace endpoints — they are not hot-path.

### 7.2 Instance name

`<instance_name>` is crucial — two DataFlow instances pointed at the same Redis must not collide. Source the instance name from `DataFlow.config.instance_name` (exists? if not, default to `os.environ.get("FABRIC_INSTANCE_NAME", "default")` with a loud WARN log if default is used in production). Document that multi-tenant Redis MUST set a unique instance name per deployment.

### 7.3 Params hash for parameterized products

The current `_cache_key` at `pipeline.py:119-124` does:

```
f"{product_name}:{canonical_json(params)}"
```

where `canonical_json` is `json.dumps(params, sort_keys=True, default=str)` at line 112-116. For Redis keys this is problematic:

- Key length is unbounded (params can be arbitrary dicts).
- Special chars (colons, spaces, unicode) in param values could confuse operators reading `redis-cli KEYS`.
- Very long keys hurt Redis memory and network.

**Change**: hash the canonical JSON with SHA-256, take the first 16 hex chars as the `params_hash`. Collision probability at 10K keys per product is 10^-29 — acceptable.

Final key format: `fabric:product:<instance_name>:<product_name>` for parameterless products, `fabric:product:<instance_name>:<product_name>:<params_hash_16>` for parameterized.

### 7.4 Serialization format

- `data` field: msgpack bytes (matches current in-memory format; no change to `_serialize`/`_deserialize`).
- `hash` field: hex string (matches current `_content_hash`).
- `cached_at`: ISO-8601 string (matches current metadata).
- Numeric fields: Redis integers (msgpack here is overkill).

No pickle. Ever.

### 7.5 TTL

- Product entry TTL: `max(product.staleness.max_age.total_seconds() * 24, 3600)` (1 hour floor, 24x multiplier). See section 5.3.
- Configurable via `FabricCacheBackend` constructor parameter `ttl_multiplier` (default 24) and `ttl_floor_seconds` (default 3600). Operators who need different retention can override.

### 7.6 Locking (none, per section 6.1 R3 recommendation)

No distributed locking. The content-hash dedup acts as the idempotence mechanism. Document.

---

## 8. Dev mode semantics

Today: `dev_mode=True` stored on `PipelineExecutor._dev_mode` at `pipeline.py:154` and **never read**. The docstring at `pipeline.py:140-141` says `dev_mode` forces in-memory "even if redis_url is provided". That branch does not exist because there is no non-in-memory path.

### 8.1 Proposed semantics

Keep the `dev_mode=True forces in-memory` contract, because operators testing locally may not want their dev cache writes to pollute a shared Redis. But ALSO allow dev_mode + redis_url to mean "use Redis with a dev-specific key prefix" for the rare case of testing Redis integration locally.

Decision matrix for `PipelineExecutor.__init__`:

| dev_mode | redis_url     | Backend selected                                                                                                                                                                 |
| -------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| False    | None          | InMemoryFabricCacheBackend                                                                                                                                                       |
| False    | "redis://..." | RedisFabricCacheBackend(instance_name=<config>)                                                                                                                                  |
| True     | None          | InMemoryFabricCacheBackend                                                                                                                                                       |
| True     | "redis://..." | InMemoryFabricCacheBackend **+ WARN log** explaining that dev_mode forces in-memory; if the operator explicitly wants Redis-in-dev they must pass `dev_mode=False`. No new flag. |

### 8.2 Logging

On backend selection, log at DEBUG (matches `leader.py:177`):

```
"PipelineExecutor cache backend: %s (redis_url=%s, dev_mode=%s)"
```

where `redis_url` is masked (just the host:port, not credentials). Use the existing `mask_sensitive_values` helper referenced at `core/engine.py:995`.

### 8.3 Operator escape hatch

Environment variable: `FABRIC_CACHE_BACKEND` with values `memory` / `redis` / `auto` (default `auto` = current behavior). Lets operators override in containers without redeploy. Document in the rule file and the fabric guide.

---

## 9. Concrete fix outline (NO code, just structure)

### 9.1 New module: `packages/kailash-dataflow/src/dataflow/fabric/cache.py`

- `FabricCacheBackend(ABC)` with async methods:
  - `async def get(key: str) -> Optional[Tuple[bytes, str, Dict[str, Any]]]` returning `(data_bytes, content_hash, metadata)` or None
  - `async def get_hash(key: str) -> Optional[str]` — dedup fast path, cheaper than `get`
  - `async def set(key: str, data_bytes: bytes, content_hash: str, metadata: Dict[str, Any]) -> None`
  - `async def invalidate(key: str) -> bool`
  - `async def invalidate_all(pattern: str) -> int`
  - `async def keys_matching(pattern: str) -> List[str]` — for status endpoints
  - `async def close() -> None`
- `InMemoryFabricCacheBackend(FabricCacheBackend)`:
  - Stores a single `OrderedDict[str, _FabricCacheEntry]` (not three parallel dicts).
  - Implements LRU eviction with `_max_entries` (default 10000, kept from current behavior).
  - Async-over-sync (methods are `async def` but do no awaiting).
- `RedisFabricCacheBackend(FabricCacheBackend)`:
  - Constructs `redis.asyncio.from_url(redis_url)` lazily on first use (matches `leader.py:62-72` pattern).
  - Uses the schema from section 7.
  - `close()` closes the client.
  - All operations are real Redis round-trips. No ThreadPoolExecutor.
- Private dataclass `_FabricCacheEntry` holding `bytes, str (hash), Dict[str, Any]` — the three-field entry that replaces today's three parallel dicts.

**Why not delegate to `dataflow.cache.auto_detection.CacheBackend`**: after a closer read of `async_redis_adapter.py`, the `AsyncRedisCacheAdapter` uses a ThreadPoolExecutor (line 72) wrapping a sync `RedisCacheManager`. That is wasteful when fabric is fully-async end-to-end. Better to implement `RedisFabricCacheBackend` directly against `redis.asyncio`, matching `RedisLeaderBackend` (`leader.py:55-105`). The framework-first argument is "reuse the Redis client code", not "reuse the thread-pool adapter". The actual Redis client is `redis-py`; we use its async entry point directly, same as `leader.py` already does.

**Note**: this means the proposed fix is closer to "Option A/B with borrowed patterns from `leader.py`" than "Option D with CacheBackend reuse". The CacheBackend reuse looked attractive on paper but the thread-pool overhead makes it the wrong choice for a hot path. **Revised recommendation: Option B + Leader-pattern Redis client.**

### 9.2 Changes to `fabric/pipeline.py`

- Line 8: update module docstring. Remove "future extension" comment at line 227.
- Line 137-142: update class docstring to reflect actual behavior.
- Line 147-182: replace the OrderedDict state with `self._cache: FabricCacheBackend`. Remove `_cache_data`, `_cache_hash`, `_cache_metadata`. Keep `_max_cache_entries` only if the caller doesn't inject a backend (for backward compat in tests).
- Line 230-268: `get_cached`, `set_cached`, `_get_cached_hash` become async thin wrappers over `self._cache`. Signatures become `async`.
- Line 274-442: `execute_product` already async. Lines 393, 407 gain `await`.
- Line 448-475: `get_product_from_cache` becomes async. Line 455 gains `await`.
- Line 481-516: `invalidate`, `invalidate_all` become async.
- Line 581-633: `InMemoryDebouncer` untouched in this fix. Add a docstring note: "Debouncer Redis backend is NOT implemented. Multi-replica debounce is a separate issue. See #<followup>."
- Logging: add DEBUG log at backend selection in `__init__`.
- 10MB size check stays in `execute_product` at line 361-379. Backend never receives oversize payloads.
- msgpack `_serialize`/`_deserialize` stay as module-level helpers at lines 79-104. Backend receives bytes.

### 9.3 Changes to `fabric/runtime.py`

- Line 69-81: `FabricRuntime` gains an optional `cache_backend` parameter for test injection (default None, constructs from `redis_url` + `dev_mode`).
- Line 170-174: `PipelineExecutor(...)` construction passes the resolved backend, not just `redis_url`.
- Line 211-214: `WebhookReceiver(...)` construction — pass `redis_client` when `redis_url` is set. **This is a SECOND BUG FIX** inside the same PR because webhook nonce dedup is also broken. Extract a helper `_get_or_create_redis_client()` that is reused for webhook nonce AND cache.
- Line 317-350 `_prewarm_products`: add follower-side branch. If `self._leader.is_leader`, run pipelines (current behavior). If not leader, call `await self._pipeline.warm_from_cache()` which iterates materialized products and does a cheap `await self._pipeline.get_cached(name)` on each. Log found/missing.
- Line 395-427 `_on_source_change`: no change. Last-writer-wins per section 6.1 R3.
- Line 475-491 `_get_products_cache`: becomes async. Every caller at lines 342, 385, 418 already async — just add `await`.
- Line 566-573 `product_info`: synchronous public method uses `_pipeline.get_cached` synchronously. **Breaking API change**. Options: (a) make async; (b) keep sync and store a shadow metadata dict in `FabricRuntime`; (c) deprecate and add `async def product_info_async`. **Recommendation: (a), make async**, with a release note in CHANGELOG. The only caller is operator-facing status and it should be async anyway given the broader fabric runtime is async.
- Line 575-589 `invalidate`, line 591-599 `invalidate_all`: same as `product_info` — async-ify.

### 9.4 Changes to `fabric/serving.py`

- Line 276, 393: add `await`.

### 9.5 Changes to `fabric/health.py`

- Line 85: inspect enclosing function. Likely becomes async or needs a shadow metadata store. To verify in implementation phase.

### 9.6 Changes to `core/engine.py`

- Line 2015-2019: `redis_url` resolution already done. No changes needed beyond wiring.

### 9.7 Test plan — TIER 2 REAL REDIS MANDATORY (`.claude/rules/testing.md`)

New integration tests under `packages/kailash-dataflow/tests/fabric/`:

1. `test_fabric_cache_redis.py` (NEW, Tier 2 — real Redis via docker-compose):
   - `test_redis_backend_writes_and_reads` — PipelineExecutor with `redis_url=fixture`, execute a product, verify Redis has the expected key with HGETALL.
   - `test_redis_backend_dedup_on_unchanged` — run pipeline twice with deterministic product function, verify second run has `cache_action=skip_unchanged`, verify Redis key was NOT overwritten (check `ttl` stays close to full).
   - `test_redis_backend_multi_replica_read` — two PipelineExecutor instances sharing the same Redis URL. Replica A writes, replica B reads without executing.
   - `test_redis_backend_ttl_applied` — verify TTL is set to `max(max_age * 24, 3600)`.
   - `test_redis_backend_invalidate_removes_key` — call `invalidate()`, verify Redis key gone.
   - `test_redis_backend_invalidate_all_scans` — populate multiple products, `invalidate_all()`, verify all fabric keys gone and UNRELATED keys preserved.
   - `test_redis_backend_parameterized_products` — verify params_hash key format.
   - `test_dev_mode_forces_in_memory_even_with_redis_url` — pass both, verify in-memory and WARN log emitted.
   - `test_follower_prewarm_reads_from_redis` — start two `FabricRuntime` instances, first becomes leader and prewarms, second becomes follower and its prewarm reads from Redis without executing pipelines. **This is the impact-verse regression test**.
   - `test_content_hash_dedup_across_replicas` — both replicas compute same product, both dedup against same Redis hash, no duplicate writes.
2. `test_fabric_webhook_nonce_redis.py` (NEW, Tier 2 — real Redis):
   - Regression for the second bug — `WebhookReceiver` with `redis_client` is wired from `FabricRuntime.start()`. Two replicas both receive the same delivery, only one processes it.
3. `test_fabric_cache_memory.py` (NEW, Tier 1 — no Redis):
   - Tests `InMemoryFabricCacheBackend` directly. LRU eviction, max_entries cap, dedup semantics.
4. Existing `test_fabric_critical_bugs.py`, `test_fabric_cache_control.py`, `test_fabric_integration.py`:
   - Every `PipelineExecutor(dataflow=db, dev_mode=True)` stays. `dev_mode=True` keeps in-memory, no behavior change.
   - Every `pipeline.get_cached(...)` becomes `await pipeline.get_cached(...)`. ~15 sites.
   - Every `pipeline.set_cached(...)` becomes `await pipeline.set_cached(...)`.
   - Every `pipeline.invalidate(...)` becomes `await pipeline.invalidate(...)`.

Test infrastructure:

- `packages/kailash-dataflow/tests/conftest.py` gains a `redis_url` fixture pointing at `docker-compose.test.yml` Redis. Pattern: `redis://localhost:6380/1` with a namespace prefix per test to avoid cross-test pollution.
- Tier 2/3 testing rules forbid mocking Redis; use the real container.

### 9.8 Documentation updates

- `packages/kailash-dataflow/CHANGELOG.md` — new entry: "Fix: fabric product cache now honors `redis_url` (#354)". Note breaking change: `FabricRuntime.product_info`, `FabricRuntime.invalidate`, `FabricRuntime.invalidate_all` became async. Provide migration snippet.
- `packages/kailash-dataflow/docs/` (if applicable) — fabric reference needs an explicit "Cache backend" section documenting the env var and constructor parameters.
- `.session-notes` and `workspaces/issue-354/` updates happen in `/implement` phase.

### 9.9 Observability changes

Every backend selection logs at DEBUG (`leader.py` pattern). Every cache write/read WARN on Redis connection errors with actionable messages ("Redis is configured but unreachable at <masked_url>; falling back to in-memory for this pipeline execution. Subsequent requests on other replicas will not see this write."). The fallback is a last-resort — if Redis is down for more than N consecutive operations, the backend should emit an ERROR and surface in `fabric.status()` as `cache_backend_health: "degraded"`.

Correlation: every cache operation log line carries `product_name` and `params_hash` fields. Metric counters: `fabric_cache_hits_total`, `fabric_cache_misses_total`, `fabric_cache_dedup_skips_total`, `fabric_cache_writes_total`, `fabric_cache_errors_total`. Register in `fabric/metrics.py`.

---

## 10. Blast radius — other fabric files accepting `redis_url` without using it

Grep across `packages/kailash-dataflow/src/dataflow/fabric/`:

| File                                                                                                                                                                                                               | Accepts `redis_url`?                        | Uses it?                                                     | Verdict                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------- |
| `fabric/pipeline.py:147`                                                                                                                                                                                           | yes                                         | **no**                                                       | **BUG (this issue)**                      |
| `fabric/runtime.py:69`                                                                                                                                                                                             | yes                                         | forwards to `PipelineExecutor` + `LeaderElector`             | partial — pipeline broken, leader correct |
| `fabric/leader.py:141`                                                                                                                                                                                             | yes                                         | yes (`RedisLeaderBackend` via `aioredis.from_url`)           | correct                                   |
| `fabric/webhooks.py`                                                                                                                                                                                               | no (accepts `redis_client` not `redis_url`) | `_RedisNonceBackend` uses the passed client correctly        | **correct, but never wired** — see below  |
| `fabric/change_detector.py`                                                                                                                                                                                        | grep: no `redis_url` parameter              | N/A                                                          | N/A                                       |
| `fabric/scheduler.py`                                                                                                                                                                                              | grep: no `redis_url` parameter              | N/A                                                          | N/A                                       |
| `fabric/serving.py`                                                                                                                                                                                                | grep: no `redis_url` parameter              | N/A                                                          | reads pipeline cache                      |
| `fabric/auth.py`                                                                                                                                                                                                   | no                                          | deliberately in-memory only ("NEVER Redis", `auth.py:9,218`) | correct — tokens must not be persisted    |
| `fabric/config.py`, `fabric/context.py`, `fabric/consumers.py`, `fabric/products.py`, `fabric/health.py`, `fabric/ssrf.py`, `fabric/metrics.py`, `fabric/sse.py`, `fabric/testing.py`, `fabric/mcp_integration.py` | no `redis_url`                              | N/A                                                          | N/A                                       |

### 10.1 Additional findings outside `pipeline.py`

**Finding A — webhook nonce dedup**: `fabric/webhooks.py:73-108` has a correct `_RedisNonceBackend` implementation. `fabric/webhooks.py:170-188` `WebhookReceiver.__init__` accepts `redis_client`. **`fabric/runtime.py:211-214` does not pass it**. In every current deployment, webhook nonce deduplication silently falls back to `_InMemoryNonceBackend` (`webhooks.py:49-70`), meaning:

- Two replicas both receive the same webhook delivery-id (Github docs recommend delivery retries up to 3x).
- Both pass HMAC + timestamp + nonce checks independently (each replica has its own in-memory nonce set).
- Both fire `_on_webhook_event` callback.
- Both trigger pipeline refreshes.

Today this is masked by the in-memory cache (each replica writes to its own cache so no corruption). Once the Redis cache lands, this becomes a visible duplicate-write with content-hash dedup catching the second one — which is fine but is wasted CPU. The fix is trivial: instantiate the Redis client in `FabricRuntime.start()` and pass to both `WebhookReceiver` and the new `RedisFabricCacheBackend`. Do it in the same PR.

**Finding B — `_RedisDebouncer` is vaporware**: `fabric/pipeline.py:581-633` only has `InMemoryDebouncer`. The docstring at line 582 says "Fallback debouncer for dev mode when Redis is not available", implying a primary Redis debouncer. There is none. Grep: `grep -rn "RedisDebouncer" packages/kailash-dataflow/` returns zero. This is the second `redis_url`-adjacent lie in the same file. It is NOT part of this fix — file as a follow-up issue tagged `dependency-of-354` with suggested pattern: `SET fabric:debounce:<key> <replica_id> NX EX <window>`.

**Finding C — `InMemoryDebouncer` is never used by `PipelineExecutor`**. The class is defined in `pipeline.py:581` but `PipelineExecutor` never instantiates it. Grep for `InMemoryDebouncer(` across the fabric module: zero instantiations. It's dead code within the file, waiting for a consumer that was apparently planned and never wired. **This is a third stub** — a class that exists to satisfy a reference that isn't made. Either delete it (zero-tolerance.md Rule 2) or wire it (some `_on_source_change` path ought to be debouncing but isn't).

**Finding D — `_queue` is also dead**: `pipeline.py:173` `self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=100)` — grep for `self._queue` in `pipeline.py`: exactly one match at line 173. Declared, never used. Another orphaned scaffold from the original TODO-11 design that nobody finished. Delete as part of this PR.

**Finding E — `_dev_mode` is dead**: `pipeline.py:154` stores `dev_mode`, never reads it in `pipeline.py`. In the proposed fix, it becomes live (backend selection). Until then it's dead state.

### 10.2 Summary of dead/lying code in `fabric/pipeline.py` alone

1. `self._redis_url` (line 152) — dead.
2. `self._dev_mode` (line 154) — dead (until the fix).
3. `self._queue` (line 173) — completely unused.
4. `InMemoryDebouncer` class (line 581) — defined but never instantiated anywhere in fabric.
5. Module docstring "Supports ... Redis (production) cache" (line 8) — lie.
6. Class docstring "Optional Redis URL for production caching" (line 137) — lie.
7. Class docstring "dev_mode forces in-memory even if redis_url is provided" (line 140) — lie (no non-in-memory path exists).
8. Comment "Cache operations (in-memory; Redis is a future extension)" (line 227) — the one truthful-but-contradictory line, which itself violates zero-tolerance rule 2 because it documents a stub.

One file. Eight distinct stubs or lies. All shipped to PyPI as part of kailash-dataflow 1.8.0.

---

## 11. Severity justification and recommendation

This is CRITICAL, not HIGH. Justification:

1. **Production impact is already visible**: impact-verse hit a Container Apps crash loop from the cascading effect (per-replica cold-start + prewarm > startup probe).
2. **Silent**: operators provision Redis, see `redis_url` flowing through configuration, read the docstring, and have no way to observe that fabric does not use it. The first observable symptom is cost and cold-start latency that look like "tuning problems".
3. **Multi-bug**: `redis_url` + webhook nonce + debouncer + dead scaffolding. Fixing one without the others leaves the other bugs in the same file festering.
4. **Cross-SDK gap**: kailash-rs has the matching absence of any Redis path.
5. **Framework-first violation inside the framework**: a cache abstraction already exists in `dataflow/cache/` and was not used.

**Recommended fix scope**:

- PR 1 (this issue): `FabricCacheBackend` ABC + `InMemoryFabricCacheBackend` + `RedisFabricCacheBackend` + wire into `PipelineExecutor` + wire `WebhookReceiver` redis_client + follower-side lazy prewarm + new integration tests + docs.
- PR 2 (follow-up, new issue): `_RedisDebouncer` + remove `_queue` dead code.
- PR 3 (cross-SDK, new issue on kailash-rs): Rust-side `CacheBackend` trait + `RedisCacheBackend` impl.
- PR 4 (design ADR, not a bug fix): unify `dataflow/cache/` with `dataflow/fabric/cache.py` into a single cache story — Option C from section 3.

PR 1 is the minimum to close #354 honestly. PR 2-4 are recorded as todos in `workspaces/issue-354/todos/` after `/analyze` completes.

---

## 12. Risk assessment

| Risk                                                                                       | Severity | Mitigation                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Async conversion of `product_info`/`invalidate`/`invalidate_all` breaks downstream callers | HIGH     | CHANGELOG breaking-change note; release as a minor version bump (1.9.0) because kailash-dataflow is still <2.0. Consider a deprecation cycle with sync shadow-metadata if a canary user is affected. |
| Redis unreachable at pipeline write time                                                   | MEDIUM   | Backend logs WARN, raises `FabricCacheError`; pipeline execution continues (data is returned to caller) but the write is lost. Health endpoint surfaces `cache_backend_health: degraded`.            |
| msgpack serialization of metadata in Redis HASH                                            | LOW      | msgpack the `data` bytes field only; metadata fields are stored as plain Redis types.                                                                                                                |
| Redis key collisions across DataFlow instances                                             | MEDIUM   | Instance-name prefix in key layout (section 7). WARN on default instance name in production.                                                                                                         |
| Test Redis pollution between test runs                                                     | MEDIUM   | Per-test Redis namespace prefix; teardown deletes the prefix.                                                                                                                                        |
| Follower lazy-prewarm misses staleness check                                               | LOW      | Lazy-prewarm only populates local trace state; serving layer still does staleness computation at request time. No semantic change.                                                                   |
| `redis.asyncio` connection pool exhaustion under high product cardinality                  | MEDIUM   | Single shared client per `RedisFabricCacheBackend`; redis-py client handles its own pool. Document max-connections guidance for operators with >1000 parameterized products.                         |
| Cross-SDK Rust lag                                                                         | LOW      | File the kailash-rs issue immediately after Python lands; mark `cross-sdk` label; no user-visible impact because kailash-rs fabric is not at production usage parity with Python today.              |

---

## 13. Open questions for human approval gate at `/todos`

1. **API break acceptability**: `FabricRuntime.product_info`/`invalidate`/`invalidate_all` become async. Acceptable in a minor release (1.9.0)? Or require sync shadow-state preservation?
2. **Follower-side lazy prewarm inclusion**: include in PR 1 or split? My recommendation is include — it is the impact-verse regression guard.
3. **Option D vs B for the Redis client**: reuse `dataflow/cache/auto_detection.CacheBackend` (thread-pool adapter overhead) or write a direct `redis.asyncio` backend matching `leader.py:55-105`? My recommendation is direct, because the `leader.py` pattern is already proven in fabric and avoids the thread pool.
4. **Dev-mode with Redis URL behavior**: force in-memory with WARN (my recommendation) or allow Redis-in-dev with a separate key prefix?
5. **Dead code deletion scope in PR 1**: delete `_queue`, `InMemoryDebouncer` (unused), and the stub docstring comments, OR leave for PR 2? My recommendation: delete `_queue` in PR 1 (trivial, reduces confusion). Leave `InMemoryDebouncer` until PR 2 because it signals a known missing feature.
6. **Backend health reporting**: surface `cache_backend: "redis" | "memory" | "degraded"` in `FabricRuntime.status()`? My recommendation: yes, operators need it.
7. **`FABRIC_INSTANCE_NAME` env var default behavior**: crash on startup if production + default instance name, or WARN? My recommendation: WARN, with the warning message listing the exact env var to set.

---

## 14. File citations — summary index

| Path                                                                  | Lines                  | What                                                                                               |
| --------------------------------------------------------------------- | ---------------------- | -------------------------------------------------------------------------------------------------- |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 8                      | Module docstring lie                                                                               |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 137-142                | Class docstring lie                                                                                |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 144-188                | Constructor with dead state                                                                        |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 152                    | `self._redis_url = redis_url` (dead)                                                               |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 173                    | `self._queue` (dead)                                                                               |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 177-182                | Three parallel dicts for cache state                                                               |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 227                    | Comment contradicting docstring                                                                    |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 230-268                | Sync cache methods that must become async                                                          |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 274-442                | `execute_product` with dedup logic at 393, 407                                                     |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 361-379                | 10MB size check (stays in execute_product)                                                         |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 448-475                | `get_product_from_cache` (becomes async)                                                           |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 481-516                | invalidate / invalidate_all (becomes async)                                                        |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`           | 581-633                | `InMemoryDebouncer` (unused class)                                                                 |
| `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`            | 69-81                  | `FabricRuntime.__init__` accepts `redis_url`                                                       |
| `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`            | 170-174                | Pipeline constructed from `redis_url`                                                              |
| `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`            | 177-182                | Leader correctly uses `redis_url`                                                                  |
| `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`            | 211-214                | **Webhook receiver MISSING redis_client**                                                          |
| `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`            | 317-350                | `_prewarm_products` (needs leader/follower split)                                                  |
| `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`            | 475-491                | `_get_products_cache` (sync -> async cascade)                                                      |
| `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`            | 560-599                | `product_info`, `invalidate`, `invalidate_all` public API                                          |
| `packages/kailash-dataflow/src/dataflow/fabric/leader.py`             | 55-105                 | Correct Redis client pattern to mirror                                                             |
| `packages/kailash-dataflow/src/dataflow/fabric/leader.py`             | 131-158                | `LeaderElector` backend selection pattern to mirror                                                |
| `packages/kailash-dataflow/src/dataflow/fabric/webhooks.py`           | 39-108                 | `_NonceBackend` ABC + `_RedisNonceBackend` pattern                                                 |
| `packages/kailash-dataflow/src/dataflow/fabric/webhooks.py`           | 170-188                | `WebhookReceiver` accepts `redis_client` but runtime doesn't pass it                               |
| `packages/kailash-dataflow/src/dataflow/fabric/serving.py`            | 276, 393               | Cache read call sites                                                                              |
| `packages/kailash-dataflow/src/dataflow/fabric/health.py`             | 85                     | Cache read call site (verify sync/async)                                                           |
| `packages/kailash-dataflow/src/dataflow/fabric/auth.py`               | 9, 218                 | Deliberate in-memory token storage (correct)                                                       |
| `packages/kailash-dataflow/src/dataflow/core/engine.py`               | 2015-2035              | `DataFlow.start()` resolves and forwards `redis_url`                                               |
| `packages/kailash-dataflow/src/dataflow/cache/auto_detection.py`      | 92-174                 | Pre-existing `CacheBackend.auto_detect` abstraction (NOT reused by fabric)                         |
| `packages/kailash-dataflow/src/dataflow/cache/async_redis_adapter.py` | 29-363                 | `AsyncRedisCacheAdapter` via ThreadPoolExecutor (rejected for hot-path)                            |
| `packages/kailash-dataflow/src/dataflow/cache/memory_cache.py`        | 24-100                 | `InMemoryCache` with asyncio.Lock (pre-existing async surface)                                     |
| `packages/kailash-dataflow/pyproject.toml`                            | 35                     | `redis>=4.5.0` is already a hard dependency                                                        |
| `crates/kailash-dataflow/src/executor.rs`                             | 32-54                  | Rust `ExecutorConfig` with **no** `redis_url`                                                      |
| `crates/kailash-dataflow/src/executor.rs`                             | 94-149                 | Rust `LruCache` is 100% in-memory                                                                  |
| `crates/kailash-dataflow/src/executor.rs`                             | 244-260                | Rust refreshes `cached_at` on dedup-hit (cross-SDK semantic divergence)                            |
| `packages/kailash-dataflow/tests/fabric/test_fabric_critical_bugs.py` | 88, 142, 197, 347, 399 | Every test constructs `PipelineExecutor(dataflow=db, dev_mode=True)` — never exercises `redis_url` |
| `packages/kailash-dataflow/tests/fabric/test_fabric_integration.py`   | 168, 238, 328, 467     | Same pattern — `dev_mode=True`, no redis_url                                                       |

---

## 15. Final verdict

**Issue #354 is valid, undersold, and should be classified CRITICAL.** The reporter's proposed fix (add `RedisBackedCache`) is directionally correct but incomplete. The comprehensive fix needs:

1. New `FabricCacheBackend(ABC)` mirroring `LeaderBackend` / `_NonceBackend` patterns in fabric.
2. Two implementations — in-memory and direct `redis.asyncio` — following the leader.py pattern, NOT the `dataflow.cache.AsyncRedisCacheAdapter` thread-pool pattern.
3. Async conversion cascading through `PipelineExecutor`, `FabricRuntime.product_info` / `invalidate` / `invalidate_all`, and call sites in `serving.py` / `health.py`.
4. Fix the adjacent `WebhookReceiver(redis_client=None)` wiring bug in the same PR.
5. Follower-side lazy prewarm that reads Redis without re-executing pipelines (the impact-verse regression guard).
6. Delete `pipeline.py:173` `self._queue` dead code.
7. Integration tests against real Redis (Tier 2 per testing rules).
8. CHANGELOG breaking-change entry; minor version bump to 1.9.0.
9. File cross-SDK follow-up issue on kailash-rs.
10. File follow-up issue for `_RedisDebouncer` and the unused `InMemoryDebouncer` class.

Time estimate: **one autonomous execution cycle** (single session) for PR 1. The implementation is mechanical once the ABC shape is decided; the slow parts are the test suite against real Redis and the async-conversion cascade.

This analysis is complete. Proceed to `/todos` with the open questions above as the human-approval gate checklist.
