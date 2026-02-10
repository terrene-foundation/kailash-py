# Quick Start Guide

**Get Nexus running in under 1 minute with zero configuration.**

## 30-Second Start

```python
from nexus import Nexus

# Zero configuration required
app = Nexus()
app.start()
```

That's it! You now have a running workflow platform with:

- **API Server** on `http://localhost:8000`
- **Health Check** at `http://localhost:8000/health`
- **Rate Limiting** at 100 requests/minute (default)
- **CLI Commands** available
- **MCP Tools** for AI agents

## Add Your First Workflow

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Create the platform
app = Nexus()

# Create a simple workflow
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch", {
    "url": "https://httpbin.org/json",
    "method": "GET"
})

# Register once, available everywhere (ALWAYS call .build())
app.register("fetch-data", workflow.build())

# Start the platform
app.start()

print("🚀 Nexus is running!")
print("📡 API: http://localhost:8000")
print("🔍 Health: http://localhost:8000/health")
print("📋 Workflows: http://localhost:8000/workflows")
```

## Test Your Workflow

**Via API (HTTP)**:

```bash
curl -X POST http://localhost:8000/workflows/fetch-data/execute
```

**Via CLI**:

```bash
nexus run fetch-data
```

**Via MCP** (for AI agents):

```json
{
  "method": "tools/call",
  "params": {
    "name": "fetch-data",
    "arguments": {}
  }
}
```

## Handler Pattern (Recommended)

For simple workflows, register async functions directly:

```python
from nexus import Nexus

app = Nexus()

@app.handler("greet", description="Greeting handler")
async def greet(name: str, greeting: str = "Hello") -> dict:
    """Available via API, CLI, and MCP from a single function."""
    return {"message": f"{greeting}, {name}!"}

app.start()
```

Test it:

```bash
curl -X POST http://localhost:8000/workflows/greet/execute \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"name": "World"}}'
```

## Enterprise Features (Optional)

Add authentication with the NexusAuthPlugin:

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig

# Create auth plugin
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"])
)

# Enterprise-ready platform
app = Nexus(
    api_port=8080,
    rate_limit=1000,          # Requests per minute
    enable_monitoring=True,   # Enable monitoring
    cors_origins=["https://myapp.com"],
)
app.add_plugin(auth)
app.start()
```

For SaaS applications with RBAC and tenant isolation:

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig

auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "user": ["read:*"]},
    tenant_isolation=TenantConfig(admin_role="admin"),
)

app = Nexus(preset="saas")
app.add_plugin(auth)
app.start()
```

## What Just Happened?

1. **Zero Configuration**: No config files, no environment variables, no setup
2. **Multi-Channel Registration**: Your workflow is instantly available via API, CLI, and MCP
3. **Enterprise Features**: Production-grade gateway with health checks, rate limiting, and auth plugins
4. **Handler Support**: Register async functions directly as multi-channel workflows
5. **Durable Execution**: Every request is a resumable workflow with checkpointing

## Next Steps

- **[Create more workflows](first-workflow.md)** - Build complex business logic
- **[Multi-channel usage](../user-guides/multi-channel-usage.md)** - Use API, CLI, and MCP
- **[Enterprise features](../user-guides/enterprise-features.md)** - Add auth, monitoring, scaling
- **[Architecture overview](../technical/architecture-overview.md)** - Understand the revolutionary design

## Troubleshooting

**Port already in use?**

```python
app = Nexus(api_port=8080, mcp_port=3002)
```

**Import errors?**

```bash
pip install kailash-nexus
```

**Need help?** Check the [troubleshooting guide](../technical/troubleshooting.md).
