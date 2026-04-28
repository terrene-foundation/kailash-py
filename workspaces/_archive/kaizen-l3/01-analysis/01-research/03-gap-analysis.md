# Gap Analysis — What Needs to Be Built

## Summary

The existing Python codebase provides ~60% of the infrastructure L3 needs. The governance layer (PACT) is the strongest foundation — envelope algebra, gradient evaluation, and enforcement patterns exist. The agent framework (Kaizen) provides autonomy, composition, and coordination foundations. The primary gaps are in continuous budget tracking, hierarchical context scoping, typed messaging, runtime agent spawning, and DAG execution.

## Gap Classification

### Green = Direct Reuse (no changes)

| Capability                     | Existing Component                     | Status   |
| ------------------------------ | -------------------------------------- | -------- |
| 5-dimension envelope model     | `ConstraintEnvelopeConfig`             | Complete |
| Envelope intersection          | `intersect_envelopes()`                | Complete |
| Monotonic tightening checks    | `MonotonicTighteningError`             | Complete |
| NaN/Inf validation on numerics | `_validate_finite()`                   | Complete |
| Gradient zone evaluation       | `GradientEngine` + `VerificationLevel` | Complete |
| D/T/R positional addressing    | `Address` in `addressing.py`           | Complete |
| Knowledge clearance levels     | `ConfidentialityLevel` (C0-C4)         | Complete |
| Frozen governance context      | `GovernanceContext`                    | Complete |
| EATP audit anchors             | `audit.py`                             | Complete |
| Per-action strict enforcement  | `StrictEnforcer`                       | Complete |
| Delegation chain management    | `chain.py`                             | Complete |

### Yellow = Extend/Adapt (modify existing)

| Capability                 | Existing                                 | Gap                                                                    | Effort |
| -------------------------- | ---------------------------------------- | ---------------------------------------------------------------------- | ------ |
| AgentConfig envelope field | `AgentConfig` dataclass                  | Add optional `envelope` field (B1)                                     | Small  |
| Budget tracking            | `BudgetTracker` (financial only)         | Extend to multi-dimension + reclamation                                | Medium |
| Agent state tracking       | State in autonomy subsystem              | Formalize 6-state machine with valid transitions                       | Medium |
| MessageType enum           | Not defined as extensible enum in Python | Add L3 variants (Delegation, Status, etc.) + forward-compat annotation | Small  |
| DAG validation             | `dag_validator.py`                       | Extend with PlanNode/PlanEdge types + envelope checks                  | Medium |
| Checkpoint model           | Checkpointing config in AgentConfig      | Add parity fields: parent_checkpoint_id, pending_actions, etc. (B2)    | Medium |
| A2A message metadata       | Likely no metadata field                 | Add optional metadata to message type (P6)                             | Small  |
| GovernanceVerdict          | String-based `level`                     | Consider enum-based GradientZone for type safety                       | Small  |

### Red = Build New

| Capability                | Spec | Complexity | Description                                                                                                                |
| ------------------------- | ---- | ---------- | -------------------------------------------------------------------------------------------------------------------------- |
| **EnvelopeTracker**       | 01   | High       | Multi-dimension budget tracking with atomic recording, child allocation, reclamation, gradient zone transitions            |
| **EnvelopeSplitter**      | 01   | Medium     | Stateless budget division with ratio validation, tightening checks                                                         |
| **EnvelopeEnforcer**      | 01   | High       | Non-bypassable middleware combining StrictEnforcer + EnvelopeTracker + HoldQueue                                           |
| **ScopedContext**         | 02   | High       | Hierarchical context tree with projection-based read/write access, classification filtering, parent traversal, child merge |
| **ScopeProjection**       | 02   | Medium     | Glob pattern matching with deny-precedence for key access control                                                          |
| **ContextValue**          | 02   | Small      | Value wrapper with provenance (written_by, classification, timestamp)                                                      |
| **L3 Message Payloads**   | 03   | Medium     | 6 typed payloads (Delegation, Status, Clarification, Completion, Escalation, System)                                       |
| **MessageEnvelope**       | 03   | Small      | Transport wrapper with TTL and typed payloads                                                                              |
| **MessageChannel**        | 03   | Medium     | Bounded async point-to-point channel with backpressure                                                                     |
| **MessageRouter**         | 03   | High       | Envelope-aware routing with 8-step validation, directionality checks                                                       |
| **DeadLetterStore**       | 03   | Small      | Bounded ring buffer for undeliverable messages                                                                             |
| **AgentSpec**             | 04   | Small      | Instantiation blueprint dataclass                                                                                          |
| **AgentInstance**         | 04   | Medium     | Running agent entity with lifecycle state machine                                                                          |
| **AgentInstanceRegistry** | 04   | Medium     | Thread-safe registry with lineage/spec indexes                                                                             |
| **AgentFactory**          | 04   | High       | spawn/terminate with 8-precondition validation, cascade termination, budget accounting                                     |
| **Plan**                  | 05   | Medium     | DAG container with PlanNode, PlanEdge, PlanState                                                                           |
| **PlanValidator**         | 05   | Medium     | Structure + envelope + resource validation                                                                                 |
| **PlanExecutor**          | 05   | Very High  | DAG scheduling, gradient-driven failure handling, suspension/cancellation                                                  |
| **PlanModification**      | 05   | Medium     | 7 typed mutations with atomic validation                                                                                   |

## Effort Distribution

```
Remediation (00):     ████████░░░░░░░░░░░░  ~15%
Envelope (01):        ████████████░░░░░░░░  ~25%
ScopedContext (02):   ██████░░░░░░░░░░░░░░  ~15%
Messaging (03):       ████████░░░░░░░░░░░░  ~20%
AgentFactory (04):    ██████░░░░░░░░░░░░░░  ~15%
Plan DAG (05):        ████████████████░░░░  ~30% (but parallelizable with 01-04)
```

Note: Percentages are relative effort within L3 scope, not absolute. Total exceeds 100% because some work is parallelizable.

## Critical Path

```
B1 (envelope on config) ─┐
B4 (message types)      ─┤
P1 (non-exhaustive)     ─┼─► EnvelopeTracker (01) ─┐
B2 (checkpoint parity)  ─┘                          │
                                                     ├─► AgentFactory (04) ──► Plan DAG (05)
ScopedContext (02) ──────────────────────────────────┤
                                                     │
                          EnvelopeEnforcer (01) ─────┤
                                                     │
                          MessageRouter (03) ────────┘
```

ScopedContext (02) is on a parallel path — can start immediately without waiting for remediation.

## Risk Areas

1. **Thread safety**: EnvelopeTracker, AgentInstanceRegistry, and MessageRouter all require thread-safe concurrent access. Python's GIL helps but async code still needs proper locking.

2. **Atomic operations**: CostEntry recording, budget allocation, state transitions all require atomicity. Need threading.Lock or asyncio.Lock patterns.

3. **Cascade termination**: Depth-first leaf-first termination across potentially deep hierarchies. Must handle partial failures and budget reclamation ordering.

4. **Plan modification during execution**: Hot modifications to a running DAG while agents are active. Must serialize modifications, re-validate invariants, and handle running-node protection.

5. **Cross-primitive integration**: Each primitive is well-specified in isolation, but the integration points (Factory calling Router for channel setup, Executor using Factory for spawning, Router using Enforcer for validation) require careful wiring.
