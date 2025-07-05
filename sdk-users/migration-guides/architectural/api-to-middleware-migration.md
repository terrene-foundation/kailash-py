# Migration Guide: API/MCP → Middleware

*Upgrading from legacy kailash.api and kailash.mcp to unified middleware*

## Overview

The Kailash SDK has consolidated the separate `kailash.api` and `kailash.mcp` modules into a unified `kailash.middleware` layer. This provides better integration, enterprise features, and a more coherent architecture.

## Quick Migration

### Import Changes

```python
# ❌ OLD - Deprecated
from kailash.api.gateway import WorkflowAPIGateway
from kailash.api.mcp_integration import MCPIntegration
from kailash.mcp.server import MCPServer

# ✅ NEW - Current
from kailash.middleware import create_gateway, MiddlewareMCPServer
from kailash.middleware import AgentUIMiddleware, RealtimeMiddleware

```

### Gateway Creation

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ❌ OLD - Deprecated
gateway = WorkflowAPIGateway(
    title="My App",
    description="Description",
    max_workers=10
)
gateway.register_workflow("process", workflow)

# ✅ NEW - Current
gateway = create_gateway(
    title="My App",
    description="Description",
    max_sessions=100
)
# Workflows created dynamically via API

```

### MCP Integration

```python
# ❌ OLD - Deprecated
from kailash.mcp.server import MCPServer

mcp = MCPServer(name="tools")
@mcp.tool
def my_tool():
    return "result"

# ✅ NEW - Current
from kailash.middleware import MiddlewareMCPServer

mcp = MiddlewareMCPServer(name="tools", agent_ui=gateway.agent_ui)
@mcp.tool
def my_tool():
    return "result"

```

## Detailed Migration Steps

### 1. Update Imports

Replace all `kailash.api` and `kailash.mcp` imports:

| Old Import | New Import |
|------------|------------|
| `from kailash.api.gateway import WorkflowAPIGateway` | `from kailash.middleware import create_gateway` |
| `from kailash.api.mcp_integration import MCPIntegration` | `from kailash.middleware import MiddlewareMCPServer` |
| `from kailash.mcp.server import MCPServer` | `from kailash.middleware.mcp import MiddlewareMCPServer` |
| `from kailash.api.auth import JWTAuthManager` | `from kailash.middleware.auth import JWTAuthManager` |

### 2. Gateway Architecture Changes

#### Before (Legacy API)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Static workflow registration
gateway = WorkflowAPIGateway(title="App")
gateway.register_workflow("process", data_workflow)
gateway.register_workflow("analyze", analysis_workflow)

# Start server
gateway.run(port=8000)

```

#### After (Middleware)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Dynamic workflow creation via API
gateway = create_gateway(title="App")

# Workflows created dynamically:
# POST /api/workflows with JSON configuration
# Real-time execution monitoring
# Session-based isolation

gateway.run(port=8000)

```

### 3. Workflow Definition Changes

#### Before (Pre-registered Workflows)
```python
# Workflows defined at startup
def create_data_workflow():
    workflow = Workflow("example", name="Example")
workflow.    # ... add nodes and connections
    return workflow

gateway.register_workflow("data_processing", create_data_workflow())

```

#### After (Dynamic Creation)
```python
# Frontend sends workflow configuration
workflow_config = {
    "nodes": [
        {
            "id": "reader",
            "type": "CSVReaderNode",
            "config": {"name": "reader", "file_path": "/data/input.csv"}
        }
    ],
    "connections": []
}

# Created via API call:
# POST /api/workflows
# { "workflow_config": workflow_config }

```

### 4. MCP Server Changes

#### Before (Standalone MCP)
```python
from kailash.mcp.server import MCPServer

mcp = MCPServer(name="tools")

@mcp.tool
def analyze_data('data') -> str:
    return f"Analysis: {data}"

# Separate from API gateway
mcp.run(port=9000)

```

#### After (Integrated MCP)
```python
from kailash.middleware import create_gateway

gateway = create_gateway(title="App")

# MCP integrated with middleware
mcp = gateway.mcp_server  # Built-in MCP server

@mcp.tool
def analyze_data('data') -> str:
    return f"Analysis: {data}"

# Single server for API + MCP + Real-time
gateway.run(port=8000)

```

### 5. Authentication Changes

#### Before (Basic JWT)
```python
from kailash.api.auth import JWTAuthManager

auth = JWTAuthManager(secret_key="secret")
gateway = WorkflowAPIGateway(auth_manager=auth)

```

#### After (Enterprise Auth)
```python
from kailash.middleware.auth import JWTAuthManager

auth = JWTAuthManager(secret_key="secret")
gateway = create_gateway(auth_manager=auth, enable_auth=True)

```

## New Features Available

### 1. Session-Based Workflows
```python
# Each user gets isolated session
POST /api/sessions
{
    "user_id": "user123",
    "metadata": {"role": "analyst"}
}

# Workflows scoped to session
POST /api/workflows
{
    "session_id": "session-uuid",
    "workflow_config": {...}
}

```

### 2. Real-Time Communication
```javascript
// WebSocket for live updates
const ws = new WebSocket('ws://localhost:8000/ws?session_id=session-uuid');
ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log('Workflow progress:', update.progress);
};

// Server-Sent Events
const events = new EventSource('http://localhost:8000/events?session_id=session-uuid');
events.onmessage = (event) => {
    console.log('Real-time update:', event.data);
};
```

### 3. AI Chat Integration
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# AI-powered workflow creation
POST /api/chat/message
{
    "session_id": "session-uuid",
    "message": "Create a workflow to process customer data",
    "context": {"available_data": ["/data/customers.csv"]}
}

# AI generates workflow configuration automatically

```

### 4. Dynamic Schema Generation
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Get available node types with schemas
GET /api/nodes

# Frontend can build forms dynamically
{
    "nodes": [
        {
            "type": "CSVReaderNode",
            "schema": {
                "parameters": {
                    "file_path": {"type": "string", "required": true},
                    "delimiter": {"type": "string", "default": ","}
                }
            }
        }
    ]
}

```

## Breaking Changes

### 1. Workflow Registration API
- **Before**: `gateway.register_workflow(id, workflow)`
- **After**: Dynamic creation via REST API

### 2. Execution Model
- **Before**: Direct workflow execution
- **After**: Session-based execution with monitoring

### 3. MCP Integration
- **Before**: Separate MCP server
- **After**: Integrated with middleware

### 4. Event System
- **Before**: Basic callbacks
- **After**: Enterprise event streaming

## Migration Checklist

### ✅ **Phase 1: Update Imports**
- [ ] Replace `from kailash.api` with `from kailash.middleware`
- [ ] Replace `from kailash.mcp` with `from kailash.middleware.mcp`
- [ ] Update authentication imports

### ✅ **Phase 2: Update Gateway Creation**
- [ ] Replace `WorkflowAPIGateway` with `create_gateway`
- [ ] Remove static workflow registration
- [ ] Add session and real-time configuration

### ✅ **Phase 3: Update Workflow Patterns**
- [ ] Convert to JSON-based workflow definitions
- [ ] Implement dynamic workflow creation
- [ ] Add session management

### ✅ **Phase 4: Update MCP Integration**
- [ ] Integrate MCP with middleware
- [ ] Use unified server for API + MCP + Real-time
- [ ] Update tool definitions

### ✅ **Phase 5: Add New Features**
- [ ] Implement real-time communication
- [ ] Add AI chat integration
- [ ] Use dynamic schema generation
- [ ] Add session-based security

## Examples

### Complete Migration Example

#### Before (Legacy)
```python
from kailash.api.gateway import WorkflowAPIGateway
from kailash.mcp.server import MCPServer
from kailash.workflow import Workflow

# Create workflows
data_workflow = Workflow("example", name="Example")
workflow.# ... build workflow

# Create gateway
gateway = WorkflowAPIGateway(title="My Platform")
gateway.register_workflow("process", data_workflow)

# Create MCP server
mcp = MCPServer(name="tools")
@mcp.tool
def analyze():
    return "analysis"

# Run separately
gateway.run(port=8000)
mcp.run(port=9000)

```

#### After (Middleware)
```python
from kailash.middleware import create_gateway

# Create unified gateway
gateway = create_gateway(
    title="My Platform",
    cors_origins=["http://localhost:3000"],
    enable_docs=True
)

# MCP integration built-in
mcp = gateway.mcp_server
@mcp.tool
def analyze():
    return "analysis"

# Workflows created dynamically via API
# Real-time updates via WebSocket/SSE
# Session-based execution

# Single server for everything
gateway.run(port=8000)

```

### Frontend Integration

#### JavaScript Example
```javascript
// Create session
const session = await fetch('http://localhost:8000/api/sessions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_id: 'user123'})
});

// Create workflow dynamically
const workflow = await fetch('http://localhost:8000/api/workflows', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        session_id: session.session_id,
        workflow_config: {
            nodes: [{
                id: 'process',
                type: 'PythonCodeNode',
                config: {name: 'process', code: 'result = {"status": "processed"}'}
            }],
            connections: []
        }
    })
});

// Execute with real-time monitoring
const execution = await fetch('http://localhost:8000/api/executions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        session_id: session.session_id,
        workflow_id: workflow.workflow_id
    })
});

// Monitor via WebSocket
const ws = new WebSocket(`ws://localhost:8000/ws?session_id=${session.session_id}`);
ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    if (update.type === 'workflow.completed') {
        console.log('Results:', update.outputs);
    }
};
```

## Getting Help

### Documentation
- **[Middleware Guide](README.md)** - Complete middleware documentation
- **[Agent-UI Communication](agent-ui-communication.md)** - Session and workflow management
- **[Real-time Communication](real-time-communication.md)** - Event streaming patterns
- **[API Gateway Guide](api-gateway-guide.md)** - REST API reference

### Examples
- **[Comprehensive Demo](../../examples/feature_examples/middleware/middleware_comprehensive_example.py)** - Complete setup
- **[Migration Examples](../../examples/feature_examples/middleware/migration/)** - Before/after comparisons

### Support
- **[Troubleshooting Guide](../developer/07-troubleshooting.md)** - Common issues and solutions
- **GitHub Issues** - Report migration problems or questions

## Timeline

### Deprecation Schedule
- **Current**: Both old and new APIs supported
- **v0.4.0**: Deprecation warnings for old API
- **v0.5.0**: Old API marked as legacy
- **v1.0.0**: Old API removed

### Migration Recommendations
- **Immediate**: Start new projects with middleware
- **Q1 2025**: Migrate existing critical applications
- **Q2 2025**: Complete migration before v1.0.0 release
