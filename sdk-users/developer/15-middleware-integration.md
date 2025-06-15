# Middleware Integration Guide

## Overview
The Kailash middleware layer provides enterprise-grade features for frontend integration, real-time communication, and workflow management. This guide covers practical usage patterns for building applications with the middleware.

## Core Concepts

### 1. Middleware Architecture
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Middleware     │    │   Kailash Core  │
│                 │    │                  │    │                 │
│  • React/Vue    │────│  • Agent-UI      │────│  • Workflows    │
│  • JavaScript   │    │  • Real-time     │    │  • Nodes        │
│  • Mobile       │    │  • API Gateway   │    │  • Runtime      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### 2. Key Components
- **AgentUIMiddleware**: Session-based workflow management
- **RealtimeMiddleware**: WebSocket/SSE event streaming
- **APIGateway**: Unified REST API with documentation
- **AIChatMiddleware**: AI-powered workflow creation
- **EventStream**: Real-time event broadcasting

## Quick Start

### Basic Middleware Setup
```python
from kailash.middleware import create_gateway

# Create gateway with all middleware components
gateway = create_gateway(
    title="My Application",
    description="Kailash-powered application",
    cors_origins=["http://localhost:3000"],
    enable_docs=True,
    max_sessions=100
)

# Access components
agent_ui = gateway.agent_ui
realtime = gateway.realtime
schema_registry = gateway.schema_registry

# Start the server
if __name__ == "__main__":
    gateway.run(port=8000)
```

### Frontend Integration Example
```javascript
// Create session
const sessionResponse = await fetch('http://localhost:8000/api/sessions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_id: 'frontend_user'})
});
const session = await sessionResponse.json();

// Execute workflow
const executionResponse = await fetch('http://localhost:8000/api/executions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        session_id: session.session_id,
        workflow_id: 'data_processing',
        inputs: {file_path: '/data/customers.csv'}
    })
});

// Monitor via WebSocket
const ws = new WebSocket(`ws://localhost:8000/ws?session_id=${session.session_id}`);
ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log('Workflow update:', update);
};
```

## Session Management

### Creating and Managing Sessions
```python
import asyncio
from kailash.middleware import AgentUIMiddleware

async def session_example():
    agent_ui = AgentUIMiddleware()

    # Create session
    session_id = await agent_ui.create_session(
        user_id="user123",
        metadata={"department": "analytics", "role": "analyst"}
    )

    # Get session info
    session = await agent_ui.get_session(session_id)
    print(f"Session created: {session.session_id}")

    # Session automatically expires after timeout
    # Manual cleanup
    await agent_ui.close_session(session_id)
```

### Session-Based Workflow Execution
```python
async def workflow_execution_example():
    agent_ui = AgentUIMiddleware()
    session_id = await agent_ui.create_session(user_id="analyst")

    # Register workflow in session
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    reader_id = builder.add_node("CSVReaderNode",
        config={"name": "reader", "file_path": "/data/input.csv"}
    )

    await agent_ui.register_workflow(
        workflow_id="data_analysis",
        workflow=builder,
        session_id=session_id
    )

    # Execute workflow
    execution_id = await agent_ui.execute_workflow(
        session_id=session_id,
        workflow_id="data_analysis",
        inputs={"custom_param": "value"}
    )

    # Monitor execution
    status = await agent_ui.get_execution_status(execution_id, session_id)
    print(f"Execution status: {status['status']}")
```

## Real-Time Communication

### Event Subscription
```python
from kailash.middleware.events import EventType

async def event_handling_example():
    agent_ui = AgentUIMiddleware()
    realtime = RealtimeMiddleware(agent_ui)

    # Define event handler
    async def workflow_event_handler(event):
        print(f"Event: {event.type}")
        if event.type == EventType.WORKFLOW_COMPLETED:
            print(f"Workflow {event.workflow_id} completed!")
        elif event.type == EventType.WORKFLOW_FAILED:
            print(f"Workflow {event.workflow_id} failed: {event.data.get('error')}")

    # Subscribe to events
    await agent_ui.subscribe_to_events(
        subscriber_id="my_app",
        callback=workflow_event_handler,
        event_types=[
            EventType.WORKFLOW_STARTED,
            EventType.WORKFLOW_COMPLETED,
            EventType.WORKFLOW_FAILED,
            EventType.WORKFLOW_PROGRESS
        ]
    )

    # Events will be automatically delivered to handler
```

### WebSocket Integration
```python
async def websocket_example():
    realtime = RealtimeMiddleware(agent_ui)

    # Register WebSocket endpoint
    @realtime.websocket_handler
    async def handle_websocket(websocket, session_id):
        await websocket.accept()

        # Subscribe to session events
        async def send_to_client(event):
            await websocket.send_json(event.to_dict())

        await agent_ui.subscribe_to_events(
            f"ws_{session_id}",
            send_to_client,
            session_id=session_id
        )

        # Handle incoming messages
        try:
            while True:
                data = await websocket.receive_json()
                # Process client messages
                await handle_client_message(data, session_id)
        except:
            await agent_ui.unsubscribe_from_events(f"ws_{session_id}")
```

## Dynamic Workflow Creation

### From JSON Configuration
```python
async def dynamic_workflow_example():
    agent_ui = AgentUIMiddleware()
    session_id = await agent_ui.create_session(user_id="developer")

    # Workflow configuration from frontend
    workflow_config = {
        "nodes": [
            {
                "id": "data_input",
                "type": "PythonCodeNode",
                "config": {
                    "name": "data_input",
                    "code": "result = {'data': input_data, 'ready': True}"
                }
            },
            {
                "id": "processor",
                "type": "PythonCodeNode",
                "config": {
                    "name": "processor",
                    "code": '''
data = input_data.get('data', {})
result = {
    'processed_data': data,
    'count': len(data) if isinstance(data, (list, dict)) else 1
}
'''
                }
            }
        ],
        "connections": [
            {
                "from_node": "data_input",
                "from_output": "result",
                "to_node": "processor",
                "to_input": "input_data"
            }
        ]
    }

    # Create workflow from config
    workflow_id = await agent_ui.create_dynamic_workflow(
        session_id=session_id,
        workflow_config=workflow_config,
        workflow_id="user_generated"
    )

    print(f"Created dynamic workflow: {workflow_id}")
```

### AI-Assisted Workflow Creation
```python
from kailash.middleware import AIChatMiddleware

async def ai_workflow_example():
    agent_ui = AgentUIMiddleware()
    ai_chat = AIChatMiddleware(agent_ui)

    session_id = await agent_ui.create_session(user_id="user")
    await ai_chat.start_chat_session(session_id)

    # Ask AI to create workflow
    response = await ai_chat.send_message(
        session_id,
        "Create a workflow that reads a CSV file and counts the rows",
        context={"available_files": ["/data/customers.csv"]}
    )

    # AI generates workflow configuration
    if response.get("workflow_config"):
        workflow_id = await agent_ui.create_dynamic_workflow(
            session_id=session_id,
            workflow_config=response["workflow_config"]
        )
        print(f"AI created workflow: {workflow_id}")
```

## Schema and Node Discovery

### Node Schema Generation
```python
async def schema_example():
    gateway = create_gateway()

    # Get available nodes
    available_nodes = await gateway.agent_ui.get_available_nodes()

    for node_info in available_nodes:
        print(f"Node: {node_info['type']}")
        print(f"Description: {node_info['description']}")
        print(f"Parameters: {node_info['schema']['parameters']}")
        print("---")

    # Generate schema for specific node
    from kailash.nodes.base import NodeRegistry
    node_class = NodeRegistry.get_node("CSVReaderNode")
    schema = gateway.schema_registry.get_node_schema(node_class)

    print(f"CSV Reader schema: {schema}")
```

### Frontend Form Generation
```javascript
// Get node schemas for form generation
const nodesResponse = await fetch('http://localhost:8000/api/nodes');
const nodes = await nodesResponse.json();

// Generate form fields from schema
function generateForm(nodeType) {
    const node = nodes.find(n => n.type === nodeType);
    const form = document.createElement('form');

    for (const [paramName, param] of Object.entries(node.schema.parameters)) {
        const label = document.createElement('label');
        label.textContent = param.description;

        const input = document.createElement('input');
        input.name = paramName;
        input.type = param.type === 'int' ? 'number' : 'text';
        input.required = param.required;

        form.appendChild(label);
        form.appendChild(input);
    }

    return form;
}
```

## Authentication and Security

### Using Middleware Auth
```python
from kailash.middleware.auth import (
    KailashJWTAuthManager,
    MiddlewareAccessControlManager
)
from dataclasses import dataclass

@dataclass
class AuthConfig:
    secret_key: str = "your-secret-key"
    algorithm: str = "HS256"
    expiration_hours: int = 24

async def auth_example():
    # Initialize authentication
    auth_config = AuthConfig()
    auth_manager = KailashJWTAuthManager(auth_config)
    access_control = MiddlewareAccessControlManager(strategy="rbac")

    # Create token
    token = auth_manager.create_token({
        "user_id": "user123",
        "role": "analyst",
        "exp": datetime.utcnow() + timedelta(hours=24)
    })

    # Validate token
    payload = auth_manager.validate_token(token)
    if payload:
        print(f"Valid user: {payload['user_id']}")

    # Check permissions
    allowed = access_control.check_permission(
        user_id="user123",
        resource="workflow:data_processing",
        action="execute"
    )
```

## Advanced Patterns

### Workflow Templates
```python
async def template_example():
    agent_ui = AgentUIMiddleware()

    # Create reusable workflow template
    template_config = {
        "name": "Data Processing Template",
        "description": "Standard data processing pipeline",
        "nodes": [
            {
                "id": "input",
                "type": "CSVReaderNode",
                "config": {
                    "name": "input",
                    "file_path": "{{ input_file }}"  # Template variable
                }
            },
            {
                "id": "process",
                "type": "PythonCodeNode",
                "config": {
                    "name": "process",
                    "code": "result = {'count': len(input_data)}"
                }
            }
        ],
        "connections": [
            {
                "from_node": "input",
                "from_output": "output",
                "to_node": "process",
                "to_input": "input_data"
            }
        ]
    }

    # Register as shared template
    await agent_ui.register_workflow(
        workflow_id="data_processing_template",
        workflow=WorkflowBuilder.from_dict(template_config),
        make_shared=True
    )
```

### Monitoring and Metrics
```python
async def monitoring_example():
    gateway = create_gateway()

    # Get middleware statistics
    stats = gateway.agent_ui.get_stats()
    print(f"Active sessions: {stats['active_sessions']}")
    print(f"Workflows executed: {stats['workflows_executed']}")
    print(f"Events emitted: {stats['events_emitted']}")

    # Real-time statistics
    realtime_stats = gateway.realtime.get_stats()
    print(f"Events processed: {realtime_stats['events_processed']}")
    print(f"Average latency: {realtime_stats['latency_stats']['avg_ms']}ms")

    # Schema statistics
    schema_stats = gateway.schema_registry.get_stats()
    print(f"Schemas generated: {schema_stats['schemas_generated']}")
    print(f"Cache hit rate: {schema_stats['cache_hit_rate']:.2%}")
```

## Deployment Patterns

### Production Configuration
```python
import os
from kailash.middleware import create_gateway

def create_production_gateway():
    return create_gateway(
        title="Production Application",
        cors_origins=os.getenv("CORS_ORIGINS", "").split(","),
        enable_docs=os.getenv("ENABLE_DOCS", "false").lower() == "true",
        max_sessions=int(os.getenv("MAX_SESSIONS", "1000")),
        session_timeout_minutes=int(os.getenv("SESSION_TIMEOUT", "60")),
        enable_workflow_sharing=True
    )

# Environment-specific settings
if __name__ == "__main__":
    gateway = create_production_gateway()
    port = int(os.getenv("PORT", "8000"))
    gateway.run(host="0.0.0.0", port=port)
```

### Docker Integration
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Expose middleware port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "middleware_app"]
```

## Best Practices

### 1. Error Handling
```python
async def robust_middleware_example():
    try:
        agent_ui = AgentUIMiddleware()
        session_id = await agent_ui.create_session(user_id="user")

        execution_id = await agent_ui.execute_workflow(
            session_id=session_id,
            workflow_id="data_processing",
            inputs={"file_path": "/data/input.csv"}
        )

        # Wait for completion with timeout
        import asyncio
        await asyncio.sleep(2)  # Allow processing time

        status = await agent_ui.get_execution_status(execution_id)
        if status["status"] == "failed":
            print(f"Workflow failed: {status['error']}")

    except Exception as e:
        print(f"Middleware error: {e}")
        # Cleanup and recovery logic
```

### 2. Resource Management
```python
async def resource_management_example():
    # Use context managers for automatic cleanup
    async with AgentUIMiddleware() as agent_ui:
        session_id = await agent_ui.create_session(user_id="user")

        # Session will be automatically cleaned up
        try:
            await agent_ui.execute_workflow(
                session_id=session_id,
                workflow_id="processing"
            )
        finally:
            # Cleanup happens automatically
            pass
```

### 3. Performance Optimization
```python
# Use connection pooling and caching
gateway = create_gateway(
    enable_caching=True,
    cache_ttl_seconds=300,
    max_connections=100,
    connection_timeout_seconds=30
)

# Batch event processing
realtime = RealtimeMiddleware(
    agent_ui,
    enable_batching=True,
    batch_size=10,
    batch_timeout_ms=100
)
```

This middleware integration enables powerful frontend applications with real-time workflow management, dynamic schema generation, and comprehensive event streaming.
