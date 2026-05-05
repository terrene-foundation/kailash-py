---
type: DISCOVERY
date: 2026-05-05
created_at: 2026-05-05T00:00:00Z
author: agent
session_id: issue-822-kaizen-typing-cascade
session_turn: /analyze
project: kailash-py / issue-822-kaizen-typing-cascade
topic: _generate_role_based_traits keyword matching violates agent-reasoning.md Rule 1
phase: analyze
tags: [issue-822, agent-reasoning, llm-first, follow-up, kaizen]
---

# DISCOVERY — `_generate_role_based_traits` violates `agent-reasoning.md` Rule 1

**Date:** 2026-05-05
**Phase:** /analyze (red-team Round 1, analyst Dim 7 #1)
**File:** `packages/kailash-kaizen/src/kaizen/core/framework.py:505-528`

## Finding

`Kaizen._generate_role_based_traits(self, role: str) -> List[str]` classifies an
agent role into a default trait list via Python keyword matching:

```python
if any(word in role_lower for word in ["research", "analyze", "study"]):
    return ["thorough", "analytical", "evidence_based", "methodical"]
elif any(word in role_lower for word in ["creative", "design", "innovative"]):
    return ["innovative", "divergent", "imaginative", "flexible"]
elif any(word in role_lower for word in ["lead", "manage", "coordinate", "moderate"]):
    return ["decisive", "communicative", "collaborative", "strategic"]
elif any(word in role_lower for word in ["technical", "develop", "engineer"]):
    return ["precise", "logical", "systematic", "detail_oriented"]
return ["professional", "reliable", "adaptive"]
```

This is a textbook `rules/agent-reasoning.md` Rule 1 BLOCKED pattern:
"Hardcoded classification (`if any(w in text for w in ["help", "support"])`)"
applied to agent input (the `role` string). The classification decides what
behavior traits the agent will be told to embody — this is reasoning that
belongs to the LLM, not to a Python `if/elif` chain.

## Why this surfaced in #822

Cluster B's deep-dive identified the `behavior_traits` dead-branch latent bug
at `framework.py:537-540`. The proposed fix (Shard 1 item 7) assigns
`agent.behavior_traits = specialized_config.get("behavior_traits", [])` —
which is the correct fix for the assignment dead branch.

But the analyst red-team noticed that `_generate_role_based_traits` (the
DEFAULT-provider when no traits are passed) is the keyword-matching
anti-pattern. The Shard 1 fix does NOT touch this method.

## Why out of scope for #822

#822 is scoped to "resolve Optional/None pyright warnings." The keyword-matching
violation is orthogonal — pyright doesn't flag it because it's syntactically
correct Python. The fix requires architectural rework (use a `Signature` that
takes role + returns trait list, route through LLM via `self.run()`),
which is significantly larger than the typing cleanup.

Per `rules/autonomous-execution.md` Rule 1 (≤500 LOC, ≤5–10 invariants,
"describable in 3 sentences"), the LLM-first rewrite is its own shard. Folding
it into #822 violates the shard budget.

## Action

File a follow-up GitHub issue (HUMAN-GATED per `rules/upstream-issue-hygiene.md`)
with the following minimal repro shape:

```
## Affected API
kaizen.Kaizen.create_specialized_agent(role=...) → agent.behavior_traits

## Minimal repro
The role-based default trait derivation in
`kaizen.core.framework._generate_role_based_traits` uses Python keyword
matching to classify role strings into trait lists. This violates the
LLM-first agent-reasoning principle: the classification is a reasoning
step that belongs to the LLM, not to a hardcoded if/elif chain.

## Expected vs actual
Expected: trait derivation goes through a Signature → LLM call.
Actual: hardcoded keyword matching on role substrings.

## Severity
LOW — does not affect runtime correctness, but encodes a brittle
classification that fails on synonyms / multilingual / paraphrased roles.

## Acceptance criteria
- [ ] _generate_role_based_traits replaced with Signature-driven derivation.
- [ ] Tier-2 test: role "machine learning researcher" → trait list contains
      "analytical" or "methodical" (or whatever the LLM returns) — exact
      assertion is on shape, not contents.
- [ ] Existing default-trait callers continue to work (no breaking change).
```

The architecture plan's Open Question #4 surfaces this for the human gate at
`/todos`. Disposition is NOT to land it in #822 — file separately.

## For Discussion

1. **Counterfactual:** if `behavior_traits` had been opt-in only (no default
   derivation when user passes no traits), would `_generate_role_based_traits`
   exist at all? Is the LLM-first rewrite valuable or should we simplify by
   removing the default-derivation entirely?
2. **Specific data:** 4 keyword buckets (`research/analyze/study`,
   `creative/design/innovative`, `lead/manage/coordinate/moderate`,
   `technical/develop/engineer`) + 1 default bucket. Roles like
   `"investigator"`, `"strategist"`, `"data scientist"`, `"product manager"`
   all fall to the default bucket and lose role-specific traits. How often
   does this manifest in production agent behavior?
3. **Scope discipline:** moving this out of #822 follows shard-budget
   discipline, but does it risk the LLM-first follow-up never landing? Per
   `rules/autonomous-execution.md` Rule 4 (fix-immediately when same bug
   class), this isn't same-bug-class as the typing fixes — different rule
   axis. Defer is correct, but a tracking-issue without a deadline still has
   landing-risk.

## References

- `rules/agent-reasoning.md` MUST Rule 1 — LLM-First For All Agent Decisions
- `framework.py:505-528` — current keyword-matching implementation
- `02-plans/01-architecture.md` § Open Questions #4
- `04-validate/01-redteam-round-1.md` Dim 7 #1
