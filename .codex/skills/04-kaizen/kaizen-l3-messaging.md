# L3 Messaging — Typed Inter-Agent Communication

## What It Is

Typed, envelope-aware communication channels between L3 agent instances. Replaces generic JSON payloads with strongly-typed message variants.

## Key Components

- **MessageChannel**: Bounded async channel with priority ordering
- **MessageRouter**: Routes messages with 8-step validation
- **DeadLetterStore**: Captures undeliverable messages (bounded ring buffer)
- **6 typed payloads**: Delegation, Status, Clarification, Completion, Escalation, System

## Message Types

| Type          | Direction        | Purpose                                  |
| ------------- | ---------------- | ---------------------------------------- |
| Delegation    | Parent → Child   | Assign task with context + envelope      |
| Status        | Child → Parent   | Report progress                          |
| Clarification | Parent ↔ Child   | Ask/answer questions                     |
| Completion    | Child → Parent   | Report results (requires correlation_id) |
| Escalation    | Child → Ancestor | Escalate problems                        |
| System        | Any              | Lifecycle (terminate, heartbeat)         |

## Usage

```python
from kaizen.l3.messaging import (
    MessageRouter, MessageChannel, MessageEnvelope,
    DelegationPayload, CompletionPayload, Priority,
)

# Create router
router = MessageRouter()

# Create bidirectional channels
router.create_channel("parent-001", "child-001", capacity=10)
router.create_channel("child-001", "parent-001", capacity=10)

# Send delegation
envelope = MessageEnvelope(
    from_instance="parent-001",
    to_instance="child-001",
    payload=DelegationPayload(
        task_description="Review code for security issues",
        context_snapshot={"project": "kaizen"},
        priority=Priority.HIGH,
    ),
)
router.route(envelope)

# Child sends completion (requires correlation_id)
completion = MessageEnvelope(
    from_instance="child-001",
    to_instance="parent-001",
    payload=CompletionPayload(result={"issues": []}, success=True),
    correlation_id=envelope.message_id,  # Links to delegation
)
router.route(completion)
```

## Routing Validation (8 Steps)

1. TTL check → 2. Self-message check → 3. Recipient state → 4. Communication envelope → 5. Directionality → 6. Correlation ID → 7. Channel exists → 8. Deliver

## Reference

- Spec: `workspaces/kaizen-l3/briefs/03-messaging.md`
- Source: `kaizen/l3/messaging/`
