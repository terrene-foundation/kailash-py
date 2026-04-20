---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T02:19:56.890Z
author: agent
session_id: 8750886d-8529-44e3-8820-bc2a38b84cdb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: extract oversized rules/orphan-detection.md and rules/agents.md into skill reference files
phase: codify
tags:
  [
    auto-generated,
    codify,
    rules,
    rule-authoring,
    skills,
    orphan-detection,
    agents,
  ]
related_journal: []
---

# DECISION — extract oversized rules into skill reference files

## Commit

`38b6b6cf56fa` — refactor(rules): extract oversized rules into skill reference files

## Body

Both `rules/orphan-detection.md` (was 240 lines) and `rules/agents.md` (was 288 lines) exceeded the 200-line cap in `rule-authoring.md` MUST Rule. Per `cc-artifacts.md` "No knowledge dumps" and `rule-authoring.md` "Rules longer than 200 lines are skimmed; the agent misses load-bearing clauses. Extract reference material into a guide or skill" — moved verbose evidence/counterfactuals/historical post-mortems into two new skill files:

1. `skills/30-claude-code-patterns/worktree-orchestration.md` (167 lines) — full evidence + prompt templates + cross-language notes for the 5 worktree rules AND the reviewer mechanical-sweep rule. Rule file now retains compact MUST/DO/DO NOT + Why + pointer-to-skill.

2. `skills/16-validation-patterns/orphan-audit-playbook.md` (89 lines) — 5-step Detection Protocol, sub-package collection-gate patterns, extended evidence for §1/§2a/§4a/§6. Rule file retains compact MUST/DO/DO NOT + Why + pointer-to-skill.

Final line counts after extraction:

- `rules/orphan-detection.md`: 240 → 190 ✅ under 200
- `rules/agents.md`: 288 → 199 ✅ under 200

Rationale preserved per `rule-authoring.md`:

- Every MUST clause retains a concrete DO/DO NOT example
- Every MUST clause retains its Why: line
- BLOCKED rationalizations retained where load-bearing
- Origin: pointers still present, now reference the skill files
- Skills use progressive disclosure — SKILL.md-equivalent sections for quick reference, sub-sections for full detail

Pre-commit auto-stash bypassed via `core.hooksPath=/dev/null` per `rules/git.md` "Pre-Commit Hook Workarounds" — same pattern as `bb1483b3` (prior codify cycle). TODO in that commit still open.

## For Discussion

1. **Counterfactual**: If the 200-line cap had NOT been enforced and both rules had remained at 240/288 lines, what is the failure mode? The rule-authoring.md rationale says "the agent misses load-bearing clauses" — is this a theoretical risk or has there been an observed session where a bloated rule's load-bearing clause was skipped?

2. **Data-referenced**: The extraction left `rules/agents.md` at exactly 199 lines — one line under cap. The rule-authoring.md cap is 200 lines. Is a 199-line rule effectively the same risk as a 240-line rule, or does the cap reflect a meaningful cognitive boundary? What evidence motivated the 200-line number specifically?

3. **Design**: Skills use "progressive disclosure" per the commit, but the orphan-audit-playbook.md (89 lines) and worktree-orchestration.md (167 lines) are referenced from rules by pointer, not eagerly loaded. A session that triggers the rule file but never reads the skill file gets only the compact MUST/DO/DO NOT. Is the pointer-to-skill pattern sufficient, or does it create a two-tier knowledge gap where agents see the rule but miss the detection protocol?
