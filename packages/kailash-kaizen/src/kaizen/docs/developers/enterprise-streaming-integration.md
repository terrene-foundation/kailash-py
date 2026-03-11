# Enterprise-App Streaming Integration Developer Guide

This guide covers the Kaizen framework's integration with the Enterprise-App platform, providing real-time streaming execution events, session management, agent discovery, and trust posture mapping.

## Overview

The Enterprise-App streaming integration enables:

1. **Real-time Event Streaming**: 10 event types for execution monitoring
2. **Session Management**: Persistent session state with pause/resume
3. **User-Filtered Discovery**: Permission-based agent discovery
4. **Skill Metadata**: UI-ready agent metadata for platform display
5. **Trust Posture Mapping**: Map verification results to trust levels

## Quick Start

### Streaming Execution

```python
from kaizen.execution.streaming_executor import StreamingExecutor, format_sse
from kaizen.execution.events import StartedEvent, CompletedEvent, ErrorEvent

# Create executor
executor = StreamingExecutor()

# Execute with streaming events
async for event in executor.execute_with_events(
    agent=my_agent,
    task="Analyze this document",
    session_id="session-123",
    trust_chain_id="chain-abc",
):
    # Send as SSE to client
    sse = format_sse(event)
    await response.write(sse)

    # Or handle specific events
    if isinstance(event, CompletedEvent):
        print(f"Done! Tokens: {event.total_tokens}, Cost: ${event.total_cost_usd}")
```

### Session Management

```python
from kaizen.session import KaizenSessionManager, InMemorySessionStorage

# Create manager (uses filesystem by default)
manager = KaizenSessionManager()

# Or with custom storage
manager = KaizenSessionManager(storage=InMemorySessionStorage())

# Start session
session_id = await manager.start_session(
    agent=my_agent,
    trust_chain_id="chain-123",
    metadata={"user_id": "user-456"},
)

# Add messages
await manager.add_message(session_id, "user", "Hello")
await manager.add_message(session_id, "assistant", "Hi there!")

# Update metrics
await manager.update_metrics(
    session_id,
    tokens_added=100,
    cost_added_usd=0.01,
)

# Pause/resume
await manager.pause_session(session_id)
state = await manager.resume_session(session_id)

# End session
summary = await manager.end_session(
    session_id,
    status="completed",
    final_output="Task completed successfully",
)
print(f"Total: {summary.total_tokens} tokens, ${summary.total_cost_usd}")
```

### Agent Discovery

```python
from kaizen.orchestration.discovery import UserFilteredAgentDiscovery, AgentSkillMetadata
from kaizen.orchestration.registry import AgentRegistry

registry = AgentRegistry()
discovery = UserFilteredAgentDiscovery(registry)

# Find agents for user
agents = await discovery.find_agents_for_user(
    user_id="user-123",
    organization_id="org-456",
)

for agent in agents:
    print(f"{agent.agent_id}: {agent.access.permission_level}")

# Get skill metadata for UI
skill = await discovery.get_skill_metadata("agent-001")
print(f"Name: {skill.name}")
print(f"Description: {skill.description}")
print(f"Capabilities: {skill.capabilities}")
```

### Trust Posture Mapping

```python
from kaizen.trust.postures import TrustPostureMapper, TrustPosture

mapper = TrustPostureMapper(
    sensitive_capabilities=["delete", "execute_code"],
    high_risk_tools=["bash_command", "delete_file"],
)

# Map verification result
result = mapper.map_verification_result(
    verification_result,
    requested_capability="delete_records",
)

if result.posture == TrustPosture.FULL_AUTONOMY:
    # Agent can act freely
    pass
elif result.posture == TrustPosture.SUPERVISED:
    # Audit logging required
    pass
elif result.posture == TrustPosture.HUMAN_DECIDES:
    # Require human approval
    pass
elif result.posture == TrustPosture.BLOCKED:
    # Deny the action
    pass
```

## Event Types

The streaming integration provides 10 event types:

| Event Type | Class | Description |
|------------|-------|-------------|
| STARTED | `StartedEvent` | Execution began |
| THINKING | `ThinkingEvent` | Agent reasoning |
| MESSAGE | `MessageEvent` | Chat message |
| TOOL_USE | `ToolUseEvent` | Tool invocation started |
| TOOL_RESULT | `ToolResultEvent` | Tool completed |
| SUBAGENT_SPAWN | `SubagentSpawnEvent` | Subagent created |
| COST_UPDATE | `CostUpdateEvent` | Cost metrics update |
| PROGRESS | `ProgressEvent` | Progress indicator |
| COMPLETED | `CompletedEvent` | Execution finished |
| ERROR | `ErrorEvent` | Error occurred |

### Event Structure

All events inherit from `ExecutionEvent` and include:

```python
@dataclass
class ExecutionEvent:
    event_type: EventType
    session_id: str = ""
    timestamp: str = ""  # ISO 8601 format
```

Each event type adds specific fields:

```python
@dataclass
class StartedEvent(ExecutionEvent):
    execution_id: str = ""
    agent_id: str = ""
    agent_name: str = ""
    trust_chain_id: str = ""

@dataclass
class CompletedEvent(ExecutionEvent):
    execution_id: str = ""
    total_tokens: int = 0
    total_cost_cents: int = 0
    total_cost_usd: float = 0.0
    duration_ms: int = 0
    cycles_used: int = 0
    tools_used: int = 0
    subagents_spawned: int = 0
```

## Session State

Session state tracks:

- **Messages**: Conversation history
- **Tool Invocations**: Tool calls with inputs/outputs
- **Subagent Calls**: Delegated tasks
- **Metrics**: Tokens, cost, cycles

```python
@dataclass
class SessionState:
    session_id: str
    agent_id: str
    trust_chain_id: str
    status: SessionStatus
    messages: List[Message]
    tool_invocations: List[ToolInvocation]
    subagent_calls: List[SubagentCall]
    tokens_used: int
    cost_usd: float
    cycles_used: int
```

### Storage Backends

Two storage backends are provided:

1. **FilesystemSessionStorage**: Persists to JSON files (default)
2. **InMemorySessionStorage**: In-memory for testing

Custom backends can implement the `SessionStorage` interface:

```python
class SessionStorage(ABC):
    @abstractmethod
    async def save(self, session_id: str, state: SessionState) -> None:
        pass

    @abstractmethod
    async def load(self, session_id: str) -> Optional[SessionState]:
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        pass

    @abstractmethod
    async def list_sessions(self, ...) -> List[str]:
        pass
```

## Trust Postures

Four trust postures control agent autonomy:

| Posture | Value | Description |
|---------|-------|-------------|
| FULL_AUTONOMY | `full_autonomy` | Agent acts freely |
| SUPERVISED | `supervised` | Actions logged, not blocked |
| HUMAN_DECIDES | `human_decides` | Each action needs approval |
| BLOCKED | `blocked` | Action denied |

### Posture Constraints

Constraints accompany posture decisions:

```python
@dataclass
class PostureConstraints:
    audit_required: bool = False
    approval_required: bool = False
    log_level: str = "info"
    allowed_capabilities: Optional[List[str]] = None
    blocked_capabilities: Optional[List[str]] = None
    max_actions_before_review: Optional[int] = None
    require_human_approval_for: Optional[List[str]] = None
```

## SSE Formatting

Format events for Server-Sent Events streaming:

```python
from kaizen.execution.streaming_executor import format_sse

for event in events:
    sse = format_sse(event)
    # Returns: "data: {...json...}\n\n"
```

## Integration with Enterprise-App Platform

### Registering Agents

```python
from kaizen.orchestration.registry import AgentRegistry

registry = AgentRegistry()

# Register agent
agent_id = await registry.register_agent(
    agent=my_agent,
    runtime_id="runtime-001",
    metadata={"capability": "code_generation"},
)
```

### Agent Skill Display

Create UI metadata for agent display:

```python
from kaizen.orchestration.discovery import AgentSkillMetadata

skill = AgentSkillMetadata.from_agent(
    agent=my_agent,
    suggested_prompts=["Analyze this code", "Explain this concept"],
    avg_execution_time=2.5,
    avg_cost_cents=10,
)

# Serialize for API response
data = skill.to_dict()
```

### Access Control

Filter agents by user permissions:

```python
discovery = UserFilteredAgentDiscovery(
    registry,
    permission_checker=my_permission_checker,
)

# Only returns agents user can access
agents = await discovery.find_agents_for_user(
    user_id="user-123",
    organization_id="org-456",
)
```

## Best Practices

1. **Always provide session_id**: Enables session tracking and resume
2. **Set trust_chain_id**: Required for trust delegation tracking
3. **Handle all event types**: Don't ignore error events
4. **Use SSE for real-time updates**: format_sse() handles proper formatting
5. **End sessions properly**: Call end_session() to create summary
6. **Check posture before actions**: Map verification to posture for sensitive operations

## Testing

The integration includes comprehensive tests:

- **Unit Tests**: 240 tests covering all components
- **Integration Tests**: 51 tests for end-to-end flows

Run tests:

```bash
# Unit tests
pytest tests/unit/execution/ tests/unit/session/ tests/unit/orchestration/test_discovery.py tests/unit/trust/test_postures.py -v

# Integration tests
pytest tests/integration/enterprise_app/ -v
```

## API Reference

### Modules

- `kaizen.execution.events`: Event dataclasses
- `kaizen.execution.streaming_executor`: StreamingExecutor and format_sse
- `kaizen.session`: KaizenSessionManager and storage backends
- `kaizen.orchestration.discovery`: UserFilteredAgentDiscovery and AgentSkillMetadata
- `kaizen.trust.postures`: TrustPostureMapper and posture enums

### Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `StreamingExecutor` | execution.streaming_executor | Event-based execution |
| `KaizenSessionManager` | session.manager | Session lifecycle |
| `SessionState` | session.state | Session data model |
| `UserFilteredAgentDiscovery` | orchestration.discovery | Filtered agent lookup |
| `AgentSkillMetadata` | orchestration.discovery | UI agent metadata |
| `TrustPostureMapper` | trust.postures | Verification to posture |
