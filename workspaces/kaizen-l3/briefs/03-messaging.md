# L3 Primitive Specification: Inter-Agent Messaging

**Status**: Draft
**Depends on**: 01-envelope-extensions.md (EnvelopeEnforcer for routing validation)
**Decision applied**: DP-3 -- EXTEND existing MessageType enum with L3 variants (add `#[non_exhaustive]` or language equivalent first)

---

## 1. Overview

Inter-Agent Messaging provides typed, envelope-aware communication channels between L3 agent instances. It replaces the existing A2A module's untyped JSON payloads with strongly-typed message variants that encode the delegation, status reporting, clarification, completion, escalation, and system-control patterns required for autonomous agent coordination.

The messaging layer enforces PACT's Communication dimension constraints at routing time: an agent cannot send a message to a recipient outside its communication envelope. Messages to terminated agents are captured in a dead letter store rather than silently dropped. Correlation IDs link request-response pairs across asynchronous exchanges.

**Boundary rule**: The messaging layer is deterministic (SDK). It validates, routes, and delivers messages. It does NOT compose message content (that requires an LLM and belongs in kaizen-agents). Deciding WHAT to say is orchestration; deciding WHETHER the message CAN be sent is enforcement.

**Relationship to existing A2A**: This specification extends the existing `MessageType` enum, `A2AMessage` struct, `MessageBus` trait, `AgentRegistry`, and `A2AProtocol`. It does not replace them. Existing L0-L2 message types (TaskRequest, TaskResponse, StatusUpdate, CapabilityQuery, CapabilityResponse, Error) continue to function. L3 variants are added to the same enum. The `MessageBus` trait gains an L3-aware implementation (`MessageRouter`) that wraps envelope validation around the transport layer.

---

## 2. Types

### 2.1 MessageType Extension (DP-3 Applied)

The existing `MessageType` enum is extended with L3 variants. Before adding these variants, the enum MUST be marked as extensible (`#[non_exhaustive]` in Rust, or equivalent in other languages) to prevent downstream exhaustive-match breakage.

**Prerequisite**: Add extensibility marker to the existing `MessageType` enum. This is a one-line, zero-cost change that must land BEFORE any L3 variant is added.

Existing variants (unchanged):

- `TaskRequest` -- L0-L2 task request
- `TaskResponse` -- L0-L2 task response
- `StatusUpdate` -- L0-L2 status update
- `CapabilityQuery` -- L0-L2 capability query
- `CapabilityResponse` -- L0-L2 capability response
- `Error` -- L0-L2 error

New L3 variants:

- `Delegation` -- Parent assigns a task to a child (L3 typed payload)
- `Status` -- Child reports progress to parent (L3 typed payload)
- `Clarification` -- Child asks parent a question, or parent responds (L3 typed payload)
- `Completion` -- Child reports task completion with results (L3 typed payload)
- `Escalation` -- Child escalates a problem upward (L3 typed payload)
- `System` -- Infrastructure-level: termination notice, envelope violation, heartbeat (L3 typed payload)

The L3 variants carry strongly-typed payloads (defined below) instead of generic JSON. L0-L2 variants continue to use the existing `payload: JSON` field on `A2AMessage`.

### 2.2 L3 Message Payloads

Each L3 variant carries a dedicated payload type. These are the fields implementations MUST support.

#### DelegationPayload

Sent by a parent to a child to assign a task.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_description` | String | Yes | Natural-language description of the delegated task |
| `context_snapshot` | Map<String, JSON> | Yes | Context keys injected from parent's ScopedContext (may be empty map) |
| `envelope` | ConstraintEnvelope | Yes | The constraint envelope allocated to the child for this task |
| `deadline` | Timestamp (nullable) | No | Absolute time by which the task should complete |
| `priority` | Priority | Yes | Execution priority for this delegation |

#### StatusPayload

Sent by a child to its parent to report progress.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `progress_pct` | Float (nullable) | No | Completion percentage, 0.0 to 1.0 inclusive. Null if indeterminate. |
| `phase` | String | Yes | Free-text description of current phase (e.g., "analyzing", "testing") |
| `resource_usage` | ResourceSnapshot | Yes | Current cumulative resource consumption across all envelope dimensions |

**ResourceSnapshot** contains:

| Field | Type | Description |
|-------|------|-------------|
| `financial_spent` | Float | Cumulative monetary spend |
| `actions_executed` | Integer | Cumulative action count |
| `elapsed_seconds` | Float | Wall-clock time since task start |
| `messages_sent` | Integer | Total messages sent by this agent |

#### ClarificationPayload

Sent by a child to request clarification from its parent, or by a parent to answer.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | String | Yes | The clarification question (when requesting) or the answer (when responding) |
| `options` | List<String> (nullable) | No | Suggested answers, if any. Null if open-ended. |
| `blocking` | Boolean | Yes | If true, the sender is suspended waiting for a response |
| `is_response` | Boolean | Yes | False when asking a question, true when answering one |

#### CompletionPayload

Sent by a child to report task completion.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `result` | JSON | Yes | The output of the completed task (structure depends on task type) |
| `context_updates` | Map<String, JSON> | Yes | Keys to merge back into the parent's ScopedContext (may be empty) |
| `resource_consumed` | ResourceSnapshot | Yes | Final cumulative resource consumption |
| `success` | Boolean | Yes | Whether the task completed successfully |
| `error_detail` | String (nullable) | No | If `success` is false, a description of the failure |

#### EscalationPayload

Sent by a child to escalate a problem it cannot resolve within its envelope.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `severity` | EscalationSeverity | Yes | How severe the escalated issue is |
| `problem_description` | String | Yes | What went wrong |
| `attempted_mitigations` | List<String> | Yes | What the child already tried (may be empty) |
| `suggested_action` | String (nullable) | No | What the child recommends the parent do |
| `violating_dimension` | String (nullable) | No | Which envelope dimension was violated, if applicable |

#### SystemPayload

Infrastructure-level messages not initiated by LLM decision-making.

| Subtype | Fields | Description |
|---------|--------|-------------|
| `TerminationNotice` | `reason: TerminationReason` | Notifies an agent it is being terminated |
| `EnvelopeViolation` | `dimension: String, detail: String` | Reports an envelope constraint violation |
| `HeartbeatRequest` | (none) | Requests a liveness check |
| `HeartbeatResponse` | `instance_id: UUID` | Responds to a heartbeat request |
| `ChannelClosing` | `reason: String` | Notifies that a channel is being torn down |

### 2.3 MessageEnvelope (Transport Wrapper)

Every L3 message is wrapped in a `MessageEnvelope` for transport. The envelope carries routing metadata separate from the payload.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message_id` | UUID | Yes | Globally unique identifier for this message, generated at creation time |
| `from` | UUID | Yes | Instance ID of the sending agent |
| `to` | UUID | Yes | Instance ID of the receiving agent |
| `correlation_id` | UUID (nullable) | No | Links this message to a prior message (e.g., a Clarification response links to the Clarification request) |
| `payload` | L3 Message (one of: DelegationPayload, StatusPayload, ClarificationPayload, CompletionPayload, EscalationPayload, SystemPayload) | Yes | The typed message content |
| `sent_at` | Timestamp | Yes | When the message was created (UTC) |
| `ttl` | Duration (nullable) | No | Maximum time-to-live. If `sent_at + ttl < now` at delivery time, the message is not delivered and goes to DeadLetterStore |

**message_id generation**: Must be UUID v4 (random). Must be unique across all messages in the system.

**correlation_id semantics**: When a child sends a ClarificationPayload, the parent's response MUST set `correlation_id` to the original Clarification's `message_id`. When a child sends a CompletionPayload, it MUST set `correlation_id` to the DelegationPayload's `message_id` that initiated the task. Status and Escalation messages SHOULD set `correlation_id` to the originating Delegation's `message_id`.

### 2.4 MessageChannel

A bounded, asynchronous, point-to-point communication link between two agent instances. Channels are created at spawn time by the AgentFactory and torn down at termination.

| Field | Type | Description |
|-------|------|-------------|
| `channel_id` | UUID | Unique identifier for this channel |
| `from_instance` | UUID | The sender endpoint |
| `to_instance` | UUID | The receiver endpoint |
| `capacity` | Integer (> 0) | Maximum number of undelivered messages buffered in the channel. When full, `send()` blocks or returns backpressure error. |

**Operations**:

| Operation | Signature | Semantics |
|-----------|-----------|-----------|
| `send` | `(envelope: MessageEnvelope) -> Result<(), ChannelError>` | Enqueues a message. Fails if channel is closed or at capacity (backpressure). |
| `recv` | `() -> Result<MessageEnvelope, ChannelError>` | Blocks until a message is available. Fails if channel is closed and empty. |
| `try_recv` | `() -> Result<Option<MessageEnvelope>, ChannelError>` | Non-blocking receive. Returns None if no message available. Fails if channel is closed. |
| `is_closed` | `() -> Boolean` | Returns true if the channel has been shut down. |
| `pending_count` | `() -> Integer` | Number of messages currently buffered. |

**Channel lifecycle**: A channel is created by `MessageRouter.create_channel()`, typically at agent spawn time. It is closed by `MessageRouter.close_channels_for()` at agent termination. Once closed, no new messages can be sent; pending messages can still be drained.

**Directionality**: Each channel is unidirectional (from_instance to to_instance). For bidirectional parent-child communication, two channels are created: parent-to-child and child-to-parent.

### 2.5 MessageRouter

The envelope-aware routing layer. Validates that the sender's communication constraints permit the recipient before delivering any message. Depends on EnvelopeEnforcer (from 01-envelope-extensions) for constraint validation.

| Field | Type | Description |
|-------|------|-------------|
| `channels` | Map<(UUID, UUID), MessageChannel> | Keyed by (from_instance, to_instance) pair |
| `registry` | Reference to AgentInstanceRegistry | For looking up agent state and envelope |
| `enforcer` | Reference to EnvelopeEnforcer | For validating communication constraints |
| `dead_letters` | DeadLetterStore | Captures undeliverable messages |

**Operations**:

| Operation | Signature | Semantics |
|-----------|-----------|-----------|
| `route` | `(envelope: MessageEnvelope) -> Result<(), RoutingError>` | Validates constraints then delivers to the appropriate channel. If validation fails, records in dead_letters. |
| `create_channel` | `(from: UUID, to: UUID, capacity: Integer) -> Result<(), RoutingError>` | Creates a channel between two instances. Fails if channel already exists. |
| `close_channels_for` | `(instance_id: UUID) -> void` | Closes all channels to/from the given instance. Pending messages for the terminated instance are moved to dead_letters. |
| `pending_for` | `(instance_id: UUID) -> List<MessageEnvelope>` | Returns all pending messages across all channels targeting this instance. Non-blocking, non-draining. |

**Routing validation sequence** (performed by `route()` before delivery):

1. **TTL check**: If `envelope.ttl` is set and `now > envelope.sent_at + envelope.ttl`, reject with `RoutingError::Expired`. Record in dead_letters with reason `Expired`.
2. **Sender existence**: Look up `envelope.from` in AgentInstanceRegistry. If not found, reject with `RoutingError::SenderNotFound`. Record in dead_letters.
3. **Recipient existence**: Look up `envelope.to` in AgentInstanceRegistry. If not found, reject with `RoutingError::RecipientNotFound`. Record in dead_letters.
4. **Recipient state**: If recipient is in state `Terminated`, `Completed`, or `Failed`, reject with `RoutingError::RecipientTerminated`. Record in dead_letters.
5. **Communication envelope check**: Retrieve sender's effective communication constraints from EnvelopeEnforcer. Verify that the recipient's instance ID (or its positional address) is within the sender's allowed recipients/channels and not in the denied set. If blocked, reject with `RoutingError::CommunicationBlocked { dimension: "communication", detail: "..." }`. Record in dead_letters.
6. **Message type directionality** (see Section 3, Invariant 3): Validate that the message type is permitted for the sender-recipient relationship.
7. **Channel existence**: Look up the `(from, to)` channel. If not found, reject with `RoutingError::NoChannel`.
8. **Deliver**: Enqueue the message on the channel. If channel is at capacity, return `RoutingError::Backpressure`.

### 2.6 DeadLetterStore

Captures messages that could not be delivered, with the reason for failure. Bounded to prevent unbounded memory growth.

| Field | Type | Description |
|-------|------|-------------|
| `max_capacity` | Integer | Maximum number of dead letters retained (ring buffer semantics: oldest evicted first) |
| `entries` | Ring buffer of `(MessageEnvelope, DeadLetterReason, Timestamp)` | The captured messages |

**DeadLetterReason** variants:

| Reason | Description |
|--------|-------------|
| `Expired` | Message TTL exceeded before delivery |
| `RecipientTerminated` | Recipient agent is in a terminal state |
| `RecipientNotFound` | Recipient instance ID not in registry |
| `SenderNotFound` | Sender instance ID not in registry |
| `CommunicationBlocked` | Sender's envelope does not permit this recipient |
| `ChannelClosed` | The channel was closed before the message could be delivered |
| `ChannelFull` | The channel was at capacity and the message was not retried |

**Operations**:

| Operation | Signature | Semantics |
|-----------|-----------|-----------|
| `record` | `(envelope: MessageEnvelope, reason: DeadLetterReason) -> void` | Adds a dead letter entry. If at capacity, evicts the oldest entry. |
| `recent` | `(limit: Integer) -> List<(MessageEnvelope, DeadLetterReason, Timestamp)>` | Returns the most recent `limit` entries, newest first. |
| `count` | `() -> Integer` | Total number of entries currently stored. |
| `drain_for` | `(instance_id: UUID) -> List<(MessageEnvelope, DeadLetterReason, Timestamp)>` | Removes and returns all dead letters where `to` matches instance_id. |

### 2.7 Priority

Execution priority for L3 messages. Affects ordering within a channel (higher priority messages are dequeued first when multiple messages are pending).

| Variant | Numeric Value | Semantics |
|---------|---------------|-----------|
| `Low` | 0 | Background, best-effort processing |
| `Normal` | 1 | Standard processing (default) |
| `High` | 2 | Expedited processing |
| `Critical` | 3 | Immediate processing, pre-empts lower-priority messages |

Priority is a property of the DelegationPayload. Other message types inherit the priority of the originating Delegation via correlation_id, or default to `Normal`.

### 2.8 EscalationSeverity

Severity levels for EscalationPayload messages.

| Variant | Semantics |
|---------|-----------|
| `Blocked` | The agent cannot proceed but the situation is not time-critical. Parent can address at next scheduling opportunity. |
| `Warning` | The agent encountered an unexpected condition but can continue with degraded quality. Informational escalation. |
| `BudgetAlert` | An envelope dimension is approaching exhaustion (e.g., 80%+ consumed). Proactive warning before a hard block. |
| `Critical` | The agent has hit a hard failure requiring immediate intervention. Task cannot continue. |

### 2.9 RoutingError

Error type returned by MessageRouter operations.

| Variant | Fields | Description |
|---------|--------|-------------|
| `Expired` | `message_id: UUID, ttl: Duration, age: Duration` | Message TTL exceeded |
| `SenderNotFound` | `instance_id: UUID` | Sender not in registry |
| `RecipientNotFound` | `instance_id: UUID` | Recipient not in registry |
| `RecipientTerminated` | `instance_id: UUID, state: AgentState` | Recipient in terminal state |
| `CommunicationBlocked` | `sender: UUID, recipient: UUID, detail: String` | Envelope constraint violation |
| `DirectionalityViolation` | `message_type: String, from: UUID, to: UUID, detail: String` | Message type not permitted for this sender-recipient relationship |
| `NoChannel` | `from: UUID, to: UUID` | No channel exists between the two instances |
| `Backpressure` | `channel_id: UUID, capacity: Integer` | Channel at capacity |
| `ChannelClosed` | `channel_id: UUID` | Channel has been shut down |

---

## 3. Behavioral Invariants

These invariants MUST hold in any conforming implementation. Violations indicate implementation bugs.

### Invariant 1: Communication Envelope Enforcement

The sender's effective communication constraints MUST permit the recipient before any message is delivered. The EnvelopeEnforcer validates:

- The recipient's address or ID is within the sender's `allowed_recipients` (if set) and NOT in `denied_recipients`.
- The channel type used is within the sender's `allowed_channels` (if set) and NOT in `denied_channels` (or `blocked_channels`).
- If `require_approval_for_external` (or `requires_review`) is true and the recipient is external, the message is held -- not delivered -- until approval is granted.

This check is non-bypassable. The MessageRouter MUST perform it on every `route()` call. There is no "skip validation" path.

### Invariant 2: Recipient State Acceptance

A message can only be delivered to an agent in a state that accepts messages:

| Agent State | Accepts Messages? |
|-------------|-------------------|
| `Pending` | Yes (queued until agent starts) |
| `Running` | Yes |
| `Waiting` | Yes |
| `Completed` | No -- to DeadLetterStore |
| `Failed` | No -- to DeadLetterStore |
| `Terminated` | No -- to DeadLetterStore |

### Invariant 3: Message Type Directionality

Not all message types can be sent in all directions. The following table defines the permitted sender-recipient relationships:

| Message Type | Permitted Direction | Validation Rule |
|--------------|-------------------|-----------------|
| `Delegation` | Parent to child, OR parent to non-descendant via bridge | Sender must be parent of recipient, OR a cross-containment bridge must exist |
| `Status` | Child to parent | Sender's `parent_id` must equal recipient's `instance_id` |
| `Clarification` | Child to parent (question), Parent to child (answer) | One of sender/recipient must be the other's parent |
| `Completion` | Child to parent | Sender's `parent_id` must equal recipient's `instance_id` |
| `Escalation` | Child to parent, OR child to grandparent (recursive) | Recipient must be an ancestor of sender in the lineage chain |
| `System` | Any direction (infrastructure) | No directionality constraint, but only the system (runtime) or a parent may send `TerminationNotice` |

**Delegation to non-descendant**: When a parent delegates to an agent that is not its child (cross-containment), this requires a PACT Cross-Containment Bridge. The bridge must exist and its scope must permit the message type and data classification. The router validates bridge existence and scope as part of the communication envelope check.

### Invariant 4: Terminated Agent Messages to DeadLetterStore

When an agent transitions to `Completed`, `Failed`, or `Terminated`, ALL subsequent messages addressed to that agent MUST be routed to the DeadLetterStore with reason `RecipientTerminated`. Additionally, any messages still buffered in the agent's inbound channels that have not been consumed MUST be moved to the DeadLetterStore with reason `ChannelClosed`.

### Invariant 5: Correlation ID Consistency

- A `CompletionPayload` message MUST carry a `correlation_id` matching the `message_id` of the `DelegationPayload` that initiated the task.
- A `ClarificationPayload` response (`is_response == true`) MUST carry a `correlation_id` matching the `message_id` of the ClarificationPayload question it answers.
- A `StatusPayload` message SHOULD carry a `correlation_id` matching the originating Delegation.
- An `EscalationPayload` message SHOULD carry a `correlation_id` matching the originating Delegation.

Implementations MUST validate correlation_id referential integrity on Completion and Clarification-response messages. If the referenced message_id does not exist in the sender's message history, the router MUST reject with `RoutingError::DirectionalityViolation`.

### Invariant 6: TTL Enforcement

If a `MessageEnvelope` has a non-null `ttl`, the message MUST NOT be delivered if `now > sent_at + ttl`. The check is performed at routing time (in `MessageRouter.route()`), not at receive time. Expired messages are recorded in the DeadLetterStore with reason `Expired`.

### Invariant 7: Channel Capacity Bounds

A `MessageChannel` MUST NOT buffer more than `capacity` messages. When a `send()` is attempted on a full channel, the implementation MUST either:

(a) Block the sender until space is available (backpressure with timeout), OR
(b) Return `ChannelError::Backpressure` immediately.

The choice between (a) and (b) is implementation-defined. The message MUST NOT be silently dropped.

### Invariant 8: Bidirectional Channel Setup at Spawn

When AgentFactory spawns a child agent, the MessageRouter MUST create exactly two channels: parent-to-child and child-to-parent. Both channels MUST be created atomically (both succeed or neither is created). Both channels MUST be closed when either agent terminates.

### Invariant 9: Dead Letter Bounded Growth

The DeadLetterStore MUST NOT grow without bound. It MUST enforce its `max_capacity` by evicting the oldest entries when new entries would exceed the limit. This is ring buffer (FIFO eviction) semantics.

---

## 4. Operations

### 4.1 Sending a Delegation

**Preconditions**:
1. Sender is in state `Running` or `Waiting`
2. Recipient exists in AgentInstanceRegistry
3. Sender is parent of recipient (or bridge exists)
4. Sender's communication envelope permits the recipient
5. Recipient is in an accepting state (`Pending`, `Running`, or `Waiting`)
6. A channel from sender to recipient exists
7. The DelegationPayload's `envelope` is a subset of the sender's active envelope (monotonic tightening, validated by EnvelopeEnforcer)

**Steps**:
1. Construct `MessageEnvelope` with `payload = DelegationPayload`, generate `message_id`, set `sent_at` to current time
2. Call `MessageRouter.route(envelope)`
3. Router performs validation sequence (Section 2.5)
4. On success, message is enqueued on the parent-to-child channel

**Postconditions**:
1. Message is buffered in the channel, awaiting recipient's `recv()`
2. An EATP Audit Anchor is created (see Section 5)

**Errors**: Any `RoutingError` variant (see Section 2.9)

### 4.2 Sending a Status Update

**Preconditions**:
1. Sender is in state `Running`
2. Sender has a parent (parent_id is not None)
3. `progress_pct`, if provided, is in range [0.0, 1.0]

**Steps**:
1. Construct `MessageEnvelope` with `payload = StatusPayload`
2. Set `correlation_id` to the originating Delegation's `message_id` (if known)
3. Call `MessageRouter.route(envelope)`

**Postconditions**:
1. Message delivered to parent's inbound channel
2. No state change on either agent

### 4.3 Sending a Clarification Request

**Preconditions**:
1. Sender is in state `Running`
2. Sender has a parent

**Steps**:
1. Construct `ClarificationPayload` with `is_response = false`
2. If `blocking = true`, sender transitions to `Waiting { reason: ClarificationPending { message_id } }` after send
3. Call `MessageRouter.route(envelope)`

**Postconditions**:
1. Message delivered to parent
2. If blocking, sender is in `Waiting` state until a Clarification response with matching `correlation_id` arrives

### 4.4 Responding to a Clarification

**Preconditions**:
1. Responder received a ClarificationPayload with `is_response = false`
2. Responder is parent of the original sender

**Steps**:
1. Construct `ClarificationPayload` with `is_response = true`
2. Set `correlation_id` to the original Clarification's `message_id`
3. Call `MessageRouter.route(envelope)`

**Postconditions**:
1. Message delivered to child
2. If child was in `Waiting` state for this clarification, child transitions back to `Running`

### 4.5 Sending a Completion

**Preconditions**:
1. Sender is in state `Running`
2. Sender has a parent
3. `correlation_id` is set to the originating Delegation's `message_id`

**Steps**:
1. Construct `CompletionPayload` with final results and resource consumption
2. Call `MessageRouter.route(envelope)`
3. Sender transitions to `Completed { result }` after successful send

**Postconditions**:
1. Message delivered to parent
2. Sender is now in `Completed` state
3. Sender's channels will be closed during cleanup (initiated by parent or registry)

### 4.6 Sending an Escalation

**Preconditions**:
1. Sender is in state `Running` or `Waiting`
2. Recipient is an ancestor of sender

**Steps**:
1. Construct `EscalationPayload` with severity and problem description
2. Call `MessageRouter.route(envelope)`
3. If `severity == Critical`, sender transitions to `Waiting { reason: EscalationPending }`

**Postconditions**:
1. Message delivered to ancestor
2. Ancestor is responsible for resolution (retry, replan, escalate further, or abandon)

### 4.7 Channel Teardown on Termination

When an agent transitions to a terminal state (`Completed`, `Failed`, `Terminated`):

1. The runtime calls `MessageRouter.close_channels_for(instance_id)`
2. All channels where `from_instance == instance_id` or `to_instance == instance_id` are closed
3. Any messages remaining in channels TO the terminated agent are moved to DeadLetterStore with reason `ChannelClosed`
4. Any messages remaining in channels FROM the terminated agent are still deliverable (they were sent before termination)
5. Future `route()` calls targeting this agent return `RoutingError::RecipientTerminated`

---

## 5. PACT Record Mapping

Every messaging operation creates EATP records for traceability. Cross-containment bridges create bilateral Delegation Records per PACT Section 4.4.

| Messaging Operation | EATP Record(s) |
|---------------------|----------------|
| **Channel established (parent-child)** | Delegation Record -- parent delegates communication authority to child as part of spawn |
| **Channel established (cross-containment bridge)** | Two cross-referencing Delegation Records created atomically. Record A references Record B's ID and vice versa. Both specify scope (permitted message types, data classification ceiling). If one record fails to create, both are rolled back. |
| **Message sent (any L3 type)** | Audit Anchor: captures `message_id`, `from`, `to`, message type, sender's effective envelope at send time, timestamp |
| **Message blocked (communication constraint)** | Audit Anchor (subtype: `barrier_enforced`): captures `message_id`, `from`, `to`, violating dimension, the constraint that blocked it |
| **Message expired (TTL)** | Audit Anchor (subtype: `message_expired`): captures `message_id`, `ttl`, `sent_at`, time of expiry check |
| **Channel closed (agent termination)** | Audit Anchor (subtype: `channel_closed`): captures `channel_id`, `instance_id` of terminated agent, count of messages moved to dead letters |
| **Bridge created** | Two Delegation Records (bilateral) with scope specifying allowed message types and classification level |
| **Bridge torn down** | Audit Anchor (subtype: `bridge_closed`): captures both endpoint IDs, bridge scope, reason for closure |

**Bridge atomicity**: PACT Section 4.4 specifies that bridges are bilateral (both parties agree). The implementation MUST create both Delegation Records in a single transaction. If the underlying EATP store does not support transactions, a BilateralDelegation wrapper pattern MUST be used (create both, roll back on partial failure).

**Bridge scope tightening**: A bridge MUST NOT grant communication access broader than either party's own envelope. The bridge scope is the intersection of both parties' Communication constraints. This is validated at bridge creation time by the EnvelopeEnforcer.

---

## 6. What Exists Today

The following components already exist in the codebase and form the foundation for L3 messaging.

### 6.1 A2AMessage (kailash-kaizen `a2a/messaging.rs`)

Current struct:

- `id: String` (UUID v4)
- `from_agent: String` (agent name/ID)
- `to_agent: String` (agent name/ID)
- `message_type: MessageType` (6-variant enum)
- `payload: serde_json::Value` (untyped JSON)
- `correlation_id: Option<String>`
- `timestamp: String` (ISO 8601)

**L3 relationship**: L3 MessageEnvelope extends this with UUID-typed IDs (instead of String), typed payloads (instead of generic JSON), `sent_at` as a proper timestamp type, and `ttl`. The existing `A2AMessage` continues to work for L0-L2 communication. L3 agents use `MessageEnvelope` which wraps typed payloads. Both transport types share the same `MessageBus` infrastructure.

### 6.2 MessageBus Trait (kailash-kaizen `a2a/messaging.rs`)

Current interface:

- `send(message: A2AMessage) -> Result<(), Error>` (async)
- `receive(agent_id: &str) -> Result<Vec<A2AMessage>, Error>` (async, drains queue)
- `peek(agent_id: &str) -> Result<usize, Error>` (async)

Implementation: `InMemoryMessageBus` -- Mutex-protected HashMap of agent_id to Vec<A2AMessage>.

**L3 relationship**: The `MessageBus` trait remains the low-level transport. `MessageRouter` wraps it to add envelope validation, channel management, and dead letter handling. The InMemoryMessageBus can serve as the underlying transport for MessageRouter's channels.

### 6.3 AgentRegistry (kailash-kaizen `a2a/discovery.rs`)

Provides agent discovery by capability (name, description, capabilities). Name-keyed DashMap.

**L3 relationship**: AgentRegistry continues for capability-based discovery. L3 adds AgentInstanceRegistry (from the AgentFactory spec) for instance-level lifecycle and lineage tracking. MessageRouter references AgentInstanceRegistry for instance state and envelope lookup.

### 6.4 Communication Constraints (EATP `constraints/communication.rs` and trust-plane `constraints.rs`)

Two existing definitions:

**EATP crate**: `allowed_channels`, `denied_channels`, `allowed_recipients`, `denied_recipients`, `require_approval_for_external`, `max_message_length`.

**Trust-plane crate**: `allowed_channels: Option<Vec<String>>`, `blocked_channels: Vec<String>`, `requires_review: bool`.

**L3 relationship**: MessageRouter uses these constraints (via EnvelopeEnforcer) to validate every `route()` call. The EATP crate's richer definition (with `allowed_recipients`, `denied_recipients`, `max_message_length`) is the primary model. The trust-plane's definition is the runtime enforcement subset. L3 messaging validates against whichever is available in the sender's effective envelope.

### 6.5 A2AProtocol (kailash-kaizen `a2a/messaging.rs`)

Combines AgentRegistry + MessageBus for discover-and-delegate semantics. Provides `discover_and_delegate()` and `respond()`.

**L3 relationship**: A2AProtocol is the L0-L2 convenience layer. L3 replaces the discover-and-delegate pattern with explicit factory-spawned children and envelope-validated routing. A2AProtocol remains available for backward compatibility and for L0-L2 code paths.

---

## 7. Edge Cases

### EC-1: Message to Self

An agent sends a message with `from == to`.

**Expected behavior**: Reject with `RoutingError::DirectionalityViolation`. Self-messaging has no valid L3 use case and indicates a programming error.

### EC-2: Rapid Termination Before Message Delivery

A parent sends a Delegation to a child. Before the child receives the message, the child is terminated (e.g., timeout).

**Expected behavior**: The termination triggers `close_channels_for()`. The undelivered Delegation message is moved to DeadLetterStore with reason `ChannelClosed`. The parent receives no Completion; the parent's orchestration layer must handle the missing response (timeout or dead letter inspection).

### EC-3: Orphaned Child Sends to Terminated Parent

A parent terminates. A child that has not yet been notified attempts to send a Status or Completion message to the parent.

**Expected behavior**: `route()` returns `RoutingError::RecipientTerminated`. The message goes to DeadLetterStore. The child should receive a `SystemPayload::TerminationNotice` from the runtime (as part of vacancy handling per PACT Section 5.5), which triggers the child's own termination cascade.

### EC-4: TTL of Zero

A message is created with `ttl = 0` (zero duration).

**Expected behavior**: The message expires immediately at routing time (since `now >= sent_at + 0`). Routed to DeadLetterStore with reason `Expired`. This is effectively a "do not deliver" marker and is valid, though unusual.

### EC-5: Channel Backpressure

A child sends Status updates faster than the parent consumes them. The channel reaches capacity.

**Expected behavior**: The channel's `send()` returns `ChannelError::Backpressure` (or blocks, implementation-defined). The child MUST handle backpressure by either reducing send frequency or buffering locally. The message is NOT silently dropped. The router returns `RoutingError::Backpressure` to the caller.

### EC-6: Correlation ID Mismatch on Completion

A child sends a CompletionPayload with a `correlation_id` that does not match any known Delegation message_id.

**Expected behavior**: The router rejects with `RoutingError::DirectionalityViolation` with detail explaining the correlation mismatch. The message goes to DeadLetterStore. This indicates a programming error in the orchestration layer.

### EC-7: Cross-Containment Message Without Bridge

Agent A (in container D1) attempts to send a Delegation to Agent B (in container D2). No cross-containment bridge exists.

**Expected behavior**: The communication envelope check in step 5 of the routing validation fails. Agent B's address is not in Agent A's `allowed_recipients` (since they are in different containers and no bridge widens the scope). Rejected with `RoutingError::CommunicationBlocked`. Message goes to DeadLetterStore.

### EC-8: DeadLetterStore at Capacity

The DeadLetterStore reaches `max_capacity`. A new dead letter arrives.

**Expected behavior**: The oldest entry is evicted (FIFO). The new entry is recorded. No error is raised -- dead letter recording is best-effort for observability, not a critical path. An Audit Anchor is still created for the routing failure regardless of DeadLetterStore capacity.

### EC-9: Heartbeat to Non-Responsive Agent

A HeartbeatRequest is sent to an agent. The agent does not respond within a configurable timeout.

**Expected behavior**: The system (runtime) may mark the agent as unhealthy. This is an implementation concern for the orchestration layer. The messaging layer delivers the HeartbeatRequest like any other System message. Timeout monitoring is NOT a messaging-layer responsibility -- it belongs to the agent lifecycle manager.

### EC-10: Concurrent Channel Creation

Two threads attempt to create a channel between the same (from, to) pair simultaneously.

**Expected behavior**: Exactly one succeeds; the other receives `RoutingError::ChannelAlreadyExists` (or equivalent). Channel creation MUST be idempotent or use compare-and-swap to prevent duplicates.

---

## 8. Conformance Test Vectors

Each test vector specifies inputs, expected outputs, and the invariant being tested. Implementations MUST pass all conformance tests to be considered compliant.

### TV-01: Basic Delegation Routing (Happy Path)

**Tests**: Invariants 1, 2, 3, 5, 8

```json
{
  "test_id": "TV-MSG-01",
  "description": "Parent sends Delegation to child; child receives it",
  "setup": {
    "agents": [
      {
        "instance_id": "aaaa-0001",
        "parent_id": null,
        "state": "Running",
        "communication_constraints": {
          "allowed_recipients": [],
          "denied_recipients": [],
          "allowed_channels": [],
          "denied_channels": []
        }
      },
      {
        "instance_id": "aaaa-0002",
        "parent_id": "aaaa-0001",
        "state": "Pending",
        "communication_constraints": {
          "allowed_recipients": [],
          "denied_recipients": [],
          "allowed_channels": [],
          "denied_channels": []
        }
      }
    ],
    "channels": [
      { "from": "aaaa-0001", "to": "aaaa-0002", "capacity": 10 },
      { "from": "aaaa-0002", "to": "aaaa-0001", "capacity": 10 }
    ]
  },
  "action": {
    "operation": "route",
    "envelope": {
      "message_id": "msg-0001",
      "from": "aaaa-0001",
      "to": "aaaa-0002",
      "correlation_id": null,
      "payload": {
        "type": "Delegation",
        "task_description": "Review authentication module",
        "context_snapshot": { "project.name": "kaizen-agents" },
        "envelope": { "financial": { "limit": 1000 } },
        "deadline": null,
        "priority": "Normal"
      },
      "sent_at": "2026-03-21T10:00:00Z",
      "ttl": null
    }
  },
  "expected": {
    "result": "Ok",
    "channel_pending_count": { "aaaa-0001->aaaa-0002": 1 },
    "dead_letter_count": 0
  }
}
```

### TV-02: Communication Constraint Blocks Message

**Tests**: Invariant 1

```json
{
  "test_id": "TV-MSG-02",
  "description": "Sender's communication constraints deny the recipient; message goes to dead letters",
  "setup": {
    "agents": [
      {
        "instance_id": "aaaa-0001",
        "parent_id": null,
        "state": "Running",
        "communication_constraints": {
          "allowed_recipients": ["aaaa-0003"],
          "denied_recipients": ["aaaa-0002"],
          "allowed_channels": [],
          "denied_channels": []
        }
      },
      {
        "instance_id": "aaaa-0002",
        "parent_id": "aaaa-0001",
        "state": "Running",
        "communication_constraints": {}
      }
    ],
    "channels": [
      { "from": "aaaa-0001", "to": "aaaa-0002", "capacity": 10 }
    ]
  },
  "action": {
    "operation": "route",
    "envelope": {
      "message_id": "msg-0002",
      "from": "aaaa-0001",
      "to": "aaaa-0002",
      "correlation_id": null,
      "payload": {
        "type": "Delegation",
        "task_description": "Should not arrive",
        "context_snapshot": {},
        "envelope": {},
        "deadline": null,
        "priority": "Normal"
      },
      "sent_at": "2026-03-21T10:00:00Z",
      "ttl": null
    }
  },
  "expected": {
    "result": "Err",
    "error_type": "CommunicationBlocked",
    "error_detail_contains": "denied_recipients",
    "dead_letter_count": 1,
    "dead_letter_reason": "CommunicationBlocked"
  }
}
```

### TV-03: Message to Terminated Agent

**Tests**: Invariants 2, 4

```json
{
  "test_id": "TV-MSG-03",
  "description": "Message to a terminated agent goes to dead letter store",
  "setup": {
    "agents": [
      {
        "instance_id": "aaaa-0001",
        "parent_id": null,
        "state": "Running",
        "communication_constraints": {}
      },
      {
        "instance_id": "aaaa-0002",
        "parent_id": "aaaa-0001",
        "state": "Terminated",
        "communication_constraints": {}
      }
    ],
    "channels": []
  },
  "action": {
    "operation": "route",
    "envelope": {
      "message_id": "msg-0003",
      "from": "aaaa-0001",
      "to": "aaaa-0002",
      "correlation_id": null,
      "payload": {
        "type": "Status",
        "progress_pct": 0.5,
        "phase": "testing",
        "resource_usage": {
          "financial_spent": 10.0,
          "actions_executed": 5,
          "elapsed_seconds": 30.0,
          "messages_sent": 2
        }
      },
      "sent_at": "2026-03-21T10:00:00Z",
      "ttl": null
    }
  },
  "expected": {
    "result": "Err",
    "error_type": "RecipientTerminated",
    "dead_letter_count": 1,
    "dead_letter_reason": "RecipientTerminated"
  }
}
```

### TV-04: TTL Expiry

**Tests**: Invariant 6

```json
{
  "test_id": "TV-MSG-04",
  "description": "Message with expired TTL is rejected and recorded as dead letter",
  "setup": {
    "agents": [
      {
        "instance_id": "aaaa-0001",
        "parent_id": null,
        "state": "Running",
        "communication_constraints": {}
      },
      {
        "instance_id": "aaaa-0002",
        "parent_id": "aaaa-0001",
        "state": "Running",
        "communication_constraints": {}
      }
    ],
    "channels": [
      { "from": "aaaa-0001", "to": "aaaa-0002", "capacity": 10 }
    ]
  },
  "action": {
    "operation": "route",
    "current_time": "2026-03-21T10:05:00Z",
    "envelope": {
      "message_id": "msg-0004",
      "from": "aaaa-0001",
      "to": "aaaa-0002",
      "correlation_id": null,
      "payload": {
        "type": "Delegation",
        "task_description": "Expired task",
        "context_snapshot": {},
        "envelope": {},
        "deadline": null,
        "priority": "Normal"
      },
      "sent_at": "2026-03-21T10:00:00Z",
      "ttl": "PT60S"
    }
  },
  "expected": {
    "result": "Err",
    "error_type": "Expired",
    "dead_letter_count": 1,
    "dead_letter_reason": "Expired",
    "note": "sent_at + 60s = 10:01:00Z, current_time = 10:05:00Z, so TTL has expired"
  }
}
```

### TV-05: Directionality Violation -- Child Sends Delegation to Sibling

**Tests**: Invariant 3

```json
{
  "test_id": "TV-MSG-05",
  "description": "A child agent cannot send a Delegation to a sibling (non-descendant)",
  "setup": {
    "agents": [
      {
        "instance_id": "aaaa-0001",
        "parent_id": null,
        "state": "Running",
        "communication_constraints": {}
      },
      {
        "instance_id": "aaaa-0002",
        "parent_id": "aaaa-0001",
        "state": "Running",
        "communication_constraints": {}
      },
      {
        "instance_id": "aaaa-0003",
        "parent_id": "aaaa-0001",
        "state": "Running",
        "communication_constraints": {}
      }
    ],
    "channels": [
      { "from": "aaaa-0002", "to": "aaaa-0003", "capacity": 10 }
    ]
  },
  "action": {
    "operation": "route",
    "envelope": {
      "message_id": "msg-0005",
      "from": "aaaa-0002",
      "to": "aaaa-0003",
      "correlation_id": null,
      "payload": {
        "type": "Delegation",
        "task_description": "Should be rejected -- sibling cannot delegate",
        "context_snapshot": {},
        "envelope": {},
        "deadline": null,
        "priority": "Normal"
      },
      "sent_at": "2026-03-21T10:00:00Z",
      "ttl": null
    }
  },
  "expected": {
    "result": "Err",
    "error_type": "DirectionalityViolation",
    "error_detail_contains": "Delegation requires sender to be parent of recipient or bridge to exist",
    "dead_letter_count": 1,
    "dead_letter_reason": "CommunicationBlocked"
  }
}
```

### TV-06: Correlation ID Required on Completion

**Tests**: Invariant 5

```json
{
  "test_id": "TV-MSG-06",
  "description": "Completion message without correlation_id is rejected",
  "setup": {
    "agents": [
      {
        "instance_id": "aaaa-0001",
        "parent_id": null,
        "state": "Running",
        "communication_constraints": {}
      },
      {
        "instance_id": "aaaa-0002",
        "parent_id": "aaaa-0001",
        "state": "Running",
        "communication_constraints": {}
      }
    ],
    "channels": [
      { "from": "aaaa-0002", "to": "aaaa-0001", "capacity": 10 }
    ]
  },
  "action": {
    "operation": "route",
    "envelope": {
      "message_id": "msg-0006",
      "from": "aaaa-0002",
      "to": "aaaa-0001",
      "correlation_id": null,
      "payload": {
        "type": "Completion",
        "result": { "status": "done" },
        "context_updates": {},
        "resource_consumed": {
          "financial_spent": 50.0,
          "actions_executed": 10,
          "elapsed_seconds": 120.0,
          "messages_sent": 5
        },
        "success": true,
        "error_detail": null
      },
      "sent_at": "2026-03-21T10:00:00Z",
      "ttl": null
    }
  },
  "expected": {
    "result": "Err",
    "error_type": "DirectionalityViolation",
    "error_detail_contains": "Completion requires correlation_id referencing originating Delegation",
    "dead_letter_count": 1
  }
}
```

### TV-07: Dead Letter Store Capacity Eviction

**Tests**: Invariant 9

```json
{
  "test_id": "TV-MSG-07",
  "description": "DeadLetterStore evicts oldest entry when at capacity",
  "setup": {
    "dead_letter_store": {
      "max_capacity": 3,
      "existing_entries": [
        { "message_id": "old-001", "reason": "Expired", "recorded_at": "2026-03-21T09:00:00Z" },
        { "message_id": "old-002", "reason": "RecipientTerminated", "recorded_at": "2026-03-21T09:01:00Z" },
        { "message_id": "old-003", "reason": "CommunicationBlocked", "recorded_at": "2026-03-21T09:02:00Z" }
      ]
    }
  },
  "action": {
    "operation": "dead_letter_record",
    "message_id": "new-004",
    "reason": "ChannelClosed"
  },
  "expected": {
    "dead_letter_count": 3,
    "contains_message_ids": ["old-002", "old-003", "new-004"],
    "evicted_message_ids": ["old-001"],
    "note": "Oldest entry (old-001) evicted to make room for new-004"
  }
}
```

---

## Appendix A: Relationship to Other L3 Primitives

| Primitive | Relationship to Messaging |
|-----------|---------------------------|
| **EnvelopeTracker + EnvelopeEnforcer** (01) | EnvelopeEnforcer validates communication constraints on every `route()` call. EnvelopeTracker tracks message count against Communication dimension quotas. |
| **ScopedContext** (02) | DelegationPayload carries `context_snapshot` -- a serialized view from the parent's ScopedContext. CompletionPayload carries `context_updates` -- keys to merge back into parent scope. The messaging layer transports these; it does not interpret them. |
| **AgentFactory** (04) | Factory creates bidirectional channels at spawn time. Factory calls `close_channels_for()` at termination. The factory spec depends on this messaging spec for channel setup. |
| **Plan DAG** (05) | PlanExecutor uses Delegation/Completion messages to assign work to plan node agents and collect results. Escalation messages from plan nodes trigger the gradient-driven failure handling in PlanExecutor. |

## Appendix B: What the SDK Does NOT Do (Orchestration Layer Responsibilities)

These are explicitly out of scope for the SDK messaging layer and belong in kaizen-agents:

| Concern | Responsible Layer | Why |
|---------|-------------------|-----|
| Composing DelegationPayload.task_description | kaizen-agents (DelegationProtocol) | Requires LLM to formulate natural-language instructions |
| Deciding when to send a Clarification | kaizen-agents (ClarificationProtocol) | Requires LLM judgment about ambiguity |
| Interpreting Escalation to determine recovery | kaizen-agents (EscalationProtocol) | Requires LLM failure diagnosis |
| Selecting message priority | kaizen-agents (plan composition) | Requires task importance judgment |
| Choosing whom to message (recipient selection) | kaizen-agents (capability matching) | Requires semantic matching beyond string comparison |
| Validating result quality in Completion | kaizen-agents (CompletionProtocol) | Requires LLM judgment about output quality |
