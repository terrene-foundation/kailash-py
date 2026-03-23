# L3 Primitive Specification: EnvelopeTracker + EnvelopeSplitter + EnvelopeEnforcer

**Status**: Proposed
**Priority**: Phase 1a -- all other L3 primitives depend on this
**Scope**: Language-agnostic. Both kailash-rs and kailash-py implement independently from this spec.

---

## 1. Overview

L3 autonomy requires agents that spawn child agents, allocate budgets, and operate within constraint envelopes over time. The existing PACT/EATP infrastructure provides validate-at-delegation-time envelope checking (StrictEnforcer) and five-dimensional constraint envelopes (ConstraintEnvelope). What is missing is **continuous runtime budget tracking**, **budget division across children**, and **non-bypassable middleware** that wraps every L3 operation.

This specification defines three primitives:

- **EnvelopeTracker** -- Maintains running totals of resource consumption across all five PACT constraint dimensions. Reports remaining budget, usage percentages, and gradient zone transitions. Monotonically decreasing budget (except on reclamation from completed children).

- **EnvelopeSplitter** -- Divides a parent envelope into child envelopes according to allocation ratios. Enforces that the sum of child allocations plus parent reserve never exceeds the parent's available budget. Produces child ConstraintEnvelope instances that are provably tighter than the parent.

- **EnvelopeEnforcer** -- Non-bypassable middleware that sits in the execution path of every L3 operation (tool execution, message send, agent spawn, context write). Combines the existing StrictEnforcer (per-action checking) with EnvelopeTracker (continuous budget) and HoldQueue (held actions). Cannot be constructed without an envelope. Cannot be disabled at runtime.

Together these three primitives form the foundation that AgentFactory, ScopedContext, Inter-Agent Messaging, and Plan DAG all depend on. No L3 operation proceeds without envelope enforcement.

---

## 2. Types

All types use pseudocode notation. Field types use common names: `string`, `uuid`, `f64`, `u64`, `bool`, `optional<T>`, `list<T>`, `map<K,V>`, `duration`, `timestamp`, `enum`. Implementations choose language-idiomatic representations.

### 2.1 GradientZone

```
enum GradientZone {
    AUTO_APPROVED   // Proceed without intervention
    FLAGGED         // Proceed, log for review
    HELD            // Suspend, wait for resolution
    BLOCKED         // Reject immediately
}
```

**Ordering**: BLOCKED > HELD > FLAGGED > AUTO_APPROVED. A zone can only be tightened (moved toward BLOCKED), never loosened, within a single delegation chain.

### 2.2 PlanGradient

```
struct PlanGradient {
    // How many retries before holding on retryable failure
    retry_budget: u64                               // default: 2

    // What zone to apply when retries are exhausted
    after_retry_exhaustion: GradientZone            // default: HELD

    // How long to wait for held resolution before escalating to BLOCKED
    resolution_timeout: duration                    // default: 300 seconds

    // How to handle optional node failures
    optional_node_failure: GradientZone             // default: FLAGGED

    // Budget consumption thresholds (fraction of allocated envelope, 0.0-1.0)
    budget_flag_threshold: f64                      // default: 0.80
    budget_hold_threshold: f64                      // default: 0.95

    // Per-dimension gradient thresholds (optional overrides)
    // If set, these override the global budget thresholds for the named dimension
    dimension_thresholds: map<string, DimensionGradient>
}
```

**Constraints**:
- `0 <= budget_flag_threshold < budget_hold_threshold <= 1.0`
- `retry_budget >= 0`
- `resolution_timeout > 0`
- `after_retry_exhaustion` must be HELD or BLOCKED (not AUTO_APPROVED or FLAGGED)
- `optional_node_failure` must be AUTO_APPROVED, FLAGGED, or HELD (not BLOCKED -- use required node for that)
- Envelope violations are always BLOCKED. This is an invariant, not a configurable field.

### 2.3 DimensionGradient

```
struct DimensionGradient {
    flag_threshold: f64     // fraction at which zone transitions to FLAGGED
    hold_threshold: f64     // fraction at which zone transitions to HELD
    // BLOCKED is always at 1.0 (envelope boundary) -- non-configurable
}
```

**Constraints**:
- `0.0 <= flag_threshold < hold_threshold <= 1.0`

### 2.4 CostEntry

```
struct CostEntry {
    action: string              // identifier of the action performed
    dimension: string           // which dimension this cost applies to
    cost: f64                   // amount consumed (always >= 0)
    timestamp: timestamp        // when the action was recorded
    agent_instance_id: uuid     // which agent instance incurred this cost
    metadata: map<string, any>  // optional context (tool name, model, etc.)
}
```

**Constraints**:
- `cost >= 0.0` (costs are always non-negative)
- `cost` must be finite (not NaN, not Inf)
- `dimension` must be one of: `"financial"`, `"operational"`, `"temporal"` (the three depletable dimensions)

### 2.5 BudgetRemaining

```
struct BudgetRemaining {
    financial_remaining: optional<f64>      // none if no financial limit set
    temporal_remaining: optional<duration>   // none if no temporal limit set
    actions_remaining: optional<u64>         // none if no action limit set
    per_dimension: map<string, f64>          // remaining amount per dimension
}
```

**Semantics**: A `none` value means the dimension has no budget limit (unbounded). A zero value means the budget is exactly exhausted. A negative value is impossible -- the tracker must reject actions that would cause it.

### 2.6 DimensionUsage

```
struct DimensionUsage {
    financial_pct: optional<f64>        // 0.0 to 1.0+, none if unbounded
    temporal_pct: optional<f64>         // 0.0 to 1.0+, none if unbounded
    operational_pct: optional<f64>      // 0.0 to 1.0+, none if unbounded
    per_dimension: map<string, f64>     // usage fraction per dimension
    highest_zone: GradientZone          // the most restrictive zone across all dimensions
}
```

**Semantics**: Usage percentage can theoretically exceed 1.0 if consumption was recorded before enforcement could block it (race condition window). `highest_zone` is the maximum zone across all dimensions -- if any dimension is HELD, `highest_zone` is at least HELD.

### 2.7 ReclaimResult

```
struct ReclaimResult {
    reclaimed_financial: f64        // amount of financial budget returned
    reclaimed_actions: u64          // number of action quota returned
    reclaimed_temporal: duration    // amount of temporal budget returned
    child_id: uuid                  // which child the budget was reclaimed from
    child_total_consumed: f64       // what the child actually spent (for audit)
    child_total_allocated: f64      // what the child was originally allocated
}
```

### 2.8 EnvelopeTracker

```
struct EnvelopeTracker {
    // Immutable after construction
    envelope: ConstraintEnvelope        // the envelope being tracked against
    gradient: PlanGradient              // gradient thresholds for zone transitions
    created_at: timestamp               // when tracking started

    // Mutable state (thread-safe / concurrency-safe)
    cost_consumed_financial: f64        // cumulative financial cost
    actions_performed: u64              // cumulative action count
    cost_history: list<CostEntry>       // ordered log of all consumption events
    child_allocations: map<uuid, f64>   // financial budget allocated to each child
    reclaimed_total: f64                // total financial budget reclaimed from children
}
```

**Construction**: An EnvelopeTracker can only be constructed with a valid ConstraintEnvelope. There is no default constructor and no way to create a tracker without an envelope.

### 2.9 AllocationRequest

```
struct AllocationRequest {
    child_id: string                                        // identifier for this child
    financial_ratio: f64                                    // fraction of parent's financial budget (0.0-1.0)
    temporal_ratio: f64                                     // fraction of parent's temporal budget (0.0-1.0)
    operational_override: optional<OperationalConstraints>  // must be tighter than parent
    data_access_override: optional<DataAccessConstraints>   // must be tighter than parent
    communication_override: optional<CommunicationConstraints> // must be tighter than parent
}
```

**Constraints**:
- `0.0 <= financial_ratio <= 1.0`
- `0.0 <= temporal_ratio <= 1.0`
- Ratios must be finite (not NaN, not Inf)
- If an override is provided, it must satisfy `is_tighter_than(parent_dimension)` for that dimension
- If no override is provided, the child inherits the parent's constraint for that dimension

### 2.10 SplitError

```
enum SplitError {
    RATIO_SUM_EXCEEDS_ONE {
        dimension: string       // "financial" or "temporal"
        total: f64              // the sum that exceeded 1.0
    }
    NEGATIVE_RATIO {
        child_id: string
        dimension: string
        value: f64
    }
    NON_FINITE_RATIO {
        child_id: string
        dimension: string
        value: f64              // the NaN or Inf value
    }
    OVERRIDE_NOT_TIGHTER {
        child_id: string
        dimension: string
    }
    RESERVE_INVALID {
        value: f64              // must be 0.0-1.0
    }
    EMPTY_ALLOCATIONS           // at least one child required
    PARENT_DIMENSION_UNBOUNDED {
        dimension: string       // cannot split a ratio of an unbounded dimension
    }
}
```

### 2.11 EnvelopeSplitter

```
struct EnvelopeSplitter {
    // Stateless. All methods are pure functions.
}
```

EnvelopeSplitter has no mutable state. It is a namespace for pure splitting operations.

### 2.12 Verdict

```
enum Verdict {
    APPROVED {
        zone: GradientZone      // AUTO_APPROVED or FLAGGED
        dimension_usage: DimensionUsage
    }
    HELD {
        dimension: string       // which dimension triggered the hold
        current_usage: f64      // current usage fraction
        threshold: f64          // the threshold that was crossed
        hold_id: uuid           // identifier for tracking resolution
    }
    BLOCKED {
        dimension: string       // which dimension triggered the block
        detail: string          // human-readable explanation
        requested: f64          // what was requested
        available: f64          // what was available
    }
}
```

### 2.13 EnforcementContext

```
struct EnforcementContext {
    action: string              // identifier of the action being checked
    estimated_cost: f64         // estimated financial cost of the action
    agent_instance_id: uuid     // which agent is performing the action
    dimension_costs: map<string, f64>  // estimated cost per dimension
    metadata: map<string, any>  // additional context for audit
}
```

### 2.14 EnvelopeEnforcer

```
struct EnvelopeEnforcer {
    tracker: EnvelopeTracker        // shared reference (multiple readers)
    enforcer: StrictEnforcer        // reuses existing per-action checking
    hold_queue: HoldQueue           // reuses existing hold queue
}
```

**Construction**: An EnvelopeEnforcer can only be constructed with all three components. There is no way to create an enforcer without a tracker (and therefore without an envelope). There is no `disable()` method, no `bypass()` method, no runtime flag to skip enforcement.

---

## 3. Behavioral Invariants

These invariants MUST hold in any conforming implementation. They are the correctness criteria for both test suites.

### INV-1: Monotonically Decreasing Budget

`EnvelopeTracker.remaining()` must return values that are monotonically decreasing over time, with exactly one exception: reclamation from a completed child. After reclamation, the remaining budget increases by at most the amount originally allocated to that child minus what the child consumed.

Formally: for any two calls `r1 = remaining()` at time `t1` and `r2 = remaining()` at time `t2` where `t2 > t1`, if no reclamation occurred between `t1` and `t2`, then `r2.financial_remaining <= r1.financial_remaining` and `r2.actions_remaining <= r1.actions_remaining`.

### INV-2: Split Conservation

`EnvelopeSplitter.split()` must reject if the sum of allocation ratios for any depletable dimension exceeds 1.0 when combined with the reserve percentage. Formally: for every depletable dimension `d`, `reserve_pct + sum(allocation[i].ratio_d for all i) <= 1.0`. Equality is permitted (exact exhaustion of the budget). Exceeding by any amount, including floating-point epsilon, must be rejected.

### INV-3: Non-Bypassable Enforcement

`EnvelopeEnforcer` cannot be disabled, paused, or bypassed at runtime. There is no method, flag, environment variable, or configuration that causes the enforcer to skip checking. The only way to widen an envelope is through the PACT emergency bypass protocol, which creates a new Delegation Record with a time-limited expanded envelope -- it does not disable the enforcer.

### INV-4: Envelope Violations Are Always BLOCKED

When an action would cause any dimension to exceed its envelope boundary (usage > 1.0), the verdict is BLOCKED. This is non-configurable. The gradient thresholds (flag, hold) apply to intermediate zones. The boundary itself is always a hard block.

### INV-5: Reclamation Ceiling

Budget reclaimed from a completed child must not exceed the amount originally allocated to that child. Formally: `reclaimed_amount <= allocated_amount - consumed_amount`, and `reclaimed_amount >= 0`.

### INV-6: Child Tighter Than Parent

Every child envelope produced by `EnvelopeSplitter.split()` must satisfy `is_tighter_than(parent)` for every dimension. This is checked at split time. If a dimension override violates monotonic tightening, the split is rejected.

### INV-7: Finite Arithmetic Only

All allocation ratios, cost values, and budget amounts must be finite real numbers. NaN and Infinity must be rejected at the boundary (constructor, method input) with an explicit error. Implementations must not propagate NaN through budget calculations.

### INV-8: Zero Budget Means Blocked

If the remaining budget for any depletable dimension is exactly zero, any action that would consume from that dimension must be BLOCKED. Zero remaining is not a "warning" state -- it is a hard stop. The only way to proceed is reclamation (from a completed child) or emergency bypass.

### INV-9: Atomic Cost Recording

Recording a consumption event and updating the running total must be atomic. Two concurrent `record_consumption()` calls must not lose either cost entry. The cost history must contain every recorded event in timestamp order. Implementations choose their concurrency mechanism (atomics, locks, channels), but the atomicity guarantee is mandatory.

### INV-10: Gradient Zone Monotonicity per Dimension

Within a single agent's lifetime, a dimension's gradient zone can only move toward BLOCKED (AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED). It never moves backward. A dimension that has reached HELD stays HELD or transitions to BLOCKED. The only exception is reclamation, which may move a HELD dimension back to FLAGGED (but only if the reclaimed budget brings usage below the hold threshold).

---

## 4. Operations

### 4.1 EnvelopeTracker Operations

#### 4.1.1 `new(envelope, gradient) -> EnvelopeTracker`

**Inputs**: A valid ConstraintEnvelope and a PlanGradient configuration.
**Outputs**: A new EnvelopeTracker with zero consumption.
**Preconditions**: Envelope must be structurally valid (no NaN in limits). Gradient must satisfy its own constraints (Section 2.2).
**Postconditions**: All running totals are zero. `remaining()` equals the full envelope budget. `usage_pct()` returns 0.0 for all dimensions.
**Errors**: `InvalidEnvelope` if envelope contains NaN/Inf. `InvalidGradient` if gradient violates constraints.

#### 4.1.2 `record_consumption(entry: CostEntry) -> Verdict`

**Inputs**: A CostEntry with non-negative, finite cost.
**Outputs**: A Verdict indicating the resulting gradient zone after recording this consumption.
**Preconditions**: `entry.cost >= 0.0`, `entry.cost` is finite, `entry.dimension` is a valid depletable dimension.
**Postconditions**: Running total for the dimension is increased by `entry.cost`. Entry is appended to cost history. If the new total crosses a gradient threshold, the Verdict reflects the new zone.
**Errors**: `InvalidCost` if cost is negative, NaN, or Inf. `UnknownDimension` if dimension is not recognized. `BudgetExceeded` if the action would push usage above 1.0 (returns `Verdict::BLOCKED`).

**Zone determination logic**:
1. Compute `new_usage = (consumed + entry.cost) / budget_limit`
2. If `new_usage > 1.0` -> `Verdict::BLOCKED` (reject, do not record)
3. Look up dimension-specific gradient thresholds (fall back to global if not set)
4. If `new_usage >= hold_threshold` -> `Verdict::HELD`
5. If `new_usage >= flag_threshold` -> `Verdict::APPROVED { zone: FLAGGED }`
6. Otherwise -> `Verdict::APPROVED { zone: AUTO_APPROVED }`

When the verdict is BLOCKED, the cost entry is NOT recorded (the action did not happen). When the verdict is HELD, the cost entry IS recorded (the action cost is committed, but downstream work is suspended).

#### 4.1.3 `remaining() -> BudgetRemaining`

**Inputs**: None.
**Outputs**: Current remaining budget across all dimensions.
**Preconditions**: None.
**Postconditions**: Pure read. No state change.
**Errors**: None.

**Computation**:
- `financial_remaining = envelope.financial_limit - cost_consumed_financial - sum(child_allocations) + reclaimed_total`
- `temporal_remaining = envelope.temporal_end - now()` (wall-clock for time-window envelopes) OR `envelope.max_duration - elapsed` (for duration envelopes)
- `actions_remaining = envelope.action_limit - actions_performed`
- Returns `none` for any dimension that has no limit set.

#### 4.1.4 `usage_pct() -> DimensionUsage`

**Inputs**: None.
**Outputs**: Current usage as a fraction (0.0 to 1.0+) per dimension, plus the highest gradient zone.
**Preconditions**: None.
**Postconditions**: Pure read. No state change.
**Errors**: None.

#### 4.1.5 `can_afford(estimated: EnforcementContext) -> bool`

**Inputs**: An EnforcementContext with estimated costs per dimension.
**Outputs**: `true` if the estimated costs would not push any dimension past its envelope boundary (> 1.0). `false` otherwise.
**Preconditions**: Estimated costs must be finite and non-negative.
**Postconditions**: Pure read. No state change. This is advisory -- the actual `record_consumption` is authoritative.
**Errors**: `InvalidCost` if estimates are NaN/Inf/negative.

#### 4.1.6 `allocate_to_child(child_id: uuid, financial_amount: f64) -> Result`

**Inputs**: Child identifier and the financial amount being allocated.
**Outputs**: Success or error.
**Preconditions**: `financial_amount > 0`, `financial_amount <= financial_remaining`, child_id must not already have an allocation.
**Postconditions**: `child_allocations[child_id] = financial_amount`. `remaining()` decreases by the allocated amount.
**Errors**: `InsufficientBudget` if amount exceeds remaining. `DuplicateChild` if child_id already allocated. `InvalidAmount` if amount is zero, negative, NaN, or Inf.

#### 4.1.7 `reclaim(child_id: uuid, child_consumed: f64) -> ReclaimResult`

**Inputs**: Child identifier and the amount the child actually consumed.
**Outputs**: A ReclaimResult describing what was returned.
**Preconditions**: `child_id` must have an existing allocation. `child_consumed >= 0`. `child_consumed <= child_allocations[child_id]`.
**Postconditions**: `reclaimed_total` increases by `(allocated - consumed)`. `child_allocations[child_id]` is removed. If reclamation causes usage to drop below a gradient threshold, zone may relax (per INV-10 exception).
**Errors**: `UnknownChild` if child_id has no allocation. `ConsumedExceedsAllocated` if child_consumed > allocated (indicates a bug in the child's enforcement). `InvalidAmount` if child_consumed is NaN/Inf/negative.

#### 4.1.8 `cost_history() -> list<CostEntry>`

**Inputs**: None.
**Outputs**: The ordered list of all recorded cost entries.
**Preconditions**: None.
**Postconditions**: Pure read.
**Errors**: None.

### 4.2 EnvelopeSplitter Operations

#### 4.2.1 `split(parent, allocations, reserve_pct) -> Result<list<(string, ConstraintEnvelope)>, list<SplitError>>`

**Inputs**:
- `parent`: A ConstraintEnvelope to divide.
- `allocations`: A list of AllocationRequest, one per child.
- `reserve_pct`: Fraction of the parent's budget to keep as reserve (0.0-1.0).

**Outputs**: A list of `(child_id, child_envelope)` pairs, one per allocation request.

**Preconditions**:
- `allocations` is non-empty.
- `0.0 <= reserve_pct <= 1.0`, finite.
- Each allocation has finite, non-negative ratios.
- `reserve_pct + sum(financial_ratio for all allocations) <= 1.0`.
- `reserve_pct + sum(temporal_ratio for all allocations) <= 1.0`.
- Every override (if present) satisfies `is_tighter_than()` for its dimension against the parent.
- For depletable dimensions being split by ratio, the parent must have a finite budget. Splitting a ratio of an unbounded dimension is an error (what is 30% of infinity?).

**Postconditions**:
- Each child envelope satisfies `child.is_tighter_than(parent)`.
- `child.financial_limit = parent.financial_limit * allocation.financial_ratio` (for each child).
- `child.temporal_limit = parent.temporal_limit * allocation.temporal_ratio` (for each child).
- For non-depletable dimensions (Data Access, Communication) without overrides, children inherit the parent's constraints unchanged.
- For non-depletable dimensions with overrides, children use the override (already validated as tighter).
- Operational dimension: if no override, child inherits parent's allowed/blocked sets. If override provided, must be tighter.

**Errors**: Returns all applicable SplitError values (not just the first). Implementations must validate all allocations before returning.

#### 4.2.2 `validate_split(parent, allocations, reserve_pct) -> Result<(), list<SplitError>>`

**Inputs**: Same as `split()`.
**Outputs**: Ok if the split would succeed; Err with all violations if it would fail.
**Preconditions**: None (this IS the validation).
**Postconditions**: No envelopes are created. Pure validation.
**Errors**: Same error types as `split()`.

### 4.3 EnvelopeEnforcer Operations

#### 4.3.1 `new(tracker, enforcer, hold_queue) -> EnvelopeEnforcer`

**Inputs**: An EnvelopeTracker, a StrictEnforcer (existing), and a HoldQueue (existing).
**Outputs**: A new EnvelopeEnforcer.
**Preconditions**: All three components must be provided. No defaults, no nulls.
**Postconditions**: Enforcer is active and cannot be deactivated.
**Errors**: None (type system prevents null construction).

#### 4.3.2 `check_action(context: EnforcementContext) -> Verdict`

**Inputs**: An EnforcementContext describing the action to be checked.
**Outputs**: A Verdict.
**Preconditions**: Context must have valid, finite cost estimates.
**Postconditions**:
- If APPROVED (AUTO_APPROVED or FLAGGED): The action may proceed. The cost has NOT been recorded yet (call `record_action` after execution).
- If HELD: The action is placed in the hold_queue. The cost has NOT been recorded. Downstream operations are suspended until resolution.
- If BLOCKED: The action is rejected. No cost is recorded.
**Errors**: `InvalidContext` if estimated costs are NaN/Inf/negative.

**Check sequence**:
1. StrictEnforcer checks the action against the envelope's non-depletable dimensions (operational allowed/blocked, data access, communication). If rejected -> `Verdict::BLOCKED`.
2. EnvelopeTracker evaluates the estimated cost against depletable dimensions. Returns the gradient zone.
3. If the zone is HELD, create a hold entry in HoldQueue.
4. Return the Verdict.

#### 4.3.3 `record_action(context: EnforcementContext, actual_cost: f64) -> Verdict`

**Inputs**: The same context that was checked, plus the actual cost incurred.
**Outputs**: A Verdict reflecting the post-action state.
**Preconditions**: `check_action` must have returned APPROVED for this context. `actual_cost >= 0`, finite.
**Postconditions**: The actual cost is recorded in the tracker. If the actual cost pushed a dimension past a threshold, the returned Verdict may differ from the pre-check verdict (e.g., estimated cost was under the flag threshold but actual cost crossed it).
**Errors**: `ActionNotApproved` if check_action was not called first. `InvalidCost` if actual_cost is NaN/Inf/negative.

#### 4.3.4 `tracker() -> EnvelopeTracker (read-only reference)`

**Inputs**: None.
**Outputs**: Read-only access to the underlying tracker for budget queries.
**Preconditions**: None.
**Postconditions**: No mutation path exposed.
**Errors**: None.

---

## 5. PACT Record Mapping

Every operation that modifies state or makes a governance decision creates an EATP record. This section maps operations to the five EATP record types per PACT Section 5.7.

### 5.1 EATP Record Types (Reference)

1. **Genesis Record** -- Created once for a root entity. Establishes the trust anchor.
2. **Delegation Record** -- Created when authority is delegated from parent to child. Contains the Constraint Envelope.
3. **Constraint Envelope** -- The five-dimensional constraint set attached to a Delegation Record.
4. **Capability Attestation** -- Certifies that an agent possesses a specific capability.
5. **Audit Anchor** -- Captures a governance event with full context at the moment it occurred.

### 5.2 Operation-to-Record Mapping

| Operation | EATP Record(s) | Subtype | Key Fields |
|---|---|---|---|
| `EnvelopeTracker.new()` | Audit Anchor | `tracker_created` | envelope_hash, gradient_config, agent_instance_id |
| `EnvelopeTracker.record_consumption()` returning AUTO_APPROVED | Audit Anchor | `action_approved` | action, dimension, cost, remaining, zone |
| `EnvelopeTracker.record_consumption()` returning FLAGGED | Audit Anchor | `action_flagged` | action, dimension, cost, remaining, zone, threshold_crossed |
| `EnvelopeTracker.record_consumption()` returning HELD | Audit Anchor | `action_held` | action, dimension, cost, remaining, zone, threshold, hold_id |
| `EnvelopeTracker.record_consumption()` returning BLOCKED | Audit Anchor | `action_blocked` | action, dimension, requested, available |
| `EnvelopeTracker.allocate_to_child()` | Delegation Record + Constraint Envelope | -- | parent_id, child_id, allocated_amount, child_envelope |
| `EnvelopeTracker.reclaim()` | Audit Anchor | `budget_reclaimed` | child_id, allocated, consumed, reclaimed |
| `EnvelopeSplitter.split()` success | Delegation Record + Constraint Envelope (one per child) | -- | parent_envelope_hash, child_id, child_envelope, allocation_ratios |
| `EnvelopeSplitter.split()` failure | Audit Anchor | `split_rejected` | parent_envelope_hash, errors, allocation_ratios |
| `EnvelopeEnforcer.check_action()` | (delegates to tracker -- records created there) | -- | -- |
| `EnvelopeEnforcer.record_action()` | (delegates to tracker -- records created there) | -- | -- |

### 5.3 Audit Anchor Mandatory Fields

Every Audit Anchor created by these primitives must include:

- `timestamp`: When the event occurred
- `agent_instance_id`: Which agent instance triggered the event
- `effective_envelope_hash`: Hash of the envelope at the moment of the event
- `dimension_usage_snapshot`: Current usage percentages at the moment of the event
- `gradient_zone`: The determined zone
- `parent_chain`: The delegation chain from root to this agent (positional address)

---

## 6. Verification Gradient Integration

The verification gradient (PACT Section 5.6) defines four zones that apply to every envelope-checked operation. This section specifies how gradient thresholds interact with envelope tracking.

### 6.1 Per-Dimension Gradient Application

Each depletable dimension has its own gradient thresholds. When multiple dimensions are involved in a single action, the MOST RESTRICTIVE zone across all dimensions applies.

**Example**: An action costs $500 (financial) and consumes 1 action (operational).
- Financial usage after action: 82% -> FLAGGED (threshold at 80%)
- Operational usage after action: 45% -> AUTO_APPROVED
- Result: FLAGGED (the more restrictive zone)

### 6.2 Default Gradient Thresholds

If no per-dimension gradient is configured, the global thresholds from PlanGradient apply:

| Usage Range | Zone |
|---|---|
| 0% to `budget_flag_threshold` (default 80%) | AUTO_APPROVED |
| `budget_flag_threshold` to `budget_hold_threshold` (default 95%) | FLAGGED |
| `budget_hold_threshold` to 100% | HELD |
| Above 100% (envelope boundary) | BLOCKED (non-configurable) |

### 6.3 Gradient-to-Envelope Interaction Matrix

| Dimension | Depletable? | Gradient Applied? | Zone Determination |
|---|---|---|---|
| Financial | Yes | Yes | Usage fraction vs. thresholds |
| Operational | Partially | Yes for quota; No for allowed/blocked | Quota: usage fraction vs. thresholds. Allowed/blocked: binary APPROVED or BLOCKED |
| Temporal | Yes | Yes | Time remaining fraction vs. thresholds |
| Data Access | No | No | Binary: allowed or BLOCKED (per StrictEnforcer) |
| Communication | No | No | Binary: allowed or BLOCKED (per StrictEnforcer) |

### 6.4 Zone Transition Events

When a dimension's zone transitions (e.g., from AUTO_APPROVED to FLAGGED), the tracker must:

1. Create an Audit Anchor capturing the transition
2. Include the old zone, new zone, dimension, and current usage
3. Emit a notification event that monitoring systems can subscribe to

Zone transitions are determined by threshold crossings, not by absolute values. If usage jumps from 70% to 92% in a single action, the transition is AUTO_APPROVED -> FLAGGED (skipping the intermediate observation).

### 6.5 Resolution of HELD Actions

When an action is HELD:

1. The action's cost is committed (the budget is consumed)
2. The hold is placed in the HoldQueue with a resolution deadline (`gradient.resolution_timeout`)
3. Three resolution paths exist:
   a. **Human resolution**: A human reviews and approves/rejects via the hold queue
   b. **Orchestration resolution**: The LLM orchestration layer (kaizen-agents) provides a PlanModification
   c. **Timeout**: If `resolution_timeout` expires, the hold escalates to BLOCKED
4. After resolution, downstream operations may resume (if approved) or terminate (if blocked)

---

## 7. What Exists Today

Both teams have substantial infrastructure to build on. No primitive starts from zero.

### 7.1 Rust (kailash-rs)

| Component | Module Path | What It Provides | L3 Reuse |
|---|---|---|---|
| `ConstraintEnvelope` | `crates/trust-plane/src/envelope.rs` | Five-dimensional constraint model with `is_tighter_than()` | Direct reuse as the envelope type inside EnvelopeTracker |
| `StrictEnforcer` | `crates/trust-plane/src/enforcer.rs` | Per-action checking against all 5 dimensions | Direct reuse inside EnvelopeEnforcer |
| `intersect()` | `crates/trust-plane/src/intersection.rs` | Commutative envelope intersection algebra | Reuse for computing effective envelopes during split |
| `HoldQueue` | `crates/trust-plane/src/holds.rs` | Queue for HELD actions awaiting resolution | Direct reuse inside EnvelopeEnforcer |
| Five constraint dimensions | `crates/eatp/src/constraints/` (`financial.rs`, `operational.rs`, `temporal.rs`, `data_access.rs`, `communication.rs`) | Per-dimension constraint types and validation | Reuse as the dimension types inside ConstraintEnvelope |
| `DelegationChain` | `crates/eatp/src/delegation.rs` | Delegation with scope subsetting | Reuse for parent-child envelope validation |
| `GovernedTaodRunner` | `crates/eatp/src/governed.rs` | Trust-governed TAOD execution with verification gradient | Pattern reference for EnvelopeEnforcer middleware wrapping |
| `BudgetTracker` | `crates/kailash-kaizen/src/cost/budget.rs` | Financial budget tracking with atomic CAS | Foundation for financial dimension of EnvelopeTracker |
| `CostTracker` | `crates/kailash-kaizen/src/cost/tracker.rs` | Per-token cost calculation | Foundation for cost recording in EnvelopeTracker |
| Constraint types | `crates/trust-plane/src/constraints.rs` | Constraint validation and comparison | Reuse for override validation in AllocationRequest |

### 7.2 Python (kailash-py)

| Component | Module Path | What It Provides | L3 Reuse |
|---|---|---|---|
| `ConstraintEnvelope` (adapter) | `packages/kailash-pact/src/pact/governance/envelope_adapter.py` | Python-side envelope with PACT integration | Foundation for EnvelopeTracker |
| `GradientEngine` | `packages/kailash-pact/src/pact/governance/gradient.py` | Gradient zone evaluation | Direct reuse for zone determination in EnvelopeTracker |
| Envelope definitions | `packages/kailash-pact/src/pact/governance/envelopes.py` | Envelope construction and validation | Foundation for EnvelopeSplitter |
| `Verdict` | `packages/kailash-pact/src/pact/governance/verdict.py` | Verdict types (approved, held, blocked) | Direct reuse as Verdict return type |
| Constraint evaluator | `src/kailash/trust/constraints/evaluator.py` | Per-dimension constraint evaluation | Reuse inside StrictEnforcer equivalent |
| Dimension model | `src/kailash/trust/constraints/dimension.py` | Dimension type definitions | Reuse for dimension-specific tracking logic |
| Budget tracker | `src/kailash/trust/constraints/budget_tracker.py` | Budget tracking primitives | Foundation for financial dimension of EnvelopeTracker |
| Budget store | `src/kailash/trust/constraints/budget_store.py` | Persistent budget storage | Foundation for durable budget state |
| Spend tracker | `src/kailash/trust/constraints/spend_tracker.py` | Spend recording and querying | Foundation for cost history in EnvelopeTracker |
| Strict enforcer | `src/kailash/trust/enforce/strict.py` | Per-action enforcement | Direct reuse inside EnvelopeEnforcer |
| Governance engine | `packages/kailash-pact/src/pact/governance/engine.py` | PACT governance orchestration with gradient | Pattern reference for EnvelopeEnforcer integration |

---

## 8. Edge Cases

### 8.1 Budget Exactly Zero

When remaining budget for a depletable dimension reaches exactly zero:
- Any further action consuming from that dimension is BLOCKED (INV-8).
- `can_afford(0.0)` returns `true` (a zero-cost action is allowed even with zero budget).
- `can_afford(epsilon)` returns `false` for any `epsilon > 0`.
- The gradient zone for that dimension is HELD if usage equals the hold threshold, or BLOCKED if usage equals 1.0.

### 8.2 Concurrent Budget Consumption

When two agents (or two parallel operations within one agent) consume budget simultaneously:
- Both `record_consumption()` calls must be atomic (INV-9).
- The second call to complete may observe that the first call exhausted the budget. In that case, the second call is BLOCKED and its cost is not recorded.
- Implementations must handle the race condition where both calls estimate they can afford the action (via `can_afford`), but by the time `record_consumption` executes, only one can succeed. `can_afford` is advisory; `record_consumption` is authoritative.
- The audit trail must reflect the actual order of recording, not the order of estimation.

### 8.3 Child Allocated Budget But Never Starts

When a child agent is allocated budget (via `allocate_to_child()` or `split()`) but never starts execution:
- The allocated budget remains reserved. It is subtracted from the parent's remaining budget.
- The parent must explicitly reclaim the budget by calling `reclaim(child_id, child_consumed=0)`.
- There is no automatic timeout-based reclamation. The orchestration layer (kaizen-agents) decides when to reclaim, using the vacancy handling rules from PACT Section 5.5.
- If the parent terminates before reclaiming, the budget is lost (the parent's parent may reclaim from the parent per the same rules).

### 8.4 Reclamation from Terminated (Not Completed) Child

When a child agent is terminated (killed, timed out, or failed) rather than completing normally:
- The parent calls `reclaim(child_id, child_consumed=X)` where `X` is the child's tracker's total consumption at termination time.
- If the child's tracker is unavailable (e.g., crash), the parent must reclaim with `child_consumed = child_allocations[child_id]` (assume all budget was consumed). This is the conservative default -- it prevents budget inflation.
- The Audit Anchor for this reclamation must include the termination reason and whether the consumed amount was actual or conservative-default.

### 8.5 NaN/Inf in Allocation Ratios

- NaN in any ratio field -> `SplitError::NON_FINITE_RATIO`. The entire split is rejected.
- Positive or negative Infinity in any ratio field -> `SplitError::NON_FINITE_RATIO`.
- NaN in `reserve_pct` -> `SplitError::RESERVE_INVALID`.
- Implementations must check for non-finite values BEFORE performing any arithmetic. Do not rely on IEEE 754 NaN propagation -- detect and reject at the boundary.

### 8.6 Parent Budget Already Partially Consumed

When `split()` is called on a parent that has already consumed some budget:
- The split ratios apply to the parent's **original** envelope, not the remaining budget.
- The EnvelopeSplitter does not know about the parent's consumption -- it splits the envelope definition.
- The parent's EnvelopeTracker must separately validate that the total allocation (via `allocate_to_child()`) does not exceed what remains.
- This is a two-step process: (1) EnvelopeSplitter produces child envelopes, (2) parent's EnvelopeTracker records the allocation. Step 2 may fail if insufficient budget remains.

### 8.7 Dimension Without a Limit (Unbounded)

Some dimensions may have no limit set (e.g., no financial budget, no action quota):
- Unbounded dimensions cannot be split by ratio (`SplitError::PARENT_DIMENSION_UNBOUNDED`). What is 30% of unlimited?
- Unbounded dimensions are inherited as-is by children (also unbounded).
- `usage_pct()` returns `none` for unbounded dimensions.
- `remaining()` returns `none` for unbounded dimensions.
- Gradient thresholds do not apply to unbounded dimensions (there is no denominator for the fraction).

### 8.8 Empty Allocation List

`split([])` (no children) is rejected with `SplitError::EMPTY_ALLOCATIONS`. A split that produces no children is meaningless.

### 8.9 Single-Dimension Overflow in Multi-Dimension Action

An action may have costs in multiple dimensions. If the financial dimension would be APPROVED but the operational dimension would be BLOCKED:
- The entire action is BLOCKED (most restrictive zone wins).
- No costs are recorded for any dimension (the action did not happen).
- The Verdict identifies the blocking dimension.

---

## 9. Conformance Test Vectors

Both implementations must produce identical outputs for these test vectors. All values are JSON. Timestamps use ISO 8601. UUIDs are fixed for reproducibility.

### Test Vector 1: Basic Budget Tracking

**Setup**:
```json
{
  "test": "basic_budget_tracking",
  "envelope": {
    "financial_limit": 100.0,
    "action_limit": 10,
    "temporal_limit_seconds": 3600
  },
  "gradient": {
    "budget_flag_threshold": 0.80,
    "budget_hold_threshold": 0.95
  }
}
```

**Actions**:
```json
[
  {
    "action": "record_consumption",
    "entry": {
      "action": "llm_call_1",
      "dimension": "financial",
      "cost": 30.0,
      "agent_instance_id": "00000000-0000-0000-0000-000000000001"
    },
    "expected_verdict": {
      "type": "APPROVED",
      "zone": "AUTO_APPROVED"
    },
    "expected_remaining": {
      "financial_remaining": 70.0,
      "actions_remaining": 10
    },
    "expected_usage": {
      "financial_pct": 0.30
    }
  },
  {
    "action": "record_consumption",
    "entry": {
      "action": "llm_call_2",
      "dimension": "financial",
      "cost": 55.0,
      "agent_instance_id": "00000000-0000-0000-0000-000000000001"
    },
    "expected_verdict": {
      "type": "APPROVED",
      "zone": "FLAGGED"
    },
    "expected_remaining": {
      "financial_remaining": 15.0
    },
    "expected_usage": {
      "financial_pct": 0.85
    }
  },
  {
    "action": "record_consumption",
    "entry": {
      "action": "llm_call_3",
      "dimension": "financial",
      "cost": 12.0,
      "agent_instance_id": "00000000-0000-0000-0000-000000000001"
    },
    "expected_verdict": {
      "type": "HELD",
      "dimension": "financial",
      "current_usage": 0.97
    },
    "expected_remaining": {
      "financial_remaining": 3.0
    }
  },
  {
    "action": "record_consumption",
    "entry": {
      "action": "llm_call_4",
      "dimension": "financial",
      "cost": 5.0,
      "agent_instance_id": "00000000-0000-0000-0000-000000000001"
    },
    "expected_verdict": {
      "type": "BLOCKED",
      "dimension": "financial",
      "requested": 5.0,
      "available": 3.0
    },
    "expected_remaining": {
      "financial_remaining": 3.0
    },
    "note": "Cost NOT recorded because action was blocked"
  }
]
```

### Test Vector 2: Envelope Split and Reclamation

**Setup**:
```json
{
  "test": "split_and_reclaim",
  "parent_envelope": {
    "financial_limit": 1000.0,
    "action_limit": 100,
    "temporal_limit_seconds": 7200
  },
  "allocations": [
    {
      "child_id": "analyzer",
      "financial_ratio": 0.30,
      "temporal_ratio": 0.40
    },
    {
      "child_id": "reviewer",
      "financial_ratio": 0.50,
      "temporal_ratio": 0.40
    }
  ],
  "reserve_pct": 0.10
}
```

**Expected Split Output**:
```json
{
  "result": "ok",
  "children": [
    {
      "child_id": "analyzer",
      "envelope": {
        "financial_limit": 300.0,
        "temporal_limit_seconds": 2880
      }
    },
    {
      "child_id": "reviewer",
      "envelope": {
        "financial_limit": 500.0,
        "temporal_limit_seconds": 2880
      }
    }
  ],
  "remaining_after_split": {
    "financial_remaining": 200.0,
    "note": "10% reserve (100) + 10% unallocated (100) = 200"
  }
}
```

**Reclamation Sequence**:
```json
[
  {
    "action": "allocate_to_child",
    "child_id": "00000000-0000-0000-0000-000000000010",
    "financial_amount": 300.0,
    "expected_parent_remaining": 700.0
  },
  {
    "action": "allocate_to_child",
    "child_id": "00000000-0000-0000-0000-000000000020",
    "financial_amount": 500.0,
    "expected_parent_remaining": 200.0
  },
  {
    "action": "reclaim",
    "child_id": "00000000-0000-0000-0000-000000000010",
    "child_consumed": 180.0,
    "expected_result": {
      "reclaimed_financial": 120.0,
      "child_total_consumed": 180.0,
      "child_total_allocated": 300.0
    },
    "expected_parent_remaining": 320.0,
    "note": "200 existing + 120 reclaimed = 320"
  }
]
```

### Test Vector 3: Split Rejection (Ratios Exceed 1.0)

**Setup**:
```json
{
  "test": "split_rejection_ratios",
  "parent_envelope": {
    "financial_limit": 1000.0
  },
  "allocations": [
    { "child_id": "a", "financial_ratio": 0.50, "temporal_ratio": 0.30 },
    { "child_id": "b", "financial_ratio": 0.40, "temporal_ratio": 0.30 },
    { "child_id": "c", "financial_ratio": 0.20, "temporal_ratio": 0.30 }
  ],
  "reserve_pct": 0.05
}
```

**Expected Output**:
```json
{
  "result": "error",
  "errors": [
    {
      "type": "RATIO_SUM_EXCEEDS_ONE",
      "dimension": "financial",
      "total": 1.15,
      "detail": "reserve(0.05) + a(0.50) + b(0.40) + c(0.20) = 1.15"
    }
  ]
}
```

### Test Vector 4: NaN and Boundary Rejection

**Setup**:
```json
{
  "test": "nan_and_boundary_rejection",
  "parent_envelope": {
    "financial_limit": 100.0,
    "action_limit": 10
  },
  "gradient": {
    "budget_flag_threshold": 0.80,
    "budget_hold_threshold": 0.95
  }
}
```

**Actions**:
```json
[
  {
    "action": "record_consumption",
    "entry": {
      "action": "bad_action",
      "dimension": "financial",
      "cost": "NaN"
    },
    "expected_error": "InvalidCost: cost must be finite and non-negative"
  },
  {
    "action": "record_consumption",
    "entry": {
      "action": "negative_cost",
      "dimension": "financial",
      "cost": -5.0
    },
    "expected_error": "InvalidCost: cost must be finite and non-negative"
  },
  {
    "action": "split",
    "allocations": [
      { "child_id": "x", "financial_ratio": "Infinity", "temporal_ratio": 0.5 }
    ],
    "reserve_pct": 0.0,
    "expected_error": {
      "type": "NON_FINITE_RATIO",
      "child_id": "x",
      "dimension": "financial"
    }
  },
  {
    "action": "record_consumption",
    "entry": {
      "action": "exact_budget",
      "dimension": "financial",
      "cost": 100.0
    },
    "expected_verdict": {
      "type": "HELD",
      "dimension": "financial",
      "current_usage": 1.0,
      "note": "Usage at exactly 1.0 is HELD (not BLOCKED) because the action fits within the boundary. The next action will be BLOCKED."
    }
  },
  {
    "action": "record_consumption",
    "entry": {
      "action": "one_more",
      "dimension": "financial",
      "cost": 0.01
    },
    "expected_verdict": {
      "type": "BLOCKED",
      "dimension": "financial",
      "requested": 0.01,
      "available": 0.0
    }
  }
]
```

**Note on exact-boundary behavior**: When an action's cost would bring usage to exactly 100% (1.0), the action is allowed but classified as HELD (because 1.0 >= hold_threshold of 0.95). The BLOCKED zone only applies when the action would push usage ABOVE 100%. This distinction is important: the action that exactly exhausts the budget succeeds; the next action is blocked.

### Test Vector 5: Multi-Dimension Enforcement (Most Restrictive Wins)

**Setup**:
```json
{
  "test": "multi_dimension_enforcement",
  "envelope": {
    "financial_limit": 100.0,
    "action_limit": 5
  },
  "gradient": {
    "budget_flag_threshold": 0.80,
    "budget_hold_threshold": 0.95,
    "dimension_thresholds": {
      "operational": {
        "flag_threshold": 0.60,
        "hold_threshold": 0.80
      }
    }
  }
}
```

**Actions**:
```json
[
  {
    "action": "record_consumption",
    "entries": [
      { "dimension": "financial", "cost": 50.0 },
      { "dimension": "operational", "cost": 1 }
    ],
    "expected_verdict": {
      "type": "APPROVED",
      "zone": "AUTO_APPROVED"
    },
    "expected_usage": {
      "financial_pct": 0.50,
      "operational_pct": 0.20
    },
    "note": "Both dimensions under their flag thresholds"
  },
  {
    "action": "record_consumption",
    "entries": [
      { "dimension": "financial", "cost": 10.0 },
      { "dimension": "operational", "cost": 2 }
    ],
    "expected_verdict": {
      "type": "APPROVED",
      "zone": "FLAGGED"
    },
    "expected_usage": {
      "financial_pct": 0.60,
      "operational_pct": 0.60
    },
    "note": "Financial is still AUTO_APPROVED (60% < 80%), but Operational is FLAGGED (60% >= 60% operational flag). Most restrictive wins: FLAGGED."
  },
  {
    "action": "record_consumption",
    "entries": [
      { "dimension": "financial", "cost": 5.0 },
      { "dimension": "operational", "cost": 1 }
    ],
    "expected_verdict": {
      "type": "HELD",
      "dimension": "operational"
    },
    "expected_usage": {
      "financial_pct": 0.65,
      "operational_pct": 0.80
    },
    "note": "Financial is AUTO_APPROVED (65% < 80%), but Operational is HELD (80% >= 80% operational hold). Most restrictive wins: HELD."
  }
]
```

### Test Vector 6: Reclamation Restores Zone

**Setup**:
```json
{
  "test": "reclamation_restores_zone",
  "envelope": {
    "financial_limit": 100.0
  },
  "gradient": {
    "budget_flag_threshold": 0.80,
    "budget_hold_threshold": 0.95
  }
}
```

**Sequence**:
```json
[
  {
    "action": "record_consumption",
    "entry": { "dimension": "financial", "cost": 10.0 },
    "note": "Parent spends 10. Remaining: 90."
  },
  {
    "action": "allocate_to_child",
    "child_id": "00000000-0000-0000-0000-000000000099",
    "financial_amount": 80.0,
    "expected_parent_remaining": 10.0,
    "expected_parent_usage_financial_pct": 0.90,
    "note": "10 consumed + 80 allocated = 90 used. 90/100 = 0.90. Zone: FLAGGED."
  },
  {
    "action": "record_consumption",
    "entry": { "dimension": "financial", "cost": 6.0 },
    "expected_verdict": {
      "type": "HELD",
      "dimension": "financial",
      "current_usage": 0.96,
      "note": "10+6=16 consumed, 80 allocated. (16+80)/100 = 0.96 >= 0.95 hold threshold."
    }
  },
  {
    "action": "reclaim",
    "child_id": "00000000-0000-0000-0000-000000000099",
    "child_consumed": 30.0,
    "expected_result": {
      "reclaimed_financial": 50.0
    },
    "expected_parent_remaining": 54.0,
    "expected_parent_usage_financial_pct": 0.46,
    "note": "16 consumed + 30 child consumed = 46 total used. 46/100 = 0.46. Zone relaxes from HELD back to AUTO_APPROVED."
  }
]
```

---

## Appendix A: Dimension Depletion Semantics

Each of the five PACT dimensions has different depletion behavior. Implementations must handle each correctly.

| Dimension | Depletion Model | Unit | Tracking Mechanism |
|---|---|---|---|
| Financial | Counter (cumulative spend) | Currency amount (f64) | Running sum of costs |
| Operational | Quota (action count) + Access Control (allowed/blocked) | Action count (u64) for quota; set membership for access | Counter for quota; set lookup for access |
| Temporal | Clock (wall-time window or duration limit) | Duration remaining | Start time + elapsed calculation |
| Data Access | None (access control only) | Classification level + scope set | Static check per access (no depletion) |
| Communication | Optional quota per recipient/channel | Message count per target | Per-target counter (if quotas configured) |

**Key distinction**: Financial and Temporal deplete continuously. Operational has both a depleting component (action quota) and a non-depleting component (allowed/blocked sets). Data Access and Communication are primarily access control (binary allowed/denied) with optional quotas for Communication.

## Appendix B: Glossary

- **Effective Envelope**: The intersection of all ancestor envelopes from root to the current agent. Always computed, never stored.
- **Monotonic Tightening**: Children can only have envelopes that are equal to or tighter than their parent's. `is_tighter_than()` checks this.
- **Deny-Overrides**: When composed allowed and blocked sets overlap, blocked takes precedence.
- **Gradient Zone**: One of four verification outcomes (AUTO_APPROVED, FLAGGED, HELD, BLOCKED) that determines what happens after an action is checked.
- **Hold Queue**: A persistent queue of HELD actions awaiting resolution by a human or the orchestration layer.
- **Reclamation**: The process of returning unused budget from a completed child to its parent.
- **Reserve**: The fraction of a parent's budget not allocated to any child, kept for the parent's own operations.
