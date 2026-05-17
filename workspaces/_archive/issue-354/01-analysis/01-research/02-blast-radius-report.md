# Issue #354 — Failure Point & Blast Radius Report

**Scope**: What breaks beyond the reporter's list, and what institutional-knowledge gaps let this stub survive.
**Companion**: dataflow-specialist is producing the fix design in parallel.
**Source of truth**: kailash-dataflow 1.8.0 in this tree.

---

## 1. Executive summary

The `redis_url` parameter is a dead-forwarded string across **four layers** of fabric, with not a single Redis client instantiated for the product cache. Four separate docstrings lie (not one). The `DataFlow(redis_url=...)` kwarg never reaches the fabric pipeline at all — it is only consumed by the Express query cache. Multi-tenant cache keys have no tenant prefix. No cache-source logging exists. Test coverage for the Redis fabric path is literally zero. This is not a gap; it is a four-layer ghost feature.

**Complexity**: Moderate. The fix itself is bounded (one new class, one wiring edit, one key-prefix change). The blast radius is wide because every docstring, README, deployment example, and runtime log path must be corrected together.

---

## 2. Every stale docstring / doc promise (§1 of brief)

| #   | Location                                                                            | Promise                                                                          | Reality                                                                                                                                                             |
| --- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:8`                       | Module docstring: _"Supports both in-memory (dev) and Redis (production) cache"_ | False. No Redis client.                                                                                                                                             |
| D2  | `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:137`                     | Class docstring: _"redis_url: Optional Redis URL for production caching"_        | False. Stored but unused.                                                                                                                                           |
| D3  | `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:140`                     | _"dev_mode: ... forces in-memory cache even if redis_url is provided"_           | Vacuous — in-memory is the ONLY backend regardless of `dev_mode`.                                                                                                   |
| D4  | `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:175`                     | Comment: _"In-memory cache (used when dev_mode or no redis_url)"_                | False. Used unconditionally.                                                                                                                                        |
| D5  | `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:227`                     | Section header: _"Cache operations (in-memory; Redis is a future extension)"_    | **Honest admission of a stub — contradicts D1-D4.** Self-refuting.                                                                                                  |
| D6  | `packages/kailash-dataflow/README.md:420`                                           | _"Prometheus metrics: Request counts, latencies, **cache hit rates**"_           | `grep cache_hit pipeline.py` → zero. No hit/miss metric.                                                                                                            |
| D7  | `packages/kailash-dataflow/README.md:404`                                           | _"dev_mode=False ... Skip pre-warming, use in-memory cache"_                     | Invert of reality — `dev_mode=False` also uses in-memory cache. `dev_mode=True` uses in-memory. Both use in-memory.                                                 |
| D8  | `packages/kailash-dataflow/README.md:426`                                           | _"Leader election for multi-worker coordination (Redis or in-memory)"_           | True for leader, but positioned to suggest fabric cache shares the same Redis story. It does not.                                                                   |
| D9  | `packages/kailash-dataflow/docs/production/deployment.md:74`                        | Example passes `redis_url=os.getenv("REDIS_URL")` in `CacheConfig`               | Only affects query cache, not fabric product cache. Users reading this assume fabric caching is covered.                                                            |
| D10 | `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:582` (was, per reporter) | `_RedisDebouncer` class                                                          | **Class does not exist.** Only `InMemoryDebouncer` at line 581. Second stub in the same file — debouncer is also in-memory-only, lost on restart, not cross-worker. |
| D11 | `packages/kailash-dataflow/src/dataflow/fabric/products.py:52`, `:111`              | _"multi_tenant: Whether cache is partitioned per tenant"_                        | `_cache_key()` at `pipeline.py:119-124` takes only `(product_name, params)`. No tenant dimension. Partitioning is not implemented.                                  |

Every one of D1-D11 is an independent lie that must either be made true or deleted.

---

## 3. Silent degradation trail (§2)

**No warning is emitted anywhere when a user passes `redis_url` and gets in-memory.**

| Check                                                                        | Result                                                                                            |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | -------- | -------------------------------------------------------------------------- |
| `PipelineExecutor.__init__` logs `redis_url` or a "Redis not wired" warning? | No — `pipeline.py:165-170` logs only `max_concurrent`, `db_budget`, `pool_size`.                  |
| `FabricRuntime.start` logs chosen cache backend?                             | No — `runtime.py:231-237` logs `leader`, `sources`, `products`, `dev_mode`. Cache backend absent. |
| `get_cached` / `set_cached` log `source=...`, `mode=real                     | fake                                                                                              | cached`? | No — **zero** `cache_hit`, `cache_miss`, `mode=` entries in `pipeline.py`. |
| Any log line differentiates "cache hit" vs "cache miss" at all?              | No — `PipelineResult.from_cache` exists on line 56 but is never logged.                           |

**Rule violated**: `.claude/rules/observability.md` § "Data Calls — Real, Fake, or Simulated" requires every data-fetch log line to include `source=...`, `mode=real|fake`. Fabric product cache emits neither. A `grep mode=fake` in production logs returns nothing — not because there is no fake, but because the log line that would reveal the fake has never been written.

---

## 4. Consumer impact map (§3)

**4.1 Production call sites (application code)**

| Call site                          | File:line                                                         | What changes                                                                                                                                                                                                                                                   |
| ---------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DataFlow.start(...)` public API   | `packages/kailash-dataflow/src/dataflow/core/engine.py:1982-2035` | Must either source `redis_url` correctly or accept it as a kwarg directly. Currently reads `self.config.redis_url`, `self.config.database.redis_url`, and `self._redis_url` (which is **never set** — see §6).                                                 |
| `DataFlow.__init__(redis_url=...)` | `engine.py:116, 473-481`                                          | The kwarg goes to `ExpressDataFlow` only. **It does NOT land on `self._redis_url`.** Users who call `DataFlow(redis_url=...)` expecting fabric caching get nothing — the fabric layer never sees it. This is a deeper wiring bug than the reporter documented. |
| `FabricRuntime.__init__`           | `runtime.py:69-81`                                                | Stores `self._redis_url` and forwards on line 172 and 178. Dead forward for pipeline; live forward for leader.                                                                                                                                                 |
| `PipelineExecutor.__init__`        | `pipeline.py:144-179`                                             | Stores `self._redis_url = redis_url` on 152 and then ignores it.                                                                                                                                                                                               |

**4.2 Tests**

| Call site                                                            | File:line                                                                                                                                    | Notes |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `test_fabric_critical_bugs.py:88, 142, 197, 250, 301, 347, 399, 473` | All instantiate `PipelineExecutor(..., dev_mode=True)` with no `redis_url`.                                                                  |
| `test_fabric_integration.py:168, 238, 328, 467, 522, 631`            | All use `dev_mode=True`, no Redis.                                                                                                           |
| `test_fabric_cache_control.py:30`                                    | Same — `dev_mode=True`.                                                                                                                      |
| **`grep -r "PipelineExecutor.*redis_url" tests/` → zero matches.**   | **Zero tests pass `redis_url` to `PipelineExecutor`.** The Redis code path has no coverage whatsoever — because there is no Redis code path. |
| `test_redis_integration.py` under `tests/integration/cache/`         | Exists, but tests the **query cache** (`RedisCacheManager`), not the fabric product cache. Orthogonal subsystem.                             |

**4.3 Examples**

| Path                                                                   | Notes                                                                                 |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `packages/kailash-dataflow/examples/fabric_reference/app.py:154`       | `await db.start(dev_mode=True)` — dev only. No example passes `redis_url`.            |
| `packages/kailash-dataflow/examples/fabric_reference/README.md:11, 18` | Documents `db.start(dev_mode=True)` only. A production-fabric example does not exist. |

**4.4 Downstream — impact-verse production**

Per the brief: this is the primary affected deployment. 26 products × 6,481 participants / 3,545 organizations / 14 clusters. Container Apps probe timed out after ~4 minutes on prewarm. Workaround: `prewarm=False` + continuous refresh task at 60s cadence. Both the probe failure AND the workaround's DB load stem from the missing cache layer.

**4.5 Cross-SDK**

`kailash-rs` must be checked for the same bug. Per `rules/cross-sdk-inspection.md`, a companion Rust issue should be filed on `esperie/kailash-rs` once this one lands. **Action**: file `esperie/kailash-rs` issue with `cross-sdk` label linking to `terrene-foundation/kailash-py#354`.

---

## 5. Operational blast radius in multi-replica prod (§4)

All numbers below assume an N-replica deployment (impact-verse used N ≥ 2, typical Container Apps range 2-10).

| Failure mode                          | Formula                                             | impact-verse scale                                                                                                                                                                                                                   |
| ------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Prewarm cost per replica              | `products × avg_pipeline_ms`                        | 26 products × ~10s average = 4-5 minutes per replica — **exceeds Container Apps default startup probe (~4 min)** → restart loop, 0% availability. Reporter observed this.                                                            |
| Cold-cache cost on restart            | `N × prewarm_cost`                                  | Every rolling restart re-pays the full prewarm per new replica. No warm handoff.                                                                                                                                                     |
| Memory per replica                    | `min(product_count × avg_bytes, 10_000 × 10MB)`     | Theoretical ceiling **100 GB per replica** (10k entries × 10 MB max, `pipeline.py:182`, `pipeline.py:42`). Practical use is lower, but duplicated across replicas — `N × actual_memory`.                                             |
| DB pool pressure during prewarm       | `20% of pool × N replicas × parallel prewarm tasks` | `pipeline.py:162` → `pool_fraction = int(pool_size × 0.2)`. With `pool_size=20`, each replica consumes 4 connections × N replicas = 4N. Prewarming 26 products on each replica concurrently multiplies DB load by N.                 |
| Redundant work                        | `N × M products` continuously                       | Each replica independently refreshes every materialized product, every poll interval. The reporter's workaround runs this every 60s: `N replicas × 26 products / 60s` = `0.43 × N` queries per second **wasted** from cache absence. |
| Continuous-refresh workaround DB load | `N × queries_per_cycle / cycle_period`              | For `N = 4 replicas × 26 products / 60s ≈ 1.7 qps of redundant work forever`. The database never sees any benefit from Redis even though Redis is provisioned and paid for.                                                          |

**Wasted Redis bill**: Redis is provisioned, used by leader election and webhook nonce dedup (`webhooks.py:73` `_RedisNonceBackend`), but the subsystem that would benefit most (product cache, ~100 MB × hours of compute) is bypassed. Redis sits 95% idle.

---

## 6. The deepest wiring bug — not in the brief

`DataFlow.__init__(redis_url=...)` DOES NOT plumb `redis_url` to the fabric.

| Step                                              | File:line             | What happens                                                                                                                                                                                                                  |
| ------------------------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. User calls `DataFlow(redis_url="redis://...")` | (user code)           | Intent: Redis everywhere.                                                                                                                                                                                                     |
| 2. `DataFlow.__init__` accepts it                 | `engine.py:116`       | Comment says _"TSG-107: Redis URL for Express cache backend"_ — scope is Express only.                                                                                                                                        |
| 3. Value flows to `ExpressDataFlow`               | `engine.py:474, 481`  | `_express_redis_url = redis_url or getattr(self.config, "cache_redis_url", None)`. Query cache gets it.                                                                                                                       |
| 4. `self._redis_url` is **never assigned**        | —                     | `grep "self\._redis_url" engine.py` → **one line: `engine.py:2019`**, which READS `self._redis_url` but no line writes it.                                                                                                    |
| 5. `DataFlow.start()` tries to resolve redis_url  | `engine.py:2015-2019` | Reads `self.config.redis_url`, then `self.config.database.redis_url`, then the nonexistent `self._redis_url`. Therefore: if the user passed `redis_url=` to `DataFlow()` but not to `DataFlowConfig`, the fabric sees `None`. |

**Consequence**: the reporter's mental model (`DataFlow(redis_url=...) → FabricRuntime → PipelineExecutor`) is correct about intent but wrong about mechanism. The `redis_url` kwarg to `DataFlow()` never even reaches the fabric layer. Only users who construct `DataFlowConfig(redis_url=...)` get the value into the fabric runtime — and even then, the fabric cache ignores it. **Two wiring bugs stacked on top of each other, both silent.**

This contradicts `rules/dataflow-pool.md` § 3 (No Deceptive Configuration): "A flag set to True with no consumer is a stub." The `redis_url` kwarg with no consumer is the same class of violation.

---

## 7. Institutional-knowledge fault line (§5)

All three CO fault lines are present. Severity ordered:

### 7.1 Context amnesia (primary)

The `TODO-11` reference at `pipeline.py:11` and `"Cache operations (in-memory; Redis is a future extension)"` comment at `pipeline.py:227` are an explicit admission that the author knew the Redis backend was a stub and left it for "later". Later never arrived. The class docstring at line 137 was then written as if the stub were implemented — **the honest comment and the dishonest docstring coexist 90 lines apart in the same file**. This is the defining signature of context amnesia: a future-tense note and a present-tense promise that drift past each other and ship together.

### 7.2 Convention drift (secondary)

`rules/dataflow-pool.md` Rule 3 (No Deceptive Configuration) was written exactly to forbid flag-without-consumer stubs. It either existed at landing time and was bypassed in review, or was written after this shipped. Either way, the stub reviewer accepted "will add later" despite the rule's existence in some form. The `rules/zero-tolerance.md` Rule 2 ("No Stubs") list includes the exact pattern that `pipeline.py:227` admits to. The reviewer did not run a `grep "future extension"` before approving.

### 7.3 Security blindness (tertiary but sharp)

`_cache_key(product_name, params)` at `pipeline.py:119-124` has **no tenant dimension**. `products.py:52, 111` documents `multi_tenant: Whether cache is partitioned per tenant` — the contract says partitioned, the implementation does not partition. In a single-process in-memory cache with low concurrency this is "merely" a bug; in a shared Redis cache across replicas it is a **cross-tenant data-leak primitive**: one tenant's cached product is returned to another tenant's request because the key is identical. Any Redis fix that does not fix this first is not a fix at all.

### 7.4 Proposed guards

1. **Spec-compliance rule**: add a line to `rules/dataflow-pool.md` Rule 3 explicitly listing `redis_url`, `cache_url`, `backend` as fields that MUST have an instantiation check at import or `__init__` time, not merely a stored value.
2. **Test rule**: `rules/testing.md` should require, for any config field named `*_url` or `*_backend`, at least one unit test that passes a non-None value and asserts the implementation instantiates the corresponding client.
3. **CI grep guard**: a red-team script that finds any occurrence of `"future extension"`, `"not yet implemented"`, `"Redis is a future"` in `src/` and fails the build.
4. **Docstring-vs-code audit**: for every parameter whose docstring contains "production" or "Redis", grep the class body for `from_url` / `aioredis` / `redis.Redis`. Zero matches → fail.

---

## 8. Historical dig (§6)

**Constraint**: this agent cannot run `git log` via shell; git history inspection must be done by the specialist or via Read of `.git` pack files. The verifiable artifacts from within the file tree:

| Evidence                                                                                                          | File:line           | Interpretation                                                                                                                                                                             |
| ----------------------------------------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pipeline.py:11` references `TODO-11` in `workspaces/data-fabric-engine/todos/active/02-products-and-pipeline.md` | Design-time todo    | Cache operations were planned, tracked, and partially built.                                                                                                                               |
| `pipeline.py:227` comment: _"Cache operations (in-memory; Redis is a future extension)"_                          | Code-time admission | The author KNEW they were landing an in-memory-only cache with a claim of Redis in the same class.                                                                                         |
| `pipeline.py:137` docstring vs `pipeline.py:227` comment                                                          | Same file           | Two lines of the same file, written ~90 lines apart, disagree about what the class does.                                                                                                   |
| `leader.py:55-106` `RedisLeaderBackend`                                                                           | Co-located proof    | Redis client wiring pattern (aioredis.from_url, lazy `_ensure_client`) is **already present in the same package**. The fabric author had a template and chose not to use it for the cache. |
| `webhooks.py:73-108` `_RedisNonceBackend`                                                                         | Second template     | Second example of the pattern in the same `fabric/` directory. Ignored.                                                                                                                    |

**Speculative (requires `git log` offline)**: The commit that added `redis_url: Optional[str] = None` to `PipelineExecutor.__init__` almost certainly landed together with the docstring at line 137 in a single commit. If so, the stub was landed whole-cloth from day one — Redis caching was **never implemented and then removed**; it was **never implemented**. The specialist should confirm via `git log -p packages/kailash-dataflow/src/dataflow/fabric/pipeline.py | grep -A 3 "redis_url: Optional"` and capture the SHA + commit message in the fix PR as historical context.

**Contract violation by that session**: a docstring was written in present tense for behavior that did not exist, in the same diff as the comment admitting the behavior did not exist. This is the exact pattern `rules/zero-tolerance.md` Rule 2 forbids.

---

## 9. Related stubs — the cluster (§7)

| #   | Location                                                                                                                                           | Stub kind                                                               | Severity                                                                                                       |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| S1  | `pipeline.py:227` comment "Redis is a future extension"                                                                                            | Declared-but-unimplemented cache backend                                | **Critical** (the issue)                                                                                       |
| S2  | `pipeline.py:581` `InMemoryDebouncer` — no `_RedisDebouncer` sibling                                                                               | Same class of failure: debounce state lost on restart; not cross-worker | **Major** (reporter flagged; silent today, loud on restart)                                                    |
| S3  | `pipeline.py:119-124` `_cache_key` has no tenant dimension despite `multi_tenant` product flag                                                     | Contract says partitioned per tenant; implementation does not partition | **Critical** (security: tenant key collision becomes a data-leak primitive once the cache is shared via Redis) |
| S4  | `runtime.py:107-129` `_validate_params` only warns on `enable_writes` / `host=0.0.0.0` without auth; does NOT validate that `redis_url` is honored | Validation pass misses the headline stub                                | **Significant**                                                                                                |
| S5  | `engine.py:2018` `hasattr(self, "_redis_url")` guard                                                                                               | Guards a value that is never set (§6) — dead branch                     | **Major** (invisible wiring gap)                                                                               |
| S6  | `gateway_integration.py:175-586` many "placeholder" comments                                                                                       | Validation-phase placeholders, not runtime stubs. Documented pattern.   | **Minor** (not a real stub)                                                                                    |

**Pattern**: every stub in this cluster is in the replication / distribution / multi-replica path. In-memory cache + in-memory debouncer + non-tenant-partitioned key space + no cache-source logging are all aligned to the same theme: **the fabric was written as if it would always run in a single process**, and the plumbing for multi-process was added as parameters but never as implementations. Single-replica testing would never catch any of this.

---

## 10. Observable signals a monitoring dashboard needs (§8)

**Today**: nothing. There is no metric, no log, no counter that distinguishes "cache working" from "each replica has its own cache". The reporter's evidence is "startup probe timed out" — a 4-minute black box.

**Minimum metrics the fix MUST expose**:

| Metric                                                                              | Label                                                  | Purpose                                                                                                            |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `dataflow_fabric_cache_hits_total`                                                  | `backend=redis\|memory`, `product`, `result=hit\|miss` | Prove cache is hit; reveal replica divergence if `hits_total` correlates 1:1 with `replica_id` cardinality.        |
| `dataflow_fabric_cache_backend_info`                                                | `backend`, `redis_url_masked`                          | Single gauge = 1 per replica. Sum across replicas: if not all replicas report `backend=redis`, wiring broke.       |
| `dataflow_fabric_cache_entries`                                                     | `replica`, `backend`                                   | Per-replica entry count. If the sum across replicas equals `N × entries_per_replica`, cache is not shared — alarm. |
| `dataflow_fabric_prewarm_duration_seconds`                                          | `replica`, `products_count`                            | Detects startup-probe timeout regressions. Alert if > 240s.                                                        |
| `dataflow_fabric_db_queries_total`                                                  | `source=prewarm\|refresh\|user`, `replica`             | Shows the 1.7 qps of wasted work from §5.                                                                          |
| `dataflow_fabric_cache_bytes`                                                       | `replica`                                              | Memory headroom per replica. Alert on > 80% of `_max_cache_entries × _max_result_bytes`.                           |
| Log field `mode=real\|cached` on every `get_cached`/`set_cached` call               | —                                                      | Satisfies `rules/observability.md` § 3.                                                                            |
| Log field `cache_backend=redis\|memory` on `PipelineExecutor.__init__` startup line | —                                                      | Single grep confirms which backend is live.                                                                        |

**Dashboard signal for "each replica has its own cache"**: `count(dataflow_fabric_cache_backend_info{backend="memory"}) > 0` with `dataflow_fabric_cache_entries > 0` across two or more `replica` labels. One alert. Done.

---

## 11. Red flag on the reporter's proposed fix (§9)

Reporter's sketch:

```python
class RedisBackedCache:
    def __init__(self, redis_url: str, key_prefix: str = "dataflow:fabric:", ttl: int = 3600):
```

**Risks**:

| Risk                                                                           | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R1: TTL vs `StalenessPolicy.max_age` mismatch**                              | Fabric products have per-product staleness via `StalenessPolicy` (`fabric/config.py`). A global 1-hour TTL will serve stale-but-cached data past the product's declared `max_age`. Fix: TTL per key = `staleness.max_age + grace_window`, not a global default.                                                                                                                                                                                                                                         |
| **R2: Refresh storms during the overlap window**                               | If a product refreshes every 60s (reporter's workaround) but its Redis TTL is 3600s, the cache is permanently warm but the content hash dedup at `pipeline.py:383` still re-serializes on every refresh. Redis bytes-written cost scales with refresh frequency even when data is unchanged. Fix: dedupe on content hash BEFORE the Redis SET; skip the write if hash matches.                                                                                                                          |
| **R3: Missing tenant partitioning**                                            | Reporter's `key_prefix = "dataflow:fabric:"` has no tenant dimension. With `multi_tenant=True` products, two tenants requesting the same product name map to the same Redis key. **This is a cross-tenant data leak the moment the cache is shared** — far worse than the in-memory bug it replaces. Fix: key = `f"{key_prefix}{tenant_id}:{product_name}:{canonical_params_hash}"`. Tenant ID MUST be required for any product with `multi_tenant=True`.                                               |
| **R4: Async-API break**                                                        | `get_cached` / `set_cached` are currently sync (`pipeline.py:230, 241`). Every existing caller becomes `await`-required. The specialist must audit: `runtime.py:479` (`self._pipeline.get_cached(name)`), `runtime.py:566` (`product_info`), `pipeline.py:393` (`_get_cached_hash`), `pipeline.py:407` (`set_cached`), `pipeline.py:455` (`get_cached`). All become async. Consider a dual sync/async facade with a sync fast-path for the in-memory backend to avoid forcing async on every call site. |
| **R5: Serialization already in-flight, but metadata is dict — needs encoding** | `data_bytes` is already bytes (msgpack/json). `metadata` is a `Dict[str, Any]` (`pipeline.py:181`). Redis SET requires the value to be bytes; metadata must be serialized separately (HSET fields) or bundled into one msgpack blob. Reporter's sketch elides this.                                                                                                                                                                                                                                     |
| **R6: No cache invalidation across replicas**                                  | `pipeline.py:491-514` `invalidate()` / `invalidate_all()` mutate `self._cache_data` directly. With Redis, `invalidate()` on replica A must reach replica B's in-memory state too — or use Redis pub/sub. Reporter's sketch does not mention invalidation fanout.                                                                                                                                                                                                                                        |
| **R7: `aioredis.from_url` resource management**                                | `leader.py:102-105` closes the client on `close()`. The new cache must implement the same pattern and be closed in `FabricRuntime.stop()` — or it leaks connections on every restart (already a per-replica problem, so ResourceWarning will scream at test time).                                                                                                                                                                                                                                      |
| **R8: Dependency already declared**                                            | `redis>=4.5.0` is in `pyproject.toml:35` as a core dependency (not an optional extra). No new declaration needed. The fabric cache fix does not widen the dependency surface.                                                                                                                                                                                                                                                                                                                           |

**Verdict**: reporter's fix sketch is directionally correct but incomplete. R3 (tenant key) is a hard blocker — shipping the Redis fix without tenant partitioning CREATES a data leak. R1/R2/R4/R6 are correctness bugs that will surface in production. R5/R7 are hygiene. The dataflow-specialist MUST address all eight before writing code.

---

## 12. Blockers for shipping today (§10)

| #   | Blocker                                                                                       | Severity          | Resolution                                                                                                                                                                                                                        |
| --- | --------------------------------------------------------------------------------------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1  | Multi-tenant key collision in any Redis implementation (§7.3, §11 R3)                         | **Critical**      | MUST add tenant dimension to `_cache_key` before Redis lands. Non-negotiable.                                                                                                                                                     |
| B2  | `DataFlow.__init__(redis_url=...)` does not plumb to fabric (§6)                              | **Critical**      | Two wiring paths must be fixed: `_redis_url` must be stored on `self`, AND the fabric start path must use it.                                                                                                                     |
| B3  | TTL semantics must match per-product `StalenessPolicy.max_age`, not a global default (§11 R1) | **Major**         | Specialist design question; no code blocker.                                                                                                                                                                                      |
| B4  | Sync-to-async API break (§11 R4)                                                              | **Major**         | Audit all callers; dual-backend facade or full async migration. Affects `runtime.py`, `serving.py`, `health.py`, consumers.                                                                                                       |
| B5  | Cross-replica invalidation (§11 R6)                                                           | **Major**         | Redis pub/sub or accept per-replica invalidate with eventual consistency. Design call.                                                                                                                                            |
| B6  | Test infrastructure: zero fabric tests exercise the Redis path (§4.2)                         | **Significant**   | Must add integration tests with real Redis (Docker) before merge. Align with `rules/testing.md` no-mocking for Tier 2/3.                                                                                                          |
| B7  | impact-verse production migration risk                                                        | **Significant**   | Fix landing flips fabric from "isolated per replica" to "shared across replicas". First deploy after the fix MUST verify the existing continuous-refresh workaround is disabled or coordinated. Production cutover plan required. |
| B8  | `_RedisDebouncer` is also missing (D10)                                                       | **Significant**   | Should be fixed in the same PR or immediately follow — half-fixing the Redis story leaves the debouncer lying.                                                                                                                    |
| B9  | Every stale docstring (§2, D1-D11) must be updated atomically with the code fix               | **Required**      | Any docstring that lies after the fix lands is a new zero-tolerance Rule 2 violation.                                                                                                                                             |
| B10 | Cross-SDK: file a `esperie/kailash-rs` companion issue per `rules/cross-sdk-inspection.md`    | **Required**      | Not a blocker for the Python fix, but required before closing #354.                                                                                                                                                               |
| B11 | `redis` package dependency                                                                    | **Not a blocker** | Already declared at `pyproject.toml:35` as `redis>=4.5.0`. No change needed.                                                                                                                                                      |
| B12 | `CHANGELOG.md` entry                                                                          | **Required**      | Per `rules/deployment.md` pre-release checklist.                                                                                                                                                                                  |

---

## 13. Cross-reference audit

**Documents affected by the fix**:

- `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py` — all docstrings (D1-D5), cache class, debouncer (D10), key function (S3)
- `packages/kailash-dataflow/src/dataflow/fabric/runtime.py` — plumbing, startup log line, invalidation fanout
- `packages/kailash-dataflow/src/dataflow/core/engine.py` — `_redis_url` assignment (§6), `start()` resolution (lines 2015-2027)
- `packages/kailash-dataflow/src/dataflow/fabric/products.py` — `multi_tenant` docstring must match implementation (lines 52, 111)
- `packages/kailash-dataflow/src/dataflow/fabric/serving.py`, `health.py` — async-migration callers of `get_cached`
- `packages/kailash-dataflow/README.md` — lines 404, 420, 426 (§2 D6-D8); add fabric + Redis production example
- `packages/kailash-dataflow/docs/production/deployment.md` — line 74 context (§2 D9)
- `packages/kailash-dataflow/examples/fabric_reference/app.py` — add a non-`dev_mode` variant with Redis
- `packages/kailash-dataflow/CHANGELOG.md` — new `[Fixed]` entry citing #354
- `packages/kailash-dataflow/tests/fabric/test_fabric_redis_cache.py` (NEW) — Tier 2 integration test with real Redis
- `.claude/rules/dataflow-pool.md` — extend Rule 3 with config-field implementation guard (§7.4)
- Issue on `esperie/kailash-rs` — cross-SDK alignment (§4.5)

**Inconsistencies found**:

1. `pipeline.py:137` docstring vs `pipeline.py:227` comment — contradictory within one file.
2. `products.py:52, 111` "partition cache per tenant" vs `pipeline.py:119` `_cache_key` implementation — contract violation.
3. `engine.py:116` comment "Redis URL for Express cache backend" vs `README.md:404` implying fabric caching — scope mismatch that users cannot see.
4. `engine.py:2018` `hasattr(self, "_redis_url")` vs no corresponding `self._redis_url = ...` in `__init__` — dead branch.
5. Reporter's mental model (D-F-P chain) vs actual wiring (D→Express only; D-config→F→P but P ignores) — mismatch between intent and reality.

---

## 14. Success criteria for a complete fix

- [ ] All of D1-D11 either made true or deleted.
- [ ] `DataFlow(redis_url=...)` kwarg plumbs to fabric pipeline (§6 closed).
- [ ] `RedisBackedCache` with tenant-partitioned key prefix, per-product TTL from `StalenessPolicy.max_age`, content-hash dedup, and invalidation fanout.
- [ ] `_RedisDebouncer` implemented or `InMemoryDebouncer` docstring updated to say single-worker-only (S2).
- [ ] `_cache_key()` takes tenant_id and partitions (S3).
- [ ] Every `get_cached` / `set_cached` call logs `mode=real|cached`, `source=redis|memory`, `cache_hit=bool` (§3 → observability.md § 3 compliance).
- [ ] `PipelineExecutor.__init__` logs the chosen backend at INFO level once per start.
- [ ] Tier 2 integration test boots real Redis via Docker and verifies: two `PipelineExecutor` instances pointing to the same Redis see each other's writes (the test that proves "shared, not per-process").
- [ ] Tenant isolation test: product A for tenant X is NOT visible to tenant Y even with the same `product_name + params`.
- [ ] Prewarm duration metric exported; impact-verse can verify probe-timeout regression.
- [ ] Cross-SDK companion issue filed on `esperie/kailash-rs`.
- [ ] Stub-detection rule added: `rules/dataflow-pool.md` Rule 3 extended with config-field guard (§7.4).
- [ ] CHANGELOG entry references #354 and names every docstring corrected.

---

## 15. Speculative items (flagged)

- **SP1**: The commit that landed `redis_url` on `PipelineExecutor` is likely the initial fabric module commit (stub from day one), not a removal. Requires `git log -p packages/kailash-dataflow/src/dataflow/fabric/pipeline.py` to confirm. Specialist should capture the SHA in the fix PR.
- **SP2**: `kailash-rs` likely has the same bug by structural symmetry (fabric was designed cross-SDK), but this agent did not verify the Rust tree. Cross-SDK inspection step required.
- **SP3**: impact-verse deployment may have additional workarounds beyond the continuous-refresh task. Verify with the deployment owner before flipping the cache to Redis, to avoid double-refresh.
