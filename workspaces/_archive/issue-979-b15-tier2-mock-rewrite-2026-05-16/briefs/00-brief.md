# Brief: tier-2 mock rewrite for 9 files moved by S4 (Workstream-B B-1.5 of #979)

Source: `gh issue view 992 --json title,body` (filed 2026-05-14).
Parent: workspace `issue-979-dataflow-unit-triage`, INDEX line 43.
Spec authority: `specs/testing-tiers.md` § Tier-2 Contract Rule 1 (NO MOCKING).

## Affected surface

`packages/kailash-dataflow/tests/integration/` — 9 files moved by PR #988
(kailash-dataflow 2.9.4) that contain `@patch`/`MagicMock`/`AsyncMock`/
`unittest.mock`:

| File (relative to `packages/kailash-dataflow/tests/integration/`) | Mock sites |
| ----------------------------------------------------------------- | ---------- |
| `cache/test_cache_invalidation.py`                                | 1          |
| `core/test_dataflow_engine_lock_integration.py`                   | 2          |
| `migration/test_impact_reporter_unit.py`                          | 4          |
| `migrations/test_async_safe_run_integration.py`                   | 1          |
| `migrations/test_auto_migration_system_lock_integration.py`       | 15         |
| `migrations/test_migration_lock_manager_integration.py`           | 14         |
| `migrations/test_migration_test_framework.py`                     | 12         |
| `package/test_package_installation_unit.py`                       | 13         |
| `performance/test_postgresql_test_manager_concurrent.py`          | 11         |
| `test_real_tdd_integration.py`                                    | 1          |

Total: ~74 mock sites across 9 files. Pre-existing on `main` `d655038e`
(S4 only changed paths via `git mv`; mock counts unchanged).

## Value-anchor (`specs/testing-tiers.md` § Tier-2 Contract Rule 1, verbatim)

> "Per `rules/testing.md` § 'No Mocking in Tier 2/3', integration tests
> MUST exercise real infrastructure:
>
> - Real PostgreSQL via `IntegrationTestSuite`
> - Real Redis / Mongo / MySQL when subject under test requires them
> - Real `AsyncLocalRuntime` / `LocalRuntime`
> - Real network calls (mockable at the response layer only via VCR-style cassettes)"

## Expected vs actual

Expected: integration tier exercises real PG via `IntegrationTestSuite`;
mocks live only in tier-1.

Actual: 9 tests in the integration tier use `@patch`/`MagicMock` for
behavior that the file names (e.g. `test_postgresql_test_manager_concurrent`,
`test_impact_reporter_unit`) suggest should be exercised against real PG.

## Severity

LOW — no tier-2 enforcement gate exists today; tests pass under current
CI. Failure mode would surface only if a future gate enforces "Tier-2
NO MOCKING" mechanically.

## Acceptance criteria

- [ ] For each of the 9 files, classify: (a) test needs real PG → rewrite
      to `IntegrationTestSuite`, OR (b) test does not need real PG →
      downgrade to tier-1 with `importorskip` or move to a clearer tier
- [ ] Per-file decisions documented in a journal `DECISION-` entry under
      `workspaces/issue-979-dataflow-unit-triage/journal/` (or new workspace)
- [ ] Post-rewrite: `grep -rcE '@patch|MagicMock|AsyncMock|unittest\.mock'
    packages/kailash-dataflow/tests/integration/{cache,core,migration,migrations,package,performance}/`
      reports zero in the rewritten files
- [ ] Decomposition: ~3 sessions of work (~100 LOC × 9 files ≈ 900 LOC)
      — shard by file or directory group

## Relation to #979

Workstream-B follow-up per
`workspaces/issue-979-dataflow-unit-triage/todos/active/00-INDEX.md`.
**NOT a blocker for #979 S6** (gate re-land + DEFENSE-2/3). Brief AC#4

- AC#5 already closed by PR #988 (kailash-dataflow 2.9.4 on PyPI).
