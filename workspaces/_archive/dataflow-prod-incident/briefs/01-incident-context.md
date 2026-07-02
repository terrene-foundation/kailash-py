# Brief — DataFlow + Core SDK production-incident class

Filed during a JourneyMate (Azure FastAPI + DataFlow) production-incident response on 2026-04-28. Five GH issues cluster around two coupled defects (DDL-retry storm + AsyncSQLDatabaseNode pool leak) plus three independent surface holes. User flagged as urgent; sweep classified two as CRIT, three as HIGH.

## What the user reported

A routine deploy of the JourneyMate backend onto Azure Container Apps started a self-amplifying connection-leak loop. Backend logs showed two patterns repeating every 30 seconds:

1. **DDL retry storm.** `ERROR:dataflow.core.engine:Failed to execute DDL: CREATE TABLE IF NOT EXISTS "evaluation_dimensions" ...` and three sibling DDLs, repeating indefinitely. Root cause: when an `auto_migrate=True` DDL fails, the engine flags the model as "needs migration" and re-attempts on the **next model access**, not at startup.

2. **Pool fallback leak.** `WARNING:kailash.nodes.data.async_sql:Per-pool locking failed for AsyncSQLDatabaseNode (pool_key: ...). Falling back to dedicated pool mode.` followed by `EnterpriseConnectionPool 'postgresql_...' initialized with 5-20 connections`. Each fallback creates a fresh 5–20 connection pool that is **never reclaimed mid-process** — only `cleanup_all_pools(graceful=True)` at shutdown frees them.

Combined effect: every 30 seconds, the failed-DDL retry fires `AsyncSQLDatabaseNode` under saturation; lock-timeout path fires; new dedicated pool created; subsequent calls each create another. Within minutes, Azure PG saturates at 480–500 connections out of the 100–200 ceiling. Backend was down ~30 minutes; recovery required setting `auto_migrate=False`, restarting the BE revision, and migrating 342 hot-path call sites away from `AsyncSQLDatabaseNode` to a dedicated app-managed asyncpg pool.

## Issues bundled into this workspace

| #       | Severity | Title                                                                                         | File pointers                                                                     |
| ------- | -------- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| **696** | CRIT     | DataFlow auto_migrate fires failed CREATE TABLE on every model access                         | `src/dataflow/core/engine.py:1576-1599`, `:6391-6455`, `:7426`, `:7511-7600`      |
| **697** | CRIT     | AsyncSQLDatabaseNode 'Per-pool locking failed' silently falls back, leaks 5-20 conns per call | `src/kailash/nodes/data/async_sql.py:501`, `:574`, `:3835`, `:3944-3956`          |
| **698** | HIGH     | AsyncSQLDatabaseNode pools have no idle-timeout / LRU reclamation                             | `src/kailash/nodes/data/async_sql.py` (`EnterpriseConnectionPool`)                |
| **685** | HIGH     | `DataFlowEngine.register_model` calls non-existent method on `DataFlow` primitive             | `packages/kailash-dataflow/src/dataflow/engine.py::DataFlowEngine.register_model` |
| **686** | HIGH     | `DataFlowEngineBuilder.build()` is async but body is purely synchronous                       | `packages/kailash-dataflow/src/dataflow/engine.py::DataFlowEngineBuilder.build`   |

## Why one workspace

- **Shared specialist** — every fix belongs to dataflow-specialist + analyst; no other framework specialists involved.
- **Shared invariant set** — engine surface, model registration, connection lifecycle, classification policy. Splitting risks duplicate root-cause analysis and divergent remediation.
- **Shared release cycle** — every fix lands in `kailash-dataflow` (and `kailash` core for the AsyncSQL side). One release-prep PR, not three.
- **Shared bug class** — #696 + #697 + #698 share the connection-lifecycle root; #685 + #686 share the engine-builder surface. Same-bug-class within shard budget per `rules/autonomous-execution.md` § 4.

## What "done" looks like

1. **Production-incident pair (#696 + #697 + #698) closed** — DDL failures fail-fast at startup with typed error + bounded retry; AsyncSQLDatabaseNode pool fallback either holds longer / fails-fast OR registers the dedicated pool in a process-wide eviction registry; idle-timeout + LRU cap configurable on `EnterpriseConnectionPool`.
2. **Engine builder surface (#685 + #686) closed** — `DataFlowEngine.register_model` is either implemented end-to-end (registers with classification policy + adds to engine's registered_models) or removed; `DataFlowEngineBuilder.build()` either gains a sync companion or honours its async signature.
3. **Tier-2 regression tests** for every fix per `rules/testing.md` § "End-to-End Pipeline Regression" — each canonical pipeline the user could reasonably write must execute against real PG without leaking connections or storming on DDL failure.
4. **Release of `kailash-dataflow` 2.3.4 (or 2.4.0 if behavioural)** + matching `kailash` patch; PyPI-published; clean-venv install verified.
5. **Cross-SDK inspection** — every fix evaluated against kailash-rs per `rules/cross-sdk-inspection.md` MUST Rule 1.

## Constraints

- **No workarounds for SDK bugs** (rules/zero-tolerance.md Rule 4) — these are SDK source bugs; fix at the SDK, not in downstream callers.
- **No silent fallbacks** (rules/zero-tolerance.md Rule 3) — the AsyncSQL fallback today is a silent fallback; the fix must surface the failure mode.
- **No half-implementations** (rules/zero-tolerance.md Rule 6) — `DataFlowEngine.register_model` is a half-implementation right now. Either complete it or remove it.
- **No mocking in Tier 2/3 tests** (rules/testing.md § 3-Tier Testing) — the regression tests MUST run against real PostgreSQL with a real failing DDL scenario.
- **Tenant isolation preserved** (rules/tenant-isolation.md) — `_kml_model_versions` schema fork in #699 is sibling work; this workspace's fixes touch DataFlow but must not regress multi-tenant DataFlow patterns.

## Out of scope (sibling workstreams)

- **kailash-ml 1.5.x followup** — #699, #700, #701 belong in `workspaces/kailash-ml-1.5.x-followup/`. They share the same MLFP M5 trigger but touch a different package.
- **Loom /sync** — the cycle-10 + cycle-11 codify proposals belong at `~/repos/loom/`; not BUILD-repo work.
- **Spec-drift-gate** — separate workstream, not blocked by this one.

## Success metric (the human's ratchet)

A clean reproduction script — `auto_migrate=True` model whose CREATE TABLE will fail, `AsyncSQLDatabaseNode` under load — runs for 30 minutes and the connection count stays bounded under the configured `max_size`, with a single ERROR + metric on the failed DDL, no retry storm, no pool leak.
