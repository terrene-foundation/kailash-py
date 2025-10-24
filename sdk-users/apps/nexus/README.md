# Kailash Nexus - Zero Configuration Workflow Orchestration

A truly zero-configuration platform that allows enterprise users to focus on creating workflows without learning infrastructure complexity.

**Current Version: v1.1.0** (2025-10-24)

## What is Nexus?

Nexus embodies the zero-config philosophy: **just create `Nexus()` and start!**

- **Zero Parameters**: No configuration files, environment variables, or setup required
- **Progressive Enhancement**: Start simple, add features as needed
- **Multi-Channel**: API, CLI, and MCP access unified
- **Simple Registration**: Use `app.register(name, workflow)` to add workflows
- **Enterprise Ready**: Built-in auth, monitoring, and rate limiting

## What's New in v1.1.0

**CRITICAL Fixes:**
- ✅ Fixed all 10 stub implementations with production-ready solutions
- ✅ Channel initialization now handled directly by Nexus (no ChannelManager stubs)
- ✅ Workflow registration through single path: `Nexus.register()`
- ✅ Event broadcasting updated with honest v1.0 behavior (logging, not real-time)
- ✅ Plugin validation improvements (checks `name` and `apply` method)
- ✅ 248/248 unit tests passing

**No Breaking Changes** - All improvements are internal

## Quick Start

```python
from nexus import Nexus

# That's it! Zero configuration needed.
app = Nexus()
app.start()
```

## Core Features

### 1. Zero Configuration Initialization
```python
from nexus import Nexus

# Create and start with zero parameters
app = Nexus()

# Optional: Configure enterprise features
app = Nexus(
    api_port=8000,      # Default: 8000
    mcp_port=3001,      # Default: 3001
    enable_auth=False,  # Default: False
    enable_monitoring=False,  # Default: False
    rate_limit=None,    # Default: None
    auto_discovery=True # Default: True
)

app.start()

# Check health
print(app.health_check())
```

### 2. Automatic Workflow Discovery
Place workflows in your directory using these patterns:
- `workflows/*.py`
- `*.workflow.py`
- `workflow_*.py`
- `*_workflow.py`

Example workflow file (`my_workflow.py`):
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {"model": "gpt-4"})
```

Nexus automatically discovers and registers it!

### 3. Workflow Registration
Register workflows with the simple `register()` method:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Create a workflow
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "process", {"code": "result = len(data)"})
workflow.add_connection("reader", "data", "process", "data")

# Register the workflow
app.register("data_processor", workflow.build())

app.start()
```

### 4. Multi-Channel Access
Your workflows are automatically available via:

- **REST API**: `http://localhost:8000/workflows/{name}`
- **CLI**: `nexus run {name}`
- **MCP**: Model Context Protocol integration

### 5. Custom REST Endpoints
Create FastAPI-style custom endpoints with path parameters, query parameters, and rate limiting:

```python
from nexus import Nexus
from fastapi import Request

app = Nexus()

# Custom endpoint with path parameters
@app.endpoint("/api/conversations/{conversation_id}", methods=["GET"], rate_limit=50)
async def get_conversation(conversation_id: str):
    """Get conversation by ID."""
    result = await app._execute_workflow("chat_workflow", {"id": conversation_id})
    return {"conversation_id": conversation_id, "data": result}

# Query parameters (built-in FastAPI support)
@app.endpoint("/api/search")
async def search(q: str, limit: int = 10, offset: int = 0):
    """Search with pagination."""
    result = await app._execute_workflow("search_workflow", {
        "query": q,
        "limit": limit,
        "offset": offset
    })
    return result

app.start()
```

**Key Features (v1.1.0):**
- ✅ Path Parameters: `/api/users/{user_id}` automatically validated
- ✅ Query Parameters: Type coercion, defaults, `pattern` validation
- ✅ Rate Limiting: Per-endpoint with automatic cleanup (default 100 req/min)
- ✅ Security: Input size (10MB max), dangerous key blocking, key length (256 chars)
- ✅ HTTP Methods: GET, POST, PUT, DELETE, PATCH

**📚 Complete Guide:** [SSE Streaming Guide](docs/technical/sse_streaming.md)

### 6. SSE Streaming for Real-Time Chat
Execute workflows with Server-Sent Events for real-time updates:

```python
# Execute workflow in streaming mode
# POST /execute with {"mode": "stream"}

# Browser JavaScript client
const eventSource = new EventSource('/workflows/chat/execute?mode=stream');

eventSource.addEventListener('complete', (e) => {
    const data = JSON.parse(e.data);
    console.log('Result:', data.result);
});
```

**Event Types:** start, complete, error, keepalive
**Format:** Proper SSE specification with `id:`, `event:`, `data:` fields

### 7. Smart Defaults
- API server on port 8000 (auto-finds available port)
- MCP server on port 3001 (auto-finds available port)
- Health endpoint at `/health`
- Auto CORS and documentation enabled
- Graceful error handling and isolation

## What's New in v1.1.0

- **Enhanced Security**: Input size validation (10MB), dangerous key blocking, key length limits (256 chars)
- **Rate Limiting Improvements**: Automatic cleanup of expired rate limit entries
- **Query Parameter Validation**: Use `pattern` parameter for regex validation
- **MCP Transport Modes**: WebSocket-only and HTTP+WebSocket modes with improved architecture
- **WebSocket API**: Updated to websockets 14.0+ (ServerConnection API)
- **Bug Fixes**: 48 test fixes including MCP protocol, E2E workflows, and production scenarios

## 🏗️ Multi-Channel Architecture

Nexus implements a sophisticated **multi-channel orchestration architecture** that provides unified access to workflows across three distinct interfaces:

### Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                    Nexus Core                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │   API    │  │   CLI    │  │   MCP    │     │
│  │ Channel  │  │ Channel  │  │ Channel  │     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
│       └──────────────┴──────────────┘           │
│         Session Manager & Event Router          │
│  ┌─────────────────────────────────────────────┐ │
│  │        Enterprise Gateway                   │ │
│  │ • Authentication  • Rate Limiting           │ │
│  │ • Authorization   • Circuit Breaker         │ │
│  │ • Monitoring      • Caching                 │ │
│  └─────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────┤
│               Kailash SDK                       │
│         Workflows │ Nodes │ Runtime             │
└─────────────────────────────────────────────────┘
```

### Multi-Channel Orchestration

#### **1. API Channel (REST/WebSocket)**
- **Purpose**: Web applications, mobile apps, external integrations
- **Features**: RESTful endpoints, WebSocket streaming, JSON responses
- **Authentication**: JWT tokens, API keys, OAuth2
- **Use Cases**: Dashboard UIs, mobile apps, third-party integrations

#### **2. CLI Channel (Command Line)**
- **Purpose**: DevOps, automation, local development
- **Features**: Command-line interface, scripting support, terminal output
- **Authentication**: Local credentials, session tokens
- **Use Cases**: CI/CD pipelines, local development, system administration

#### **3. MCP Channel (Model Context Protocol)**
- **Purpose**: AI agent integration, LLM workflows
- **Features**: Tool discovery, resource access, AI-native protocols
- **Authentication**: Agent credentials, capability-based security
- **Use Cases**: AI assistants, automated workflows, intelligent agents

### Parameter Passing from API Calls to Workflows

#### **Parameter Flow Architecture**

```python
# API Request → Workflow Parameters
POST /api/workflows/data_processor/execute
{
    "input_data": [1, 2, 3],
    "threshold": 0.5,
    "user_id": "user123"
}

# Becomes workflow parameters:
workflow_params = {
    "input_data": [1, 2, 3],
    "threshold": 0.5,
    "user_id": "user123"
}
```

#### **Cross-Channel Parameter Consistency**

1. **API Channel**: JSON body parameters
2. **CLI Channel**: Command-line arguments (converted to JSON)
3. **MCP Channel**: Tool parameters (native protocol)

All channels produce the same internal parameter structure for workflows.

### Enterprise Features

#### **Zero-Config vs Enterprise Configuration**

**Zero-Config (Development)**:
```python
nexus = Nexus()  # Everything configured automatically
```

**Enterprise (Production)**:
```python
nexus = Nexus(
    # Multi-channel ports
    api_port=8000,
    cli_port=8001,
    mcp_port=3001,

    # Security
    enable_auth=True,
    auth_providers=["oauth2", "saml"],
    enable_rate_limiting=True,

    # Performance
    enable_caching=True,
    cache_backend="redis",
    enable_monitoring=True,

    # Reliability
    enable_circuit_breaker=True,
    max_concurrent_workflows=100
)
```

### Troubleshooting Guide

#### **Common Errors and Solutions**

1. **Port Conflicts**:
   ```bash
   # Error: Address already in use
   nexus = Nexus(api_port=8001, mcp_port=3002)
   ```

2. **Workflow Not Found**:
   ```python
   # Error: Workflow 'my_workflow' not registered
   # Solution: Ensure workflow is built and registered
   workflow = WorkflowBuilder()
   # ... configure workflow ...
   nexus.register("my_workflow", workflow.build())  # Must call .build()
   ```

3. **Authentication Issues**:
   ```python
   # Error: Unauthorized
   # Solution: Configure authentication
   nexus = Nexus(enable_auth=True)
   nexus.auth.configure(provider="oauth2", client_id="...", client_secret="...")
   ```

4. **Parameter Validation Errors**:
   ```python
   # Error: Invalid parameter type
   # Solution: Check parameter types match node requirements
   # Use proper JSON types in API calls
   ```

### Working Examples for Each Channel

#### **API Channel Example**:
```bash
# Start Nexus
python -c "
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

nexus = Nexus()
workflow = WorkflowBuilder()
workflow.add_node('PythonCodeNode', 'process', {'code': 'result = sum(data)'})
nexus.register('calculator', workflow.build())
nexus.start()
"

# Use via HTTP
curl -X POST http://localhost:8000/api/workflows/calculator/execute \
  -H "Content-Type: application/json" \
  -d '{"data": [1, 2, 3, 4, 5]}'
```

#### **CLI Channel Example**:
```bash
# Same setup as above, then:
nexus execute calculator --data "[1,2,3,4,5]"
```

#### **MCP Channel Example**:
```python
# MCP client integration
import mcp_client

client = mcp_client.connect("http://localhost:3001")
result = client.call_tool("calculator", {"data": [1, 2, 3, 4, 5]})
```

### Testing Strategies for Each Channel

#### **API Channel Testing**:
```python
import requests

def test_api_channel():
    response = requests.post(
        "http://localhost:8000/api/workflows/test_workflow/execute",
        json={"param1": "value1"}
    )
    assert response.status_code == 200
```

#### **CLI Channel Testing**:
```bash
# Test CLI integration
nexus execute test_workflow --param1 "value1"
echo $?  # Should be 0 for success
```

#### **MCP Channel Testing**:
```python
def test_mcp_channel():
    client = mcp_client.connect("http://localhost:3001")
    result = client.call_tool("test_workflow", {"param1": "value1"})
    assert result is not None
```

## Implementation Architecture

Nexus is built as a separate application using Kailash SDK components:

```
┌─ kailash_nexus_app/
├── core.py          # Zero-config wrapper around SDK
├── discovery.py     # Auto-discovery of workflows
├── plugins.py       # Progressive enhancement system
├── channels.py      # Multi-channel configuration
└── __init__.py      # Simple `create_nexus()` function
```

### Key Principles

1. **SDK as Building Blocks**: Uses existing Kailash SDK without modification
2. **Zero Config by Default**: No parameters required for basic usage
3. **Progressive Enhancement**: Add complexity only when needed
4. **Smart Defaults**: Everything just works out of the box

## Plugin System

Built-in plugins include:

- **Auth Plugin**: Authentication and authorization
- **Monitoring Plugin**: Performance metrics and health checks
- **Rate Limit Plugin**: Request rate limiting

Create custom plugins:
```python
from kailash_nexus_app.plugins import NexusPlugin

class MyPlugin(NexusPlugin):
    @property
    def name(self):
        return "my_plugin"

    @property
    def description(self):
        return "My custom plugin"

    def apply(self, nexus_instance):
        # Enhance nexus functionality
        nexus_instance.my_feature = True
```

## Testing

Comprehensive test suite with 52 tests:

```bash
# Run all tests
python -m pytest tests/ -v

# Unit tests only (45 tests)
python -m pytest tests/unit/ -v

# Integration tests only (7 tests)
python -m pytest tests/integration/ -v
```

## Use Cases

### Data Scientists
```python
# Just start and focus on workflows
from nexus import create_nexus
create_nexus().start()
```

### DevOps Engineers
```python
# Add production features progressively
from nexus import create_nexus

create_nexus().enable_auth().enable_monitoring().start()
```

### AI Developers
```python
# Register AI workflows automatically
from nexus import create_nexus
from kailash.workflow.builder import WorkflowBuilder

n = create_nexus()

# Manual registration
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "ai", {"model": "gpt-4"})
n.register("ai-assistant", workflow)

n.start()
```

## Comparison with v1

| Feature | Nexus v1 | Nexus v2 (This Implementation) |
|---------|----------|--------------------------------|
| Configuration | 200+ lines | 0 lines |
| Startup | Complex setup | `create_nexus().start()` |
| Channels | Manual config | Auto-configured |
| Discovery | None | Automatic |
| Enhancement | Built-in complexity | Progressive plugins |

## Implementation Status

✅ **Core Features Implemented**:
- Zero-config initialization
- Workflow discovery and auto-registration
- Plugin system for progressive enhancement
- Channel configuration with smart defaults
- Comprehensive test suite (52 tests passing)

⏳ **Future Enhancements**:
- Real SDK gateway integration
- Production deployment patterns
- Advanced enterprise features

This implementation demonstrates the true zero-config vision: a platform where enterprise users can focus on creating workflows without infrastructure complexity.
