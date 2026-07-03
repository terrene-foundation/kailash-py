<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: 558c85c53
migrated_from: .session-notes
---

# Session Notes — 2026-07-03 (continuation)

## Where we are

Clean checkpoint on `main` @ `558c85c53` (post-release-prep merge). **#1498 CLOSED.**
`/autonomize` + `/redteam` drove the SQLite `-k sqlite` suite from **14 failed → 485 passed,
1 skipped, 3 xfailed, 0 failed**, then full release:

- **kailash 2.45.2** (tag `v2.45.2`) + **kailash-dataflow 2.13.5** (tag `dataflow-v2.13.5`)
  published to PyPI, core-first; dataflow `kailash>=` floor bumped `2.28.0 → 2.45.2`.
- Clean-venv verified live (Python 3.12, published wheels + `aiosqlite`): both versions +
  upsert fix behavior (RETURNING row returned; conflict applies `update` values).

Nothing in-flight except the post-release docs commit (this notes + deployment record +
config log) landing now.

## What shipped (two coupled product bugs)

1. **Core** `async_sql.py` SQLite adapter discarded `RETURNING` rows (two DML short-circuits) →
   added `and "RETURNING" not in query.upper()` guards (PostgreSQL-adapter parity).
2. **DataFlow** `dialects.py::build_upsert_query` (SQLite + PG) used `EXCLUDED.col` (the INSERT/
   `create` value) for the SET clause instead of the caller's `update` payload → now binds the
   `update` values as params. Also fixed 2 pre-existing PG upsert failures (verified vs real PG in CI).

Regression test: `tests/regression/test_issue_1498_sqlite_upsert_returning.py`.

## Read first (next session)

1. `deploy/deployments/2026-07-03-v2.45.2-dataflow-2.13.5-1498-sqlite-upsert.md` — full record.
2. `gh issue view 1502` — the real next-shard product work (see ledger F5).

## Outstanding ledger (forest)

| ID  | Item                                                                                                                 | Value-anchor (MUST-1 source)                                                               | Status                                                           |
| --- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------- |
| F5  | Bare sqlite `:memory:` multi-connection: wire the orphaned shared-cache URI through CRUD/registry/migration hot path | user 2026-07-03 "converge" + #1502; user cares re SQLite-default (feedback_sqlite_default) | queued (#1502) — multi-shard product fix; file-backed unaffected |
| F6  | Convert `test_production_dataflow` off the mock engine (Tier-2 NO-MOCKING)                                           | #1503; rules/testing.md §Tier 2                                                            | queued (#1503) — xfail-strict self-clears                        |
| F7  | `test_concurrent_order_processing` PG two-manual-txn isolation fails on main                                         | #1504 (pre-existing, proven at HEAD)                                                       | queued (#1504) — separate PG-isolation shard                     |
| F2  | mops-onboarding cross-repo: loom issue + kailash-rs rollout                                                          | user 2026-06-23 "roll out to kailash-rs…file 2 into loom"                                  | GATED (see Traps)                                                |
| F3  | ~29 prod TODO markers                                                                                                | user 2026-06-26 "leave as baseline"                                                        | DEFERRED (user)                                                  |
| F4  | Loom Gate-1: templatize Rust SDK refs                                                                                | mops journal/0009 DECISION; proposal latest.yaml                                           | EXTERNAL (loom)                                                  |

Closed this session: **#1498** → PR #1505 (fix+tests) + PR #1506 (release) + tags `v2.45.2` /
`dataflow-v2.13.5`. Filed: #1502, #1503, #1504.

## Traps

- **Baseline pre-existing proof (used 4× this session):** to prove a failure is pre-existing,
  `cp <file> $SCRATCH/mine.py; git checkout HEAD -- <files>; <run test>; cp $SCRATCH/mine.py <file>`.
  NEVER `git stash` (stash@{0} is a preserved PRIOR-session release-prep stash — clobber hazard).
- **F2 receipt-gated:** per `repo-scope-discipline.md`, land a fresh journaled
  `cross-repo-authorized:` receipt + a genuine user re-confirm turn BEFORE any command touches
  loom or esperie-enterprise/kailash-rs. Do NOT self-authorize on the 2026-06-23 grant.
- **Test env:** `.venv/bin/python -m pytest` (NOT `uv run` — conftest loom-path import error).
  Root `.venv` (has pytest + editable dataflow); `packages/kailash-dataflow/.venv` lacks pytest.
  `kailash-mcp` was NOT editable-installed at session start (broke pre-commit Tier-1 collection) —
  installed it via `uv pip install -e packages/kailash-mcp` (this modified `uv.lock`, left uncommitted).
- **`.venv/bin/pre-commit` has a broken shebang** — use `.venv/bin/python -m pre_commit`.
- **Release:** sub-package = own tag; publish core-first when a dataflow fix depends on a core fix;
  PyPI/uv cache lags — `uv pip install --refresh` OR pip `--no-cache-dir` fallback; SQLite behavior
  verify needs `aiosqlite` (optional extra) in the clean venv.

## Open questions for the human

- **F5 (#1502)** is the highest-value follow-up given your SQLite-default preference, but it's a
  genuine multi-shard product fix (engine.py + core async_sql.py + sync_ddl_executor + model_registry
  - a cross-thread ProgrammingError + keeping a shared-cache conn alive). Want it taken next, sharded?
- **F2:** ready to re-confirm the cross-repo loom + kailash-rs rollout in a dedicated session?
