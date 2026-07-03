<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: 5d9128924
migrated_from: .session-notes
---

# Session Notes — 2026-07-03 (continuation)

## Where we are

Clean on `main` @ `5d9128924` (post #1502 release-prep merge). This session shipped
**two full releases** under `/autonomize`:

1. **#1498** (SQLite `-k sqlite` failures) → `kailash 2.45.2` + `kailash-dataflow 2.13.5`
   (upsert RETURNING + update-value; -k sqlite 14→0 failed).
2. **#1502** (bare `:memory:` multi-connection) → `kailash 2.45.3` + `kailash-dataflow 2.13.6`
   (one shared-cache URI per instance + lifetime anchor threaded through every SQLite
   connection site; cross-thread registry StaticPool). Clean-venv verified live.

All committed, merged, released, clean-venv verified. Post-release docs commit
(deployment record + config log + these notes) landing now. Nothing else in-flight.

## Read first (next session)

1. `deploy/deployments/2026-07-03-v2.45.3-dataflow-2.13.6-1502-sqlite-memory.md` — the #1502 record.
2. `gh issue view 1508` — the highest-value queued follow-up (see F8).

## Outstanding ledger (forest)

| ID  | Item                                                                         | Value-anchor (MUST-1 source)                               | Status                                                                                                                              |
| --- | ---------------------------------------------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| F8  | upsert `conflict_on=[field]` fails when field has no UNIQUE constraint       | #1508; surfaced by #1502; user cares re SQLite correctness | queued (#1508) — needs DataFlow upsert-semantics decision (auto-index conflict fields vs validate-and-raise vs require unique=True) |
| F6  | Convert `test_production_dataflow` off the mock engine (Tier-2 NO-MOCKING)   | #1503; rules/testing.md §Tier 2                            | queued (#1503) — xfail-strict self-clears                                                                                           |
| F7  | `test_concurrent_order_processing` PG two-manual-txn isolation fails on main | #1504 (pre-existing, proven at HEAD)                       | queued (#1504) — separate PG-isolation shard                                                                                        |
| F2  | mops-onboarding cross-repo: loom issue + kailash-rs rollout                  | user 2026-06-23 "roll out to kailash-rs…file 2 into loom"  | GATED (see Traps)                                                                                                                   |
| F3  | ~29 prod TODO markers                                                        | user 2026-06-26 "leave as baseline"                        | DEFERRED (user)                                                                                                                     |
| F4  | Loom Gate-1: templatize Rust SDK refs                                        | mops journal/0009 DECISION; proposal latest.yaml           | EXTERNAL (loom)                                                                                                                     |

Closed this session: **#1498** (PR #1505/#1506), **#1502** (PR #1509/#1511). Filed:
#1502, #1503, #1504 (during #1498); #1508 (during #1502). Two pre-existing PG upsert
failures remain (test_postgresql_auto_timestamp_management + composite_conflict "order_items
does not exist") — PG-specific, likely local-postgres-env artifacts (main CI green), out of scope.

## Traps

- **Prove pre-existing via file-swap, NOT git stash** (stash@{0} = preserved PRIOR-session
  release-prep stash; clobber hazard): `cp <f> $SCRATCH; git checkout HEAD -- <f>; test; cp back`.
  And `for f in $FILES` does NOT word-split in zsh — use a `FILES=(...)` array.
- **F2 receipt-gated**: per `repo-scope-discipline.md`, land a fresh journaled
  `cross-repo-authorized:` receipt + a genuine user re-confirm turn BEFORE any command touches
  loom or esperie-enterprise/kailash-rs. Do NOT self-authorize on the 2026-06-23 grant.
- **Test env**: root `.venv/bin/python -m pytest` (NOT `uv run`); `kailash-mcp` must be
  editable-installed (`uv pip install -e packages/kailash-mcp`) or pre-commit Tier-1 collection
  breaks; `.venv/bin/pre-commit` has a broken shebang → use `.venv/bin/python -m pre_commit`.
- **SQLite behavior tests need `aiosqlite`** (optional extra) in the clean venv.
- **Release**: core-first when a dataflow fix depends on a core fix; PyPI/uv/pip index lags —
  `uv pip install --refresh` OR pip `--no-cache-dir` with a 60s-retry loop (the `pypi.org/pypi/
<pkg>/<ver>/json` endpoint reflects the upload before pip's simple-index view does).
- **`:memory:` shared-cache primitive** (from #1502): `DataFlow._memory_db_uri` +
  `_memory_connection` anchor + `SQLDatabaseNode.dispose_pools_for()`. Any new SQLite
  connection-construction site MUST route bare `:memory:` through `_memory_db_uri` + pass uri=True.

## Open questions for the human

- **F8 (#1508)** is the natural next SQLite-correctness follow-up (upsert conflict_on without a
  UNIQUE index) — but it needs a DataFlow upsert-semantics decision (auto-create a UNIQUE index
  for conflict_on fields, vs validate-and-raise, vs require `unique=True`). Which direction?
- **F2**: ready to re-confirm the cross-repo loom + kailash-rs rollout in a dedicated session?
