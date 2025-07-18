# Nexus Implementation Guide

## Overview

Nexus is a **zero-configuration wrapper** around the Kailash SDK's enterprise components. This guide explains how to properly leverage enterprise functionality instead of recreating it.

## Core Principle: SDK-First Enterprise Architecture

**✅ DO**: Leverage existing SDK enterprise components
**❌ DON'T**: Recreate enterprise functionality from scratch

## Enterprise Components Used

### 1. EnterpriseWorkflowServer (Core Foundation)

```python
from kailash.servers.gateway import create_gateway

# Nexus uses enterprise server by default
self._gateway = create_gateway(
    server_type="enterprise",
    enable_durability=True,
    enable_resource_management=True,
    enable_async_execution=True,
    enable_health_checks=True
)
```

**Provides out-of-the-box:**
- Multi-channel support (API, CLI, MCP)
- Enterprise endpoints (`/enterprise/health`, `/enterprise/features`)
- Authentication and authorization
- Resource management and registry
- Async workflow execution
- Health monitoring and metrics

### 2. MCPClient (Production MCP)

```python
from kailash.mcp_server.client import MCPClient

# Use SDK's production MCP client
mcp_client = MCPClient(
    auth_provider=auth_provider,
    retry_strategy="circuit_breaker",
    enable_metrics=True,
    enable_http_transport=True
)
```

**Provides:**
- Multiple transports (stdio, sse, http)
- Authentication, retry strategies, circuit breaker
- Connection pooling, metrics, health checks
- Real tool execution capabilities

### 3. MiddlewareAuthManager (Enterprise Auth)

```python
from kailash.middleware.auth.auth_manager import MiddlewareAuthManager

# Use SDK's enterprise authentication
auth_manager = MiddlewareAuthManager(
    enable_api_keys=True,
    enable_audit=True
)
```

**Provides:**
- JWT token management with CredentialManagerNode
- API key rotation with RotatingCredentialNode
- Permission checking with PermissionCheckNode
- Security event logging and audit trails

### 4. CLI and MCP Channels

```python
from kailash.channels.cli_channel import CLIChannel
from kailash.channels.mcp_channel import MCPChannel

# Use SDK's channel implementations
cli_channel = CLIChannel(config)
mcp_channel = MCPChannel(config)
```

## Implementation Patterns

### Nexus Initialization

```python
class Nexus:
    def __init__(self, api_port=8000, **kwargs):
        # Use enterprise gateway - NOT basic server
        self._gateway = create_gateway(
            title="Kailash Nexus - Zero-Config Workflow Platform",
            server_type="enterprise",  # Required
            cors_origins=["*"],
            max_workers=20
        )

        # Enterprise gateway provides all needed capabilities:
        # - Multi-channel support
        # - Authentication and authorization
        # - Health monitoring and metrics
        # - Resource management
        # - Durability and async execution
```

### Workflow Registration

```python
def register(self, name: str, workflow: Workflow):
    """Register workflow using enterprise gateway."""
    # Handle WorkflowBuilder
    if hasattr(workflow, "build"):
        workflow = workflow.build()

    # Store for Nexus-specific features
    self._workflows[name] = workflow

    # Register with enterprise gateway - auto multi-channel exposure
    self._gateway.register_workflow(name, workflow)
```

### Authentication Integration

```python
def enable_auth(self):
    """Enable authentication using SDK capabilities."""
    if hasattr(self._gateway, 'enable_auth'):
        self._gateway.enable_auth()
    # Fallback to plugin system if needed
    return self.use_plugin("auth")
```

## Enterprise Endpoints Available

The enterprise gateway automatically provides:

### Core Endpoints
- `GET /` - Server information with enterprise details
- `GET /health` - Standard health check
- `GET /workflows` - List registered workflows
- `WebSocket /ws` - Real-time updates

### Enterprise-Specific Endpoints
- `GET /enterprise/features` - Enabled enterprise features
- `GET /enterprise/health` - Comprehensive health check
- `GET /enterprise/resources` - Resource management
- `POST /enterprise/workflows/{id}/execute_async` - Async execution

## Testing Enterprise Integration

### Unit Tests
```python
def test_enterprise_gateway_initialization():
    """Test that Nexus uses enterprise components."""
    app = Nexus(api_port=8001)
    assert isinstance(app._gateway, EnterpriseWorkflowServer)
    assert app._gateway.enable_durability == True
    assert app._gateway.enable_resource_management == True
```

### Integration Tests
```python
def test_enterprise_endpoints():
    """Test enterprise endpoints are available."""
    # Test /enterprise/health
    response = requests.get(f"{base_url}/enterprise/health")
    assert response.status_code == 200

    # Test /enterprise/features
    response = requests.get(f"{base_url}/enterprise/features")
    assert response.status_code == 200
```

## What Nexus Adds

Nexus provides a **zero-configuration wrapper** that:

1. **Simplifies initialization** of enterprise components
2. **Provides progressive enhancement** API
3. **Enables auto-discovery** of workflows
4. **Offers developer-friendly** interface

Nexus does NOT recreate enterprise functionality.

## Migration from Custom Implementation

### Before (Custom Implementation)
```python
# WRONG: Recreating enterprise functionality
server = WorkflowServer()  # Basic server
@server.app.get("/metrics")
def custom_metrics(): pass  # Recreating
@server.app.post("/auth/login")
def custom_auth(): pass     # Recreating
```

### After (SDK Enterprise)
```python
# CORRECT: Using enterprise components
gateway = create_gateway(server_type="enterprise")
# All enterprise endpoints provided automatically
# /enterprise/health, /enterprise/features, etc.
```

## Plugin System

For Nexus-specific enhancements:

```python
def use_plugin(self, plugin_name: str):
    """Apply additional features via plugins."""
    from .plugins import get_plugin_registry
    registry = get_plugin_registry()
    registry.apply(plugin_name, self)
    return self
```

## Performance Targets

Using enterprise components:
- **Startup time**: <2 seconds
- **Request latency**: <100ms
- **Multi-channel registration**: <1 second per workflow
- **Enterprise features**: Enabled by default

## Error Handling

```python
def _initialize_gateway(self):
    """Initialize enterprise gateway with error handling."""
    try:
        self._gateway = create_gateway(server_type="enterprise")
    except Exception as e:
        # Fail fast - enterprise required for production
        raise RuntimeError(f"Nexus requires enterprise gateway: {e}")
```

## Best Practices

1. **Always use enterprise server** - Never fallback to basic
2. **Leverage built-in endpoints** - Don't recreate enterprise functionality
3. **Use SDK auth components** - Don't implement custom authentication
4. **Test enterprise integration** - Verify all enterprise features work
5. **Monitor SDK updates** - Stay current with enterprise enhancements

## Related Documentation

- [`/docs/ARCHITECTURE_DECISION_RECORD.md`](./ARCHITECTURE_DECISION_RECORD.md) - Architecture decisions
- [`/tests/`](../tests/) - Enterprise integration tests
- SDK enterprise documentation - Primary reference
