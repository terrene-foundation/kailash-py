# Kailash Nexus - Multi-Channel Workflow Platform

**Version: 1.4.1** | Built on [Kailash Core SDK](https://github.com/terrene-foundation/kailash-py) | `pip install kailash-nexus`

Nexus is a **zero-configuration platform** that deploys Kailash workflows simultaneously across API, CLI, and MCP channels. Register a workflow once, and it becomes available as a REST endpoint, a CLI command, and an MCP tool -- with unified session state across all three.

```python
from nexus import Nexus

app = Nexus()
app.start()
```

## Installation

```bash
pip install kailash-nexus
```

```python
from nexus import Nexus
```

## Quick Start

### Zero-Config

```python
from nexus import Nexus

app = Nexus()
app.start()
```

### Workflow Registration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": "result = {'message': 'Hello, ' + parameters.get('name', 'World')}"
})

app.register("greet", workflow.build())
app.start()

# Now available on all channels:
# API:  POST http://localhost:8000/workflows/greet
# CLI:  nexus run greet --name "Alice"
# MCP:  greet tool for AI assistants
```

### Handler Pattern (Recommended)

The `@app.handler()` decorator registers async functions directly as multi-channel workflows. This bypasses PythonCodeNode sandbox restrictions and provides simpler syntax:

```python
from nexus import Nexus

app = Nexus()

@app.handler("summarize", description="Summarize text")
async def summarize(text: str, max_length: int = 200) -> dict:
    # No sandbox restrictions -- use any library
    return {"summary": text[:max_length]}

app.start()
```

Handlers derive parameters automatically from function signatures and deploy to all three channels from a single function definition.

## Part of the Kailash Ecosystem

Nexus is one of three frameworks built on the [Kailash Core SDK](https://github.com/terrene-foundation/kailash-py), each addressing a different layer of application development:

| Framework                                                           | Purpose                              | Install                        |
| ------------------------------------------------------------------- | ------------------------------------ | ------------------------------ |
| **[DataFlow](https://github.com/terrene-foundation/kailash-dataflow)** | Workflow-native database operations  | `pip install kailash-dataflow` |
| **Nexus** (this)                                                    | Multi-channel platform (API/CLI/MCP) | `pip install kailash-nexus`    |
| **[Kaizen](https://github.com/terrene-foundation/kailash-kaizen)**     | AI agent framework with trust        | `pip install kailash-kaizen`   |

All three frameworks share the same workflow execution model: `runtime.execute(workflow.build())`. Nexus serves as the deployment layer -- DataFlow database workflows and Kaizen AI agent workflows are both deployed through Nexus to reach users via REST API, command line, or MCP.

**CARE/EATP Trust Framework**: The Kailash platform includes a cross-cutting trust layer (Context, Action, Reasoning, Evidence) that propagates trust context through workflow execution. Nexus includes EATP trust middleware for agent verification, ensuring that workflows executing through Nexus channels carry trust lineage information. The `RuntimeTrustContext` from `kailash.runtime.trust` tracks human origin, delegation chains, and constraint propagation. Trust verification operates in three modes -- disabled (default, backward compatible), permissive (log violations), and enforcing (block on violations).

## Multi-Channel Architecture

```
                    Nexus Core
  +-----------+  +-----------+  +-----------+
  |    API    |  |    CLI    |  |    MCP    |
  |  Channel  |  |  Channel  |  |  Channel  |
  +-----+-----+  +-----+-----+  +-----+-----+
        |               |               |
        +---------------+---------------+
              Session Manager & Router
  +-------------------------------------------+
  |          Enterprise Gateway               |
  | Authentication  Rate Limiting             |
  | Authorization   Circuit Breaker           |
  | Monitoring      Caching                   |
  +-------------------------------------------+
  |            Kailash Core SDK               |
  |      Workflows | Nodes | Runtime          |
  +-------------------------------------------+
```

All channels produce the same internal parameter structure for workflows. API sends JSON body, CLI sends command-line arguments, MCP sends tool parameters -- Nexus normalizes them before execution.

## Native Middleware API

Nexus exposes a Starlette-compatible middleware API for adding custom behavior to the API channel:

```python
from nexus import Nexus

app = Nexus()

# Add ASGI/Starlette middleware
from starlette.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Mount FastAPI routers for custom endpoints
from fastapi import APIRouter
router = APIRouter()

@router.get("/custom")
async def custom_endpoint():
    return {"status": "ok"}

app.include_router(router, prefix="/api")

# Install plugins implementing NexusPluginProtocol
app.add_plugin(my_plugin)

app.start()
```

## Preset System

Presets apply preconfigured middleware stacks with a single parameter:

```python
from nexus import Nexus

# One-line middleware stack
app = Nexus(preset="saas")
```

| Preset        | What It Includes                                  |
| ------------- | ------------------------------------------------- |
| `none`        | No middleware (bare Nexus)                        |
| `lightweight` | Request logging, basic health checks              |
| `standard`    | Logging, CORS, error handling                     |
| `saas`        | Standard + auth, rate limiting, tenant isolation  |
| `enterprise`  | SaaS + audit logging, circuit breaker, monitoring |

## Authentication and Authorization

The `NexusAuthPlugin` provides a complete auth stack:

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, AuditConfig

# Basic auth setup
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # Must be >= 32 chars for HS*
    audit=AuditConfig(backend="logging"),
)

app = Nexus()
app.add_plugin(auth)
app.start()
```

### Auth Features

- **JWT**: HS256, RS256, JWKS (Auth0/Okta compatible). Secrets must be >= 32 characters for HS\* algorithms.
- **RBAC**: Role-based access control with wildcard permissions. Errors return generic "Forbidden" (no role/permission leakage).
- **SSO**: GitHub, Google, Azure AD, Apple providers. SSO errors are sanitized (status-only to client, details logged server-side).
- **Rate Limiting**: Memory and Redis backends, per-route configuration.
- **Tenant Isolation**: Header or JWT claim resolution with admin override.
- **Audit Logging**: Logging, DataFlow, and custom backends.

### Factory Methods

```python
# Minimal JWT auth
auth = NexusAuthPlugin.basic_auth(jwt=JWTConfig(secret=os.environ["JWT_SECRET"]))

# SaaS with RBAC and rate limiting
auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "user": ["read:*"]},
)

# Enterprise with full stack
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"]},
    sso_providers=["github", "google"],
    audit=AuditConfig(backend="dataflow"),
)
```

### Security Defaults

- `cors_allow_credentials=False` by default (safe with wildcard origins)
- RBAC errors return generic "Forbidden" messages
- SSO errors are sanitized before reaching clients

## Custom Endpoints

```python
from nexus import Nexus

app = Nexus()

@app.endpoint("/api/conversations/{conversation_id}", methods=["GET"], rate_limit=50)
async def get_conversation(conversation_id: str):
    return {"conversation_id": conversation_id}

@app.endpoint("/api/search")
async def search(q: str, limit: int = 10):
    return {"query": q, "limit": limit}

app.start()
```

## SSE Streaming

Execute workflows with Server-Sent Events for real-time updates:

```python
# POST /execute with {"mode": "stream"}
# Event types: start, complete, error, keepalive
```

## Plugin System

Create custom plugins implementing `NexusPluginProtocol`:

```python
from nexus import Nexus, NexusPluginProtocol


class MyPlugin:
    @property
    def name(self) -> str:
        return "my_plugin"

    def install(self, app: Nexus) -> None:
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

## Constructor Parameters

```python
app = Nexus(
    api_port=8000,            # API server port (default: 8000)
    mcp_port=3001,            # MCP server port (default: 3001)
    enable_auth=None,         # None=auto, True=always, False=never
    rate_limit=100,           # Requests/min (default: 100, None to disable)
    auto_discovery=False,     # Auto-discover workflow files (default: False)
    enable_monitoring=False,  # Enable monitoring (default: False)
    preset="none",            # Middleware preset (none/lightweight/standard/saas/enterprise)
    cors_origins=["*"],       # CORS allowed origins
    cors_allow_credentials=False,  # CORS credentials (default: False)
)
```

## Use Cases

### Deploy DataFlow Workflows

```python
from nexus import Nexus
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

@db.model
class Product:
    name: str
    price: float

app = Nexus()

workflow = WorkflowBuilder()
workflow.add_node("ProductListNode", "list_products", {
    "filter": {"price": {"$lt": 100}},
    "limit": 20
})
app.register("affordable_products", workflow.build())
app.start()
```

### Deploy Kaizen AI Agents

```python
import os
from dotenv import load_dotenv
load_dotenv()

from nexus import Nexus

app = Nexus()

@app.handler("ask", description="Ask the AI agent a question")
async def ask_agent(question: str) -> dict:
    from kaizen.api import Agent
    model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
    agent = Agent(model=model)
    result = await agent.run(question)
    return result

app.start()
```

## Implementation Architecture

```
nexus/
  __init__.py        # Exports: Nexus, NexusPluginProtocol, presets
  core.py            # Nexus class, middleware/router/plugin API
  presets.py         # Preset system
  discovery.py       # Auto-discovery of workflow files
  validation.py      # Registration-time sandbox validation
  channels.py        # Multi-channel configuration
  cli/               # CLI channel
  mcp/               # MCP channel
  trust/             # EATP trust middleware
  auth/              # Authentication and authorization
    plugin.py        # NexusAuthPlugin with factory methods
    jwt.py           # JWT middleware (HS256/RS256/JWKS)
    rbac.py          # Role-based access control
    sso/             # SSO providers (GitHub, Google, Azure, Apple)
    rate_limit/      # Rate limiting (memory + Redis)
    tenant/          # Tenant isolation middleware
    audit/           # Audit logging
```

## Testing

1,515+ tests across three tiers:

```bash
# Unit tests
python -m pytest tests/unit/ -v

# Integration tests (real middleware, auth flows)
python -m pytest tests/integration/ -v

# E2E tests (full API lifecycle)
python -m pytest tests/e2e/ -v
```

## Feature Summary

| Feature                     | Status                                                  |
| --------------------------- | ------------------------------------------------------- |
| Zero-config startup         | `Nexus()` with smart defaults                           |
| Workflow registration       | `app.register(name, workflow.build())`                  |
| Handler registration        | `@app.handler()` decorator                              |
| Multi-channel (API/CLI/MCP) | Automatic from single registration                      |
| Preset system               | none, lightweight, standard, saas, enterprise           |
| Plugin API                  | `NexusPluginProtocol` with `add_plugin()`               |
| Middleware API              | `add_middleware()`, `include_router()`                  |
| JWT authentication          | HS256, RS256, JWKS                                      |
| RBAC                        | Wildcard permissions, `RequireRole`/`RequirePermission` |
| SSO                         | GitHub, Google, Azure AD, Apple                         |
| Rate limiting               | Memory + Redis backends                                 |
| Tenant isolation            | Header/JWT claim resolution                             |
| Audit logging               | Logging, DataFlow, custom backends                      |
| EATP trust middleware       | Agent verification                                      |
| Custom endpoints            | `@app.endpoint()` with path/query params                |
| SSE streaming               | Real-time workflow events                               |
| Sandbox validation          | Registration-time blocked import detection              |
| Test coverage               | 1,515+ tests, 0 failures                                |

## Documentation

- [Nexus CLAUDE.md](CLAUDE.md) -- Quick reference for Claude Code
- [Quick Start](docs/getting-started/quick-start.md)
- [Architecture Overview](docs/technical/architecture-overview.md)
- [Integration Guide](docs/technical/integration-guide.md)
- [API Reference](docs/reference/api-reference.md)
- [CLI Reference](docs/reference/cli-reference.md)
- [Troubleshooting](docs/technical/troubleshooting.md)

## Version History

- **v1.4.1**: Current stable release
- **v1.3.0**: Middleware API, plugin system, presets, NexusAuthPlugin, CORS config
- **v1.2.0**: `@app.handler()` decorator, sandbox validation, EATP trust middleware
- **v1.1.0**: Enhanced security, rate limiting, MCP transport modes
