<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: c889f3fa9
migrated_from: .session-notes
---

# Session Notes — 2026-07-04

## Where we are

Clean on `main`, 0 open PRs. This session **shipped kailash-dataflow 2.13.10** (`/autonomize` +
`/redteam` to convergence + full `/release`), closing **#1520** (F-PG — PG single-record upsert with
`conflict_on` on a non-unique field raised the raw driver text; now raises typed
`UpsertConflictTargetError` naming field + remedy; PG keeps atomic ON CONFLICT, no auto-DDL). Fix PR
#1536, release PR #1539, tag `dataflow-v2.13.10`, publish run 28676581625 SUCCESS, clean-venv install
verified. Also fixed 2 pre-existing PG single-upsert integration test failures (proven pre-existing).
Filed follow-ups **#1537** (MySQL silent-upsert-on-PK) + **#1538** (`express.list` staleness).

Prior: 2.13.9 closed #1519 (F-BULK). The upsert `conflict_on` family (#1508 SQLite single, #1519
bulk, #1520 PG single) is now fully shipped.

## Read first

1. `deploy/deployments/2026-07-04-dataflow-v2.13.10-1520-pg-single-upsert-conflict-on.md` — #1520 root cause + red-team + verify.
2. `workspaces/mops-onboarding/journal/0011-*.md` — #1520 decision + redteam receipts.
3. `gh issue view 1537` / `gh issue view 1538` — the filed follow-ups (MySQL + list-staleness).

## Recommended next

- **#1537** (F-MYSQL) — MySQL single-record upsert silently upserts on `id` PK ignoring `conflict_on`;
  needs proactive `information_schema` constraint precheck (different mechanism than #1520's error-catch).
- **#1538** (F-LISTSTALE) — root-cause the `express.list` read-after-upsert-update staleness.
- **kailash-rs parity** for #1520 (`cross-sdk-inspection.md`) — needs a fresh read-only rs grant.

## Outstanding ledger (forest)

| ID          | Item                                                                                                              | Value-anchor (MUST-1 source)                              | Status                                                                                                                              |
| ----------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| F-PG        | PG upsert `conflict_on` on non-unique field → cryptic driver error                                                | #1520; sibling of #1508/#1519                             | **CLOSED → dataflow 2.13.10** (PR #1536 fix, #1539 release, tag `dataflow-v2.13.10`; #1520 closed). journal/0011.                   |
| F-MYSQL     | MySQL single-record upsert silently upserts on `id` PK, ignores `conflict_on`                                     | #1537; dataflow-specialist redteam of #1520 (2026-07-04)  | OPEN MED (#1537) — pre-existing; diff mechanism (proactive `information_schema` constraint precheck, not error-catch); own shard.   |
| F-LISTSTALE | `express.list(cache_ttl=0)` returns stale rows after an upsert-UPDATE (plain update reads fresh; raw SQL correct) | #1538; discovered while testing #1520 (2026-07-04)        | OPEN (#1538) — pre-existing PG read-snapshot/pool gap (likely the #1519-notes "single-upsert pool gap"); separate class from #1520. |
| F-LOGSYNC   | Propagate the #1534 log-triage hook fix to loom/USE templates                                                     | cc-architect #1534 LOW-1; artifact-flow (synced hook)     | OPEN LOW — `/codify` proposal so the fix cascades downstream.                                                                       |
| F-COMPKEY   | multi_tenant single-column `id` PK → tenants can't share natural key                                              | #1526; #1518 AC (user 2026-07-03)                         | OPEN design — composite `(tenant_id,id)`; fails closed today. Maintainer call.                                                      |
| F6          | Convert `test_production_dataflow` off mock engine (Tier-2 NO-MOCK)                                               | #1503; rules/testing.md §Tier 2                           | queued (#1503) — xfail-strict self-clears                                                                                           |
| F7          | `test_concurrent_order_processing` PG two-txn isolation fails on main                                             | #1504 (pre-existing at HEAD)                              | queued (#1504) — separate PG-isolation shard                                                                                        |
| F2          | mops-onboarding cross-repo: loom issue + kailash-rs rollout                                                       | user 2026-06-23 "roll out to kailash-rs…file 2 into loom" | GATED (receipt-gated; dedicated session)                                                                                            |
| F3          | ~29 prod TODO markers                                                                                             | user 2026-06-26 "leave as baseline"                       | DEFERRED (user)                                                                                                                     |

Closed this session: `F-BULK` → `dataflow-v2.13.9` (PR #1530 fix, #1531 release, tag `dataflow-v2.13.9`; #1519 closed). Log-triage audit-log false-positive → PR #1534 (F-LOGSYNC opened for its loom propagation).

## Traps

- Live express bulk path = `features/bulk.py` (P1), NOT `nodes/bulk_upsert.py` (P2) nor `sql/dialects.py`.
- PG `test_single_upsert_*::TestPostgreSQL*` + `test_bulk_upsert_comprehensive.py` fail/hang on `main` (pre-existing PG-fixture/pool gap, proven via stash). Don't chase.
- Cross-SDK: #1519/#1520 likely exist in the Rust SDK (bulk/single upsert `conflict_on`) — needs a fresh read-only rs grant (repo-scope-discipline); prior grant was #1508/#1518-scoped.
- Bulk `conflict_on` requires PK/UNIQUE → else `BulkUpsertConflictTargetError`; SQLite single-record tolerates non-unique via #1508 precheck.
- PyPI/uv release-verify: `uv pip install --refresh` (uv venv has no pip); PyPI json endpoint confirms publish before the index reflects it.
