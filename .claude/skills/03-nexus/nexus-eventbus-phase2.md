---
skill: nexus-eventbus-phase2
description: Advanced event capabilities including custom events, scheduled tasks, DataFlow integration, file handling, and background services
priority: LOW
tags: [nexus, events, eventbus, scheduled, dataflow-bridge, files, background]
---

# Nexus EventBus and Advanced Event Capabilities

## Overview

The Nexus EventBus provides a thread-safe event infrastructure that bridges synchronous and asynchronous execution boundaries. Built on top of the basic event system, it adds scheduled task execution, DataFlow event bridging, cross-transport file handling, and extensible background services.

## When to Use

- Reacting to events across sync/async boundaries (e.g., MCP thread to HTTP event loop)
- Scheduling periodic tasks (cleanup, reports, health checks)
- Bridging DataFlow write operations into Nexus event handlers
- Handling file uploads across different transports (HTTP, CLI, MCP)
- Running background services within the Nexus lifecycle

## Architecture

### EventBus Internals

The EventBus uses a bounded queue (default capacity 256) to bridge synchronous publishers and asynchronous subscribers:

```
Sync Publisher          Bounded Queue         Async Dispatch Loop
   publish() --------> [capacity 256] ------> fan-out to subscribers
```

Subscribers can filter events using predicates, receiving only matching events on their own queue. This enables selective subscription without processing every event.

## Capabilities

| Capability             | Description                                                                    |
| ---------------------- | ------------------------------------------------------------------------------ |
| Event handlers         | Subscribe to named event types and react asynchronously                        |
| Scheduled tasks        | Run functions on fixed intervals or cron expressions                           |
| Event emission         | Fire custom events from handlers and workflows                                 |
| DataFlow bridge        | Receive DataFlow write events as Nexus events                                  |
| File abstraction       | Unified file type that adapts to transport (HTTP upload, CLI path, MCP base64) |
| Background services    | Extensible base for internal services (scheduler, metrics, cleanup)            |
| Filtered subscriptions | Subscribe with predicates to receive only matching events                      |
| Event history          | Bounded storage of recent events, queryable by session                         |

## Event Handlers

Register functions that react to named event types. Handlers are asynchronous and receive an event object containing the event type and payload.

Event types use dot-notation namespacing (e.g., `user.created`, `order.completed`, `dataflow.User.create`).

## Scheduled Tasks

Register periodic tasks using either interval syntax or cron expressions:

| Syntax   | Example         | Meaning          |
| -------- | --------------- | ---------------- |
| Interval | `"5m"`          | Every 5 minutes  |
| Interval | `"1h"`          | Every 1 hour     |
| Cron     | `"0 2 * * *"`   | Daily at 2:00 AM |
| Cron     | `"0 */6 * * *"` | Every 6 hours    |

Scheduled tasks run via a background service that manages timing and execution.

## DataFlow Event Bridge

Connecting DataFlow to Nexus enables automatic event emission for all DataFlow write operations. When a model record is created, updated, or deleted through DataFlow, a corresponding event fires in the Nexus EventBus.

Event naming convention: `dataflow.{ModelName}.{operation}` (e.g., `dataflow.User.create`, `dataflow.Order.delete`).

The bridge covers all write operations per model, allowing reactive workflows that respond to database changes.

**Critical**: Use `auto_discovery=False` when integrating DataFlow with Nexus to prevent startup blocking.

## File Handling

Nexus provides a unified file abstraction that normalizes file input across all transports:

| Transport | Input Format     | Conversion           |
| --------- | ---------------- | -------------------- |
| HTTP      | Multipart upload | From upload object   |
| CLI       | File path        | From filesystem path |
| MCP       | Base64 string    | From encoded data    |
| WebSocket | Binary frame     | From raw bytes       |

Handlers declare file parameters using the file type, and the transport layer automatically converts the input format.

## Background Services

An abstract base for internal services that run alongside the Nexus application. Background services have a defined lifecycle (start, stop) and report health status. The built-in scheduler is implemented as a background service.

Custom background services can be created for periodic cleanup, metrics aggregation, or any long-running internal process.

## Best Practices

1. **Use dot-notation for event names** -- provides natural namespacing and filtering
2. **Keep event payloads serializable** -- events may cross thread/process boundaries
3. **Set `auto_discovery=False`** when using the DataFlow bridge
4. **Use cron for precise scheduling** -- intervals drift over time
5. **Implement health checks** in custom background services

See language-specific variant for implementation details and code examples.

## Related Skills

- [nexus-event-system](nexus-event-system.md) - Basic event system
- [nexus-dataflow-integration](nexus-dataflow-integration.md) - DataFlow integration patterns
- [nexus-transport-architecture](nexus-transport-architecture.md) - Transport layer details
