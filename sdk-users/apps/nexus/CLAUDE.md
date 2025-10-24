# Kailash Nexus - Quick Reference for Claude Code

## 🚀 Zero-Config Platform

**Nexus** provides unified workflow orchestration across API, CLI, and MCP channels with true zero-configuration setup.

## ⚡ Quick Start

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Zero configuration needed
app = Nexus()

# Create and register a workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {"code": "result = {'message': 'Hello!'}"})
app.register("my_workflow", workflow.build())

# Start the platform (runs in foreground)
app.start()
```

## 🎯 Core API

### Constructor (v1.1.1+ Security Defaults)
```python
app = Nexus(
    api_port=8000,                # API server port (default: 8000)
    mcp_port=3001,                # MCP server port (default: 3001)

    # Security (v1.1.1+ improved defaults)
    enable_auth=None,             # Authentication (default: None)
                                  # None = auto-enable if NEXUS_ENV=production
                                  # True = always enabled
                                  # False = always disabled (logs warning in production)

    rate_limit=100,               # Rate limit req/min (default: 100 for DoS protection)
                                  # Set to None to disable (not recommended)

    # Discovery (v1.1.1+ changed to prevent blocking)
    auto_discovery=False,         # Auto-discover workflows (default: False)
                                  # Set to True to enable auto-discovery

    enable_monitoring=False       # Enable monitoring (default: False)
)
```

### Registration
```python
# Register a workflow
app.register(name: str, workflow: Workflow)

# The workflow is automatically available on:
# - API: POST /workflows/{name}
# - CLI: nexus run {name}
# - MCP: As a tool named {name}
```

## 📚 Documentation Structure

### Getting Started
- **[Quick Start](docs/getting-started/quick-start.md)** - 5-minute tutorial
- **[Concepts](docs/getting-started/concepts.md)** - Core concepts

### User Guides
- **[Workflow Registration](docs/user-guides/workflow-registration.md)** - Register workflows
- **[Multi-Channel Access](docs/user-guides/multi-channel-access.md)** - API, CLI, MCP usage

### Technical Guides
- **[Architecture](docs/technical/architecture-overview.md)** - System architecture
- **[Integration](docs/technical/integration-guide.md)** - Integration patterns
- **[Troubleshooting](docs/technical/troubleshooting.md)** - Common issues

### Reference
- **[API Reference](docs/reference/api-reference.md)** - Complete API docs
- **[CLI Reference](docs/reference/cli-reference.md)** - CLI commands

## 🔧 Common Patterns

### Basic Workflow Registration
```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {"model": "gpt-4"})

# Register workflow
app.register("chat", workflow.build())

# Note: Use app.start() to run the platform (blocks until stopped)
```

### Enterprise Configuration
```python
app = Nexus(enable_auth=True, enable_monitoring=True)

# Configure auth (optional)
app.auth.strategy = "oauth2"
app.auth.provider = "auth0"

# Configure monitoring (optional)
app.monitoring.backend = "prometheus"
app.monitoring.interval = 60

# Note: Use app.start() to run the platform (blocks until stopped)
```

### Parameter Passing
```python
# Workflows receive parameters from all channels:
# API: JSON body
# CLI: Command-line arguments
# MCP: Tool parameters

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": "result = parameters.get('input_data', [])"
})
```

## ⚠️ Common Mistakes to Avoid

1. **Wrong Import**: Use `from nexus import Nexus`, NOT `from kailash.nexus import create_nexus`
2. **Wrong Registration Order**: Use `app.register(name, workflow)`, NOT `app.register(workflow, name)`
3. **Missing Build**: Remember to call `.build()` on WorkflowBuilder before registering
4. **Port Conflicts**: Default ports are 8000 (API) and 3001 (MCP) - check if they're available

## 🧪 Testing

### Unit Tests
```python
from nexus import Nexus

def test_workflow_registration():
    app = Nexus()
    app.register("test", workflow)
    assert "test" in app._workflows
```

### Integration Tests
See `tests/integration/test_nexus_integration.py` for examples.

## 🏗️ Architecture

Nexus uses Kailash SDK's enterprise gateway for unified workflow management:

```
┌─────────────────────────────────────────────────┐
│                    Nexus                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │   API    │  │   CLI    │  │   MCP    │     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
│       └──────────────┴──────────────┘           │
│              Enterprise Gateway                  │
├─────────────────────────────────────────────────┤
│               Kailash SDK                       │
│         Workflows │ Nodes │ Runtime             │
└─────────────────────────────────────────────────┘
```

## 🚦 Production Deployment

See [Production Guide](docs/production/deployment.md) for:
- Docker deployment
- Kubernetes manifests
- Environment configuration
- Monitoring setup
- Security hardening

## 💡 Tips

1. **Zero-Config First**: Start with `Nexus()` and add features only when needed
2. **Use Registration**: Don't try to use decorators - use `app.register()`
3. **Check Health**: Use `app.health_check()` to verify services are running
4. **Multi-Channel**: Test your workflows on all three channels (API, CLI, MCP)
5. **Enterprise Features**: Enable auth and monitoring only when going to production

---

**For SDK details**: See [../../sdk-users/](../../sdk-users/)
**For examples**: See [examples/](examples/)
