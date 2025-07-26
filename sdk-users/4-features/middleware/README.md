# Kailash Middleware Guide

*Enterprise-grade middleware for real-time agent-UI communication*

## Overview

The Kailash Middleware layer provides a comprehensive communication framework between AI agents and frontend applications. Built on the XAI-UI architecture, it enables real-time workflows, dynamic UI generation, and seamless frontend integration.

## Quick Navigation

| Component | Purpose | When to Use |
|-----------|---------|-------------|
| **[AgentUIMiddleware](agent-ui-communication.md)** | Session-based workflow management | Building interactive applications |
| **[RealtimeMiddleware](real-time-communication.md)** | Event streaming and updates | Real-time dashboards and monitoring |
| **[APIGateway](api-gateway-guide.md)** | Unified REST API with docs | Web applications and services |
| **[AIChatMiddleware](ai-chat-integration.md)** | AI-powered workflow creation | Chat interfaces and assistants |
| **[Authentication](authentication-security.md)** | JWT auth and access control | Secure enterprise applications |

## Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Middleware     │    │   Kailash Core  │
│                 │    │                  │    │                 │
│  • React/Vue    │────│  • Agent-UI      │────│  • Workflows    │
│  • JavaScript   │    │  • Real-time     │    │  • Nodes        │
│  • Mobile Apps  │    │  • API Gateway   │    │  • Runtime      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Quick Start

### 1. Basic Middleware Setup

```python
from kailash.api.middleware import create_gateway

# Create gateway with all middleware components
gateway = create_gateway(
    title="My Application",
    cors_origins=["http://localhost:3000"],
    enable_docs=True
)

# Start the server
gateway.run(port=8000)

```

### 2. Frontend Integration

```javascript
// Create session
const session = await fetch('http://localhost:8000/api/sessions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_id: 'frontend_user'})
});

// Execute workflow
const execution = await fetch('http://localhost:8000/api/executions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        session_id: session.session_id,
        workflow_id: 'data_processing',
        inputs: {file_path: '/data/input.csv'}
    })
});

// Monitor via WebSocket
const ws = new WebSocket(`ws://localhost:8000/ws?session_id=${session.session_id}`);
ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log('Workflow update:', update);
};
```

### 3. Dynamic Workflow Creation

```python
from kailash.api.middleware import AgentUIMiddleware

async def create_dynamic_workflow():
    agent_ui = AgentUIMiddleware()
    session_id = await agent_ui.create_session(user_id="user123")

    # Workflow from frontend JSON
    workflow_config = {
        "nodes": [
            {
                "id": "input",
                "type": "CSVReaderNode",
                "config": {"name": "input", "file_path": "/data/customers.csv"}
            },
            {
                "id": "process",
                "type": "PythonCodeNode",
                "config": {"name": "process", "code": "result = {'count': len(input_data)}"}
            }
        ],
        "connections": [
            {"from_node": "input", "from_output": "output",
             "to_node": "process", "to_input": "input_data"}
        ]
    }

    # Create and execute
    workflow_id = await agent_ui.create_dynamic_workflow(
        session_id=session_id,
        workflow_config=workflow_config
    )

    execution_id = await agent_ui.execute_workflow(
        session_id=session_id,
        workflow_id=workflow_id
    )

```

## Key Features

### ✅ **Event-Driven Architecture**
- Real-time WebSocket, SSE, and webhook support
- Event streaming with automatic batching
- Session-based state management

### ✅ **Dynamic Workflow Creation**
- JSON-based workflow definitions
- Frontend-driven workflow building
- AI-assisted workflow generation

### ✅ **Enterprise Security**
- JWT authentication with 100% Kailash components
- RBAC/ABAC access control integration
- Session isolation and cleanup

### ✅ **Performance Optimized**
- Sub-200ms latency for real-time updates
- Event batching and compression
- Connection pooling and reuse

### ✅ **Frontend Ready**
- React hooks and patterns
- Dynamic schema generation for forms
- Real-time progress updates

## Migration from Legacy API/MCP

### Old Pattern (Deprecated)
```python
# ❌ OLD - Don't use
from kailash.api.gateway import WorkflowAPIGateway
from kailash.mcp.server import MCPServer

gateway = WorkflowAPIGateway(title="App")
mcp = MCPServer(name="tools")

```

### New Pattern (Current)
```python
# ✅ NEW - Use this
from kailash.api.middleware import create_gateway, MiddlewareMCPServer

gateway = create_gateway(title="App")
mcp = MiddlewareMCPServer(name="tools", agent_ui=gateway.agent_ui)

```

## Component Guides

### Core Middleware
- **[Agent-UI Communication](agent-ui-communication.md)** - Session management and workflow execution
- **[Real-time Communication](real-time-communication.md)** - Event streaming and WebSocket patterns
- **[API Gateway](api-gateway-guide.md)** - REST API with automatic documentation

### Integration
- **[AI Chat Integration](ai-chat-integration.md)** - AI-powered workflow creation
- **[Authentication & Security](authentication-security.md)** - JWT auth and access control
- **[Database Integration](database-integration.md)** - Persistence and state management

### Advanced
- **[Performance Optimization](performance-optimization.md)** - Scaling and optimization
- **[Custom Middleware](custom-middleware.md)** - Extending the middleware layer
- **[Deployment Patterns](deployment-patterns.md)** - Production deployment

## Examples

### Working Examples
- **[Comprehensive Demo](../../examples/feature_examples/middleware/middleware_comprehensive_example.py)** - Complete middleware setup
- **[Chat Interface](../../examples/feature_examples/middleware/ai_chat_example.py)** - AI chat integration
- **[Real-time Dashboard](../../examples/feature_examples/middleware/realtime_dashboard.py)** - Live monitoring

### Frontend Examples
- **JavaScript Integration** - Vanilla JS patterns
- **React Integration** - React hooks and components
- **Vue.js Integration** - Vue composition patterns

## Troubleshooting

### Common Issues
1. **Connection timeouts** - Check CORS origins and network configuration
2. **Session not found** - Verify session creation and cleanup timing
3. **Import errors** - Use `from kailash.api.middleware import ...` patterns
4. **WebSocket disconnections** - Implement reconnection logic

### Debug Mode
```python
import logging
logging.getLogger("kailash.middleware").setLevel(logging.DEBUG)

# Enable debug output for troubleshooting
gateway = create_gateway(debug=True)

```

## Next Steps

1. **Choose your component** - Pick the middleware component for your use case
2. **Follow the guide** - Use the specific component documentation
3. **Run examples** - Test with working examples in the repository
4. **Build integration** - Create your frontend integration patterns
5. **Deploy** - Use deployment guides for production setup

---

**Need help?** Check the [troubleshooting guide](../developer/07-troubleshooting.md) or see [working examples](../../examples/feature_examples/middleware/).
