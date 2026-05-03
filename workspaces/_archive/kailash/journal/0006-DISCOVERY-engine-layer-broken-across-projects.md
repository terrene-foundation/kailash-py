---
type: DISCOVERY
date: 2026-03-30
project: kailash
topic: Engine layer is broken in kailash-py, clean in kailash-rs — feedback from 3 dev teams
phase: analyze
tags: [engine, primitives, kaizen, dataflow, nexus, cross-sdk, P0, agent-api]
---

# Discovery: Engine Layer Broken Across Projects

## What Was Found

Three independent development teams (Arbor, Pact, ImpactVerse) independently reported that the Kailash Python SDK's engine layer is broken or invisible. Investigation confirmed:

1. **kailash-py kaizen-agents Agent API has 3 CRITICAL bugs** (all confirmed in v0.5.0):
   - `AgentResult.error()` doesn't exist (should be `from_error()`) — errors crash
   - Silent success fabrication on failure — masks real errors
   - Tools parameter accepted but never wired to LLM — silently dropped

2. **kailash-py DataFlow Express** is mostly fixed (auto-ID return works, :memory: mitigated) but still async-only.

3. **kailash-rs engine architecture is clean** — all engines compose from primitives correctly. Zero anti-patterns found. This is the reference implementation.

4. **COC artifacts teach only primitives** — the friction gradient is backwards (simplest working API has highest discovery friction).

## Why This Matters

The engine layer is supposed to be the primary developer interface — the thing that makes Kailash productive. Instead:

- Devs are building on Layer 2 primitives (60+ lines of boilerplate per agent)
- When they try to upgrade to engines, the engines are broken
- They fall back to primitives, and the COC reinforces this pattern
- This is a feedback loop that gets worse over time

## Root Cause

The COC artifact gap is a _symptom_. The root cause is that kailash-py's Agent API was left incomplete when the Delegate API was built as its replacement, but the relationship was never clarified and the COC was never updated to route developers to Delegate.

## Consequences

- All downstream projects using Kaizen are building on primitives (BaseAgent) instead of engines (Delegate)
- Agent API is a trap — it accepts tools silently but doesn't use them
- Convention drift: 83+ primitive call sites in pact-platform alone that should be Express
- Developer trust erosion — teams that hit these bugs lose confidence in the engine layer

## Next Steps

P0: Fix the 3 Agent API bugs before any COC changes.
P1: Decide Agent vs Delegate relationship (wrap, deprecate, or fix independently).
P2: Update COC artifacts with three-layer model after engines work.

See: `workspaces/kailash/01-analysis/04-engine-layer-deficiency-report.md` for full analysis.
