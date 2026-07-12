<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: 1a0b5d372
migrated_from: .session-notes
---

# Session Notes — 2026-07-12 (#1694 re-strand — #21/#22 fixed + full-suite audit)

## Where we are

Continued mops-onboarding **Phase 05-codify** on loom Gate-1 flag-back **#1694**. Re-authored the two
stranded proposal entries #21 (45-genesis watched-paths + runEnrollmentCeremony return) + #22
(43-ecosystem STATE_PATH_RX hedge) as files-present edits, verified byte-for-byte vs the wired hooks,
redteam-converged (reviewer + cc-architect CLEAN), merged **PR #1704**. Full-suite re-verification
found **7 more stranded** entries → reported to loom Gate-1 on #1694. On `main`, board clean (0 PRs).

## Read first

1. `.session-notes.shared.md` — authoritative root forest ledger (F1/F13/F14-FC/F23/F24). START HERE.
2. `gh issue view 1694` + its latest comment — the re-strand disposition + the 7 stranded entries for loom Gate-1.
3. `workspaces/mops-onboarding/journal/0044-DECISION-re-strand-1694-fix-21-22-plus-fullsuite-audit.md` — full receipt.

## Executed this session

- None — no external actions this session (PR #1704 is in THIS repo's git log; the #1694 disposition is a comment on this repo's own issue).

## In-flight state

- **7 stranded proposal entries (#10–#16)** reported to loom Gate-1 via the #1694 comment, awaiting loom-side classification (canonical-apply vs "needs re-authoring here" like #21/#22). NOT re-applied BUILD-side (anti-churn + repo-scope). Loom-tracked, NOT kailash-py SDK forest.
- #21/#22 now files-present on main — loom Gate-1 must re-ingest so the next sync carries them forward, not revert.

## Outstanding ledger (forest)

Authoritative = root `.session-notes.shared.md` (UNCHANGED this session — #1694 is a sub-thread of the
mops-onboarding program F1, which stays BLOCKED on user cross-repo re-confirm). No forest closures.
Warm next pick remains **F13 #1532** (DEFERRED; grant journaled sdk-backlog/0014).

Closed this session: none (forest-level).

## Traps

- **#21/#22 are loom-synced files** — stranded because a prior `/sync-to-build` reverted the BUILD-side edits. Files-present now on main, but loom Gate-1 MUST re-ingest (#1694) or a future sync reverts again. Do NOT re-apply after a revert — let loom Gate-1 canonicalize.
- **Do NOT re-apply the 7 stranded #10–#16 BUILD-side** (churn loop + repo-scope) — loom Gate-1 classifies each per the workspace anti-churn guidance.
- **state-file-guard blocks a `node -e` / `node <script>` bundled with a protected STATE_PATH_RX path** (roster.json/schema, coordination-log, posture, violations, observations, presence-mechanism, .initialized, caches) — split the command or use script-by-path (a `grep operators.roster.schema.json` on the same line as a `node -e` trips it).
- **venv tool shebangs stale** (repo moved from `~/repos/loom/kailash-py`): use `.venv/bin/python -m black|isort|pre_commit`.
- **Root split canonical** — write wrapups to `.session-notes.d/esperie.md` + `.session-notes.shared.md`; workspace monoliths are pointer-stubs.
