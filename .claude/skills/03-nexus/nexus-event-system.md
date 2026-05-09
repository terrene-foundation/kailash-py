---
skill: nexus-event-system
description: Event system for workflow lifecycle, cross-channel broadcasting, and custom events
priority: LOW
tags: [nexus, events, broadcasting, lifecycle, hooks]
---

# Nexus Event System

## Overview

Nexus provides an event-driven architecture for reacting to workflow lifecycle changes, broadcasting information across channels, and implementing custom event-based workflows. Events are the primary integration point for logging, monitoring, notifications, and cross-channel coordination.

## When to Use

- Logging workflow executions for auditing or debugging
- Sending notifications when workflows complete or fail
- Tracking metrics (request counts, durations, error rates)
- Coordinating state across API, CLI, and MCP channels
- Building reactive workflows that respond to platform activity

## Architecture

### Event Flow

```
Event Source (workflow, session, registration)
    |
    v
Event Emitted (with metadata: name, channel, session, timestamp)
    |
    v
Event Logged (stored in bounded event history)
    |
    v
Event Handlers Invoked (fan-out to all registered handlers)
```

Events carry a standard set of metadata regardless of the originating channel. Handlers receive an event object containing workflow name, session ID, channel, timestamp, inputs, results, errors, and custom metadata.

## Built-in Event Types

### Workflow Lifecycle

| Event              | Fires When                       | Key Data                                   |
| ------------------ | -------------------------------- | ------------------------------------------ |
| Workflow Started   | A workflow begins execution      | Workflow name, channel, session ID, inputs |
| Workflow Completed | A workflow finishes successfully | Workflow name, duration, result            |
| Workflow Failed    | A workflow encounters an error   | Workflow name, error message, stack trace  |

### Session Lifecycle

| Event           | Fires When                   | Key Data                             |
| --------------- | ---------------------------- | ------------------------------------ |
| Session Created | A new session is established | Session ID, channel, user ID         |
| Session Updated | Session state changes        | Session ID, changes                  |
| Session Ended   | A session terminates         | Session ID, duration, workflow count |

### Registration

| Event                 | Fires When              | Key Data                |
| --------------------- | ----------------------- | ----------------------- |
| Workflow Registered   | A new workflow is added | Workflow name, metadata |
| Workflow Unregistered | A workflow is removed   | Workflow name           |

## Event Handling

Nexus supports multiple handlers per event type. Handlers can be synchronous or asynchronous. When multiple handlers are registered for the same event, all are invoked. Handler errors are isolated -- one handler's failure does not prevent others from running.

### Handler Capabilities

- **Multiple handlers per event** -- register as many as needed
- **Async support** -- handlers can perform I/O (webhooks, database writes)
- **Conditional logic** -- handlers can inspect event data and act selectively
- **Channel filtering** -- handlers can target specific channels (API-only, MCP-only)
- **Workflow filtering** -- handlers can target specific workflow names

## Event History

Events are stored in a bounded history (recent events retained, oldest discarded). Events can be queried by type or session ID. This provides a lightweight audit trail without requiring external storage.

## Custom Events

Applications can define and emit custom event types with schemas describing the expected payload structure. Custom events participate in the same handler and history system as built-in events.

## Cross-Channel Broadcasting

Events can be broadcast across all active channels. The delivery mechanism depends on the channel:

| Channel | Delivery                                         |
| ------- | ------------------------------------------------ |
| API     | Event log (polling) / WebSocket (when available) |
| CLI     | Console output                                   |
| MCP     | Event notification                               |

## Common Integration Patterns

| Pattern               | Description                                                |
| --------------------- | ---------------------------------------------------------- |
| Notification dispatch | Send Slack/email/webhook on workflow completion or failure |
| Audit logging         | Write all events to a database for compliance              |
| Metrics collection    | Aggregate event data for dashboards and alerting           |
| Error alerting        | Trigger alerts when error rates exceed thresholds          |
| Progress tracking     | Emit progress events during long-running workflows         |

## Best Practices

1. **Keep event payloads small** -- store large data externally, reference by ID
2. **Handle errors in handlers** -- unhandled exceptions should be logged, not propagated
3. **Use event filtering** -- subscribe only to relevant events to reduce overhead
4. **Design for idempotency** -- handlers may receive duplicate events in edge cases
5. **Plan for async** -- use async handlers for I/O operations

See language-specific variant for implementation details and code examples.

## Related Skills

- [nexus-eventbus-phase2](nexus-eventbus-phase2.md) - Advanced event capabilities
- [nexus-multi-channel](nexus-multi-channel.md) - Multi-channel architecture
- [nexus-sessions](nexus-sessions.md) - Session event lifecycle
- [nexus-health-monitoring](nexus-health-monitoring.md) - Monitoring via events
