<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->
---
last_reconciled_sha: c21818af435a1dfa38e04a76f368de80186d03b8
migrated_from: .session-notes
---

# Session Notes — 2026-07-02 (v2)

## Where we are

Clean checkpoint on `main` @ `cbbc506e8`. **kailash 2.45.1 + kailash-dataflow 2.13.2
published to PyPI** (clean-venv verified). #1492 (ChangeDetector startup poll storm)
fixed + redteamed to convergence. 0 open issues, 0 open PRs, 0 active todos, 63 local
branches, 24 active workspaces. Forest near-empty — external-only blockers remain.

## Read first

1. `SWEEP-2026-07-02-consolidated.md` — last full sweep (superseded by this session's work)
2. `workspaces/mops-onboarding/journal/` — latest codify work (cross-sdk disclosure hygiene)
3. `gh issue list -R terrene-foundation/kailash-py --state open` — confirm still 0

## In-flight state

None. All work committed, pushed, and released.

## Outstanding ledger (forest)

| ID             | Item                                   | Value-anchor (MUST-1 source)                  | Status          |
| -------------- | -------------------------------------- | --------------------------------------------- | --------------- |
| F-LOOM-GATE1   | Loom Gate-1: templatize Rust SDK refs  | journal/0009 DECISION; proposal latest.yaml   | EXTERNAL (loom) |
| F-SCOPED-OUT   | Scoped-out residuals (5 gov files)     | PR #1491 reviewer verdict (low severity)      | DEFERRED        |
| F-FSTUBS       | ~29 TODO markers in prod code          | user 2026-06-26 "leave as baseline"           | DEFERRED (user) |
| F-AIOSQLITE    | aiosqlite undeclared eager dep in df   | clean-venv install of kailash-dataflow fails  | OPEN — unfiled  |

Closed this session: `F-1492` → PR #1493 + tag v2.45.1 / dataflow-v2.13.2; `F-EXCINFO` → c53308b86; `F-UVLOCK` → 8276d1a15; `F-CLEANUP-BRANCHES` → deleted 179 branches; `F-CLEANUP-WS` → archived 12 workspaces; `F-CLEANUP-SWEEP` → pruned 8 SWEEP files.

## Traps

- `uv run` hits a pre-existing conftest import error (loom paths in editable installs);
  use `.venv/bin/python -m pytest` instead.
- `kailash-dataflow` clean install fails on `import dataflow` because `aiosqlite` is
  an undeclared eager transitive dep — pre-existing; install `aiosqlite` manually or
  use `kailash[db-sqlite]`. (F-AIOSQLITE above.)
- Sub-package releases need separate tags (`dataflow-v*`, `mcp-v*`); core `v*` tags
  publish only the core kailash package.

## Open questions for the human

- F-AIOSQLITE: file the eager-dep issue and fix, or defer?
- F-LOOM-GATE1: when is the next loom session to propagate Gate-1?
