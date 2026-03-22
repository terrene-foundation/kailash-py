# L3 Autonomy Primitives — Overview

L3 enables agents that spawn child agents, allocate constrained budgets, communicate through typed channels, and execute dynamic task graphs — all under PACT governance.

## Five Primitives

| Primitive                         | Module                | Purpose                                                                    |
| --------------------------------- | --------------------- | -------------------------------------------------------------------------- |
| EnvelopeTracker/Splitter/Enforcer | `kaizen.l3.envelope`  | Continuous budget tracking, division, non-bypassable enforcement           |
| ScopedContext                     | `kaizen.l3.context`   | Hierarchical context with projection-based access control + classification |
| MessageRouter/Channel             | `kaizen.l3.messaging` | Typed inter-agent messaging with routing validation                        |
| AgentFactory/Registry             | `kaizen.l3.factory`   | Runtime agent spawning with lifecycle state machine                        |
| PlanValidator/Executor            | `kaizen.l3.plan`      | DAG task graphs with gradient-driven failure handling                      |

## Key Principle: SDK Boundary

All L3 primitives are **deterministic** — no LLM calls. The orchestration layer (kaizen-agents) decides WHAT to do; the SDK validates and enforces.

## Quick Import

```python
from kaizen.l3 import (
    EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer, GradientZone, Verdict,
    ContextScope, ScopeProjection, DataClassification, ContextValue,
    MessageRouter, MessageChannel, MessageEnvelope, DeadLetterStore, MessageType,
    AgentFactory, AgentInstance, AgentInstanceRegistry, AgentSpec,
    Plan, PlanValidator, PlanExecutor, apply_modification, apply_modifications,
)
```

## Architecture Decisions

- `asyncio.Lock` for all shared state (overrides threading.Lock per AD-L3-04)
- Custom dot-segment matcher for projections (not fnmatch per AD-L3-13)
- `frozen=True` for value types, mutable for entity types (AD-L3-15)
- GradientZone reuses VerificationLevel enum (AD-L3-02)
- Callback-based PlanExecutor (agent spawning is orchestration concern)

## Specs Reference

See `workspaces/kaizen-l3/briefs/` for full specifications.
See `docs/00-authority/l3-autonomy-primitives.md` for authority documentation.
