# kaizen-agents Package Brief

## What This Is

kaizen-agents is the PACT-governed L3 orchestration package. It consumes kailash-kaizen L3 primitives and adds LLM-driven intelligence: task decomposition, plan composition, failure diagnosis, recovery, inter-agent protocols, and governance enforcement.

## Three-Layer Architecture

- **kailash-kaizen** (this monorepo, `packages/kailash-kaizen/`) — L0-L3 primitives, no LLM calls
- **kaizen-agents** (this monorepo, `packages/kaizen-agents/`) — L3 orchestration, LLM-driven
- **kaizen-cli-py** (separate repo, `terrene-foundation/kaizen-cli-py`) — CLI binary, thin shell

Boundary rule: Does it require an LLM? If yes → kaizen-agents. If no → kailash-kaizen.

## Current State

Code was moved from the standalone `kaizen-agents` repo. Ground truth audit (doc 01) found:

- Zero SDK imports — all code uses local type stubs instead of `kaizen.l3`
- Planner (decomposer, designer, composer) — real LLM logic, wrong types
- Recovery (diagnoser, recomposer) — real LLM logic, wrong types
- Protocols (delegation, clarification, escalation) — real LLM composition, no message transport
- PlanMonitor — async execution loop, admits to being a stub in its own docstring
- Governance — empty
- Audit — empty

## What Needs to Happen

1. **Fix SDK prerequisites** — kailash-kaizen is async-first, so PlanExecutor must be async, HELD must be a real state, Signatures must support structured output. These are SDK bugs, not design constraints.
2. **Wire kaizen-agents to real SDK** — replace local types with `kaizen.l3` imports
3. **Add message transport** — wire protocol implementations to SDK MessageRouter
4. **Build governance** — PACT enforcement, EATP audit trail, D/T/R accountability
5. **Red team to convergence**

## Constraints

- Apache 2.0, Terrene Foundation
- Uses CARE, PACT, EATP, CO standards
- kailash SDK is async-first — orchestration layer must use async SDK primitives
- No workarounds for SDK bugs — fix them in the SDK (same monorepo)
