---
skill: nexus-sessions
description: Unified session management across API, CLI, and MCP channels with state persistence
priority: HIGH
tags: [nexus, sessions, state, multi-channel, persistence]
---

# Nexus Session Management

## Overview

Nexus sessions provide unified state management across all channels (API, CLI, MCP). A session tracks workflow executions, preserves state between steps, and enables cross-channel continuity -- start a workflow via API, continue via CLI, complete via MCP, all within the same session context.

## When to Use

- Multi-step workflows that span multiple requests
- Cross-channel workflows where users switch between API, CLI, and MCP
- Stateful interactions requiring context preservation between invocations
- Batch processing where related executions share context
- Long-running workflows requiring checkpoint and recovery

## Architecture

### Session Data Model

A session contains:

| Field      | Description                                             |
| ---------- | ------------------------------------------------------- |
| Session ID | Unique identifier, provided by client or auto-generated |
| Channel    | Originating channel (API, CLI, MCP)                     |
| Metadata   | User ID, organization, permissions, custom context      |
| State      | Accumulated workflow results and intermediate data      |
| Timestamps | Creation time, last activity, expiration                |
| Status     | Active, completed, failed, expired                      |

### Session Lifecycle

```
Create Session (explicit or implicit on first request)
    |
    v
Execute Workflows (state accumulates across invocations)
    |
    v
Cross-Channel Continue (same session ID, different channel)
    |
    v
End Session (explicit or timeout)
    |
    v
Cleanup (expired sessions purged)
```

## Capabilities

### Cross-Channel Continuity

Sessions are channel-agnostic. The same session ID can be used across:

- **API** -- passed via header (e.g., `X-Session-ID`) or request body
- **CLI** -- passed as a command-line flag (e.g., `--session`)
- **MCP** -- passed as a tool parameter

State accumulated in one channel is immediately available in others.

### Storage Backends

| Backend   | Use Case                                                          |
| --------- | ----------------------------------------------------------------- |
| In-memory | Development, single-instance deployments                          |
| Redis     | Production, distributed deployments with multiple Nexus instances |
| Database  | Persistent sessions that survive restarts                         |

### Session Configuration

| Setting          | Description                                  |
| ---------------- | -------------------------------------------- |
| Timeout          | Duration before idle sessions expire         |
| Backend          | Storage backend selection                    |
| Persistence      | Whether sessions survive application restart |
| Cleanup interval | How often expired sessions are purged        |
| Max age          | Absolute maximum session lifetime            |

### Session Operations

| Operation | Description                                    |
| --------- | ---------------------------------------------- |
| Create    | Establish a new session with optional metadata |
| Get       | Retrieve session state and metadata            |
| Update    | Modify session state or metadata               |
| End       | Explicitly terminate a session                 |
| Extend    | Push back the expiration deadline              |
| Sync      | Synchronize session data to a target channel   |

### Session Events

The event system emits events for session lifecycle changes:

| Event           | Fires When                                 |
| --------------- | ------------------------------------------ |
| Session created | A new session is established               |
| Session updated | Session state changes                      |
| Session ended   | A session terminates (explicit or timeout) |

## Advanced Patterns

### Nested Sessions

Child sessions can be created under a parent session, inheriting parent context. This enables sub-workflows that share the parent's state.

### Session Groups

Related sessions can be grouped for batch operations -- create multiple sessions under a group ID, then manage the group collectively (wait for all, end all).

### Session Checkpoints

Long-running workflows can create checkpoints at configurable intervals. If execution fails, the workflow can resume from the last checkpoint rather than restarting.

### Request-Scoped Sessions

Create a session per request for workflows that need execution context but no cross-request persistence. The session is automatically cleaned up after the response.

### User-Scoped Sessions

Maintain a persistent session per user, reusing it across multiple requests. Useful for conversational or stateful interactions.

## Session Security

Sessions can require authentication:

- Validate auth tokens before allowing session creation
- Associate sessions with authenticated user identity
- Prevent session hijacking through token validation

## Session Monitoring

Track session metrics for operational visibility:

- Active session count
- Total sessions created
- Average session duration
- Session success rate

## Troubleshooting

| Issue                       | Resolution                                                       |
| --------------------------- | ---------------------------------------------------------------- |
| Session not found           | Session may have expired -- check timeout settings               |
| State not persisting        | Verify storage backend configuration                             |
| Cross-channel state missing | Ensure same session ID is passed across channels                 |
| Recovery failed             | Check that persistence is enabled and checkpoint interval is set |

See language-specific variant for implementation details and code examples.

## Related Skills

- [nexus-multi-channel](nexus-multi-channel.md) - Multi-channel architecture
- [nexus-enterprise-features](nexus-enterprise-features.md) - Authentication and security
- [nexus-event-system](nexus-event-system.md) - Session events
