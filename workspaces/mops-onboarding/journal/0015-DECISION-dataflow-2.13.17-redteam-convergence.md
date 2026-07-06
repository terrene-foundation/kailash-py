---
type: DECISION
date: 2026-07-05
author: agent
project: dataflow-2.13.17-async-column-detection-and-upsert-family-removal
topic: DataFlow 2.13.17 red-team convergence receipt — #1564 (async column detection + dead upsert-family removal)
phase: redteam
relates_to: 0014-DECISION-dataflow-2.13.16-redteam-convergence
verified_id: esperie
person_id: esperie
display_id: esperie
tags: [dataflow, redteam, "1564", async-column-detection, updated_at, dead-code]
---

# DECISION — DataFlow 2.13.17 red-team converged (2 rounds)

Coordination receipt for GitHub issue #1564 (the deferred tail of the 2.13.16 red-team).
Working tree on `main`, NOT committed — branch/PR/CI/merge/`/release` gated on user
confirmation (BUILD repo). Base `main` `082215197`.

## What #1564 turned out to be

The issue framed two "small" cleanups. Investigation (ground-truth verified) reclassified
Part 2 from a design-cleanup into a **real latent bug**:

- **Part 1 (dead code — as framed):** the zero-caller `get_upsert_sql`
  (`database/multi_database.py::DatabaseAdapter`) and `upsert_clause`
  (`adapters/dialect.py::SQLDialect`) abstractmethod families — each a base
  `@abstractmethod` + PG/MySQL/SQLite overrides, **8 methods** — undocumented,
  unexported, zero-caller.
- **Part 2 (latent bug — NOT "delete the orphan"):** every DataFlow workflow-node
  CRUD SQL generator runs inside `async def async_run` (`core/nodes.py`; the sync
  `run()` is a thin `async_safe_run(self.async_run(...))`). The 5 column-detection
  sites called the **sync** `_get_table_columns`, which raises "cannot be called
  from a running async context" inside any event loop and returns `[]`. So
  `has_updated_at` was ALWAYS False → the UPDATE/UPSERT SET clause never bumped
  `updated_at` on PostgreSQL/SQLite (MySQL masked it via `ON UPDATE CURRENT_TIMESTAMP`),
  and node SELECT column lists dropped `created_at`/`updated_at`. Proven RED on main:
  `updated_at == created_at` after a delayed node UPDATE.

## Design decision (dataflow-specialist consult → hybrid, perf-safe)

Deleting the orphan would cement the bug; naively wiring `_get_table_columns_async`
(→ whole-catalog `discover_schema_async`) would add a per-op introspection round-trip.
The specialist-recommended **hybrid** (Approach C) resolves both:

- **Managed path** (`auto_migrate and not existing_schema_mode`): derive columns from
  in-memory model metadata at **ZERO DB cost** — `_generate_create_table_sql`
  unconditionally appends both timestamps (invariant proven set+order-equal vs
  `PRAGMA table_info` across edge cases: custom fields, explicit timestamps, field
  named `id`, custom `__tablename__`).
- **Existing-schema / non-auto-migrate path**: cached async catalog introspection
  (`_get_table_columns_async`, memoized per `sha256(db_url)[:16]:table` in a new
  `_column_cache`, invalidated by `clear_schema_cache`/`clear_table_cache`).

New engine methods: `_resolve_table_columns_async`, `_resolve_columns_via_introspection`,
`_generate_select_sql_async`, `_build_select_sql_templates` (shared pure builder). The
now-orphaned sync `_generate_select_sql` + `_get_table_columns` were **deleted** (round-1
finding). 5 node sites converted to `await` the resolver/async-twin.

**No-shim decision (deviation from #1564's stated Rule-6a approach):** Part 1 removed
with NO deprecation shim. Evidence: the 8 methods are undocumented, not exported from any
package `__init__`, zero-caller SDK-wide; removing a base `@abstractmethod` + all overrides
is a relaxing change (external subclasses stay valid, classes stay instantiable). Rule 6a
protects _documented public API_; these are internal dead code. Aligns with the standing
no-shims preference. Flagged in the CHANGELOG.

## Files (working tree)

`packages/kailash-dataflow/`: `src/dataflow/core/engine.py`, `src/dataflow/core/nodes.py`,
`src/dataflow/adapters/dialect.py`, `src/dataflow/database/multi_database.py`,
`CHANGELOG.md`, `pyproject.toml`, `src/dataflow/__init__.py` (version 2.13.16→2.13.17,
both anchors verified) + new `tests/regression/test_issue_1564_async_column_detection.py`
(6 tests: AC1 update-bump SQLite, AC2 upsert-bump + CREATE-branch, AC3 SELECT-timestamps,
AC4 managed zero-DB-IO boundary-injection, AC5 existing-schema custom-`__tablename__`
introspection + cache-evict, AC6 real PostgreSQL).

## Red-team rounds (durable verdicts)

- **Round 1** (reviewer `af3defa4197bd1d14` + security-reviewer `a1b032470ec39ceb6` +
  dataflow-specialist `a7ea01552e3d2dfda`, parallel): no BLOCKER/HIGH. Managed-derivation
  invariant proven HOLDS. Findings → all fixed:
  - MED (orphan): sync `_generate_select_sql` + `_get_table_columns` newly zero-caller →
    deleted (verified `discover_schema` sync retains other callers; no cascade).
  - MED (sec): `_column_cache` key held raw DB URL → SHA-256-hashed (sibling pattern).
  - MED (test): AC5 `__dataflow__` table_name was a no-op → rewrote with `__tablename__`
    ≠ default plural (now exercises custom-name introspection; passes → resolution honors
    `__tablename__` via `model_info["table_name"]`, engine.py:2040).
  - LOW: sanitize introspection-fallback log; assert upsert CREATE-branch; None-guard the
    `_unique_index_cache.clear()` sibling.
- **Round 2** (reviewer `ae5fc40eeab9bccb6` + security-reviewer `a0775ae013396e9f3` +
  dataflow-specialist `aa70b447c904c3a88`, parallel): code-review CLEAN, domain CLEAN
  (invariant + custom-`__tablename__` correctness re-confirmed end-to-end), security MED-1
  hash PASSED + one new LOW (the round-1 sanitize landed on a handler shadowed by
  `_get_table_columns_async`'s own catch; `sanitize_db_error` doesn't redact DSNs anyway).
  LOW → fixed: all 4 introspection-fallback DEBUG logs now emit `type(e).__name__` (no
  DSN/value can leak), grep-verified + 6/6 re-run green.

Convergence criteria met: 2 independent Round-2 reviewers CLEAN; the residual security-LOW
closed with grep + test evidence (a behavior-inert logging-value change in cold except paths).

## Test evidence (all green)

- `pytest --collect-only` = **6614 collected**, exit 0.
- New #1564 suite: **6 passed** (SQLite AC1-5 + real PostgreSQL AC6); RED→GREEN proven
  (stash-src on main → `updated_at == created_at` fails AC1).
- Regression suite: **563 passed, 4 skipped** (pre- and post-fix identical).
- Core+schema unit: **816 passed**.
- MySQL node UPDATE smoke (real 8.0.46): `updated_at` bumped, no crash.

## Deferred / notes (tracked, NOT actioned)

- Pre-existing dataflow package lint/type debt (Pyright unused-import/param,
  reportOptionalMemberAccess, unreachable code, `async_run` too-complex) — different bug
  class, exceeds this shard, NOT swept (would be its own mypy-hygiene shard).
- Pre-existing sibling inconsistency: `_unique_index_cache` keys the RAW db_url (the new
  `_column_cache` hashes it) — in-memory-key-only, never logged; the new code is the more
  defensive; out of scope.
- MySQL aiomysql teardown `Event loop is closed` on GC — test-script teardown artifact,
  not in the suite's clean output; not a defect.

## Pending user-gated actions (shared-state — BUILD repo)

1. branch (`release/v2.13.17` or `fix/...`) → commit → push → PR → CI → admin-merge →
   `/release` → PyPI 2.13.17.
2. Close #1564 (both parts delivered) with the merged-PR reference.
