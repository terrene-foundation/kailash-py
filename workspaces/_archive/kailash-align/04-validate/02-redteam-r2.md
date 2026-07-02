# Red Team Round 2 — Spec-vs-Implementation Gap Analysis

**Date**: 2026-04-01
**Scope**: Full cross-reference of ALL analysis docs, briefs, plans, and journal entries against implementation
**Agents**: deep-analyst (gap analysis), Explore (cross-workspace check)

## Methodology

Read every file in:

- `workspaces/kailash-align/briefs/` (user input)
- `workspaces/kailash-align/01-analysis/` (16 research docs)
- `workspaces/kailash-align/02-plans/` (implementation plan)
- `workspaces/kailash-align/journal/` (16 journal entries)
- `workspaces/kailash-align/01-analysis/13-red-team-r1.md` through `16-red-team-r3-todos.md`

Cross-referenced against all 17 source files in `packages/kailash-align/src/kailash_align/`.

## Findings Fixed in R2

| ID    | Finding                                                                  | Severity | Fix                                 |
| ----- | ------------------------------------------------------------------------ | -------- | ----------------------------------- |
| R2-01 | `click` not in pyproject.toml — CLI entry point fails at runtime         | CRITICAL | Added `click>=8.0` to dependencies  |
| R2-02 | `httpx` used by bridge.py but not declared                               | HIGH     | Added `httpx>=0.27` to dependencies |
| R2-03 | PPO trainer missing from MethodRegistry — ambiguous omission vs deferral | HIGH     | Registered PPO (12 methods total)   |
| R2-04 | Tests used "ppo" as invalid method example — now valid                   | LOW      | Changed to "nonexistent"            |

## Verified IMPLEMENTED (all spec engines)

All 6 core engines from the overview brief are fully implemented:

1. AdapterRegistry (registry.py) — CRUD + stage transitions
2. AlignmentPipeline (pipeline.py) — generic \_run_training() via MethodRegistry
3. AlignmentEvaluator (evaluator.py) — lm-eval + custom scoring
4. AlignmentServing (serving.py) — GGUF + Ollama + vLLM
5. KaizenModelBridge (bridge.py) — Delegate creation + model discovery
6. OnPremModelCache (onprem.py) — download + verify + air-gap

## Verified DEFERRED (explicitly out of scope)

- 4 Kaizen agents (v1.1) — deterministic logic, not genuine agent reasoning
- local_hf strategy in bridge (v1.1)
- RLVR/DAPO trainers (custom implementation needed)
- kailash-rl (separate package, journal 0016)
- kailash-rs alignment serving crate

## Accepted PARTIAL items (by design)

| Item                                   | Status               | Rationale                                                   |
| -------------------------------------- | -------------------- | ----------------------------------------------------------- |
| AdapterRegistry persistence (DataFlow) | In-memory only       | Acceptable for v1.0 — training session lifecycle            |
| VLLMBackend not wired to pipeline      | TRL handles own vLLM | Standalone backends for user-facing API                     |
| Chat/multi-turn data format            | Not implemented      | TRL auto-detects; users can use transformers chat templates |
| Multi-GPU config surface               | Not exposed          | `accelerate` handles via environment config                 |
| OnPremSetupGuide.generate_checklist()  | Not implemented      | Low priority — CLI covers the workflow                      |

## Cross-workspace Verification

- **kailash-ml**: ModelRegistry contract frozen. Composition pattern shields align from internal changes.
- **kailash-rl**: Separate package, zero dependency on align (journal 0016).
- **kailash-rs**: No alignment capability. Python-only for training.
- **All other workspaces**: No blocking dependencies found.

## R1+R2 Red Team Convergence

| Metric         | R1  | R2  | Total |
| -------------- | --- | --- | ----- |
| CRITICAL found | 2   | 1   | 3     |
| CRITICAL fixed | 2   | 1   | 3     |
| HIGH found     | 5   | 2   | 7     |
| HIGH fixed     | 5   | 2   | 7     |
| Tests          | 388 | 391 | +3    |
| Regressions    | 0   | 0   | 0     |

**CONVERGED**: All actionable findings fixed. No remaining CRITICAL or HIGH issues.
**Final test count**: 391 passed, 1 skipped, 0 regressions.
