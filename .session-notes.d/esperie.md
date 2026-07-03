<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: 7811d2062
migrated_from: .session-notes
---

# Session Notes — 2026-07-03 (continuation)

## Where we are

Clean on `main`. This session shipped **kailash-dataflow 2.13.8** under `/autonomize` +
`/redteam`, closing **#1518** (F-TENANT, the prior session's recommended-next work).

- **#1518** — `multi_tenant=True` single-record upsert persisted the row's `id` value in
  `tenant_id` instead of the active tenant (cross-tenant leak class). Root cause: the SQLite
  precheck-upsert builder (`build_precheck_upsert_query`, #1508) emits named `:pN` placeholders;
  the tenant `QueryInterceptor` appends `tenant_id` when the INSERT omits it, but
  `_detect_placeholder_style` didn't recognise `:pN` → defaulted to `qmark` → appended a `?` into
  a `:pN` query → downstream `_convert_to_named_parameters` renumbered that `?` to `:p0`,
  colliding with the existing `:p0` so `tenant_id` bound to the first value. Fix: interceptor now
  recognises the `:pN` (`colon`) style across INSERT + UPDATE/DELETE + SELECT paths → pure `:pN`.
  PR #1525 (fix) + #1527 (release-prep) → tag `dataflow-v2.13.8` (publish `28657016873` SUCCESS).
  Clean-venv verified live (repro raw `tenant_id == "tenant-a"`, was the `id` value pre-fix).
  Red-team CONVERGED (Round 1 reviewer + security-reviewer both MERGE-WITH-FIXES; the SELECT-path
  `:pN` sibling gap fixed in-session; Round 2 adversarial verifier CONVERGED). 11 regression tests.
- **#1508** (prior) — SQLite upsert `conflict_on` on a non-UNIQUE field → `dataflow-v2.13.7`.

## Read first (next session)

1. `gh issue view 1518` (CLOSED) + `1526` (composite-key follow-up) + `1519`/`1520` (siblings).
2. `deploy/deployments/2026-07-03-dataflow-v2.13.8-1518-multi-tenant-upsert-tenant-id.md`.

## Outstanding ledger (forest)

| ID        | Item                                                                            | Value-anchor (MUST-1 source)                               | Status                                                                                                                                                                        |
| --------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F-TENANT  | multi-tenant upsert mis-maps `tenant_id` (INSERT injection writes wrong value)  | #1518; surfaced by #1508 red-team; user flagged 2026-07-03 | **CLOSED 2026-07-03 → `dataflow-v2.13.8`** (PR #1525 fix, #1527 release). Interceptor `:pN` colon-style fix. Composite-key AC split to #1526.                                 |
| F-COMPKEY | multi_tenant single-column `id` PK → two tenants can't share a natural key      | #1526; surfaced fixing #1518                               | OPEN (design) — needs composite `(tenant_id, id)` uniqueness (migrations, PG+SQLite, cross-SDK). Fails closed today (UNIQUE constraint — safe, no leak). Maintainer decision. |
| F-BULK    | bulk_upsert silently ignores `conflict_on` on SQLite (hardcodes ON CONFLICT id) | #1519; surfaced by #1508 red-team                          | HIGH — dup rows + 0 counts; 3 divergent bulk builders + orphaned dialect methods. Design shard.                                                                               |
| F-PG      | PG upsert conflict_on on non-unique field → cryptic driver error                | #1520; sibling of #1508                                    | MED — add actionable up-front error (no auto-DDL). Small follow-up.                                                                                                           |
| F6        | Convert `test_production_dataflow` off the mock engine (Tier-2 NO-MOCKING)      | #1503; rules/testing.md §Tier 2                            | queued (#1503) — xfail-strict self-clears                                                                                                                                     |
| F7        | `test_concurrent_order_processing` PG two-manual-txn isolation fails on main    | #1504 (pre-existing, proven at HEAD)                       | queued (#1504) — separate PG-isolation shard                                                                                                                                  |
| F2        | mops-onboarding cross-repo: loom issue + kailash-rs rollout                     | user 2026-06-23 "roll out to kailash-rs…file 2 into loom"  | GATED (receipt-gated; dedicated session)                                                                                                                                      |
| F3        | ~29 prod TODO markers                                                           | user 2026-06-26 "leave as baseline"                        | DEFERRED (user)                                                                                                                                                               |

Closed this session: **#1518** (PR #1525 fix, #1527 release → `dataflow-v2.13.8`).
Filed this session: **#1526** (composite-key design follow-up, split from #1518's AC).
Prior session: closed #1508 → `dataflow-v2.13.7`; filed #1518/#1519/#1520.

## Cross-SDK (kailash-rs) — #1508 NOT applicable

User-authorized READ-ONLY inspection (journal `0010`, `cross-repo-authorized: esperie-enterprise/kailash-rs`).
Finding: the Rust DataFlow upsert primitive `QueryDialect::upsert_conflict_clause(pk: &str, update_columns)`
(`crates/kailash-dataflow/src/dialect.rs`, called `upsert_conflict_clause(pk, …)` in `query.rs`) conflicts on
a **single primary key** (`ON CONFLICT({pk})`) — ALWAYS PK-constraint-backed. It does NOT expose an arbitrary
non-unique `conflict_on`/`conflict_keys` field, so the #1508 bug class (SQLite ON CONFLICT on a non-unique
target) is **structurally unreachable** in rs. Legitimate EATP-D6 API divergence (same shape as kailash-py's
own pk-only bulk path). **No rs fix or issue needed for #1508.** (rs `excluded.col` SET is correct for its
single-payload upsert — no #1498 divergence: #1498 was py's separate create-vs-update-dict bug.)
**#1518 (tenant mis-map) NOT assessed in rs** — py-implementation-specific (interceptor INSERT column/param
misalignment); rs has an independent Rust tenant impl. If rs cross-check for #1518 is wanted, do it from a
DEDICATED kailash-rs session (its own scope), not cross-repo from here. NO issue filed on rs (scope-fenced;
filing needs a separate gate per upstream-issue-hygiene MUST-1).

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
