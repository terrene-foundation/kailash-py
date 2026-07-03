<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: 75015a852
migrated_from: .session-notes
---

# Session Notes — 2026-07-03

## Where we are

Clean on `main`, working tree clean, 0 open PRs. This session shipped **kailash-dataflow 2.13.8**
(`/autonomize` + `/redteam`), closing **#1518** (multi_tenant upsert mis-mapped `tenant_id` →
cross-tenant leak class) via an interceptor `:pN` colon-style fix. Recommended next: **#1519**
(F-BULK, same upsert bug family).

## Read first

1. `gh issue view 1519` — recommended next (bulk_upsert ignores `conflict_on` on SQLite).
2. `deploy/deployments/2026-07-03-dataflow-v2.13.8-1518-multi-tenant-upsert-tenant-id.md` — #1518 root cause.
3. `packages/kailash-dataflow/src/dataflow/sql/dialects.py` — the 3 divergent bulk builders (#1519 core).
4. `packages/kailash-dataflow/src/dataflow/tenancy/interceptor.py` — the `:pN` machinery just fixed.

## Outstanding ledger (forest)

| ID        | Item                                                                   | Value-anchor (MUST-1 source)                              | Status                                                                                                        |
| --------- | ---------------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| F-BULK    | bulk_upsert ignores `conflict_on` on SQLite (hardcodes ON CONFLICT id) | #1519; surfaced by #1508 redteam                          | OPEN HIGH — dup rows + 0 counts; 3 divergent builders + orphaned methods. Design shard. **RECOMMENDED NEXT.** |
| F-PG      | PG upsert `conflict_on` on non-unique field → cryptic driver error     | #1520; sibling of #1508                                   | OPEN MED — add actionable up-front error (no auto-DDL).                                                       |
| F-COMPKEY | multi_tenant single-column `id` PK → tenants can't share a natural key | #1526; #1518 AC (user-flagged 2026-07-03)                 | OPEN design — needs composite `(tenant_id,id)` uniqueness. Fails closed today (safe). Maintainer call.        |
| F6        | Convert `test_production_dataflow` off mock engine (Tier-2 NO-MOCK)    | #1503; rules/testing.md §Tier 2                           | queued (#1503) — xfail-strict self-clears                                                                     |
| F7        | `test_concurrent_order_processing` PG two-txn isolation fails on main  | #1504 (pre-existing at HEAD)                              | queued (#1504) — separate PG-isolation shard                                                                  |
| F2        | mops-onboarding cross-repo: loom issue + kailash-rs rollout            | user 2026-06-23 "roll out to kailash-rs…file 2 into loom" | GATED (receipt-gated; dedicated session)                                                                      |
| F3        | ~29 prod TODO markers                                                  | user 2026-06-26 "leave as baseline"                       | DEFERRED (user)                                                                                               |

Closed this session: `F-TENANT` → `dataflow-v2.13.8` (PR #1525 fix, #1527 release; #1518 closed).

## Traps

- Test env: `.venv/bin/python -m pytest` (NOT `uv run`); SQLite tests need `aiosqlite`; real PG on 5434.
- PG upsert integration tests (`test_single_upsert_*`) fail on `main` with `relation "order_items" does not exist` — pre-existing PG-fixture gap, NOT a regression (proven via stash). Don't chase as new.
- `:pN` (colon) placeholders come from EVERY upsert/bulk dialect builder, not only the SQLite precheck — relevant to #1519's builder reconciliation.
- PyPI/uv index lag on release-verify: `uv pip install --refresh`, retry ~3×/60s.
