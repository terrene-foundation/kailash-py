# Session Management Example

## Overview

This example demonstrates **cross-channel session management** for Kaizen agents deployed via Nexus. Sessions maintain consistent state whether accessed through API, CLI, or MCP channels.

## What This Example Shows

1. **Session Creation** - Creating sessions with user ID and TTL
2. **Cross-Channel Sync** - State synchronizes automatically across channels
3. **Channel Activity Tracking** - Monitor which channels are used
4. **Memory Pool Integration** - Bind sessions to shared memory pools
5. **Session Lifecycle** - Automatic expiration and cleanup

## Architecture

```
┌─────────────────────────────────────────────────┐
│           NexusSessionManager                    │
│  ┌──────────────────────────────────────────┐   │
│  │  CrossChannelSession (user-123)          │   │
│  │                                          │   │
│  │  State: {conversation_history, ...}     │   │
│  │  Activity: {api, cli, mcp}              │   │
│  │  Memory Pool: shared-pool-xyz           │   │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│              Nexus Platform                     │
│  ┌───────┐   ┌───────┐   ┌───────┐             │
│  │  API  │   │  CLI  │   │  MCP  │             │
│  └───────┘   └───────┘   └───────┘             │
└─────────────────────────────────────────────────┘
```

## Running the Example

```bash
# From the session-management directory
python workflow.py
```

## Expected Output

```
============================================================
Cross-Channel Session Management Example
============================================================

1. Initializing Nexus with session management...
   ✓ Nexus platform initialized
   ✓ Session manager created (10min cleanup interval)

2. Creating conversation agent...
   ✓ ConversationAgent created with mock provider

3. Deploying with session management...
   ✓ Deployed across channels:
     - api: /api/workflows/chat/execute
     - cli: nexus run chat
     - mcp: chat

============================================================
Simulating Cross-Channel Conversation
============================================================

   Session created: abc123...
   User ID: user-123
   Expires: 2025-01-01 15:00:00

   [API Channel]
   User: What's the weather like?
   ✓ State updated via API
   ✓ Conversation history: 2 messages

   [CLI Channel]
   User checks conversation history...
   ✓ Retrieved 2 messages from API
   ✓ Last message: "I'll check the weather for you."
   ✓ Added new message via CLI
   ✓ Total messages now: 3

   [MCP Channel]
   Tool retrieves full context...
   ✓ Retrieved 3 messages
   ✓ Message count: 3
   ✓ CLI accessed: True

============================================================
Verifying Cross-Channel Consistency
============================================================

   API State:  3 messages
   CLI State:  3 messages
   MCP State:  3 messages

   ✓ All channels see identical state!

============================================================
Channel Activity Tracking
============================================================

   Session abc123...:
   User: user-123
   Created: 14:00:00
   Last accessed: 14:00:05

   Channel Activity:
     - api: 14:00:01
     - cli: 14:00:03
     - mcp: 14:00:05

============================================================
Memory Pool Integration
============================================================

   Binding session to shared memory pool...
   ✓ Session bound to memory pool: shared-pool-xyz
   ✓ Agents can now share memory via this session
   ✓ Stored 2 agent memories in session
   ✓ Memories accessible to all agents: 2

============================================================
Session Management Summary
============================================================

   Total Sessions: 1
   Active Session: abc123...
   Channels Used: ['api', 'cli', 'mcp']
   State Keys: ['conversation_history', 'message_count', 'cli_accessed', 'agent_memories']
   Memory Pool: shared-pool-xyz

============================================================
Example Complete
============================================================

Key Takeaways:
  1. Sessions maintain state across API, CLI, and MCP channels
  2. All channels see the same state in real-time
  3. Channel activity is tracked automatically
  4. Sessions can bind to memory pools for agent collaboration
  5. Session expiration and cleanup handled automatically
```

## Key Components

### CrossChannelSession

Represents a user session across multiple channels:

```python
session = CrossChannelSession(
    session_id="custom-id",  # Optional, auto-generated
    user_id="user-123",
    expires_at=datetime.now() + timedelta(hours=1)
)

# Update state
session.update_state({"key": "value"}, channel="api")

# Get state
state = session.get_state(channel="cli")  # Returns copy
```

### NexusSessionManager

Manages sessions across all channels:

```python
manager = NexusSessionManager(cleanup_interval=300)

# Create session
session = manager.create_session(user_id="user-123", ttl_hours=1)

# Update state
manager.update_session_state(
    session.session_id,
    {"data": "value"},
    channel="api"
)

# Get state
state = manager.get_session_state(session.session_id, channel="cli")

# Bind memory pool
manager.bind_memory_pool(session.session_id, "pool-id")

# Cleanup expired sessions
count = manager.cleanup_expired_sessions()
```

### deploy_with_sessions

Deploy agent with session support:

```python
from kaizen.integrations.nexus import deploy_with_sessions, NexusSessionManager

manager = NexusSessionManager()
channels = deploy_with_sessions(agent, app, "chat", manager)

# Create and use session
session = manager.create_session(user_id="user-123")
manager.update_session_state(session.session_id, {...}, "api")
state = manager.get_session_state(session.session_id, "cli")
```

## Use Cases

### 1. Multi-Channel Conversation

User starts conversation in CLI, continues in web UI (API), completes via Claude Code (MCP):

```python
# CLI: Initial message
manager.update_session_state(sid, {"msg": "Start"}, "cli")

# API: Continue conversation
state = manager.get_session_state(sid, "api")
manager.update_session_state(sid, {"msg": "Continue"}, "api")

# MCP: Complete task
state = manager.get_session_state(sid, "mcp")
# All history available
```

### 2. Agent Memory Sharing

Multiple agents share context via session:

```python
# Bind to shared memory pool
manager.bind_memory_pool(session_id, "shared-pool")

# Agent 1 stores context
manager.update_session_state(sid, {"context": "..."}, "api")

# Agent 2 accesses context
state = manager.get_session_state(sid, "cli")
# Context available to Agent 2
```

### 3. Session Recovery

User disconnects and reconnects:

```python
# Before disconnect
manager.update_session_state(sid, {"work": "in-progress"})

# After reconnect
state = manager.get_session_state(sid)
# Work state preserved
```

## Session Lifecycle

1. **Creation**: `manager.create_session(user_id, ttl_hours)`
2. **Active Use**: State updates and retrievals via channels
3. **Refresh**: Automatic expiration extension on access
4. **Expiration**: TTL expires (default: 1 hour)
5. **Cleanup**: Automatic removal via cleanup interval

## Configuration Options

### Session Manager

```python
manager = NexusSessionManager(
    cleanup_interval=300  # Cleanup every 5 minutes
)
```

### Session Creation

```python
session = manager.create_session(
    session_id="custom-id",  # Optional
    user_id="user-123",
    ttl_hours=2  # Custom TTL
)
```

## Related Examples

- **Multi-Channel Deployment** - Basic multi-channel deployment
- **API Deployment** - API-specific deployment
- **CLI Deployment** - CLI-specific deployment
- **MCP Deployment** - MCP-specific deployment

## Phase Information

This example demonstrates **Phase 3** of TODO-149: Unified Session Management

**Objectives**:
- Session consistency across channels ✓
- State management for AI operations ✓
- Session synchronization ✓
- Memory pool integration ✓

**Tests**: 47 tests (35 unit + 12 integration) - All passing
