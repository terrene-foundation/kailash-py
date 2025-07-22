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
- ✅ **API Server** on `http://localhost:8000`
- ✅ **Health Check** at `http://localhost:8000/health`
- ✅ **Auto-Discovery** enabled for workflows
- ✅ **CLI Commands** available
- ✅ **MCP Tools** for AI agents

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

# Register once, available everywhere
app.register("fetch-data", workflow)

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

## Enterprise Features (Optional)

Add enterprise features with simple constructor options:

```python
from nexus import Nexus

# Enterprise-ready platform
app = Nexus(
    enable_auth=True,        # OAuth2, API keys, RBAC
    enable_monitoring=True,  # Prometheus, OpenTelemetry
    rate_limit=1000,        # Requests per minute
    api_port=8080          # Custom port
)

app.start()
```

## Progressive Enhancement

Fine-tune via attributes:

```python
from nexus import Nexus

app = Nexus()

# Configure authentication
app.auth.strategy = "oauth2"
app.auth.provider = "google"

# Configure monitoring
app.monitoring.interval = 30
app.monitoring.metrics = ["requests", "latency", "errors"]

# Configure API
app.api.cors_enabled = True
app.api.max_request_size = 10 * 1024 * 1024  # 10MB

app.start()
```

## What Just Happened?

1. **Zero Configuration**: No config files, no environment variables, no setup
2. **Multi-Channel Registration**: Your workflow is instantly available via API, CLI, and MCP
3. **Enterprise Features**: Production-grade gateway with health checks, docs, monitoring
4. **Auto-Discovery**: Nexus automatically discovers workflows in your project
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
