# XAI-UI Middleware Guide

## Overview

XAI-UI (eXplainable AI - User Interface) is Kailash SDK's middleware layer for sophisticated agent-UI communication. Inspired by the AG-UI Protocol, XAI-UI provides real-time, bidirectional communication between AI agents and frontend applications with a focus on explainability and transparency.

## Key Features

### 1. Event-Driven Architecture

XAI-UI uses 16 standard event types for comprehensive agent-UI communication:

```python
from kailash.xai_ui.events import XAIEvent, XAIEventType

# Execution lifecycle
XAIEventType.RUN_STARTED
XAIEventType.RUN_FINISHED

# Text messaging
XAIEventType.TEXT_MESSAGE_START
XAIEventType.TEXT_MESSAGE_CONTENT
XAIEventType.TEXT_MESSAGE_CHUNK
XAIEventType.TEXT_MESSAGE_END

# Tool execution
XAIEventType.TOOL_CALL_START
XAIEventType.TOOL_CALL_ARGS
XAIEventType.TOOL_CALL_CHUNK
XAIEventType.TOOL_CALL_END

# State synchronization
XAIEventType.STATE_SNAPSHOT
XAIEventType.STATE_DELTA

# UI and interaction
XAIEventType.MEDIA_FRAME
XAIEventType.GENERATIVE_UI
XAIEventType.APPROVAL_REQUEST
XAIEventType.USER_RESPONSE

```

### 2. Transport Agnostic

Supports multiple transport mechanisms:

- **Server-Sent Events (SSE)**: Default for unidirectional streaming
- **WebSocket**: For bidirectional real-time communication
- **Webhook**: For server-to-server communication

### 3. State Synchronization

Efficient state updates using JSON Patch (RFC 6902):

```python
# Only send changes, not full state
state_manager.update_state(session_id, {"progress": 50})
# Generates: [{"op": "replace", "path": "/progress", "value": 50}]

```

### 4. Human-in-the-Loop Workflows

Enable user approval and feedback:

```python
async def execute_with_approval(self, 'tool_name', args: dict):
    # Request approval
    event = XAIEvent(
        type=XAIEventType.APPROVAL_REQUEST,
        tool_name=tool_name,
        tool_args=args
    )
    await self.router.emit(event)

    # Wait for user response
    response = await self.wait_for_response()
    if response.approved:
        return await self.execute_tool(tool_name, args)

```

### 5. Generative UI

Dynamically generate UI components:

```python
# Generate a custom form
ui_event = XAIEvent(
    type=XAIEventType.GENERATIVE_UI,
    ui_component={
        "type": "Form",
        "props": {
            "fields": [
                {"name": "query", "type": "text", "label": "Search Query"},
                {"name": "limit", "type": "number", "label": "Result Limit"}
            ]
        }
    }
)

```

## Usage Examples

### Basic Agent Communication

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes import XAIUIBridgeNode
from kailash.runtime.local import LocalRuntime

# Create workflow with XAI-UI bridge
workflow = WorkflowBuilder()

# Add XAI-UI bridge for communication
workflow.add_node("XAIUIBridgeNode", "bridge", {
    "session_id": "chat-123",
    "transport": "sse",
    "enable_explanations": True
})

# Add your agent logic
workflow.add_node("LLMAgentNode", "agent", {
    "model": "gpt-4",
    "prompt": "You are a helpful AI assistant"
})
workflow.add_connection("agent", "result", "bridge", "input")

# Execute with real-time UI updates
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "agent": {"query": "Explain quantum computing"}
})

```

### React Frontend Integration

```typescript
import { useXAIUI } from '@kailash/xai-ui-react';

function ChatInterface() {
  const {
    agentState,
    events,
    connected,
    sendResponse
  } = useXAIUI('chat-123');

  // Handle approval requests
  useEffect(() => {
    const approvalEvent = events.find(
      e => e.type === 'approval.request' && !e.handled
    );

    if (approvalEvent) {
      const approved = window.confirm(
        `Allow agent to call ${approvalEvent.tool_name}?`
      );
      sendResponse(approvalEvent.id, { approved });
    }
  }, [events]);

  return (
    <div>
      <div>Status: {connected ? 'Connected' : 'Disconnected'}</div>
      <div>Agent State: {JSON.stringify(agentState)}</div>
      {/* Render messages, UI components, etc. */}
    </div>
  );
}
```

### Streaming Text Generation

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

class StreamingAgentNode(AsyncNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Bridge will be connected via workflow
        self.session_id = kwargs.get('session_id', self.id)

    async def async_run(self, prompt: str) -> Dict[str, Any]:
        # Example streaming response
        response = "Quantum computing uses quantum bits (qubits) that can be in superposition."

        # Return structured result for the bridge
        return {
            "text": response,
            "metadata": {"model": "gpt-4"},
            "stream_events": [
                {"type": "TEXT_MESSAGE_START"},
                {"type": "TEXT_MESSAGE_CONTENT", "content": response},
                {"type": "TEXT_MESSAGE_END"}
            ]
        }

```

### Tool Execution with Approval

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

class ToolAgentNode(AsyncNode):
    async def async_run(self, **inputs) -> Dict[str, Any]:
        # Example tool execution with approval request
        tool_request = {
            "tool_name": "database_query",
            "args": {"query": "SELECT * FROM users"},
            "require_approval": True
        }

        # Simulate approval flow
        # In real implementation, this would interact with the bridge
        approved = inputs.get("user_approved", True)

        if not approved:
            return {"status": "cancelled", "reason": "User denied approval"}

        # Simulate database query result
        result = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]

        return {"result": result, "tool_request": tool_request}

```

## Architecture Patterns

### 1. Event Router Pattern

```python
# Centralized event routing
router = XAIEventRouter()

# Register handlers
router.register_handler(
    XAIEventType.USER_RESPONSE,
    handle_user_response
)

# Add transports
router.add_transport("sse", SSETransport())
router.add_transport("ws", WebSocketTransport())

# Start routing
await router.start()

```

### 2. State Management Pattern

```python
# Initialize state
state_manager.initialize_state(session_id, {
    "stage": "processing",
    "progress": 0,
    "results": []
})

# Update with deltas
for i in range(100):
    patch = state_manager.update_state(
        session_id,
        {"progress": i + 1}
    )
    # Only sends the change, not full state

```

### 3. Middleware Pattern

```python
# Add authentication
@router.middleware
async def workflow.()  # Type signature example:
    if not event.metadata.get("auth_token"):
        raise AuthenticationError()
    return await next(event)

# Add rate limiting
@router.middleware
async def workflow.()  # Type signature example:
    if not rate_limiter.check(event.session_id):
        raise RateLimitError()
    return await next(event)

```

## Performance Considerations

1. **Event Batching**: Group multiple events to reduce overhead
2. **State Compression**: Use JSON Patch for minimal data transfer
3. **Connection Pooling**: Reuse transport connections
4. **Binary Optimization**: 60% smaller payloads for media
5. **Selective Updates**: Only update affected UI components

## Security Best Practices

1. **Authentication**: Always verify session tokens
2. **Authorization**: Check permissions for tool execution
3. **Input Validation**: Validate all user responses
4. **Rate Limiting**: Prevent abuse with request limits
5. **Encryption**: Use TLS for all transports

## Migration Guide

### From Basic REST API

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Before: Simple REST
@app.post("/api/chat")
async def workflow.()  # Type signature example:
    response = agent.execute(message)
    return {"response": response}

# After: XAI-UI
@app.post("/api/xai-ui/sessions")
async def create_session():
    session_id = str(uuid.uuid4())
    bridge = XAIUIBridgeNode(session_id=session_id)
    return {"session_id": session_id}

@app.get("/api/xai-ui/sessions/{session_id}/events")
async def workflow.()  # Type signature example:
    return StreamingResponse(
        bridge.stream_events(session_id),
        media_type="text/event-stream"
    )

```

### From WebSocket Only

```python
# Before: Raw WebSocket
@app.websocket("/ws")
async def workflow.()  # Type signature example:
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        response = process(data)
        await websocket.send_text(response)

# After: XAI-UI WebSocket transport
transport = WebSocketTransport()
router.add_transport("websocket", transport)
await router.handle_websocket(websocket, session_id)

```

## Troubleshooting

### Common Issues

1. **Events not receiving**: Check transport connection and session ID
2. **State out of sync**: Verify JSON Patch application order
3. **Approval timeout**: Increase timeout or add retry logic
4. **Performance issues**: Enable event batching and compression

### Debug Mode

```python
# Enable debug logging
import logging
logging.getLogger("kailash.xai_ui").setLevel(logging.DEBUG)

# Event inspection
@router.middleware
async def workflow.()  # Type signature example:
    logger.debug(f"Event: {event.type} - {event.id}")
    result = await next(event)
    logger.debug(f"Result: {result}")
    return result

```

## Related Documentation

- [ADR-0037: XAI-UI Middleware Architecture](../adr/0037-xai-ui-middleware-architecture.md)
- [API Integration Guide](api_integration.md)
- [Agent Coordination Patterns](agent_coordination_patterns.md)
- [Workflow Studio Guide](../workflow_studio.rst)
