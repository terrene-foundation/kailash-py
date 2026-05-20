# DECISION — Todos crystallized as 3-shard sequence + verification gate (ready for human approval)

**Date**: 2026-05-15
**Phase**: /todos complete; awaiting human gate

## Decision

Adopt `todos/active/{00-INDEX,01-S1-cluster-a-tier1-moves,02-S2-cluster-b-file6-split,03-S3-verification-gate}.md` as the crystallized work plan. STOP for human approval per `/todos` workflow step 6.

## Round history (this phase)

| Round                                | Verdict                            | Source                                             |
| ------------------------------------ | ---------------------------------- | -------------------------------------------------- |
| /todos red-team (analyst)            | APPROVE-WITH-FIXES (1 MED + 4 LOW) | findings returned inline (agent didn't write file) |
| /todos red-team (testing-specialist) | APPROVE with 1 LOW                 | `04-validate/08-redteam-todos-testing.md`          |

All findings amended in-place (no v2 todos needed). Specifically:

| Finding                                                                                         | Severity            | Fix                                                                                            |
| ----------------------------------------------------------------------------------------------- | ------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Tenth file `performance/test_postgresql_test_manager_concurrent.py` silently dropped from audit | MED                 | Added File 10 to S1 scope; recorded in `journal/0006`; INDEX updated; new open question #6     |
| INDEX doesn't surface 128-vs-74 mock-count delta                                                | LOW                 | New § "Verified scope correction" prepended to INDEX                                           |
| S3 grep verifies original paths but not new Tier-1 paths                                        | LOW                 | S3 § Scope step 1b added (Tier-1 sanity check)                                                 |
| `rules/upstream-issue-hygiene.md` cited for intra-repo follow-up                                | LOW                 | S3 § Scope step 9 reworded — body shape is modelled after the rule, not strictly subject to it |
| S2 verification regex `::test\_(parameter_conversion                                            | .+\_param)` brittle | LOW                                                                                            | Replaced with `<file>::TestConnectionManagerAdapter` + `::TestParameterConversionEdgeCases` class-name filter |
| S1+S2 lacked explicit parent-side `ls` verification (per worktree-isolation Rule 3)             | LOW                 | Both shards now include the orchestrator's post-exit ls block                                  |
| S3 sequencing needed `gh pr view --json mergedAt` runnable gate                                 | LOW                 | Pre-flight gate added to S3 § Sequencing reason                                                |

## Capacity-budget check

Per `rules/autonomous-execution.md` MUST-1 (≤500 LOC, ≤10 invariants, ≤4 call-graph hops):

| Shard |                                            LOC | Invariants |      Call-graph hops | Verdict    |
| ----- | ---------------------------------------------: | ---------: | -------------------: | ---------- |
| S1    | ~-220 (10 moves + 1 split + smoke-test delete) |          9 | 1 (structural moves) | within cap |
| S2    |                    -300/+50 (extract + delete) |          4 |    1 (local extract) | within cap |
| S3    |                          0 (verification only) |          5 |      0 (bookkeeping) | within cap |

## What the human approves at this gate (per `rules/autonomous-execution.md` § Structural vs Execution Gates)

- The WHAT and WHY of the work (3-shard plan + value-anchors per shard).
- The 6 open questions in INDEX § "Open questions for human gate".
- Not the HOW or WHEN (execution is autonomous per /implement after gate clears).

## What happens after approval

`/implement issue-979-b15-tier2-mock-rewrite` runs autonomously:

1. Pre-flight: `git fetch origin && git rev-parse origin/main` pins base SHA.
2. Wave 1 (parallel worktree, ≤3 per Rule 4): launch S1 + S2 agents with worktrees. Parent verifies cwd + branch + commits + deliverables after each agent exits.
3. After BOTH PRs merge to main (detected via `gh pr view --json mergedAt`), launch S3 (sequential, no worktree — verification only).
4. S3 closes #992, writes `journal/0008-DECISION-shard-classifications.md`, and surfaces the E2E TDD-mode follow-up issue draft for user gate.

## Convergence verdict

Plan ready for /implement. Human gate is the next step.
