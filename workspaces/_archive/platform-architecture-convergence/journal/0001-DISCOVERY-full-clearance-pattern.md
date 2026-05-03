---
type: DISCOVERY
date: 2026-04-10
created_at: 2026-04-10T16:40:00Z
author: co-authored
session_id: 2026-04-10-full-clearance
session_turn: codify
project: platform-architecture-convergence
topic: full clearance of 30 GH issues in a single session via parallel agent waves + strategic merge
phase: codify
tags:
  [
    convergence,
    parallel-agents,
    worktree-merge,
    issue-clearance,
    pact,
    ml,
    kaizen,
  ]
---

# Full Clearance Pattern — 30 Issues in One Session

## What happened

Starting state: 30 open GH issues, 13 active todo files in platform-architecture-convergence, 73 uncommitted files from a prior parallel-agent session, 5 PACT agents had independently modified `engine.py` in separate worktrees.

Ending state: Zero open issues, two atomic commits (`090c0e97`, `fca3b1fb`), 5742 trust tests passing, 900+ new tests added.

## The pattern

**1. Wave structure**. Issues grouped into 4 clearance waves by complexity and dependency:

- Wave 0: Bugs + framework fixes (Wave 0, Trust/PACT bug cluster)
- Wave 1: Quick fixes in parallel (Gemini, Ollama pair, API parity tooling)
- Wave 2: Medium complexity (shim package, FabricIntegrity, N6 conformance)
- Wave 3: Largest feature (OntologyRegistry)

Each wave launched 3-4 agents via `run_in_background: true` — they worked independently while the main session continued committing Wave 0 and merging previous work.

**2. Merge strategy for parallel engine.py edits**. The 5 PACT features (N1-N5) were implemented in 5 separate worktrees that all modified `engine.py`. Resolution:

- `git show HEAD:engine.py > /tmp/engine_head.py` to capture common base
- `diff -u /tmp/engine_head.py .claude/worktrees/agent-XXX/.../engine.py > feature.patch` per worktree
- Hand all 5 diffs + injection-point documentation to a pact-specialist agent
- Specialist applies changes section by section using Edit, not `patch` (patch can't handle line drift from 5 concurrent features)
- Interaction points (e.g., both N2 and N5 adding code to `grant_clearance`) documented explicitly in the merge brief
- Result: 1192 PACT tests passed on first merged run

**3. Test-driven verification between waves**. After each wave, run only the tests affected by that wave. Run the full `tests/trust/` suite only after all merges to catch interaction bugs. This found 17 failures from the #386 posture rename that needed per-test updates.

**4. Commit discipline**. Two logical commits instead of 30 per-issue commits:

- `feat(platform): full clearance — 33 issues, PACT N1-N5, 8 ML engines` (Waves 0+3)
- `feat(platform): resolve remaining 8 issues — full clearance complete` (Waves 1+2)

Smaller commits would have created 30 review surfaces with high interdependency. Bundling kept review coherent.

## What made this work

- **Parallel agent background launch**. Agents ran in parallel with `run_in_background: true`, freeing the main session to do merges and commits while they worked.
- **Specialist delegation for complex merges**. The pact-specialist owned the engine.py merge end-to-end because it understood the PACT architecture.
- **Explicit injection-point documentation**. When delegating the merge, listed exactly which imports, init params, fields, and methods each N-feature needed.
- **Fail-closed merge order**. Features were merged in N1 → N2 → N3 → N4 → N5 order, matching the specification sequence, so any interaction bugs surfaced at the expected layer.

## Where this pattern applies next

- **SPEC-04 (BaseAgent slimming, #392)**: 53 tasks that touch the same 2103-line file. This is exactly the pattern for parallel worktree specialist delegation. Extract modules to `agent_loop.py`, `message_builder.py`, `mcp_handler.py`, `posture_validator.py` in parallel worktrees, then merge via a kaizen-specialist who understands BaseAgent's internal dependencies.
- **SPEC-05 (Delegate facade, #393)**: Smaller scope but depends on SPEC-04. Single-agent composition rewrite, no merge complexity.
- **SPEC-10 (multi-agent, #394)**: 7 patterns × wrapper migration. One agent per pattern in parallel, central reviewer at the end.

## Counter-examples (when NOT to use this pattern)

- Small fixes (1-2 files, single concern) — overhead of wave structure exceeds the benefit
- Cross-package refactors where the merge surface is unbounded — prefer sequential work
- When the tests are slow (> 5 min) — feedback loop is too long to detect interaction bugs between waves

## See also

- `.claude/skills/30-claude-code-patterns/parallel-merge-workflow.md` — the reusable how-to
- Commits `090c0e97`, `fca3b1fb`
- GH issues #341-348, #351, #357, #360, #365, #366, #369, #370, #371, #373, #374, #375, #377, #380-385, #386, #388, #389, #390 (all closed)
