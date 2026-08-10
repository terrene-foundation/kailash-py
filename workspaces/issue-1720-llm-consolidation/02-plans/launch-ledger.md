# Orchestration launch-ledger (`orchestration-launch-ledger.md` MUST-1)

Durable record of every spawned agent. **Consult BEFORE every spawn (MUST-2);
match every completion notification against this table BEFORE reacting (MUST-3).**
Survives compaction — working memory does not.

Session: 2026-08-10 (burn-down waves). Base after Gate 0: `a101c81f9` (main).

## Gate 0 — CLEARED

PR #2028 merged as `a101c81f9` (1,819 files). #1995 closed with the SHA.
CodeQL red was proven a **line-keyed-diff-baseline artifact**, not a regression:
`comm -23 pr main` over `(rule, severity, path)` tuples is EMPTY (PR ⊆ main), and
`comm -13` shows 26 `unused-import` alerts the PR REMOVES. Totals reconcile
(2345 − 2319 = 26). Evidence posted as a PR comment before merge.

## Wave 0 — investigation (READ-ONLY, no branch, no worktree)

| track          | agent        | issue(s)      | branch | status    |
| -------------- | ------------ | ------------- | ------ | --------- |
| 1A-investigate | INV-1A-2025  | #2025         | (none) | in-flight |
| 1B-investigate | INV-1B-2024  | #2024         | (none) | in-flight |
| 1D-investigate | INV-1D-agent | #2030 + #2022 | (none) | in-flight |

## Wave 1 — implementation (sibling worktrees, one PR per lane)

Worktree parent: `/Users/esperie/repos/kailash/build/.kailash-py-wt/`
All branches pinned to merge-base `a101c81f9` (verified at creation, `worktree-isolation.md` Rule 5).

| track | agent        | issue(s)      | branch                           | worktree  | status            |
| ----- | ------------ | ------------- | -------------------------------- | --------- | ----------------- |
| 1A    | —            | #2025         | —                                | —         | blocked on INV-1A |
| 1B    | —            | #2024         | —                                | —         | blocked on INV-1B |
| 1C    | LANE-1C-2026 | #2026         | `fix/2026-auth-test-stubs`       | `lane-1c` | in-flight         |
| 1D    | —            | #2030 + #2022 | —                                | —         | blocked on INV-1D |
| 1E    | LANE-1E-2027 | #2027         | `fix/2027-sensitive-value-sinks` | `lane-1e` | in-flight         |

## Sequencing constraints (from `burndown-waves.md`)

- **1E → 3A**: lane 1E touches `packages/kailash-dataflow/src/dataflow/core/nodes.py`;
  #2006 (lane 3A) touches the same file and MUST wait for 1E to merge.
- **#2030 + #2022 share `base_agent.py`** → one lane (1D), never two.

## Pre-existing worktrees (prior sessions — reconcile before reuse)

`f10-scanner`, `f10-scrubber`, `f10-sinks`, `f11-core-repr`, `f11-kaizen-repr`,
`f13-lifecycle`. NOT touched by this session. Reconcile against merged state
before any cleanup — do NOT bulk-remove (`feedback_no_bulk_worktree_discard`).
