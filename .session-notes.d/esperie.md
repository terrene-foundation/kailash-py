<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: 3aff2a707
migrated_from: .session-notes
---

# Session Notes — 2026-07-03

## Where we are

Clean on `main`, working tree clean, 0 open PRs. This session shipped **kailash-dataflow 2.13.9**
(`/autonomize` + `/redteam` to convergence), closing **#1519** (F-BULK — `bulk_upsert` silently
ignored `conflict_on`, hardcoded `ON CONFLICT (id) DO NOTHING` → dup rows + 0 counts). Fix reconciled
3 divergent builders → native `ON CONFLICT (conflict_on) DO UPDATE ... RETURNING` (SQLite/PG) /
`ON DUPLICATE KEY UPDATE` (MySQL), express default `update`, real counts, typed
`BulkUpsertConflictTargetError` on a non-unique target, orphan `build_bulk_upsert_query` deleted.
Red-team also landed identifier-validation (bulk + single-record `{Model}UpsertNode` caller) +
driver-error PII redaction. Recommended next: **#1520** (F-PG, same upsert family).

## Read first

1. `gh issue view 1520` — recommended next (PG upsert `conflict_on` on a non-unique field → cryptic
   driver error; add an actionable up-front error, no auto-DDL — mirrors #1519's raise).
2. `deploy/deployments/2026-07-03-dataflow-v2.13.9-1519-bulk-upsert-conflict-on.md` — #1519 root cause + red-team.
3. `packages/kailash-dataflow/src/dataflow/features/bulk.py` — the LIVE express bulk path (P1);
   `bulk_upsert` + `_build_{postgresql,sqlite,mysql}_upsert` + `_count_existing_conflicts`.
4. `packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py` — the workflow/gateway node (P2).

## Outstanding ledger (forest)

| ID        | Item                                                                   | Value-anchor (MUST-1 source)                              | Status                                                                                                                        |
| --------- | ---------------------------------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| F-PG      | PG upsert `conflict_on` on non-unique field → cryptic driver error     | #1520; sibling of #1508/#1519                             | OPEN MED — add actionable up-front error (no auto-DDL); mirror #1519's `BulkUpsertConflictTargetError`. **RECOMMENDED NEXT.** |
| F-COMPKEY | multi_tenant single-column `id` PK → tenants can't share a natural key | #1526; #1518 AC (user-flagged 2026-07-03)                 | OPEN design — needs composite `(tenant_id,id)` uniqueness. Fails closed today (safe). Maintainer call.                        |
| F6        | Convert `test_production_dataflow` off mock engine (Tier-2 NO-MOCK)    | #1503; rules/testing.md §Tier 2                           | queued (#1503) — xfail-strict self-clears                                                                                     |
| F7        | `test_concurrent_order_processing` PG two-txn isolation fails on main  | #1504 (pre-existing at HEAD)                              | queued (#1504) — separate PG-isolation shard                                                                                  |
| F2        | mops-onboarding cross-repo: loom issue + kailash-rs rollout            | user 2026-06-23 "roll out to kailash-rs…file 2 into loom" | GATED (receipt-gated; dedicated session)                                                                                      |
| F3        | ~29 prod TODO markers                                                  | user 2026-06-26 "leave as baseline"                       | DEFERRED (user)                                                                                                               |

Closed this session: `F-BULK` → `dataflow-v2.13.9` (PR #1530 fix, #1531 release, tag `dataflow-v2.13.9` publish run 28663196213; #1519 closed).

## Traps

- Test env: `.venv/bin/python -m pytest` (NOT `uv run`); SQLite tests need `aiosqlite`; real PG on 5434.
- **Live express bulk path = `features/bulk.py` (P1), NOT `nodes/bulk_upsert.py` (P2) nor `sql/dialects.py`.** `db.express.bulk_upsert` → generated `{Model}BulkUpsertNode` → `core/nodes.py` generic bulk handler → `self.bulk.bulk_upsert`. P2 (`DataFlowBulkUpsertNode`) is the separate `workflow.add_node(...)` / gateway path. `sql/dialects.py::build_bulk_upsert_query` was orphan dead code — deleted in #1519.
- PG upsert integration tests (`test_single_upsert_*::TestPostgreSQL*`) fail on `main` (`could not create unique index "user_email_unique"` / `relation "order_items" does not exist`) — pre-existing PG-fixture-isolation gap, NOT a regression (proven via stash). Don't chase as new.
- `test_bulk_upsert_comprehensive.py` HANGS (pytest-timeout) on `main` too — pre-existing pool/ordering issue; exclude from sweeps, don't chase.
- Bulk/single-record upsert `conflict_on` MUST reference a PK/UNIQUE key → else `BulkUpsertConflictTargetError` (bulk) / driver error (#1520, single-record PG). SQLite single-record tolerates non-unique via the #1508 WHERE-precheck; bulk requires unique (batch-internal-dup ambiguity).
- PyPI/uv index lag on release-verify: `uv pip install --refresh` (uv venv has no pip — don't `python -m pip`); PyPI json endpoint confirms publish before the index reflects it.
