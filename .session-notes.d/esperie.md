<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: a1725ffa6
migrated_from: .session-notes
---

# Session Notes — 2026-07-04

## Where we are

Clean on `main`, 0 open PRs. This session shipped **kailash-dataflow 2.13.10** (`/autonomize` +
`/redteam` + full `/release`), closing **#1520** (F-PG — PG single-record upsert `conflict_on` on a
non-unique field → actionable typed `UpsertConflictTargetError`; mirrors #1519). Filed follow-ups
**#1537** (F-MYSQL) + **#1538** (F-LISTSTALE). Upsert `conflict_on` family (#1508/#1519/#1520) now
fully shipped. **Recommended next: #1537 or #1538** (freshest sibling-class items).

## Read first

1. `deploy/deployments/2026-07-04-dataflow-v2.13.10-1520-pg-single-upsert-conflict-on.md` — #1520 root cause + red-team + the release pattern to mirror.
2. `gh issue view 1537` / `gh issue view 1538` — the filed follow-ups (MySQL silent-upsert; list staleness).
3. `packages/kailash-dataflow/src/dataflow/sql/dialects.py` — `MySQLDialect.build_upsert_query` (the F-MYSQL/#1537 site).

## Outstanding ledger (forest)

| ID          | Item                                                                          | Value-anchor (MUST-1 source)                | Status                                                                                  |
| ----------- | ----------------------------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------- |
| F-MYSQL     | MySQL single-record upsert silently upserts on `id` PK, ignores `conflict_on` | #1537; dataflow-specialist redteam of #1520 | OPEN MED (#1537) — proactive `information_schema` precheck, not error-catch; own shard. |
| F-LISTSTALE | `express.list(cache_ttl=0)` stale after an upsert-UPDATE                      | #1538; discovered testing #1520             | OPEN (#1538) — pre-existing PG read-snapshot/pool gap.                                  |
| F-COMPKEY   | multi_tenant single-column `id` PK → tenants can't share natural key          | #1526; #1518 AC (user 2026-07-03)           | OPEN design — composite `(tenant_id,id)`; maintainer call.                              |
| F-LOGSYNC   | Propagate #1534 log-triage hook fix to loom/USE templates                     | cc-architect #1534 LOW-1; artifact-flow     | OPEN LOW — `/codify` proposal so the fix cascades downstream.                           |
| F6          | Convert `test_production_dataflow` off mock engine (Tier-2 NO-MOCK)           | #1503; rules/testing.md §Tier 2             | queued (#1503) — xfail-strict self-clears.                                              |
| F7          | `test_concurrent_order_processing` PG two-txn isolation fails on main         | #1504 (pre-existing at HEAD)                | queued (#1504) — separate PG-isolation shard.                                           |
| F2          | mops-onboarding cross-repo: loom issue + kailash-rs rollout                   | user 2026-06-23 "roll out to kailash-rs…"   | GATED (receipt-gated; dedicated session).                                               |
| F3          | ~29 prod TODO markers                                                         | user 2026-06-26 "leave as baseline"         | DEFERRED (user).                                                                        |

Closed this session: `F-PG` → dataflow 2.13.10 (PR #1536 fix, #1539 release, tag `dataflow-v2.13.10`, publish run 28676581625 SUCCESS; #1520 closed).

## Traps

- Live single-record upsert path = `core/nodes.py` native-ON-CONFLICT execute (the #1520 guard site); `build_upsert_query` has ONE prod caller there. Bulk = `features/bulk.py` (P1).
- PG single-upsert integration tests: persistent tables accumulate rows across runs (fixture never truncates) → drop-first + `auto_migrate=True` (as #1520's fix did), else `CREATE UNIQUE INDEX` fails on dup data.
- In upsert tests, verify persisted state via raw SQL / `pg_suite.get_connection()`, NOT `express.list` — it can read stale after an upsert-UPDATE (#1538).
- MySQL `ON DUPLICATE KEY UPDATE` ignores `conflict_on` (matches `id` PK) — #1537 needs a constraint precheck, not the #1520 reactive error-catch.
- PyPI/uv release-verify: `uv pip install --refresh` (uv index cache lag); `/<ver>/json` returns 200 before `info.version` updates.

## Unreleased packages

None — dataflow 2.13.10 released + clean-venv-verified this session; all siblings in-sync with PyPI (checked at release). Post-tag commits are docs/workspace-only (carve-out).
