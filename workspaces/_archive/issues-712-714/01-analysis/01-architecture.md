# Architecture — issues #712 / #713 / #714

## Brief corrections

The original brief contained THREE distinct factual inaccuracies — surfaced
by parallel deep-dive verification per `rules/agents.md` MUST rule on
≥3-issue briefs. These corrections were caught BEFORE plan drafting; without
the parallel sweep, the implementation would have targeted the wrong root
causes.

| Issue | Brief asserted                                                                                    | Reality (per deep-dive)                                                                                                                                                        |
| ----- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| #712  | `WorkflowServer.__init__` constructs FastAPI with `lifespan=` set, silently disabling `@on_event` | Lifespan IS set, but it explicitly iterates `app.router.on_startup` (lines 234-237) and `on_shutdown` (lines 279-282). `@on_event` IS picked up. The brief mis-frames the bug. |
| #712  | Cited `workflow_server.py:138-149` for FastAPI construction                                       | Actual is `:297-299`; lines 138-149 are docstring                                                                                                                              |
| #713  | Cited `engine.py:452-460` for runtime selection                                                   | Actual is `:552-565` (file is 10,083 lines)                                                                                                                                    |
| #713  | Cited `engine.py:7271` for `_execute_ddl_async`                                                   | Actual is `:7688`                                                                                                                                                              |

## Per-issue architecture

### #712 — Nexus startup-handler discoverability + sibling FastAPI sites

**Real failure modes (revised)**:

1. **Discoverability gap**: There is NO public `Nexus.add_startup_handler(func)` method. Consumers wanting to register an async startup hook must:
   - Write a Plugin class implementing `NexusPluginProtocol` (verbose), OR
   - Reach for `nexus.fastapi_app.on_event(...)` — which:
     - Has a timing trap (the property returns `None` until lazy `_initialize_gateway()` fires on first `register()`)
     - Lands in `app.router.on_startup` and IS executed by the lifespan
     - Works correctly if registered BEFORE `nexus.start()`, but the consumer doesn't know about the timing trap

2. **Sibling FastAPI() construction sites — CONFIRMED unmitigated #500-class bugs** (deep-dive verified):
   - `KailashAPIGateway` at `src/kailash/middleware/communication/api_gateway.py:191-208` — lifespan calls only `_log_startup()` + `_cleanup()`, NO router iteration. Public class.
   - `WorkflowAPIGateway` at `src/kailash/api/gateway.py:136-149` — lifespan logs + closes `_proxy_client`, NO router iteration. Public class.
   - `WorkflowAPI` at `src/kailash/api/workflow_api.py:144-173` — `_lifespan` only `yield`s + clears `_execution_cache`, NO router iteration. Public class.
     Two sites without `lifespan=` are safe by default (`visualization/api.py`, `gateway/api.py`). Possible additional audits needed in `kailash-kaizen/.../metrics_endpoint.py`, `metrics_auth.py`, `dashboard.py`, `kailash-pact/.../router.py`. Per `security.md` § Multi-Site Kwarg Plumbing + `rules/agents.md` Rule 3 fix-immediately, all confirmed sites MUST be patched in the same PR.

3. **The downstream consumer likely on stale Nexus** (pre-2.1.1, where the #500 fix landed). Their `app.router.lifespan_context` workaround is the same one impact-verse used pre-2.1.1.

**Fix surface (#712)**:

| Component                                                                                                             | Change                                                                                                                                                                                    | Rationale                                                                                                                                 |
| --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `packages/kailash-nexus/src/nexus/core.py`                                                                            | Add `Nexus.add_startup_handler(func)` and `Nexus.add_shutdown_handler(func)` public methods that route into existing `_startup_hooks`/`_shutdown_hooks` infrastructure                    | Closes the discoverability gap. Under-the-hood plumbing already exists for plugin protocol; new methods are 30-50 LOC.                    |
| `packages/kailash-nexus/src/nexus/__init__.py`                                                                        | Add new methods to `__all__` if exported as module-level surface                                                                                                                          | Per orphan-detection.md Rule 6                                                                                                            |
| NEW `src/kailash/utils/lifespan.py`                                                                                   | Extract shared helper module: `drive_router_lifespan_startup(app)` + `drive_router_lifespan_shutdown(app)`. Single source of truth for FastAPI/Starlette router-iteration semantics.      | Localizes the cross-version invariant to one file + one test. Prevents drift across sites the next time FastAPI changes router semantics. |
| `src/kailash/servers/workflow_server.py:234-237` + `:279-282`                                                         | Refactor existing inline iteration to call the shared helper.                                                                                                                             | Single source of truth.                                                                                                                   |
| `src/kailash/middleware/communication/api_gateway.py:191-208` (KailashAPIGateway lifespan)                            | Add calls to shared helper. Currently zero router iteration → confirmed #500-class bug.                                                                                                   | Multi-site fix per `security.md` § Multi-Site Kwarg Plumbing                                                                              |
| `src/kailash/api/gateway.py:136-149` (WorkflowAPIGateway lifespan)                                                    | Add calls to shared helper. Confirmed #500-class bug.                                                                                                                                     | Same                                                                                                                                      |
| `src/kailash/api/workflow_api.py:144-173` (WorkflowAPI `_lifespan`)                                                   | Add calls to shared helper. Confirmed #500-class bug.                                                                                                                                     | Same                                                                                                                                      |
| Audit pass: `kailash-kaizen/.../metrics_endpoint.py`, `metrics_auth.py`, `dashboard.py`, `kailash-pact/.../router.py` | Verify whether each constructs FastAPI with `lifespan=`. If yes, route through shared helper. If internal-only with no consumer surface, document as "internal — `on_event` not exposed". | Sweep per `rules/agents.md` Rule 3 fix-immediately                                                                                        |
| `tests/regression/test_issue_712_lifespan_consumer_patterns.py`                                                       | New regression test exercising `@nexus.app.on_event("startup")` from CONSUMER perspective (downstream-consumer pattern) AND `nexus.add_startup_handler(func)` from new public API                  | Tier-2/3 per `testing.md` §3-tier; behavioral assertion (call hook, observe side effect)                                                  |
| `specs/nexus-core.md` §10                                                                                             | Add §10.3 documenting `Nexus.add_startup_handler/add_shutdown_handler`. Update §10.2 cross-reference.                                                                                     | Spec authority Rule 5                                                                                                                     |
| Docs / docstrings on `Nexus`, `Nexus.fastapi_app`                                                                     | Document the timing trap on `fastapi_app` (None before gateway init)                                                                                                                      | Discoverability                                                                                                                           |

### #713 — DataFlow runtime binding at construction

**Real failure mode**: `DataFlow.__init__` (lines 552-565) selects `LocalRuntime` vs `AsyncLocalRuntime` ONCE at construction via `asyncio.get_running_loop()`. Module-import construction (the natural FastAPI pattern) binds `LocalRuntime` permanently, so any later `db.create_tables_async()` call inside uvicorn's loop hits `AttributeError: 'LocalRuntime' object has no attribute 'execute_workflow_async'`.

**Workaround the downstream consumer found**: `db.runtime = AsyncLocalRuntime(); db._is_async = True`. Works for `_execute_ddl_async` (which reads `self.runtime` fresh per call at line 7664) but does NOT propagate to subsystems that captured `self.runtime` in their own `__init__`: `ModelRegistry`, `BulkOperations`, `TransactionManager`, `auto_migration_system`, `schema_state_manager`, `gateway_integration` (6 subsystems, ~12 capture sites). The workaround is fragile.

**Fix surface (#713)** — combination of two approaches:

| Component                                                                                                                                               | Change                                                                                                                                                                                                                                                                              | Rationale                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `packages/kailash-dataflow/src/dataflow/core/engine.py:552-565`                                                                                         | Convert `self.runtime` from a plain attribute to a `@property` with a setter. Property detects async context per access (cached per event-loop ID, similar to `_async_sql_node_cache` at line 7488). Setter preserves `db.runtime = X` mutation pattern for tests + workarounds.    | Lazy + per-loop cache fixes the module-import case; setter preserves backwards-compat |
| `packages/kailash-dataflow/src/dataflow/core/engine.py` `__init__` signature                                                                            | Add `runtime: Optional[Runtime] = None` kwarg; if provided, skip auto-detect                                                                                                                                                                                                        | Explicit escape hatch for tests + advanced usage                                      |
| 6 subsystem captures (`model_registry.py:151`, `gateway_integration.py:103,113`, `auto_migration_system.py:266 etc`, `schema_state_manager.py:696 etc`) | Convert to lazy lookups via parent's property accessor — pass `self._dataflow_ref` and read `self._dataflow_ref.runtime` each access                                                                                                                                                | Subsystems must follow parent's runtime, not snapshot                                 |
| `tests/regression/test_issue_713_module_import_then_async_ddl.py`                                                                                       | New regression: `db = DataFlow(...)` at module scope (sync), then `await db.create_tables_async()` inside `asyncio.run(...)`. Pre-fix: `AttributeError`. Post-fix: succeeds. Plus subsystem-test: ModelRegistry follows runtime swap.                                               | Tier-2 against PostgreSQL container                                                   |
| `specs/dataflow-core.md` §1.5                                                                                                                           | Update from "selected at construction" to "lazily resolved per access via per-loop cache, with `db.runtime = X` as override surface and `runtime=` kwarg as init-time override". Plus sibling re-derivation across `dataflow-{express,models,cache}.md` per spec-authority Rule 5b. | Spec authority Rule 5 + 5b                                                            |

### #714 — DDL connection thrash

**Real failure mode (post deep-dive — brief was misframed)**:

The brief framed this as "fresh pool per model." That framing is **incorrect**. `AsyncSQLDatabaseNode` defaults `share_pool=True` (`async_sql.py:2897, 3684`) with a class-level `_shared_pools` dict keyed by config — iterations over models with the same connection_string DO reuse the asyncpg pool. There is only ONE underlying pool per process per connection_string.

Actual failure modes:

1. **Per-statement node + WorkflowBuilder construction** in `_execute_ddl` (`engine.py:7531-7627`) and `_execute_ddl_async` (`:7629-7722`). Each iteration constructs a fresh `AsyncSQLDatabaseNode` and a fresh `WorkflowBuilder`. The pool is reused via `_shared_pools` cache hit, but the workflow build/teardown overhead is wasted.

2. **DDL via `AsyncSQLDatabaseNode` is overkill**: DDL is single-connection work. Routing it through a pool-aware, transaction-mode-aware, fetch-mode-aware node creates a connection pool the operator must size for DDL bursts. With `pool_size=10`, that's 10 client connections held against pgbouncer — even with `share_pool`. If the pgbouncer session-mode cap is below `pool_size`, the cap is hit.

3. **the downstream consumer's specific `MaxClientsInSessionMode`** likely triggered when (a) `share_pool` was disabled by config, (b) `pool_size` was configured > pgbouncer cap, or (c) a sibling DataFlow code path concurrently allocated against the same cap. The brief's "19 models × per-model pool" is an oversimplification but the symptom is real.

**Fix surface (#714)**:

| Component                                                                                                  | Change                                                                                                                                                                                                                                             | Rationale                                                                   |
| ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `packages/kailash-dataflow/src/dataflow/core/engine.py:7531` `_execute_ddl` + `:7629` `_execute_ddl_async` | Refactor to bypass `AsyncSQLDatabaseNode` for DDL. Acquire ONE connection from `self._connection_manager`, run all DDL statements on it, release. Use dialect's connection directly via `dataflow.adapters.<dialect>` per `infrastructure-sql.md`. | DDL is single-connection work; doesn't need pool/transaction/fetch plumbing |
| `tests/regression/test_issue_714_create_tables_pgbouncer.py`                                               | Tier-3: spin up pgbouncer container in session-mode with low cap (≤5 clients), register 10+ models, call `create_tables()` AND `create_tables_async()`, assert no `MaxClientsInSessionMode` and steady-state connection count = 1 during DDL.      | Real infra, real failure mode per `testing.md` Tier-3                       |
| `specs/dataflow-core.md` §1.4 (lazy connection) and §1.6 (auto_migrate)                                    | Document DDL connection-reuse pattern; cross-reference #696 (related pool-exhaustion failure mode under `auto_migrate=True`)                                                                                                                       | Spec authority Rule 5                                                       |

## Why all three ship together

the downstream consumer's recovery requires all three fixes:

```
WITHOUT #712: consumer cannot register startup hook                    → blocked
WITHOUT #713: consumer wraps lifespan, calls db.create_tables_async()  → AttributeError
WITHOUT #714: consumer falls back to sync, hits pgbouncer cap          → MaxClientsInSessionMode
```

Each fix removes one workaround; only all three together reduce the
downstream `<external consumer codebase>` workaround to zero.

Per the brief's constraint: "Fixes MUST land such that the downstream
workaround can be deleted entirely."

## Spec coverage required

Per `rules/specs-authority.md` Rule 4 (read specs first) and Rule 5b
(sibling re-derivation):

- `specs/nexus-core.md` §10 — extend with public lifespan-handler API
- `specs/nexus-services.md` (FastAPI app construction) — document the timing trap on `fastapi_app`
- `specs/dataflow-core.md` §1.4 + §1.5 — document new lazy runtime resolution + DDL pool-reuse
- Sibling re-derivation: `specs/dataflow-express.md`, `specs/dataflow-models.md`, `specs/dataflow-cache.md` — verify any references to "runtime selected at construction" or "per-model pool"

## Sharding for /todos

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget (≤500 LOC
load-bearing per shard, ≤5-10 invariants), the work shards naturally as:

| Shard | Issue           | Surface                                                                                                                                                     | LOC est.              | Invariants                                                                                                  |
| ----- | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------- |
| S1    | #712 helper     | NEW `src/kailash/utils/lifespan.py` shared helper + refactor `workflow_server.py` to use it + Tier-2 unit test for the helper                               | ~80 LOC               | router iteration semantics, coroutine vs sync handler dispatch, exception isolation per handler             |
| S2    | #712 siblings   | Patch 3 sibling FastAPI lifespan sites (api_gateway, gateway, workflow_api) to call shared helper; audit kaizen+pact internals                              | ~100 LOC              | every public lifespan iterates `router.on_startup`/`on_shutdown`, no internal-only sites left silent        |
| S3    | #712 public API | Add `Nexus.add_startup_handler/add_shutdown_handler` + Tier-3 regression test + spec §10.3 + docstring on `fastapi_app` timing trap                         | ~200 LOC              | discoverability, hooks fire, no double-fire, async-task survival, post-start registration rejected          |
| S4    | #713 core       | Lazy `runtime` `@property` + setter + `runtime=` kwarg in `__init__` + Tier-3 regression (module-import-then-async-DDL)                                     | ~200 LOC load-bearing | per-loop cache correctness, setter wins over auto-detect, kwarg wins over both, sync path unchanged         |
| S5    | #713 subsystems | Convert 6 subsystem captures (ModelRegistry, BulkOps, TransactionManager, auto_migration, schema_state_manager, gateway_integration) to lazy lookups        | ~150 LOC              | every subsystem follows parent's runtime swap, no orphan captures, all 12+ capture sites converted          |
| S6    | #714            | Refactor `_execute_ddl` + `_execute_ddl_async` to bypass `AsyncSQLDatabaseNode` and use single connection from `_connection_manager`; Tier-3 pgbouncer test | ~150 LOC              | single connection across DDL loop, async + sync paths symmetric, no `MaxClientsInSessionMode` under low cap |
| S7    | Specs + docs    | Update `dataflow-core.md` §1.4, §1.5, §1.6, `nexus-core.md` §10, `nexus-services.md`; sibling re-derive across `dataflow-{express,models,cache}.md`         | ~150 LOC              | spec authority Rule 5b sibling sweep, every brief requirement maps to a spec section                        |

Total: ~1030 LOC across 7 shards, all within budget. Dependencies:

- S2 depends on S1 (shared helper must exist before siblings can call it)
- S5 depends on S4 (subsystems consume the parent property)
- S7 (specs) is best done last, observing the actual landed surface

Parallelizable wave 1 (no inter-dependencies): {S1, S3, S4, S6}.
Wave 2 (after S1): {S2}. Wave 2 (after S4): {S5}. Wave 3 (after all): {S7}.

Per `rules/worktree-isolation.md` Rule 4 (waves of ≤3 worktree agents),
launch Wave 1 in two sub-waves: {S1, S4, S6} first, then {S3} after.

This keeps Wave 1 critical-path latency at ~1 worktree-agent duration plus
the second sub-wave for S3.

## Cross-SDK parity check

Per `rules/agents.md` § Worktree Isolation (kailash-rs has equivalent code paths):

- Nexus side: kailash-rs uses axum + tokio, no equivalent custom-lifespan footgun (per #501 cross-SDK note)
- DataFlow side: kailash-rs uses tokio runtime which is always present once `#[tokio::main]` runs; the runtime-binding-at-construction issue does NOT have a structural analogue
- Pgbouncer / pool-exhaustion: kailash-rs may or may not have this — file companion issue OR add `python-specific:` PR comment

## Files of interest captured

- `src/kailash/servers/workflow_server.py:297-299` (FastAPI ctor); `:203-295` (lifespan); `:234-237` + `:279-282` (router iteration)
- `packages/kailash-nexus/src/nexus/core.py:1942` (`add_plugin`); `:573-579` (`fastapi_app` property); `:775-787` (lifespan wiring); `:2084-2103` (`_call_startup_hooks_async`)
- `packages/kailash-dataflow/src/dataflow/core/engine.py:552-565` (runtime selection); `:7664, :7688` (DDL execute); `:6588-6595` (sync DDL refusal)
- 6 subsystem capture sites: `model_registry.py:151,169,175`, `gateway_integration.py:103,113`, `auto_migration_system.py:266,276,1024,1034,1605,1615`, `schema_state_manager.py:696,708`
- 3 sibling FastAPI sites: `middleware/communication/api_gateway.py:201`, `api/gateway.py:147`, `api/workflow_api.py:145`
- 1 backwards-compat-sensitive test: `test_string_id_type_coercion_integration.py:35` (assigns `db.runtime`)
- 3 prior regression tests: `tests/regression/test_issue_500_router_on_startup.py`, `:test_issue_501_hook_task_lifetime.py`, `:test_issue_531_nexus_lifespan_startup_shutdown.py`
