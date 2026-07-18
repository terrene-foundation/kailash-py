---
type: AMENDMENT
date: 2026-07-07
author: agent
project: kailash-py / kailash-dataflow
topic: dataflow 2.14.2 follow-up cycle — Wave 1 (correctness) convergence receipt; #1600 shipped, #1252 leak REFUTED, #1606 filed
phase: redteam
tags: [dataflow, auto-migrate, tenant-isolation, redteam, wave-loop, 2.14.2]
relates_to: 0022-AMENDMENT-soft-delete-2.14.0-redteam-convergence
---

# 0023 — AMENDMENT: dataflow 2.14.2 follow-ups, Wave 1 (correctness) converged

Continuation of journal 0022's out-of-scope follow-ups. Value-ranked the queued
DataFlow follow-ups; Wave 1 = the correctness cluster. Branch
`fix/dataflow-2.14.2-followups`. Posture L5_DELEGATED.

## Shipped (Wave 1)

- **#1600 — auto-migrate ALTER-ADD** (`08d3929b1` + hardening `ca14ad72b`). `ensure_table_exists`
  relied on `CREATE TABLE IF NOT EXISTS` (no-op on existing tables) so an evolved model never
  got its new column on a pre-existing table. Wired an additive column reconciler into the async
  ensure path AND the eager sync `_create_tables_batch`/`_create_table_sync` paths (sync marks
  ensured before async could run — fix must live on both). Reuses `_convert_fields_to_columns`,
  `SQLiteMigrationGenerator._map_type_to_sqlite`, `SyncDDLExecutor`; additive-only; NOT-NULL-no-default
  → NULLABLE; every identifier via `quote_identifier`; PG+SQLite. Flipped the #1600 strict-xfail +
  Tier-2 regression. G1 hardening: both reconcilers self-guard the post-inspection body (fail-open
  WARN+skip, symmetric across async/sync — was an asymmetry where sync marked a present table
  FAILED); sync ALTER-error detail → DEBUG (Rule 8); injection regression test on the DDL path.
- **#1252 — tenant-isolation regression** (`b00509c27`). The failing
  `test_bulk_upsert_round_trips_under_tenant_and_isolates` looked like a cross-tenant leak but was
  **REFUTED with decoded evidence**: `bulk_upsert` SQL is correct (`ON CONFLICT (id) DO UPDATE`,
  tenant stamped via canonical `get_current_tenant_id()`, fail-closed), verified isolated on BOTH
  SQLite and PostgreSQL. The failure was a TEST-HARNESS artifact — a process-shared Redis whose
  express cache key carries a tenant but NO database-instance dimension fed the test a phantom PK
  from a sibling test's DB, which the upsert then (correctly) targeted. Fix: `cache_enabled=False`
  in the `mt_db` fixture (write-path isolation is cache-independent; no assertion weakened).

## Filed (genuine gap, deferred)

- **#1606** — express+query cache keys omit a database-instance identity → cross-DB same-tenant
  cache bleed on a shared Redis (narrow production hazard + broad test-hermeticity hazard). A
  cross-SDK keyspace change (v2 pinned to Rust-SDK parity) → cross-SDK lockstep per
  cross-sdk-inspection Rule 4b, out of this cycle's shard budget + repo authority.

## G1 convergence receipt (wave-loop G1)

- **Round 1 — 2 parallel adversarial agents** (reviewer + security-reviewer) scoped to the diff:
  0 CRIT / 0 HIGH. reviewer MED-1 (async/sync fail-disposition asymmetry) + LOW-1 (DDL injection
  test) + LOW-2 (accepted-design). security 0 CRIT/HIGH; MED = the #1606 cache gap (filed); LOW =
  sync ALTER-error column-name-at-WARN. Independently confirmed bulk_upsert has NO leak.
- **Fixes applied + verified** (`ca14ad72b`): MED-1 + both LOWs resolved; 22 passed
  (#1600 regression ×2 + injection ×2 + soft_delete lifecycle ×18); #1252 file 10 passed.
- **Non-regression PROVEN via set-diff** on `core_engine/` integration: baseline (no reconciler)
  = 37 failed / 196 passed / 9 errors; with reconciler = 35 failed / 198 passed / 9 errors. The
  set-diff shows ZERO new failing test IDs and the reconciler FIXES real tests
  (`test_crud_operations_real_database`, `test_query_performance`, the `column "active"/"in_stock"
does not exist` errors — exactly #1600). The ~35 residual core_engine failures are PRE-EXISTING
  debt on main (likely PG-test-manager infra-dependent locally); CI with full infra is the
  authoritative arbiter on the PR.

## Next

Wave 2 (hygiene+security+completeness): #1603 (bulk_update identifier quoting), #1604
(express.find_one include_deleted), #1605 + #1599 (purge fictional versioned/optimistic-locking/
RetryNode; keep-removed + reject unknown `__dataflow__` keys). Then G2 redteam → holistic redteam →
version bump 2.14.1→2.14.2 → PR/CI → user-gated /release to PyPI.
