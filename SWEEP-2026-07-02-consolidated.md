# /sweep — kailash-py — 2026-07-02 (consolidated)

Repo-wide outstanding-work audit. Scope: kailash-py only (current repo). Branch `main` @ `ee6e01d57`, in sync with `origin/main` (0/0).

> **Consolidates and supersedes `SWEEP-2026-06-26.md` + `SWEEP-2026-07-02.md`.** Since those runs: the 4 trust/PACT issues (#1480–#1483) shipped via PRs #1484/#1485/#1486 → released as `kailash 2.45.0` (PyPI-verified) + a cross-SDK disclosure hygiene sweep (PRs #1487/#1488/#1489/#1491) genericized every private-Rust-SDK reference across 47 synced `.claude/` files. One NEW issue (#1492) was filed today and is the sole live item.

## Verdict

**Near-clean checkpoint. 1 genuinely-actionable open issue (#1492).** Everything from the prior sweep cycle is shipped + released + verified. 0 open PRs, 0 orphan remote branches, 0 active todos, 0 pending journal candidates, 1 worktree (main, clean), in sync with origin. 0 shippable commits since `v2.45.0` — nothing unreleased. Two process-hygiene items surfaced: significant local branch clutter (242 local branches, 57 worktree-agent remnants) and an accumulation of 24 historical SWEEP files at repo root.

## Findings

| #   | Sweep              | Severity | Finding                                                                                                                   | Disposition                                                 |
| --- | ------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| 1   | 1 Todos            | —        | No active todos in any of the 40 workspaces                                                                               | CLEAN                                                       |
| 2   | 2 Pending journals | —        | 0 `.pending` candidates; `.pending/` dir exists (mops-onboarding) but is empty                                            | CLEAN                                                       |
| 3   | 3 Issues           | MED      | 1 open issue (#1492, filed today) — ChangeDetector startup poll storm + max_concurrent not exposed                        | SURFACE-FOR-PRIORITIZATION                                  |
| 4   | 4 PRs/branches     | LOW      | 0 open PRs; 242 local branches (86 local-only unmerged, 57 worktree-agent remnants)                                       | DEFER-WITH-REASON (branch hygiene; see detail)              |
| 5   | 5 Redteam          | N/A      | No `workspaces/*/specs/` (spec_count=0) — orchestration mode                                                              | N/A (structural — sentinel below)                           |
| 6   | 6 Worktrees        | —        | 1 worktree (main @ `ee6e01d57`, clean); 0 stale `.pending` >14d; 0 stale `.session-notes` >30d                            | CLEAN                                                       |
| 7   | 7 Process          | —        | Working tree: `.session-notes` (M, expected) + 2 untracked `SWEEP-*.md` (prior sweeps); 0/0 vs origin                     | CLEAN                                                       |
| 8   | 7 Stub markers     | LOW      | F-STUBS baseline unchanged; 0 introduced this cycle                                                                       | DEFER-WITH-REASON (user baseline, 2026-06-26)               |
| 9   | 8 Release          | —        | `kailash 2.45.0` published; 0 shippable commits after tag; all closed issues shipped in release                           | NO RELEASE WARRANTED                                        |
| 10  | — Root sweep files | LOW      | 24 `SWEEP-*.md` files accumulated at repo root (24 files, ~270KB); prior sweeps are historical snapshots, not active debt | DEFER-WITH-REASON (archive older than 30d; keep latest 2–3) |

<!-- sweep-redteam:v1:N/A reason=orchestration-mode no_specs=true no_tool=false -->

## Detail

### #3 — Open issue #1492 (MED — newly filed, genuinely actionable)

Filed 2026-07-02. `fix(fabric): ChangeDetector first poll storm-materializes at startup; PipelineExecutor.max_concurrent not exposed via start()`.

- **Affected API**: `dataflow.fabric.change_detector.ChangeDetector._poll_loop`, `dataflow.fabric.runtime.FabricRuntime.start`
- **What**: `_poll_loop` calls `adapter.safe_detect_change()` immediately at t=0 (sleep is at the END of the loop). A fresh adapter with empty change-state returns `True`, dispatching every dependent product for full re-materialization concurrent with the startup pre-warm — an N-source burst that can freeze the event loop for tens of seconds.
- **Contributing**: `PipelineExecutor(max_concurrent=3)` would bound this but `FabricRuntime.start()` doesn't expose it.
- **Severity**: MEDIUM — availability (no data corruption, but probe failures / restart risk on large datasets).
- **Not deferred, not closeable** — has detailed acceptance criteria, a clear root cause, and is genuinely actionable.

**Why this matters**: This is the only live item across the entire repo surface. Everything else shipped in v2.45.0.

### #4 — Local branch hygiene (LOW, deferred with reason)

The repo has accumulated 242 local branches, of which:

- **57 are `worktree-agent-*` branches** — these are temporary isolation branches from parallel agent work. They are never pushed to remote (worktree agents commit locally only). Once the work is merged, these are dead weight — they don't appear in `git branch -r --no-merged origin/main` (0 remote unmerged branches), meaning every substantive fix already landed on main.
- **86 are local-only branches** (no remote tracking) — old feature branches, release-prep branches, audit branches, and debug branches from sessions dating back 8–12 months. Their code shipped long ago; the branches are commit-history bookmarks with no ongoing purpose.
- **~99 are branches with remote tracking** — these include release branches (merged and tagged), codify branches (merged), and feature branches (merged). Most are already merged to main.

**Why not auto-delete**: Bulk branch deletion is a destructive operation across git refs. Per `rules/cross-repo.md` MUST-2, destructive operations require explicit user confirmation. The risk is low (no unmerged work), but the cleanup is mechanical, not urgent, and the user should gate it.

**Recommended cleanup** (if authorized):

```bash
# 1. Delete all worktree-agent branches (temporary, never pushed)
git branch | grep "worktree-agent-" | xargs git branch -D

# 2. Delete merged local branches (safe — already on main)
git branch --merged origin/main | grep -v "^* main$" | xargs git branch -d

# 3. For local-only unmerged branches: review individually, delete most
```

### #8 — Stub-marker baseline (LOW, DEFER-WITH-REASON)

The `# TODO` / `NotImplementedError` matches in `src/` + `packages/*/src` are the F-STUBS baseline the user designated leave-as-baseline on 2026-06-26 (auto-memory `project_fstubs_baseline`). The raw grep over-counts: most `NotImplementedError` are legitimate ABC/override contracts or codegen templates emitting scaffolding for users, most `XXX` are hex/substring false positives, and the genuine `# TODO` comments (~29) are the unchanged pre-existing set. 0 introduced this cycle. Not re-queued per user call.

### #10 — Sweep file accumulation (LOW, deferred)

24 `SWEEP-*.md` files have accumulated at repo root dating back to 2026-04-28. These are deliberately untracked (never committed — `main` is protected; they are session-local audit artifacts per the established pattern). At ~270KB total they are negligible in size, but the clutter makes it hard to find the latest sweep. The most recent 2–3 are the only ones with current relevance. Older files (>30d) are historical snapshots with no ongoing value — they documented the repo state at a point in time that has since been superseded by shipped work.

### Prior sweep resolution — all closed

The 4 issues from the 2026-07-02 sweep are now CLOSED (verified via `gh issue list`):

| Issue     | Disposition                                           | Shipped in                         |
| --------- | ----------------------------------------------------- | ---------------------------------- |
| **#1480** | Authz-root re-validation — `_deserialize_org` fix     | PR #1484 → v2.45.0                 |
| **#1483** | HoldQueue disclosure binding (cross-sdk)              | PR #1485 → v2.45.0                 |
| **#1481** | ConsentAttestation trust primitive                    | PR #1486 → v2.45.0                 |
| **#1482** | Disclosure-trace tokens                               | PR #1486 → v2.45.0                 |
| —         | Cross-SDK disclosure hygiene (47-file genericization) | PRs #1487/#1488/#1489/#1491 → main |

### Release readiness — verified

| Package        | In-tree version | Latest tag  | Status             |
| -------------- | --------------- | ----------- | ------------------ |
| kailash (core) | 2.45.0          | v2.45.0     | ✓ Published (PyPI) |
| kailash-mcp    | 0.2.15          | mcp-v0.2.15 | ✓ Published        |
| kaizen-agents  | 0.9.11          | —           | ✓ Published        |

0 shippable commits since `v2.45.0` — the 2 post-tag commits (PR #1491 merge + its child) are `.claude/` COC documentation only. NO RELEASE WARRANTED.

## Cross-cutting observations

- **The repo shipped a complete cycle**: 4 issues → 3 PRs → release → cross-SDK hygiene → codify. Zero carry-forward, zero deferred work from the prior sweep. This is the cleanest checkpoint in recent history.
- **The only live item is #1492** (fabric ChangeDetector bug). Single-workspace scope, likely fits one shard. The session notes document an outstanding loom Gate-1 propagation item (templatized Rust SDK refs need to flow upstream) — but that's external to kailash-py per `rules/repo-scope-discipline.md`.
- **The mops-onboarding workspace** is complete on the kailash-py side (9 journal entries, proposal staged in `.claude/.proposals/latest.yaml`, loom#669 filed). Remaining distribution is external.
- **Branch hygiene** is the main process debt — 242 local branches, most dead. A one-time cleanup would reduce `git branch` output from ~240 lines to ~20.
- **Sweep file accumulation** is mild clutter — archiving files older than 30d would reduce root-level noise from 24 files to ~3.

## Recommended next-session items (ranked)

1. **#1492 — ChangeDetector startup poll storm** (fabric bug). Fix the `_poll_loop` to seed fingerprints on `connect()` (or sleep before first poll) + expose `max_concurrent` through `FabricRuntime.start()`. Single-workspace, fits one shard, has detailed acceptance criteria in the issue body.
2. **Branch hygiene cleanup** — _if the user wants it_. Delete 57 worktree-agent branches + merged local branches. Low urgency, but mechanical and fast (~30 seconds with the right `xargs` invocation).
3. **Sweep file archive** — _if the user wants it_. Delete or move SWEEP files older than 30d. The prior sweeps documented repo state at points that have since been superseded.
4. _(external, not kailash-py)_ Loom Gate-1 propagation of the templatized Rust SDK refs (the `build.rs` key + Rule 6). Blocked on a loom session; not actionable from here per `repo-scope-discipline.md`.

---

_This report supersedes `SWEEP-2026-06-26.md` and `SWEEP-2026-07-02.md`. It is deliberately left untracked at repo root (the established kailash-py pattern: `main` is protected; `.session-notes` + `SWEEP-*.md` are session-local audit artifacts excluded from PRs)._
