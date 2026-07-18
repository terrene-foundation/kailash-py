---
type: DECISION
date: 2026-07-04
display_id: esperie
project: dataflow-upsert-1508
topic: "#1520 F-PG — PostgreSQL single-record upsert conflict_on actionable error"
phase: redteam
---

# DECISION — #1520 (F-PG): typed error for PG single-record upsert on a non-unique conflict target

## What & why

Continuation of the upsert `conflict_on` family (#1508 SQLite single-record precheck,
#1519 bulk). On PostgreSQL a single-record upsert (`db.express.upsert` /
`upsert_advanced` / workflow `{Model}UpsertNode`) with `conflict_on=[field]` where the
field lacks a PK/UNIQUE constraint surfaced the raw driver text *"there is no unique or
exclusion constraint matching the ON CONFLICT specification"* — never naming the field
or the fix. PG's `ON CONFLICT` is atomic and genuinely requires the constraint (a
WHERE-precheck would be a TOCTOU race, unlike SQLite #1508) → the fix is a better error,
not a behavior change.

## Change (working tree, uncommitted — BUILD repo, commit is the user's)

- `core/exceptions.py` — new `UpsertConflictTargetError` (single-record sibling of
  `BulkUpsertConflictTargetError`); added to `__all__`; corrected the now-PG-misleading
  recovery note #2 in `BulkUpsertConflictTargetError` (WHERE-precheck fallback is
  SQLite-only; PG single-record also requires the unique constraint).
- `core/nodes.py` — try/except around the single-record native-ON-CONFLICT execute
  (~:3529), catching the shared `is_conflict_target_error` classifier → raises the typed
  error naming `conflict_on` + remedy; non-matching errors re-raise unchanged (no swallow).
  Verified the SINGLE chokepoint: every single-record surface (express.upsert /
  upsert_advanced / sync variants / fabric / workflow node) funnels through this execute;
  `build_upsert_query` has exactly one production caller (this site).
- NEW `tests/regression/test_issue_1520_pg_single_upsert_conflict_target.py` — 6 tests:
  Tier-2 PG error-path (raise + no row lands + actionable msg) + no-regression happy path
  (real-infra read-back via `get_connection`), cross-dialect SQLite non-raise pin, 3 unit
  pins (message actionable, classifier PG+SQLite match, distinct-but-parallel types).
- `tests/integration/test_single_upsert_conflict_fields.py` — fixed 2 **pre-existing**
  PG failures (proven pre-existing via `git stash`): missing `auto_migrate=True` + no
  table cleanup → persistent dup-data broke `CREATE UNIQUE INDEX`. Drop-first + auto_migrate;
  deterministic across re-runs.

## Redteam — CONVERGED (round 1 clean, 3 independent parallel reviewers)

Receipts (background agent verdicts, 2026-07-04):
- **security-reviewer** (`a362945e6917fe4df`) → **SECURE**: 42P10 conflict-target error
  carries no column VALUES; typed message never interpolates driver text; `original_error`
  handling identical to the bulk sibling — no new leak, no injection.
- **reviewer** (`a6dfb14d2196511a2`) → **CLEAN / ship-ready**: all 5 mechanical sweeps pass
  (single chokepoint, both entry points reach guard, `__all__` parity, operands in scope,
  14+1xfail green). 3 minor advisories (cosmetic message-dialect wording, deep-import
  ergonomics = sibling parity, cross-SDK checklist).
- **dataflow-specialist** (`a7e0c9db3076f7faa`) → **CLEAN on core fix**: guard correctly
  placed + complete; SQLite (#1508) and MySQL behavior undisturbed; tenancy/multi-tenant
  route through the same guard.

Applied post-review: corrected the guard comment (SQLite reaches the execute but never
trips the matcher; MySQL emits ON DUPLICATE KEY UPDATE). Kept the PG-specific error
message (only PostgreSQL reaches this raise today; the divergence-pin test guards a future
SQLite-via-ON-CONFLICT refactor). Re-verified green.

Test tally: upsert family **75 passed / 1 xfailed**; #1520 + single-upsert integration
**14 passed / 1 xfailed** on real PG:5434.

## Out-of-scope follow-ups (exceed this shard; surfaced for user)

1. **MySQL non-unique conflict target silently upserts on the PK** (specialist finding).
   `ON DUPLICATE KEY UPDATE` ignores `conflict_on` and matches the `id` PK → silent INSERT
   instead of upsert-on-field. Pre-existing; NOT introduced by #1520; different mechanism
   (needs proactive `information_schema` constraint precheck, not reactive error-catch) →
   own shard. Recommend a follow-up issue.
2. **`express.list` read-after-upsert-UPDATE staleness** (discovered while testing).
   `db.express.list(cache_ttl=0)` returns stale data after an upsert-UPDATE specifically
   (a plain `update` reads fresh; raw SQL confirms the DB row is correct). Repro standalone
   (no test fixture). Pre-existing (the #1520 guard is transparent on the success path);
   likely the same "PG single-upsert pool gap" the #1519 session notes flagged. Separate
   class from #1520.
3. **Cross-SDK (kailash-rs) parity** for #1520 per `cross-sdk-inspection.md` Rule 1 —
   user-owned; a filing on rs needs a separate explicit gate (`upstream-issue-hygiene.md`).

## Next

Recommend proceeding to `/release` (dataflow patch, mirroring #1519 → 2.13.9): version
bump + CHANGELOG + regression `git add` + PR + admin-merge + PyPI + tag. Awaiting user go
(BUILD-repo shared-state/irreversible steps require confirmation per autonomize Prudence).
