# DISCOVERY — Real-PG `MigrationLockManager` coverage already lives at singular-dir path

**Date**: 2026-05-15
**Phase**: /analyze Round-1 red team
**Source**: dataflow-specialist agent DF-1 CRIT (`04-validate/02-redteam-dataflow.md`)

## What we found

Two files with the **same filename** exist in the integration tier:

- `packages/kailash-dataflow/tests/integration/migration/test_migration_lock_manager_integration.py` (singular `migration/`) — **real PG, zero mocks**, uses `IntegrationTestSuite` + real `asyncpg`. Covers `MigrationLockManager.acquire_migration_lock` / `release_migration_lock` / `check_lock_status` / `migration_lock` ctx-mgr end-to-end.
- `packages/kailash-dataflow/tests/integration/migrations/test_migration_lock_manager_integration.py` (plural `migrations/`) — File 6 of the 9 in scope. **37 mock sites**. Tests the same SUT via mocks.

The classification audit looked at File 6 in the plural dir and proposed a "create new tier-2 wiring file" shard (v1 Cluster B). It missed the existing real-PG suite in the singular dir.

## Why this matters

v1 Shard 2 would have shipped duplicate tier-2 coverage. Architecture plan v2 collapses Shard 2 from "split + new tier-2 file" to "split + delete plural file entirely; tier-2 already covered by singular file."

The directory naming collision (`migration/` vs `migrations/`) is the institutional tripwire. Both dirs exist; both have differently-classified files; the plural dir's contents are S4-move legacy.

## Verification

```bash
ls packages/kailash-dataflow/tests/integration/migration/test_migration_lock_manager_integration.py
ls packages/kailash-dataflow/tests/integration/migrations/test_migration_lock_manager_integration.py
# → both exist

grep -cE "@patch|MagicMock|AsyncMock|unittest\.mock|Mock\(\)" \
  packages/kailash-dataflow/tests/integration/migration/test_migration_lock_manager_integration.py
# → 0 mocks

grep -cE "@patch|MagicMock|AsyncMock|unittest\.mock|Mock\(\)" \
  packages/kailash-dataflow/tests/integration/migrations/test_migration_lock_manager_integration.py
# → 37 mocks
```

## Disposition

Captured in `02-plans/01-architecture-plan-v2.md` § Shard 2 + `02-plans/02-amendments-post-round2.md` A10 (Tier-1 extract is NOT duplicate of singular-file Tier-2 coverage — they test same SUT at different tiers per `rules/testing.md` § One Direct Test Per Variant).

## Cross-rule relevance

This is the same failure mode `rules/specs-authority.md` MUST-5b prevents
for specs (sibling re-derivation when one is edited): two files with the
same name in adjacent directories MUST be cross-checked before classifying.
Loops back into `rules/spec-accuracy.md` Rule 1 (every citation grep-
resolves at merge time).
