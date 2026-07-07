---
type: AMENDMENT
date: 2026-07-08
author: agent
project: kailash-py / kailash-dataflow
topic: kailash-dataflow 2.14.3 RELEASED to PyPI — #1573 __tablename__ migration-path fix converged + published + clean-venv verified
phase: redteam
tags:
  [dataflow, release, pypi, redteam, 2.14.3, tablename, migration, convergence]
relates_to: 0024-AMENDMENT-dataflow-2.14.2-released
---

# 0025 — AMENDMENT: kailash-dataflow 2.14.3 released + verified (#1573)

Picks up the session-8 recommended-next pick (#1573, the migration-subsystem
sibling of #1600/#1541). NOT recoverable from git log alone: the PyPI publish +
clean-venv verification + the process lesson below.

## What shipped (2.14.3, PR #1613, merge `cd796e8d1`, tag `dataflow-v2.14.3`)

**#1573 — AutoMigrationSystem trigger/tracking paths respect `__tablename__`.**
#1541 routed the CREATE INDEX / FK ALTER generators through the
`__tablename__`-respecting resolver `_get_table_name`, but the migration TRIGGER
paths (sync + the 3 async `_execute_*` variants), the diff/target builders
(`_trigger_postgresql_enhanced_schema_management`, `_trigger_postgresql_migration_system`,
`_build_incremental_model_schema`), and the tracking DDL path
(`_execute_postgresql_migration_with_tracking` → `_generate_migration_sql` + its 2
model reverse-lookups) still keyed the migration TARGET schema / diff / ALTER DDL
to the pluralized class-name default. Routed **11 in-scope sites** through
`_get_table_name`. Reachability was evidence-first confirmed (the schema-state
diff planned a phantom `issue1573b_accounts` CREATE TABLE while the real table
was `acct_custom_1573b`; the tracking reverse-lookup resolved the ADD COLUMN
ALTER to an empty statement for a custom-tablename model).

## The process lesson (why this took the shape it did)

- **Over-reach caught by baseline set-diff.** An initial pass ALSO re-keyed the
  3 FK-detection/`_relationships` sites (`_auto_detect_relationships` sync+async,
  `get_relationships`) from default → `__tablename__`. That broke the #1541
  FK/index regression tests. A `git stash` baseline set-diff PROVED the 2 #1541
  failures were mine (green on baseline, red with my change) — the `_relationships`
  dict is keyed by the class-name default by established contract (the #1541 test
  stores under, and `_generate_foreign_key_constraints_sql` reads via, that key).
  Reverted those 3 sites (with NB comments); scope reduced to 11. The FK/query
  keying is a separate, higher-blast-radius concern → filed as #1614.
- **Vacuous-assertion bug caught by verify-claims.** The regression test first
  hardcoded `default_plural` guesses (`issue1573schemaaccounts`) that never matched
  the real snake_cased pluralization (`issue1573_schema_accounts`), making the
  "default absent" / phantom assertions vacuously true. Fixed to compute the
  default via `_class_name_to_table_name` at runtime. Only THEN did the RED→GREEN
  revert-check actually go RED.

## Verification (evidence)

- 3 real-PG regression tests (`tests/regression/test_issue_1573_tablename_migration_tracking_paths.py`):
  Test 1 (incremental-schema builder keys to custom table) + Test 2 (tracking-path
  ALTER generator resolves custom table) are **RED→GREEN proven** by reverting each
  swap; Test 3 is an end-to-end no-phantom/history-consistency guard.
- No regression: #1541 (5), #1600 (2), #1573 (3), DDL-safety/legacy/engine-error
  (27) green; `integration/migration` failure set **byte-identical** to baseline
  (48 = 48, zero delta — all pre-existing PG-test-manager infra failures).
- Redteam converged: reviewer + security-reviewer both clean with quoted evidence
  (reviewer independently re-proved Test 2 RED→GREEN; security-reviewer confirmed
  `_validate_identifier` still fires on the resolved value, no new DDL interpolation).
- CI all-green (20 checks) on pinned head `cc541cc3e`; PyPI publish run
  `28882078313` success; clean-venv `pip install kailash-dataflow==2.14.3` →
  `dataflow.__version__ == 2.14.3`, 11 `#1573` markers present in the shipped wheel.

## Follow-up filed

**#1614** — `Model.query_builder()` (engine.py:2215) has the SAME root
(`_class_name_to_table_name` ignoring `__tablename__`) on the QUERY surface (a
distinct, higher-blast-radius surface, reachable via the query_features integration
suite). Out of #1573's migration scope; carries its own behavioral test + a
cross-SDK (Rust) inspection note. MED.

Pre-existing LOW noted (not filed): the auto-migration `DROP_COLUMN` path
(engine.py:8008) has no `force_drop`/`force_downgrade` confirmation gate
(`schema-migration.md` Rule 7) — a separate hardening candidate, not introduced here.
