# Kailash Middleware Layer

A comprehensive middleware layer for agent-frontend communication, providing real-time capabilities, dynamic workflow management, and AI-powered assistance.

## 🎯 Overview

The Kailash Middleware layer bridges the gap between the Kailash SDK and frontend applications, enabling:

- **Real-time Communication**: WebSocket, SSE, and Webhook support
- **Agent-UI Protocol**: Standardized event-driven communication
- **Dynamic Workflows**: Create and modify workflows on-the-fly
- **AI Chat Integration**: Natural language workflow generation
- **Schema Generation**: Dynamic UI form generation
- **Session Management**: Multi-user session handling

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend UI   │◄──►│  API Gateway     │◄──►│  Agent UI       │
│                 │    │  (FastAPI)       │    │  Middleware     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌──────────────────┐             │
         └──────────────►│  Realtime        │◄────────────┘
                        │  Middleware      │
                        │  (WS/SSE/Webhook)│
                        └──────────────────┘
                                 │
                        ┌──────────────────┐
                        │  Event System    │
                        │  (16+ types)     │
                        └──────────────────┘
```

## 🚀 Quick Start

### Basic Server Setup

```python
from kailash.middleware import create_gateway

# Create and run middleware server
gateway = create_gateway(
    title="My App Middleware",
    cors_origins=["http://localhost:3000"],
    enable_docs=True
)

gateway.run(port=8000)
```

### With Custom Configuration

```python
from kailash.middleware import AgentUIMiddleware, RealtimeMiddleware, APIGateway

# Create components
agent_ui = AgentUIMiddleware(max_sessions=1000)
realtime = RealtimeMiddleware(agent_ui)
gateway = APIGateway(agent_ui, realtime)

# Register shared workflows
from kailash.workflow.builder import WorkflowBuilder
builder = WorkflowBuilder()
# ... configure workflow
gateway.register_shared_workflow("data_pipeline", builder)

gateway.run(host="0.0.0.0", port=8000)
```

## 📡 API Endpoints

### Session Management
- `POST /api/sessions` - Create new session
- `GET /api/sessions/{session_id}` - Get session info
- `DELETE /api/sessions/{session_id}` - Close session

### Workflow Operations
- `POST /api/workflows` - Create dynamic workflow
- `GET /api/workflows/{workflow_id}` - Get workflow schema
- `POST /api/executions` - Execute workflow
- `GET /api/executions/{execution_id}` - Get execution status

### Real-time Communication
- `ws://server/ws` - WebSocket connection
- `GET /events` - Server-Sent Events stream
- `POST /api/webhooks` - Register webhook

### Schema & Discovery
- `GET /api/schemas/nodes` - Get available node schemas
- `GET /api/schemas/workflows/{workflow_id}` - Get workflow schema

### AI Chat
- `POST /api/chat/sessions` - Start chat session
- `POST /api/chat/message` - Send chat message
- `GET /api/chat/history/{session_id}` - Get chat history

## 🔄 Real-time Events

The middleware emits 16+ standardized event types:

### Workflow Events
- `workflow.created` - Workflow created
- `workflow.started` - Execution started
- `workflow.progress` - Progress update
- `workflow.completed` - Execution completed
- `workflow.failed` - Execution failed
- `workflow.cancelled` - Execution cancelled

### Node Events
- `node.started` - Node execution started
- `node.progress` - Node progress update
- `node.completed` - Node execution completed
- `node.failed` - Node execution failed
- `node.skipped` - Node was skipped

### UI Events
- `ui.input_required` - User input needed
- `ui.approval_required` - User approval needed
- `ui.choice_required` - User choice needed
- `ui.confirmation_required` - User confirmation needed

### System Events
- `system.status` - System status update
- `system.error` - System error occurred
- `system.warning` - System warning

## 🔌 Frontend Integration

### WebSocket Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws?session_id=my_session');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Event:', data.event.type, data.event);
};

// Send workflow execution request
ws.send(JSON.stringify({
    type: 'execute_workflow',
    session_id: 'my_session',
    workflow_id: 'data_pipeline',
    inputs: { file_path: '/data/input.csv' }
}));
```

### REST API Usage

```javascript
// Create session
const session = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: 'frontend_user' })
});

// Execute workflow
const execution = await fetch('/api/executions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        workflow_id: 'data_pipeline',
        inputs: { file_path: '/data/input.csv' }
    })
});

// Monitor with Server-Sent Events
const eventSource = new EventSource('/events?session_id=my_session');
eventSource.onmessage = (event) => {
    console.log('SSE Event:', JSON.parse(event.data));
};
```

### AI Chat Integration

```javascript
// Start chat session
await fetch('/api/chat/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: 'my_session' })
});

// Send message
const response = await fetch('/api/chat/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        session_id: 'my_session',
        message: 'Create a workflow that processes customer data',
        context: { available_files: ['/data/customers.csv'] }
    })
});

const chatData = await response.json();
if (chatData.workflow_config) {
    // AI generated a workflow configuration
    console.log('Generated workflow:', chatData.workflow_config);
}
```

## 🧠 AI Chat Features

The AI chat middleware provides:

- **Natural Language Workflow Generation**: Describe what you want in plain English
- **Node Recommendations**: Get suggestions for specific tasks
- **Concept Explanations**: Learn about Kailash concepts
- **Debugging Assistance**: Get help troubleshooting issues

### Example Interactions

```
User: "Create a workflow that reads a CSV file and counts the rows"
AI: I've created a workflow for you. It uses a CSVReaderNode to read the file
    and a PythonCodeNode to count the rows and return the total.

User: "What nodes should I use for processing images?"
AI: For image processing, I recommend:
    1. DirectoryReaderNode - To read image files from a folder
    2. PythonCodeNode - For custom image processing with PIL/OpenCV
    3. HTTPRequestNode - To call external image processing APIs
```

## 📊 Dynamic Schema Generation

The middleware automatically generates UI schemas for all nodes:

```python
# Get schema for a node type
schema = gateway.schema_registry.get_node_schema(CSVReaderNode)

# Schema includes:
{
    "node_type": "CSVReaderNode",
    "category": "data",
    "description": "Reads data from CSV files",
    "parameters": [
        {
            "name": "file_path",
            "type": "string",
            "widget": "file_upload",
            "required": true,
            "description": "Path to the CSV file"
        }
    ],
    "ui_config": {
        "icon": "📊",
        "color": "#3498db"
    }
}
```

This enables frontends to dynamically generate forms and UI components.

## 🔧 Extending the Middleware

### Custom Event Types

```python
from kailash.middleware.events import BaseEvent, EventType

class CustomEvent(BaseEvent):
    custom_field: str

# Emit custom events
await event_stream.emit(CustomEvent(
    type=EventType.SYSTEM_STATUS,
    custom_field="custom_value"
))
```

### Custom Node Integration

```python
from kailash.nodes.mixins import EventEmitterMixin

class MyCustomNode(Node, EventEmitterMixin):
    async def process(self, inputs):
        await self.emit_node_started(inputs)

        # ... processing logic ...

        await self.emit_node_progress(50.0, "Halfway done")

        # ... more processing ...

        await self.emit_node_completed(outputs)
        return outputs
```

### Webhook Integration

```python
# Register webhook for external notifications
gateway.realtime.register_webhook(
    webhook_id="slack_notifications",
    url="https://hooks.slack.com/services/...",
    event_types=["workflow.completed", "workflow.failed"],
    headers={"Authorization": "Bearer token"}
)
```

## 📈 Performance & Scaling

### Latency Optimization
- **Target**: Sub-200ms event processing
- **Event Batching**: Automatic batching for efficiency
- **Connection Pooling**: Efficient WebSocket management
- **Caching**: Schema and metadata caching

### Monitoring
```python
# Get comprehensive statistics
stats = gateway.get_stats()
print(f"Active sessions: {stats['agent_ui']['active_sessions']}")
print(f"Events/second: {stats['realtime']['events_processed']}")
print(f"Avg latency: {stats['realtime']['latency_stats']['avg_ms']}ms")
```

### Configuration
```python
gateway = create_gateway(
    max_sessions=1000,              # Session limit
    cors_origins=["*"],             # CORS configuration
    latency_target_ms=200,          # Performance target
    enable_batching=True,           # Event batching
    session_timeout_minutes=60      # Session timeout
)
```

## 🔒 Security Considerations

- **Authentication**: Integrate with existing auth systems
- **CORS**: Configure allowed origins
- **Rate Limiting**: Built-in connection limits
- **Input Validation**: Automatic parameter validation
- **Session Isolation**: User data separation

## 🧪 Testing

```python
import pytest
from kailash.middleware import create_gateway

@pytest.mark.asyncio
async def test_middleware():
    gateway = create_gateway()

    # Test session creation
    session_id = await gateway.agent_ui.create_session()
    assert session_id is not None

    # Test workflow execution
    execution_id = await gateway.agent_ui.execute_workflow(
        session_id, "test_workflow", {}
    )
    assert execution_id is not None
```

## 📚 Examples

- **Basic Server**: [middleware_comprehensive_example.py](../../../examples/feature_examples/middleware/middleware_comprehensive_example.py)
- **Frontend Integration**: See JavaScript examples in the file above
- **Custom Nodes**: Check node examples with event emission
- **AI Chat**: Complete chat integration examples

## 🗺️ Roadmap

- **Enhanced AI**: More sophisticated workflow generation
- **Visual Editor**: Drag-and-drop workflow builder support
- **Collaboration**: Multi-user workflow editing
- **Templates**: Pre-built workflow templates
- **Analytics**: Advanced usage analytics and insights

---

The Kailash Middleware layer provides a complete foundation for building sophisticated agent-frontend applications with real-time capabilities and AI-powered assistance. It's designed to scale from simple prototypes to enterprise-grade applications.
