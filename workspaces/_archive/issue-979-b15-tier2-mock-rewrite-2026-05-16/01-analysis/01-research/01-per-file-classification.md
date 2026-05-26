# Per-File Classification — 9 Files in #992 B-1.5

Source: analyst audit 2026-05-15. Spec authority: `specs/testing-tiers.md` §
Tier-2 Contract Rule 1 (NO MOCKING, verbatim).

## Summary table

| #   | File                                                        | SUT                                                                                                                                                                                                          |                                                                Mock count | Classification                                                                                                                                   |                 Rewrite LOC |
| --- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------: | ------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------: |
| 1   | `cache/test_cache_invalidation.py`                          | `CacheInvalidator` (pure dispatch over `CacheManager` protocol)                                                                                                                                              |                                                              ~30 `Mock()` | **(b) Tier-1 move**                                                                                                                              |                         -45 |
| 2   | `core/test_dataflow_engine_lock_integration.py`             | `DataFlow.__init__` param plumbing                                                                                                                                                                           |                                                                1 `@patch` | **(b) Tier-1 move**                                                                                                                              |                          -8 |
| 3   | `migration/test_impact_reporter_unit.py`                    | `ImpactReporter` / `DependencyAnalyzer` / `ColumnRemovalManager` against simulated asyncpg row shapes                                                                                                        |                                         `AsyncMock`/`MagicMock` × 5 tests | **(b) Tier-1 move** (filename already `_unit.py`)                                                                                                |                         -10 |
| 4   | `migrations/test_async_safe_run_integration.py`             | `_execute_workflow_safe` helper + sqlite-in-memory init flow; regression scenarios document PG requirement                                                                                                   |                                                  minimal (imports unused) | **(c) Split** — Tier-1 helper-existence + Tier-2 PG regression carve-out                                                                         |                    +80 / -3 |
| 5   | `migrations/test_auto_migration_system_lock_integration.py` | `AutoMigrationSystem` lock-manager wiring (param-plumbing + dispatch)                                                                                                                                        |                                `Mock` dataflow + `AsyncMock` lock methods | **(b) Tier-1 move** (real Tier-2 coverage delivered by Shard 2's File 6 split)                                                                   |                          -5 |
| 6   | `migrations/test_migration_lock_manager_integration.py`     | TWO SUTs: (a) `ConnectionManagerAdapter._convert_parameters` pure string algo; (b) `MigrationLockManager.acquire_migration_lock` / `release_migration_lock` / `check_lock_status` / `migration_lock` ctx mgr |                          `Mock` dataflow + `AsyncMock` on `execute_query` | **(c) Split** — Tier-1 param-conversion + Tier-2 lock-manager wiring (real PG, real concurrent acquire)                                          | +120 / preserve param tests |
| 7   | `migrations/test_migration_test_framework.py`               | `MigrationTestFramework` (a test-harness scaffolding class itself)                                                                                                                                           | `patch("sqlite3.connect")`, `patch("asyncpg.connect")`, `Mock` everywhere | **(b) Tier-1 move** (it tests a test framework — no infra value)                                                                                 |                          -3 |
| 8   | `package/test_package_installation_unit.py`                 | `DataFlow(...)` + `@db.model` + `WorkflowBuilder.add_node` API shape                                                                                                                                         |                  `@patch("AsyncSQLDatabaseNode.async_run")` × 11/13 tests | **(b) Tier-1 move** (filename already `_unit.py`, pytestmark already `unit`)                                                                     |                          -3 |
| 9   | `test_real_tdd_integration.py`                              | `DataFlow.__init__` w/ `tdd_mode` propagation                                                                                                                                                                |                        7 `patch()` per test on every internal init helper | **(b) Tier-1 move + rename** to `test_tdd_mode_init_wiring.py` (current filename is actively misleading — entire file mocks every DB init phase) |                          -5 |

## Cluster proposal (for sharding)

### Cluster A — Pure Tier-1 moves (7 files, mechanical)

Mechanical S4 reversal: change directory, drop `@pytest.mark.integration`
decorators, drop dead `test_suite`/`runtime` fixtures, drop unused
`IntegrationTestSuite` imports. Zero behavioral change.

- File 1 → `tests/unit/cache/test_cache_invalidation.py`
- File 2 → `tests/unit/core/test_dataflow_engine_lock_integration.py`
- File 3 → `tests/unit/migrations/test_impact_reporter_unit.py`
- File 5 → `tests/unit/migrations/test_auto_migration_system_lock_integration.py`
- File 7 → `tests/unit/migrations/test_migration_test_framework.py`
- File 8 → `tests/unit/package/test_package_installation_unit.py`
- File 9 → `tests/unit/core/test_tdd_mode_init_wiring.py` (renamed from `test_real_tdd_integration.py`)

Capacity: ~6 invariants (test count preserved per file × 7 + decorator
hygiene + collection-time NO-MOCKING scan passes). Single shard.

### Cluster B — File 6 split (Tier-1 + Tier-2)

- `tests/unit/migrations/test_connection_adapter_param_conversion.py` —
  `TestConnectionManagerAdapter` parameter-conversion class (lines 24-227)
  - `TestParameterConversionEdgeCases` (392-466). Pure string-algorithm tests.
    No infra.
- `tests/integration/migrations/test_migration_lock_manager_wiring.py` —
  `TestMigrationLockManagerIntegration` (lines 230-389) rewritten against
  real PG via `IntegrationTestSuite`. Real concurrent acquire→fail→release→
  acquire flow. Closes the `facade-manager-detection.md` Rule 1 gap for
  `MigrationLockManager`.

Capacity: 5 invariants (param-conversion regression preserved, concurrent
acquire blocks, release unblocks, status check returns row, NO-MOCKING
scan passes). Single shard.

### Cluster C — File 4 split (Tier-1 + Tier-2)

- `tests/unit/migrations/test_async_safe_run.py` — helper-existence tests
  - sync-context execution (~70% of current file). SQLite is the helper's
    intentional Tier-1 test surface.
- `tests/integration/migrations/test_async_safe_run_postgres.py` —
  `test_original_bug_scenario` (lines 612-660) + `test_simulated_fastapi_lifespan`
  (lines 662-684) rewritten against real PG. Closes the in-file documented
  gap (lines 30, 154, 218, 449, 622-624) that says "PG is the actual
  production use case and has no helper-tier coverage."

Capacity: 4 invariants (PG regression covers both scenarios, helper-existence
preserved Tier-1, SQLite-intentional-fail tests preserved, NO-MOCKING scan
passes). Single shard.

## Open questions resolved by Cluster B + C

The analyst raised these as open; resolved as follows:

| Q                                                                                    | Status                                          | Resolution                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------------ | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Authoring missing Tier-2 `MigrationLockManager` wiring test in scope?                | **Yes — Cluster B**                             | File 6's existing `TestMigrationLockManagerIntegration` block IS the wiring test; we just rewrite it from mocked to real. NEW file in `tests/integration/migrations/test_migration_lock_manager_wiring.py` is the Tier-2 carve-out. This fulfills both #992 AC (a) AND `facade-manager-detection.md` Rule 1. |
| File 4 Tier-2 carve-out in scope?                                                    | **Yes — Cluster C**                             | The PG regression is documented in-file but never tested anywhere. Cluster C's new `test_async_safe_run_postgres.py` closes the gap that File 4 itself flagged.                                                                                                                                              |
| File 5 facade-manager Tier-2 gap?                                                    | **Closed by Cluster B**                         | File 5 tests `AutoMigrationSystem`'s LOCK-WIRING (param plumbing) — the real lock behavior lives in `MigrationLockManager`, which gets real-PG coverage in Cluster B's new wiring test. File 5 → pure Tier-1 move.                                                                                           |
| File 1 conflicting markers (`pytestmark = unit` + class `@pytest.mark.integration`)? | **Cleanup in Cluster A**                        | Drop the `@pytest.mark.integration` class decorators; `pytestmark = unit` is canonical.                                                                                                                                                                                                                      |
| Cross-SDK (kailash-rs) sibling sweep?                                                | **Out of scope** per `repo-scope-discipline.md` | This workstream stays in kailash-py. kailash-rs sibling work, if needed, lives in a separate kailash-rs session.                                                                                                                                                                                             |
| Rename File 9?                                                                       | **Yes — in Cluster A**                          | New name: `test_tdd_mode_init_wiring.py`.                                                                                                                                                                                                                                                                    |
| Drop dead fixtures (Files 1, 3)?                                                     | **Yes — in Cluster A**                          | Delete unused `test_suite` / `runtime` fixtures + unused `IntegrationTestSuite` imports during move.                                                                                                                                                                                                         |

## Dependency graph

```
Shard 1 (Cluster A) ──┐
Shard 2 (Cluster B) ──┼──→ Shard 4: post-merge verification (grep zero mocks)
Shard 3 (Cluster C) ──┘
```

All three implementation shards are independent (touch disjoint files; no
shared invariants). Eligible for parallel worktree wave per
`rules/worktree-isolation.md` Rule 4 (waves of ≤3 — exactly 3).

## Critical insights from harness audit (`02-harness-contract.md`)

These constraints bind Cluster B + C work:

1. **`IntegrationTestSuite.session()` is the only lifecycle entry point**
   (`tests/infrastructure/test_harness.py:434`). No `clean_database()` method
   exists despite older docs hinting at one.

2. **NO MOCKING enforced at collection time via AST scan**
   (`tests/integration/conftest.py:120-145`). Any leftover `from unittest.mock
import patch | Mock | MagicMock | AsyncMock` in a tier-2 file fails
   collection — the cleanup must be total.

3. **Shared `test_suite` fixture is global** at `tests/integration/conftest.py:304-318`.
   New Cluster B + C tier-2 tests do NOT need to redefine it locally.

4. **`pool_size=2, max_overflow=2`** is canonical mitigation against PG
   `max_connections` saturation when a test constructs multiple `DataFlow`
   instances.

5. **`pytest.ini::addopts` filters `requires_postgres` by default** — tier-2
   tests use `@pytest.mark.integration` to run in the default tier-1 sweep
   exclusion AND opt-in to tier-2 jobs.
