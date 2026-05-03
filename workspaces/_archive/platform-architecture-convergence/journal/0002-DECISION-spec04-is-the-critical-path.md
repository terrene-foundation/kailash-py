---
type: DECISION
date: 2026-04-10
created_at: 2026-04-10T16:42:00Z
author: co-authored
session_id: 2026-04-10-full-clearance
session_turn: codify
project: platform-architecture-convergence
topic: SPEC-04 BaseAgent slimming is the critical path blocker for the next 3 convergence phases
phase: codify
tags: [spec-04, spec-05, spec-10, critical-path, base-agent, refactor]
---

# SPEC-04 BaseAgent Slimming is the Critical Path

## Context

At session end (2026-04-10), the red team sweep of active todos produced this convergence progress picture:

| SPEC                          | Status | LOC target | Current      | Blocker                   |
| ----------------------------- | ------ | ---------- | ------------ | ------------------------- |
| SPEC-01 MCP package           | ✓ done |            |              |                           |
| SPEC-02 Provider split        | ~55%   |            |              | #395                      |
| SPEC-03 Composition wrappers  | ✓ done |            |              |                           |
| SPEC-04 BaseAgent slimming    | 0/53   | <1000 LOC  | **2103 LOC** | #392                      |
| SPEC-05 Delegate facade       | 0/30   | ~200 LOC   | 612 LOC      | #393 (blocked by SPEC-04) |
| SPEC-06 Nexus auth            | ✓ done |            |              |                           |
| SPEC-07 Envelope unification  | ✓ done |            |              | (except legacy #398)      |
| SPEC-08 Audit consolidation   | ~40%   |            |              | #396                      |
| SPEC-09 Cross-SDK validation  | ~20%   |            |              | #397                      |
| SPEC-10 Multi-agent migration | 0/40   |            |              | #394 (blocked by SPEC-04) |

## The decision

**Next session focuses exclusively on SPEC-04.** Three reasons:

1. **SPEC-04 is the single largest unblock**. Two other phases (SPEC-05, SPEC-10) depend on it. Finishing SPEC-04 unlocks 70 downstream tasks.
2. **SPEC-04 is the highest-risk phase**. A 2103-line class with 53 planned edits (extractions, behavior changes, security mitigations) is where interaction bugs will be worst. Focused attention beats context-switching.
3. **SPEC-02 and SPEC-08 can run in parallel**. They touch different subsystems (providers, audit stores) and don't depend on SPEC-04. Once SPEC-04 is underway, background agents can fill in SPEC-02 and SPEC-08 tasks without blocking.

## What NOT to work on next session

- **SPEC-05 Delegate facade** — wait for SPEC-04 to land
- **SPEC-10 multi-agent** — wait for SPEC-04 to land
- **SPEC-09 cross-SDK** — 80% remaining and not on critical path; batch with a dedicated cross-SDK session
- **Issues #400, #401, #403** (dependency/mark fixes) — 5-minute fixes, bundle with whatever session is easiest

## SPEC-04 execution plan (sketch)

Based on the 53 tasks in `todos/active/05-phase3-baseagent.md`:

1. **Extract phase** (parallel worktrees — the pattern from 0001-DISCOVERY applies):
   - `agent_loop.py` (already partially extracted, complete it)
   - `message_builder.py`
   - `mcp_handler.py`
   - `posture_validator.py`
   - `config_validator.py`

2. **Slim phase** (single worktree, sequential):
   - Freeze BaseAgentConfig
   - `@deprecated` decorator on extension points
   - `_DEPRECATED_PARAMETERS` filter
   - `_deferred_mcp` tuple guard
   - `_build_messages` signature-first priority
   - Posture-aware validation (strict/moderate/soft)

3. **Verify phase**:
   - Line-count invariant test (`base_agent.py` MUST be < 1000 lines)
   - Subclass regression sweeps
   - Security tests (threat models 10.1-10.5)
   - Full kaizen test suite green

**Estimated**: 1-2 autonomous execution sessions (per rules/autonomous-execution.md 10x multiplier).

## Success criteria

- `wc -l packages/kailash-kaizen/src/kaizen/core/base_agent.py` < 1000
- All extracted modules have Tier 2 integration tests
- `packages/kailash-kaizen/tests/` passes fully
- #392 closed
- SPEC-05 (#393) and SPEC-10 (#394) unblocked

## Rationale archive

The critical path argument is load-bearing. SPEC-04 isn't the most interesting task, but it's the one whose completion unlocks the most other work. Autonomous execution rules (`rules/autonomous-execution.md`) emphasize parallelization where possible, but parallelization requires independent paths. SPEC-04 is the sequential bottleneck that must finish before three other phases can start in parallel.

## See also

- GH #392 (SPEC-04 umbrella issue filed this session)
- `workspaces/platform-architecture-convergence/todos/active/05-phase3-baseagent.md` — full 53-task list
- `.claude/skills/30-claude-code-patterns/parallel-merge-workflow.md` — reusable merge pattern
