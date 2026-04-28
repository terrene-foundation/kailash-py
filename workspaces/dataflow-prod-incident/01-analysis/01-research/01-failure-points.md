# 01 — Failure Points Analysis

Five issues, three coupled shards, two coupled root causes. This file maps each issue to the production code that produced it, identifies the underlying invariant violated, and surfaces the cross-cutting failure pattern.

## Shard A — DataFlow auto_migrate retry storm (#696)

### Code path

| File                                                    |     Lines | Behavior                                                                                                                                                                            |
| ------------------------------------------------------- | --------: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `packages/kailash-dataflow/src/dataflow/core/engine.py` | 1576-1599 | `_register_model` calls `_create_table_sync()` if connected; on failure, `logger.debug("sync DDL failed, table will be created lazily on first access")` and proceeds.              |
| `packages/kailash-dataflow/src/dataflow/core/engine.py` | 1603-1689 | `ensure_table_exists()` is the lazy-creation hot path. Checks `_schema_cache` (line 1632), runs full migration if not cached. **Cache is marked-ensured ONLY on success.**          |
| `packages/kailash-dataflow/src/dataflow/core/engine.py` | 7400-7429 | `_execute_ddl` (sync). Bare `except Exception as e: logger.error(f"Failed to execute DDL: {statement[:100]}... Error: {e}"); continue` — no state, no retry-suppression, no metric. |
| `packages/kailash-dataflow/src/dataflow/core/engine.py` | 7431-7509 | `_execute_ddl_async`. Same swallow pattern at line 7504-7508.                                                                                                                       |

### Root cause

The error path violates two MUST clauses:

1. **`zero-tolerance.md` Rule 3 (silent fallbacks).** `except Exception: continue` after a DDL failure is the canonical silent-fallback. The error log is ERROR level (correct) but the **next** model access re-enters `ensure_table_exists()`, the cache says "not ensured", and the failed DDL fires again. The "fallback" is implicit: failure becomes infinite retry.
2. **`dataflow-pool.md` Rule 2 (validate at startup).** Pool config and connectivity are validated, but DDL applicability is not. A model whose CREATE TABLE will fail (FK ordering, role lacks CREATE, column-type mismatch) is NOT detected at `DataFlow.__init__` — only at first access.

### Why it amplifies in production

- Every 30 s, the FastAPI app's health check (or any user request that touches a model) re-enters `ensure_table_exists()`.
- The schema cache in `_schema_cache` only marks-ensured on success, so failed-DDL models stay un-cached forever.
- Combined with #697 below, every retry creates a brand-new connection pool of 5–20 connections that is never reclaimed.

### Invariant the fix must preserve

A failed CREATE TABLE under `auto_migrate=True` MUST be a single, loud, fail-fast error AT STARTUP — not a per-access silent retry. The user MUST be able to override (e.g., `auto_migrate="warn"` for dev) but the default MUST surface the failure at the point the operator can act on it.

---

## Shard B — AsyncSQLDatabaseNode pool fallback leak (#697 + #698)

### Code path

| File                                  |     Lines | Behavior                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------------------------- | --------: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/kailash/nodes/data/async_sql.py` |   501-575 | `EnterpriseConnectionPool.__init__`. Min/max size, health-check interval, analytics interval. **No `idle_timeout`. No process-wide cap.**                                                                                                                                                                                                                                           |
| `src/kailash/nodes/data/async_sql.py` | 3835-3876 | `_generate_pool_key()` includes `id(get_running_loop())` for event-loop isolation. Per-event-loop separation is intentional; per-instance fallback is not.                                                                                                                                                                                                                          |
| `src/kailash/nodes/data/async_sql.py` | 3878-3962 | `_get_adapter` — three priority paths: external pool → runtime pool → class-level shared pool. The shared-pool path acquires a per-pool lock with `timeout=5.0`.                                                                                                                                                                                                                    |
| `src/kailash/nodes/data/async_sql.py` | 3944-3956 | **The leak.** `except (RuntimeError, asyncio.TimeoutError, Exception)` catches anything; sets `self._share_pool = False`, `self._pool_key = None`, calls `_create_adapter()` to make a fresh dedicated pool. **The dedicated pool is held only on the node instance** — every subsequent call sees `self._adapter is None` (different instance) and creates ANOTHER dedicated pool. |

### Root cause

Three coupled MUST violations:

1. **`zero-tolerance.md` Rule 3 (silent fallback).** The `WARNING` log fires once per fallback, but the leak is invisible to alerting because the log doesn't escalate. From the issue body: "These pairs repeated 4-5 times per 30s. Each 'fallback' creates a brand-new EnterpriseConnectionPool (5-20 connections) that is never reclaimed mid-process."
2. **`dataflow-pool.md` Rule 5 (no orphan runtimes — extends to pools).** A pool created in fallback mode has no parent registry that would call its `close()`. Only `AsyncSQLDatabaseNode.cleanup_all_pools()` at process shutdown reaps it. This is the orphan-pool sibling of the orphan-runtime pattern (Phase 5.11 prior art).
3. **`zero-tolerance.md` Rule 6 (no half-implementation).** `EnterpriseConnectionPool` ships with no `idle_timeout`, no LRU eviction, no `max_pool_count_per_process`. The class advertises "enterprise" features (analytics, health checks, circuit breaker) but lacks the lifecycle invariant that any production-grade pool needs.

### Why it amplifies in production

- Per-event-loop isolation means each gunicorn worker pre-fork sees `id(get_running_loop())` change → new pool key → new pool.
- 13 DataFlow instances × N event-loop transitions = 13 × N pools.
- Combined with #696, every 30 s the failed-DDL retry fires under saturation. Saturation triggers the 5 s lock-timeout. Each timeout creates a new 5–20 connection pool.
- Within minutes: 480–500 connections vs Azure PG's 100–200 ceiling.

### Invariant the fix must preserve

(a) Fallback is a structural option, not a silent default. (b) Every pool created in fallback mode is registered process-wide so it can be reclaimed on idle. (c) Pool-creation events are bounded — when the pool count exceeds a threshold, new lock-timeouts fail-fast instead of creating yet another pool.

---

## Shard C — DataFlowEngine surface holes (#685 + #686)

### Code path

| File                                               |   Lines | Behavior                                                                                                                                                                            |
| -------------------------------------------------- | ------: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `packages/kailash-dataflow/src/dataflow/engine.py` | 235-265 | `DataFlowEngineBuilder.build()` is `async def`, body never `await`s. Body: instantiate DataFlow + QueryEngine, call `dataflow.source()` (sync method), instantiate DataFlowEngine.  |
| `packages/kailash-dataflow/src/dataflow/engine.py` | 328-346 | `DataFlowEngine.register_model(self, registry, model)` calls `self._dataflow.register_model(model)` — **DataFlow has no such method.** Decorator-only registration via `@db.model`. |

### Root cause

Two MUST violations:

1. **`zero-tolerance.md` Rule 6 (no half-implementation).** Line 339 — `self._dataflow.register_model(model)` — IS the half-implementation. The method is documented in the docstring (line 32-36 of `engine.py`: "engine.register_model(registry, UserModel)"), the signature exists, the inner body refers to a nonexistent method on the wrapped object. This is the canonical "if endpoint exists, it returns real data" failure mode.
2. **`patterns.md` § "Paired Public Surface — Consistent Async-ness".** `build()` is async, never awaits. Module-import-time `@lru_cache get_db()` patterns can't use it. HANA Phase 2 deferred via ADR 0003 because of this.

### Why these are HIGH not CRIT

- They block engine-first migration but don't take production down. HANA's deferral is the audit trail.
- The fix is small (single-shard, ≤200 LOC) and well-bounded — the engine surface is < 500 LOC total.

### Invariant the fix must preserve

(a) `register_model` either works end-to-end (registers with classification policy + `_registered_models` + the `DataFlow` model registry) OR is removed (zero-tolerance Rule 6 — half-implementation is BLOCKED, but the surgical option is delete-not-deprecate per `orphan-detection.md` Rule 3). User comment on the issue suggests it should work. (b) `build()` shape matches its body: either drop async OR add a synchronous companion that downstream import-time patterns can use.

---

## Cross-cutting failure pattern

**Three of five issues (#696, #697, #698) trace to the same root: silent fallback + no lifecycle bound.**

In each case, the failure mode is "the framework ran into an error, decided to keep working, and didn't surface the cost of keeping working":

- #696: failed DDL → "we'll try again next time" (forever)
- #697: per-pool lock timeout → "we'll make a dedicated pool" (forever, no eviction)
- #698: pool created → "we'll keep it until shutdown" (forever, no idle bound)

This is the production-incident class that `zero-tolerance.md` Rule 3 + `dataflow-pool.md` Rule 5 + `observability.md` Rule 7 all target separately. The fix is structural at three layers:

- **Surface (DDL):** convert "failed → retry on every access" into "failed → flagged + bounded + surfaced".
- **Lifecycle (pool):** convert "pool created → pool kept" into "pool created → pool tracked → pool reclaimed".
- **Visibility:** every state transition emits a structured log + metric so alerting can fire BEFORE the connection ceiling.

#685 + #686 are independent surface-holes on the engine builder; same package, same release, different bug class. Bundling them into the same workstream is correct (one release cycle, one specialist) but they do not share a root cause with #696/#697/#698.

---

## Repro setup (for Tier-2 regression tests)

Per `rules/testing.md` § "End-to-End Pipeline Regression", every fix lands a regression test that exercises the docs-exact pattern:

### Repro 1 — DDL retry storm (#696)

```python
# Define a model whose CREATE TABLE will fail (FK ordering)
@db.model
class Order:
    user_id: int  # references user.id, but user table not yet defined

# Initialize with auto_migrate=True
db = DataFlow(test_pg_url, auto_migrate=True)

# Touch the model 10 times — failed DDL must NOT fire 10 times
for _ in range(10):
    try: await db.express.list("Order")
    except Exception: pass

# Assertion: log captured exactly 1 ERROR + 1 metric, NOT 10
assert error_log_count("Failed to execute DDL") == 1  # not 10
```

### Repro 2 — Pool fallback leak (#697 + #698)

```python
# Force lock contention by setting timeout very low + spawning many concurrent calls
import os; os.environ["DATAFLOW_PER_POOL_LOCK_TIMEOUT"] = "0.1"
db = DataFlow(test_pg_url)

# 50 concurrent reads — many will hit the lock-timeout fallback
await asyncio.gather(*(db.express.list("User") for _ in range(50)))

# Assertion: total pool count stays bounded under a configured cap
assert AsyncSQLDatabaseNode.pool_count() <= MAX_POOL_COUNT_PER_PROCESS
```

### Repro 3 — Engine.register_model (#685)

```python
db = DataFlow("sqlite:///:memory:", auto_migrate=True)
engine = await DataFlowEngine.builder("sqlite:///:memory:").build()

@db.model
class Foo:
    name: str

engine.register_model(None, Foo)  # MUST succeed (no AttributeError)
report = engine.get_model_classification_report(Foo)
assert isinstance(report, dict)
```

### Repro 4 — Builder sync companion (#686)

```python
# Module-import-time pattern (HANA Phase 2's blocker)
@lru_cache
def get_db():
    return DataFlowEngine.builder_sync("sqlite:///app.db").build_sync()

# OR confirm async signature is honest:
import inspect
src = inspect.getsource(DataFlowEngineBuilder.build)
assert "await " in src or "async with" in src  # signature MUST match body
```

---

## Cross-SDK applicability (per `rules/cross-sdk-inspection.md`)

| Issue | kailash-rs equivalent?                                                                                                                                                           | Disposition                                                                        |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| #696  | Likely. Rust DataFlow auto-migrate has the same model-access lazy-creation pattern.                                                                                              | File cross-SDK issue at `esperie/kailash-rs` after this fix lands; reference here. |
| #697  | Almost certainly. Rust DataFlow has `EnterpriseConnectionPool` analog.                                                                                                           | File cross-SDK issue.                                                              |
| #698  | Same as #697.                                                                                                                                                                    | Bundle.                                                                            |
| #685  | Probably not — Rust uses generics for model registration; the AttributeError class doesn't exist. Verify with structural-API-divergence test per `cross-sdk-inspection.md` § 3a. | File a verification ticket only.                                                   |
| #686  | Originated from cross-SDK parity. Rust's `build()` IS legitimately async (runtime initialization). The fix here is a sync companion, not a surface change.                       | No cross-SDK issue.                                                                |

---

## Open questions for the implementation phase

1. **DDL fail-fast vs retry-with-backoff.** The user's recommendation in #696 is fail-fast at startup with a clear error. Is there a consumer who legitimately wants retry-with-backoff (e.g., DDL in a multi-region setup where the secondary takes time to propagate)? If yes, that becomes a configurable option (`auto_migrate=True` → fail-fast; `auto_migrate="retry"` → bounded retry with circuit breaker).
2. **Pool eviction policy.** LRU on idle-timeout is the obvious choice. But for an event-loop-isolated pool key, "LRU" needs to mean "evict the oldest pool whose event loop is still alive" or "evict pools whose event loop is gone". The latter is automatic (the loop is dead, the pool can't be used); the former needs explicit tracking.
3. **`MAX_POOL_COUNT_PER_PROCESS` default.** The issue body proposes 50. With 13 DataFlow instances × ~5 distinct event loops = ~65, so 50 is too low. Realistic default depends on PG `max_connections` ceiling. Probably 100 is safer; needs benchmarking.
4. **`force_drop=True` interaction.** If we add a "registered-models" registry to `DataFlow` for #685, does removing/replacing a model need `force_drop` semantics per `dataflow-identifier-safety.md` Rule 4? Probably yes — registration replacement that drops the prior table is destructive.
