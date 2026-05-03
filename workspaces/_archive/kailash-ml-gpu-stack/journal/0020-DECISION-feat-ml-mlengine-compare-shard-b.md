---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T07:56:32.458Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: MLEngine.compare() — multi-family Lightning sweep (shard-B)
phase: implement
tags:
  [
    auto-generated,
    kailash-ml,
    mlengine,
    compare,
    lightning,
    multi-family,
    shard-b,
  ]
related_journal: []
---

# DECISION — MLEngine.compare() — multi-family Lightning sweep (shard-B)

## Commit

`115b13ec244f` — feat(ml): implement MLEngine.compare() — multi-family Lightning sweep (shard-B)

## Body

Replaces the Phase 2 `NotImplementedError` stub with a production implementation per `specs/ml-engines.md` §2.1 MUST 7 (Lightning-as-spine). Every family in the sweep routes through `self.fit()` so the Trainer is the single enforcement point for accelerator / precision resolution.

**Key design decisions**:

- Default family set derived from `setup_result.task_type`: classification / regression → (sklearn, xgboost, lightgbm); clustering → (sklearn,).
- Escape-hatch kwargs `data=` and `target=` let `compare()` run without a prior `setup()` call — needed because `SetupResult._data` storage is owned by sibling shard A and not yet landed; explicit data supersedes whatever `setup_result` contains.
- Optional-extra families (xgboost / lightgbm) skip gracefully when the backend is not installed; no hard-require.
- Ranking metric direction pinned by `_HIGHER_IS_BETTER_METRICS` / `_LOWER_IS_BETTER_METRICS` sets; unknown metrics default to higher-is-better with a WARN for audit.
- `timeout_seconds` budgets the whole sweep; on exceed returns partial leaderboard + WARN log naming the timed-out families per `rules/observability.md`.
- `tenant_id` propagates onto `ComparisonResult` per spec §4.2 MUST 3.

The v0.9.x audit flagged three dispatch branches (sklearn / lightgbm / lightning) each with its own partial device story. Routing every family through `fit()` closes the "some families ignore GPU" failure mode by construction.

Pre-commit bypassed (`core.hooksPath=/dev/null`): the hook resolves `.venv/bin/python` relative to the worktree cwd and the worktree has no local venv. Per `rules/git.md` § Pre-Commit Hook Workarounds.

## For Discussion

1. **Counterfactual**: The v0.9.x audit found three separate dispatch branches each with a partial device story. Routing all families through `self.fit()` as the single Lightning-spine enforcement point closes this. If the old three-branch approach had been retained and a fourth family (e.g. catboost with GPU support) had been added, how many additional device-handling code paths would have been needed, and would the inconsistency have been detectable without an explicit audit?

2. **Data-referenced**: Unknown ranking metrics default to higher-is-better with a WARN. The `_HIGHER_IS_BETTER_METRICS` / `_LOWER_IS_BETTER_METRICS` sets encode this assumption. If a user passes a custom metric name (e.g. `"mean_calibration_error"`) that is lower-is-better, the leaderboard will rank the best-performing model last. Is the WARN sufficient signal, or should unknown-direction metrics cause `compare()` to raise until the caller explicitly specifies direction?

3. **Design**: The `timeout_seconds` budget applies to the whole sweep and returns a partial leaderboard on timeout. The WARN log names the timed-out families. If the timed-out families include the one that would have ranked first, the partial leaderboard leads the caller to select a suboptimal model without realizing it. Should the `ComparisonResult` surface a `timed_out_families` field so callers can detect this programmatically rather than parsing logs?
