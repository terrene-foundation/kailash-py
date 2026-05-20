# DataFlow Red Team Round 2 — v2 Plan

## Verdict

APPROVE-WITH-FIXES. v2 CLOSES DF-1/2/3/4. Two new HIGH on extract overlap + sync-context staleness; three LOW on marker/regression hygiene.

## Round 1 closure

- **DF-1 (CRIT)**: CLOSED. Shard 2 drops the new Tier-2 file, deletes plural `test_migration_lock_manager_integration.py`, cites singular `migration/` path (v2 §Shard 2.2).
- **DF-2 (HIGH)**: CLOSED. v2 §Out-of-scope cites `dataflow_migration_locks` + row-level INSERT ON CONFLICT verbatim. Confirmed singular file references `dataflow_migration_locks` at lines 66, 110, 150, 178, 195, 204, 237, 280, 292, 302, 317, 325.
- **DF-3 (HIGH)**: CLOSED. v2 deletes `test_simulated_fastapi_lifespan` (Shard 1 step 5c).
- **DF-4 (HIGH)**: CLOSED. v2 changelog drops `pool_size=2`. Confirmed singular file uses no `pool_size`/`max_overflow`.

## New findings

### [DF-R2-1 type:HIGH] Tier-1 extract duplicates existing Tier-1 coverage

The plural File 6 lines 24-227 (`TestConnectionManagerAdapter`) + 392-466 (`TestParameterConversionEdgeCases`) ARE Tier-1 already. But the singular real-PG file at `tests/integration/migration/test_migration_lock_manager_integration.py:419-528` contains `TestConnectionAdapterIntegration` — real-PG parameter-conversion coverage via `test_parameter_conversion_with_real_queries` (lines 423-448). The plural-file extract is `%s→$1` string-algorithm tests (no DB); the singular has the same conversion verified end-to-end. The Tier-1 extract is NOT duplicate — it tests the pure transform without DB roundtrip. Keep, but Shard 2 invariants MUST add: "Tier-1 extract covers string algorithm only; real-PG conversion stays at singular `migration/` file."

### [DF-R2-2 type:HIGH] Sync-context tests target the now-obsolete SUT branch

File 4 lines 100-145 (`TestSyncContextExecution`) call `_execute_workflow_safe(workflow)` synchronously. Per `auto_migration_system.py:40-114`, the helper is now sync over `SyncDDLExecutor` — these tests still exercise current behavior. Lines 50-72 (`test_helper_function_exists*`) are structural existence-only — they pass against the v0.10.11 sync helper. Lines 321-365 (TestAsyncSafeRunIntegration class lives at 318) are NOT what v2 plans to move; v2 cites 321-365 inside `TestAsyncSafeRunIntegration` which exercises the LEGACY `async_safe_run(coro)` helper from `dataflow.core.async_utils:121` (still exists per v2's own verification). The helper exists; tests are valid Tier-1.

**Disposition**: v2's line ranges are imprecise. Shard 1 step 5 MUST verify each block against current `dataflow/core/async_utils.py` + `dataflow/migrations/auto_migration_system.py` AT MOVE TIME. Tests whose SUT is the legacy `async_safe_run` belong in tests/unit/migrations/test_async_safe_run.py; tests whose SUT is `_execute_workflow_safe` (sync) belong there too. Per `rules/spec-accuracy.md` Rule 1, every cited line range MUST grep-resolve at merge.

### [DF-R2-3 type:HIGH] `test_original_bug_scenario` is behavioral but asserts SQLite-thread-error semantics

Lines 612-660: calls `_execute_workflow_safe(workflow)`, asserts `"bug_repro" in results` OR (`"future attached to a different loop" not in error_str` AND `"thread" in error_str`). Per `rules/testing.md` § Behavioral Regression: this IS behavioral (calls the function, asserts on return/raise). But the assertion pins SQLite's threading error message — `"thread" in error_str`. The sync helper no longer threads; SQLite-in-memory now SUCCEEDS through `SyncDDLExecutor`. The `try/except` will take the success branch; the `except` arm is dead. Per `rules/zero-tolerance.md` Rule 2 (dead branch = fake test), Shard 1 step 5b MUST simplify to: assert `"bug_repro" in results` only, delete the `except` arm.

### [DF-R2-4 type:LOW] `regression` marker IS registered

`packages/kailash-dataflow/pytest.ini:33` registers `regression`. Shard 1's `@pytest.mark.regression` will collect cleanly. No action needed; remove this as a Shard 1 concern in plan prose.

### [DF-R2-5 type:LOW] `requires_postgres` marker drift

`pytest.ini:21` registers `requires_postgres`. Sampled Files 1/4/5: zero `@pytest.mark.requires_postgres`. Files 4-5 use `@pytest.mark.asyncio` only. Marker filter exclusion is non-issue for these 9 files. Confirm at Shard 3 grep step.

### [DF-R2-6 type:LOW] Net zero src/ change confirmed

v2 §Out of scope explicitly states zero production-code changes. Verified: deletes/moves touch `tests/` only. Import paths `dataflow.core.async_utils`, `dataflow.migrations.auto_migration_system`, `dataflow.utils.connection_adapter` all stable at current SHAs.

## Required fixes for APPROVE

1. DF-R2-1: Shard 2 invariant adds Tier-1-vs-real-PG distinction note.
2. DF-R2-2: Shard 1 step 5 re-verifies line ranges against current source at move time.
3. DF-R2-3: Shard 1 step 5b simplifies `test_original_bug_scenario` assertion + deletes dead `except` arm.

With those three fixes the plan is one-shard implementable per `rules/autonomous-execution.md` capacity budget.
