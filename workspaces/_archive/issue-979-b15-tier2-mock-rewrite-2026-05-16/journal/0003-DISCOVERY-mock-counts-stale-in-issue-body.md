# DISCOVERY — Issue #992 body mock counts understated by ~73%

**Date**: 2026-05-15
**Phase**: /analyze Round-1 red team

## What we found

Issue #992 body table cites per-file mock counts totalling **74**. Verified
counts via `grep -cE "@patch|MagicMock|AsyncMock|unittest\.mock|Mock\(\)"`
total **128** across the same 9 files. The body undercounts by 54 sites.

Per-file delta:

| File                                                      | Body claim | Verified |   Delta |
| --------------------------------------------------------- | ---------: | -------: | ------: |
| cache/test_cache_invalidation.py                          |          1 |       28 |     +27 |
| core/test_dataflow_engine_lock_integration.py             |          2 |        2 |       0 |
| migration/test_impact_reporter_unit.py                    |          4 |        4 |       0 |
| migrations/test_async_safe_run_integration.py             |          1 |        1 |       0 |
| migrations/test_auto_migration_system_lock_integration.py |         15 |       29 |     +14 |
| migrations/test_migration_lock_manager_integration.py     |         14 |       37 |     +23 |
| migrations/test_migration_test_framework.py               |         12 |       13 |      +1 |
| package/test_package_installation_unit.py                 |         13 |       13 |       0 |
| test_real_tdd_integration.py                              |          1 |        1 |       0 |
| **Total**                                                 |     **74** |  **128** | **+54** |

## Why this matters

The body's per-file estimate (~100 LOC × 9 files = 900 LOC) is approximately
correct in spirit but the mock-density distribution is uneven. Three files
(cache, auto_migration_system, lock_manager) carry 73% of all mocks.

For the architecture plan, this confirms:

- File 1 (cache) is mock-heavy → still classifies cleanly as Tier-1 move
  (the SUT is `CacheInvalidator`, a pure protocol-dispatch class — verified
  in the classification audit).
- File 6 (lock_manager) is mock-heavy → its tier-2 wiring SUT was the
  flagged orphan, BUT the singular-dir file already covers it (see
  `0001-DISCOVERY-duplicate-coverage-at-singular-dir.md`).

Per `rules/testing.md` § MUST: Verified Numerical Claims, the plan v2 uses
the verified counts, not the body's claim.

## Disposition

v2 § "Verified per-file state" table cites the grep'd counts. Issue body
remains unchanged (out-of-session edit per `rules/upstream-issue-hygiene.md`
MUST-1).
