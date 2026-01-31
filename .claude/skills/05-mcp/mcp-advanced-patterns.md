---
name: mcp-advanced-patterns
description: "Advanced MCP patterns including multi-server config, JWT auth, service discovery, structured tools, and progress reporting. Use for 'advanced MCP', 'MCP discovery', 'MCP authentication', 'MCP registry'."
---

# Advanced MCP Patterns

> **Skill Metadata**
> Category: `mcp`
> Priority: `HIGH`
> SDK Version: `0.6.6+`
> Note: Real MCP execution is default since v0.6.6

## Multi-Server Configuration

```python
mcp_servers = [
    # HTTP server with auth
    {
        "name": "weather-service",
        "transport": "http",
        "url": "http://localhost:8081",
        "headers": {"API-Key": "demo-key"}
    },
    # STDIO server
    {
        "name": "calculator",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "mcp_calc_server"]
    },
    # External NPX server
    {
        "name": "file-system",
        "transport": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem", "./output"]
    }
]
```

## JWT Authentication

```python
from kailash.mcp_server.auth import JWTAuth

jwt_auth = JWTAuth(
    secret_key="your-secret-key",
    algorithm="HS256"
)

server = MCPServer("jwt-server", auth_provider=jwt_auth)

@server.tool(required_permission="admin")
async def admin_operation(action: str) -> dict:
    return {"action": action, "status": "completed"}
```

## Service Discovery Patterns

### Registry-Based Discovery

```python
from kailash.mcp_server.discovery import ServiceRegistry

registry = ServiceRegistry()

# Register server with capabilities
await registry.register_server({
    "id": "data-processor-001",
    "name": "data-processor",
    "transport": "stdio",
    "endpoint": "python -m data_processor",
    "capabilities": ["tools", "data_processing"],
    "metadata": {"version": "1.0", "priority": 10}
})

# Discover by capability
tools_servers = await registry.discover_servers(capability="tools")
```

### Convenience Functions

```python
from kailash.mcp_server import discover_mcp_servers, get_mcp_client

# Auto-discover servers
servers = await discover_mcp_servers(capability="tools")

# Get client for specific capability
client = await get_mcp_client("database")
```

## Structured Tools with Validation

```python
from kailash.mcp_server.advanced_features import structured_tool

@structured_tool(
    output_schema={
        "type": "object",
        "properties": {
            "results": {"type": "array"},
            "count": {"type": "integer"}
        },
        "required": ["results", "count"]
    }
)
def search_tool(query: str) -> dict:
    return {"results": ["item1", "item2"], "count": 2}
```

## Resource Templates and Subscriptions

```python
from kailash.mcp_server.advanced_features import ResourceTemplate

template = ResourceTemplate(
    uri_template="files://{path}",
    name="File Access",
    description="Access files by path"
)

# Subscribe to resource changes
subscription = await template.subscribe(
    uri="files://documents/report.pdf",
    callback=lambda change: print(f"File changed: {change}")
)
```

## Progress Reporting

```python
from kailash.mcp_server.protocol import ProgressManager

progress = ProgressManager()

# Long-running operation with progress
token = progress.start_progress("processing", total=100)
for i in range(100):
    await progress.update_progress(token, progress=i, status=f"Step {i}")
await progress.complete_progress(token)
```

## v0.6.6+ Breaking Changes

### Migration Pattern

```python
# OLD: Mock was default
workflow.add_node("LLMAgentNode", "agent", {
    "mcp_servers": [config]  # Was mocked by default
})

# NEW: Real is default, explicit mock needed
workflow.add_node("LLMAgentNode", "agent", {
    "mcp_servers": [config],
    "use_real_mcp": False  # Only for testing
})
```

- **Real MCP execution is now the default** (`use_real_mcp=True`)
- Previous mock behavior now requires explicit `use_real_mcp=False`
- Set `KAILASH_USE_REAL_MCP=false` for global mock behavior

## Production Readiness Checklist

- [ ] Real MCP execution enabled (default)
- [ ] Proper authentication configured
- [ ] Tool discovery enabled
- [ ] Error handling implemented
- [ ] Monitoring and metrics enabled
- [ ] Transport configuration complete

<!-- Trigger Keywords: advanced MCP, MCP discovery, MCP authentication, MCP registry, JWT MCP, multi-server MCP, structured tools, progress reporting, MCP subscription -->
