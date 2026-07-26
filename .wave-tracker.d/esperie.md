# Wave tracker — esperie

## Status: NO WAVES IN FLIGHT

All agents idle as of 2026-07-26. Nothing to resume, nothing to re-launch.

## Waves this session (all closed)

- **Wave 5** — 6 shards over the #1970/#1971/#1972/#1974/#1981 forest. ALL SIX died
  mid-flight on a usage limit (not a code failure). Work survived because shards edited
  the SHARED tree, not `isolation: "worktree"` — a worktree wave would have left 6 orphan
  checkouts to recover.
- **Wave 6** — 4 shards re-dispatched to finish + verify. All reported or were verified
  orchestrator-side from the tree.
- **Redteam round 1** — 3 lenses. Only SECURITY reported; correctness + teeth went silent.
- **Redteam round 2** — 3 lenses. All eventually reported (2 required a resume message).

## Standing operational note for the next wave

Agents go idle WITHOUT delivering a final report — **6 occurrences this session**. The
working remedy is to RESUME via message rather than re-dispatch: it recovered 3 of 4,
including the round-1 security report that found both HIGH credential leaks, and a
round-1 lens that surfaced ~6 hours late carrying the session's only commit-blocker.
Re-dispatch only after a resume ALSO returns empty. Never score a silent-idle as a clean
round — that manufactures a convergence that never happened.

## Concurrency

Cold-start ~3 concurrent agents (`rules/worktree-isolation.md` Rule 4). Also run heavy
test suites SERIALLY: concurrent suite runs alongside live agents produced `sqlite3 disk
I/O error` and perf-threshold failures that were self-inflicted, not real.
