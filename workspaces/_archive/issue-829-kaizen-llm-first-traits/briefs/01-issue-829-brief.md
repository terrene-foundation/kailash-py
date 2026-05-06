# Brief — Issue #829: kaizen LLM-first trait derivation

**Source:** github.com/terrene-foundation/kailash-py/issues/829 (filed 2026-05-05)
**Origin:** Follow-up from #822 todo 3.4 (`workspaces/issue-822-kaizen-typing-cascade/todos/completed/3.4-llm-first-traits-followup-issue.md`)

## Problem

`Kaizen._generate_role_based_traits(self, role: str) -> List[str]` at
`packages/kailash-kaizen/src/kaizen/core/framework.py:505-528` uses Python keyword
matching to classify role strings into trait lists:

```python
if any(word in role_lower for word in ["research", "analyze", "study"]):
    return ["thorough", "analytical", "evidence_based", "methodical"]
elif any(word in role_lower for word in ["creative", "design", "innovative"]):
    return ["innovative", "divergent", "imaginative", "flexible"]
# ...
```

This violates `rules/agent-reasoning.md` Rule 1 (BLOCKED — hardcoded
classification of agent input). The trait derivation is reasoning the LLM should
do, not a Python `if/elif` chain.

## Affected API

`kaizen.Kaizen.create_specialized_agent(role=...) -> agent.behavior_traits`

## Expected vs actual

**Expected:** trait derivation goes through a `Signature` → LLM call (e.g.,
`RoleToTraitsSignature(role: str) -> traits: List[str]`).

**Actual:** hardcoded keyword matching on role substrings. Fails on synonyms
(`"investigator"` → no match → default traits), multilingual roles, paraphrased
roles, novel domains.

## Severity

**LOW** — does not affect runtime correctness for roles matching the hardcoded
keywords. Fails silently with default traits for everything else, which encodes
a brittle classification users cannot extend without modifying SDK source.

## Acceptance criteria (from issue body)

- [ ] `_generate_role_based_traits` replaced with `Signature`-driven derivation.
- [ ] Tier-2 test: role `"machine learning researcher"` → trait list contains
      LLM-derived traits (assertion on shape, not exact contents).
- [ ] Tier-2 test: existing default-trait callers (e.g., role `"data analyst"`)
      continue to work — no breaking change to `agent.behavior_traits` shape.
- [ ] Spec updated at `specs/kaizen-core.md` § Agent class to document the new
      derivation contract.

## Constraints

- **Stay in lane**: kailash-py only (kailash-rs / loom out-of-scope per
  `rules/repo-scope-discipline.md`).
- **LLM-first**: solution MUST go through `self.run()` (or async equivalent)
  on a `Signature` — NOT pre-filtering, dispatch tables, or keyword fallbacks
  per `rules/agent-reasoning.md` MUST Rule 1–3.
- **Backwards compatibility**: `agent.behavior_traits` shape (list of strings)
  is the public surface; downstream callers MUST NOT need to change.
- **Caching**: per-Kaizen-instance cache keyed by role string. First call for a
  given role hits the LLM; subsequent identical roles return cached traits.
  Cache lives on the `Kaizen` instance (cleared when instance is GC'd); no
  cross-instance persistence.
- **Determinism**: LLM call uses `temperature=0` (or provider equivalent) so
  per-role output is stable within a process run. Combined with the cache
  above, a given Kaizen instance will return identical traits for identical
  roles for its full lifetime.

## Tech stack

- Backend: kailash-kaizen (current PyPI: 2.19.0)
- AI: Kaizen `Signature` system, BaseAgent
- Tests: pytest 3-tier (Tier 2 against real LLM provider per `rules/testing.md`)

## Users

- SDK users calling `Kaizen.create_specialized_agent(role="...")` — trait
  derivation should generalize to any role description, not just the 8 hardcoded
  keyword groups.

## Out of scope

- Sibling hardcoded methods in `framework.py` — strict scope to
  `_generate_role_based_traits` only. If `/analyze` finds direct invariant
  dependencies (e.g., another method that consumes the cached traits), surface
  them as a finding for a separate follow-up issue rather than expanding the
  shard.
- Other `agent-reasoning.md` Rule 1 violations elsewhere in kaizen — those get
  their own issues if found, per repo-scope-discipline (one fix per PR).
