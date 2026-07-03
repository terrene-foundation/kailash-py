<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: 9d765c435
migrated_from: .session-notes
---

# Session Notes — 2026-07-03 (continuation)

## Where we are

Clean on `main`. This session shipped **kailash-dataflow 2.13.7** under `/autonomize`,
closing **#1508** (the F8 item the prior session approved as next work).

- **#1508** — SQLite single-record upsert `conflict_on` on a non-UNIQUE field failed
  (`ON CONFLICT ... does not match any UNIQUE constraint`). The SQLite path already ran a
  WHERE pre-check but discarded it and still emitted `INSERT ... ON CONFLICT`. Fix: use the
  pre-check `row_exists` to emit a plain INSERT / `UPDATE ... WHERE` via new
  `SQLDialect.build_precheck_upsert_query`. PG path unchanged. PR #1521 (fix) + #1522
  (release-prep) → tag `dataflow-v2.13.7` (publish `28651414046` SUCCESS). Clean-venv verified
  live (repro `created: True`). Red-team CONVERGED (3 parallel reviewers, all live-evidence).

## Read first (next session)

1. `gh issue view 1518` — **the recommended next work** (see F-TENANT below).
2. `deploy/deployments/2026-07-03-dataflow-v2.13.7-1508-upsert-conflict-on.md` — the #1508 record.

## Outstanding ledger (forest)

| ID       | Item                                                                            | Value-anchor (MUST-1 source)                               | Status                                                                                                                                                                                            |
| -------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F-TENANT | multi-tenant upsert mis-maps `tenant_id` (INSERT injection writes wrong value)  | #1518; surfaced by #1508 red-team; user flagged 2026-07-03 | **HIGH / security (cross-tenant leak class). RECOMMENDED NEXT.** Proven pre-existing on `main` via file-swap. Orthogonal subsystem (tenant interceptor). Needs its own implement+redteam+release. |
| F-BULK   | bulk_upsert silently ignores `conflict_on` on SQLite (hardcodes ON CONFLICT id) | #1519; surfaced by #1508 red-team                          | HIGH — dup rows + 0 counts; 3 divergent bulk builders + orphaned dialect methods. Design shard.                                                                                                   |
| F-PG     | PG upsert conflict_on on non-unique field → cryptic driver error                | #1520; sibling of #1508                                    | MED — add actionable up-front error (no auto-DDL). Small follow-up.                                                                                                                               |
| F6       | Convert `test_production_dataflow` off the mock engine (Tier-2 NO-MOCKING)      | #1503; rules/testing.md §Tier 2                            | queued (#1503) — xfail-strict self-clears                                                                                                                                                         |
| F7       | `test_concurrent_order_processing` PG two-manual-txn isolation fails on main    | #1504 (pre-existing, proven at HEAD)                       | queued (#1504) — separate PG-isolation shard                                                                                                                                                      |
| F2       | mops-onboarding cross-repo: loom issue + kailash-rs rollout                     | user 2026-06-23 "roll out to kailash-rs…file 2 into loom"  | GATED (receipt-gated; dedicated session)                                                                                                                                                          |
| F3       | ~29 prod TODO markers                                                           | user 2026-06-26 "leave as baseline"                        | DEFERRED (user)                                                                                                                                                                                   |

Closed this session: **#1508** (PR #1521 fix, #1522 release → `dataflow-v2.13.7`).
Filed this session: **#1518**, **#1519**, **#1520** (all pre-existing, surfaced by #1508 red-team).

## Bug-origin context (user asked "why so many issues suddenly?")

NOT new regressions — pre-existing test-coverage debt in the DataFlow upsert/SQLite/multi-tenant
subsystem, surfacing now because it's under active repair. `conflict_on` feature landed
`a96c942d1` 2025-11-02; ON CONFLICT + tenant-injection machinery predates the 2026-03-11 monorepo
move. Mechanism: layered-masking cascade — #1498 (RETURNING/EXCLUDED) → #1502 (`:memory:` private
DB, "no such table") → #1508 (ON CONFLICT constraint); each fix made the next bug reachable
(#1508's test was red the whole time behind an earlier error). Red-teaming #1508 then surfaced the
adjacent untested paths (#1518 tenant, #1519 bulk). The neighborhood + era + missing-tests explain
the batch.

## Traps

- **Prove pre-existing via file-swap, NOT git stash**, AND restore CLEANLY: `git checkout main -- <f>`
  STAGES the reverted file into the index — a later `git commit` (even one adding OTHER files) sweeps
  the staged reversion in. THIS SESSION: that exact hazard silently reverted the #1508 nodes.py fix
  in commit 2bc5c457c; caught via the PR's "1 uncommitted change" warning, restored in 558bb3d07.
  After a file-swap, `git status` and `git diff HEAD` BEFORE any commit; `git add` only intended paths.
- **Release is a structural human gate** — even under /autonomize, get explicit per-release approval
  before the immutable PyPI tag-push (every deployment record shows an explicit "approved").
- **Test env**: root `.venv/bin/python -m pytest` (NOT `uv run`); `.venv/bin/python -m pre_commit`
  (broken shebang on `.venv/bin/pre-commit`). SQLite behavior tests need `aiosqlite`.
- **Broad `-k` test sweeps hang** on infra-dependent tests without Docker — scope to SQLite/unit
  with `--timeout`. Real PG available on 5434 (`aegis-test-pg`).
- **PyPI/uv index lag**: `uv pip install --refresh`, retry 3× / 60s; pip `--no-cache-dir` fallback.

## Open questions for the human

- **F-TENANT (#1518)** — authorize starting the multi-tenant `tenant_id` mis-map fix next? (HIGH
  security; recommended.)
- Batch F-BULK (#1519) + F-PG (#1520) with it, or separate cycles?
