# Data/Control Flow: Plan DAG Execution

## Overview

This document traces the execution of a Plan DAG from composition through completion, including gradient-driven failure handling and runtime modifications.

## Flow: Plan Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. PLAN COMPOSITION (kaizen-agents / orchestration layer)       │
│    LLM TaskDecomposer: objective → subtasks                     │
│    LLM PlanComposer: subtasks → Plan DAG                        │
│    LLM AgentDesigner: subtask → AgentSpec (per node)            │
│    LLM EnvelopeAllocator: parent envelope → per-node allocation │
│    Output: Plan { nodes, edges, envelope, gradient }            │
│    Plan state: Draft                                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. PLAN VALIDATION (SDK / PlanValidator.validate())             │
│                                                                 │
│    validate_structure():                                        │
│      - Cycle detection (topological sort)                       │
│      - Referential integrity (edges → nodes)                    │
│      - Input mapping consistency                                │
│      - Root/leaf existence                                      │
│      - Unique node IDs, no self-edges                           │
│                                                                 │
│    validate_envelopes():                                        │
│      - Budget summation ≤ plan envelope                         │
│      - Per-node monotonic tightening                            │
│      - Temporal feasibility (critical path)                     │
│                                                                 │
│    validate_resources():                                        │
│      - Concurrency limits                                       │
│      - Per-node resource requirements                           │
│                                                                 │
│    On success: Plan state: Draft → Validated                    │
│    On failure: Returns ALL errors (not just first)              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. PLAN EXECUTION LOOP (SDK / PlanExecutor.execute())           │
│    Plan state: Validated → Executing                            │
│                                                                 │
│    repeat:                                                      │
│      a. Identify all Ready nodes (dependencies satisfied)       │
│      b. For each Ready node:                                    │
│         → Spawn agent via AgentFactory (see delegation flow)    │
│         → Emit NodeStarted                                      │
│         → Node state: Ready → Running                           │
│      c. Wait for any running node to complete/fail              │
│      d. On completion/failure: classify via gradient (Step 4)   │
│      e. Update node state, emit PlanEvent                       │
│      f. Re-evaluate which nodes are now Ready                   │
│    until: no Ready nodes AND no Running nodes                   │
│                                                                 │
│    If all required nodes Completed: emit PlanCompleted          │
│    If any required node in terminal failure: emit PlanFailed    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. GRADIENT CLASSIFICATION (SDK / deterministic)                │
│                                                                 │
│    G1: NodeCompleted (success)                                  │
│        → AutoApproved. Record output. Continue.                 │
│                                                                 │
│    G2: NodeFailed (retryable, retries remaining)                │
│        → AutoApproved. Increment retry. Re-spawn.               │
│                                                                 │
│    G3: NodeFailed (retries exhausted)                            │
│        → gradient.after_retry_exhaustion (default: Held)        │
│                                                                 │
│    G4: NodeFailed (non-retryable, optional)                     │
│        → gradient.optional_node_failure (default: Flagged)      │
│        → Skip node. Continue.                                   │
│                                                                 │
│    G5: NodeFailed (non-retryable, required)                     │
│        → Held. Suspend downstream. Wait for resolution.         │
│                                                                 │
│    G6: BudgetWarning (flag threshold, e.g. 80%)                 │
│        → Flagged. Emit EnvelopeWarning. Continue.               │
│                                                                 │
│    G7: BudgetWarning (hold threshold, e.g. 95%)                 │
│        → Held. Suspend downstream.                              │
│                                                                 │
│    G8: EnvelopeViolation (any dimension)                        │
│        → BLOCKED (always, non-configurable)                     │
│        → Terminate plan branch (cascade via DataDependency)     │
│                                                                 │
│    G9: ResolutionTimeout (held node exceeds timeout)            │
│        → Blocked. Emit NodeBlocked.                             │
└─────────────────────────────────────────────────────────────────┘
```

## Node Readiness Rules

```
A node transitions from Pending → Ready when ALL of:
  1. All incoming DataDependency sources are Completed
  2. All incoming CompletionDependency sources are in a terminal state
  3. All incoming CoStart sources are at least Running or terminal

Edge type semantics:
  DataDependency:       to REQUIRES from's output. If from fails → to cannot execute.
  CompletionDependency: to waits for from to finish (any outcome). Used for cleanup.
  CoStart:              to starts when from starts. Advisory, not blocking.
```

## Runtime Plan Modification

```
┌─────────────────────────────────────────────────────────────────┐
│ MODIFICATION (kaizen-agents submits PlanModification)           │
│                                                                 │
│  7 mutation types:                                              │
│    AddNode     { node, edges }                                  │
│    RemoveNode  { node_id }         ← Running = Held (INV-15)   │
│    ReplaceNode { old_id, new_node } ← Running = Held (INV-15)  │
│    AddEdge     { edge }            ← Must not create cycle      │
│    RemoveEdge  { from, to }                                     │
│    UpdateSpec  { node_id, spec }   ← Running = rejected         │
│    SkipNode    { node_id, reason }                              │
│                                                                 │
│  Validation:                                                    │
│    1. Check all structural invariants (acyclicity, refs)        │
│    2. Check envelope invariants (budget summation, tightening)  │
│    3. Check running-node protection (INV-PLAN-15)               │
│    4. If valid: apply atomically                                │
│    5. If Validated plan: back to Draft (re-validate)            │
│    6. If Executing plan: re-validate in-place                   │
│    7. Re-evaluate Ready nodes                                   │
│                                                                 │
│  Batch: apply_modifications(list) — all or nothing              │
└─────────────────────────────────────────────────────────────────┘
```

## Example: Diamond Dependency with Optional Failure

```
Plan:
  A ──DataDep──► B (optional)
  A ──DataDep──► C (required)
  B ──CompDep──► D (required)
  C ──DataDep──► D (required)

Execution:
  1. A completes → B and C become Ready (parallel)
  2. B fails (non-retryable, optional) → Gradient G4: Flagged → Skipped
  3. C completes
  4. D readiness check:
     - C → D (DataDep): C is Completed ✓
     - B → D (CompDep): B is Skipped (terminal) ✓
     → D becomes Ready
  5. D executes and completes
  6. PlanCompleted (B was optional, so its skip doesn't fail the plan)
```

## Suspension and Cancellation

```
Suspension (plan.state = Executing → Suspended):
  - No new agents spawned for Ready nodes
  - Running nodes continue (not interrupted)
  - Ready transitions queued, not executed
  - Modifications can be applied during suspension
  - Resume: Suspended → Executing (spawn queued Ready nodes)

Cancellation (plan.state = Executing/Suspended → Cancelled):
  - All Running agents terminated via AgentFactory cascade
  - Pending/Ready nodes → Skipped (reason: "plan_cancelled")
  - Terminal: no further events except mid-termination cleanup
```
