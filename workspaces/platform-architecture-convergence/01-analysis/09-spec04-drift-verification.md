# SPEC-04 Drift Verification — 2026-04-10

**Purpose**: Re-baseline the SPEC-04 "BaseAgent slimming" plan against current `main` state before resuming `/implement`. The prior session's `.session-notes` (1h old) called SPEC-04 "0/53 tasks, 2103 LOC". Verification found a much more complicated picture.

## TL;DR

**SPEC-04 was already completed, then silently regressed by a parallel-worktree merge from the last clearance session.** The 53-task plan in `todos/active/05-phase3-baseagent.md` was never re-baselined after the first slimming pass and describes a world that no longer exists.

The right next action is **NOT** to execute the 53-task plan. It is:

1. Diagnose the regression (what exactly got re-inlined)
2. Re-extract the regressed code (most extraction modules still exist)
3. Add the line-count guard test (TASK-04-50) so this cannot recur
4. Restore orphaned workspace artifacts (spec + research + ADR) from scrap branch to main
5. Update the `parallel-merge-workflow` skill with the regression lesson
6. Rewrite the todos file against current state

## Timeline: base_agent.py line count across commits

| Commit     | Date   | base_agent.py LOC | Event                                                               |
| ---------- | ------ | ----------------- | ------------------------------------------------------------------- |
| `4cd5ef51` | Apr 8  | (3,132 baseline)  | Snapshot of pre-triage working tree (scrap safety net)              |
| `626b008b` | Apr 8  | **925**           | **SPEC-02 provider split + SPEC-04 slimming** (extraction complete) |
| `1e39a061` | Apr 9  | **994**           | SPEC-04 `@deprecated` + `AgentPosture` enum applied                 |
| `7d237786` | Apr 9  | **2,019**         | 🚨 Merge `worktree-agent-a0ad1085` — **+1,094 insertions**          |
| `c9bd9e50` | Apr 9  | **2,088**         | 🚨 Merge `worktree-agent-ab1c46d6` — **+69 more lines**             |
| `fca3b1fb` | Apr 10 | **2,103**         | full clearance remaining 8 issues                                   |
| `HEAD`     | Apr 10 | **2,103**         | current                                                             |

**The regression is silent because the line-count invariant test (TASK-04-50) from the plan was never added.**

## What happened in the regression

`7d237786` merged `worktree-agent-a0ad1085` into `feat/platform-architecture-convergence`. The worktree branch was based on a **stale pre-slimming base**. The merge conflict in `base_agent.py` resolved by **taking the worktree branch's full 2,000+ LOC version**, wiping out the SPEC-04 slimming that had landed on the target branch one commit earlier.

Representative diff from `git diff 7d237786^1 7d237786^2`:

```diff
-Extension Points (7 total, deprecated in v2.5.0 -- use composition wrappers):
+Extension Points (7 total):
+1. _default_signature() - Override to provide agent-specific signature
+2. _default_strategy() - Override to provide agent-specific strategy
+...
```

The worktree branch restored the pre-deprecation docstring and re-inlined the mixin methods that had been properly extracted to `mcp_mixin.py` and `a2a_mixin.py`. **`class BaseAgent(MCPMixin, A2AMixin, Node)` is still present**, so the file now has duplicated implementations: the inherited mixin methods AND the re-inlined copies that shadow them.

`c9bd9e50` compounded the problem with a second merge. `fca3b1fb` added 15 lines on top as part of the full clearance.

## What the plan assumes vs. what exists

| Plan assumption                                       | Reality on main                                                                   | Drift           |
| ----------------------------------------------------- | --------------------------------------------------------------------------------- | --------------- |
| `base_agent.py` is 2,103 LOC baseline                 | 2,103 LOC (numerical match, different contents)                                   | **Yes**         |
| `_build_messages` method exists to refactor           | Does NOT exist — was removed during slimming                                      | **Yes**         |
| `_DEPRECATED_PARAMETERS` filter exists                | Does NOT exist                                                                    | **Yes**         |
| `_deferred_mcp` tuple exists                          | Does NOT exist — MCP initialization is direct in `__init__`                       | **Yes**         |
| TAOD loop inlined in BaseAgent                        | Extracted to `agent_loop.py` (459 LOC) — but partially re-inlined via regression  | **Yes**         |
| 7 extension points need `@deprecated` applied         | Already applied (commit `1e39a061`), implemented via `_impl` + wrapper pattern    | **Done**        |
| `BaseAgentConfig` is plain dataclass, needs freezing  | Still plain `@dataclass` (not frozen) at `config.py:37`                           | No (still open) |
| 188 subclasses across packages/, examples/, tests/    | 439 raw grep matches, ~189 real subclasses (rest are test stubs / re-exports)     | Partial         |
| `AgentPosture` enum needs creation                    | Exists in `kailash.trust.envelope`; used via `kaizen.trust.postures` shim         | **Done**        |
| `MCPMixin`, `A2AMixin`, `AgentLoop`, `deprecation.py` | All exist (774, 295, 459, 51 LOC respectively)                                    | **Done**        |
| Provider split (SPEC-02 dependency)                   | Done (`providers/` package with llm/, embedding/ subpackages)                     | **Done**        |
| 5 security surfaces §10.1-§10.5 open                  | Only §10.2 and §10.3 confirmably open; §10.1/§10.5 referred to removed structures | **Yes**         |

## Orphaned workspace artifacts

The 53-task plan references three files that **do not exist on main**. They live only on `scrap/pre-triage-snapshot-2026-04-08`:

| Artifact                                                         | Lines | Status            |
| ---------------------------------------------------------------- | ----- | ----------------- |
| `01-analysis/03-specs/04-spec-baseagent-slimming.md`             | 940   | Scrap branch only |
| `01-analysis/01-research/07-baseagent-audit.md`                  | 208   | Scrap branch only |
| `01-analysis/04-adrs/02-adr-baseagent-keeps-node-inheritance.md` | ?     | Scrap branch only |

`workspaces/platform-architecture-convergence/01-analysis/03-specs/` is an **empty directory on main** (contains only `.claude/` and `.env`). Anyone opening the todos file and following the spec reference finds nothing. The snapshot commit `4cd5ef51` lists these as "legitimate SPEC convergence work plus drift plus landmines" — they were classified as drift and never brought forward.

**Disposition needed**: Cherry-pick these files from scrap → main, or decide they're obsolete and rewrite from current state.

## Security surface status (actual, against current code)

| Surface                              | Status                                                                                                                                                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| §10.1 Deferred MCP window            | Concept no longer applies — `_deferred_mcp` doesn't exist. MCP is initialized directly at `base_agent.py:182-224`. Needs re-analysis: is there a mutation window between `__init__` and first `run()`? |
| §10.2 Legacy `**kwargs` catch-all    | **OPEN**. `base_agent.py:133` accepts `**kwargs`, passed to `super().__init__(**kwargs)` at line 263. No allowlist filter.                                                                             |
| §10.3 Posture tampering              | **OPEN**. `config.py:37` is `@dataclass` (not frozen). `config.posture = X` mutation is unguarded.                                                                                                     |
| §10.4 Extension point shadow hooks   | PARTIAL. `_impl` wrapper pattern + `__init_subclass__` warning + `@deprecated` applied. No runtime block.                                                                                              |
| §10.5 `_build_messages` key fallback | N/A — `_build_messages` was removed. If the fallback logic exists elsewhere (AgentLoop or strategy), re-analyze there.                                                                                 |

## What needs to happen next

### Option A — Undo the regression, then resume

**Pros**: Fastest path to <1000 LOC target. The SPEC-04 work actually converged at commit `1e39a061`; we just need to restore that state.

**Cons**: The regression merges also brought in the "full clearance" changes across 33 issues. Restoring base_agent.py to the 994 LOC version would need surgical: take the `1e39a061` base_agent.py, apply only the legitimate fixes from `fca3b1fb`/`c9bd9e50`/`7d237786` that aren't re-inlining. This is not a clean revert.

**Steps**:

1. Extract `base_agent.py` at `1e39a061` (994 LOC) to a reference file
2. Diff against current HEAD (2103 LOC) to identify the 1109 lines of drift
3. Split the drift into (a) legitimate new code, (b) re-inlined methods shadowing mixin methods
4. Delete (b); keep (a)
5. Run full kaizen test suite — any regressions will come from the shadow-method removal
6. Add TASK-04-50 line-count guard test: `assert wc -l base_agent.py < 1000`
7. Close §10.2 (`**kwargs` → allowlist) and §10.3 (freeze config)
8. Restore spec + research + ADR from scrap to main
9. Rewrite `todos/active/05-phase3-baseagent.md` against the new baseline

### Option B — Rewrite the plan from current state

**Pros**: Clean slate. The current code is a hybrid — partially slimmed, partially re-inlined. Treating it as a new baseline gives a cleaner narrative.

**Cons**: Abandons validated work from `626b008b`+`1e39a061`. Re-deliberates decisions already made.

### Recommendation

**Option A**, with the first three steps run as an `/analyze` pass (no code changes) to confirm the diff is surgically separable. If the drift is entangled, fall back to Option B.

## Parallel-merge skill update needed

The codified skill `.claude/skills/30-claude-code-patterns/parallel-merge-workflow.md` (from the prior session's `/codify`) describes the pattern that produced this regression. The skill needs to add:

- **Invariant checks before merge**: for any file being touched by multiple worktree branches, define numeric invariants (line count, method count, specific imports) and verify them after each merge.
- **Stale base detection**: before merging a worktree branch back, check if its merge-base is older than the target branch's latest changes to the same files. If so, rebase the worktree branch first OR explicitly choose which version wins per file.
- **Test the invariant**: the line-count guard test (TASK-04-50) is not a SPEC-04 implementation detail — it is a _category_ of test that every "shrink N by M lines" refactor should add. Generalize it as a skill.

## For Discussion

1. **Is Option A's surgical diff actually feasible?** The 1109-line drift between `1e39a061` (994 LOC) and HEAD (2103 LOC) could be: (a) ~1100 lines of re-inlined mixin methods (easy to remove), or (b) a tangled mix of regression + legitimate fixes (hard to separate). A diff pass will answer this.

2. **Counterfactual: what if the worktree merge had hit a build break instead of a silent line-count regression?** The build would have failed and the merge would have been re-done. A line-count regression has no build signal — it only shows up in a metric that nobody looked at. Should every refactor spec now include a numeric invariant test as a hard requirement, not an optional one?

3. **Why did the full clearance session's codify phase not catch this?** The session journal and skills should have captured "the BaseAgent was slimmed to 994 LOC and then re-grew to 2103". The codify phase ran after the regression had already happened; the skill it produced (`parallel-merge-workflow.md`) didn't include the failure mode that was sitting right in its own commit history.

## See also

- Journal: `workspaces/platform-architecture-convergence/journal/0002-DECISION-spec04-is-the-critical-path.md` (now partially invalidated by this finding)
- Commit `626b008b` — the original slimming (925 LOC)
- Commit `1e39a061` — deprecation + AgentPosture (994 LOC)
- Commit `7d237786` — the regression merge (+1,094 LOC)
- Commit `c9bd9e50` — the second regression merge (+69 LOC)
- Scrap branch `scrap/pre-triage-snapshot-2026-04-08` — orphaned spec/research/ADR files
- Skill `.claude/skills/30-claude-code-patterns/parallel-merge-workflow.md` — describes the pattern that produced the regression
