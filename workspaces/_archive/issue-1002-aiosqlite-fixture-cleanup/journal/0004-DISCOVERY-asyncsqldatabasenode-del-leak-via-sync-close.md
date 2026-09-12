# 0004 DISCOVERY — DataFlow.close() (sync) does not close cached AsyncSQLDatabaseNode instances

Date: 2026-05-14
Phase: /implement Shard 1
Surfaced by: dataflow-specialist agent during Shard 1 final pytest validation

## Finding

After Shard 1's migration converted all 67 inline `DataFlow(...)` constructions to fixture-managed / context-manager-wrapped sites, the targeted pytest run reports:

- 105 passed, exit 0 ✓
- ZERO `ResourceWarning` from `DataFlow.__del__` (the warning gate per `pytest -W "error::ResourceWarning"` passes)
- 6 surviving `PytestUnraisableExceptionWarning` from `AsyncSQLDatabaseNode.__del__` triggered specifically by `test_refresh_returns_correct_result` calling `refresh_derived_sync`

The leak class is distinct: the synchronous `DataFlow.close()` at `packages/kailash-dataflow/src/dataflow/core/engine.py:9948` does NOT close cached `AsyncSQLDatabaseNode` instances; only `DataFlow.close_async()` at line 10051 closes them (per the agent's reading of the engine file, lines 10117-10127 vs the sync close).

Symptom: when `refresh_derived_sync` constructs an `AsyncSQLDatabaseNode` for the sync code path AND the test wraps DataFlow in `with DataFlow(...) as db:` (sync `__exit__` → sync `close()`), the cached node leaks. The `__del__` finalizer on the leaked node fires later and emits `PytestUnraisableExceptionWarning`.

## Why this is in scope for Shard 1's spirit but out of scope for Shard 1's surface

Shard 1's surface is `tests/unit/<5 files>` — fixing test-body inline construction patterns. The fix here is in `packages/kailash-dataflow/src/dataflow/core/engine.py::close()` (production SDK code), NOT in the test files. Per `rules/autonomous-execution.md` MUST-1 (call-graph hops ≤3-4), pulling production engine changes into Shard 1 would push the call graph past the budget — the engine fix needs its own shard with full engine-context loaded.

## Disposition

**Add to Shard 2 todo (`02-shard2-mid-concentration-and-async-adapter-cleanup.md`)** as an additional invariant:

> "Sync `DataFlow.close()` MUST close the cached `AsyncSQLDatabaseNode` instances (not only `close_async()`). Pin via test in `packages/kailash-dataflow/tests/unit/core/` exercising the sync close path and asserting zero `PytestUnraisableExceptionWarning` from `AsyncSQLDatabaseNode.__del__`."

Rationale: Shard 2 already touches engine-adjacent test surface (cache + adapters); the engine fix lives within Shard 2's call-graph distance. Adding it expands Shard 2's invariants from 9 to 10 — within the ≤5-10 budget per `autonomous-execution.md` MUST-1.

If the engine fix exceeds Shard 2's LOC budget on inspection, split it into a dedicated Shard 2.5 (engine-only) and re-evaluate at /todos for Shard 3.

## Cross-SDK note (per `rules/cross-sdk-inspection.md` MUST-1)

The Rust SDK's sync close path also delegates to async resource cleanup via tokio. Whether the Rust equivalent has the same drop-non-daemon-handle issue is a kailash-rs-session question, not autonomous-action here. Informational only.

## Evidence cited

- `packages/kailash-dataflow/src/dataflow/core/engine.py:9948` — sync `def close(self):`
- `packages/kailash-dataflow/src/dataflow/core/engine.py:10051` — `async def close_async(self):`
- `packages/kailash-dataflow/src/dataflow/core/engine.py:10117-10127` — async cleanup that closes cached AsyncSQLDatabaseNode (per agent's reading)
- 6 PytestUnraisableExceptionWarning emissions in Shard 1 final pytest run, all from `test_refresh_returns_correct_result` via `refresh_derived_sync`
