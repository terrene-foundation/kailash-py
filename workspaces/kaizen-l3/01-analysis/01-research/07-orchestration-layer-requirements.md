# Orchestration Layer Requirements — kaizen-agents Package

## 1. Executive Summary

The L3 SDK primitives (kailash-kaizen v2.1.0) provide deterministic, conformance-tested enforcement for autonomous agent systems. What remains is the **LLM-dependent orchestration layer** — the components that decide WHAT to do (while the SDK enforces HOW constraints are respected).

The specs define a clean, principled boundary:

- **SDK (kailash-kaizen)**: Validates, enforces, tracks. No LLM. Deterministic. Conformance-testable.
- **Orchestration (kaizen-agents)**: Decides, composes, diagnoses, recovers. Requires LLM. Non-deterministic. Quality-testable.

This document catalogs every orchestration-layer responsibility extracted from the six L3 specs.

---

## 2. Component Inventory

### 2.1 Plan Generation Pipeline

These components transform a high-level objective into an executable Plan DAG.

| Component             | Source Spec                   | Input                                                | Output                                       | LLM Role                                             |
| --------------------- | ----------------------------- | ---------------------------------------------------- | -------------------------------------------- | ---------------------------------------------------- |
| **TaskDecomposer**    | 05, Appendix A                | Objective (string), parent envelope                  | List of subtasks with descriptions           | Semantic understanding of goals                      |
| **PlanComposer**      | 05, Appendix A                | Subtasks, available AgentSpecs                       | Plan DAG (nodes, edges, input mappings)      | Wiring decisions, parallelism strategy               |
| **AgentDesigner**     | 04, Appendix A                | Subtask description, tool inventory, parent envelope | AgentSpec (tool_ids, capabilities, envelope) | Tool selection, capability matching, envelope sizing |
| **EnvelopeAllocator** | 04, Appendix A; 01, Section 9 | Parent envelope, list of child requirements          | Per-child ConstraintEnvelope allocations     | Estimating resource needs per subtask                |
| **PlanEvaluator**     | 05, Appendix A                | Plan DAG, original objective                         | Pass/fail with semantic feedback             | "Will this plan achieve the objective?"              |

**Pipeline Flow**:

```
Objective
  -> TaskDecomposer -> [subtasks]
  -> AgentDesigner -> [AgentSpecs per subtask]
  -> EnvelopeAllocator -> [envelopes per spec]
  -> PlanComposer -> Plan DAG
  -> PlanValidator (SDK) -> structural check
  -> PlanEvaluator -> semantic check
  -> PlanExecutor (SDK) -> execution
```

### 2.2 Failure Recovery

These components handle failures that the SDK's gradient system escalates to HELD status.

| Component            | Source Spec    | Trigger                                      | Input                                         | Output                                             |
| -------------------- | -------------- | -------------------------------------------- | --------------------------------------------- | -------------------------------------------------- |
| **FailureDiagnoser** | 05, Appendix A | NodeHeld event from PlanExecutor             | Failed node event, agent logs, envelope state | Diagnosis: retryable / recoverable / fatal         |
| **Recomposer**       | 05, Appendix A | FailureDiagnoser output + current plan state | PlanModification or escalation recommendation | Recovery strategy (retry, replace, reroute, abort) |

**Integration Point**: PlanExecutor emits `NodeHeld` events. The orchestration layer subscribes to these events and has `gradient.resolution_timeout_seconds` (default 300s) to respond with a PlanModification before the hold auto-escalates to BLOCKED.

### 2.3 Communication Protocols

These are interaction patterns built on the SDK's typed messaging infrastructure.

| Protocol                  | Source Spec    | Messages Used                        | LLM Role                                  |
| ------------------------- | -------------- | ------------------------------------ | ----------------------------------------- |
| **DelegationProtocol**    | 03, Appendix B | Delegation -> Status\* -> Completion | Compose task_description, select priority |
| **ClarificationProtocol** | 03, Appendix B | Clarification (request/response)     | Judge ambiguity, formulate answers        |
| **EscalationProtocol**    | 03, Appendix B | Escalation -> recovery action        | Diagnose failure, plan recovery           |
| **CompletionProtocol**    | 03, Appendix B | Completion with context_updates      | Validate result quality                   |

**Key Contract**: The SDK (MessageRouter) validates WHETHER a message CAN be sent (envelope, channel, TTL). The orchestration layer composes WHAT the message says.

### 2.4 Content & Classification

| Component                  | Source Spec    | Input                                        | Output                     | LLM Role                                   |
| -------------------------- | -------------- | -------------------------------------------- | -------------------------- | ------------------------------------------ |
| **ClassificationAssigner** | 02, Section 10 | Data value + context                         | DataClassification (C0-C4) | Content-aware sensitivity assessment       |
| **CapabilityMatcher**      | 04, Appendix A | Subtask description, agent capabilities list | Best-matching agent(s)     | Semantic matching beyond string comparison |
| **ResultAggregator**       | 05, Appendix A | Leaf node outputs (Map<PlanNodeId, Value>)   | Unified result             | Synthesis of multiple outputs              |

---

## 3. Invariants the Orchestration Layer Must Respect

The orchestration layer is free to make decisions, but those decisions must pass through SDK validation. These are the constraints:

### 3.1 Envelope Invariants

- **INV-PLAN-06**: Sum of all node envelopes cannot exceed parent envelope (financial dimension)
- **INV-PLAN-07**: Every node envelope must be tighter than parent on every dimension
- **I-01**: Child envelope <= parent active envelope on all 5 dimensions
- **I-05**: Child tool_ids must be subset of parent's allowed tools
- **I-07**: Parent must have remaining budget >= child allocation

### 3.2 Structural Invariants

- **INV-PLAN-01**: Plan DAG must be acyclic
- **INV-PLAN-02**: All edge references must point to existing nodes
- **INV-PLAN-05**: Plan must have at least one node
- **I-09**: Delegation depth cannot exceed max_depth from any ancestor

### 3.3 Lifecycle Invariants

- **I-02**: Cascade termination is automatic — orchestration layer cannot prevent it
- **I-04**: parent_id is immutable — no lineage rewriting
- **I-06**: State machine transitions are validated — no invalid transitions

### 3.4 Message Invariants

- Communication envelope limits recipient set
- TTL expiration is enforced at routing time
- Dead letters are captured, not silently dropped

---

## 4. SDK API Surface for Orchestration Layer

The orchestration layer consumes these SDK APIs:

### 4.1 Plan Lifecycle

```python
# Create and validate
plan = Plan(plan_id=..., envelope=parent_envelope, gradient=gradient, nodes={}, edges=[])
errors = PlanValidator.validate_structure(plan)
errors = PlanValidator.validate_envelopes(plan)

# Execute
events = PlanExecutor.execute(plan, node_callback=spawn_and_run_agent)

# Modify during execution
result = apply_modification(plan, AddNode(...))
result = apply_modifications(plan, [modification_list])

# Control
PlanExecutor.suspend(plan)
PlanExecutor.resume(plan)
PlanExecutor.cancel(plan)
```

### 4.2 Agent Lifecycle

```python
# Spawn
instance = AgentFactory.spawn(child_spec, parent_envelope, parent_id)

# State management
AgentFactory.update_state(instance_id, AgentState.Running())
AgentFactory.update_state(instance_id, AgentState.Completed(result=...))

# Termination
AgentFactory.terminate(instance_id, TerminationReason.ExplicitTermination(by=caller_id))

# Queries
children = AgentFactory.children_of(parent_id)
ancestors = AgentFactory.lineage(instance_id)
descendants = AgentFactory.all_descendants(instance_id)
```

### 4.3 Messaging

```python
# Send typed messages
router.route(MessageEnvelope(
    from_agent=parent_id,
    to_agent=child_id,
    message_type=MessageType.DELEGATION,
    payload=DelegationPayload(task_description=..., context_snapshot=..., envelope=..., priority=...),
    ttl=300
))

# Channel management (auto-created at spawn)
channel = router.get_channel(parent_id, child_id)
```

### 4.4 Context

```python
# Create child scope
child_scope = parent_scope.create_child(
    scope_id=...,
    read_projection=ScopeProjection(allow_patterns=["project.*"], deny_patterns=["project.secrets.*"]),
    write_projection=ScopeProjection(allow_patterns=["review.*"]),
    effective_clearance=DataClassification.RESTRICTED
)

# Merge results back
merge_result = parent_scope.merge_child_results(child_scope, conflict_resolution=ConflictResolution.LAST_WRITER_WINS)
```

### 4.5 Envelope

```python
# Split budget
child_envelopes = EnvelopeSplitter.split(parent_envelope, allocations=[...])

# Track consumption
verdict = tracker.record_consumption(CostEntry(action="llm_call", dimension="financial", cost=0.05, ...))

# Reclaim on completion
reclaim_result = tracker.reclaim(child_tracker)
```

---

## 5. Cross-Primitive Integration Points

The orchestration layer must coordinate across all 5 SDK primitives simultaneously. These are the integration seams:

| Integration          | What Happens                                     | Orchestration Responsibility                                   |
| -------------------- | ------------------------------------------------ | -------------------------------------------------------------- |
| Factory + Envelope   | Spawn deducts budget; termination reclaims       | Choose allocation ratios                                       |
| Factory + Context    | required_context_keys validated at spawn         | Decide which keys child needs                                  |
| Factory + Messaging  | Channels created at spawn, closed at termination | Compose message content                                        |
| Plan + Factory       | PlanExecutor spawns agents per node              | Provide node_callback that wires Factory + Context + Messaging |
| Plan + Envelope      | Budget summation validated; per-node tracking    | Allocate budgets across plan nodes                             |
| Context + Completion | Child writes to scope; completion merges back    | Decide merge strategy, handle conflicts                        |

---

## 6. Open Design Questions

These are decisions that must be made before implementation:

1. **Package boundary**: Separate PyPI package or subpackage of kailash-kaizen?
2. **LLM abstraction**: Use Kaizen signatures or direct LLM calls?
3. **Event consumption model**: How does the orchestration layer subscribe to PlanExecutor events?
4. **Protocol state machines**: Are protocols explicit state machines or callback-based?
5. **Testing strategy**: How to test LLM-dependent components deterministically?
6. **Existing pattern migration**: Do the 11 L0-L2 patterns get L3 equivalents, or do they coexist?
