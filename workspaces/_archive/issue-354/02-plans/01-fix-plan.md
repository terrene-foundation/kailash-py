# Issue #354 — Fix Plan

**Target branch**: `fix/354-fabric-redis-cache` (NEW, branched from `main`)
**Release**: `kailash-dataflow` minor version bump `1.8.0 → 1.9.0`
**Execution**: one autonomous cycle (single `/implement` session), single PR
**Risk**: HIGH (breaking async API on 3 public methods) — gated by CHANGELOG + migration snippet

## Goals

1. Make `DataFlow(redis_url=...)` and `DataFlowConfig(redis_url=...)` actually drive the fabric product cache.
2. Preserve all current in-memory behavior when no Redis URL is provided.
3. Add tenant-partitioned cache keys AND plumb `tenant_extractor` through `FabricServingLayer`, `health.py`, `_get_products_cache` (BLOCKER for shipping — prevents data leak).
4. Fix the parallel webhook nonce wiring bug in the same PR.
5. Add **leader-side warm-cache on election** so a new leader does not re-run full prewarm when Redis already holds fresh entries (impact-verse regression guard — followers already skip prewarm today).
6. Add **write CAS by `run_started_at`** to `RedisFabricCacheBackend.set()` so stale data cannot overwrite fresh data under the R3 last-writer-wins model.
7. Add **Redis-outage fallback** — catch `ConnectionError`/`TimeoutError`, emit `fabric_cache_degraded=1`, return cache miss and keep serving.
8. Add a **`get_metadata(key)`** fast path to `FabricCacheBackend` ABC for `product_info`/health paths that only need `cached_at`.
9. Delete dead code in `pipeline.py` **AND** delete the matching `change_detector.py:274-296` consumer block atomically.
10. Correct every lying docstring atomically with the code.
11. Add Tier 2 integration tests with real Redis.
12. Add observability (logs + metrics).
13. File follow-up issues for `_RedisDebouncer` and the cross-SDK Rust gap **in parallel with the Python PR**, not after it merges.

## Out of scope (follow-up issues)

- `_RedisDebouncer` implementation → filed as new issue with label `dependency-of-354`
- kailash-rs `CacheBackend` trait → filed as new issue on `esperie-enterprise/kailash-rs` with label `cross-sdk`
- Unifying `dataflow/cache/` with `dataflow/fabric/cache.py` → future ADR, not a bug fix

## Deliverables

### New files

| Path                                                                        | Purpose                                                                                                         |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `packages/kailash-dataflow/src/dataflow/fabric/cache.py`                    | `FabricCacheBackend` ABC + `InMemoryFabricCacheBackend` + `RedisFabricCacheBackend` + `_FabricCacheEntry`       |
| `packages/kailash-dataflow/tests/fabric/test_fabric_cache_redis.py`         | Tier 2 integration tests — 10+ scenarios against real Redis                                                     |
| `packages/kailash-dataflow/tests/fabric/test_fabric_cache_memory.py`        | Tier 1 unit tests — LRU, dedup, max_entries, tenant isolation                                                   |
| `packages/kailash-dataflow/tests/fabric/test_fabric_webhook_nonce_redis.py` | Regression for the webhook wiring bug — two replicas, same delivery, one processes                              |
| `packages/kailash-dataflow/tests/regression/test_issue_354_fabric_redis.py` | `@pytest.mark.regression` — exact issue reproduction: instantiate with `redis_url`, verify Redis traffic exists |

### Modified files

| Path                                                               | Change summary                                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`        | Delete three parallel dicts, delete `_queue` (paired with `change_detector.py` update below), update docstrings, async cache methods, backend delegation                                                                                                                                                                                                                         |
| `packages/kailash-dataflow/src/dataflow/fabric/change_detector.py` | Delete lines `274-296` `getattr(self._pipeline_executor, "_queue", None)` fallback dispatch — paired with the `_queue` deletion in `pipeline.py`. Verify runtime.py:207 always sets `on_change` before removing both.                                                                                                                                                            |
| `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`         | `_get_or_create_redis_client` helper (shared between cache, webhook, leader), wire `WebhookReceiver(redis_client=...)`, **leader-side warm-cache on election** (replaces "follower-lazy-prewarm" framing), pass `tenant_extractor` to `FabricServingLayer`, async cascade on `product_info`/`invalidate`/`invalidate_all`, async `_get_products_cache` with `tenant_id` argument |
| `packages/kailash-dataflow/src/dataflow/fabric/serving.py`         | Accept `tenant_extractor` in `__init__`; invoke per request. Replace `get_cached(name)` with `get_cached(name, tenant_id=extract(request))` at lines 276, 393. Add `await`.                                                                                                                                                                                                      |
| `packages/kailash-dataflow/src/dataflow/fabric/health.py`          | Line 85: decide — either (a) use `get_metadata(key)` fast path with a "system" tenant scope for cache-health probes, or (b) iterate tenants via SCAN. Pick (a) for simplicity. Add `await`.                                                                                                                                                                                      |
| `packages/kailash-dataflow/src/dataflow/fabric/products.py`        | Pass `tenant_id` into cache operations for `multi_tenant=True` products. Raise `FabricTenantRequiredError` if `multi_tenant=True` and no tenant_id provided.                                                                                                                                                                                                                     |
| `packages/kailash-dataflow/src/dataflow/fabric/metrics.py`         | Register new counters + gauge                                                                                                                                                                                                                                                                                                                                                    |
| `packages/kailash-dataflow/src/dataflow/core/engine.py`            | Store `self._redis_url = redis_url` in `__init__` — the deepest wiring fix                                                                                                                                                                                                                                                                                                       |
| `packages/kailash-dataflow/src/dataflow/__init__.py`               | Version bump to `1.9.0`                                                                                                                                                                                                                                                                                                                                                          |
| `packages/kailash-dataflow/pyproject.toml`                         | Version bump to `1.9.0`                                                                                                                                                                                                                                                                                                                                                          |
| `packages/kailash-dataflow/CHANGELOG.md`                           | `1.9.0` entry with breaking change note                                                                                                                                                                                                                                                                                                                                          |
| `packages/kailash-dataflow/README.md`                              | Lines 404, 420, 426 — correct Redis claims                                                                                                                                                                                                                                                                                                                                       |
| `packages/kailash-dataflow/docs/production/deployment.md`          | Line 74 — clarify that `redis_url` now covers fabric cache                                                                                                                                                                                                                                                                                                                       |
| `packages/kailash-dataflow/examples/fabric_reference/app.py`       | Add a production-mode example branch with `redis_url`                                                                                                                                                                                                                                                                                                                            |
| `.claude/rules/dataflow-pool.md`                                   | Extend Rule 3 with `*_url`/`*_backend`/`*_client` guard                                                                                                                                                                                                                                                                                                                          |
| `.claude/rules/testing.md`                                         | Extend with "config fields whose docstring mentions Redis require Tier 2 integration test"                                                                                                                                                                                                                                                                                       |

### Existing tests to migrate

Every fabric test that calls `pipeline.get_cached(...)` / `set_cached(...)` / `invalidate(...)` synchronously becomes `await ...`. Estimated ~15 call sites across:

- `tests/fabric/test_fabric_critical_bugs.py`
- `tests/fabric/test_fabric_integration.py`
- `tests/fabric/test_fabric_cache_control.py`

No semantic changes to these tests — only `async` / `await` insertions.

## Implementation order (strict)

Every phase ends with `ruff check .`, `mypy packages/kailash-dataflow/src/dataflow/fabric/`, and `pytest tests/fabric/ -x` before moving to the next. Zero tolerance for warnings.

1. **Phase 0: Branch + version bump** — `git checkout -b fix/354-fabric-redis-cache main`, bump `pyproject.toml` + `__init__.py` to 1.9.0. File the cross-SDK Rust issue on `esperie-enterprise/kailash-rs` at the same time (parallel authoring, not after merge — autonomous execution is 10x parallel, waiting is waste).
2. **Phase 1: `fabric/cache.py`** — write the ABC and both backends with full Tier 1 unit tests. Zero couplings to existing code yet. ABC includes `get_metadata(key)` fast path alongside `get(key)` so `product_info`/health can do a cheap `HGET cached_at, content_hash, size_bytes` without fetching the payload.
3. **Phase 2: Tenant partitioning** — extend `_cache_key` signature to take `tenant_id: Optional[str]`. Raise `FabricTenantRequiredError` on `multi_tenant=True` without tenant_id.
4. **Phase 3: Plumb `engine.py`** — `self._redis_url = redis_url` assignment in `DataFlow.__init__`. Verify `engine.py:2018` `hasattr` branch now fires.
5. **Phase 4: Rewrite `PipelineExecutor`** — delegate to `FabricCacheBackend`, delete the three parallel dicts, convert cache methods to async, update docstrings. Update internal callers (lines 393, 407, 455). **DO NOT delete `_queue` yet** — paired with Phase 4b.
6. **Phase 4a: Write-CAS for R3** — `RedisFabricCacheBackend.set()` uses a Lua CAS script keyed on `run_started_at`. Older writers cannot overwrite newer entries. Tier 2 test launches two concurrent writers with staggered start times and asserts the newer one wins. Closes the last-writer-wins bug R3 would otherwise permit.
7. **Phase 4b: Paired dead-code deletion** — delete `self._queue` in `pipeline.py:173` AND delete `change_detector.py:274-296` (the `getattr(self._pipeline_executor, "_queue", None)` fallback consumer) in the same commit. Verify `runtime.py:207` `set_on_change` is always called before both deletions. If any doubt remains, keep `_queue` in place and add a docstring noting the fallback is never reached in production.
8. **Phase 5: Cascade async + tenant plumbing through `runtime.py`, `serving.py`, `health.py`** — in order:
   - 5a. `FabricServingLayer.__init__` gains `tenant_extractor: Optional[Callable]`. `runtime.py:217-225` passes `self._tenant_extractor`.
   - 5b. `serving.py:276, 393` replace `get_cached(name)` with `get_cached(name, tenant_id=self._extract_tenant(request))`. Add `await`.
   - 5c. `runtime.py:472-491 _get_products_cache` becomes async, gains `tenant_id` parameter. Callers at `runtime.py:338, 381` (already async) pass `ctx.tenant_id`.
   - 5d. `runtime.py:566 product_info` either (i) becomes tenant-scoped via an explicit argument, or (ii) becomes a system-level metadata endpoint that scans all tenant keys. **Pick (i)** — explicit tenant argument, document in CHANGELOG.
   - 5e. `health.py:85` uses `get_metadata(key)` fast path with a "system" tenant scope for cache-health probes (non-authoritative, just "is the entry present").
   - 5f. Run tests between each file.
9. **Phase 6: Webhook nonce wiring** — extract `_get_or_create_redis_client` in `FabricRuntime.start()`, pass to `WebhookReceiver(redis_client=...)` AND to the new cache backend AND to `LeaderElector` (one shared client per replica, not three). Write the webhook regression test.
10. **Phase 7: Leader-side warm-cache on election** (NOT follower-lazy-prewarm) — `_prewarm_products` gains a read-before-execute step. For each materialized product:
    - Query Redis for `(content_hash, cached_at, run_started_at)` via `cache.get_metadata(key)`.
    - If cache hit AND `cached_at + staleness.max_age > now`, skip execution and record trace `cache_action=warm_skipped`.
    - Else re-execute.
    - This is the **actual** impact-verse regression guard: followers already skip prewarm today (`runtime.py:185-189 if self._leader.is_leader and prewarm`). The crash loop is specifically when the leader dies during a rolling deploy and a new leader must re-run serial prewarm on 26 products × 10s = 4-5 min. With warm-cache-on-election, the new leader reads Redis for each product and only re-executes missing or stale entries.
11. **Phase 8: Observability** — log lines + metrics. Includes Redis-outage fallback: `RedisFabricCacheBackend.get/set` wrapped in try/except `(redis.ConnectionError, asyncio.TimeoutError)` with structured WARN log (masked URL + error_class), return None on catch, increment `fabric_cache_errors_total`, set `fabric_cache_degraded=1` gauge. Verify `grep mode=` in test output returns expected entries.
12. **Phase 9: Migrate existing fabric tests to async cache API** — ~15 call sites.
13. **Phase 10: Write Tier 2 Redis integration tests** — 15+ scenarios (see expanded test plan below, now includes R3 CAS, outage fallback, leader-election warm-cache).
14. **Phase 11: Documentation updates** — CHANGELOG, README, deployment.md, fabric_reference example.
15. **Phase 12: Correct every D1-D11 docstring lie** — final audit pass with grep against `grep -n "Redis\|redis\|cache" packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`.
16. **Phase 13: Follow-up issue for `_RedisDebouncer`** — the cross-SDK Rust issue is already filed in Phase 0 (parallel authoring). File the `_RedisDebouncer` follow-up after PR 1 opens.

## Test plan

### Tier 1 (unit, mocking allowed, <1s/test)

- `test_fabric_cache_memory.py::test_in_memory_backend_basic_get_set`
- `test_fabric_cache_memory.py::test_in_memory_backend_lru_eviction_at_max_entries`
- `test_fabric_cache_memory.py::test_in_memory_backend_dedup_on_unchanged_hash`
- `test_fabric_cache_memory.py::test_in_memory_backend_tenant_isolation` (two tenants, same product_name, get separate entries)
- `test_fabric_cache_memory.py::test_in_memory_backend_params_hash_key_format`
- `test_fabric_cache_memory.py::test_in_memory_backend_invalidate_removes_key`
- `test_fabric_cache_memory.py::test_in_memory_backend_invalidate_all_pattern`
- `test_fabric_cache_memory.py::test_multi_tenant_without_tenant_id_raises`

### Tier 2 (integration, real Redis via docker-compose, NO mocking)

- `test_fabric_cache_redis.py::test_redis_backend_writes_and_reads`
- `test_fabric_cache_redis.py::test_redis_backend_dedup_on_unchanged_hash_no_write`
- `test_fabric_cache_redis.py::test_redis_backend_multi_replica_read` — two `PipelineExecutor` instances, replica A writes, replica B reads without executing
- `test_fabric_cache_redis.py::test_redis_backend_ttl_max_age_24x_with_1h_floor`
- `test_fabric_cache_redis.py::test_redis_backend_invalidate_removes_key`
- `test_fabric_cache_redis.py::test_redis_backend_invalidate_all_scans_not_keys` — verify no `KEYS` command in Redis slowlog
- `test_fabric_cache_redis.py::test_redis_backend_parameterized_products_params_hash_key`
- `test_fabric_cache_redis.py::test_redis_backend_multi_tenant_cross_tenant_isolation` — **the data-leak regression guard**
- `test_fabric_cache_redis.py::test_redis_backend_instance_name_prefix_isolation` — two `DataFlow` instances share Redis, don't collide
- `test_fabric_cache_redis.py::test_dev_mode_forces_in_memory_even_with_redis_url_and_warns`
- `test_fabric_cache_redis.py::test_leader_warm_cache_on_election_skips_fresh_entries` — **the actual impact-verse regression guard**: leader A writes 26 products, leader A dies, leader B elects, leader B prewarms in <5s because every product's `cached_at + max_age > now`.
- `test_fabric_cache_redis.py::test_leader_warm_cache_re_executes_stale_entries` — same scenario but with `cached_at + max_age < now` — leader B must re-execute.
- `test_fabric_cache_redis.py::test_content_hash_dedup_across_replicas`
- `test_fabric_cache_redis.py::test_write_cas_blocks_older_writer` — two concurrent writers, replica A starts at T=0 (10s pipeline), replica B starts at T=5 (2s pipeline). Replica B writes `run_started_at=5` first. Replica A writes `run_started_at=0` at T=10 — MUST be rejected by CAS. Regression guard for R3 worst-case race.
- `test_fabric_cache_redis.py::test_redis_down_mid_operation_falls_back_and_recovers` — start with Redis reachable, bring Redis down, verify `fabric_cache_degraded=1` gauge flips, cache operations return None without raising, bring Redis back up, verify gauge flips back and operations resume.
- `test_fabric_cache_redis.py::test_get_metadata_fast_path_no_payload_transfer` — `cache.get_metadata(key)` runs `HGET cached_at content_hash size_bytes` not `HGETALL`. Measurable latency difference with a large payload.
- `test_fabric_webhook_nonce_redis.py::test_two_replicas_dedupe_same_delivery_via_redis`
- `test_fabric_webhook_nonce_redis.py::test_in_memory_fallback_when_redis_url_absent`

### Tier 3 (E2E) — optional, nice-to-have

- `test_fabric_redis_e2e.py::test_impact_verse_style_prewarm_crash_loop_resolved` — docker-compose with 2 replicas of a minimal FabricRuntime, verify follower startup < 30s despite leader still prewarming

### Regression

- `tests/regression/test_issue_354_fabric_redis.py` — exact minimal reproduction:
  ```python
  @pytest.mark.regression
  async def test_issue_354_redis_url_honored_by_fabric_cache(db_factory, redis_url):
      """Regression: #354 — DataFlow(redis_url=...) must drive fabric product cache."""
      db = DataFlow(url=..., redis_url=redis_url)
      # ... run a pipeline, verify Redis has the key
      client = redis.asyncio.from_url(redis_url)
      assert await client.exists("fabric:product:default:my_product") == 1
  ```

## Rollback plan

If Tier 2 Redis tests hang, flaky, or fail:

1. Revert `fabric/cache.py` import in `PipelineExecutor`.
2. Restore the three parallel dicts (git show the pre-change state).
3. Keep the version bump so release doesn't silently re-ship broken 1.9.0.
4. Skip closing #354; it stays open with a comment explaining the rollback.

## Migration notes for downstream consumers (CHANGELOG entry)

```markdown
## 1.9.0 — Fabric Redis cache (#354)

### Fixed (CRITICAL)

- **`DataFlow(redis_url=...)` now honors Redis for the fabric product cache.** Previously the parameter was accepted and silently ignored; fabric ran with a per-process `OrderedDict` regardless of configuration. Multi-replica deployments now share the cache via Redis. (#354)
- **Webhook nonce deduplication is now cross-replica via Redis when `redis_url` is provided.** Previously every replica had its own in-memory nonce set, meaning retried webhooks could be processed multiple times. (#354 secondary fix)
- **Follower replicas no longer re-execute pipelines on prewarm** — they read from Redis. Fixes the Container Apps startup-probe crash loop on multi-replica deployments with long prewarm times. (#354 impact-verse regression)

### Changed (BREAKING)

The following `FabricRuntime` public methods are now `async` to support the Redis-backed cache:

- `FabricRuntime.product_info(name)` → `await runtime.product_info(name)`
- `FabricRuntime.invalidate(name)` → `await runtime.invalidate(name)`
- `FabricRuntime.invalidate_all()` → `await runtime.invalidate_all()`

Migration: wrap callers in `async def` or use `asyncio.run()` for sync contexts.

### Security

- **Multi-tenant cache keys now include tenant_id**. Previously, products declared with `multi_tenant=True` had no tenant dimension in their cache key. On a single-process in-memory cache this was a latent bug; it would have become a cross-tenant data leak the moment the cache was shared via Redis. Products declared `multi_tenant=True` now REQUIRE a `tenant_id` at lookup time or raise.

### Deprecated

- `InMemoryDebouncer` docstring updated to reflect single-worker semantics. Cross-replica debouncing via Redis remains unimplemented; tracked as a follow-up to #354.
```

## Human approval checkpoints (`/todos` gate)

Before `/implement`, confirm:

1. **Breaking async API change acceptable in a 1.x minor bump?** (Recommendation: yes; kailash-dataflow is <2.0 so minor bumps can break in CHANGELOG.)
2. **Follower-side lazy prewarm in scope?** (Recommendation: yes — impact-verse regression guard.)
3. **Tenant partitioning as `raise` or `warn`?** (Recommendation: `raise` for `multi_tenant=True` without `tenant_id`. The warn path lets the data leak happen silently under load.)
4. **`FABRIC_INSTANCE_NAME` default: crash on prod or warn?** (Recommendation: WARN with actionable message naming the env var.)
5. **Dev-mode + redis_url: in-memory with WARN or allow Redis-in-dev?** (Recommendation: in-memory with WARN.)
6. **Dead code deletion (`_queue`, `InMemoryDebouncer`) scope?** (Recommendation: delete `_queue` this PR; leave `InMemoryDebouncer` with updated docstring and a follow-up issue filed.)
7. **Impact-verse coordination**: does the existing continuous-refresh workaround need to be disabled or coordinated with the deploy? Ask the deployment owner before cutover.

## References

- Issue: terrene-foundation/kailash-py#354
- Analysis: `workspaces/issue-354/01-analysis/00-executive-summary.md`
- Specialist report: `workspaces/issue-354/01-analysis/01-research/01-dataflow-specialist-report.md`
- Blast radius report: `workspaces/issue-354/01-analysis/01-research/02-blast-radius-report.md`
- Correct pattern: `packages/kailash-dataflow/src/dataflow/fabric/leader.py:55-158`
- Reference bug site: `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:137, 152, 227, 581`
