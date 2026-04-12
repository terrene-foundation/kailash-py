# Issue #354 — Follow-up Issues to File

These are discovered during analysis but OUT OF SCOPE for the #354 fix PR. File each with the appropriate label after PR 1 lands.

## Follow-up 1: `_RedisDebouncer` + cross-replica debounce semantics

**Repo**: `terrene-foundation/kailash-py`
**Label**: `bug`, `dependency-of-354`
**Title**: `bug(dataflow-fabric): InMemoryDebouncer is single-worker only; no cross-replica debounce despite fabric being multi-replica`

**Body**:

````markdown
## Problem

`packages/kailash-dataflow/src/dataflow/fabric/pipeline.py:581-633` defines `InMemoryDebouncer`. Its docstring says "Fallback debouncer for dev mode when Redis is not available" — implying a primary Redis debouncer that does not exist.

Verified: `grep -rn "RedisDebouncer" packages/kailash-dataflow/` returns zero matches.

Two additional findings from #354 analysis:

1. `InMemoryDebouncer` is **never instantiated anywhere in fabric** (grep: zero call sites). The class is dead code.
2. The change detection + webhook paths fire pipeline refreshes **without any debouncing**, per-replica, which becomes visible as duplicate pipeline work once #354 lands and the cache is shared.

## Impact

- Multi-replica fabric deployments do not debounce rapid source-change events across replicas.
- Each replica independently handles its own observed events.
- Downstream of #354: duplicate pipeline executions become visible via shared Redis cache traces.

## Suggested fix

Implement `_RedisDebouncer` using atomic SET-NX with TTL:

```python
class _RedisDebouncer:
    async def enqueue(self, product_name: str, debounce_seconds: float, callback):
        # SET fabric:debounce:<name> <replica_id> NX EX <seconds>
        # First replica to SET within the window wins; others short-circuit.
```
````

Wire `PipelineExecutor` (or `FabricRuntime`) to instantiate `_RedisDebouncer(redis_client)` when `redis_url` is provided, `InMemoryDebouncer()` otherwise. Match the `FabricCacheBackend` pattern landed in #354.

## Dependency

This issue depends on #354 landing first, because the Redis client infrastructure will be in place after #354.

## Cross-SDK

File a matching issue on `esperie-enterprise/kailash-rs` after this one lands.

````

---

## Follow-up 2: Cross-SDK Rust parity — `CacheBackend` trait

**Repo**: `esperie-enterprise/kailash-rs`
**Label**: `enhancement`, `cross-sdk`
**Title**: `feat(dataflow-fabric): add CacheBackend trait with Redis implementation (cross-SDK alignment with terrene-foundation/kailash-py#354)`

**Body**:

```markdown
## Problem

Cross-SDK alignment with `terrene-foundation/kailash-py#354` which ships a `FabricCacheBackend` ABC with in-memory and Redis implementations for the fabric product cache.

The Rust side currently has zero Redis support in the fabric executor:

- `crates/kailash-dataflow/src/executor.rs:32-54` — `ExecutorConfig` has `max_concurrency`, `max_cache_entries`, `max_result_bytes`, `max_traces`. **No `redis_url` field.**
- `crates/kailash-dataflow/src/executor.rs:102-149` — `LruCache` struct backed by `HashMap<String, CacheEntry>` + `VecDeque<String>`. 100% in-process.
- `crates/kailash-dataflow/src/executor.rs:94-99` — `PipelineExecutor` owns `cache: Arc<Mutex<LruCache>>` with no trait abstraction.
- `grep -rn "redis\|Redis" crates/kailash-dataflow/src/` → zero matches.

This violates EATP D6 (independent implementation, matching semantics): a fabric product pipeline ported from Python to Rust changes behavior from "Redis-shared cache" (after #354 lands) to "in-process only", silently.

## Suggested fix

1. Define `trait CacheBackend` in `crates/kailash-dataflow/src/cache.rs` (new file) mirroring the Python ABC surface:
   ```rust
   #[async_trait]
   pub trait CacheBackend: Send + Sync {
       async fn get(&self, key: &str) -> Result<Option<CacheEntry>>;
       async fn get_hash(&self, key: &str) -> Result<Option<String>>;
       async fn set(&self, key: &str, entry: CacheEntry) -> Result<()>;
       async fn invalidate(&self, key: &str) -> Result<bool>;
       async fn invalidate_matching(&self, pattern: &str) -> Result<usize>;
       async fn close(&self) -> Result<()>;
   }
````

2. Two implementations:
   - `InMemoryCacheBackend` — migrate existing `LruCache` logic behind the trait.
   - `RedisCacheBackend` — use `redis = { version = "0.27", features = ["tokio-comp"] }` as an optional feature.
3. `ExecutorConfig` gains an `Option<String> cache_redis_url` field; `PipelineExecutor::new` selects backend based on it.
4. Schema alignment: match the Python key layout exactly (`fabric:product:<instance>:<tenant>:<name>[:<params_hash>]`).
5. Cross-replica semantics: last-writer-wins with content-hash dedup (matches Python R3 recommendation).
6. Tests: integration test against real Redis via testcontainers.

## Dependency

Blocked by `terrene-foundation/kailash-py#354` landing first (to ratify the schema and ABC shape).

## References

- Python issue: terrene-foundation/kailash-py#354
- Python analysis: `workspaces/issue-354/01-analysis/` in kailash-py
- Rust current state: `crates/kailash-dataflow/src/executor.rs:32-149`

````

---

## Follow-up 3: Unify `dataflow/cache/` with `dataflow/fabric/cache.py` (ADR)

**Repo**: `terrene-foundation/kailash-py`
**Label**: `architecture`, `adr-candidate`, `tech-debt`
**Title**: `adr(dataflow): unify dataflow/cache/ (query cache) with dataflow/fabric/cache.py (product cache) into a single CacheBackend story`

**Body**:

```markdown
## Problem

After #354 lands, kailash-dataflow will have **two parallel cache systems**:

1. `dataflow/cache/` — query cache, express cache. `CacheBackend.auto_detect()` returns `AsyncRedisCacheAdapter | InMemoryCache`. Thread-pool-wrapped sync Redis client.
2. `dataflow/fabric/cache.py` (new in #354) — product cache. `FabricCacheBackend` ABC with `InMemoryFabricCacheBackend | RedisFabricCacheBackend`. Direct `redis.asyncio` client, no thread pool.

The two systems have:
- Different TTL semantics (query TTL vs content-hash dedup + staleness-policy TTL)
- Different invalidation semantics (query pattern-based vs per-product + pattern)
- Different key schemas (query fingerprint vs product_name+params+tenant)
- Different Redis clients (sync-over-thread-pool vs async)

## Why this is worth an ADR

Two cache systems in the same package is a framework-first violation inside the framework. Eventually a user will ask "why are there two cache layers?" and the answer will be unsatisfying. The unification is architecturally correct but has real cost:

- Merging two TTL models into one is a semantic decision, not a code change.
- The query cache's pattern-based invalidation doesn't map cleanly to per-product keys.
- The express cache is a hot path — any thread-pool replacement must be benchmarked.
- The fabric cache is a new hot path — any unification must not re-introduce the thread-pool overhead that #354 explicitly rejected.

## Suggested scope

An ADR documenting:
1. The two cache systems as they exist post-#354.
2. Options for unification: (a) single backend + multiple adapters, (b) single abstract store + per-use-case ABC, (c) leave them separate and document the rationale.
3. Performance budgets and migration cost.
4. Decision and next steps.

Not a code change. An architecture decision that should precede any refactor.
````

---

## Coordination notes

1. **Order**: `#354 → Follow-up 1 → Follow-up 2 → Follow-up 3`. Each depends on the previous.
2. **Cross-repo**: Follow-up 2 is filed on `esperie-enterprise/kailash-rs` AFTER #354 merges. Per `.claude/rules/artifact-flow.md`, BUILD repos do not sync directly; all coordination goes through `loom/`.
3. **Labels**: use `cross-sdk` label on Rust issue; `dependency-of-354` on Python follow-ups.
4. **Owner**: same session author can file all three via `gh issue create` after the #354 PR is merged.
