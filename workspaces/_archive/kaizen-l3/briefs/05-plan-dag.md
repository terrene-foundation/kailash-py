# L3 Primitive Specification: Plan DAG + PlanValidator + PlanExecutor + PlanModification

## Status

Specification — Ready for Implementation

## Dependencies

This is the most complex L3 primitive. It depends on all four others:

- **EnvelopeTracker** (spec 01) — budget tracking during plan execution
- **ScopedContext** (spec 02) — context scoping for spawned plan nodes
- **Inter-Agent Messaging** (spec 03) — communication between plan nodes
- **AgentFactory** (spec 04) — spawning agents for plan nodes

---

## 1. Overview

The Plan DAG replaces rigid orchestration strategies (Sequential, Parallel, Hierarchical, Pipeline) with a dynamic, modifiable task graph. A Plan is a directed acyclic graph of PlanNodes connected by PlanEdges, where each node represents an agent to be spawned and each edge represents a dependency between agents.

PlanValidator performs all structural and envelope feasibility checks deterministically -- no LLM required.

PlanExecutor schedules nodes for execution according to the DAG topology and uses PACT's verification gradient for failure handling. The gradient is configuration from the PACT envelope, set by the supervisor. The executor classifies failures into gradient zones (auto-approved, flagged, held, blocked) deterministically. It does NOT decide how to recover -- that is the orchestration layer's responsibility.

PlanModification provides typed mutations for runtime plan changes. Modifications are validated against DAG invariants and envelope constraints before application.

**The boundary rule**: PlanValidator, PlanExecutor, and PlanModification are SDK primitives (no LLM). Plan generation (TaskDecomposer, PlanComposer), plan evaluation (PlanEvaluator), and failure recovery (FailureDiagnoser, Recomposer) live in the orchestration layer (kaizen-agents) because they require LLM judgment.

---

## 2. Types

### Plan

A directed acyclic graph of agent tasks with dependency edges. The plan is the unit of L3 execution.

```
Plan:
  plan_id:     UniqueId          -- generated at creation
  name:        String            -- human-readable plan name
  envelope:    ConstraintEnvelope -- parent envelope bounding the entire plan
  gradient:    PlanGradient      -- verification gradient config (from PACT envelope)
  nodes:       Map<PlanNodeId, PlanNode>
  edges:       List<PlanEdge>
  state:       PlanState
  created_at:  Timestamp
  modified_at: Timestamp
```

### PlanNode

A single task within the plan, mapped to an AgentSpec to be spawned.

```
PlanNode:
  node_id:       PlanNodeId      -- unique within the plan
  agent_spec:    AgentSpec       -- blueprint for the agent to execute this node
  input_mapping: Map<String, PlanNodeOutput> -- which predecessor outputs feed into this node
  state:         PlanNodeState
  instance_id:   Option<UniqueId> -- populated once agent is spawned (None before execution)
  optional:      Boolean         -- if true, failure uses optional_node_failure gradient zone
  retry_count:   Integer         -- number of retries attempted so far (starts at 0)
```

### PlanNodeOutput

A reference to a specific output from another node.

```
PlanNodeOutput:
  source_node: PlanNodeId       -- the node that produces this output
  output_key:  String           -- the key within that node's output map
```

### PlanEdge

A directed dependency between two nodes.

```
PlanEdge:
  from:      PlanNodeId
  to:        PlanNodeId
  edge_type: EdgeType
```

### EdgeType

```
EdgeType:
  | DataDependency         -- `to` cannot start until `from` completes successfully
  | CompletionDependency   -- `to` cannot start until `from` completes (regardless of outcome)
  | CoStart                -- `to` starts when `from` starts (soft coordination dependency)
```

Semantics:

- **DataDependency**: The strongest edge. If `from` fails, `to` cannot execute (it depends on `from`'s output). `to` accesses `from`'s output via input_mapping.
- **CompletionDependency**: `to` waits for `from` to reach a terminal state (Completed, Failed, or Skipped). Used when `to` needs to run after `from` regardless of outcome (e.g., cleanup nodes).
- **CoStart**: `to` is eligible to start as soon as `from` starts. Used for resource coordination where two nodes should execute concurrently. Does not block `to` if `from` has not started yet -- it is advisory.

### PlanState

```
PlanState:
  | Draft                                -- being composed, not yet validated
  | Validated                            -- passed all PlanValidator checks
  | Executing                            -- at least one node is running
  | Completed { results: Map<PlanNodeId, Value> }  -- all required nodes completed
  | Failed { failed_nodes: List<PlanNodeId> }      -- plan cannot continue
  | Suspended                            -- paused; no new nodes spawn, running nodes continue
  | Cancelled                            -- terminated; all running agents are terminated
```

State transitions:

```
Draft -> Validated              (PlanValidator.validate succeeds)
Draft -> Draft                  (modifications applied while drafting)
Validated -> Executing          (PlanExecutor.execute called)
Validated -> Draft              (modification applied after validation)
Executing -> Completed          (all required nodes completed)
Executing -> Failed             (unrecoverable failure per gradient)
Executing -> Suspended          (PlanExecutor.suspend called)
Executing -> Cancelled          (PlanExecutor.cancel called)
Suspended -> Executing          (PlanExecutor.resume called)
Suspended -> Cancelled          (PlanExecutor.cancel called)
```

No transitions from Completed, Failed, or Cancelled. These are terminal states.

### PlanNodeState

```
PlanNodeState:
  | Pending                              -- waiting for dependencies to complete
  | Ready                                -- all dependencies met, awaiting execution slot
  | Running                              -- agent spawned and executing
  | Completed { output: Value }          -- agent finished successfully
  | Failed { error: String }             -- agent failed (may be retried per gradient)
  | Skipped { reason: String }           -- removed from execution without failure
```

Node state transitions:

```
Pending -> Ready                (all incoming DataDependency sources Completed;
                                 all incoming CompletionDependency sources terminal;
                                 all incoming CoStart sources at least Running or terminal)
Pending -> Skipped              (upstream DataDependency failed and node was not required, or SkipNode modification)
Ready -> Running                (agent spawned by PlanExecutor)
Running -> Completed            (agent returned successfully)
Running -> Failed               (agent returned error or envelope violation)
Failed -> Running               (retry within budget -- gradient auto-approved)
Failed -> Skipped               (gradient: optional_node_failure is auto-approved or flagged)
```

### PlanGradient

Verification gradient configuration for plan execution. Set by the supervisor via the PACT envelope. This is configuration data, not policy -- the SDK reads it and executes deterministically.

```
PlanGradient:
  retry_budget:              Integer        -- max retries before escalation (default: 2)
  after_retry_exhaustion:    GradientZone   -- what to do when retries are spent (default: Held)
  resolution_timeout_seconds: Integer       -- how long to wait for held resolution (default: 300)
  optional_node_failure:     GradientZone   -- how to handle optional node failures (default: Flagged)
  budget_flag_pct:           Float          -- budget consumption % that triggers flagged (default: 0.80)
  budget_hold_pct:           Float          -- budget consumption % that triggers held (default: 0.95)
```

Invariant: `budget_flag_pct < budget_hold_pct`. Validated at construction time.

Invariant: `after_retry_exhaustion` must be Held or Blocked (not AutoApproved or Flagged -- exhausted retries on a required node cannot be silently skipped).

Invariant: Envelope violations are always Blocked. This is not a configurable field -- it is a hard invariant of the system.

### GradientZone

```
GradientZone:
  | AutoApproved    -- proceed without intervention
  | Flagged         -- proceed, but log for review
  | Held            -- pause downstream nodes, wait for resolution
  | Blocked         -- terminate the plan branch, cascade to dependents
```

### PlanEvent

Events emitted during plan execution. Every state transition produces at least one event.

```
PlanEvent:
  | NodeReady     { node_id: PlanNodeId }
  | NodeStarted   { node_id: PlanNodeId, instance_id: UniqueId }
  | NodeCompleted  { node_id: PlanNodeId, output: Value }
  | NodeFailed     { node_id: PlanNodeId, error: String, retryable: Boolean }
  | NodeRetrying   { node_id: PlanNodeId, attempt: Integer, max_attempts: Integer }
  | NodeHeld       { node_id: PlanNodeId, reason: String, zone: GradientZone }
  | NodeBlocked    { node_id: PlanNodeId, dimension: String, detail: String }
  | NodeSkipped    { node_id: PlanNodeId, reason: String }
  | NodeFlagged    { node_id: PlanNodeId, reason: String }
  | PlanCompleted  { results: Map<PlanNodeId, Value> }
  | PlanFailed     { failed_nodes: List<PlanNodeId>, reason: String }
  | PlanSuspended  { }
  | PlanResumed    { }
  | PlanCancelled  { }
  | EnvelopeWarning { node_id: PlanNodeId, dimension: String, usage_pct: Float, zone: GradientZone }
  | ModificationApplied { modification: PlanModification, timestamp: Timestamp }
```

### PlanModification

Typed mutations that preserve audit trail. Each modification is a first-class value, not an ad-hoc edit.

```
PlanModification:
  | AddNode     { node: PlanNode, edges: List<PlanEdge> }
  | RemoveNode  { node_id: PlanNodeId }
  | ReplaceNode { old_node_id: PlanNodeId, new_node: PlanNode }
  | AddEdge     { edge: PlanEdge }
  | RemoveEdge  { from: PlanNodeId, to: PlanNodeId }
  | UpdateSpec  { node_id: PlanNodeId, new_spec: AgentSpec }
  | SkipNode    { node_id: PlanNodeId, reason: String }
```

---

## 3. Behavioral Invariants

These invariants MUST hold in any conforming implementation. They are the specification -- not guidelines.

### Structural Invariants

**INV-PLAN-01: Acyclicity.** The plan graph is always a DAG. No sequence of edges may form a cycle. Validated at construction time (PlanValidator) and re-validated after every modification.

**INV-PLAN-02: Referential Integrity.** Every edge references nodes that exist in the plan. Every input_mapping references a source_node that exists and has an outgoing edge (DataDependency or CompletionDependency) to the referencing node.

**INV-PLAN-03: Root Existence.** A valid plan has at least one root node (a node with no incoming DataDependency or CompletionDependency edges). CoStart edges do not contribute to root/leaf determination.

**INV-PLAN-04: Leaf Existence.** A valid plan has at least one leaf node (a node with no outgoing DataDependency or CompletionDependency edges).

**INV-PLAN-05: Non-Empty.** A valid plan has at least one node. Empty plans (zero nodes) are rejected by PlanValidator.

### Envelope Invariants

**INV-PLAN-06: Budget Summation.** The sum of all node envelopes (Financial dimension) does not exceed the plan's parent envelope. Formally: `sum(node.agent_spec.envelope.financial for node in plan.nodes) <= plan.envelope.financial`.

**INV-PLAN-07: Monotonic Tightening.** Each node's envelope is tighter than the plan's parent envelope on every dimension. Formally: for every dimension d and every node n, `n.agent_spec.envelope[d] <= plan.envelope[d]`, using the per-dimension intersection rules from PACT Section 5.3.

**INV-PLAN-08: Envelope Violations Are Blocked.** If any node's action violates its envelope, the result is always GradientZone.Blocked. This is non-configurable. No gradient setting can override it.

### Execution Invariants

**INV-PLAN-09: Event Completeness.** PlanExecutor emits at least one PlanEvent for every state transition of every node and of the plan itself. No state transition is silent.

**INV-PLAN-10: Suspension Semantics.** A suspended plan does not spawn new nodes. Nodes already in Running state continue to execute. New Ready transitions are queued but not executed until resume.

**INV-PLAN-11: Cancellation Semantics.** A cancelled plan terminates all Running agents (via AgentFactory cascade termination). Pending and Ready nodes transition to Skipped with reason "plan_cancelled". No further events are emitted after PlanCancelled except terminal node events from agents that were mid-termination.

**INV-PLAN-12: Gradient Determinism.** Every gradient zone classification made by PlanExecutor is deterministic given the same PlanGradient configuration and event sequence. No randomness, no LLM consultation.

### Modification Invariants

**INV-PLAN-13: Atomic Validation.** Every PlanModification is validated against all structural and envelope invariants before application. If validation fails, the plan is unchanged (no partial application).

**INV-PLAN-14: Batch Atomicity.** apply_modifications(plan, list) applies all modifications or none. If any single modification in the batch would violate an invariant (considering all preceding modifications in the batch), the entire batch is rejected.

**INV-PLAN-15: Running Node Protection.** RemoveNode and ReplaceNode on a Running node result in a Held or Blocked decision (implementation chooses, but it must not silently terminate a running agent). UpdateSpec on a Running node is rejected -- the agent has already been spawned from the original spec.

---

## 4. Operations

### PlanValidator

All checks are deterministic. No LLM required.

#### validate_structure(plan) -> Result<(), List<ValidationError>>

Checks:
1. **Cycle detection**: Topological sort of the DAG. If topological sort fails, report the cycle.
2. **Referential integrity**: Every edge's `from` and `to` exist in plan.nodes. Every input_mapping's source_node exists in plan.nodes.
3. **Input mapping consistency**: For every input_mapping entry, there exists a DataDependency or CompletionDependency edge from the source_node to the referencing node.
4. **Root existence**: At least one node has no incoming DataDependency or CompletionDependency edges.
5. **Leaf existence**: At least one node has no outgoing DataDependency or CompletionDependency edges.
6. **Node count**: At least one node exists.
7. **Unique node IDs**: No duplicate PlanNodeIds.
8. **Self-edges**: No edge where `from == to`.

Returns all errors found (not just the first).

#### validate_envelopes(plan) -> Result<(), List<ValidationError>>

Checks:
1. **Budget summation**: Sum of node.agent_spec.envelope.financial across all nodes does not exceed plan.envelope.financial.
2. **Per-node tightening**: Each node.agent_spec.envelope is tighter than plan.envelope on every dimension, using PACT per-dimension intersection rules.
3. **Temporal feasibility**: For the critical path (longest chain of DataDependency edges), the sum of temporal constraints allows completion within the plan's temporal window.

#### validate_resources(plan) -> Result<(), List<ValidationError>>

Checks:
1. **Concurrency limits**: The maximum parallel fan-out (nodes that could execute simultaneously) does not exceed the plan's operational concurrency limit (if specified in the envelope).
2. **Per-node resource requirements**: Each node's operational constraints are satisfiable within the plan's operational envelope.

#### validate(plan) -> Result<(), List<ValidationError>>

Runs validate_structure, validate_envelopes, and validate_resources. Returns the union of all errors. If no errors, transitions plan.state from Draft to Validated.

### PlanExecutor

Executes a validated plan by spawning agents according to the DAG. Uses the verification gradient for failure handling.

#### execute(plan) -> Stream<PlanEvent>

Precondition: plan.state is Validated (or Executing for resume scenarios).

Execution loop:
1. Identify all Ready nodes (dependencies satisfied).
2. For each Ready node, spawn an agent via AgentFactory using the node's agent_spec.
3. Emit NodeStarted. Store instance_id on the node.
4. Wait for any running node to complete or fail.
5. On completion or failure, classify via the verification gradient (see Section 6).
6. Update node state, emit appropriate PlanEvent.
7. Re-evaluate which nodes are now Ready.
8. Repeat until no nodes are Ready and no nodes are Running.
9. If all required nodes are Completed, emit PlanCompleted.
10. If any required node is in a terminal failure state (Failed or Blocked with no recovery), emit PlanFailed.

#### suspend(plan) -> Result<(), ExecutionError>

Precondition: plan.state is Executing.

Behavior:
- Set plan.state to Suspended.
- Stop spawning new agents for Ready nodes.
- Running nodes continue to execute (they are not interrupted).
- Emit PlanSuspended.

Error: Returns error if plan.state is not Executing.

#### resume(plan) -> Result<(), ExecutionError>

Precondition: plan.state is Suspended.

Behavior:
- Set plan.state to Executing.
- Resume spawning agents for Ready nodes (including any that became Ready during suspension).
- Emit PlanResumed.

Error: Returns error if plan.state is not Suspended.

#### cancel(plan) -> Result<(), ExecutionError>

Precondition: plan.state is Executing or Suspended.

Behavior:
- Terminate all Running agents via AgentFactory cascade termination.
- Transition all Pending and Ready nodes to Skipped with reason "plan_cancelled".
- Set plan.state to Cancelled.
- Emit PlanCancelled.

Error: Returns error if plan.state is terminal (Completed, Failed, Cancelled).

#### apply_modification(plan, modification) -> Result<(), PlanError>

Behavior:
1. Validate the modification against all invariants (structural, envelope, running-node protection).
2. If valid, apply the modification to the plan.
3. If the plan was Validated, transition back to Draft (re-validation required before new execution). If Executing, re-validate in-place (the executor must handle hot modifications).
4. Emit ModificationApplied.
5. Re-evaluate Ready nodes (a modification may unblock held nodes or create new Ready nodes).

Error: Returns error if the modification would violate any invariant.

### PlanModification Semantics

#### AddNode { node, edges }

- Adds a new node to the plan.
- Adds all provided edges.
- Node must have a unique node_id (not already in plan).
- All edges must reference existing nodes or the new node.
- Must not create a cycle.
- New node starts in Pending state.
- Node's envelope must satisfy tightening invariant against plan envelope.

#### RemoveNode { node_id }

- Removes the node and all edges referencing it (incoming and outgoing).
- Only valid if node is in Pending, Ready, or Skipped state.
- If node is Running, the modification is Held (per INV-PLAN-15).
- If node is Completed, removal is valid (the output remains available for downstream nodes that already consumed it, but the node is removed from the plan's active set).

#### ReplaceNode { old_node_id, new_node }

- Removes old_node_id and adds new_node in its place.
- All edges that referenced old_node_id now reference new_node.node_id.
- old_node must be in Pending, Ready, Failed, or Skipped state. Running is Held per INV-PLAN-15.
- new_node starts in Pending state.
- new_node's envelope must satisfy tightening invariant.

#### AddEdge { edge }

- Adds a new edge between existing nodes.
- Must not create a cycle.
- Both from and to must exist in the plan.

#### RemoveEdge { from, to }

- Removes the edge between from and to.
- If no such edge exists, returns an error.
- May cause downstream nodes to become Ready (if the removed edge was their only unsatisfied dependency).

#### UpdateSpec { node_id, new_spec }

- Updates the agent_spec of the specified node.
- Only valid if node is in Pending or Ready state (not Running -- the agent was already spawned from the old spec).
- new_spec's envelope must satisfy tightening invariant.
- Budget summation must still hold with the new spec.

#### SkipNode { node_id, reason }

- Transitions the node to Skipped state with the given reason.
- Valid for Pending and Ready nodes.
- Running nodes: Held per INV-PLAN-15.
- Downstream nodes with DataDependency on this node are also evaluated: if they are required, they are Held. If optional, they may be Skipped.
- Removes the node's budget allocation from the plan's committed budget.

#### apply_modifications(plan, list) -> Result<(), PlanError>

- Applies a batch of modifications atomically.
- All modifications are validated as a batch: each modification is applied tentatively in sequence, and if any fails, the entire batch is rolled back.
- On success, emits one ModificationApplied event per modification in the batch.

---

## 5. PACT Record Mapping

Every plan operation creates EATP records for traceability. Per PACT thesis Section 5.7.

| Plan Operation | EATP Record(s) |
|---|---|
| Plan created (objective decomposed into DAG) | Audit Anchor (subtype: plan_created) capturing plan_id, envelope, node count, gradient config |
| Node spawned (agent instantiated for a node) | Genesis Record (if root agent) OR Delegation Record + Constraint Envelope (if child). Created by AgentFactory -- the plan records the delegation_record_id on the node. |
| Node completed | Audit Anchor (subtype: node_completed) capturing node_id, output summary, resource consumption |
| Node failed | Audit Anchor (subtype: node_failed) capturing node_id, error, gradient zone classification |
| Node held for resolution | Audit Anchor (subtype: action_held) capturing node_id, gradient zone, threshold that triggered the hold |
| Node blocked | Audit Anchor (subtype: action_blocked) capturing node_id, violating dimension, detail |
| Gradient zone determination | Audit Anchor per verification, capturing the effective envelope at decision time, the zone, and the threshold values |
| Plan modified (recomposition) | Audit Anchor (subtype: plan_modified) capturing the PlanModification payload. Plus new Delegation Record for new/changed nodes. |
| Plan completed | Audit Anchor (subtype: plan_completed) capturing all node outcomes, total resource consumption across all dimensions |
| Plan failed | Audit Anchor (subtype: plan_failed) capturing failed nodes, reason, total consumption at failure time |
| Plan suspended | Audit Anchor (subtype: plan_suspended) capturing running nodes at suspension time |
| Plan cancelled | Audit Anchor (subtype: plan_cancelled) capturing terminated agents |
| Budget warning (flagged/held) | Audit Anchor (subtype: budget_warning) capturing dimension, current consumption, threshold crossed, zone |
| Emergency bypass activated | Audit Anchor (subtype: emergency_bypass) per PACT Section 9, capturing bypass tier, approver, expiry |

---

## 6. Verification Gradient (CRITICAL SECTION)

This section defines how PlanExecutor uses the PACT verification gradient to handle execution events. The gradient is the failure handling policy. It is configuration from the PACT envelope, set by the supervisor. PlanExecutor makes zero LLM calls.

### Gradient Classification Rules

The following rules are deterministic and exhaustive:

**Rule G1: NodeCompleted (success)**
- Zone: AutoApproved
- Action: Record output. Mark node Completed. Continue to next ready nodes.

**Rule G2: NodeFailed (retryable error, retries remaining)**
- Zone: AutoApproved
- Action: Increment retry_count. Re-spawn the agent. Emit NodeRetrying.
- Condition: `node.retry_count < gradient.retry_budget` AND error is marked retryable.

**Rule G3: NodeFailed (retry budget exhausted)**
- Zone: `gradient.after_retry_exhaustion` (default: Held)
- Action: Apply the configured zone behavior (see zone actions below).
- Condition: `node.retry_count >= gradient.retry_budget` AND error is retryable.

**Rule G4: NodeFailed (non-retryable error, optional node)**
- Zone: `gradient.optional_node_failure` (default: Flagged)
- Action: Apply the configured zone behavior.
- Condition: Error is not retryable AND `node.optional == true`.

**Rule G5: NodeFailed (non-retryable error, required node)**
- Zone: Held
- Action: Suspend downstream nodes. Emit NodeHeld. Wait for resolution.
- Condition: Error is not retryable AND `node.optional == false`.

**Rule G6: BudgetWarning (flag threshold)**
- Zone: Flagged
- Action: Emit EnvelopeWarning with zone Flagged. Continue execution.
- Condition: Cumulative consumption for any dimension crosses `gradient.budget_flag_pct` of the node's allocated budget.

**Rule G7: BudgetWarning (hold threshold)**
- Zone: Held
- Action: Emit EnvelopeWarning with zone Held. Emit NodeHeld. Suspend downstream.
- Condition: Cumulative consumption for any dimension crosses `gradient.budget_hold_pct` of the node's allocated budget.

**Rule G8: EnvelopeViolation**
- Zone: Blocked (ALWAYS -- non-configurable)
- Action: Emit NodeBlocked. Terminate the plan branch. Cascade termination to all downstream nodes that depend on this node via DataDependency.
- Condition: Any node action exceeds its envelope on any dimension.

**Rule G9: ResolutionTimeout**
- Zone: Blocked
- Action: A held node that has waited longer than `gradient.resolution_timeout_seconds` without resolution transitions to Blocked. Emit NodeBlocked with reason "resolution_timeout".
- Condition: `time_since_held > gradient.resolution_timeout_seconds`.

### Zone Actions

When a gradient zone is determined, PlanExecutor performs the corresponding action:

**AutoApproved:**
- For success: continue.
- For optional failure: mark node Skipped, emit NodeSkipped, continue.
- Downstream nodes with DataDependency on a skipped node: if optional, also skip. If required, hold.

**Flagged:**
- Mark node Skipped (for failure cases) or continue (for budget warnings).
- Emit NodeFlagged with reason.
- Execution continues. The flag is for monitoring -- the orchestration layer or human reviews flagged events asynchronously.

**Held:**
- Emit NodeHeld.
- Suspend all downstream nodes (they remain in Pending state, do not transition to Ready even if other dependencies are met).
- Wait for resolution. Resolution comes from one of three sources:
  1. **Human** (via the hold queue from PACT infrastructure).
  2. **Orchestration layer** (kaizen-agents FailureDiagnoser + Recomposer submit a PlanModification).
  3. **Timeout** (configurable via `gradient.resolution_timeout_seconds`, default 300s, after which the held node transitions to Blocked).

**Blocked:**
- Emit NodeBlocked.
- Terminate the plan branch: cascade to all downstream nodes reachable via DataDependency edges.
- Downstream nodes transition to Skipped with reason referencing the blocked node.
- If all remaining required nodes are in terminal states and at least one is blocked/failed, emit PlanFailed.

### Branch Termination Semantics

When a node is Blocked, branch termination follows DataDependency edges only:

1. Identify all nodes reachable from the blocked node via outgoing DataDependency edges (transitive closure).
2. For each reachable node:
   - If Pending or Ready: transition to Skipped with reason "upstream_blocked: {blocked_node_id}".
   - If Running: the running agent continues (it was spawned before the block). When it completes, its output is recorded but downstream propagation follows the same blocked path rules.
3. CompletionDependency edges do NOT cascade termination. A node with a CompletionDependency on a blocked node becomes Ready when the blocked node reaches its terminal state.

### Interaction with EnvelopeTracker

PlanExecutor uses EnvelopeTracker for each active node:

1. When a node is spawned, an EnvelopeTracker is initialized with the node's envelope from its agent_spec.
2. The tracker monitors resource consumption during node execution.
3. When the tracker detects a threshold crossing (budget_flag_pct or budget_hold_pct), it notifies PlanExecutor.
4. PlanExecutor emits the corresponding EnvelopeWarning event with the appropriate gradient zone.
5. Envelope violations detected by EnvelopeTracker are always Blocked (Rule G8).

---

## 7. What Exists Today

The following existing components provide the foundation for Plan DAG implementation.

| Component | Location | Reuse Strategy |
|---|---|---|
| ChainPipeline (sequential execution) | kailash-kaizen pipelines | Pattern reference -- Plan DAG with linear edges generalizes this |
| MapReducePipeline (parallel fan-out/fan-in) | kailash-kaizen pipelines | Pattern reference -- Plan DAG with fan-out/fan-in topology generalizes this |
| MultiAgentOrchestrator (topological dependency tracking) | kailash-kaizen orchestration | Scheduling foundation -- topological sort logic reusable for DAG scheduling |
| OrchestrationRuntime (4 strategies) | kailash-kaizen orchestration | Replaced by PlanExecutor for L3. L1-L2 strategies remain for simpler use cases. |
| Verification gradient (4 zones) | PACT thesis Section 5.6, EATP enforcer | Direct reuse -- PlanGradient and GradientZone are the same concept applied to plan execution |
| HoldQueue | trust-plane holds | Direct reuse -- NodeHeld events are placed on the hold queue for resolution |
| ConstraintEnvelope with is_tighter_than() | trust-plane envelope | Direct reuse -- PlanValidator uses this for envelope feasibility |
| Envelope intersection algebra | trust-plane intersection | Direct reuse -- PlanValidator uses this for budget summation validation |
| StrictEnforcer (per-action checking) | trust-plane enforcer | Foundation -- PlanExecutor extends per-action to per-node gradient checking |
| BudgetTracker with atomic CAS | kailash-kaizen cost | Foundation for EnvelopeTracker financial dimension integration |

---

## 8. Edge Cases

### EC-01: Single-Node Plan (Degenerate but Valid)

A plan with exactly one node and zero edges is valid. It has one root and one leaf (the same node). PlanExecutor spawns it, waits for completion, and emits PlanCompleted or PlanFailed. This is equivalent to a direct agent execution but wrapped in plan infrastructure for gradient handling and audit trail.

### EC-02: All Nodes Fail

If every node in the plan reaches a terminal failure state (Failed and not retryable, or Blocked), the plan transitions to Failed. PlanFailed is emitted with the list of all failed node IDs. No partial success is reported in this case (but individual NodeCompleted events for any nodes that did succeed before the cascade were already emitted).

### EC-03: Modification Removes a Running Node

RemoveNode on a Running node is classified as Held per INV-PLAN-15. The executor does not silently terminate the running agent. Resolution options:
- The orchestration layer (or human) can cancel the node explicitly (via AgentFactory), then resubmit the RemoveNode.
- The orchestration layer can wait for the node to complete, then remove it.
- The resolution timeout applies -- if unresolved, the modification attempt is Blocked (rejected).

### EC-04: Modification Creates a Cycle

Any modification (AddNode with edges, AddEdge) that would create a cycle is rejected immediately. The modification returns an error, the plan is unchanged. No partial application occurs.

### EC-05: Concurrent Modifications

Modifications to an executing plan are serialized. If two modifications arrive concurrently, they are applied in arrival order. The second modification validates against the state left by the first. If the second modification would be invalid after the first (e.g., references a node the first modification removed), it is rejected.

Implementation note: the serialization mechanism (mutex, channel, etc.) is implementation-defined, but the observable behavior must be sequential consistency.

### EC-06: Empty Plan (Zero Nodes)

Rejected by PlanValidator.validate_structure(). Returns a ValidationError indicating "plan must contain at least one node". PlanState remains Draft.

### EC-07: Diamond Dependency Pattern

Nodes A, B, C, D where A -> B, A -> C, B -> D, C -> D. This is a valid DAG (diamond, not cycle). D becomes Ready only when both B and C complete. If B fails and C succeeds, D's readiness depends on the edge types:
- If B -> D is DataDependency: D cannot execute (B's output is required).
- If B -> D is CompletionDependency: D becomes Ready when B reaches terminal state (even Failed).

### EC-08: CoStart with Failed Source

If node A has a CoStart edge to node B, and A fails before B starts, B is not affected. CoStart is advisory -- it does not block B's execution. B becomes Ready based on its DataDependency and CompletionDependency edges independently of the CoStart source's outcome.

### EC-09: Modification During Suspension

Modifications can be applied to a Suspended plan. The plan remains Suspended after modification. The modifications take effect when the plan is resumed. If the modification requires re-validation (e.g., AddNode), the plan transitions to Draft and must be re-validated before resume.

### EC-10: Budget Reclamation After Node Completion

When a node completes and has unused budget (consumed less than allocated in its envelope), the unused portion is reclaimed by the plan-level EnvelopeTracker. This reclaimed budget is available for subsequently spawned nodes. PlanValidator's budget summation check is validated at plan creation time against allocated budgets, but runtime execution may benefit from reclaimed budget.

### EC-11: Held Node Resolution Unblocks Downstream

When a held node receives a resolution (via PlanModification such as ReplaceNode or via human intervention on the hold queue), the PlanExecutor:
1. Applies the resolution.
2. Re-evaluates downstream node readiness.
3. Transitions newly Ready nodes and spawns agents.
4. The hold is cleared -- no further waiting.

---

## 9. Conformance Test Vectors

These test vectors define expected behavior for any conforming implementation. Input is a plan structure and execution scenario. Output is the expected sequence of PlanEvents and final plan state.

### CT-PLAN-01: Linear Three-Node Plan (Happy Path)

```
Input:
  plan:
    envelope: { financial: 1000 }
    gradient: { retry_budget: 2, budget_flag_pct: 0.80, budget_hold_pct: 0.95 }
    nodes:
      - { node_id: "A", agent_spec: { envelope: { financial: 300 } }, optional: false }
      - { node_id: "B", agent_spec: { envelope: { financial: 300 } }, optional: false,
          input_mapping: { "data": { source_node: "A", output_key: "result" } } }
      - { node_id: "C", agent_spec: { envelope: { financial: 300 } }, optional: false,
          input_mapping: { "data": { source_node: "B", output_key: "result" } } }
    edges:
      - { from: "A", to: "B", edge_type: "DataDependency" }
      - { from: "B", to: "C", edge_type: "DataDependency" }

  execution_outcomes:
    A: { status: "completed", output: { "result": "alpha" } }
    B: { status: "completed", output: { "result": "beta" } }
    C: { status: "completed", output: { "result": "gamma" } }

Expected:
  validation: pass
  events:
    - NodeReady { node_id: "A" }
    - NodeStarted { node_id: "A", instance_id: <generated> }
    - NodeCompleted { node_id: "A", output: { "result": "alpha" } }
    - NodeReady { node_id: "B" }
    - NodeStarted { node_id: "B", instance_id: <generated> }
    - NodeCompleted { node_id: "B", output: { "result": "beta" } }
    - NodeReady { node_id: "C" }
    - NodeStarted { node_id: "C", instance_id: <generated> }
    - NodeCompleted { node_id: "C", output: { "result": "gamma" } }
    - PlanCompleted { results: { "A": { "result": "alpha" }, "B": { "result": "beta" }, "C": { "result": "gamma" } } }
  final_state: Completed
```

### CT-PLAN-02: Parallel Fan-Out / Fan-In

```
Input:
  plan:
    envelope: { financial: 1000 }
    gradient: { retry_budget: 1 }
    nodes:
      - { node_id: "split", agent_spec: { envelope: { financial: 200 } }, optional: false }
      - { node_id: "worker_1", agent_spec: { envelope: { financial: 200 } }, optional: false,
          input_mapping: { "chunk": { source_node: "split", output_key: "chunk_1" } } }
      - { node_id: "worker_2", agent_spec: { envelope: { financial: 200 } }, optional: false,
          input_mapping: { "chunk": { source_node: "split", output_key: "chunk_2" } } }
      - { node_id: "merge", agent_spec: { envelope: { financial: 200 } }, optional: false,
          input_mapping: {
            "result_1": { source_node: "worker_1", output_key: "result" },
            "result_2": { source_node: "worker_2", output_key: "result" }
          } }
    edges:
      - { from: "split", to: "worker_1", edge_type: "DataDependency" }
      - { from: "split", to: "worker_2", edge_type: "DataDependency" }
      - { from: "worker_1", to: "merge", edge_type: "DataDependency" }
      - { from: "worker_2", to: "merge", edge_type: "DataDependency" }

  execution_outcomes:
    split: { status: "completed", output: { "chunk_1": "data_a", "chunk_2": "data_b" } }
    worker_1: { status: "completed", output: { "result": "processed_a" } }
    worker_2: { status: "completed", output: { "result": "processed_b" } }
    merge: { status: "completed", output: { "result": "final" } }

Expected:
  validation: pass
  events:
    - NodeReady { node_id: "split" }
    - NodeStarted { node_id: "split" }
    - NodeCompleted { node_id: "split" }
    - NodeReady { node_id: "worker_1" }
    - NodeReady { node_id: "worker_2" }
    # worker_1 and worker_2 start in any order (parallel)
    - NodeStarted { node_id: "worker_1" }
    - NodeStarted { node_id: "worker_2" }
    # completion order is non-deterministic
    - NodeCompleted { node_id: "worker_1" }  # or worker_2 first
    - NodeCompleted { node_id: "worker_2" }
    - NodeReady { node_id: "merge" }
    - NodeStarted { node_id: "merge" }
    - NodeCompleted { node_id: "merge" }
    - PlanCompleted { results: { ... } }
  final_state: Completed
  note: "worker_1 and worker_2 MUST both be Ready after split completes. merge MUST NOT be Ready until both workers complete."
```

### CT-PLAN-03: Retry Within Budget (AutoApproved)

```
Input:
  plan:
    envelope: { financial: 500 }
    gradient: { retry_budget: 2, after_retry_exhaustion: "Held" }
    nodes:
      - { node_id: "flaky", agent_spec: { envelope: { financial: 500 } }, optional: false }
    edges: []

  execution_outcomes:
    flaky_attempt_1: { status: "failed", error: "timeout", retryable: true }
    flaky_attempt_2: { status: "completed", output: { "result": "ok" } }

Expected:
  events:
    - NodeReady { node_id: "flaky" }
    - NodeStarted { node_id: "flaky" }
    - NodeFailed { node_id: "flaky", error: "timeout", retryable: true }
    - NodeRetrying { node_id: "flaky", attempt: 1, max_attempts: 2 }
    - NodeStarted { node_id: "flaky" }
    - NodeCompleted { node_id: "flaky", output: { "result": "ok" } }
    - PlanCompleted { results: { "flaky": { "result": "ok" } } }
  final_state: Completed
  gradient_zone_for_retry: AutoApproved
```

### CT-PLAN-04: Retry Budget Exhausted (Held)

```
Input:
  plan:
    envelope: { financial: 500 }
    gradient: { retry_budget: 1, after_retry_exhaustion: "Held", resolution_timeout_seconds: 10 }
    nodes:
      - { node_id: "failing", agent_spec: { envelope: { financial: 500 } }, optional: false }
    edges: []

  execution_outcomes:
    failing_attempt_1: { status: "failed", error: "service_down", retryable: true }
    failing_attempt_2: { status: "failed", error: "service_down", retryable: true }

Expected:
  events:
    - NodeReady { node_id: "failing" }
    - NodeStarted { node_id: "failing" }
    - NodeFailed { node_id: "failing", error: "service_down", retryable: true }
    - NodeRetrying { node_id: "failing", attempt: 1, max_attempts: 1 }
    - NodeStarted { node_id: "failing" }
    - NodeFailed { node_id: "failing", error: "service_down", retryable: true }
    - NodeHeld { node_id: "failing", reason: "retry_budget_exhausted", zone: Held }
  final_state: Executing (waiting for resolution)
  gradient_zone: Held
  note: "If no resolution within 10 seconds, NodeBlocked is emitted and plan transitions to Failed."
```

### CT-PLAN-05: Optional Node Failure (Flagged, Skip and Continue)

```
Input:
  plan:
    envelope: { financial: 1000 }
    gradient: { retry_budget: 0, optional_node_failure: "Flagged" }
    nodes:
      - { node_id: "required", agent_spec: { envelope: { financial: 400 } }, optional: false }
      - { node_id: "optional_analysis", agent_spec: { envelope: { financial: 200 } }, optional: true }
      - { node_id: "final", agent_spec: { envelope: { financial: 300 } }, optional: false,
          input_mapping: { "data": { source_node: "required", output_key: "result" } } }
    edges:
      - { from: "required", to: "optional_analysis", edge_type: "DataDependency" }
      - { from: "required", to: "final", edge_type: "DataDependency" }
      - { from: "optional_analysis", to: "final", edge_type: "CompletionDependency" }

  execution_outcomes:
    required: { status: "completed", output: { "result": "data" } }
    optional_analysis: { status: "failed", error: "analysis_failed", retryable: false }
    final: { status: "completed", output: { "result": "done" } }

Expected:
  events:
    - NodeReady { node_id: "required" }
    - NodeStarted { node_id: "required" }
    - NodeCompleted { node_id: "required" }
    - NodeReady { node_id: "optional_analysis" }
    - NodeStarted { node_id: "optional_analysis" }
    - NodeFailed { node_id: "optional_analysis", error: "analysis_failed" }
    - NodeFlagged { node_id: "optional_analysis", reason: "optional_node_failure" }
    - NodeSkipped { node_id: "optional_analysis", reason: "flagged_optional_failure" }
    - NodeReady { node_id: "final" }  # CompletionDependency satisfied (optional_analysis is terminal)
    - NodeStarted { node_id: "final" }
    - NodeCompleted { node_id: "final" }
    - PlanCompleted { results: { "required": { "result": "data" }, "final": { "result": "done" } } }
  final_state: Completed
  gradient_zone_for_optional: Flagged
  note: "optional_analysis failure does NOT block final because (a) it is Flagged not Held, and (b) the edge to final is CompletionDependency not DataDependency."
```

### CT-PLAN-06: Envelope Violation (Always Blocked)

```
Input:
  plan:
    envelope: { financial: 100 }
    gradient: { retry_budget: 5 }  # high retry budget -- irrelevant, envelope violations bypass gradient
    nodes:
      - { node_id: "spender", agent_spec: { envelope: { financial: 100 } }, optional: false }
      - { node_id: "downstream", agent_spec: { envelope: { financial: 50 } }, optional: false,
          input_mapping: { "data": { source_node: "spender", output_key: "result" } } }
    edges:
      - { from: "spender", to: "downstream", edge_type: "DataDependency" }

  execution_outcomes:
    spender: { status: "envelope_violation", dimension: "financial", detail: "attempted $150 against $100 limit" }

Expected:
  events:
    - NodeReady { node_id: "spender" }
    - NodeStarted { node_id: "spender" }
    - NodeBlocked { node_id: "spender", dimension: "financial", detail: "attempted $150 against $100 limit" }
    - NodeSkipped { node_id: "downstream", reason: "upstream_blocked: spender" }
    - PlanFailed { failed_nodes: ["spender"], reason: "envelope_violation" }
  final_state: Failed
  gradient_zone: Blocked (non-configurable)
  note: "Envelope violations are ALWAYS Blocked regardless of retry_budget or any other gradient setting. This is INV-PLAN-08."
```

### CT-PLAN-07: Modification During Execution (AddNode)

```
Input:
  plan:
    envelope: { financial: 1000 }
    gradient: { retry_budget: 1 }
    nodes:
      - { node_id: "A", agent_spec: { envelope: { financial: 400 } }, optional: false }
      - { node_id: "B", agent_spec: { envelope: { financial: 300 } }, optional: false,
          input_mapping: { "data": { source_node: "A", output_key: "result" } } }
    edges:
      - { from: "A", to: "B", edge_type: "DataDependency" }

  execution_sequence:
    1. Execute plan. A starts.
    2. A completes with output { "result": "data" }.
    3. Before B starts, apply modification:
       AddNode {
         node: { node_id: "A_prime", agent_spec: { envelope: { financial: 200 } }, optional: false,
                 input_mapping: { "data": { source_node: "A", output_key: "result" } } },
         edges: [
           { from: "A", to: "A_prime", edge_type: "DataDependency" },
           { from: "A_prime", to: "B", edge_type: "DataDependency" }
         ]
       }
    4. B now depends on both A (original) and A_prime (new).
    5. A_prime executes and completes.
    6. B executes and completes.

Expected:
  modification_validation: pass (no cycle, envelope valid, budget sum <= 1000)
  events_after_modification:
    - ModificationApplied { modification: AddNode { ... } }
    - NodeReady { node_id: "A_prime" }
    - NodeStarted { node_id: "A_prime" }
    - NodeCompleted { node_id: "A_prime" }
    - NodeReady { node_id: "B" }
    - NodeStarted { node_id: "B" }
    - NodeCompleted { node_id: "B" }
    - PlanCompleted { ... }
  final_state: Completed
  note: "B was not Ready before the modification because the AddEdge from A_prime to B made it wait for A_prime."
```

### CT-PLAN-08: Cycle Detection in Modification

```
Input:
  plan:
    envelope: { financial: 500 }
    nodes:
      - { node_id: "A", agent_spec: { envelope: { financial: 200 } }, optional: false }
      - { node_id: "B", agent_spec: { envelope: { financial: 200 } }, optional: false }
    edges:
      - { from: "A", to: "B", edge_type: "DataDependency" }

  modification:
    AddEdge { edge: { from: "B", to: "A", edge_type: "DataDependency" } }

Expected:
  modification_validation: fail
  error: "Modification would create cycle: B -> A -> B"
  plan_state_after: unchanged (Draft or Validated -- whatever it was before)
  note: "INV-PLAN-01 (acyclicity) is enforced on every modification."
```

### CT-PLAN-09: Resolution Timeout Escalation

```
Input:
  plan:
    envelope: { financial: 500 }
    gradient: { retry_budget: 0, after_retry_exhaustion: "Held", resolution_timeout_seconds: 5 }
    nodes:
      - { node_id: "failing", agent_spec: { envelope: { financial: 500 } }, optional: false }
    edges: []

  execution_outcomes:
    failing: { status: "failed", error: "crash", retryable: true }
    # No resolution provided within 5 seconds

Expected:
  events:
    - NodeReady { node_id: "failing" }
    - NodeStarted { node_id: "failing" }
    - NodeFailed { node_id: "failing", error: "crash", retryable: true }
    - NodeHeld { node_id: "failing", reason: "retry_budget_exhausted", zone: Held }
    # ... 5 seconds pass with no resolution ...
    - NodeBlocked { node_id: "failing", dimension: "timeout", detail: "resolution_timeout_exceeded: 5s" }
    - PlanFailed { failed_nodes: ["failing"], reason: "resolution_timeout" }
  final_state: Failed
  note: "Rule G9: held nodes that are not resolved within the timeout window transition to Blocked."
```

### CT-PLAN-10: Budget Warning Thresholds

```
Input:
  plan:
    envelope: { financial: 1000 }
    gradient: { budget_flag_pct: 0.80, budget_hold_pct: 0.95 }
    nodes:
      - { node_id: "expensive", agent_spec: { envelope: { financial: 1000 } }, optional: false }
    edges: []

  execution_scenario:
    expensive consumes budget incrementally:
      - $500 consumed → no warning (50%)
      - $800 consumed → flag threshold crossed (80%)
      - $950 consumed → hold threshold crossed (95%)

Expected:
  events:
    - NodeReady { node_id: "expensive" }
    - NodeStarted { node_id: "expensive" }
    - EnvelopeWarning { node_id: "expensive", dimension: "financial", usage_pct: 0.80, zone: Flagged }
    # execution continues
    - EnvelopeWarning { node_id: "expensive", dimension: "financial", usage_pct: 0.95, zone: Held }
    - NodeHeld { node_id: "expensive", reason: "budget_hold_threshold", zone: Held }
  final_state: Executing (waiting for budget resolution)
  note: "Two distinct gradient zones triggered at two thresholds. The flag at 80% does not stop execution. The hold at 95% does."
```

### CT-PLAN-11: Validation Rejects Budget Overflow

```
Input:
  plan:
    envelope: { financial: 100 }
    nodes:
      - { node_id: "A", agent_spec: { envelope: { financial: 60 } }, optional: false }
      - { node_id: "B", agent_spec: { envelope: { financial: 60 } }, optional: false }
    edges: []

Expected:
  validation: fail
  error: "Budget summation exceeds plan envelope: sum(60, 60) = 120 > 100 on financial dimension"
  plan_state: Draft (not transitioned to Validated)
  note: "INV-PLAN-06: sum of node budgets must not exceed plan envelope."
```

### CT-PLAN-12: CompletionDependency Unblocks on Failure

```
Input:
  plan:
    envelope: { financial: 500 }
    gradient: { retry_budget: 0, optional_node_failure: "Flagged" }
    nodes:
      - { node_id: "maybe", agent_spec: { envelope: { financial: 200 } }, optional: true }
      - { node_id: "cleanup", agent_spec: { envelope: { financial: 200 } }, optional: false,
          input_mapping: {} }
    edges:
      - { from: "maybe", to: "cleanup", edge_type: "CompletionDependency" }

  execution_outcomes:
    maybe: { status: "failed", error: "not_available", retryable: false }
    cleanup: { status: "completed", output: { "status": "cleaned" } }

Expected:
  events:
    - NodeReady { node_id: "maybe" }
    - NodeStarted { node_id: "maybe" }
    - NodeFailed { node_id: "maybe", error: "not_available" }
    - NodeFlagged { node_id: "maybe", reason: "optional_node_failure" }
    - NodeSkipped { node_id: "maybe", reason: "flagged_optional_failure" }
    - NodeReady { node_id: "cleanup" }  # CompletionDependency satisfied by terminal state
    - NodeStarted { node_id: "cleanup" }
    - NodeCompleted { node_id: "cleanup" }
    - PlanCompleted { results: { "cleanup": { "status": "cleaned" } } }
  final_state: Completed
  note: "CompletionDependency means cleanup waits for maybe to reach ANY terminal state. maybe's failure (Flagged + Skipped) IS a terminal state, so cleanup proceeds."
```

---

## Appendix A: What the SDK Does NOT Do (Orchestration Layer Responsibility)

These capabilities require LLM judgment and live in kaizen-agents, not in the SDK:

| Component | What It Does | Why LLM |
|---|---|---|
| TaskDecomposer | Objective -> subtasks | Understanding goal semantics |
| PlanComposer | Subtasks + agent specs -> Plan DAG | Wiring, parallelism, data flow decisions |
| PlanEvaluator | Assess plan quality before execution | Semantic judgment (is this plan likely to achieve the objective?) |
| AgentDesigner | Subtask -> AgentSpec | Selecting tools, capabilities, envelope sizing |
| FailureDiagnoser | Failed node -> root cause analysis | Error interpretation |
| Recomposer | Failed plan -> PlanModification | Creative recovery strategy |
| EnvelopeAllocator | Parent envelope -> per-child budget allocation | Estimating resource needs per task |
| ResultAggregator | Leaf node outputs -> unified result | Synthesis of multiple outputs |

The boundary:
- **PlanValidator** (SDK) catches structural impossibilities (cycles, budget overflow, missing references).
- **PlanEvaluator** (kaizen-agents) catches semantic deficiencies (wrong decomposition granularity, semantically incorrect input mappings, suboptimal DAG topology).
- Both must pass before execution.

## Appendix B: Gradient Configuration Is Not Policy

The verification gradient thresholds are configuration data from the PACT envelope, set by the supervisor who delegated the task. They are not policy decisions made by the SDK or by the LLM.

The SDK reads the gradient config and executes deterministically. The orchestration layer (or human) resolves held events. Neither is incomplete without the other:
- SDK-only: plans execute with gradient handling. Held events wait for resolution (with timeout). The human hold queue provides the resolution path.
- SDK + kaizen-agents: held events are resolved faster via LLM-driven FailureDiagnoser + Recomposer. kaizen-agents is an accelerator, not a requirement.

This is PACT's Human-on-the-Loop pattern: the human defined the boundaries (gradient thresholds), the agent operates within them autonomously.
