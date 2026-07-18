---
type: DECISION
date: 2026-07-05
author: agent
display_id: esperie
person_id: esperie
project: dataflow-2.13.16-legacy-migration-and-leak-cleanup
topic: DataFlow 2.13.16 red-team convergence receipt — #1559/#1560/#1561/#1562
phase: redteam
relates_to: 0013-AMENDMENT-kailash-rs-1552-cross-sdk-outcome
---

# DECISION — DataFlow 2.13.16 red-team converged (2 rounds)

Coordination receipt for the F10 follow-up batch surfaced by the 2.13.15 red-team.
Branch `fix/dataflow-2.13.16-legacy-migration-mysql-and-leak-cleanup`, tip `75c3f8e50`,
base `main` `ba60d2bc3`. NOT pushed — merge + PyPI publish gated on user confirmation.

## Fixes (commit SHAs)

| Issue | Fix | Commit |
| ----- | --- | ------ |
| #1559 | legacy `AutoMigrationSystem` emitted Postgres-only DDL on MySQL (`_detect_database_type` never returned "mysql"); + MySQL migration-table DDL variant + `_ensure_migration_table`/`_load_migration_history` MySQL branches | `4a69e6ec1` (+ `4da723196` teardown) |
| #1560 | throwaway `AsyncSQLDatabaseNode` in the `$11` create-retry leaked a connection → `try/finally: cleanup()` | `be484d1d0` |
| #1561 | SQLi-suite fixtures leaked `AsyncSQLDatabaseNode` → `try/finally` cleanup; all 18 injection assertions preserved | `da3284073` |
| #1562 | removed 5 zero-caller dead methods: `_generate_bulk_sql` + `generate_all_crud_sql` (`f74b22f60`) + the 3 transitively-dead `_generate_{insert,update,delete}_sql` exposed by that removal (`e2a777c17`) | `f74b22f60` + `e2a777c17` |
| — | version bump 2.13.15→2.13.16 (both anchors) + CHANGELOG | `75c3f8e50` |

## Red-team rounds (durable verdicts)

- **Round 1** (reviewer + security-reviewer + closure-parity, parallel; agents
  `a1bdd4d66aff1db97`/`acd4e259d7e91d113`/`a3543d5be68a914fa`):
  security CLEAN; closure-parity no UNMET criteria; reviewer MERGE-WITH-FIXES —
  one finding: the #1562 `generate_all_crud_sql` deletion left 3 transitively-dead
  helpers. Fixed `e2a777c17` (autonomous-execution Rule 4 same-shard fix).
  All suites green on real MySQL 8.0.46 + PostgreSQL.
- **Round 2** (reviewer + holistic verifier, parallel; agents
  `a10b7591210738da9`/`a5193d75a67d692f1`): code CLEAN both lenses (exactly 5
  methods removed, all 8 remaining `_generate_*` have live callers, no new orphan,
  #1559 mysql branch correct, version consistent). One durable-artifact finding:
  CHANGELOG said "four" removed vs actual five → corrected (amended into `75c3f8e50`).
  Suites re-run green: MySQL 3/3, PG 2/2 (0 ResourceWarnings), SQLi 18/18,
  adapters 198, 4156 collected exit 0.

Both findings were non-code (one dead-code completeness, one CHANGELOG count) and
are fixed + verified. Code surface independently verified clean by 5 agent-passes
across 2 rounds. Convergence criteria met.

## Deferred (tracked, NOT actioned this session)

- `_get_table_columns_async` (`core/engine.py`) is a PRE-EXISTING zero-caller orphan
  (not exposed by this batch; different bug class). Removing an advertised
  "async-context entry point" is a design decision → follow-up issue, not force-fit
  into a patch release.
- Full removal of the zero-caller `get_upsert_sql`/`upsert_clause` adapter family
  (base `@abstractmethod` + all 3 concrete overrides): deletion-in-isolation breaks
  instantiation → a public-API `zero-tolerance` Rule-6a deprecation-cycle change,
  deferred as a separate PR.
- Pre-existing CWD-fragile test `test_bulk_upsert_no_quote_escape_in_source`
  (SHA `7a4fd3647`, untouched by this branch): optional path-anchoring hardening.

## Pending user-gated actions (shared-state)

1. push → PR → CI → admin-merge → `/release` → PyPI 2.13.16.
2. Issue comments: #1560 premise correction ("per `$11`-retry invocation", not
   "per call"); #1562 scope note (2 of 3 named methods retained as abstractmethod
   overrides; dead-family removal deferred).
3. File follow-up issue for the `_get_table_columns_async` orphan.
