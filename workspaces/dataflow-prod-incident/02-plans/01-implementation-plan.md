# 02 — Implementation Plan

Three shards, sized per `rules/autonomous-execution.md` § "Per-Session Capacity Budget" (≤500 LOC load-bearing logic, ≤5–10 invariants, ≤3–4 call-graph hops, describable in 3 sentences). Each shard is a single session with a single specialist + reviewer.

## Sequencing

```
Shard A (#696 DDL fail-fast)            ─┐
                                         ├──→ kailash-dataflow 2.4.0 release
Shard B (#697 + #698 pool lifecycle)    ─┤    + kailash 2.12.0 patch
                                         │    (one paired release; both
Shard C (#685 + #686 engine surface)    ─┘     packages share regression
                                              tests)
```

A and B may run in parallel under `rules/worktree-isolation.md` waves-of-3 protocol — they touch different packages (`kailash-dataflow` for A, `kailash` core for B). C is independent surface work in `kailash-dataflow` and may run in parallel with A if their files don't overlap (they don't — A is `core/engine.py`, C is `engine.py`).

Recommended: launch A + C as a wave-of-2 (both in `kailash-dataflow`, separate worktrees), then B on its own (different package, different specialist load).

## Shard A — DDL fail-fast circuit breaker (#696)

**Specialist:** dataflow-specialist
**Estimated LOC:** ~250 load-bearing logic
**Invariants held:** 4 (cache-hit fast-path; failed-DDL state tracking; user override flag; no log spam)
**Files touched:** 2

### Description (3 sentences)

A failed CREATE TABLE under `auto_migrate=True` MUST be a single, loud error at startup — not a per-access silent retry. Add a per-model failed-DDL state to `DataFlow._schema_cache` that records the failure + reason, prevents subsequent retries, and surfaces a clear runtime error on the next access. Operators get one ERROR log + one metric increment per failed model, not N per request.

### Changes

1. **`packages/kailash-dataflow/src/dataflow/core/engine.py`**
   - Add `_failed_table_creations: dict[str, FailedDDLRecord]` to `DataFlow.__init__` where `FailedDDLRecord = (timestamp, error_message, statement_preview)`.
   - In `_register_model` (line 1576-1599), if `_create_table_sync()` returns False AND we're connected, fail-fast with `DDLFailedError(model_name, error)` instead of falling through to lazy creation.
   - In `ensure_table_exists()` (line 1603), check `_failed_table_creations` BEFORE the cache check. If present, raise `DDLFailedError` immediately — do NOT re-fire the DDL.
   - In `_execute_ddl()` (line 7400-7429) and `_execute_ddl_async` (line 7431-7509), wrap each statement's `except Exception` to record the failure into `_failed_table_creations` AND emit metric `dataflow.ddl_failed_total{model=...}`. Continue iterating ONLY for index/FK statements; CREATE TABLE failures abort the whole batch.
   - Add `auto_migrate` enum: `True` (fail-fast at startup, default), `"warn"` (log + continue, current behavior), `False` (no auto-migration, manual). Update `DataFlow.__init__` signature to accept `bool | Literal["warn"]`.
2. **`packages/kailash-dataflow/src/dataflow/core/exceptions.py`** (new file or existing)
   - Add `DDLFailedError(DataFlowError)` with `.model_name`, `.statement`, `.original_error` attributes.

### Tests

Per `rules/testing.md` § "End-to-End Pipeline Regression":

- **Tier 2 regression:** `tests/regression/test_issue_696_ddl_retry_storm.py` — define a model whose CREATE TABLE will fail (FK ordering or column-type mismatch), call `db.express.list()` 10 times, assert ERROR-level log fires exactly once + assert `_failed_table_creations` contains the record.
- **Tier 2 invariant:** assert that calling the failed-DDL path 100x in a tight loop does NOT increase connection count beyond 1 (proves no retry storm under saturation).
- **Tier 1 unit:** `auto_migrate="warn"` reproduces current behavior (continue + log); `auto_migrate=True` (default) fails-fast.

### Cross-SDK action

File `esperie/kailash-rs#NNN` — "DataFlow auto-migrate retry storm — same bug class as kailash-py#696". Include byte-vector regression test per `rules/cross-sdk-inspection.md` § 4.

### Edge cases / risks

- **Existing apps relying on retry-on-access** — none expected (the retry was a bug, not a feature). Migration path: `auto_migrate="warn"` opt-in.
- **Race in concurrent registration** — multiple workers may all hit the failed DDL once each before `_failed_table_creations` is populated. Acceptable: `dict.setdefault()` semantics give us at-least-once semantics; metric is correct.
- **Migration tracking table failure** — if `_ensure_migration_tables` itself fails (line 6427), the system can't track ANYTHING; needs a separate fail-fast path. Acceptable: this fails so loud you'd never miss it.

---

## Shard B — Pool lifecycle: bounded fallback + idle eviction (#697 + #698)

**Specialist:** dataflow-specialist (with infrastructure-specialist consult on the pool-registry pattern)
**Estimated LOC:** ~400 load-bearing logic
**Invariants held:** 6 (pool-key uniqueness; per-event-loop isolation; max-pool-count cap; idle-timeout reclamation; tenant-isolation preserved; no leaked pools across worker pre-fork)
**Files touched:** 2

### Description (3 sentences)

`AsyncSQLDatabaseNode`'s per-pool-locking fallback creates a fresh `EnterpriseConnectionPool` per call with no process-wide registration; pools accumulate until process shutdown. Add a process-wide `PoolRegistry` that tracks every pool by key, evicts on idle-timeout (default 300 s), and bounds total count via LRU (default 100); when the cap is exceeded, lock-timeout MUST fail-fast with a typed error instead of creating yet another pool. The eviction is event-loop-aware: pools whose loop is closed are reaped immediately; live pools wait for idle.

### Changes

1. **`src/kailash/nodes/data/async_sql.py`**
   - Add module-level `_PROCESS_POOL_REGISTRY: weakref.WeakValueDictionary[str, EnterpriseConnectionPool]` keyed on `pool_key`.
   - Add module-level config `_POOL_DEFAULTS = {"idle_timeout": 300, "max_pool_count_per_process": 100}` overridable via `set_pool_defaults()`.
   - Add `EnterpriseConnectionPool.set_idle_timeout(seconds: int)` and `EnterpriseConnectionPool.is_idle()` (last-activity timestamp tracking).
   - Add `EnterpriseConnectionPool._reaper_task` that runs every `idle_timeout / 4` seconds, walks the registry, calls `close()` + `del registry[key]` for any idle pool whose event loop is alive (pools with dead loops are reaped immediately on registry access via the WeakValueDictionary).
   - In `_get_adapter` fallback path (line 3944-3956): replace the silent fallback with:
     ```python
     except (RuntimeError, asyncio.TimeoutError) as e:
         if len(_PROCESS_POOL_REGISTRY) >= _POOL_DEFAULTS["max_pool_count_per_process"]:
             raise PoolExhaustedError(
                 f"Pool count {len(_PROCESS_POOL_REGISTRY)} exceeds cap "
                 f"{_POOL_DEFAULTS['max_pool_count_per_process']}; refusing to create dedicated fallback. "
                 f"Increase via set_pool_defaults(max_pool_count_per_process=N) or fix the contention root cause."
             ) from e
         logger.warning("async_sql.fallback_pool_created",
             extra={"pool_key": self._pool_key, "registry_size": len(_PROCESS_POOL_REGISTRY)})
         self._adapter = await self._create_adapter()
         _PROCESS_POOL_REGISTRY[f"fallback_{id(self)}"] = self._adapter._pool  # tracked!
     ```
     Note: catching bare `Exception` is removed — only `RuntimeError` (closed loop) and `asyncio.TimeoutError` (lock timeout) are legitimate fallback triggers per `rules/zero-tolerance.md` Rule 3.
   - Add `AsyncSQLDatabaseNode.pool_count() -> int` classmethod (returns `len(_PROCESS_POOL_REGISTRY)`).
2. **`src/kailash/nodes/data/exceptions.py`** (existing or new)
   - Add `PoolExhaustedError(NodeExecutionError)`.

### Tests

Per `rules/testing.md` § "End-to-End Pipeline Regression":

- **Tier 2 regression:** `tests/regression/test_issue_697_pool_leak.py` — set `max_pool_count_per_process=10`, set lock timeout to 0.1 s, spawn 50 concurrent reads against real PG. Assert pool count never exceeds 10 + assert `PoolExhaustedError` fires when cap reached.
- **Tier 2 idle eviction:** create 20 pools with `idle_timeout=2`, sleep 5 s, assert `pool_count() == 0`.
- **Tier 2 cross-event-loop:** create pool in event loop A, switch to event loop B, assert pool A is reaped (WeakValueDictionary semantics).
- **Tier 1 unit:** signature/structural invariant on `set_pool_defaults` — accepts only `idle_timeout`, `max_pool_count_per_process`; rejects unknown kwargs.

### Cross-SDK action

File `esperie/kailash-rs#NNN` — Rust DataFlow has its own pool primitive; same lifecycle gaps likely apply.

### Edge cases / risks

- **Event-loop GC race** — WeakValueDictionary auto-cleanup happens on GC; under high churn the cleanup may lag. Add an explicit reaper task as belt-and-suspenders.
- **Per-test cleanup** — pytest tests may leave registries non-empty across tests. Add `cleanup_all_pools()` extension that clears registry; fixture in `conftest.py` calls it after every test.
- **Tenant-isolation preserved** — pool keys already include `dialect|connection_string` per `rules/tenant-isolation.md` § 1; multi-tenant deployments using separate connection strings get separate pools. NO change to the keying.
- **Backwards compat** — apps that depend on unbounded pool creation will see `PoolExhaustedError` they didn't see before. Mitigation: default cap at 100 (generous) + clear error message naming `set_pool_defaults`.

---

## Shard C — DataFlowEngine surface fixes (#685 + #686)

**Specialist:** dataflow-specialist
**Estimated LOC:** ~150 load-bearing logic
**Invariants held:** 3 (engine.register_model is end-to-end; build() body matches signature; cross-SDK parity preserved on the async build path)
**Files touched:** 2

### Description (3 sentences)

`DataFlowEngine.register_model` calls a non-existent method on `DataFlow` and `DataFlowEngineBuilder.build()` is async-but-sync. Implement `DataFlow.register_model(model)` as a non-decorator entry-point that performs the same registration as `@db.model`, and add `DataFlowEngineBuilder.build_sync()` for module-import-time patterns. The async `build()` stays for cross-SDK parity with kailash-rs (where it IS legitimately async).

### Changes

1. **`packages/kailash-dataflow/src/dataflow/core/engine.py`**
   - Add `DataFlow.register_model(self, model_cls)` — extracts the class-decorator logic from `@db.model` (which currently uses `__init_subclass__` or similar) into a callable. Both paths share the same body. Returns the decorated class for chaining.
2. **`packages/kailash-dataflow/src/dataflow/engine.py`**
   - `DataFlowEngine.register_model(self, registry, model)` — fix the implementation. The `registry` param is unused by the docstring but exists for cross-SDK parity (kailash-rs passes a registry). Kailash-py path: `self._dataflow.register_model(model)`. Same downstream — append to `_registered_models`, register with classification policy if available.
   - Add `DataFlowEngineBuilder.build_sync(self) -> DataFlowEngine` — body identical to current async `build()` (which doesn't await). Document `build_async()` (alias for `build()`) for cross-SDK clarity.

### Tests

- **Tier 2 regression:** `tests/regression/test_issue_685_engine_register_model.py` — repro from issue body + assert no AttributeError + assert `engine.get_model_classification_report(Foo)` returns a dict.
- **Tier 2 regression:** `tests/regression/test_issue_686_builder_sync.py` — `DataFlowEngine.builder("sqlite:///:memory:").build_sync()` returns engine without requiring an event loop.
- **Tier 1 invariant:** `DataFlowEngineBuilder.build()` must be async OR call `build_sync()` directly — never reach a state where the async signature has body-side `await`s removed.

### Cross-SDK action

- #685: filed as cross-SDK; verify Rust `register_model` is end-to-end.
- #686: NOT filed cross-SDK — Rust's `build()` IS legitimately async (runtime init). Python's sync companion is a Python-specific affordance.

### Edge cases / risks

- **Existing `@db.model` usage** — extracting the class-decorator body MUST not change `@db.model` semantics. Tier 1 test: `@db.model class X` produces same registration as `db.register_model(X)`.
- **HANA Phase 2 unblock** — once `build_sync` ships, HANA's ADR 0003 deferral is closed. Add a note to the release CHANGELOG.

---

## Combined release plan

### Branches (per `rules/git.md` § Release-Prep)

- `feat/dataflow-696-ddl-fail-fast` (Shard A)
- `feat/dataflow-697-698-pool-lifecycle` (Shard B)
- `feat/dataflow-685-686-engine-surface` (Shard C)
- `release/v2.4.0-dataflow-prod-incident` (release-prep PR, metadata-only)

### Release scope

- **`kailash-dataflow`** 2.3.3 → 2.4.0 (semver-major because `auto_migrate=True` default now fails-fast — behavioral change for apps that depended on the retry-storm bug)
- **`kailash`** 2.11.3 → 2.12.0 (semver-major because `_PROCESS_POOL_REGISTRY` adds a process-wide cap that fails-fast on exhaustion)

Per `feedback_optimal_outcome` — choose the optimal architecture; semver-major is the honest semver call. Per `feedback_no_shims` — no deprecation timeline; the cleanup happens in the same release.

### Pre-release gates

Per `rules/deployment.md` § "Before Any Release" + `rules/git.md` § "Pre-FIRST-Push CI Parity":

1. Full test suite green across Python 3.11 / 3.12 / 3.13 / 3.14
2. Tier-2 regression tests pass against real PostgreSQL (Azure-class)
3. Cross-SDK parity issues filed at `esperie/kailash-rs`
4. Security review by security-reviewer (mandatory per `rules/agents.md` Quality Gates)
5. Reviewer + security-reviewer pass at `/implement` gate
6. `pre-commit run --all-files` + `pytest --collect-only` exit 0 across every test directory
7. CHANGELOG entries for all three shards under one 2.4.0 / 2.12.0 release block
8. Spec updates: `specs/dataflow-core.md` section on `auto_migrate` semantics; `specs/dataflow-cache.md` section on pool lifecycle

### Cross-SDK propagation

After kailash-py release, file these issues at `esperie/kailash-rs`:

- DataFlow auto-migrate retry storm (cross-SDK of #696)
- DataFlow per-pool-locking fallback leak (cross-SDK of #697 + #698)
- DataFlowEngine.register_model parity check (cross-SDK of #685 — verify Rust path)

Per `rules/cross-sdk-inspection.md` § 4: each cross-SDK issue includes byte-vector test cases derived from kailash-py's regression tests.

---

## What stays out of this workstream

- **#699 / #700 / #701** — kailash-ml 1.5.x followup; separate workspace.
- **Loom `/sync`** — cycle 10 + cycle 11 propagation; not BUILD-repo work.
- **Spec-drift-gate** — separate workspace, not blocked by this one.
- **Stub-marker triage** — 122 markers from sweep v1 LOW-6; spread across multiple sessions.

---

## Acceptance — "done" gate

The workspace is converged when ALL of the following hold:

1. PRs for all three shards merged to main + reviewed by reviewer + security-reviewer.
2. Release PR for `kailash-dataflow` 2.4.0 + `kailash` 2.12.0 merged.
3. Tags pushed individually per `rules/deployment.md` § "Multi-Package Release Tags Pushed Individually" (`v2.12.0`, `dataflow-v2.4.0`).
4. PyPI publishing workflow_dispatch successful for both packages.
5. Clean-venv install verified against PyPI for both packages.
6. The user's repro script runs for 30 minutes without connection-count growth.
7. Cross-SDK issues filed at kailash-rs.
8. Issues #696, #697, #698, #685, #686 closed with delivered-code references per `rules/git.md` § Issue Closure Discipline.
9. `/codify` extracts new institutional knowledge (e.g., "silent-fallback + no-lifecycle is one failure pattern; structural fix at three layers" deserves codification).
