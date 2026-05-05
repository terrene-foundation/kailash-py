# DECISION — Sync `create_specialized_agent` constrains the implementation shape

**Date:** 2026-05-06
**Phase:** /todos
**Status:** Recorded

## Decision

Implementation uses `BaseAgent.run()` (sync) inside the existing sync
`Kaizen.create_specialized_agent`. Rejected three alternatives:

- **Option B** — make `create_specialized_agent` async. Rejected: every
  existing caller (production + 8 test files) breaks. Acceptance criterion #3
  ("no breaking change to `agent.behavior_traits` shape" — interpreted broadly
  as no breaking change to the create-call signature either) forbids this.
- **Option C** — companion async method `create_specialized_agent_async`.
  Rejected: doubles the public API surface, leaves the Rule 1 violation in the
  sync path. Exact "both shapes" anti-pattern called out in `rules/patterns.md`
  Paired Public Surface — Consistent Async-ness.
- **Option D** — pre-derive at Kaizen init for a hardcoded role taxonomy.
  Rejected: still hardcoded classification (which roles exist), moves the Rule
  1 violation up one level. Also fails on novel roles.

## Trade-offs accepted

1. **First-call latency cost.** Every novel role triggers one LLM round-trip at
   `create_specialized_agent` time. Subsequent identical roles return from
   cache instantly. For most applications this is fine because agent creation
   is a setup-time concern — but a workload that creates many specialized
   agents with diverse roles in a hot path will pay the LLM cost upfront.
   The escape hatch is the existing `behavior_traits=[...]` config arg.

2. **Failure-mode change.** Previous: silent default-trait list when role
   matched no keyword bucket. New: `RuntimeError` when LLM is unavailable.
   This is observable to callers and warrants a minor version bump (2.20.0
   per todo 1.7).

3. **Test cost.** Tier-1 unit tests that previously called
   `create_specialized_agent(name=X, role=Y, config={})` and got deterministic
   keyword-classifier output now need to either supply explicit
   `behavior_traits` (preferred — keeps Tier-1 fast and deterministic) or
   migrate to Tier-2 (real LLM). Todo 1.4 sweeps this.

## Why this matters

The decision is load-bearing: it determines all 9 todos in the active list.
Every todo (the Signature module, the cache, the test sweep, the spec section
on failure modes, the CHANGELOG migration text) flows from the choice to keep
the surface sync. Reversing this decision later means re-doing all of them.

## Connections

- `rules/patterns.md` Paired Public Surface — Consistent Async-ness — directly
  invoked rejecting Option C.
- `rules/agent-reasoning.md` Rule 1 — invariant the chosen design satisfies.
- `01-analysis/01-research/02-design-options.md` — full option-by-option
  analysis with the rejected designs explained.
- `01-analysis/02-risks-and-edges.md` Risk 1 — failure-mode disposition.
