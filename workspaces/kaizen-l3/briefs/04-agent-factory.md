# L3 Primitive Specification: AgentFactory + AgentInstanceRegistry

**Spec ID**: M1-04
**Status**: Draft
**Date**: 2026-03-21
**Dependencies**: M1-01 (EnvelopeTracker), M1-03 (MessageRouter)
**Decisions Applied**: DP-5 (AgentInstance is SEPARATE from AgentCard), D-AC1 (AgentConfig has optional envelope field)
**PACT Sections**: 4.1-4.3 (D/T/R Grammar), 5.1-5.3 (Recursive Delegation), 5.5 (Vacancy Handling), 5.7 (EATP Record Mapping)

---

## 1. Overview

AgentFactory and AgentInstanceRegistry provide runtime agent instantiation with PACT-governed envelope enforcement. A parent agent spawns child agents dynamically; the factory validates that every child operates within a strictly bounded subset of the parent's authority. The registry tracks all live instances, their lineage (parent-child relationships), and their lifecycle states.

These primitives live in the SDK layer (kailash-kaizen / kailash-py). They are deterministic -- no LLM calls. The orchestration layer (kaizen-agents) decides WHAT to spawn and HOW to allocate envelopes; the SDK validates and enforces.

**Boundary rule**: The SDK validates envelope subsetting, manages lifecycle state, enforces cascade termination, and tracks lineage. It does not decide what agent to spawn, what envelope to allocate, or when to spawn vs. handle inline. Those decisions require an LLM and belong to the orchestration layer.

**Relationship to existing types**: AgentCard (in `a2a/discovery.rs`) remains the static capability description used for agent discovery. AgentSpec is the runtime instantiation blueprint. AgentInstance is the running entity. AgentInstanceRegistry is a new struct separate from the existing AgentRegistry. The existing AgentRegistry continues to serve name-based AgentCard lookups unchanged.

---

## 2. Types

### 2.1 AgentSpec

A blueprint containing everything needed to instantiate an agent at runtime, except the LLM connection. AgentSpec is a value type -- it can be reused to spawn multiple instances.

| Field | Type | Required | Description |
|---|---|---|---|
| `spec_id` | string | yes | Unique identifier for this spec (immutable after creation). Used to correlate instances back to their blueprint. |
| `name` | string | yes | Human-readable name for this agent type (e.g., "Code Reviewer"). |
| `description` | string | yes | Description of what this agent does. Used by orchestration layer for capability matching. |
| `capabilities` | list of string | yes (may be empty) | Capabilities this agent provides (e.g., ["code-review", "style-check"]). Used for discovery. |
| `tool_ids` | list of string | yes (may be empty) | Tool identifiers this agent has access to. Must be a subset of the parent's allowed tools at spawn time. |
| `envelope` | ConstraintEnvelope | yes | The constraint envelope for this agent. Must satisfy monotonic tightening against the parent's envelope at spawn time. |
| `memory_config` | MemoryConfig | yes | Configuration for memory backends to attach (session, shared, persistent). |
| `max_lifetime` | duration or null | no | Maximum wall-clock lifetime. After this duration, the agent is terminated with reason Timeout. Null means no limit (bounded only by parent's temporal envelope). |
| `max_children` | integer or null | no | Maximum number of direct children this agent may spawn. Null means no limit (bounded only by budget). |
| `max_depth` | integer or null | no | Maximum delegation depth below this agent. Null means unlimited. Configurable per PACT supervisor policy. See invariant I-09. |
| `required_context_keys` | list of string | yes (may be empty) | Context keys this agent requires from its parent's ScopedContext at spawn time. Spawn fails if any key is missing. |
| `produced_context_keys` | list of string | yes (may be empty) | Context keys this agent will produce. Used by the orchestration layer for data flow planning; not enforced by the SDK. |
| `metadata` | map of string to JSON value | no | Arbitrary key-value pairs for orchestration layer use. The SDK stores but does not interpret these. |

### 2.2 AgentInstance

A running agent entity with lifecycle tracking. Created by the factory at spawn time. Each instance is uniquely identified and linked to its parent in the delegation hierarchy.

| Field | Type | Mutable | Description |
|---|---|---|---|
| `instance_id` | UUID | no | Globally unique identifier generated at spawn time. Never reused. |
| `spec_id` | string | no | The AgentSpec this instance was created from. |
| `parent_id` | UUID or null | no | The parent instance that spawned this agent. Null only for the root agent. Immutable after creation (lineage never changes). |
| `state` | AgentState | yes | Current lifecycle state. Transitions governed by state machine (Section 2.3). |
| `created_at` | timestamp (UTC) | no | When this instance was created. |
| `active_envelope` | ConstraintEnvelope | yes | The active envelope. Initially set from the spec's envelope. May be tightened at runtime (never widened except via emergency bypass per PACT Section 9). |
| `budget_tracker` | EnvelopeTracker | yes | Runtime budget tracker for this instance. Initialized from `active_envelope` at spawn. Consumes budget as the agent acts. Depends on M1-01 EnvelopeTracker. |

### 2.3 AgentState

Lifecycle states for an agent instance. This is a discriminated union (tagged enum).

```
AgentState =
  | Pending                              -- Created but not yet started
  | Running                              -- Currently executing
  | Waiting { reason: WaitReason }       -- Blocked, waiting for external input
  | Completed { result: JSON value }     -- Finished successfully
  | Failed { error: string }             -- Encountered an unrecoverable error
  | Terminated { reason: TerminationReason }  -- Forcibly stopped
```

**State machine transitions** (valid transitions only):

```
Pending   -> Running                    (agent starts execution)
Pending   -> Terminated                 (terminated before starting)
Running   -> Waiting                    (blocked on delegation, approval, or resource)
Running   -> Completed                  (finished successfully)
Running   -> Failed                     (unrecoverable error)
Running   -> Terminated                 (forcibly stopped)
Waiting   -> Running                    (wait condition resolved)
Waiting   -> Terminated                 (forcibly stopped while waiting)
```

Terminal states (no transitions out): `Completed`, `Failed`, `Terminated`.

Invalid transitions (must be rejected): any transition FROM a terminal state; `Pending -> Completed`; `Pending -> Failed`; `Pending -> Waiting`; `Waiting -> Completed`; `Waiting -> Failed`.

### 2.4 WaitReason

Why an agent is in the Waiting state.

```
WaitReason =
  | DelegationResponse { message_id: UUID }   -- Waiting for a child to return a result
  | HumanApproval { hold_id: UUID }           -- Action in HELD zone, awaiting human decision
  | ResourceAvailability                       -- Waiting for a resource (e.g., rate limit, pool)
```

### 2.5 TerminationReason

Why an agent was forcibly terminated.

```
TerminationReason =
  | ParentTerminated                                   -- Parent was terminated; cascade rule applied
  | EnvelopeViolation { dimension: string, detail: string }  -- Attempted action outside envelope
  | Timeout                                            -- max_lifetime exceeded
  | BudgetExhausted { dimension: string }              -- EnvelopeTracker reports dimension depleted
  | ExplicitTermination { by: UUID }                   -- Another agent or external caller requested termination
```

### 2.6 AgentInstanceRegistry

A thread-safe registry tracking all agent instances, their lineage, and their state. Supports concurrent reads and serialized writes.

**Internal structure** (implementation-private, shown for clarity):

- Primary index: `instance_id -> AgentInstance`
- Lineage index: `parent_id -> list of child instance_ids`
- Spec index: `spec_id -> list of instance_ids` (optional, for discovery)

**Operations**: See Section 4.

### 2.7 FactoryError

Errors returned by AgentFactory operations.

```
FactoryError =
  | EnvelopeNotTighter { dimension: string, parent_value: string, child_value: string }
  | InsufficientBudget { dimension: string, required: string, available: string }
  | MaxChildrenExceeded { parent_id: UUID, limit: integer, current: integer }
  | MaxDepthExceeded { parent_id: UUID, depth_limit: integer, current_depth: integer }
  | ToolNotInParent { tool_id: string }
  | InstanceNotFound { instance_id: UUID }
  | InvalidStateTransition { from: AgentState, to: AgentState }
  | RequiredContextMissing { keys: list of string }
  | RegistryError { detail: string }
```

---

## 3. Behavioral Invariants

These invariants MUST hold in any conformant implementation (Rust, Python, or other). Violation of any invariant is a conformance failure.

### I-01: Monotonic Envelope Tightening at Spawn

For every dimension d of the constraint envelope: `child.envelope.d <= parent.active_envelope.d`. This is checked at spawn time using the per-dimension intersection algebra from PACT Section 5.3:

| Dimension | Tightening Rule |
|---|---|
| Financial | child.limit <= parent.remaining (not parent.original -- accounts for already-allocated budget) |
| Operational | child.allowed is subset of parent.allowed; child.blocked is superset of parent.blocked |
| Temporal | child.window is within parent.window; child.blackouts is superset of parent.blackouts |
| Data Access | child.ceiling <= parent.ceiling; child.scopes is subset of parent.scopes |
| Communication | child.recipients is subset of parent.recipients; child.channels is subset of parent.channels |

When composed allowed and blocked sets overlap for Operational actions, the blocked set takes precedence (deny-overrides, per PACT Section 5.3).

### I-02: Cascade Termination

When a parent agent transitions to a terminal state (Completed, Failed, or Terminated), ALL descendants (children, grandchildren, etc.) MUST be terminated with reason `ParentTerminated`. The cascade is recursive and depth-first. No descendant may continue executing after its ancestor has reached a terminal state.

Cascade order: depth-first, leaves first. A parent is not marked terminal until all descendants have been terminated. This prevents a race where a child observes its parent terminated but its own children are still running.

### I-03: Globally Unique Instance IDs

Every `instance_id` generated by the factory MUST be globally unique across all time. UUID v4 (random) or UUID v7 (time-ordered random) are both acceptable. An instance_id MUST NOT be reused even after the instance is deregistered.

### I-04: Immutable Lineage

The `parent_id` of an AgentInstance MUST NOT change after creation. The delegation hierarchy is write-once. If a parent is terminated and children need reassignment, this is handled through the vacancy protocol (Section 8.4), which designates an acting parent but does not rewrite the original `parent_id`.

### I-05: Tool Allowlist Subsetting

Every `tool_id` in the child's AgentSpec MUST exist in the parent's allowed tool set. This is a strict subset check at spawn time. If the parent's Operational envelope restricts certain tools, the child cannot access them regardless of what its spec requests.

### I-06: State Machine Validity

State transitions MUST follow the state machine defined in Section 2.3. Any attempt to perform an invalid transition (e.g., Completed -> Running) MUST return `FactoryError::InvalidStateTransition`.

### I-07: Budget Accounting at Spawn

When a child is spawned, the parent's EnvelopeTracker MUST deduct the child's allocated budget from the parent's remaining budget. This prevents a parent from spawning children whose combined budgets exceed the parent's own budget. The check is:

```
parent.budget_tracker.remaining[dimension] >= child.envelope[dimension]
```

for all depletable dimensions (Financial, Operational quota, Communication volume). After spawn, the parent's remaining budget is reduced by the child's allocation.

### I-08: Budget Reclamation on Completion

When a child reaches a terminal state (Completed, Failed, Terminated), any unused budget from the child's EnvelopeTracker MUST be returned to the parent's remaining pool. The reclaimed amount is:

```
reclaimed[dimension] = child.allocated[dimension] - child.consumed[dimension]
```

### I-09: Max Depth Enforcement

If `max_depth` is set on an AgentSpec (or on any ancestor), the factory MUST compute the current depth of the parent in the lineage tree and reject the spawn if adding a child would exceed the limit. Depth is defined as the number of edges from the root to the instance. The root agent has depth 0. Default: unlimited (null).

When multiple ancestors specify `max_depth`, the effective limit is the minimum of all ancestor limits minus the edges already traversed. Formally: for each ancestor A with `max_depth = M` at depth D, the remaining depth budget from A is `M - (current_depth - D)`. The effective remaining depth is `min(remaining_depth_budget)` across all ancestors with a limit set.

### I-10: Required Context Validation at Spawn

If `required_context_keys` is non-empty, the factory MUST verify that the parent's ScopedContext contains all listed keys before spawning. Spawn fails with `FactoryError::RequiredContextMissing` if any key is absent.

---

## 4. Operations

### 4.1 spawn(child_spec, parent_envelope, parent_id) -> AgentInstance

Creates a new agent instance from a spec, validates all invariants, and registers the instance.

**Parameters**:
- `child_spec`: AgentSpec -- the blueprint for the new agent
- `parent_envelope`: ConstraintEnvelope -- the parent's current active envelope (used for tightening validation)
- `parent_id`: UUID or null -- the spawning parent's instance_id (null only for root agent creation)

**Preconditions**:
1. If `parent_id` is not null, the parent MUST exist in the registry and MUST be in state Running or Waiting (cannot spawn from a terminal or Pending state).
2. `child_spec.envelope` satisfies monotonic tightening against `parent_envelope` (I-01).
3. Parent's EnvelopeTracker has sufficient remaining budget for the child's allocation (I-07).
4. Parent has not exceeded `max_children` limit (from the parent's own spec, if set).
5. Current delegation depth does not exceed `max_depth` limits from any ancestor (I-09).
6. Every tool_id in `child_spec.tool_ids` exists in the parent's allowed tools (I-05).
7. All `required_context_keys` are present in the parent's ScopedContext (I-10).

**Postconditions**:
1. A new AgentInstance is created with a unique `instance_id`, state `Pending`, `created_at` set to now (UTC).
2. The instance is registered in the AgentInstanceRegistry.
3. The parent's lineage index is updated to include the new child.
4. The parent's EnvelopeTracker is debited by the child's allocated envelope budget.
5. An EnvelopeTracker is initialized for the child from `child_spec.envelope`.
6. EATP records are created (see Section 5).

**Errors** (in check order):
1. `InstanceNotFound` -- parent_id does not exist in registry
2. `InvalidStateTransition` -- parent is not in Running or Waiting state
3. `EnvelopeNotTighter` -- envelope fails monotonic tightening on any dimension
4. `InsufficientBudget` -- parent lacks budget for child allocation
5. `MaxChildrenExceeded` -- parent at child limit
6. `MaxDepthExceeded` -- delegation chain too deep
7. `ToolNotInParent` -- tool_id not in parent's allowed set
8. `RequiredContextMissing` -- required context keys absent

### 4.2 terminate(instance_id, reason) -> void

Terminates an agent instance and cascades to all descendants.

**Parameters**:
- `instance_id`: UUID -- the instance to terminate
- `reason`: TerminationReason -- why termination is occurring

**Preconditions**:
1. The instance MUST exist in the registry.
2. The instance MUST NOT already be in a terminal state (Completed, Failed, Terminated). Terminating an already-terminated agent is a no-op (idempotent), not an error. See edge case 8.3.

**Procedure**:
1. Collect all descendants of `instance_id` via `all_descendants()`.
2. Sort descendants by depth (deepest first -- leaves before parents).
3. For each descendant, transition state to `Terminated { reason: ParentTerminated }`.
4. Perform budget reclamation for each terminated descendant back to its direct parent (I-08).
5. Transition `instance_id` to `Terminated { reason: <provided reason> }`.
6. Reclaim unused budget from `instance_id` back to its parent (if it has one).
7. Create EATP Audit Anchor for each termination (see Section 5).

**Postconditions**:
1. The instance and all its descendants are in state Terminated.
2. Unused budgets have been reclaimed up the chain.
3. EATP records exist for every termination.

### 4.3 get_state(instance_id) -> AgentState

Returns the current lifecycle state of an agent instance.

**Errors**: `InstanceNotFound` if the instance does not exist in the registry.

### 4.4 update_state(instance_id, new_state) -> void

Transitions an agent instance to a new state, subject to state machine validity (I-06).

**Errors**: `InstanceNotFound` if absent; `InvalidStateTransition` if the transition is not in the valid transition set.

### 4.5 children_of(parent_id) -> list of AgentInstance

Returns all direct children of the given parent. Returns an empty list if the parent has no children. Returns an empty list (not an error) if the parent_id does not exist -- this supports querying for potential parents before they have spawned children.

### 4.6 lineage(instance_id) -> list of UUID

Returns the path from the root agent to the given instance, inclusive. The first element is the root; the last element is `instance_id`. For a root agent, returns a single-element list.

**Errors**: `InstanceNotFound` if the instance does not exist.

This operation walks `parent_id` links from the instance up to the root. The result is reversed to produce root-to-instance order.

### 4.7 all_descendants(instance_id) -> list of UUID

Returns all recursive descendants (children, grandchildren, etc.) of the given instance. Does not include the instance itself. Returns an empty list if the instance has no children.

Uses breadth-first or depth-first traversal of the lineage index. The order is implementation-defined but MUST be deterministic for a given registry state.

### 4.8 count_live() -> integer

Returns the count of all instances NOT in a terminal state (Completed, Failed, Terminated).

### 4.9 register(instance) -> void

Adds an instance to the registry. Called internally by `spawn()`. Exposed for testing and for the root agent bootstrap (the root agent is registered without a parent).

**Errors**: `RegistryError` if an instance with the same `instance_id` already exists (I-03).

### 4.10 deregister(instance_id) -> AgentInstance

Removes an instance from the registry and returns it. The instance MUST be in a terminal state before deregistration. Deregistration is optional cleanup -- terminated instances MAY remain in the registry for audit purposes.

**Errors**: `InstanceNotFound`; `InvalidStateTransition` if the instance is not in a terminal state.

---

## 5. PACT Record Mapping

Every AgentFactory operation that changes governance state creates EATP records per PACT Section 5.7. Implementations claiming PACT conformance MUST produce these records.

| Operation | EATP Record(s) | Content |
|---|---|---|
| spawn() -- root agent (parent_id is null) | Genesis Record | Records the creation of the root agent as a governed entity. Contains: instance_id, spec_id, active_envelope, created_at. |
| spawn() -- child agent | Delegation Record + Constraint Envelope | The Delegation Record captures: delegator (parent_id), delegate (instance_id), scope (child's active_envelope). The Constraint Envelope captures all five dimensions of the child's allocated envelope. |
| spawn() -- spawn rejected | Audit Anchor (subtype: spawn_rejected) | Captures: parent_id, spec_id, rejection reason, violating dimension (if envelope), timestamp. |
| terminate() | Audit Anchor (subtype: agent_terminated) | Captures: instance_id, termination reason, final state of budget_tracker (consumed vs. allocated per dimension), timestamp. One record per terminated instance (including cascade). |
| update_state() | Audit Anchor (subtype: state_transition) | Captures: instance_id, previous state, new state, timestamp. |
| Budget reclamation | Audit Anchor (subtype: budget_reclaimed) | Captures: child_id, parent_id, reclaimed amounts per dimension, timestamp. |

The Audit Anchor created at spawn time captures the effective envelope as computed at that moment (the intersection of all ancestor envelopes from root to child). This enables point-in-time audit queries: "What was this agent's actual authority boundary when it was created?"

---

## 6. PACT D/T/R Integration

### 6.1 Organizational Addressing for Agent Instances

PACT's positional addressing scheme (Section 4.3) maps to the agent hierarchy. Each agent instance occupies a position in the D/T/R tree. For L3 agent spawning, each spawn creates a new T-R pair under the parent's position:

```
Root agent:       D1-R1
  Child 1:        D1-R1-T1-R1
    Grandchild:   D1-R1-T1-R1-T1-R1
  Child 2:        D1-R1-T2-R1
```

The T index increments per spawn within a parent (T1, T2, T3...). Each T gets exactly one R (the child agent), satisfying the D/T/R grammar's container-must-have-head invariant.

### 6.2 Address Computation

An agent's positional address is computed deterministically from its lineage:

```
address(root) = "D1-R1"  (or configured root prefix)
address(child) = address(parent) + "-T{n}-R1"
  where n = ordinal of child among parent's children (1-indexed, by creation order)
```

Addresses support:
- **Prefix containment**: Agent X is a descendant of agent Y if and only if X's address starts with Y's address.
- **Ancestry queries**: Reading X's address left-to-right enumerates every accountable position from root to X.
- **Sibling detection**: Two agents are siblings if their addresses share a prefix up to the last T-R pair.

### 6.3 Address as Routing Identifier

The MessageRouter (M1-03) uses positional addresses for routing decisions:
- **Parent-child messages**: Destination is a prefix extension of source (or vice versa). Always permitted.
- **Sibling messages**: Share a common parent prefix. Permitted if within communication envelope.
- **Cross-subtree messages**: Different prefixes diverge above the nearest common ancestor. Requires a bridge (PACT Section 4.4).

---

## 7. What Exists Today

The following components in kailash-kaizen provide the foundation for AgentFactory. L3 builds on these; it does not replace them.

| Component | Location | What It Provides | L3 Relationship |
|---|---|---|---|
| `BaseAgent` trait | `kailash-kaizen/agent/mod.rs` | `name()`, `description()`, `run()`, `run_with_memory()` | AgentInstance wraps a `BaseAgent` implementation. The trait is object-safe (`Arc<dyn BaseAgent>` works). |
| `AgentConfig` | `kailash-kaizen/types.rs` | `model`, `execution_mode`, `system_prompt` | Extended with optional `envelope` field (D-AC1). Non-breaking: `#[serde(default)]`. |
| `Agent::new()` | `kailash-kaizen/agent/concrete.rs` | Single-instance creation from LlmClient + AgentConfig | Factory wraps this: creates the config, calls `Agent::new()`, then wraps in AgentInstance with lifecycle tracking. |
| `AgentRegistry` (name-based) | `kailash-kaizen/a2a/discovery.rs` | `register()`, `find()`, `list()` for AgentCards | Unchanged. AgentInstanceRegistry is a NEW struct for lifecycle tracking. AgentRegistry continues to serve static card lookups. |
| `AgentCard` | `kailash-kaizen/a2a/discovery.rs` | `name`, `description`, `url`, `capabilities`, `skills` | Unchanged (DP-5). AgentSpec is a different type for runtime instantiation. AgentCard is for discovery. |
| `DelegationChain` | `eatp/delegation.rs` | Chain of delegation records with scope subsetting | Reused directly. Each spawn extends the chain. `DelegationChain.is_valid()` checks the entire chain. |
| `ConstraintEnvelope` | `trust-plane/envelope.rs` | 5-dimensional constraint model with `is_tighter_than()` | Reused directly for spawn-time validation (I-01). |
| `intersect()` | `trust-plane/intersection.rs` | Envelope intersection algebra (commutative) | Reused for effective envelope computation. |
| `StrictEnforcer` | `trust-plane/enforcer.rs` | Per-action checking against all 5 dimensions | Reused. Every agent action passes through StrictEnforcer with the agent's active_envelope. |
| `BudgetTracker` | `kailash-kaizen/cost/budget.rs` | Atomic CAS budget tracking | Foundation for EnvelopeTracker's financial dimension. |
| `WorkerStatus` | `kailash-kaizen/orchestration/` | 3 states: Idle, Working, Failed | Superseded by AgentState (6 states). Mapping: Idle -> Pending or Completed, Working -> Running, Failed -> Failed. |

---

## 8. Edge Cases

### 8.1 Spawn When Parent Has Zero Remaining Budget

**Scenario**: Parent's EnvelopeTracker shows `remaining[financial] = 0`. A spawn is attempted with a child spec requesting any positive financial allocation.

**Expected behavior**: Spawn MUST fail with `FactoryError::InsufficientBudget { dimension: "financial", required: "<child amount>", available: "0" }`.

**Rationale**: Zero remaining budget means the parent has consumed or allocated its entire authority. No child can be created with a non-trivial envelope. A child requesting a zero-budget envelope on all dimensions is degenerate but technically valid (see 8.2).

### 8.2 Spawn With Envelope Identical to Parent (No Tightening)

**Scenario**: Child spec has an envelope that is exactly equal to the parent's active envelope on all dimensions.

**Expected behavior**: Spawn MUST succeed. The monotonic tightening invariant requires `child.d <= parent.d` for all dimensions, which includes equality. An identical envelope satisfies the invariant.

**Warning**: This is a valid but suspicious pattern. PACT Section 5.4 identifies this as a potential "gradient dereliction" -- the parent has delegated its full authority without narrowing. Implementations SHOULD emit a warning or monitoring event but MUST NOT reject the spawn solely on this basis.

**Budget note**: An identical envelope means the child's allocation equals the parent's remaining budget. After spawn, the parent will have zero remaining on all depletable dimensions. This is valid but means the parent cannot spawn additional children or perform budget-consuming actions itself.

### 8.3 Terminate an Already-Terminated Agent

**Scenario**: `terminate(instance_id, reason)` is called on an instance that is already in state `Terminated`.

**Expected behavior**: No-op. The operation MUST return successfully (not an error). The termination reason is NOT updated -- the original reason is preserved. No EATP records are created for the redundant termination. No cascade is triggered (descendants are already terminated).

**Rationale**: Idempotent termination simplifies cascade logic. When multiple paths lead to the same termination (e.g., parent terminated + budget exhausted simultaneously), the first to arrive wins.

### 8.4 Orphaned Children (Vacancy Handling)

**Scenario**: A parent agent is terminated but its children are still running (this occurs during the cascade before the children have been terminated, or if cascade is interrupted).

**Expected behavior per PACT Section 5.5**:

1. **Immediate**: All children continue operating but under tightened constraints. Their envelopes are intersected with the parent's envelope at time of termination (which may be more restrictive than what was originally allocated to the children, since the parent may have tightened its own envelope during execution).

2. **Deadline (configurable, default 24 hours in PACT)**: For L3 agent runtime, this deadline is much shorter -- configurable per deployment, default 60 seconds. Within the deadline, the system MUST either:
   - Designate an acting parent (the terminated parent's own parent, if alive), or
   - Terminate the orphaned children.

3. **After deadline with no acting parent**: All orphaned children are suspended (all actions HELD) with escalation to the nearest living ancestor.

In practice, the cascade termination (I-02) handles this: when a parent is terminated, all descendants are terminated depth-first. The vacancy protocol applies only if cascade termination is interrupted (process crash, network partition in distributed scenarios).

### 8.5 Concurrent Spawns From Same Parent

**Scenario**: Two concurrent spawn requests arrive for the same parent, both requesting budget allocation.

**Expected behavior**: The registry MUST serialize spawn operations for the same parent. The second spawn sees the budget after the first spawn's deduction. If the first spawn consumes all remaining budget, the second MUST fail with `InsufficientBudget`.

**Implementation note**: This requires either a mutex per parent or optimistic concurrency with retry. The registry's write serialization (Section 2.6) provides the synchronization point.

### 8.6 Spawn During Parent's Waiting State

**Scenario**: A parent agent is in state `Waiting { reason: DelegationResponse }` (waiting for one child) and attempts to spawn another child.

**Expected behavior**: Spawn MUST succeed. The Waiting state does not prevent spawning additional children. A parent may be simultaneously waiting for one child's result while dispatching another child to work on a parallel subtask.

### 8.7 Max Depth With Multiple Ancestors Setting Limits

**Scenario**: Root agent has `max_depth = 5`. Root spawns Child A with `max_depth = 3`. Child A spawns Child B (no max_depth). Child B attempts to spawn Child C.

**Expected behavior**: Child B is at depth 2 from root, depth 1 from Child A.
- Root's limit: remaining = 5 - 2 = 3 (depth from root to C would be 3, which equals limit -- allowed)
- Child A's limit: remaining = 3 - 1 = 2 (depth from A to C would be 2, which equals limit -- allowed)
- Child B has no limit.

Spawn succeeds. If Child C then tries to spawn Child D:
- Root's limit: remaining = 5 - 3 = 2 (depth from root to D would be 4 -- allowed since 4 <= 5)
- Child A's limit: remaining = 3 - 2 = 1 (depth from A to D would be 3, which equals limit -- allowed)

Still succeeds. But if Child D tries to spawn Child E:
- Child A's limit: remaining = 3 - 3 = 0 (depth from A to E would be 4, which exceeds limit of 3)
- Spawn fails with `MaxDepthExceeded`.

### 8.8 Root Agent Bootstrap

**Scenario**: The very first agent instance has no parent.

**Expected behavior**: The root agent is created by calling `register()` directly (not `spawn()`), with `parent_id = null`. The root agent's envelope is not validated against a parent (there is none). It is the top-level authority, typically configured by the human supervisor. A Genesis Record is created per PACT Section 5.7.

---

## 9. Conformance Test Vectors

Each test vector specifies inputs, expected outputs, and the invariant(s) it validates. Implementations in any language MUST pass all vectors.

### TV-01: Successful Spawn With Tighter Envelope

**Validates**: I-01 (monotonic tightening), I-07 (budget accounting)

```json
{
  "test_id": "TV-01",
  "description": "Child with strictly tighter envelope spawns successfully",
  "setup": {
    "parent": {
      "instance_id": "00000000-0000-0000-0000-000000000001",
      "state": "Running",
      "active_envelope": {
        "financial": { "limit": 10000 },
        "operational": { "allowed": ["read_file", "write_file", "grep", "lint"], "blocked": [] },
        "temporal": { "window_start": "2026-03-21T00:00:00Z", "window_end": "2026-03-22T00:00:00Z" },
        "data_access": { "ceiling": "CONFIDENTIAL", "scopes": ["project-alpha", "project-beta"] },
        "communication": { "recipients": ["agent-a", "agent-b", "agent-c"], "channels": ["internal"] }
      },
      "budget_remaining": {
        "financial": 10000
      }
    }
  },
  "input": {
    "child_spec": {
      "spec_id": "code-reviewer",
      "name": "Code Reviewer",
      "description": "Reviews code for correctness",
      "capabilities": ["code-review"],
      "tool_ids": ["read_file", "grep"],
      "envelope": {
        "financial": { "limit": 2000 },
        "operational": { "allowed": ["read_file", "grep"], "blocked": [] },
        "temporal": { "window_start": "2026-03-21T08:00:00Z", "window_end": "2026-03-21T18:00:00Z" },
        "data_access": { "ceiling": "RESTRICTED", "scopes": ["project-alpha"] },
        "communication": { "recipients": ["agent-a"], "channels": ["internal"] }
      },
      "memory_config": "session_only",
      "max_lifetime": "PT30M",
      "max_children": null,
      "max_depth": null,
      "required_context_keys": [],
      "produced_context_keys": ["review_result"],
      "metadata": {}
    },
    "parent_id": "00000000-0000-0000-0000-000000000001"
  },
  "expected": {
    "outcome": "success",
    "instance": {
      "spec_id": "code-reviewer",
      "parent_id": "00000000-0000-0000-0000-000000000001",
      "state": "Pending",
      "active_envelope_matches_spec": true
    },
    "parent_budget_after": {
      "financial": 8000
    },
    "eatp_records": [
      { "type": "DelegationRecord", "delegator": "00000000-0000-0000-0000-000000000001" },
      { "type": "ConstraintEnvelope", "financial_limit": 2000 }
    ]
  }
}
```

### TV-02: Spawn Rejected -- Envelope Not Tighter

**Validates**: I-01 (monotonic tightening)

```json
{
  "test_id": "TV-02",
  "description": "Child with wider financial limit is rejected",
  "setup": {
    "parent": {
      "instance_id": "00000000-0000-0000-0000-000000000001",
      "state": "Running",
      "active_envelope": {
        "financial": { "limit": 5000 },
        "operational": { "allowed": ["read_file"], "blocked": [] },
        "temporal": { "window_start": "2026-03-21T00:00:00Z", "window_end": "2026-03-22T00:00:00Z" },
        "data_access": { "ceiling": "RESTRICTED", "scopes": ["project-alpha"] },
        "communication": { "recipients": ["agent-a"], "channels": ["internal"] }
      },
      "budget_remaining": {
        "financial": 5000
      }
    }
  },
  "input": {
    "child_spec": {
      "spec_id": "expensive-agent",
      "name": "Expensive Agent",
      "description": "Requests more budget than parent has",
      "capabilities": [],
      "tool_ids": ["read_file"],
      "envelope": {
        "financial": { "limit": 10000 },
        "operational": { "allowed": ["read_file"], "blocked": [] },
        "temporal": { "window_start": "2026-03-21T00:00:00Z", "window_end": "2026-03-22T00:00:00Z" },
        "data_access": { "ceiling": "RESTRICTED", "scopes": ["project-alpha"] },
        "communication": { "recipients": ["agent-a"], "channels": ["internal"] }
      },
      "memory_config": "session_only",
      "max_lifetime": null,
      "max_children": null,
      "max_depth": null,
      "required_context_keys": [],
      "produced_context_keys": [],
      "metadata": {}
    },
    "parent_id": "00000000-0000-0000-0000-000000000001"
  },
  "expected": {
    "outcome": "error",
    "error_type": "EnvelopeNotTighter",
    "error_dimension": "financial",
    "parent_value": "5000",
    "child_value": "10000",
    "parent_budget_unchanged": true,
    "eatp_records": [
      { "type": "AuditAnchor", "subtype": "spawn_rejected", "reason": "envelope_not_tighter" }
    ]
  }
}
```

### TV-03: Cascade Termination

**Validates**: I-02 (cascade termination), I-08 (budget reclamation)

```json
{
  "test_id": "TV-03",
  "description": "Terminating a parent cascades to all descendants and reclaims budget",
  "setup": {
    "instances": [
      {
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "spec_id": "root",
        "parent_id": null,
        "state": "Running",
        "allocated_financial": 10000,
        "consumed_financial": 1000
      },
      {
        "instance_id": "00000000-0000-0000-0000-000000000002",
        "spec_id": "child-a",
        "parent_id": "00000000-0000-0000-0000-000000000001",
        "state": "Running",
        "allocated_financial": 4000,
        "consumed_financial": 500
      },
      {
        "instance_id": "00000000-0000-0000-0000-000000000003",
        "spec_id": "child-b",
        "parent_id": "00000000-0000-0000-0000-000000000001",
        "state": "Waiting",
        "allocated_financial": 3000,
        "consumed_financial": 200
      },
      {
        "instance_id": "00000000-0000-0000-0000-000000000004",
        "spec_id": "grandchild",
        "parent_id": "00000000-0000-0000-0000-000000000002",
        "state": "Running",
        "allocated_financial": 1500,
        "consumed_financial": 100
      }
    ]
  },
  "input": {
    "terminate_instance_id": "00000000-0000-0000-0000-000000000001",
    "reason": { "type": "ExplicitTermination", "by": "00000000-0000-0000-0000-fffffffffff1" }
  },
  "expected": {
    "outcome": "success",
    "terminated_instances": [
      {
        "instance_id": "00000000-0000-0000-0000-000000000004",
        "reason": "ParentTerminated",
        "order": 1
      },
      {
        "instance_id": "00000000-0000-0000-0000-000000000002",
        "reason": "ParentTerminated",
        "order": 2
      },
      {
        "instance_id": "00000000-0000-0000-0000-000000000003",
        "reason": "ParentTerminated",
        "order": 3
      },
      {
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "reason": "ExplicitTermination",
        "order": 4
      }
    ],
    "eatp_records_count": 4,
    "all_eatp_records_are_audit_anchors_subtype_agent_terminated": true,
    "budget_reclamation": {
      "grandchild_to_child_a": { "financial": 1400 },
      "child_a_to_root": { "financial": 3500 },
      "child_b_to_root": { "financial": 2800 }
    }
  }
}
```

### TV-04: Tool Allowlist Violation

**Validates**: I-05 (tool subsetting)

```json
{
  "test_id": "TV-04",
  "description": "Child requesting a tool not in parent's allowed set is rejected",
  "setup": {
    "parent": {
      "instance_id": "00000000-0000-0000-0000-000000000001",
      "state": "Running",
      "active_envelope": {
        "financial": { "limit": 10000 },
        "operational": { "allowed": ["read_file", "grep"], "blocked": ["write_file", "bash"] },
        "temporal": { "window_start": "2026-03-21T00:00:00Z", "window_end": "2026-03-22T00:00:00Z" },
        "data_access": { "ceiling": "CONFIDENTIAL", "scopes": ["all"] },
        "communication": { "recipients": ["*"], "channels": ["internal"] }
      },
      "budget_remaining": { "financial": 10000 }
    }
  },
  "input": {
    "child_spec": {
      "spec_id": "writer-agent",
      "name": "Writer Agent",
      "description": "Needs write access",
      "capabilities": ["file-write"],
      "tool_ids": ["read_file", "write_file"],
      "envelope": {
        "financial": { "limit": 1000 },
        "operational": { "allowed": ["read_file", "write_file"], "blocked": [] },
        "temporal": { "window_start": "2026-03-21T00:00:00Z", "window_end": "2026-03-22T00:00:00Z" },
        "data_access": { "ceiling": "RESTRICTED", "scopes": ["all"] },
        "communication": { "recipients": ["*"], "channels": ["internal"] }
      },
      "memory_config": "session_only",
      "max_lifetime": null,
      "max_children": null,
      "max_depth": null,
      "required_context_keys": [],
      "produced_context_keys": [],
      "metadata": {}
    },
    "parent_id": "00000000-0000-0000-0000-000000000001"
  },
  "expected": {
    "outcome": "error",
    "error_type": "ToolNotInParent",
    "error_tool_id": "write_file",
    "parent_budget_unchanged": true,
    "eatp_records": [
      { "type": "AuditAnchor", "subtype": "spawn_rejected", "reason": "tool_not_in_parent" }
    ]
  }
}
```

### TV-05: Max Depth Exceeded Across Multiple Ancestors

**Validates**: I-09 (max depth enforcement)

```json
{
  "test_id": "TV-05",
  "description": "Spawn fails when delegation depth exceeds ancestor's max_depth limit",
  "setup": {
    "instances": [
      {
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "spec_id": "root",
        "parent_id": null,
        "state": "Running",
        "max_depth": null,
        "depth": 0
      },
      {
        "instance_id": "00000000-0000-0000-0000-000000000002",
        "spec_id": "supervisor",
        "parent_id": "00000000-0000-0000-0000-000000000001",
        "state": "Running",
        "max_depth": 2,
        "depth": 1
      },
      {
        "instance_id": "00000000-0000-0000-0000-000000000003",
        "spec_id": "worker-a",
        "parent_id": "00000000-0000-0000-0000-000000000002",
        "state": "Running",
        "max_depth": null,
        "depth": 2
      },
      {
        "instance_id": "00000000-0000-0000-0000-000000000004",
        "spec_id": "worker-b",
        "parent_id": "00000000-0000-0000-0000-000000000003",
        "state": "Running",
        "max_depth": null,
        "depth": 3
      }
    ]
  },
  "input": {
    "child_spec": {
      "spec_id": "too-deep-agent",
      "name": "Too Deep Agent",
      "description": "Would exceed supervisor's max_depth",
      "capabilities": [],
      "tool_ids": [],
      "envelope": {
        "financial": { "limit": 100 },
        "operational": { "allowed": [], "blocked": [] },
        "temporal": { "window_start": "2026-03-21T00:00:00Z", "window_end": "2026-03-22T00:00:00Z" },
        "data_access": { "ceiling": "PUBLIC", "scopes": [] },
        "communication": { "recipients": [], "channels": [] }
      },
      "memory_config": "session_only",
      "max_lifetime": null,
      "max_children": null,
      "max_depth": null,
      "required_context_keys": [],
      "produced_context_keys": [],
      "metadata": {}
    },
    "parent_id": "00000000-0000-0000-0000-000000000004"
  },
  "expected": {
    "outcome": "error",
    "error_type": "MaxDepthExceeded",
    "error_detail": {
      "parent_id": "00000000-0000-0000-0000-000000000004",
      "depth_limit": 2,
      "limiting_ancestor": "00000000-0000-0000-0000-000000000002",
      "current_depth_from_ancestor": 3,
      "explanation": "Supervisor at depth 1 set max_depth=2. Child would be at depth 4 (3 levels below supervisor), exceeding limit."
    },
    "parent_budget_unchanged": true,
    "eatp_records": [
      { "type": "AuditAnchor", "subtype": "spawn_rejected", "reason": "max_depth_exceeded" }
    ]
  }
}
```

### TV-06: Idempotent Termination

**Validates**: Edge case 8.3 (terminate already-terminated)

```json
{
  "test_id": "TV-06",
  "description": "Terminating an already-terminated agent is a no-op",
  "setup": {
    "instances": [
      {
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "spec_id": "already-done",
        "parent_id": null,
        "state": { "Terminated": { "reason": "Timeout" } }
      }
    ]
  },
  "input": {
    "terminate_instance_id": "00000000-0000-0000-0000-000000000001",
    "reason": { "type": "ExplicitTermination", "by": "00000000-0000-0000-0000-fffffffffff1" }
  },
  "expected": {
    "outcome": "success",
    "state_unchanged": true,
    "original_reason_preserved": "Timeout",
    "eatp_records_count": 0
  }
}
```

### TV-07: Lineage Query

**Validates**: I-04 (immutable lineage), Operation 4.6

```json
{
  "test_id": "TV-07",
  "description": "Lineage returns root-to-instance path",
  "setup": {
    "instances": [
      { "instance_id": "aaa", "parent_id": null, "depth": 0 },
      { "instance_id": "bbb", "parent_id": "aaa", "depth": 1 },
      { "instance_id": "ccc", "parent_id": "bbb", "depth": 2 },
      { "instance_id": "ddd", "parent_id": "ccc", "depth": 3 }
    ]
  },
  "input": {
    "lineage_of": "ddd"
  },
  "expected": {
    "lineage": ["aaa", "bbb", "ccc", "ddd"]
  }
}
```

---

## Appendix A: What the SDK Does NOT Do

These responsibilities belong to the orchestration layer (kaizen-agents), not the SDK:

| Responsibility | Why Not SDK |
|---|---|
| Decide WHAT agent to spawn | Requires understanding task semantics (LLM) |
| Decide the envelope allocation | Requires estimating resource needs per subtask (LLM-assisted policy) |
| Generate AgentSpec descriptions | Requires understanding the domain (LLM) |
| Set memory_config based on task requirements | Requires task analysis (policy) |
| Decide whether to spawn or handle inline | Requires judgment about complexity (LLM) |
| Match capabilities to subtask requirements | Requires semantic matching beyond string comparison (LLM) |
| Budget rebalancing across siblings | Requires prioritization intelligence (orchestration policy) |
| Vacancy resolution (choosing acting parent) | Requires organizational context (orchestration policy) |

## Appendix B: Relationship to Other L3 Specs

| Spec | Dependency Direction | Integration Point |
|---|---|---|
| M1-01: EnvelopeTracker | AgentFactory DEPENDS ON EnvelopeTracker | `AgentInstance.budget_tracker` is an EnvelopeTracker. Spawn debits parent's tracker. Termination reclaims to parent's tracker. |
| M1-02: ScopedContext | AgentFactory DEPENDS ON ScopedContext (weak) | `required_context_keys` validated against parent's ScopedContext at spawn. Child receives a projected scope from parent. |
| M1-03: Messaging | AgentFactory DEPENDS ON MessageRouter (weak) | At spawn, a parent-child communication channel is established via MessageRouter. Termination tears down channels. |
| M1-05: Plan DAG | Plan DAG DEPENDS ON AgentFactory | PlanExecutor uses AgentFactory to spawn agents for plan nodes. PlanValidator checks envelope feasibility via factory's validation logic. |
