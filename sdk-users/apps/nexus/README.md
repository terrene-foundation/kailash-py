# Kailash Nexus - Zero Configuration Workflow Orchestration

A truly zero-configuration platform that allows enterprise users to focus on creating workflows without learning infrastructure complexity.

**Current Version: v1.3.0**

## What is Nexus?

Nexus embodies the zero-config philosophy: **just create `Nexus()` and start!**

- **Zero Parameters**: No configuration files, environment variables, or setup required
- **Progressive Enhancement**: Start simple, add features as needed
- **Multi-Channel**: API, CLI, and MCP access unified
- **Simple Registration**: Use `app.register(name, workflow)` to add workflows
- **Enterprise Ready**: Built-in auth, monitoring, and rate limiting

## What's New in v1.3.0

**Handler Support (v1.2.0+):**

- `@app.handler()` decorator to register async functions directly as multi-channel workflows
- `register_handler()` method for non-decorator registration
- Bypasses PythonCodeNode sandbox restrictions (no import blocking)
- Automatic parameter derivation from function signatures

**Middleware & Plugin API (v1.3.0):**

- `add_middleware()` - Add ASGI/Starlette middleware to the FastAPI app
- `include_router()` - Mount FastAPI routers for custom endpoints
- `add_plugin()` - Install plugins implementing `NexusPluginProtocol`
- Preset system: `Nexus(preset="saas")` for one-line middleware stacks (none, lightweight, standard, saas, enterprise)
- Native CORS configuration via `cors_origins`, `cors_allow_credentials` (default: `False`)

**Auth Plugin (v1.3.0):**

- `NexusAuthPlugin` with JWT, RBAC, SSO (GitHub/Google/Azure), rate limiting, tenant isolation, audit logging
- Factory methods: `basic_auth()`, `saas_app()`, `enterprise()`
- JWTConfig enforces 32-char minimum for HS\* secrets
- See `.claude/skills/03-nexus/nexus-auth-plugin.md` for details

**Security Defaults (v1.3.0):**

- `cors_allow_credentials=False` by default (safe with wildcard origins)
- RBAC errors return generic "Forbidden" (no role/permission leakage)
- SSO errors sanitized (status-only to client, details logged server-side)
- 1,515 tests passing, 0 failures

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
    auto_discovery=False # Default: False (prevents blocking with DataFlow)
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

**Key Features:**

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

## Version History

- **v1.3.0**: Middleware API, plugin system, presets, NexusAuthPlugin, CORS config
- **v1.2.0**: `@app.handler()` decorator, `register_handler()`, sandbox validation, EATP trust middleware
- **v1.1.0**: Enhanced security, rate limiting improvements, MCP transport modes, WebSocket API updates

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
   # Solution: Use NexusAuthPlugin for authentication (v1.3.0+)
   import os
   from nexus.auth.plugin import NexusAuthPlugin
   from nexus.auth import JWTConfig
   auth = NexusAuthPlugin.basic_auth(jwt=JWTConfig(secret=os.environ["JWT_SECRET"]))
   nexus = Nexus()
   nexus.add_plugin(auth)
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

Nexus is built as a separate package (`kailash-nexus`) using Kailash SDK components:

```
nexus/
├── __init__.py        # Package exports: Nexus, NexusPluginProtocol, presets
├── core.py            # Nexus class, NexusPluginProtocol, middleware/router/plugin API
├── presets.py         # Preset system (none, lightweight, standard, saas, enterprise)
├── discovery.py       # Auto-discovery of workflow files
├── plugins.py         # Legacy plugin base class
├── channels.py        # Multi-channel configuration
├── validation.py      # Workflow sandbox validation at registration time
├── resources.py       # Resource management
├── mcp_websocket_server.py  # WebSocket MCP transport
├── cli/               # CLI channel (command-line interface)
├── mcp/               # MCP channel (Model Context Protocol server)
├── trust/             # EATP trust middleware for agent verification
└── auth/              # Authentication & authorization package
    ├── plugin.py      # NexusAuthPlugin with factory methods
    ├── jwt.py         # JWT middleware (HS256/RS256/JWKS)
    ├── rbac.py        # Role-based access control
    ├── dependencies.py # FastAPI dependencies (RequireRole, RequirePermission)
    ├── models.py      # Auth data models
    ├── sso/           # SSO providers (GitHub, Google, Azure, Apple)
    ├── rate_limit/    # Rate limiting (memory + Redis backends)
    ├── tenant/        # Tenant isolation middleware
    └── audit/         # Audit logging (logging, DataFlow, custom backends)
```

### Key Principles

1. **SDK as Building Blocks**: Uses existing Kailash SDK without modification
2. **Zero Config by Default**: No parameters required for basic usage
3. **Progressive Enhancement**: Add complexity only when needed
4. **Smart Defaults**: Everything just works out of the box

## Plugin System

Nexus uses the `NexusPluginProtocol` -- a runtime-checkable Protocol requiring a `name` property and an `install(app)` method.

**Built-in plugins:**

- **NexusAuthPlugin**: JWT, RBAC, SSO, rate limiting, tenant isolation, audit logging (with factory methods: `basic_auth()`, `saas_app()`, `enterprise()`)

**Create custom plugins:**

```python
from nexus import Nexus, NexusPluginProtocol


class MyPlugin:
    """Custom plugin implementing NexusPluginProtocol."""

    @property
    def name(self) -> str:
        return "my_plugin"

    def install(self, app: Nexus) -> None:
        """Called during app.add_plugin(). Configure middleware, routers, etc."""
        # Example: add a custom FastAPI router
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/my-feature")
        async def my_feature():
            return {"enabled": True}

        app.include_router(router, prefix="/api", tags=["my_plugin"])


app = Nexus()
app.add_plugin(MyPlugin())
app.start()
```

## Testing

Comprehensive test suite with 1,515+ tests across three tiers:

```bash
# Run all tests
python -m pytest tests/ -v

# Unit tests (core, auth, handlers, middleware, presets, CORS, plugins, routers)
python -m pytest tests/unit/ -v

# Integration tests (auth flows, middleware stacks, CORS, handler execution)
python -m pytest tests/integration/ -v

# End-to-end tests (full API lifecycle, auth E2E, handler E2E, middleware E2E)
python -m pytest tests/e2e/ -v
```

## Use Cases

### Data Scientists

```python
# Just start and focus on workflows
from nexus import Nexus

app = Nexus()
app.start()
```

### DevOps Engineers

```python
# Add production features progressively
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, AuditConfig

auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    audit=AuditConfig(backend="logging"),
)

app = Nexus(enable_monitoring=True)
app.add_plugin(auth)
app.start()
```

### AI Developers

```python
# Register AI workflows with handler pattern
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Handler pattern (recommended for simple workflows)
@app.handler("summarize", description="Summarize text with AI")
async def summarize(text: str, max_length: int = 200) -> dict:
    # Use any library -- no sandbox restrictions
    return {"summary": text[:max_length]}

# Traditional workflow registration
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "ai", {"model": "gpt-4"})
app.register("ai-assistant", workflow.build())  # Always call .build()

app.start()
```

## Feature Summary

| Feature                     | Status                                                  |
| --------------------------- | ------------------------------------------------------- |
| Zero-config startup         | `Nexus()` with smart defaults                           |
| Workflow registration       | `app.register(name, workflow.build())`                  |
| Handler registration        | `@app.handler()` decorator + `register_handler()`       |
| Multi-channel (API/CLI/MCP) | Automatic from single registration                      |
| Preset system               | none, lightweight, standard, saas, enterprise           |
| Plugin API                  | `NexusPluginProtocol` with `add_plugin()`               |
| Middleware API              | `add_middleware()`, `include_router()`                  |
| CORS configuration          | Constructor params or `configure_cors()`                |
| JWT authentication          | HS256, RS256, JWKS (Auth0/Okta)                         |
| RBAC                        | Wildcard permissions, `RequireRole`/`RequirePermission` |
| SSO                         | GitHub, Google, Azure AD, Apple                         |
| Rate limiting               | Memory + Redis backends, per-route config               |
| Tenant isolation            | Header/JWT claim resolution, admin override             |
| Audit logging               | Logging, DataFlow, custom backends                      |
| Custom endpoints            | `@app.endpoint()` with path/query params                |
| SSE streaming               | Real-time workflow execution events                     |
| Sandbox validation          | Registration-time detection of blocked imports          |
| Trust middleware            | EATP agent verification                                 |
| Test coverage               | 1,515+ tests, 0 failures                                |

This implementation delivers the zero-config vision: a platform where enterprise users can focus on creating workflows without infrastructure complexity, while providing a full production-grade feature set when needed.
