# Data/Control Flow: Budget Lifecycle

## Overview

Traces the lifecycle of budget allocation, consumption, gradient transitions, and reclamation through the EnvelopeTracker system.

## Budget Lifecycle Phases

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: INITIALIZATION                                         │
│                                                                 │
│  Root agent receives ConstraintEnvelope from supervisor         │
│  EnvelopeTracker initialized:                                   │
│    cost_consumed_financial = 0                                  │
│    actions_performed = 0                                        │
│    child_allocations = {}                                       │
│    reclaimed_total = 0                                          │
│    cost_history = []                                            │
│                                                                 │
│  remaining() = full envelope budget                             │
│  usage_pct() = 0.0 for all dimensions                          │
│  EATP: Audit Anchor (tracker_created)                           │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 2: CONSUMPTION (Agent performs actions)                    │
│                                                                 │
│  For each action:                                               │
│    1. EnvelopeEnforcer.check_action(context)                    │
│       → StrictEnforcer checks non-depletable dims (ops, data,  │
│         communication) → APPROVED or BLOCKED                    │
│       → EnvelopeTracker checks depletable dims (financial,      │
│         temporal, action count)                                  │
│    2. If APPROVED/FLAGGED: action proceeds                      │
│    3. EnvelopeEnforcer.record_action(context, actual_cost)      │
│       → CostEntry appended to cost_history                     │
│       → Running totals updated atomically                      │
│    4. Verdict returned reflects post-action zone                │
│                                                                 │
│  Zone transitions (per dimension, monotonic within agent):      │
│    0%─────────80%────────95%─────────100%                       │
│    AUTO_APPROVED  FLAGGED   HELD     BLOCKED                    │
│                                                                 │
│  Multi-dimension: most restrictive zone wins                    │
│  EATP: Audit Anchor per action (subtype varies by zone)         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 3: CHILD ALLOCATION (Agent spawns children)               │
│                                                                 │
│  Step 1: EnvelopeSplitter.split(parent_envelope, allocations)   │
│    → Validates ratio sums ≤ 1.0 per depletable dimension       │
│    → Validates overrides are tighter                            │
│    → Produces child envelopes                                   │
│                                                                 │
│  Step 2: EnvelopeTracker.allocate_to_child(child_id, amount)    │
│    → Deducts from parent's remaining budget                     │
│    → child_allocations[child_id] = amount                       │
│    → remaining() decreases                                      │
│    → Parent's usage_pct() increases (allocated = "committed")   │
│                                                                 │
│  Budget accounting:                                              │
│    remaining = envelope_limit                                    │
│              - cost_consumed (own actions)                       │
│              - sum(child_allocations)                            │
│              + reclaimed_total                                   │
│                                                                 │
│  EATP: Delegation Record + Constraint Envelope per child        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 4: CHILD EXECUTION (Children consume their budgets)       │
│                                                                 │
│  Each child has its own EnvelopeTracker                          │
│  Child tracks consumption independently                         │
│  Child may spawn grandchildren (recursive allocation)           │
│                                                                 │
│  Parent sees:                                                    │
│    - Own remaining budget (after deductions + reclamations)     │
│    - Cannot see child's internal consumption directly           │
│    - Receives StatusPayload with ResourceSnapshot periodically  │
│                                                                 │
│  Budget hierarchy:                                              │
│    Root:    $10,000 total                                       │
│      own:  $1,500 consumed                                      │
│      A:    $3,000 allocated (A consumed $2,100)                 │
│      B:    $4,000 allocated (B consumed $1,800)                 │
│      reserve: $1,500 remaining                                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 5: RECLAMATION (Children complete/terminate)              │
│                                                                 │
│  When child reaches terminal state (Completed/Failed/Term):     │
│    1. Child's final consumption = child_tracker.cost_consumed   │
│    2. Parent calls reclaim(child_id, child_consumed)            │
│    3. reclaimed = allocated - consumed                          │
│    4. Parent's remaining increases by reclaimed amount          │
│    5. Parent's usage_pct() decreases                            │
│    6. Zone may relax (e.g., HELD → FLAGGED)                    │
│                                                                 │
│  Example:                                                       │
│    A completed: consumed $2,100 of $3,000 → reclaim $900       │
│    Parent remaining: $1,500 + $900 = $2,400                    │
│    Parent usage: ($1,500 + $2,100 + $4,000) / $10,000 = 76%   │
│    → Zone: AUTO_APPROVED (below 80% flag threshold)            │
│                                                                 │
│  If child tracker unavailable (crash):                          │
│    reclaim(child_id, child_consumed = allocated)                │
│    → Conservative default: assume all budget consumed           │
│    → Reclaimed = 0                                              │
│                                                                 │
│  EATP: Audit Anchor (budget_reclaimed)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 6: ZONE RELAXATION (Exception to monotonicity)            │
│                                                                 │
│  Normally: zones only escalate (AUTO → FLAG → HELD → BLOCKED)  │
│  Exception: reclamation may de-escalate                         │
│                                                                 │
│  If reclamation brings usage below hold threshold:              │
│    HELD → FLAGGED (zone relaxes)                                │
│  If reclamation brings usage below flag threshold:              │
│    FLAGGED → AUTO_APPROVED (zone relaxes)                       │
│                                                                 │
│  This is the ONLY mechanism for zone relaxation                 │
│  (besides PACT emergency bypass which creates a new envelope)   │
│                                                                 │
│  EATP: Audit Anchor (zone transition)                           │
└─────────────────────────────────────────────────────────────────┘
```

## Held Action Resolution Flow

```
Action checked → Verdict: HELD
  │
  ├─► Cost committed (budget consumed)
  ├─► Hold entry created in HoldQueue
  ├─► Hold ID returned in Verdict
  ├─► Downstream operations suspended
  │
  ├─► Resolution path 1: HUMAN
  │     Human reviews hold in queue
  │     → Approve: downstream resumes
  │     → Reject: escalate to BLOCKED
  │
  ├─► Resolution path 2: ORCHESTRATION
  │     kaizen-agents FailureDiagnoser
  │     → Submit PlanModification
  │     → Re-route around held action
  │
  └─► Resolution path 3: TIMEOUT
        gradient.resolution_timeout expires
        → Auto-escalate: HELD → BLOCKED
        → Terminate affected plan branch
```

## Five-Dimension Budget Summary

| Dimension     | Depletion Model                        | Tracked By                    | Gradient Applies?               |
| ------------- | -------------------------------------- | ----------------------------- | ------------------------------- |
| Financial     | Cumulative spend (f64)                 | Running sum of CostEntry.cost | Yes (flag/hold thresholds)      |
| Operational   | Action count (u64) + access control    | Counter + set membership      | Quota: yes. Access: binary.     |
| Temporal      | Wall-clock window or duration          | Start time + elapsed          | Yes (time remaining fraction)   |
| Data Access   | Classification ceiling + scope set     | Static per-access check       | No (binary: allowed/blocked)    |
| Communication | Per-recipient/channel quota (optional) | Per-target counter            | Optional (if quotas configured) |

Financial and Temporal deplete continuously. Operational has both depleting (quota) and non-depleting (allowed/blocked) components. Data Access and Communication are primarily access control with optional quotas.
