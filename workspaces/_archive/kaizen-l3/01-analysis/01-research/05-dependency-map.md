# Dependency Map — Spec-to-Spec and Code Dependencies

## Spec-to-Spec Dependencies

```
Brief 00: L0-L2 Remediation
  │
  ├─► B1 (AgentConfig.envelope) ──────────────► Spec 01, 04
  ├─► B2 (Checkpoint parity) ─────────────────► Spec 05 (plan checkpointing)
  ├─► B3 (ContextScope in SDK) ───────────────► Spec 02
  ├─► B4 (MessageType L3 variants) ───────────► Spec 03
  └─► B5 (AgentInstance struct) ──────────────► Spec 04

Spec 01: EnvelopeTracker/Splitter/Enforcer
  Dependencies IN:
    - ConstraintEnvelopeConfig (PACT config.py) — envelope type
    - StrictEnforcer (trust enforce/strict.py) — per-action checks
    - HoldQueue (trust-plane or PACT) — held action queue
    - GradientEngine (PACT gradient.py) — zone evaluation
    - BudgetTracker (trust constraints/budget_tracker.py) — financial tracking foundation
  Dependencies OUT:
    → Spec 03 (MessageRouter uses EnvelopeEnforcer for communication validation)
    → Spec 04 (AgentFactory uses EnvelopeTracker for budget accounting at spawn)
    → Spec 05 (PlanExecutor uses EnvelopeTracker per plan node)

Spec 02: ScopedContext
  Dependencies IN:
    - DataClassification / ConfidentialityLevel (PACT clearance.py) — classification levels
  Dependencies OUT:
    → Spec 04 (AgentFactory validates required_context_keys at spawn)
    → Spec 03 (DelegationPayload carries context_snapshot; CompletionPayload carries context_updates)

Spec 03: Inter-Agent Messaging
  Dependencies IN:
    - Spec 01 EnvelopeEnforcer — communication constraint validation
    - Spec 04 AgentInstanceRegistry — recipient state lookup
    - Existing A2AMessage + MessageBus — transport foundation
  Dependencies OUT:
    → Spec 04 (Factory creates channels at spawn; closes at termination)
    → Spec 05 (PlanExecutor uses Delegation/Completion messages for plan nodes)

Spec 04: AgentFactory + Registry
  Dependencies IN:
    - Spec 01 EnvelopeTracker — budget accounting at spawn/reclaim
    - Spec 01 EnvelopeSplitter — child envelope creation
    - Spec 02 ScopedContext — context key validation at spawn
    - Spec 03 MessageRouter — channel setup at spawn
    - B1 AgentConfig.envelope — envelope on config
    - B5 AgentInstance struct — lifecycle types
  Dependencies OUT:
    → Spec 05 (PlanExecutor spawns agents for plan nodes via Factory)

Spec 05: Plan DAG
  Dependencies IN:
    - Spec 01 EnvelopeTracker — per-node budget tracking
    - Spec 02 ScopedContext — context scoping for plan nodes
    - Spec 03 MessageRouter — delegation/completion messaging
    - Spec 04 AgentFactory — agent spawning for plan nodes
    - Existing dag_validator.py — cycle detection (P5: make public)
  Dependencies OUT:
    (None — Plan DAG is the capstone primitive)
```

## Code-to-Code Dependencies (Python-specific)

```
packages/kailash-kaizen/src/kaizen/l3/
  ├── envelope/
  │     ├── types.py
  │     │     imports: pact.governance.config (ConstraintEnvelopeConfig, VerificationLevel)
  │     │     imports: pact.governance.envelopes (intersect_envelopes)
  │     ├── tracker.py
  │     │     imports: kaizen.l3.envelope.types (CostEntry, BudgetRemaining, GradientZone, Verdict)
  │     │     imports: pact.governance.gradient (GradientEngine)
  │     │     imports: kailash.trust.constraints.budget_tracker (BudgetTracker) [optional foundation]
  │     ├── splitter.py
  │     │     imports: kaizen.l3.envelope.types (AllocationRequest, SplitError)
  │     │     imports: pact.governance.envelopes (intersect_envelopes, check_degenerate_envelope)
  │     └── enforcer.py
  │           imports: kaizen.l3.envelope.tracker (EnvelopeTracker)
  │           imports: kailash.trust.enforce.strict (StrictEnforcer)
  │           imports: (HoldQueue — location TBD)
  │
  ├── context/
  │     ├── types.py
  │     │     imports: pact.governance.clearance (ConfidentialityLevel / DataClassification mapping)
  │     ├── projection.py
  │     │     imports: fnmatch (stdlib)
  │     └── scope.py
  │           imports: kaizen.l3.context.types (ContextValue, DataClassification)
  │           imports: kaizen.l3.context.projection (ScopeProjection)
  │
  ├── messaging/
  │     ├── types.py
  │     │     imports: kaizen.l3.envelope.types (GradientZone)
  │     │     imports: pact.governance.config (ConstraintEnvelopeConfig)
  │     ├── channel.py
  │     │     imports: asyncio (Queue)
  │     ├── dead_letters.py
  │     │     imports: collections (deque)
  │     └── router.py
  │           imports: kaizen.l3.messaging.channel (MessageChannel)
  │           imports: kaizen.l3.messaging.dead_letters (DeadLetterStore)
  │           imports: kaizen.l3.envelope.enforcer (EnvelopeEnforcer)
  │           imports: kaizen.l3.factory.registry (AgentInstanceRegistry)
  │
  ├── factory/
  │     ├── spec.py
  │     │     imports: pact.governance.config (ConstraintEnvelopeConfig)
  │     ├── instance.py
  │     │     imports: kaizen.l3.envelope.tracker (EnvelopeTracker)
  │     ├── registry.py
  │     │     imports: kaizen.l3.factory.instance (AgentInstance)
  │     └── factory.py
  │           imports: kaizen.l3.factory.spec (AgentSpec)
  │           imports: kaizen.l3.factory.instance (AgentInstance, AgentState)
  │           imports: kaizen.l3.factory.registry (AgentInstanceRegistry)
  │           imports: kaizen.l3.envelope.tracker (EnvelopeTracker)
  │           imports: kaizen.l3.envelope.splitter (EnvelopeSplitter)
  │           imports: kaizen.l3.messaging.router (MessageRouter)
  │           imports: kaizen.l3.context.scope (ContextScope)
  │
  └── plan/
        ├── types.py
        │     imports: kaizen.l3.factory.spec (AgentSpec)
        │     imports: kaizen.l3.envelope.types (GradientZone, PlanGradient)
        ├── validator.py
        │     imports: kaizen.l3.plan.types (Plan, PlanNode, PlanEdge)
        │     imports: kaizen.composition.dag_validator (topological_sort)
        │     imports: pact.governance.envelopes (intersect_envelopes)
        ├── executor.py
        │     imports: kaizen.l3.plan.types (Plan, PlanState, PlanNodeState, PlanEvent)
        │     imports: kaizen.l3.factory.factory (AgentFactory)
        │     imports: kaizen.l3.envelope.tracker (EnvelopeTracker)
        └── modification.py
              imports: kaizen.l3.plan.types (PlanModification, Plan, PlanNode, PlanEdge)
              imports: kaizen.l3.plan.validator (PlanValidator)
```

## Import Cycle Risk

No import cycles exist in the proposed structure:

- `envelope/` → PACT/trust (external, no back-reference)
- `context/` → PACT clearance (external, no back-reference)
- `messaging/` → `envelope/` + `factory/registry` (one-way)
- `factory/` → `envelope/` + `messaging/router` + `context/` (one-way)
- `plan/` → `factory/` + `envelope/` (one-way)

The dependency flow is strictly: `envelope` → `context` → `messaging` → `factory` → `plan`. No cycles.
