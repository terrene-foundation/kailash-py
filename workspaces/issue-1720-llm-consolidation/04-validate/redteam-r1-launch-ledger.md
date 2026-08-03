# Redteam Round 1 — Launch Ledger

Per `rules/orchestration-launch-ledger.md` MUST-1: written BEFORE spawn, consulted before any
further spawn (MUST-2), matched against every completion notification (MUST-3).

- **Branch:** `fix/issue-1720-forest-drain` @ `f7c30101f` (pushed; `origin/main` @ `26a4509b4`)
- **Scope:** 134 files, 6 packages, 17 commits — issues #1970 #1971 #1972 #1974 #1981
- **Round:** 1 of N. Convergence = 2 consecutive clean rounds on **BUG + INVEST-NOW only**
  (`rules/product-completion-first.md`; INCREMENTAL accrues to the deferred-quality backlog
  and does NOT reset the counter).
- **Materialized surface** (read-only reviewers cannot run git): `<scratch>/redteam/` —
  `forest-code.diff` (16,255 lines), `security-surface.diff` (3,522), `changed-files.txt`
  (134), `commits.txt` (17).

## Launch table

| track          | agent             | scope                                                       | status    |
| -------------- | ----------------- | ----------------------------------------------------------- | --------- |
| r1-correctness | reviewer          | closure-parity: 5 issues → delivered code; regression tests | in-flight |
| r1-security    | security-reviewer | ADVERSARIAL, prompted to REFUTE — credential-scrub surfaces | in-flight |
| r1-sweep       | reviewer          | mechanical AST/grep over ABSOLUTE state, not only the diff  | in-flight |

Concurrency 3 — cold-start cap per `rules/worktree-isolation.md` Rule 4. No worktrees: all
three tracks are READ-ONLY, so no isolation is required and none was created.

## Evidence gate (`rules/agents.md` § Redteam Reviewer Dispatch)

A round counts CLEAN only when EVERY dispatched reviewer returns a genuine ran-signal. An
errored / empty / timed-out / throttled return is ZERO evidence, MUST be re-run, and MUST NOT
count toward a clean round. On a synchronized-throttle signal (≥2 agents dying within a
~30–48s window carrying `not your usage limit`), reduce concurrency and re-run the throttled
reviewers.

## Two-lens requirement

`rules/agents.md` § "Correctness-Review-Clean Is Not Security-Clean": these commits change
credential scrubbing, provider-error sanitization, and redaction paths. A CLEAN correctness
verdict is NOT evidence the change is security-clean. Both r1-correctness AND r1-security
must return genuine ran-signals before convergence is claimable for this round.

## Round-1 result

_(pending — filled on completion)_
