# Kailash SDK MCP Implementation Analysis for Kaizen Integration

**Generated**: 2025-10-04
**Purpose**: Comprehensive analysis of Kailash SDK's production-ready MCP implementation to guide Kaizen integration

---

## Executive Summary

Kailash SDK has a **complete, production-ready MCP implementation** in `src/kailash/mcp_server/` with enterprise-grade features. This analysis provides patterns and code examples for properly integrating MCP into Kaizen's agent examples.

**Key Finding**: Kaizen's current partial MCP implementation in `src/kaizen/mcp/` should leverage Kailash's proven patterns rather than reimplementing them.

---

## 1. MCP Architecture Overview

### Core Components Location

```

├── __init__.py          # Main exports and public API
├── client.py            # MCPClient - Enhanced client with auth, retry, pooling
├── server.py            # MCPServer, MCPServerBase, SimpleMCPServer
├── discovery.py         # ServiceRegistry, NetworkDiscovery, ServiceMesh
├── auth.py              # APIKeyAuth, JWTAuth, BearerTokenAuth, OAuth
├── errors.py            # MCPError hierarchy with structured error codes
├── protocol.py          # Complete MCP protocol implementation
├── transports.py        # Multiple transport support (STDIO, HTTP, SSE, WebSocket)
├── advanced_features.py # Streaming, progress, cancellation
├── oauth.py             # OAuth 2.1 implementation
└── utils/               # Cache, config, metrics, formatters
```

### Key Documentation

- **Quick Start**: `sdk-users/1-quickstart/mcp-quickstart.md`
- **Integration Guide**: `sdk-users/2-core-concepts/cheatsheet/025-mcp-integration.md`
- **Development Guide**: `sdk-users/3-development/17-mcp-development-guide.md`
- **Examples**: See inline code examples throughout this guide

---

## 2. MCP Client Implementation Patterns

### 2.1 Basic Client Creation

```python
from kailash_mcp import MCPClient

# Minimal client
client = MCPClient()

# Client with authentication
from kailash_mcp.auth import APIKeyAuth

auth = APIKeyAuth({"user1": "secret-key"})
client = MCPClient(
    auth_provider=auth,
    enable_metrics=True,
    retry_strategy="exponential"
)
```

**File**: `

### 2.2 Tool Discovery Pattern

```python
# Discover tools from MCP server
server_config = {
    "name": "weather-server",
    "transport": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-filesystem", "/data"]
}

# Discover available tools
tools = await client.discover_tools(
    server_config,
    force_refresh=False,  # Use cache if available
    timeout=30.0
)

# Tools are cached automatically
for tool in tools:
    print(f"Tool: {tool['name']}")
    print(f"  Description: {tool['description']}")
    print(f"  Parameters: {tool['parameters']}")
```

**File**: `

### 2.3 Tool Execution Pattern

```python
# Execute a tool
result = await client.call_tool(
    server_config,
    tool_name="search",
    arguments={"query": "AI research"},
    timeout=60.0
)

# Check result
if result["success"]:
    print(f"Content: {result['content']}")
else:
    print(f"Error: {result['error']}")
```

**File**: `

### 2.4 Multi-Transport Support

```python
# STDIO Transport
stdio_config = {
    "transport": "stdio",
    "command": "python",
    "args": ["-m", "mcp_server"],
    "env": {"API_KEY": "secret"}
}

# HTTP Transport
http_config = {
    "transport": "http",
    "url": "http://localhost:8080",
    "headers": {"Authorization": "Bearer token123"}
}

# WebSocket Transport with Connection Pooling
websocket_config = {
    "transport": "websocket",
    "url": "ws://localhost:3001/mcp",
    "connection_pool_config": {
        "max_connections": 10,
        "connection_timeout": 30.0,
        "ping_interval": 20.0
    }
}

# Client automatically detects and uses appropriate transport
tools = await client.discover_tools(stdio_config)
result = await client.call_tool(http_config, "search", {"q": "test"})
```

**File**: `

### 2.5 Authentication Patterns

```python
# Extract credentials from server config
def _extract_credentials(self, server_config):
    """Extract credentials for auth manager."""
    auth_config = server_config.get("auth", {})

    if auth_config.get("type") == "api_key":
        return {"api_key": auth_config.get("key")}
    elif auth_config.get("type") == "bearer":
        return {"token": auth_config.get("token")}
    elif auth_config.get("type") == "basic":
        return {
            "username": auth_config.get("username"),
            "password": auth_config.get("password")
        }

    return {}
```

**File**: `

### 2.6 WebSocket Connection Pooling

```python
# Connection pooling for WebSocket (production feature)
client = MCPClient(
    connection_pool_config={
        "enable_connection_reuse": True,
        "max_connections": 10,
        "max_idle_time": 60  # seconds
    }
)

# Connections are automatically pooled and reused
async with client:
    # First call creates connection
    result1 = await client.call_tool(ws_config, "tool1", {})

    # Second call reuses connection
    result2 = await client.call_tool(ws_config, "tool2", {})

    # Check pooling metrics
    metrics = client.get_metrics()
    print(f"Pool hits: {metrics['websocket_pool_hits']}")
    print(f"Pool misses: {metrics['websocket_pool_misses']}")
```

**File**: `

---

## 3. MCP Server Implementation Patterns

### 3.1 Simple Server (Prototyping)

```python
from kailash_mcp import SimpleMCPServer

# Lightweight server for development
server = SimpleMCPServer("my-tools")

@server.tool("Add two numbers")
def add_numbers(a: int, b: int) -> dict:
    """Add two numbers together."""
    return {"result": a + b}

@server.tool("Get weather")
def get_weather(city: str) -> dict:
    """Get weather for a city."""
    return {
        "city": city,
        "temperature": 72,
        "conditions": "sunny"
    }

# Run the server (no configuration needed)
if __name__ == "__main__":
    server.run()
```

**File**: `

### 3.2 Production Server with Features

```python
from kailash_mcp import MCPServer
from kailash_mcp.auth import APIKeyAuth

# Create production server
auth = APIKeyAuth({
    "admin_key": {"permissions": ["read", "write", "admin"]},
    "read_key": {"permissions": ["read"]}
})

server = MCPServer(
    "my-server-prod",
    enable_cache=True,
    enable_metrics=True,
    auth_provider=auth,
    rate_limit_config={"requests_per_minute": 100},
    circuit_breaker_config={"failure_threshold": 5}
)

# Add production tools with caching
@server.tool(cache_ttl=300)  # Cache for 5 minutes
async def expensive_operation(data: str) -> dict:
    """Cached operation."""
    return {"processed": data}

# Run the server
if __name__ == "__main__":
    server.run()
```

**File**: `

### 3.3 Server Base Class Pattern

```python
from kailash_mcp import MCPServerBase

class MyCustomServer(MCPServerBase):
    """Custom MCP server with specific tools."""

    def setup(self):
        """Setup server tools, resources, and prompts."""

        @self.add_tool()
        def search(query: str) -> str:
            """Search for information."""
            return f"Results for: {query}"

        @self.add_resource("data://schema")
        def get_schema():
            """Get database schema."""
            return {"tables": ["users", "orders"]}

        @self.add_prompt("analyze")
        def analyze_prompt(data: str) -> str:
            """Generate analysis prompt."""
            return f"Analyze this data: {data}"

# Use the server
server = MyCustomServer("my-server", port=8080)
server.start()
```

**File**: `

### 3.4 WebSocket Server Transport

```python
from kailash_mcp import MCPServer
from kailash_mcp.transports import WebSocketTransport

# Create WebSocket server
server = MCPServer(
    "websocket-server",
    transport="websocket",
    websocket_host="0.0.0.0",
    websocket_port=3001,
    enable_websocket_compression=True,
    compression_threshold=1024  # Compress messages > 1KB
)

@server.tool()
async def process_data(data: dict) -> dict:
    """Process data via WebSocket."""
    return {"processed": True, "data": data}

# Run WebSocket server
if __name__ == "__main__":
    server.run()
```

**File**: `

---

## 4. Service Discovery Patterns

### 4.1 Server Registration

```python
from kailash_mcp import ServiceRegistry, ServerInfo

# Create registry
registry = ServiceRegistry()

# Register server
server_info = ServerInfo(
    name="weather-server",
    transport="http",
    url="http://localhost:8080",
    capabilities=["weather.get", "weather.forecast"],
    metadata={"version": "1.0.0", "author": "team"}
)

await registry.register_server(server_info)
```

**File**: `

### 4.2 Server Discovery

```python
# Discover servers by capability
servers = await registry.discover_servers(capability="weather.get")

for server in servers:
    print(f"Server: {server.name}")
    print(f"  URL: {server.url}")
    print(f"  Capabilities: {server.capabilities}")
    print(f"  Health: {server.health_status}")
```

**File**: `

### 4.3 Auto-Discovery with Registration

```python
from kailash_mcp import MCPServer, enable_auto_discovery

# Create server
server = MCPServer("my-server")

# Add tools
@server.tool()
async def my_tool(data: str) -> dict:
    return {"result": data}

# Enable auto-discovery
registrar = enable_auto_discovery(
    server,
    enable_network_discovery=True,  # UDP broadcast
    registry_path="mcp_registry.json"
)

# Start with automatic registration
registrar.start_with_registration()
```

**File**: `

### 4.4 Health Checking

```python
from kailash_mcp.discovery import HealthChecker

# Create health checker
health_checker = HealthChecker(registry)

# Check server health
health_status = await health_checker.check_server(server_info)

if health_status["status"] == "healthy":
    print(f"Server is healthy (response time: {health_status['response_time']}ms)")
else:
    print(f"Server is unhealthy: {health_status['error']}")
```

**Reference**: Discovery module includes `HealthChecker` class for automated health monitoring

---

## 5. Authentication & Authorization Patterns

### 5.1 API Key Authentication

```python
from kailash_mcp.auth import APIKeyAuth

# Simple API key auth
auth = APIKeyAuth(["secret-key-1", "secret-key-2"])

# API keys with permissions
auth = APIKeyAuth({
    "admin_key": {"permissions": ["read", "write", "admin"]},
    "read_key": {"permissions": ["read"]},
    "write_key": {"permissions": ["read", "write"]}
})

# Use with server
server = MCPServer("secure-server", auth_provider=auth)

# Use with client
client = MCPClient(auth_provider=auth)
```

**File**: `

### 5.2 JWT Authentication

```python
from kailash_mcp.auth import JWTAuth

# Create JWT auth provider
auth = JWTAuth(
    secret="my-jwt-secret",
    algorithm="HS256",
    expiration=3600  # 1 hour
)

# Create token for user
token = auth.create_token({
    "user": "alice",
    "permissions": ["read", "write"]
})

# Client uses token
client = MCPClient(auth_provider=auth)
```

**File**: `

### 5.3 Bearer Token Authentication

```python
from kailash_mcp.auth import BearerTokenAuth

# Simple bearer tokens
auth = BearerTokenAuth(tokens=["bearer-token-123"])

# Bearer tokens with permissions
auth = BearerTokenAuth(tokens={
    "token-admin": {"permissions": ["read", "write", "admin"]},
    "token-user": {"permissions": ["read"]}
})

# JWT validation
auth = BearerTokenAuth(
    validate_jwt=True,
    jwt_secret="my-secret",
    jwt_algorithm="HS256"
)
```

**File**: `

### 5.4 Permission Management

```python
from kailash_mcp.auth import PermissionManager

# Create permission manager
perm_manager = PermissionManager()

# Define permissions
perm_manager.add_permission("tools.execute")
perm_manager.add_permission("tools.admin")
perm_manager.add_permission("resources.read")
perm_manager.add_permission("resources.write")

# Check permissions
user_perms = ["tools.execute", "resources.read"]
can_execute = perm_manager.has_permission(user_perms, "tools.execute")  # True
can_admin = perm_manager.has_permission(user_perms, "tools.admin")  # False
```

**Reference**: `PermissionManager` class in auth module

### 5.5 Rate Limiting

```python
from kailash_mcp.auth import RateLimiter

# Create rate limiter
rate_limiter = RateLimiter(
    requests_per_minute=100,
    burst_size=10
)

# Check rate limit
user_id = "user123"
allowed = rate_limiter.check_rate_limit(user_id)

if not allowed:
    raise RateLimitError("Rate limit exceeded", retry_after=60)
```

**Reference**: `RateLimiter` class in auth module

---

## 6. Integration with LLM Agents

### 6.1 Basic LLM Agent with MCP

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {})

# Execute with MCP servers
runtime = LocalRuntime()
results, run_id = runtime.execute(
    workflow.build(),
    parameters={
        "agent": {
            "provider": "ollama",
            "model": "llama3.2",
            "messages": [
                {"role": "user", "content": "What tools are available?"}
            ],
            "mcp_servers": [
                {
                    "name": "filesystem",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["@modelcontextprotocol/server-filesystem", "/data"]
                }
            ],
            "auto_discover_tools": True,
            "auto_execute_tools": True
        }
    }
)

# Check results
if results["agent"]["success"]:
    print(results["agent"]["response"])
    tools = results["agent"]["context"].get("tools_available", [])
    print(f"Discovered {len(tools)} tools")
```

**Reference**: See Section 6.1 above for the complete basic LLM agent with MCP pattern

### 6.2 Multi-Tool Agent Pattern

```python
# Agent using multiple MCP servers
results, run_id = runtime.execute(
    workflow.build(),
    parameters={
        "multi_agent": {
            "provider": "openai",
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "Get weather and save to file"}
            ],
            "mcp_servers": [
                {
                    "name": "weather-service",
                    "transport": "http",
                    "url": "http://localhost:8081",
                    "headers": {"API-Key": "demo-key"}
                },
                {
                    "name": "file-system",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["@modelcontextprotocol/server-filesystem", "./output"]
                }
            ],
            "auto_discover_tools": True,
            "auto_execute_tools": True,
            "tool_discovery_config": {
                "cache_discoveries": True,
                "parallel_discovery": True
            },
            "tool_execution_config": {
                "max_rounds": 5,
                "parallel": True,
                "timeout": 120
            }
        }
    }
)
```

**Reference**: See Section 6.2 above for the complete multi-tool agent pattern

### 6.3 Tool Execution Configuration

```python
# Advanced tool execution settings
tool_execution_config = {
    "max_rounds": 3,           # Maximum tool execution rounds
    "timeout": 120,            # Total timeout in seconds
    "parallel": True,          # Allow parallel tool execution
    "retry_failed": True,      # Retry failed tool calls
    "max_retries": 2,          # Maximum retries per tool
    "log_executions": True     # Log all tool executions
}

tool_discovery_config = {
    "max_tools": 50,           # Limit number of tools
    "cache_discoveries": True,  # Cache discovered tools
    "cache_ttl": 3600,         # Cache time-to-live
    "timeout": 30,             # Discovery timeout
    "parallel_discovery": True  # Discover from multiple servers in parallel
}
```

**File**: `

---

## 7. Error Handling & Retry Patterns

### 7.1 Error Hierarchy

```python
from kailash_mcp.errors import (
    MCPError,                    # Base error
    AuthenticationError,         # Auth failures
    AuthorizationError,          # Permission denied
    RateLimitError,             # Rate limit exceeded
    ToolError,                  # Tool execution errors
    ResourceError,              # Resource access errors
    TransportError,             # Transport failures
    ServiceDiscoveryError,      # Discovery failures
    ValidationError             # Input validation errors
)

# Error codes
from kailash_mcp.errors import MCPErrorCode

MCPErrorCode.AUTHENTICATION_FAILED
MCPErrorCode.AUTHORIZATION_FAILED
MCPErrorCode.RATE_LIMITED
MCPErrorCode.TOOL_NOT_FOUND
MCPErrorCode.TOOL_EXECUTION_FAILED
MCPErrorCode.RESOURCE_NOT_FOUND
MCPErrorCode.TRANSPORT_ERROR
```

**File**: `

### 7.2 Retry Strategies

```python
from kailash_mcp.errors import (
    ExponentialBackoffRetry,
    CircuitBreakerRetry,
    RetryableOperation
)

# Exponential backoff
retry_strategy = ExponentialBackoffRetry(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0
)

# Circuit breaker
circuit_breaker = CircuitBreakerRetry(
    failure_threshold=5,
    timeout=60.0,
    half_open_max_calls=3
)

# Use with client
client = MCPClient(retry_strategy=retry_strategy)

# Or use directly
operation = RetryableOperation(retry_strategy)
result = await operation.execute(async_function)
```

**File**: `

### 7.3 Error Aggregation

```python
from kailash_mcp.errors import ErrorAggregator

# Collect errors from multiple operations
aggregator = ErrorAggregator()

try:
    result1 = await operation1()
except Exception as e:
    aggregator.add_error("operation1", e)

try:
    result2 = await operation2()
except Exception as e:
    aggregator.add_error("operation2", e)

# Check if any errors occurred
if aggregator.has_errors():
    summary = aggregator.get_error_summary()
    print(f"Errors: {summary['total_errors']}")
    for error in summary['errors']:
        print(f"  {error['operation']}: {error['message']}")
```

**Reference**: `ErrorAggregator` class in errors module

---

## 8. Testing Patterns

### 8.1 Unit Test Pattern (Tier 1)

```python
import pytest
from kailash_mcp import MCPClient
from kailash_mcp.auth import APIKeyAuth

def test_mcp_client_initialization():
    """Test client initialization."""
    auth = APIKeyAuth(["test-key"])
    client = MCPClient(
        auth_provider=auth,
        enable_metrics=True,
        retry_strategy="exponential"
    )

    assert client.auth_provider is auth
    assert client.enable_metrics is True
    assert client.retry_operation is not None

@pytest.mark.asyncio
async def test_tool_discovery():
    """Test tool discovery with mock server."""
    client = MCPClient()

    # Mock server config
    server_config = {
        "transport": "stdio",
        "command": "echo",
        "args": ["test"]
    }

    # Test would use mocked responses in unit tests
    # Real server tests are in integration tests
```

**File**: `

### 8.2 Integration Test Pattern (Tier 2)

```python
import pytest
from kailash_mcp import MCPClient, MCPServer

@pytest.mark.integration
async def test_real_mcp_server_communication():
    """Test with real MCP server running."""
    # Start real MCP server (in Docker or subprocess)
    server = MCPServer("test-server")

    @server.tool()
    async def add_numbers(a: int, b: int) -> dict:
        return {"result": a + b}

    # Start server in background
    # ... server startup code ...

    # Create client and test
    client = MCPClient()
    server_config = {
        "transport": "http",
        "url": "http://localhost:8080"
    }

    # Discover tools
    tools = await client.discover_tools(server_config)
    assert len(tools) > 0
    assert any(t["name"] == "add_numbers" for t in tools)

    # Call tool
    result = await client.call_tool(
        server_config,
        "add_numbers",
        {"a": 5, "b": 3}
    )
    assert result["success"] is True
    assert result["result"]["result"] == 8
```

**File**: `

### 8.3 E2E Test Pattern (Tier 3)

```python
@pytest.mark.e2e
async def test_llm_agent_with_mcp_tools():
    """End-to-end test: LLM agent using MCP tools."""
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime.local import LocalRuntime

    # Create workflow
    workflow = WorkflowBuilder()
    workflow.add_node("LLMAgentNode", "agent", {})

    # Execute with real MCP server
    runtime = LocalRuntime()
    results, run_id = runtime.execute(
        workflow.build(),
        parameters={
            "agent": {
                "provider": "ollama",
                "model": "llama3.2",
                "messages": [{"role": "user", "content": "Add 5 and 3"}],
                "mcp_servers": [{
                    "name": "math-tools",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "test_mcp_server"]
                }],
                "auto_discover_tools": True,
                "auto_execute_tools": True
            }
        }
    )

    assert results["agent"]["success"] is True
    assert "8" in results["agent"]["response"]
```

**Reference**: E2E tests in `tests/e2e/mcp_server/`

---

## 9. Production Deployment Patterns

### 9.1 Server Configuration

```python
from kailash_mcp import MCPServer
from kailash_mcp.auth import JWTAuth

# Production server setup
auth = JWTAuth(
    secret=os.getenv("JWT_SECRET"),
    expiration=3600
)

server = MCPServer(
    "production-server",
    # Transport
    transport="websocket",
    websocket_host="0.0.0.0",
    websocket_port=3001,

    # Security
    auth_provider=auth,
    rate_limit_config={
        "requests_per_minute": 1000,
        "burst_size": 100
    },

    # Reliability
    circuit_breaker_config={
        "failure_threshold": 10,
        "timeout": 60.0
    },

    # Performance
    enable_cache=True,
    cache_backend="redis",
    cache_config={
        "redis_url": os.getenv("REDIS_URL"),
        "prefix": "mcp:"
    },

    # Monitoring
    enable_metrics=True,
    enable_monitoring=True,

    # WebSocket compression
    enable_websocket_compression=True,
    compression_threshold=1024,
    compression_level=6
)

# Register tools
@server.tool(cache_ttl=300)
async def expensive_operation(data: str) -> dict:
    """Cached expensive operation."""
    return {"result": process(data)}

# Run server
if __name__ == "__main__":
    server.run()
```

**File**: `

### 9.2 Client Configuration

```python
from kailash_mcp import MCPClient
from kailash_mcp.auth import JWTAuth

# Production client
auth = JWTAuth(secret=os.getenv("JWT_SECRET"))

client = MCPClient(
    # Authentication
    auth_provider=auth,

    # Reliability
    retry_strategy="circuit_breaker",
    circuit_breaker_config={
        "failure_threshold": 5,
        "timeout": 30.0
    },

    # Performance
    connection_pool_config={
        "enable_connection_reuse": True,
        "max_connections": 20,
        "max_idle_time": 60
    },

    # Monitoring
    enable_metrics=True,

    # Timeouts
    connection_timeout=30.0,
    transport_timeout=60.0
)
```

**Reference**: Client configuration options in `client.py` init method

### 9.3 Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Environment variables
ENV MCP_SERVER_NAME=production-server
ENV MCP_SERVER_PORT=3001
ENV JWT_SECRET=change-me-in-production

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:3001/health')"

# Run server
CMD ["python", "-m", "mcp_server"]
```

**Reference**: Docker deployment patterns in SDK documentation

---

## 10. Key Imports for Kaizen

### 10.1 Client-Side Imports

```python
# MCP Client
from kailash_mcp import MCPClient

# Authentication
from kailash_mcp.auth import (
    APIKeyAuth,
    BearerTokenAuth,
    JWTAuth
)

# Error Handling
from kailash_mcp.errors import (
    MCPError,
    AuthenticationError,
    ToolError,
    TransportError,
    ExponentialBackoffRetry,
    CircuitBreakerRetry
)

# Discovery
from kailash_mcp import (
    discover_mcp_servers,
    get_mcp_client
)
```

### 10.2 Server-Side Imports

```python
# MCP Server
from kailash_mcp import (
    MCPServer,           # Production server
    SimpleMCPServer,     # Prototyping server
    MCPServerBase        # Custom server base class
)

# Service Discovery
from kailash_mcp import (
    ServiceRegistry,
    ServerInfo,
    enable_auto_discovery
)

# Authentication
from kailash_mcp.auth import (
    AuthProvider,
    APIKeyAuth,
    JWTAuth,
    PermissionManager,
    RateLimiter
)
```

### 10.3 Workflow Integration Imports

```python
# Workflow components
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# LLM nodes with MCP support
from kailash.nodes.ai import LLMAgentNode

# No special imports needed - MCP is built into LLMAgentNode
```

---

## 11. Recommendations for Kaizen

### 11.1 Replace Partial Implementation

**Current**: Kaizen has partial/mocked MCP in `src/kaizen/mcp/`

**Recommended**: Leverage Kailash's production-ready implementation:

```python
# Instead of custom MCP client
from kaizen.mcp import MCPClient  # ❌ Partial implementation

# Use Kailash's proven implementation
from kailash_mcp import MCPClient  # ✅ Production-ready
```

### 11.2 Example Updates

Update Kaizen examples to use Kailash MCP patterns:

```python
# examples/5-mcp-integration/agent-as-client/workflow.py

from kailash_mcp import MCPClient
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def create_mcp_agent():
    """Create agent that uses MCP tools."""
    workflow = WorkflowBuilder()
    workflow.add_node("LLMAgentNode", "agent", {})

    runtime = LocalRuntime()
    results, _ = runtime.execute(
        workflow.build(),
        parameters={
            "agent": {
                "provider": "ollama",
                "model": "llama3.2",
                "messages": [
                    {"role": "user", "content": "Search for information"}
                ],
                "mcp_servers": [
                    {
                        "name": "search-tools",
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["@modelcontextprotocol/server-brave-search"]
                    }
                ],
                "auto_discover_tools": True,
                "auto_execute_tools": True
            }
        }
    )

    return results
```

### 11.3 Testing Strategy

Follow Kailash's 3-tier testing approach:

1. **Tier 1 (Unit)**: Test Kaizen-specific logic with mocked MCP
2. **Tier 2 (Integration)**: Test with real MCP servers in Docker
3. **Tier 3 (E2E)**: Test complete agent workflows with MCP

### 11.4 Documentation Updates

Update Kaizen's MCP documentation to reference Kailash patterns:

```markdown
# Kaizen MCP Integration

Kaizen leverages Kailash SDK's production-ready MCP implementation.

## Quick Start

See [Kailash MCP Quick Start](../../kailash_python_sdk/sdk-users/1-quickstart/mcp-quickstart.md)

## Patterns

- Client: Use `kailash_mcp.MCPClient`
- Server: Use `kailash_mcp.MCPServer`
- Auth: Use `kailash_mcp.auth` module
```

---

## 12. File Paths Reference

### Documentation

- **Quick Start**: `
- **Integration Guide**: `
- **Development Guide**: `
- **Enterprise Patterns**: `

### Source Code

- **Client**: `
- **Server**: `
- **Discovery**: `
- **Auth**: `
- **Errors**: `

### Examples

- **Simple Agent**: See Section 6.1 of this guide (Basic LLM Agent with MCP)
- **Multi-Tool Agent**: See Section 6.2 of this guide (Multi-Tool Agent Pattern)

### Tests

- **Unit Tests**: `
- **Integration Tests**: `
- **E2E Tests**: `

---

## 13. Next Steps for Kaizen Integration

1. **Remove partial MCP implementation** in `src/kaizen/mcp/`
2. **Update imports** in Kaizen examples to use `kailash_mcp`
3. **Add MCP examples** following Kailash patterns
4. **Implement tests** using 3-tier strategy
5. **Update documentation** to reference Kailash MCP docs

---

## Conclusion

Kailash SDK provides a comprehensive, production-ready MCP implementation with:

- ✅ Complete client/server implementation
- ✅ Multiple transport support (STDIO, HTTP, SSE, WebSocket)
- ✅ Enterprise auth (API Key, JWT, OAuth)
- ✅ Service discovery and health checking
- ✅ Connection pooling and retry logic
- ✅ Comprehensive error handling
- ✅ Full test coverage (407 tests)

**Recommendation**: Kaizen should leverage these proven patterns rather than reimplementing MCP functionality.
