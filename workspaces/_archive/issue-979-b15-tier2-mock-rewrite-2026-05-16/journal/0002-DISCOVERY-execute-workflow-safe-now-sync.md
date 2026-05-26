# DISCOVERY — `_execute_workflow_safe` is sync in v0.10.11+ (event-loop bug class closed)

**Date**: 2026-05-15
**Phase**: /analyze Round-1 red team
**Source**: dataflow-specialist agent DF-3 HIGH (`04-validate/02-redteam-dataflow.md`)

## What we found

`packages/kailash-dataflow/src/dataflow/migrations/auto_migration_system.py:40-114`
declares the current `_execute_workflow_safe` implementation. Module docstring
explicitly says "ARCHITECTURE FIX (v0.10.11): This function now uses synchronous
database connections (psycopg2/sqlite3) instead of async connections via
AsyncLocalRuntime."

The previous async approach (which File 4's `test_original_bug_scenario` +
`test_simulated_fastapi_lifespan` regression tests target) is gone. The bug
class — connections bound to a thread-pool event loop being unusable in
uvicorn's loop — was closed by switching DDL to sync `SyncDDLExecutor`.

The two helpers `async_safe_run` and `get_execution_context` still exist in
`dataflow/core/async_utils.py:80,121` (verified). They are no longer used by
the migration system but remain in the public API.

## Why this matters

v1 Shard 3 proposed porting `test_original_bug_scenario` +
`test_simulated_fastapi_lifespan` to real-PG Tier-2 tests. But:

1. `test_simulated_fastapi_lifespan` is a `try: ...; except Exception: ...`
   smoke test — `rules/zero-tolerance.md` Rule 3 violation. DELETE outright,
   not port.
2. `test_original_bug_scenario` tests behavior that was closed by refactor.
   Per `rules/testing.md` § Regression, regression tests are PERMANENT — but
   the test's dead `except` arm (`"thread" in error_str`) must be simplified
   (the sync helper doesn't thread, so the except never fires).

## Disposition

v2 § Shard 1 Step 5 moves `test_original_bug_scenario` to
`tests/regression/test_issue_dataflow_async_safe_run_no_event_loop_bridge.py`
with simplified assertion (per `02-amendments-post-round2.md` A9), and
DELETES `test_simulated_fastapi_lifespan`. v1's separate "PG regression
carve-out shard" is dropped — the regression carve-out happens INSIDE
Shard 1.

## Cross-rule relevance

`rules/testing.md` § Regression: "regression tests are PERMANENT — never
deleted." This preserves the historical regression even when the bug class
is closed by refactor. The test asserts current behavior using a known-
historically-failing input.

`rules/spec-accuracy.md` Rule 1: every citation must grep-resolve. v1's plan
cited "PG is where the bug manifests" — false per current source. v2 corrects.
