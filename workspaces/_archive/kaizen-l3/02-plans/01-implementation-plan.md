# L3 Implementation Plan

## Execution Model

Per `rules/autonomous-execution.md`: autonomous agent execution with 10x multiplier. Estimated at **3-5 autonomous sessions** across parallel agent deployment.

## Phase 0: Remediation (Blocking — Must Complete First)

**Session 1a** (parallel with Phase 0b)

### 0a: Blocking Items (B1-B5)

All must complete before any L3 implementation.

| Item | What                                           | Where                         | Acceptance                                                                                                |
| ---- | ---------------------------------------------- | ----------------------------- | --------------------------------------------------------------------------------------------------------- |
| B1   | Add optional `envelope` field to `AgentConfig` | `kaizen/agent_config.py`      | Optional field, None default, serialization round-trip                                                    |
| B2   | Harmonize checkpoint data model                | `kaizen/core/autonomy/state/` | Add `parent_checkpoint_id`, `pending_actions`, `completed_actions`, `workflow_state`                      |
| B3   | ~~DOWNGRADED to PREPARATORY~~ (per F-23)       | —                             | B3 IS Spec 02 work. Full ScopedContext is Phase 1b, not a Phase 0 blocker.                                |
| B4   | Extend MessageType with L3 variants            | A2A module or new module      | **6 variants per Brief 03** (F-02 fix): Delegation, Status, Clarification, Completion, Escalation, System |
| B5   | Add `AgentInstance` struct                     | New module in kaizen          | Lifecycle state enum (6 states), valid transitions, instance_id                                           |

### 0b: Preparatory Items (P1-P7)

Can parallel with 0a. Should complete before L3 integration testing.

| Item | What                                  | Where                                           |
| ---- | ------------------------------------- | ----------------------------------------------- |
| P1   | Mark enums as forward-compatible      | Document contract for consumers                 |
| P2   | Fix RoutingCondition::Regex           | Verify Python equivalent behavior               |
| P3   | Rename LlmDecision                    | Check if Python has equivalent                  |
| P4   | Fix SupervisorAgent depth race        | Verify Python depth tracking                    |
| P5   | Make topological_sort public          | Check `composition/dag_validator.py` visibility |
| P6   | Add metadata field to A2A messages    | A2A module                                      |
| P7   | Forward-compatible struct annotations | Document Python construction contracts          |

**Note**: P2, P3, P4 need verification — they reference Rust-specific issues. Check if Python equivalents exist.

## Phase 1: Foundation Primitives (Parallelizable)

**Session 2** (deploy 3 agents in parallel)

### 1a: EnvelopeTracker + EnvelopeSplitter + EnvelopeEnforcer

**Module**: `packages/kailash-kaizen/src/kaizen/l3/envelope/`

```
kaizen/l3/
  __init__.py
  envelope/
    __init__.py
    tracker.py      # EnvelopeTracker
    splitter.py     # EnvelopeSplitter
    enforcer.py     # EnvelopeEnforcer
    types.py        # GradientZone, CostEntry, BudgetRemaining, DimensionUsage, etc.
    errors.py       # SplitError, TrackerError
```

**Implementation order**:

1. Types (dataclasses for all 14 spec types)
2. EnvelopeSplitter (stateless, easiest to test)
3. EnvelopeTracker (stateful, thread-safe, atomic recording)
4. EnvelopeEnforcer (composition of tracker + strict enforcer + hold queue)

**Test vectors**: 6 conformance vectors from spec, plus edge cases.

### 1b: ScopedContext (PARALLEL with 1a)

**Module**: `packages/kailash-kaizen/src/kaizen/l3/context/`

```
kaizen/l3/context/
  __init__.py
  scope.py         # ContextScope
  projection.py    # ScopeProjection with glob matching
  types.py         # ContextValue, DataClassification, MergeResult, etc.
  errors.py        # ContextError variants
```

**Implementation order**:

1. Types (DataClassification mapping to PACT levels, ContextValue, ScopeProjection)
2. ScopeProjection (glob pattern matching with deny precedence)
3. ContextScope (hierarchical tree: create_child, get, set, remove, visible_keys, snapshot, merge)
4. Root factory method

**Test vectors**: 8+ conformance vectors from spec.

### 1c: Inter-Agent Messaging (AFTER 1a EnvelopeEnforcer)

**Module**: `packages/kailash-kaizen/src/kaizen/l3/messaging/`

```
kaizen/l3/messaging/
  __init__.py
  types.py          # MessageType L3 variants, all 6 payload types
  envelope.py       # MessageEnvelope transport wrapper
  channel.py        # MessageChannel (bounded async)
  router.py         # MessageRouter (envelope-aware routing)
  dead_letters.py   # DeadLetterStore (bounded ring buffer)
  errors.py         # RoutingError, ChannelError
```

**Implementation order**:

1. Types (payload dataclasses, Priority, EscalationSeverity)
2. MessageEnvelope
3. MessageChannel (asyncio.Queue-based bounded channel)
4. DeadLetterStore (collections.deque with maxlen)
5. MessageRouter (8-step validation, directionality checks)

**Test vectors**: 7 conformance vectors from spec.

## Phase 2: Agent Lifecycle (After Phase 1a + 1c)

**Session 3**

### 2a: AgentFactory + AgentInstanceRegistry

**Module**: `packages/kailash-kaizen/src/kaizen/l3/factory/`

```
kaizen/l3/factory/
  __init__.py
  spec.py           # AgentSpec dataclass
  instance.py       # AgentInstance, AgentState, WaitReason, TerminationReason
  registry.py       # AgentInstanceRegistry (thread-safe)
  factory.py        # AgentFactory (spawn, terminate, cascade)
  errors.py         # FactoryError variants
```

**Implementation order**:

1. Types (AgentState enum + state machine, WaitReason, TerminationReason)
2. AgentSpec
3. AgentInstance
4. AgentInstanceRegistry (with lineage/spec indexes)
5. AgentFactory (spawn with 8 preconditions, terminate with cascade)
6. EATP record mapping integration

**Test vectors**: 9+ conformance vectors from spec.

## Phase 3: Plan Execution (After All of Phase 1-2)

**Session 4-5**

### 3a: Plan DAG + PlanValidator + PlanExecutor

**Module**: `packages/kailash-kaizen/src/kaizen/l3/plan/`

```
kaizen/l3/plan/
  __init__.py
  types.py           # Plan, PlanNode, PlanEdge, PlanState, PlanNodeState, etc.
  validator.py       # PlanValidator (structural + envelope + resource)
  executor.py        # PlanExecutor (gradient-driven scheduling)
  modification.py    # PlanModification variants + apply logic
  events.py          # PlanEvent variants
  errors.py          # PlanError, ValidationError, ExecutionError
```

**Implementation order**:

1. Types (Plan, PlanNode, PlanEdge, PlanState, PlanNodeState, EdgeType)
2. PlanGradient (reuse PACT GradientEngine)
3. PlanValidator (reuse dag_validator.py for cycle detection, add envelope checks)
4. PlanModification (7 typed mutations with validation)
5. PlanExecutor (execution loop, gradient classification, suspension/cancellation)
6. PlanEvent emission

**Test vectors**: 12 conformance vectors from spec.

## Phase 4: Integration & Red Team

**Session 5** (continuation)

1. Integration tests across all primitives
2. Cross-primitive wiring (Factory → Router for channel setup, Executor → Factory for spawning)
3. Red team with security-reviewer for:
   - NaN/Inf injection across all boundaries
   - State machine transition fuzzing
   - Concurrent budget allocation races
   - Cascade termination ordering
   - Dead letter store capacity eviction
4. EATP record completeness audit

## Module Structure Summary

```
packages/kailash-kaizen/src/kaizen/l3/
  __init__.py              # L3 public API
  envelope/                # Spec 01: Budget tracking + enforcement
    tracker.py
    splitter.py
    enforcer.py
    types.py
    errors.py
  context/                 # Spec 02: Hierarchical scoped context
    scope.py
    projection.py
    types.py
    errors.py
  messaging/               # Spec 03: Inter-agent messaging
    types.py
    envelope.py
    channel.py
    router.py
    dead_letters.py
    errors.py
  factory/                 # Spec 04: Agent factory + registry
    spec.py
    instance.py
    registry.py
    factory.py
    errors.py
  plan/                    # Spec 05: Plan DAG execution
    types.py
    validator.py
    executor.py
    modification.py
    events.py
    errors.py
```

## Testing Strategy

Per `rules/testing.md` — 3-tier approach, NO MOCKING in Tiers 2-3.

| Tier                 | What                        | Approach                                                                              |
| -------------------- | --------------------------- | ------------------------------------------------------------------------------------- |
| Tier 1 (Unit)        | Each primitive in isolation | Spec conformance test vectors + edge cases. Mock external dependencies only.          |
| Tier 2 (Integration) | Cross-primitive wiring      | Factory + Router + Enforcer working together. Real objects, no mocks.                 |
| Tier 3 (E2E)         | Full delegation chain       | Root agent spawns children, delegates tasks, collects results through plan execution. |

## Session Estimate

| Phase                 | Sessions | Notes                                              |
| --------------------- | -------- | -------------------------------------------------- |
| Phase 0 (Remediation) | 1        | Mostly small changes, parallel across items        |
| Phase 1 (Foundation)  | 1-2      | 3 parallel agent streams                           |
| Phase 2 (Factory)     | 1        | Sequential due to dependency on Phase 1            |
| Phase 3 (Plan DAG)    | 1-2      | Most complex single primitive                      |
| Phase 4 (Integration) | 1        | Red team + integration                             |
| **Total**             | **4-6**  | With autonomous 10x multiplier: ~2-3 calendar days |
