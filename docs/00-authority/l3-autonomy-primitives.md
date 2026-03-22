# L3 Autonomy Primitives — Authority Document

## What It Is

`kaizen.l3` is the Level 3 autonomy layer for the Kailash Kaizen agent framework. It enables agents that spawn child agents, allocate constrained budgets, communicate through typed channels, and execute dynamic task graphs — all under PACT governance.

All L3 primitives are **deterministic** (no LLM calls). The orchestration layer (kaizen-agents) decides WHAT to do; the SDK validates and enforces.

## How to Use It

```python
from kaizen.l3 import (
    # Envelope (Spec 01) — Budget tracking and enforcement
    EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer, GradientZone, Verdict,
    # Context (Spec 02) — Hierarchical scoped context
    ContextScope, ScopeProjection, DataClassification, ContextValue,
    # Messaging (Spec 03) — Typed inter-agent communication
    MessageRouter, MessageChannel, MessageEnvelope, DeadLetterStore, MessageType,
    # Factory (Spec 04) — Runtime agent spawning
    AgentFactory, AgentInstance, AgentInstanceRegistry, AgentSpec,
    # Plan (Spec 05) — DAG task execution
    Plan, PlanValidator, PlanExecutor, apply_modification, apply_modifications,
)
```

## Five Primitives

### 1. EnvelopeTracker / Splitter / Enforcer (`kaizen.l3.envelope`)

Continuous runtime budget tracking across all 5 PACT constraint dimensions (Financial, Operational, Temporal, Data Access, Communication).

- **EnvelopeTracker**: Maintains running totals, reports remaining budget, gradient zone transitions (AUTO_APPROVED → FLAGGED → HELD → BLOCKED)
- **EnvelopeSplitter**: Divides parent envelope into child envelopes by ratio (stateless, pure functions)
- **EnvelopeEnforcer**: Non-bypassable middleware — no disable/bypass/skip methods

### 2. ScopedContext (`kaizen.l3.context`)

Hierarchical context scopes with projection-based access control and PACT knowledge clearance.

- **ContextScope**: Tree of scopes where children see filtered subsets of parent data
- **ScopeProjection**: Glob patterns (`*` = one segment, `**` = any segments) with deny precedence
- **DataClassification**: 5 levels (PUBLIC → TOP_SECRET), agents only see data at or below their clearance

### 3. Inter-Agent Messaging (`kaizen.l3.messaging`)

Typed, envelope-aware communication between agent instances.

- **MessageChannel**: Bounded async channels with priority ordering
- **MessageRouter**: 8-step routing validation (TTL, directionality, correlation)
- **DeadLetterStore**: Bounded ring buffer for undeliverable messages
- 6 typed payloads: Delegation, Status, Clarification, Completion, Escalation, System

### 4. AgentFactory + Registry (`kaizen.l3.factory`)

Runtime agent instantiation with PACT-governed lifecycle.

- **AgentFactory**: `spawn()` with 8 preconditions, cascade `terminate()` (depth-first, leaves first)
- **AgentInstanceRegistry**: Thread-safe registry with lineage/spec indexes
- **AgentInstance**: 6-state lifecycle machine (Pending → Running → Waiting → Completed/Failed/Terminated)

### 5. Plan DAG (`kaizen.l3.plan`)

Dynamic task graphs with verification gradient failure handling.

- **PlanValidator**: Structural + envelope validation (cycle detection, budget summation)
- **PlanExecutor**: Gradient-driven DAG scheduling (G1-G8 rules, all deterministic)
- **PlanModification**: 7 typed mutations (AddNode, RemoveNode, ReplaceNode, AddEdge, RemoveEdge, UpdateSpec, SkipNode) with batch atomicity

## Architecture Decisions

| ADR      | Decision                                                          |
| -------- | ----------------------------------------------------------------- |
| AD-L3-01 | L3 lives in `kaizen/l3/` (not separate package)                   |
| AD-L3-02 | GradientZone reuses VerificationLevel (str-backed enum)           |
| AD-L3-03 | asyncio.PriorityQueue for MessageChannel                          |
| AD-L3-04 | asyncio.Lock for all shared state (overrides threading.Lock rule) |
| AD-L3-13 | Custom dot-segment matcher for projections (not fnmatch)          |
| AD-L3-15 | frozen=True for value types, mutable for entity types             |

## File Structure

```
kaizen/l3/
  __init__.py              # Public API (20 exports)
  envelope/                # Spec 01: Budget tracking + enforcement
    types.py               # GradientZone, CostEntry, Verdict, PlanGradient, etc.
    errors.py              # SplitError, TrackerError, EnforcerError
    splitter.py            # EnvelopeSplitter (stateless)
    tracker.py             # EnvelopeTracker (asyncio.Lock)
    enforcer.py            # EnvelopeEnforcer (non-bypassable)
  context/                 # Spec 02: Hierarchical scoped context
    types.py               # DataClassification, ContextValue, MergeResult
    projection.py          # ScopeProjection (custom segment matcher)
    scope.py               # ContextScope (parent traversal, merge)
  messaging/               # Spec 03: Inter-agent messaging
    types.py               # MessageType, 6 payloads, MessageEnvelope
    channel.py             # MessageChannel (asyncio.PriorityQueue)
    dead_letters.py        # DeadLetterStore (bounded deque)
    router.py              # MessageRouter (routing validation)
    errors.py              # RoutingError, ChannelError
  factory/                 # Spec 04: Agent factory + registry
    instance.py            # AgentInstance, AgentLifecycleState, state machine
    spec.py                # AgentSpec (frozen blueprint)
    registry.py            # AgentInstanceRegistry (asyncio.Lock)
    factory.py             # AgentFactory (spawn, terminate, cascade)
    errors.py              # FactoryError hierarchy
  plan/                    # Spec 05: Plan DAG execution
    types.py               # Plan, PlanNode, PlanEdge, PlanEvent, PlanModification
    validator.py           # PlanValidator (structural + envelope)
    executor.py            # PlanExecutor (gradient-driven scheduling)
    modification.py        # apply_modification, apply_modifications
    errors.py              # PlanError, ValidationError, ExecutionError
```

## Specs

The L3 implementation is based on 6 specification briefs:

- `workspaces/kaizen-l3/briefs/00-l0-l2-remediation.md`
- `workspaces/kaizen-l3/briefs/01-envelope-extensions.md`
- `workspaces/kaizen-l3/briefs/02-scoped-context.md`
- `workspaces/kaizen-l3/briefs/03-messaging.md`
- `workspaces/kaizen-l3/briefs/04-agent-factory.md`
- `workspaces/kaizen-l3/briefs/05-plan-dag.md`
