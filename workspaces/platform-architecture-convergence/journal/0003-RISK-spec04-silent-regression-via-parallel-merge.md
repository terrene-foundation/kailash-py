---
type: RISK
date: 2026-04-10
created_at: 2026-04-10T18:15:00Z
author: agent
session_id: 2026-04-10-spec04-reverify
session_turn: analyze
project: platform-architecture-convergence
topic: SPEC-04 slimming was silently regressed by parallel-worktree merge from clearance session
phase: analyze
tags:
  [
    spec-04,
    regression,
    parallel-merge,
    line-count-guard,
    invariant-test,
    base-agent,
    clearance-session,
  ]
---

# SPEC-04 Silently Regressed via Parallel-Worktree Merge

## Context

On 2026-04-10 we opened a session to begin SPEC-04 BaseAgent slimming based on prior `.session-notes` that called it the critical path and reported "0/53 tasks, 2103 LOC". A pre-`/implement` verification pass discovered the `.session-notes` was wrong in a subtle and dangerous way.

## The finding

`base_agent.py` has been slimmed before — and silently regressed.

| Commit     | LOC  | Event                                                       |
| ---------- | ---- | ----------------------------------------------------------- |
| `626b008b` | 925  | SPEC-04 slimming landed (under 1000 LOC target)             |
| `1e39a061` | 994  | `@deprecated` + `AgentPosture` applied                      |
| `7d237786` | 2019 | Merge `worktree-agent-a0ad1085` — **+1094 line regression** |
| `c9bd9e50` | 2088 | Merge `worktree-agent-ab1c46d6` — +69 more                  |
| `fca3b1fb` | 2103 | full clearance +15                                          |
| `HEAD`     | 2103 | current                                                     |

The mixin inheritance (`class BaseAgent(MCPMixin, A2AMixin, Node)`) is still present AND the mixin classes still exist as separate modules (`mcp_mixin.py` 774 LOC, `a2a_mixin.py` 295 LOC). But ~1100 LOC of duplicate/shadow method implementations got re-inlined into `base_agent.py` by a merge from a worktree branch that had been based on a stale pre-slimming tree.

The `.session-notes` from the clearance session reported "2103 LOC / 0 tasks complete" because it measured the file's line count, did NOT examine git history for prior SPEC-04 commits, and did NOT notice that extraction modules already existed. The codified skill `parallel-merge-workflow.md` — which was created in the same session that produced the regression — does not mention the failure mode.

## Why this matters — the missing invariant

SPEC-04's TASK-04-50 was a line-count invariant test: `assert wc -l base_agent.py < 1000`. It was never added. If it had been, the regression merge would have immediately failed CI with "base_agent.py grew from 994 to 2019, invariant violated". Instead, the merge silently succeeded, the session reported "SPEC-04 done via 626b008b + 1e39a061", and the next session (this one) was told SPEC-04 was untouched.

Two separate failure modes compounded:

1. **Content-based merge resolution took the stale version**. The worktree branch's `base_agent.py` was 2000+ LOC (pre-slimming); the target branch's was 994 LOC (post-slimming). The merge tool had no way to know which was "correct" and the agent resolving the conflict chose the larger one — probably because it had more methods that matched the mental model of "BaseAgent does lots of things".

2. **No numeric invariant to detect it**. Line count, method count, specific imports — any of these would have caught the regression at the moment it happened. None were in place.

## Risk classification

**HIGH.** This failure mode is:

- **Silent** — no build break, no test failure, no runtime error
- **Recurring** — same failure pattern could hit every future slimming refactor
- **Concealed by "done" commits** — the SPEC-04 commits are on main, so a naive search for "is SPEC-04 done" finds them and reports yes
- **Captured in a codified skill** — the `parallel-merge-workflow.md` skill was created in the same session that produced this regression and does not warn against it

## Mitigation

Short-term (this session):

1. Write drift-verification report (done: `01-analysis/09-spec04-drift-verification.md`)
2. Escalate to user; do NOT run `/implement` on the 53-task plan as-is

Medium-term (next 1-2 sessions): 3. Restore base_agent.py to ~994 LOC by surgically removing re-inlined shadow methods 4. Add line-count guard test as a permanent pytest invariant (`tests/invariants/test_base_agent_line_count.py`) 5. Restore orphaned workspace artifacts (spec, research, ADR) from scrap branch 6. Close §10.2 (`**kwargs` allowlist) and §10.3 (freeze `BaseAgentConfig`) — the two security surfaces still open 7. Rewrite `todos/active/05-phase3-baseagent.md` against the new baseline

Long-term (skill + rule update): 8. Update `.claude/skills/30-claude-code-patterns/parallel-merge-workflow.md` with:

- Stale-base detection before any worktree merge
- Mandatory numeric invariant for any "shrink N" refactor
- Conflict-resolution protocol: if the two sides differ by >200 lines on the same file, STOP and ask for human disambiguation

9. Add a rule (`rules/refactor-invariants.md` or extend `zero-tolerance.md`): "Every refactor that claims to shrink, extract, or consolidate a file MUST land a programmatic invariant test in the same commit."

## For Discussion

1. **Counterfactual**: if the worktree merge had been a REBASE instead of a merge, would the conflict have surfaced earlier? A rebase would have tried to replay the worktree branch's pre-slimming commits on top of the post-slimming target, producing a sequence of loud conflicts that no agent would have auto-resolved without noticing. Merges are seductive because they "just work" — but that's exactly the problem when the two sides encode incompatible intents.

2. **Data question**: how many other files in this repo have been silently grown by the same pattern? The audit protocol is: for every `refactor:` or `feat:` commit message that mentions "slimming" / "extract" / "consolidate", grep the file's subsequent history for merge commits that increased the line count by >20%. Worth running as an automated scan before the next release — the answer to "how often does this happen" determines whether the mitigation is "add one invariant test" or "add an invariant framework".

3. **Codify failure mode**: the `parallel-merge-workflow` skill was created in the same session that produced the regression. The skill-authoring agent and the implementing agent had access to the same git log but drew different conclusions. Why didn't `/codify` notice the line-count drift? Because `/codify`'s validation step is "did the final commit compile and pass tests" — neither of which detects a 1100-line growth in a previously-slimmed file. The codify phase needs a "diff against the decision record" step: if a journal entry says "SPEC-04 target is <1000 LOC", the codify phase should verify that claim against current state.

## See also

- `01-analysis/09-spec04-drift-verification.md` — full drift report with per-task reconciliation
- Commit `626b008b` — the original slimming
- Commit `1e39a061` — deprecation application
- Commit `7d237786` — the regression merge
- Commit `c9bd9e50` — compounding merge
- `.claude/skills/30-claude-code-patterns/parallel-merge-workflow.md` — the skill that needs updating
- `journal/0002-DECISION-spec04-is-the-critical-path.md` — the prior decision this invalidates
