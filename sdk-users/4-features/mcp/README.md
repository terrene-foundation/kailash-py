# Model Context Protocol (MCP) Integration

**Complete production-ready MCP implementation with enterprise features**

The Kailash SDK provides a comprehensive Model Context Protocol implementation that extends the official MCP Python SDK with production-ready capabilities including service discovery, authentication, load balancing, and advanced protocol features.

## 🚀 Quick Start

### Basic MCP Server

```python
from kailash.mcp_server import MCPServer

# Create server
server = MCPServer("my-ai-server")

# Add tools
@server.tool()
def search_data(query: str) -> dict:
    """Search for data based on query."""
    return {"results": f"Found data for: {query}"}

@server.tool(cache_key="calculate", cache_ttl=300)
def calculate(expression: str) -> dict:
    """Calculate mathematical expression."""
    result = eval(expression)  # Note: Use safe evaluation in production
    return {"expression": expression, "result": result}

# Add resources
@server.resource("config://settings")
def get_settings():
    """Get application settings."""
    return {"version": "1.0.0", "features": ["tools", "resources"]}

# Run server
server.run()  # Starts on STDIO by default
```

### MCP Client

```python
from kailash.mcp_server import MCPClient

# Configure client
config = {
    "name": "ai-client",
    "transport": "stdio",
    "command": "python",
    "args": ["-m", "my_mcp_server"]
}

client = MCPClient(config)

# Connect and use
async with client:
    # Call tools
    result = await client.call_tool("search_data", {"query": "AI models"})
    print(result)

    # Read resources
    settings = await client.read_resource("config://settings")
    print(settings)
```

## 🏗️ Production Setup

### Server with Authentication

```python
from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth

# Setup authentication
auth = APIKeyAuth({
    "admin_key_123": {"permissions": ["admin", "tools", "resources"]},
    "user_key_456": {"permissions": ["tools"]}
})

# Create production server
server = MCPServer(
    "production-server",
    auth_provider=auth,
    enable_metrics=True,
    enable_http_transport=True,
    rate_limit_config={"requests_per_minute": 100},
    circuit_breaker_config={"failure_threshold": 5}
)

# Admin-only tool
@server.tool(required_permission="admin")
def admin_operation(action: str) -> dict:
    """Administrative operation requiring admin permission."""
    return {"action": action, "status": "completed"}

# Public tool with caching
@server.tool(cache_key="public_data", cache_ttl=600)
def get_public_data(category: str) -> dict:
    """Get public data by category."""
    return {"category": category, "data": "public information"}

server.run()
```

### Service Discovery

```python
from kailash.mcp_server import discover_mcp_servers, get_mcp_client

# Discover available servers
servers = await discover_mcp_servers(capability="search")
print(f"Found {len(servers)} search servers")

# Get best client for capability
client = await get_mcp_client("search")
if client:
    result = await client.call_tool("search", {"query": "AI"})
```

## 🔧 Advanced Features

### Progress Reporting

```python
from kailash.mcp_server.advanced_features import create_progress_reporter

@server.tool()
async def long_operation(data: str, progress_token=None) -> dict:
    """Long-running operation with progress reporting."""
    async with create_progress_reporter("processing", total=100) as progress:
        for i in range(100):
            # Do work
            await asyncio.sleep(0.01)
            await progress.update(progress=i, status=f"Processing step {i}")

    return {"result": f"Processed {data}"}
```

### Structured Tools with Validation

```python
from kailash.mcp_server.advanced_features import structured_tool

@structured_tool(
    input_schema={
        "type": "object",
        "properties": {
            "email": {"type": "string", "format": "email"},
            "age": {"type": "integer", "minimum": 0}
        },
        "required": ["email"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "user_id": {"type": "string"}
        },
        "required": ["status"]
    }
)
@server.tool()
def create_user(email: str, age: int = None) -> dict:
    """Create user with validation."""
    user_id = f"user_{hash(email) % 10000}"
    return {"status": "created", "user_id": user_id}
```

### Multi-Modal Content

```python
from kailash.mcp_server.advanced_features import MultiModalContent

@server.tool()
def generate_report(data: str) -> dict:
    """Generate report with multiple content types."""
    content = MultiModalContent()
    content.add_text("Analysis Report")
    content.add_image(chart_image_bytes, "image/png")
    content.add_resource("file://report.pdf", "Full Report")

    return {"content": content.to_list()}
```

### OAuth 2.1 Authentication

```python
from kailash.mcp_server.oauth import AuthorizationServer, ResourceServer

# Authorization server
auth_server = AuthorizationServer(
    issuer="https://auth.example.com",
    private_key_path="private.pem"
)

# Register client
client = await auth_server.register_client(
    client_name="MCP Client",
    redirect_uris=["http://localhost:8080/callback"],
    grant_types=["authorization_code"],
    scopes=["mcp.tools", "mcp.resources"]
)

# Resource server
resource_server = ResourceServer(
    issuer="https://auth.example.com",
    audience="mcp-api"
)

server = MCPServer("oauth-server", auth_provider=resource_server)
```

## 🌐 Transport Options

### STDIO (Default)
```python
# Server runs on STDIO by default
server = MCPServer("stdio-server")
server.run()

# Client connects via STDIO
client_config = {
    "transport": "stdio",
    "command": "python",
    "args": ["-m", "my_server"]
}
```

### HTTP Transport
```python
# Server with HTTP
server = MCPServer("http-server", enable_http_transport=True)
server.run(host="localhost", port=8080)

# Client via HTTP
client_config = {
    "transport": "http",
    "url": "http://localhost:8080"
}
```

### Server-Sent Events (SSE)
```python
# Server with SSE
server = MCPServer("sse-server", enable_sse_transport=True)

# Client via SSE
client_config = {
    "transport": "sse",
    "url": "http://localhost:8080/sse"
}
```

### WebSocket Transport
```python
# Basic WebSocket client
client_config = {
    "transport": "websocket",
    "url": "ws://localhost:8080/ws"
}

# WebSocket with enterprise connection pooling
client_config = {
    "transport": "websocket",
    "url": "wss://api.example.com/mcp",
    "connection_pool_config": {
        "max_connections": 10,
        "connection_timeout": 30.0,
        "pool_cleanup_interval": 300
    },
    "ping_interval": 20.0,
    "ping_timeout": 20.0
}

# WebSocket server transport
from kailash.mcp_server.transports import WebSocketTransport, WebSocketServerTransport

# Client transport for connecting to servers
ws_transport = WebSocketTransport(
    url="wss://secure.example.com/mcp",
    subprotocols=["mcp-v1"],  # MCP protocol version
    ping_interval=20.0,
    ping_timeout=20.0
)

# Server transport for accepting connections
ws_server = WebSocketServerTransport(
    host="0.0.0.0",
    port=3001,
    ping_interval=20.0,
    ping_timeout=20.0,
    max_message_size=10 * 1024 * 1024  # 10MB message limit
)
```

## 🌐 WebSocket Transport Features

### Connection Pooling
Kailash MCP client includes enterprise-grade WebSocket connection pooling:

```python
from kailash.mcp_server import MCPClient

# Configure connection pooling
client = MCPClient(
    connection_pool_config={
        "max_connections": 20,      # Maximum pooled connections
        "connection_timeout": 30.0, # Connection timeout in seconds
        "pool_cleanup_interval": 300, # Pool cleanup interval in seconds
        "keep_alive": True,         # Keep connections alive
        "ping_interval": 20.0      # WebSocket ping interval
    }
)

# Use pooled connections automatically
async with client:
    # First call creates connection and pools it
    result1 = await client.call_tool("ws://api.example.com/mcp", "search", {"query": "AI"})

    # Second call reuses pooled connection (faster)
    result2 = await client.call_tool("ws://api.example.com/mcp", "analyze", {"data": result1})

    # Pool automatically manages connection lifecycle
```

### Error Handling & Resilience
WebSocket transport includes comprehensive error handling:

```python
from kailash.mcp_server.errors import TransportError, ConnectionError

try:
    async with client:
        result = await client.call_tool("wss://unreliable.example.com/mcp", "process", {"data": "test"})

except TransportError as e:
    if "connection" in str(e).lower():
        print(f"Connection failed: {e}")
        # Implement retry logic

except ConnectionError as e:
    print(f"WebSocket connection error: {e}")
    # Connection was dropped, will be cleaned from pool
```

### Performance Monitoring
Built-in metrics for WebSocket connections:

```python
# Enable metrics collection
client = MCPClient(enable_metrics=True)

async with client:
    # Make some calls
    await client.call_tool("ws://api.example.com/mcp", "test", {})

    # Get connection metrics
    metrics = client.get_metrics()
    print(f"Pool hits: {metrics.get('websocket_pool_hits', 0)}")
    print(f"Pool misses: {metrics.get('websocket_pool_misses', 0)}")
    print(f"Active connections: {len(client._websocket_pools)}")
```

### Security Considerations
WebSocket transport security limitations and best practices:

```python
# ⚠️ IMPORTANT: WebSocket transport limitations
# - No support for custom authentication headers during handshake
# - SSL/TLS termination should be handled by reverse proxy
# - Use wss:// URLs for production environments

# Production WebSocket setup
client_config = {
    "transport": "websocket",
    "url": "wss://secure-api.example.com/mcp",  # Always use wss:// in production
    "ping_interval": 30.0,     # Longer intervals for production
    "ping_timeout": 10.0,      # Shorter timeout for faster failure detection
    "allow_localhost": False,  # Disable localhost for production
    "skip_security_validation": False  # Never skip security validation
}

# For development/testing only
dev_config = {
    "transport": "websocket",
    "url": "ws://localhost:3001/mcp",
    "allow_localhost": True,          # OK for development
    "skip_security_validation": True  # Only for testing
}
```

## 📊 Service Discovery & Load Balancing

### Automatic Server Discovery

```python
from kailash.mcp_server import ServiceRegistry, enable_auto_discovery

# Enable auto-discovery for server
server = MCPServer("discoverable-server")
registrar = enable_auto_discovery(
    server,
    enable_network_discovery=True,
    capabilities=["tools", "nlp", "search"]
)
registrar.start_with_registration()

# Discover servers programmatically
registry = ServiceRegistry()
servers = await registry.discover_servers(capability="nlp")
best_server = await registry.get_best_server_for_capability("search")
```

### Service Mesh with Failover

```python
from kailash.mcp_server import ServiceMesh

mesh = ServiceMesh(registry)

# Call with automatic failover
result = await mesh.call_with_failover(
    capability="search",
    tool="web_search",
    params={"query": "Python MCP"},
    max_retries=3
)
```

## 🔒 Security Features

### API Key Authentication
```python
from kailash.mcp_server.auth import APIKeyAuth

auth = APIKeyAuth({
    "key1": {"permissions": ["tools"], "rate_limit": {"requests": 100, "window": 60}},
    "key2": {"permissions": ["admin"], "metadata": {"user": "admin"}}
})
```

### JWT Authentication
```python
from kailash.mcp_server.auth import JWTAuth

auth = JWTAuth(
    secret="your-secret-key",
    algorithm="HS256",
    token_expiry=3600
)

# Create token
token = auth.create_token({
    "user": "alice",
    "permissions": ["tools", "resources"],
    "exp": time.time() + 3600
})
```

### Rate Limiting
```python
server = MCPServer(
    "rate-limited-server",
    rate_limit_config={
        "requests_per_minute": 100,
        "burst_size": 20,
        "per_user": True
    }
)
```

## 📈 Monitoring & Metrics

### Built-in Metrics
```python
server = MCPServer("monitored-server", enable_metrics=True)

# Get metrics
metrics = server.get_metrics()
print(f"Tools called: {metrics['tools_called']}")
print(f"Cache hits: {metrics['cache_hits']}")
print(f"Error rate: {metrics['error_rate']}")
```

### Custom Metrics
```python
@server.tool()
def monitored_tool(data: str) -> dict:
    """Tool with custom metrics."""
    start_time = time.time()

    # Do work
    result = process_data(data)

    # Record custom metric
    server.metrics.record("processing_time", time.time() - start_time)
    server.metrics.increment("data_processed")

    return result
```

## 🛠️ Error Handling

### Structured Errors
```python
from kailash.mcp_server.errors import MCPError, MCPErrorCode

@server.tool()
def safe_tool(data: str) -> dict:
    """Tool with proper error handling."""
    try:
        if not data:
            raise MCPError(
                "Data cannot be empty",
                error_code=MCPErrorCode.INVALID_PARAMS
            )

        result = process_data(data)
        return {"result": result}

    except ValueError as e:
        raise MCPError(
            f"Invalid data format: {e}",
            error_code=MCPErrorCode.VALIDATION_ERROR,
            retryable=False
        )
```

### Circuit Breaker
```python
server = MCPServer(
    "resilient-server",
    circuit_breaker_config={
        "failure_threshold": 5,
        "timeout": 60,
        "success_threshold": 3
    }
)

@server.tool(enable_circuit_breaker=True)
def external_api_tool(query: str) -> dict:
    """Tool that calls external API with circuit breaker."""
    # This will be protected by circuit breaker
    return call_external_api(query)
```

## 🧪 Testing

### ✅ Test Results (2025-07-04)
**Comprehensive testing completed:** 407 tests across all MCP components with **100% pass rate**

- **Unit Tests**: 391 tests covering auth, server, client, errors, cache, config, metrics, formatters
- **Integration Tests**: 14 tests with real Docker services (NO MOCKING)
- **E2E Tests**: 2 end-to-end scenarios validating tool execution workflows

### Unit Testing Examples
```python
import pytest
from kailash.mcp_server import MCPServer

def test_mcp_server_creation():
    server = MCPServer("test-server")
    assert server.name == "test-server"

def test_tool_registration():
    server = MCPServer("test-server")

    @server.tool()
    def test_tool(data: str) -> str:
        return f"processed: {data}"

    result = test_tool("test")
    assert result == "processed: test"

def test_auth_configuration():
    """Test authentication setup."""
    from kailash.mcp_server.auth import APIKeyAuth

    auth = APIKeyAuth(["key1", "key2"])
    server = MCPServer("auth-server", auth_provider=auth)
    assert server.auth_provider is not None
```

### Integration Testing with Real Services
```python
import pytest
from kailash.mcp_server import MCPClient, MCPServer

@pytest.mark.integration
@pytest.mark.requires_docker
async def test_client_server_communication():
    """Test real client-server communication."""
    # Setup server with echo tool
    server = MCPServer("echo-server")

    @server.tool()
    def echo(message: str) -> dict:
        return {"echo": message}

    # Setup client with real transport
    client_config = {
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "echo_server"]
    }

    client = MCPClient(client_config)

    async with client:
        result = await client.call_tool("echo", {"message": "hello"})
        assert result["echo"] == "hello"

@pytest.mark.integration
async def test_error_handling():
    """Test error propagation and handling."""
    server = MCPServer("error-test")

    @server.tool()
    def failing_tool() -> dict:
        raise ValueError("Expected error")

    client = MCPClient({"transport": "stdio"})

    with pytest.raises(MCPError) as exc_info:
        await client.call_tool("failing_tool", {})

    assert exc_info.value.error_code == MCPErrorCode.TOOL_ERROR
```

### E2E Testing
```python
@pytest.mark.e2e
@pytest.mark.requires_docker
async def test_llm_mcp_tool_execution():
    """Test LLM agent with MCP tool execution."""
    from kailash.nodes.ai.llm_agent import LLMAgentNode

    # Real LLM with MCP server
    agent = "LLMAgentNode"
    result = await agent.run(
        provider="ollama",
        model="llama3.2:1b",
        messages=[{"role": "user", "content": "Use MCP tools"}],
        mcp_servers=[{
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "kailash.mcp_server.test_server"]
        }]
    )

    assert result["status"] == "success"
```

### Running MCP Tests
```bash
# Run all MCP unit tests (2 seconds)
pytest tests/unit/mcp_server/ -v

# Run specific component tests
pytest tests/unit/mcp_server/test_auth.py      # 33 auth tests
pytest tests/unit/mcp_server/test_server.py    # 97 server tests
pytest tests/unit/mcp_server/test_client.py    # 77 client tests
pytest tests/unit/mcp_server/test_errors.py    # 88 error tests

# Run integration tests with Docker
pytest tests/integration/mcp/ -v

# Run E2E tests
pytest tests/e2e/test_mcp_tool_execution_scenarios.py -v
```

### Testing Best Practices
1. **NO MOCKING in Integration/E2E** - Use real Docker services
2. **Fast Unit Tests** - All tests complete in <1 second
3. **Comprehensive Coverage** - Test all public APIs
4. **Real Implementation** - Tests match actual usage patterns
5. **Security Testing** - Auth framework has dedicated test suite

For detailed testing guide, see [MCP Testing Best Practices](../testing/MCP_TESTING_BEST_PRACTICES.md)

## 📚 API Reference

For complete API documentation, see:
- **[MCP Server API](mcp-server-api.md)** - Complete server implementation
- **[MCP Client API](mcp-client-api.md)** - Client configuration and usage
- **[Authentication](authentication.md)** - Auth providers and security
- **[Service Discovery](service-discovery.md)** - Discovery and load balancing
- **[Advanced Features](advanced-features.md)** - Progress, validation, streaming
- **[Transport Layer](transports.md)** - STDIO, HTTP, SSE, WebSocket

## 🔗 Integration Guides

- **[FastAPI Integration](integrations/fastapi.md)** - Embed MCP in FastAPI apps
- **[Django Integration](integrations/django.md)** - Django MCP middleware
- **[Docker Deployment](integrations/docker.md)** - Containerized MCP servers
- **[Kubernetes](integrations/kubernetes.md)** - K8s service discovery

## 🎯 Best Practices

### Production Deployment
1. **Use authentication** - Always enable auth for production servers
2. **Enable metrics** - Monitor performance and usage
3. **Implement rate limiting** - Protect against abuse
4. **Use service discovery** - Enable automatic server discovery
5. **Handle errors gracefully** - Use structured error codes
6. **Cache appropriately** - Cache expensive operations
7. **Monitor health** - Use health checks and circuit breakers

### Performance Optimization
1. **Cache frequently used data** - Use built-in caching
2. **Batch operations** - Combine multiple requests
3. **Use async/await** - Leverage async capabilities
4. **Connection pooling** - Reuse connections
5. **Load balancing** - Distribute load across servers

### Security Guidelines
1. **Validate all inputs** - Use schema validation
2. **Implement proper authentication** - Use JWT or API keys
3. **Use HTTPS in production** - Encrypt all communications
4. **Rate limit requests** - Prevent DoS attacks
5. **Audit access** - Log all authenticated requests
6. **Keep dependencies updated** - Regular security updates

## 🐛 Troubleshooting

### Common Issues

**Server won't start:**
```bash
# Check if port is available
lsof -i :8080

# Check server logs
python -m my_server --log-level DEBUG
```

**Client can't connect:**
```bash
# Test server connectivity
curl http://localhost:8080/health

# Check client configuration
python -c "from kailash.mcp_server import MCPClient; print(MCPClient(config).validate())"
```

**WebSocket connection issues:**
```python
# Test WebSocket connectivity
import asyncio
import websockets

async def test_websocket():
    try:
        async with websockets.connect("ws://localhost:3001") as ws:
            await ws.send('{"method": "ping"}')
            response = await ws.recv()
            print(f"WebSocket working: {response}")
    except Exception as e:
        print(f"WebSocket failed: {e}")

asyncio.run(test_websocket())
```

**Connection pool debugging:**
```python
# Debug connection pool state
client = MCPClient(enable_metrics=True)
print(f"Active pools: {len(client._websocket_pools)}")
print(f"Pool config: {client.connection_pool_config}")

# Clear connection pool if needed
await client._clear_connection_pools()
```

**Authentication failures:**
```python
# Debug auth headers
print(client.auth_provider.get_headers())

# Test auth manually
from kailash.mcp_server.auth import APIKeyAuth
auth = APIKeyAuth({"test": {"permissions": ["tools"]}})
result = auth.authenticate({"api_key": "test"})
print(result)
```

For more troubleshooting, see **[Troubleshooting Guide](troubleshooting.md)**.

---

**Next Steps:**
- Try the [MCP Tutorial](tutorial.md) for hands-on learning
- Explore [Example Applications](../patterns/mcp-examples/)
- Check out [Production Patterns](../production-patterns/mcp-deployment.md)
