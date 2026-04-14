# MCP Integration Quick Reference for Kaizen

**Last Updated**: 2025-10-04

---

## Essential Imports

```python
# Client
from kailash_mcp import MCPClient

# Server
from kailash_mcp import MCPServer, SimpleMCPServer

# Authentication
from kailash_mcp.auth import APIKeyAuth, JWTAuth, BearerTokenAuth

# Discovery
from kailash_mcp import ServiceRegistry, ServerInfo, enable_auto_discovery

# Error Handling
from kailash_mcp.errors import (
    MCPError, AuthenticationError, ToolError, TransportError
)
```

---

## Client Pattern (3 Lines)

```python
from kailash_mcp import MCPClient

client = MCPClient(enable_metrics=True)
tools = await client.discover_tools(server_config)
result = await client.call_tool(server_config, "tool_name", {"arg": "value"})
```

---

## Simple Server Pattern (5 Lines)

```python
from kailash_mcp import SimpleMCPServer

server = SimpleMCPServer("my-tools")

@server.tool()
def add(a: int, b: int) -> dict:
    return {"result": a + b}

server.run()
```

---

## LLM Agent with MCP (Complete Example)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {})

runtime = LocalRuntime()
results, _ = runtime.execute(
    workflow.build(),
    parameters={
        "agent": {
            "provider": "ollama",
            "model": "llama3.2",
            "messages": [{"role": "user", "content": "Your question"}],
            "mcp_servers": [{
                "name": "tools",
                "transport": "stdio",
                "command": "npx",
                "args": ["@modelcontextprotocol/server-filesystem", "/data"]
            }],
            "auto_discover_tools": True,
            "auto_execute_tools": True
        }
    }
)
```

---

## Server Configurations

### STDIO Transport

```python
{
    "name": "local-server",
    "transport": "stdio",
    "command": "python",
    "args": ["-m", "mcp_server"]
}
```

### HTTP Transport

```python
{
    "name": "remote-server",
    "transport": "http",
    "url": "http://localhost:8080",
    "headers": {"Authorization": "Bearer token"}
}
```

### WebSocket Transport

```python
{
    "name": "realtime-server",
    "transport": "websocket",
    "url": "ws://localhost:3001/mcp",
    "connection_pool_config": {
        "max_connections": 10
    }
}
```

---

## Authentication Patterns

### API Key

```python
from kailash_mcp.auth import APIKeyAuth

auth = APIKeyAuth({
    "admin_key": {"permissions": ["read", "write", "admin"]},
    "read_key": {"permissions": ["read"]}
})
server = MCPServer("secure-server", auth_provider=auth)
```

### JWT

```python
from kailash_mcp.auth import JWTAuth

auth = JWTAuth(secret="my-secret", expiration=3600)
token = auth.create_token({"user": "alice", "permissions": ["read", "write"]})
```

---

## Production Server

```python
from kailash_mcp import MCPServer
from kailash_mcp.auth import JWTAuth

auth = JWTAuth(secret="production-secret")
server = MCPServer(
    "prod-server",
    auth_provider=auth,
    enable_cache=True,
    enable_metrics=True,
    rate_limit_config={"requests_per_minute": 1000},
    circuit_breaker_config={"failure_threshold": 10}
)

@server.tool(cache_ttl=300)
async def expensive_op(data: str) -> dict:
    return {"result": process(data)}

server.run()
```

---

## Service Discovery

```python
from kailash_mcp import ServiceRegistry, ServerInfo

registry = ServiceRegistry()

# Register
server_info = ServerInfo(
    name="weather",
    transport="http",
    url="http://localhost:8080",
    capabilities=["weather.get", "weather.forecast"]
)
await registry.register_server(server_info)

# Discover
servers = await registry.discover_servers(capability="weather.get")
```

---

## Error Handling

```python
from kailash_mcp.errors import (
    MCPError, AuthenticationError, ToolError, TransportError
)

try:
    result = await client.call_tool(config, "tool", args)
except AuthenticationError:
    # Handle auth failure
    pass
except ToolError as e:
    # Handle tool execution error
    print(f"Tool failed: {e.error_code}")
except TransportError:
    # Handle connection issues
    pass
```

---

## Retry Strategies

```python
from kailash_mcp import MCPClient

# Exponential backoff
client = MCPClient(retry_strategy="exponential")

# Circuit breaker
client = MCPClient(
    retry_strategy="circuit_breaker",
    circuit_breaker_config={"failure_threshold": 5, "timeout": 60}
)
```

---

## Testing Patterns

### Unit Test

```python
def test_mcp_client():
    from kailash_mcp import MCPClient
    client = MCPClient(enable_metrics=True)
    assert client.metrics is not None
```

### Integration Test

```python
@pytest.mark.integration
async def test_real_server():
    from kailash_mcp import MCPClient, MCPServer

    server = MCPServer("test")
    @server.tool()
    async def add(a: int, b: int) -> dict:
        return {"result": a + b}

    # Start server, test with client
    client = MCPClient()
    result = await client.call_tool(config, "add", {"a": 2, "b": 3})
    assert result["success"]
```

---

## Key Files Reference

### Documentation

- Quick Start: `sdk-users/1-quickstart/mcp-quickstart.md`
- Integration: `sdk-users/2-core-concepts/cheatsheet/025-mcp-integration.md`
- Development: `sdk-users/3-development/17-mcp-development-guide.md`

### Source Code

- Client: `src/kailash/mcp_server/client.py`
- Server: `src/kailash/mcp_server/server.py`
- Auth: `src/kailash/mcp_server/auth.py`
- Discovery: `src/kailash/mcp_server/discovery.py`

### Examples

- See `implementation-guide.md` in this directory for complete inline examples (Sections 6.1 and 6.2)

---

## Common Patterns

### Discover and Execute

```python
# Discover tools
tools = await client.discover_tools(server_config)

# Execute specific tool
result = await client.call_tool(server_config, "search", {"query": "AI"})
```

### Multiple Servers

```python
mcp_servers = [
    {"name": "db", "transport": "stdio", "command": "mcp-sqlite"},
    {"name": "api", "transport": "http", "url": "http://api.example.com"},
    {"name": "files", "transport": "stdio", "command": "mcp-fs"}
]
```

### Health Checking

```python
health = await client.health_check(server_config)
if health["status"] == "healthy":
    print(f"Server ready ({health['tools_available']} tools)")
```

---

## For Kaizen Integration

1. **Replace** `from kaizen.mcp import ...` with `from kailash_mcp import ...`
2. **Use** Kailash's proven patterns instead of custom implementations
3. **Follow** Kailash's 3-tier testing strategy
4. **Reference** Kailash MCP docs in Kaizen documentation

---

## Production Checklist

- [ ] Use authentication (APIKeyAuth, JWTAuth, or OAuth)
- [ ] Enable metrics for monitoring
- [ ] Configure rate limiting
- [ ] Set up circuit breaker for reliability
- [ ] Enable caching for performance
- [ ] Use connection pooling for WebSocket
- [ ] Configure retry strategies
- [ ] Set appropriate timeouts
- [ ] Enable health checks
- [ ] Log all errors and tool executions

---

## See Also

- **Full Analysis**: `KAILASH_MCP_IMPLEMENTATION_ANALYSIS.md` (comprehensive patterns)
- **Kailash Docs**: `../../kailash_python_sdk/sdk-users/` (complete SDK documentation)
- **Test Examples**: `../../kailash_python_sdk/tests/integration/mcp_server/` (real integration tests)
