# L3 Autonomy Primitives -- Overview

L3 enables agents that spawn child agents, allocate constrained budgets, communicate through typed channels, and execute dynamic task graphs -- all under PACT governance.

## Five Primitives

| Primitive                         | Module                | Purpose                                                                    |
| --------------------------------- | --------------------- | -------------------------------------------------------------------------- |
| EnvelopeTracker/Splitter/Enforcer | `kaizen.l3.envelope`  | Continuous budget tracking, division, non-bypassable enforcement           |
| ScopedContext                     | `kaizen.l3.context`   | Hierarchical context with projection-based access control + classification |
| MessageRouter/Channel             | `kaizen.l3.messaging` | Typed inter-agent messaging with routing validation                        |
| AgentFactory/Registry             | `kaizen.l3.factory`   | Runtime agent spawning with lifecycle state machine                        |
| PlanValidator/Executor            | `kaizen.l3.plan`      | DAG task graphs with gradient-driven failure handling                      |

## Key Principle: SDK Boundary

All L3 primitives are **deterministic** -- no LLM calls. The orchestration layer (kaizen-agents) decides WHAT to do; the SDK validates and enforces.

## Quick Import

```python
from kaizen.l3 import (
    EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer, GradientZone, Verdict,
    ContextScope, ScopeProjection, DataClassification, ContextValue,
    MessageRouter, MessageChannel, MessageEnvelope, DeadLetterStore, MessageType,
    AgentFactory, AgentInstance, AgentInstanceRegistry, AgentSpec,
    Plan, PlanValidator, PlanExecutor, apply_modification, apply_modifications,
)
```

## Architecture Decisions

- `asyncio.Lock` for all shared state (overrides threading.Lock per AD-L3-04)
- Custom dot-segment matcher for projections (not fnmatch per AD-L3-13)
- `frozen=True` for value types, mutable for entity types (AD-L3-15)
- GradientZone reuses VerificationLevel enum (AD-L3-02)
- Callback-based PlanExecutor (agent spawning is orchestration concern)

## L3Runtime (Integration Layer)

`L3Runtime` is a convenience class that wires all 5 primitives together, eliminating cross-primitive boilerplate.

### Cross-Primitive Wiring

| Wiring                    | What Happens                                                |
| ------------------------- | ----------------------------------------------------------- |
| Factory -> Enforcer       | `spawn()` registers child agent envelopes with the enforcer |
| Factory -> Router         | `spawn()` creates bidirectional message channels             |
| Factory -> Context        | `spawn()` creates child `ContextScope`                      |
| Enforcer -> Plan          | `AsyncPlanExecutor` checks budget before node execution     |

### Usage

```python
from kaizen.l3 import L3Runtime, AgentSpec

# One-liner: all 5 subsystems wired
runtime = L3Runtime(root_envelope={"financial_limit": 100.0})

# Spawn agent with full integration
spec = AgentSpec(agent_type="analyzer", capabilities=["read"])
instance = await runtime.spawn_agent(spec, parent_id="root")

# Create plan executor with enforcer integration
executor = runtime.create_plan_executor(node_callback=my_callback)
```

### Constructor

```python
L3Runtime(
    root_envelope: dict | None = None,       # Root constraints (default: 1000/3600s/10000 actions)
    gradient: PlanGradient | None = None,     # Gradient config (default zones)
    root_owner_id: str = "root",              # Owner ID for root ContextScope
    default_channel_capacity: int = 100,      # Message channel buffer size
)
```

Attributes: `tracker`, `enforcer`, `router`, `registry`, `factory`, `root_scope`.

## EATP Event System

L3 primitives emit governance events through a pub/sub bus. An EATP translator converts these into audit records for compliance traceability.

### L3EventBus

Central pub/sub dispatcher. Thread-safe, bounded listeners (max 1000 per event type).

```python
from kaizen.l3.event_hooks import L3EventBus
from kaizen.l3.events import L3Event, L3EventType

bus = L3EventBus()
bus.subscribe(L3EventType.AGENT_SPAWNED, my_handler)
bus.subscribe_all(audit_handler)  # wildcard -- receives every event

# Primitives emit events:
bus.emit(L3Event.create(L3EventType.AGENT_SPAWNED, "agent-1", {"spec": "analyzer"}))
```

### L3EventType (15 event types)

| Category  | Event Types                                                               |
| --------- | ------------------------------------------------------------------------- |
| Envelope  | `ENVELOPE_VIOLATION`, `ENVELOPE_REGISTERED`, `ENVELOPE_SPLIT`            |
| Factory   | `AGENT_SPAWNED`, `AGENT_TERMINATED`, `AGENT_STATE_CHANGED`               |
| Messaging | `MESSAGE_ROUTED`, `MESSAGE_DEAD_LETTERED`                                |
| Plan      | `PLAN_VALIDATED`, `PLAN_EXECUTED`, `PLAN_NODE_COMPLETED`, `PLAN_NODE_FAILED`, `PLAN_NODE_HELD` |
| Context   | `CONTEXT_SCOPE_CREATED`, `CONTEXT_ACCESS_DENIED`                         |

### EatpTranslator

Converts L3 events into EATP-compatible audit record dicts. Subscribe to the bus for automatic translation.

```python
from kaizen.l3.eatp_translator import EatpTranslator

translator = EatpTranslator(max_records=10_000)
bus.subscribe_all(translator.handle_event)

# Events are now automatically translated and stored:
bus.emit(L3Event.create(L3EventType.ENVELOPE_VIOLATION, "agent-1", {"reason": "over budget"}))

records = translator.get_records()
# [{"record_id": "...", "action_type": "envelope_violation", "subject_id": "agent-1",
#   "recorded_at": "...", "context": {...}, "severity": "high", "source": "l3_event_bus"}]
```

Translation mapping: `event_type` -> `action_type`, `agent_id` -> `subject_id`, `timestamp` -> `recorded_at`, `details` -> `context`. Severity derived from event classification (violations/failures = high/medium, normal = low).
