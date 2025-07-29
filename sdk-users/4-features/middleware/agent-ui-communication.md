# Agent-UI Communication Guide

*Session-based workflow management with real-time updates*

## Overview

The AgentUIMiddleware provides the core communication layer between AI agents and frontend applications. It manages sessions, workflows, and real-time execution with full state tracking.

## Core Concepts

### Sessions
- **Session**: Isolated workspace for a user's workflows and executions
- **Lifecycle**: Create → Use → Automatic cleanup after timeout
- **State**: All workflow executions and data isolated per session

### Workflows
- **Dynamic Creation**: Build workflows from JSON configurations sent by frontend
- **Execution Tracking**: Monitor progress with real-time updates
- **State Management**: Complete execution history and results

## Quick Start

### Basic Setup
```python
from kailash.api.middleware import AgentUIMiddleware

# Create agent-UI middleware
agent_ui = AgentUIMiddleware(
    enable_dynamic_workflows=True,
    max_sessions=100,
    session_timeout_minutes=60
)

# Create session
session_id = await agent_ui.create_session(
    user_id="user123",
    metadata={"role": "analyst", "department": "data"}
)

```

### Dynamic Workflow Creation
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

# Workflow configuration from frontend
workflow_config = {
    "nodes": [
        {
            "id": "reader",
            "type": "CSVReaderNode",
            "config": {
                "name": "reader",
                "file_path": "/data/customers.csv"
            }
        },
        {
            "id": "analyzer",
            "type": "PythonCodeNode",
            "config": {
                "name": "analyzer",
                "code": '''
data = input_data
result = {
    "total_rows": len(data) if isinstance(data, list) else 1,
    "analysis": "Data processed successfully",
    "timestamp": datetime.now().isoformat()
}
'''
            }
        }
    ],
    "connections": [
        {
            "from_node": "reader",
            "from_output": "output",
            "to_node": "analyzer",
            "to_input": "input_data"
        }
    ]
}

# Create workflow from frontend config
workflow_id = await agent_ui.create_dynamic_workflow(
    session_id=session_id,
    workflow_config=workflow_config,
    workflow_id="data_analysis"
)

```

### Workflow Execution
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

# Execute workflow with monitoring
execution_id = await agent_ui.execute(
    session_id=session_id,
    workflow_id=workflow_id,
    parameters={"custom_param": "value"},
    config_overrides={"timeout": 300}
)

# Monitor execution status
status = await agent_ui.get_execution_status(execution_id, session_id)
print(f"Status: {status['status']}")
print(f"Progress: {status['progress']}%")

if status['status'] == 'completed':
    print(f"Results: {status['outputs']}")
elif status['status'] == 'failed':
    print(f"Error: {status['error']}")

```

## Session Management

### Creating Sessions
```python
# Basic session
session_id = await agent_ui.create_session(user_id="user123")

# Session with metadata
session_id = await agent_ui.create_session(
    user_id="analyst_1",
    metadata={
        "role": "data_analyst",
        "department": "analytics",
        "permissions": ["read_data", "create_reports"],
        "preferences": {"theme": "dark", "auto_save": True}
    }
)

# Custom session ID
session_id = await agent_ui.create_session(
    user_id="user123",
    session_id="custom-session-id",
    metadata={"source": "mobile_app"}
)

```

### Session Information
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

# Get session details
session = await agent_ui.get_session(session_id)
print(f"Created: {session.created_at}")
print(f"User: {session.user_id}")
print(f"Active: {session.active}")
print(f"Workflows: {len(session.workflows)}")
print(f"Executions: {len(session.executions)}")

# List all workflows in session
for workflow_id, workflow in session.workflows.items():
    print(f"Workflow: {workflow_id} - {workflow.name}")

# List executions
for execution_id, execution in session.executions.items():
    print(f"Execution: {execution_id} - {execution['status']}")

```

### Session Cleanup
```python
# Manual cleanup
await agent_ui.close_session(session_id)

# Automatic cleanup happens based on:
# - session_timeout_minutes setting
# - max_sessions limit reached
# - Session inactivity

```

## Workflow Registration

### Pre-built Workflows
```python
from kailash.workflow.builder import WorkflowBuilder

# Create workflow with builder
builder = WorkflowBuilder()

reader_id = builder.add_node("CSVReaderNode", "reader",
    {"file_path": "/data/input.csv"}
)

processor_id = builder.add_node("PythonCodeNode", "processor",
    {"code": "result = {'processed': True}"}
)

builder.add_connection(reader_id, "output", processor_id, "input_data")

# Register for all sessions (shared)
await agent_ui.register_workflow(
    workflow_id="standard_processing",
    workflow=builder,
    make_shared=True
)

# Register for specific session only
await agent_ui.register_workflow(
    workflow_id="custom_analysis",
    workflow=builder,
    session_id=session_id
)

```

### Shared Workflow Behavior

When using `make_shared=True`, the workflow becomes available to all sessions:

```python
# Register a shared workflow
await agent_ui.register_workflow(
    workflow_id="shared_analyzer",
    workflow=builder,
    make_shared=True
)

# Any session can now execute this workflow
session1_id = await agent_ui.create_session()
session2_id = await agent_ui.create_session()

# Both sessions can execute the shared workflow
exec1 = await agent_ui.execute(session1_id, "shared_analyzer", inputs)
exec2 = await agent_ui.execute(session2_id, "shared_analyzer", inputs)
```

**Important Notes:**
- Shared workflows are automatically copied to a session when first executed
- Session-specific workflows take priority over shared workflows with the same ID
- Shared workflows are ideal for common processing patterns used across multiple sessions
- Each session maintains its own execution state, ensuring proper isolation

### Template Workflows
```python
# Register workflow template
template_workflow = WorkflowBuilder()
# ... build template workflow

await agent_ui.register_workflow(
    workflow_id="data_processing_template",
    workflow=template_workflow,
    make_shared=True
)

# Use template in session
workflow_id = await agent_ui.create_dynamic_workflow(
    session_id=session_id,
    workflow_config={
        "template": "data_processing_template",
        "parameters": {
            "input_file": "/data/customers.csv",
            "output_format": "json"
        }
    }
)

```

## Event Subscription

### Basic Event Handling
```python
from kailash.middleware.events import EventType

# Define event handler
async def workflow_event_handler(event):
    print(f"Event: {event.type}")
    print(f"Workflow: {event.workflow_id}")
    print(f"Data: {event.data}")

    if event.type == EventType.WORKFLOW_COMPLETED:
        print("Workflow finished successfully!")
    elif event.type == EventType.WORKFLOW_FAILED:
        print(f"Workflow failed: {event.data.get('error')}")

# Subscribe to events
await agent_ui.subscribe_to_events(
    subscriber_id="my_app",
    callback=workflow_event_handler,
    session_id=session_id,  # Optional: filter by session
    event_types=[
        EventType.WORKFLOW_STARTED,
        EventType.WORKFLOW_COMPLETED,
        EventType.WORKFLOW_FAILED,
        EventType.WORKFLOW_PROGRESS
    ]
)

```

### Filtering Events
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

# Session-specific events only
await agent_ui.subscribe_to_events(
    subscriber_id="session_monitor",
    callback=session_event_handler,
    session_id=session_id
)

# All workflow completion events
await agent_ui.subscribe_to_events(
    subscriber_id="completion_tracker",
    callback=completion_handler,
    event_types=[EventType.WORKFLOW_COMPLETED]
)

# All events for monitoring
await agent_ui.subscribe_to_events(
    subscriber_id="global_monitor",
    callback=global_event_handler
)

```

### Unsubscribing
```python
# Remove event subscription
await agent_ui.unsubscribe_from_events("my_app")

```

## Execution Management

### Execution Control
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

# Start execution
execution_id = await agent_ui.execute(
    session_id=session_id,
    workflow_id=workflow_id,
    parameters={"data": "input_value"}
)

# Cancel running execution
await agent_ui.cancel_execution(execution_id, session_id)

# Get detailed status
status = await agent_ui.get_execution_status(execution_id)
print(f"Status: {status['status']}")
print(f"Started: {status['created_at']}")
print(f"Progress: {status['progress']}%")
print(f"Current Node: {status['current_node']}")

if status['outputs']:
    print(f"Results: {status['outputs']}")

```

### Execution Monitoring
```python
# Monitor execution progress
async def monitor_execution(execution_id, session_id):
    while True:
        status = await agent_ui.get_execution_status(execution_id, session_id)

        if not status:
            print("Execution not found")
            break

        print(f"Progress: {status['progress']}%")

        if status['status'] in ['completed', 'failed', 'cancelled']:
            print(f"Final status: {status['status']}")
            if status['status'] == 'completed':
                print(f"Results: {status['outputs']}")
            elif status['status'] == 'failed':
                print(f"Error: {status['error']}")
            break

        await asyncio.sleep(1)

# Start monitoring
await monitor_execution(execution_id, session_id)

```

## Statistics and Monitoring

### Middleware Statistics
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

# Get comprehensive stats
stats = agent_ui.get_stats()

print(f"Uptime: {stats['uptime_seconds']} seconds")
print(f"Active Sessions: {stats['active_sessions']}")
print(f"Total Sessions Created: {stats['total_sessions_created']}")
print(f"Workflows Executed: {stats['workflows_executed']}")
print(f"Events Emitted: {stats['events_emitted']}")
print(f"Active Executions: {stats['active_executions']}")
print(f"Shared Workflows: {stats['shared_workflows']}")

# Event stream statistics
event_stats = stats['event_stream_stats']
print(f"Events Processed: {event_stats['events_processed']}")
print(f"Subscribers: {event_stats['subscribers']}")

```

### Performance Monitoring
```python
# Track execution performance
import time

start_time = time.time()
execution_id = await agent_ui.execute(
    session_id=session_id,
    workflow_id=workflow_id
)

# Wait for completion
while True:
    status = await agent_ui.get_execution_status(execution_id, session_id)
    if status['status'] in ['completed', 'failed']:
        break
    await asyncio.sleep(0.1)

execution_time = time.time() - start_time
print(f"Execution completed in {execution_time:.2f} seconds")

```

## Error Handling

### Common Error Patterns
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

try:
    # Session operations
    session_id = await agent_ui.create_session(user_id="user123")

    # Workflow operations
    workflow_id = await agent_ui.create_dynamic_workflow(
        session_id=session_id,
        workflow_config=workflow_config
    )

    # Execution operations
    execution_id = await agent_ui.execute(
        session_id=session_id,
        workflow_id=workflow_id
    )

except ValueError as e:
    # Invalid parameters, missing session, etc.
    print(f"Invalid request: {e}")

except Exception as e:
    # Other errors
    print(f"Unexpected error: {e}")

    # Cleanup on error
    if 'session_id' in globals():
        await agent_ui.close_session(session_id)

```

### Validation Errors
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

# Handle workflow validation errors
try:
    workflow_id = await agent_ui.create_dynamic_workflow(
        session_id=session_id,
        workflow_config=invalid_config
    )
except WorkflowValidationError as e:
    print(f"Workflow validation failed: {e}")
    # Show user-friendly error message

# Handle execution errors
try:
    execution_id = await agent_ui.execute(
        session_id=session_id,
        workflow_id="non_existent_workflow"
    )
except ValueError as e:
    print(f"Workflow not found: {e}")

```

## Integration Patterns

### With API Gateway
```python
from kailash.api.middleware import create_gateway

# Create integrated gateway
gateway = create_gateway(
    title="My Application",
    enable_docs=True
)

# Access agent UI from gateway
agent_ui = gateway.agent_ui

# Use as normal
session_id = await agent_ui.create_session(user_id="user123")

```

### With Real-time Middleware
```python
from kailash.api.middleware import AgentUIMiddleware, RealtimeMiddleware

# Create components
agent_ui = AgentUIMiddleware()
realtime = RealtimeMiddleware(agent_ui)

# Events automatically flow to real-time layer
session_id = await agent_ui.create_session(user_id="user123")
# Real-time clients receive session creation event

```

### With AI Chat
```python
from kailash.api.middleware import AIChatMiddleware

# Create AI chat integration
ai_chat = AIChatMiddleware(agent_ui)

# Start chat session
await ai_chat.start_chat_session(session_id)

# AI can create workflows
response = await ai_chat.send_message(
    session_id,
    "Create a workflow that processes customer data",
    context={"available_data": ["/data/customers.csv"]}
)

if response.get("workflow_config"):
    # AI generated a workflow
    workflow_id = await agent_ui.create_dynamic_workflow(
        session_id=session_id,
        workflow_config=response["workflow_config"]
    )

```

## Best Practices

### 1. Session Management
```python
# Use context managers for automatic cleanup
async def with_session(user_id):
    session_id = await agent_ui.create_session(user_id=user_id)
    try:
        yield session_id
    finally:
        await agent_ui.close_session(session_id)

# Usage
async with with_session("user123") as session_id:
    # Use session
    workflow_id = await agent_ui.create_dynamic_workflow(...)
    # Automatic cleanup when done

```

### 2. Error Recovery
```python
# Implement retry logic for transient failures
async def robust_execution(session_id, workflow_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            execution_id = await agent_ui.execute(
                session_id=session_id,
                workflow_id=workflow_id
            )
            return execution_id
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"Attempt {attempt + 1} failed: {e}, retrying...")
            await asyncio.sleep(2 ** attempt)  # Exponential backoff

```

### 3. Performance Optimization
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

# Batch workflow creations
workflows_to_create = [config1, config2, config3]
workflow_ids = []

for config in workflows_to_create:
    workflow_id = await agent_ui.create_dynamic_workflow(
        session_id=session_id,
        workflow_config=config
    )
    workflow_ids.append(workflow_id)

# Execute in parallel
execution_tasks = [
    agent_ui.execute(session_id, wf_id)
    for wf_id in workflow_ids
]
execution_ids = await asyncio.gather(*execution_tasks)

```

## Related Documentation

- **[Real-time Communication](real-time-communication.md)** - Event streaming patterns
- **[API Gateway Guide](api-gateway-guide.md)** - REST API integration
- **[AI Chat Integration](ai-chat-integration.md)** - AI-powered workflow creation
- **[Authentication & Security](authentication-security.md)** - Securing agent-UI communication

## Examples

- **[Comprehensive Demo](../../examples/feature_examples/middleware/middleware_comprehensive_example.py)** - Complete setup
- **[Session Management](../../examples/feature_examples/middleware/session_management_example.py)** - Session patterns
- **[Dynamic Workflows](../../examples/feature_examples/middleware/dynamic_workflow_example.py)** - Frontend-driven workflows
