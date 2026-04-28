# Data/Control Flow: Agent Delegation Chain

## Overview

This document traces the complete data and control flow when a parent agent spawns a child, delegates a task, and collects results — the fundamental L3 operation.

## Flow: Parent Delegates Task to Child

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. PLAN COMPOSITION (kaizen-agents / orchestration layer)       │
│    LLM decides to spawn a child agent for subtask              │
│    Produces: AgentSpec + AllocationRequest                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. ENVELOPE SPLITTING (SDK / EnvelopeSplitter)                  │
│    Input:  parent envelope + AllocationRequest (ratios)         │
│    Check:  ratio sums <= 1.0, overrides are tighter, NaN/Inf   │
│    Output: child ConstraintEnvelope                             │
│    EATP:   Delegation Record + Constraint Envelope              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. AGENT SPAWNING (SDK / AgentFactory.spawn())                  │
│    Preconditions (8 checks):                                    │
│      1. Parent exists and is Running/Waiting                    │
│      2. Child envelope satisfies monotonic tightening (I-01)    │
│      3. Parent has sufficient remaining budget (I-07)           │
│      4. Parent not at max_children limit                        │
│      5. Delegation depth not exceeded (I-09)                    │
│      6. Child's tools are subset of parent's tools (I-05)      │
│      7. Required context keys exist in parent scope (I-10)      │
│      8. Context keys accessible at parent's clearance           │
│                                                                 │
│    On success:                                                  │
│      - AgentInstance created (state: Pending)                   │
│      - Registered in AgentInstanceRegistry                      │
│      - Parent's EnvelopeTracker debited                         │
│      - EnvelopeTracker initialized for child                    │
│      - EATP Genesis/Delegation record created                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. CHANNEL SETUP (SDK / MessageRouter.create_channel())         │
│    Creates 2 unidirectional channels:                           │
│      parent → child (capacity: configurable)                    │
│      child → parent (capacity: configurable)                    │
│    Atomic: both succeed or neither is created                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. CONTEXT SCOPING (SDK / ContextScope.create_child())          │
│    Parent creates child scope with:                             │
│      read_projection:  subset of parent's (monotonic)           │
│      write_projection: what child can produce                   │
│      effective_clearance: <= parent's clearance                  │
│    Child scope starts empty — reads traverse to parent          │
│    EATP: Delegation Record (scope creation)                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. DELEGATION MESSAGE (SDK / MessageRouter.route())             │
│    Parent sends DelegationPayload:                              │
│      task_description, context_snapshot, child envelope,        │
│      deadline, priority                                         │
│    Router validation (8 steps):                                 │
│      TTL → sender existence → recipient existence →             │
│      recipient state → communication envelope →                 │
│      directionality → channel existence → deliver               │
│    EATP: Audit Anchor (message sent)                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. CHILD EXECUTION (Orchestration layer)                        │
│    AgentInstance state: Pending → Running                       │
│    Child executes task within its envelope                      │
│    Every action checked by child's EnvelopeEnforcer:            │
│      StrictEnforcer → EnvelopeTracker → gradient zone           │
│    Periodic StatusPayload messages to parent                    │
│    May send ClarificationPayload (blocking or non-blocking)    │
│    All costs recorded in child's EnvelopeTracker               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. COMPLETION (SDK / MessageRouter.route())                     │
│    Child sends CompletionPayload:                               │
│      result, context_updates, resource_consumed, success        │
│      correlation_id → originating Delegation message_id         │
│    Child state: Running → Completed                             │
│    EATP: Audit Anchor (completion)                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9. CONTEXT MERGE (SDK / ContextScope.merge_child_results())     │
│    Parent merges child's context_updates into parent scope      │
│    Only keys within child's write_projection are merged         │
│    Conflicts resolved: child wins (default)                     │
│    Skipped keys reported in MergeResult                         │
│    EATP: Audit Anchor (context merged)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 10. BUDGET RECLAMATION (SDK / EnvelopeTracker.reclaim())        │
│     Reclaimed = child_allocated - child_consumed                │
│     Parent's remaining budget increases                         │
│     Gradient zone may relax (HELD → FLAGGED if below threshold) │
│     EATP: Audit Anchor (budget reclaimed)                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 11. CHANNEL TEARDOWN (SDK / MessageRouter.close_channels_for()) │
│     Both channels closed                                        │
│     Undelivered messages → DeadLetterStore                      │
│     Child deregistered (optional cleanup)                       │
│     EATP: Audit Anchor (channel closed)                         │
└─────────────────────────────────────────────────────────────────┘
```

## Error / Escalation Flows

### Budget Exhaustion During Child Execution

```
Child action → EnvelopeEnforcer.check_action()
  → EnvelopeTracker: usage > hold_threshold
    → Verdict: HELD
      → Action placed in HoldQueue
      → Child state: Running → Waiting { reason: HumanApproval }
      → EscalationPayload sent to parent (severity: BudgetAlert)
      → Resolution: human/orchestration/timeout
        → If approved: resume
        → If timeout: Verdict → BLOCKED
          → Child state: Waiting → Terminated { reason: BudgetExhausted }
          → Cascade to child's children
```

### Non-Retryable Failure in Child

```
Child fails (non-retryable, required)
  → Child state: Running → Failed
  → CompletionPayload { success: false, error_detail: "..." }
  → Parent processes failure
  → Budget reclamation from failed child
  → If this is a plan node: gradient rule G5 → NodeHeld
    → Wait for resolution (human/recomposition/timeout)
```

### Cascade Termination

```
Parent terminated (any reason)
  → AgentFactory.terminate(parent_id, reason)
    → Collect all_descendants(parent_id)
    → Sort by depth (deepest first)
    → For each descendant (leaf → root):
      1. State → Terminated { reason: ParentTerminated }
      2. Reclaim unused budget to direct parent
      3. Close channels
      4. EATP Audit Anchor
    → Finally: parent state → Terminated
    → Reclaim parent's unused budget to grandparent
```

## Data Flow Diagram

```
                   ┌──────────────┐
                   │  Orchestration│
                   │    Layer      │
                   │ (kaizen-     │
                   │  agents)     │
                   └──────┬───────┘
                          │ AgentSpec + AllocationRequest
                          ▼
  ┌───────────────────────────────────────────────────┐
  │                    SDK LAYER                       │
  │                                                    │
  │  ┌──────────────┐    ┌──────────────┐             │
  │  │ Envelope     │    │ Scoped       │             │
  │  │ Splitter     │    │ Context      │             │
  │  │  (split)     │    │  (scope)     │             │
  │  └──────┬───────┘    └──────┬───────┘             │
  │         │ child_envelope    │ child_scope          │
  │         ▼                   ▼                      │
  │  ┌──────────────────────────────────────┐         │
  │  │         AgentFactory                  │         │
  │  │  (spawn → validate → register)       │         │
  │  └──────┬────────────────┬──────────────┘         │
  │         │                │                         │
  │         ▼                ▼                         │
  │  ┌───────────┐    ┌───────────┐                   │
  │  │ Instance  │    │ Message   │                    │
  │  │ Registry  │    │ Router    │                    │
  │  │ (lineage) │    │ (channels)│                    │
  │  └───────────┘    └─────┬─────┘                   │
  │                         │ DelegationPayload        │
  │                         ▼                          │
  │  ┌──────────────────────────────────────┐         │
  │  │       EnvelopeEnforcer                │         │
  │  │  (StrictEnforcer + Tracker + HoldQ)   │         │
  │  │  validates every child action         │         │
  │  └──────────────────────────────────────┘         │
  │                                                    │
  └────────────────────────────────────────────────────┘
```
