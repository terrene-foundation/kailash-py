# Kailash Middleware API Gateway

The Kailash Middleware API Gateway provides a unified, enterprise-grade entry point for managing workflows, real-time communication, and frontend integration through a comprehensive middleware layer.

## Overview

The middleware gateway architecture provides:

- **Unified Access**: Single server managing all workflows and real-time communication
- **Agent-UI Communication**: Session-based workflow management with real-time updates
- **Dynamic Workflow Creation**: JSON-based workflow building from frontend applications
- **Event Streaming**: WebSocket, SSE, and webhook support for real-time updates
- **AI Integration**: Built-in AI chat for intelligent workflow creation
- **Enterprise Security**: JWT authentication and RBAC/ABAC access control
- **Production Features**: Automatic API documentation, health monitoring, CORS

## Quick Start

### Basic Gateway Setup

```python
from kailash.middleware import create_gateway

# Create comprehensive middleware gateway
gateway = create_gateway(
    title="My Platform",
    description="Enterprise workflow platform with real-time capabilities",
    cors_origins=["http://localhost:3000"],
    enable_docs=True,
    max_sessions=100
)

# Start the server
gateway.run(port=8000)
```

### Manual Component Setup

```python
from kailash.middleware import (
    AgentUIMiddleware, RealtimeMiddleware, APIGateway,
    AIChatMiddleware, KailashJWTAuthManager
)

# Create components
auth_manager = KailashJWTAuthManager()
agent_ui = AgentUIMiddleware(auth_manager=auth_manager)
realtime = RealtimeMiddleware(agent_ui)
ai_chat = AIChatMiddleware(agent_ui)

# Create gateway with components
gateway = APIGateway(
    agent_ui=agent_ui,
    realtime=realtime,
    ai_chat=ai_chat,
    auth_manager=auth_manager,
    title="Custom Platform"
)

# Start server
gateway.run(port=8000)
```

## Core Features

### 1. Session-Based Workflow Management

```python
# Frontend creates session
POST /api/sessions
{
    "user_id": "user123",
    "metadata": {"role": "analyst"}
}

# Response
{
    "session_id": "session-uuid",
    "created_at": "2025-06-13T10:00:00Z"
}
```

### 2. Dynamic Workflow Creation

```python
# Frontend sends workflow configuration
POST /api/workflows
{
    "session_id": "session-uuid",
    "workflow_config": {
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
                "id": "processor",
                "type": "PythonCodeNode",
                "config": {
                    "name": "processor",
                    "code": "result = {'count': len(input_data)}"
                }
            }
        ],
        "connections": [
            {
                "from_node": "reader",
                "from_output": "output",
                "to_node": "processor",
                "to_input": "input_data"
            }
        ]
    }
}

# Response
{
    "workflow_id": "workflow-uuid",
    "status": "created"
}
```

### 3. Workflow Execution

```python
# Execute workflow
POST /api/executions
{
    "session_id": "session-uuid",
    "workflow_id": "workflow-uuid",
    "inputs": {"custom_param": "value"}
}

# Response
{
    "execution_id": "execution-uuid",
    "status": "started"
}

# Monitor execution
GET /api/executions/{execution_id}

# Response
{
    "execution_id": "execution-uuid",
    "status": "completed",
    "progress": 100,
    "outputs": {"count": 1500},
    "created_at": "2025-06-13T10:01:00Z",
    "completed_at": "2025-06-13T10:01:05Z"
}
```

### 4. Real-Time Communication

```javascript
// WebSocket connection
const ws = new WebSocket('ws://localhost:8000/ws?session_id=session-uuid');

ws.onmessage = (event) => {
    const update = JSON.parse(event.data);

    switch(update.type) {
        case 'workflow.started':
            console.log('Workflow started:', update.workflow_id);
            break;
        case 'workflow.progress':
            console.log('Progress:', update.progress + '%');
            break;
        case 'workflow.completed':
            console.log('Completed:', update.outputs);
            break;
    }
};

// Server-Sent Events
const eventSource = new EventSource('http://localhost:8000/events?session_id=session-uuid');
eventSource.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log('SSE Update:', update);
};
```

### 5. AI Chat Integration

```python
# Start AI chat session
POST /api/chat/sessions
{
    "session_id": "session-uuid",
    "user_id": "user123"
}

# Send message to AI
POST /api/chat/message
{
    "session_id": "session-uuid",
    "message": "Create a workflow that processes customer data and generates a report",
    "context": {
        "available_data": ["/data/customers.csv"],
        "output_format": "json"
    }
}

# Response (AI generates workflow)
{
    "message": "I'll create a customer data processing workflow for you.",
    "workflow_config": {
        "nodes": [...],
        "connections": [...]
    },
    "workflow_id": "ai-generated-workflow-uuid"
}
```

## API Endpoints

### Session Management
- `POST /api/sessions` - Create new session
- `GET /api/sessions/{session_id}` - Get session info
- `DELETE /api/sessions/{session_id}` - Close session

### Workflow Management
- `POST /api/workflows` - Create dynamic workflow
- `GET /api/workflows/{workflow_id}` - Get workflow info
- `POST /api/workflows/{workflow_id}/execute` - Execute workflow

### Execution Management
- `POST /api/executions` - Start workflow execution
- `GET /api/executions/{execution_id}` - Get execution status
- `DELETE /api/executions/{execution_id}` - Cancel execution

### Real-Time Communication
- `GET /ws` - WebSocket connection for real-time updates
- `GET /events` - Server-Sent Events stream
- `POST /api/webhooks` - Register webhook endpoints

### AI Chat
- `POST /api/chat/sessions` - Start AI chat session
- `POST /api/chat/message` - Send message to AI
- `GET /api/chat/history/{session_id}` - Get chat history

### Schema and Discovery
- `GET /api/nodes` - Get available node types with schemas
- `GET /api/nodes/{node_type}/schema` - Get specific node schema
- `GET /health` - Health check endpoint

## Authentication

### JWT Authentication

```python
from kailash.middleware.auth import KailashJWTAuthManager

# Setup authentication
auth_manager = KailashJWTAuthManager(
    secret_key="your-secret-key",
    algorithm="HS256",
    expiration_hours=24
)

# Create gateway with auth
gateway = create_gateway(
    title="Secure Platform",
    auth_manager=auth_manager,
    enable_auth=True
)

# Protected endpoints require Authorization header
# Authorization: Bearer <jwt_token>
```

### Authentication Flow

```python
# Login (implement your login logic)
POST /api/auth/login
{
    "username": "user123",
    "password": "password"
}

# Response
{
    "access_token": "jwt-token-here",
    "token_type": "bearer",
    "expires_in": 86400
}

# Use token in requests
Authorization: Bearer jwt-token-here
```

## Configuration

### Environment Variables

```bash
# Server Configuration
KAILASH_HOST=0.0.0.0
KAILASH_PORT=8000
KAILASH_DEBUG=false

# Security
KAILASH_JWT_SECRET=your-secret-key
KAILASH_CORS_ORIGINS=http://localhost:3000,https://myapp.com

# Session Management
KAILASH_MAX_SESSIONS=1000
KAILASH_SESSION_TIMEOUT=3600

# Real-time Features
KAILASH_ENABLE_WEBSOCKET=true
KAILASH_ENABLE_SSE=true
KAILASH_EVENT_BATCH_SIZE=10
```

### Configuration Object

```python
from kailash.middleware import create_gateway
import os

gateway = create_gateway(
    title="Production Platform",
    cors_origins=os.getenv("KAILASH_CORS_ORIGINS", "").split(","),
    enable_docs=os.getenv("KAILASH_DEBUG", "false").lower() == "true",
    max_sessions=int(os.getenv("KAILASH_MAX_SESSIONS", "1000")),
    session_timeout_minutes=int(os.getenv("KAILASH_SESSION_TIMEOUT", "60")),
    enable_auth=True,
    jwt_secret=os.getenv("KAILASH_JWT_SECRET")
)
```

## Production Deployment

### Docker Setup

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

CMD ["python", "-m", "kailash.middleware.server"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kailash-middleware
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kailash-middleware
  template:
    metadata:
      labels:
        app: kailash-middleware
    spec:
      containers:
      - name: middleware
        image: kailash-middleware:latest
        ports:
        - containerPort: 8000
        env:
        - name: KAILASH_JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: kailash-secrets
              key: jwt-secret
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

### Load Balancing

```python
# Multiple gateway instances
gateway1 = create_gateway(port=8001)
gateway2 = create_gateway(port=8002)
gateway3 = create_gateway(port=8003)

# Use nginx or cloud load balancer to distribute traffic
```

## Migration from Legacy API

### Old Pattern (Deprecated)

```python
# ❌ OLD - Don't use
from kailash.api.gateway import WorkflowAPIGateway
from kailash.api.mcp_integration import MCPIntegration

gateway = WorkflowAPIGateway(title="App")
gateway.add_mcp_integration(mcp_server)
gateway.register_workflow("process", workflow)
```

### New Pattern (Current)

```python
# ✅ NEW - Use this
from kailash.middleware import create_gateway

gateway = create_gateway(title="App")
# Workflows created dynamically via API
# MCP integration built-in
```

## Examples

### Complete Integration Example

```python
from kailash.middleware import create_gateway
import asyncio

async def main():
    # Create gateway
    gateway = create_gateway(
        title="Customer Analytics Platform",
        description="Real-time customer data processing and analytics",
        cors_origins=["http://localhost:3000"],
        enable_docs=True
    )

    # Pre-register some common workflows
    agent_ui = gateway.agent_ui

    # Customer analysis template
    from kailash.workflow.builder import WorkflowBuilder

    template = WorkflowBuilder()
    reader_id = template.add_node("CSVReaderNode",
        config={"name": "reader", "file_path": "{{input_file}}"}
    )
    analyzer_id = template.add_node("PythonCodeNode",
        config={
            "name": "analyzer",
            "code": """
result = {
    'total_customers': len(input_data),
    'analysis_date': datetime.now().isoformat(),
    'summary': 'Customer analysis completed'
}
"""
        }
    )
    template.add_connection(reader_id, "output", analyzer_id, "input_data")

    await agent_ui.register_workflow(
        "customer_analysis_template",
        template,
        make_shared=True
    )

    print("🚀 Middleware gateway started!")
    print("📡 API: http://localhost:8000")
    print("📚 Docs: http://localhost:8000/docs")
    print("🔌 WebSocket: ws://localhost:8000/ws")

    # Start server
    gateway.run(port=8000)

if __name__ == "__main__":
    asyncio.run(main())
```

## Troubleshooting

### Common Issues

1. **CORS Errors**: Add your frontend domain to `cors_origins`
2. **Session Timeouts**: Increase `session_timeout_minutes`
3. **WebSocket Disconnections**: Implement reconnection logic in frontend
4. **Memory Usage**: Monitor session count and implement cleanup

### Debug Mode

```python
import logging
logging.getLogger("kailash.middleware").setLevel(logging.DEBUG)

gateway = create_gateway(debug=True)
```

### Health Monitoring

```python
# Check gateway health
GET /health

# Response
{
    "status": "healthy",
    "uptime_seconds": 3600,
    "active_sessions": 25,
    "memory_usage_mb": 512,
    "version": "1.0.0"
}
```

## Related Documentation

- [Agent-UI Communication Guide](../../sdk-users/4-features/middleware/agent-ui-communication.md)
- [Real-time Communication](../../sdk-users/4-features/middleware/real-time-communication.md)
- [Authentication & Security](../../sdk-users/4-features/middleware/authentication-security.md)
- [Middleware Examples](../../examples/feature_examples/middleware/)
