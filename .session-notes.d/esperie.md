<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: c889f3fa9
migrated_from: .session-notes
---

# Session Notes — 2026-07-03

## Where we are

Clean on `main`, 0 open PRs. This session shipped **kailash-dataflow 2.13.9** (`/autonomize` +
`/redteam` to convergence), closing **#1519** (F-BULK — `bulk_upsert` ignored `conflict_on`,
hardcoded `ON CONFLICT (id) DO NOTHING` → dup rows + 0 counts), and fixed a session-end log-triage
false-positive (PR #1534, merged). Recommended next: **#1520** (F-PG, same upsert family).

## Read first

1. `gh issue view 1520` — recommended next (PG upsert `conflict_on` on non-unique → cryptic driver
   error; add an actionable up-front error mirroring #1519's `BulkUpsertConflictTargetError`, no auto-DDL).
2. `deploy/deployments/2026-07-03-dataflow-v2.13.9-1519-bulk-upsert-conflict-on.md` — #1519 root cause + red-team.
3. `packages/kailash-dataflow/src/dataflow/features/bulk.py` — the LIVE express bulk path (P1).

## Outstanding ledger (forest)

| ID        | Item                                                                  | Value-anchor (MUST-1 source)                              | Status                                                                                  |
| --------- | --------------------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| F-PG      | PG upsert `conflict_on` on non-unique field → cryptic driver error    | #1520; sibling of #1508/#1519                             | OPEN MED — actionable up-front error, mirror #1519's typed raise. **RECOMMENDED NEXT.** |
| F-LOGSYNC | Propagate the #1534 log-triage hook fix to loom/USE templates         | cc-architect #1534 LOW-1; artifact-flow (synced hook)     | OPEN LOW — `/codify` proposal so the fix cascades downstream.                           |
| F-COMPKEY | multi_tenant single-column `id` PK → tenants can't share natural key  | #1526; #1518 AC (user 2026-07-03)                         | OPEN design — composite `(tenant_id,id)`; fails closed today. Maintainer call.          |
| F6        | Convert `test_production_dataflow` off mock engine (Tier-2 NO-MOCK)   | #1503; rules/testing.md §Tier 2                           | queued (#1503) — xfail-strict self-clears                                               |
| F7        | `test_concurrent_order_processing` PG two-txn isolation fails on main | #1504 (pre-existing at HEAD)                              | queued (#1504) — separate PG-isolation shard                                            |
| F2        | mops-onboarding cross-repo: loom issue + kailash-rs rollout           | user 2026-06-23 "roll out to kailash-rs…file 2 into loom" | GATED (receipt-gated; dedicated session)                                                |
| F3        | ~29 prod TODO markers                                                 | user 2026-06-26 "leave as baseline"                       | DEFERRED (user)                                                                         |

Closed this session: `F-BULK` → `dataflow-v2.13.9` (PR #1530 fix, #1531 release, tag `dataflow-v2.13.9`; #1519 closed). Log-triage audit-log false-positive → PR #1534 (F-LOGSYNC opened for its loom propagation).

## Traps

- Live express bulk path = `features/bulk.py` (P1), NOT `nodes/bulk_upsert.py` (P2) nor `sql/dialects.py`.
- PG `test_single_upsert_*::TestPostgreSQL*` + `test_bulk_upsert_comprehensive.py` fail/hang on `main` (pre-existing PG-fixture/pool gap, proven via stash). Don't chase.
- Cross-SDK: #1519/#1520 likely exist in the Rust SDK (bulk/single upsert `conflict_on`) — needs a fresh read-only rs grant (repo-scope-discipline); prior grant was #1508/#1518-scoped.
- Bulk `conflict_on` requires PK/UNIQUE → else `BulkUpsertConflictTargetError`; SQLite single-record tolerates non-unique via #1508 precheck.
- PyPI/uv release-verify: `uv pip install --refresh` (uv venv has no pip); PyPI json endpoint confirms publish before the index reflects it.
