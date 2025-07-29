# MCP (Model Context Protocol) Development Guide

## Overview

The Model Context Protocol (MCP) enables standardized communication between AI applications and external tools/resources. This guide covers how to build MCP-enabled applications using the Kailash SDK.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Core Concepts](#core-concepts)
3. [Building MCP Servers](#building-mcp-servers)
4. [Building MCP Clients](#building-mcp-clients)
5. [Integration with LLM Agents](#integration-with-llm-agents)
6. [Authentication & Security](#authentication--security)
7. [Service Discovery](#service-discovery)
8. [Production Deployment](#production-deployment)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

## Quick Start

### Basic MCP Server

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.mcp_server import MCPServer

# Create server
server = MCPServer("my-server")

# Register a tool
@server.tool()
def calculate_sum(a: int, b: int) -> dict:
    """Add two numbers."""
    return {"result": a + b}

# Start server
await server.start(host="0.0.0.0", port=8080)
```

### Basic MCP Client

```python
from kailash.mcp_server import MCPClient

# Create client
client = MCPClient("my-client")

# Connect and use
await client.connect("mcp://localhost:8080")
result = await client.call_tool("calculate_sum", {"a": 5, "b": 3})
print(result)  # {"result": 8}
```

### LLM Agent with MCP

```python
from kailash.nodes.ai import LLMAgentNode

# Create agent with MCP access
agent = LLMAgentNode(
    name="mcp_agent",
    mcp_servers=["mcp://localhost:8080"],
    enable_mcp=True
)

# Agent can now discover and use MCP tools
response = await agent.process({
    "messages": [{"role": "user", "content": "Calculate 15 + 27"}]
})
```

## Core Concepts

### Tools

Tools are functions that MCP servers expose for clients to call:

```python
@server.tool()
def get_weather(city: str, units: str = "celsius") -> dict:
    """Get weather for a city."""
    # Implementation
    return {"temperature": 22, "conditions": "sunny"}
```

### Resources

Resources provide access to data or configuration:

```python
@server.resource()
async def database_schema() -> dict:
    """Provide database schema information."""
    return {
        "tables": ["users", "orders"],
        "version": "1.0"
    }
```

### Authentication

MCP supports multiple authentication methods:

```python
from kailash.mcp_server.auth import BearerTokenAuth

auth = BearerTokenAuth(token="secret-token")
server = MCPServer("secure-server", auth=auth)
```

## Building MCP Servers

### Server Configuration

```python
from kailash.mcp_server import MCPServer, ServerConfig

config = ServerConfig(
    host="0.0.0.0",
    port=8080,
    enable_cache=True,
    cache_ttl=300,
    enable_metrics=True,
    max_connections=1000
)

server = MCPServer("production-server", config=config)
```

### Tool Registration Patterns

#### Simple Tools

```python
@server.tool()
def echo(message: str) -> dict:
    return {"echo": message}
```

#### Tools with Validation

```python
from pydantic import BaseModel, Field

class CalculationRequest(BaseModel):
    operation: str = Field(..., pattern="^(add|subtract|multiply|divide)$")
    a: float
    b: float

@server.tool()
def calculate(request: CalculationRequest) -> dict:
    operations = {
        "add": lambda: request.a + request.b,
        "subtract": lambda: request.a - request.b,
        "multiply": lambda: request.a * request.b,
        "divide": lambda: request.a / request.b if request.b != 0 else None
    }

    result = operations[request.operation]()
    if result is None:
        raise ValueError("Division by zero")

    return {"result": result, "operation": request.operation}
```

#### Tools with Caching

```python
@server.tool(cache_key="weather_{city}_{date}")
def get_weather_forecast(city: str, date: str) -> dict:
    """Get weather forecast with caching."""
    # Expensive API call cached by city and date
    forecast = fetch_weather_api(city, date)
    return forecast
```

#### Async Tools

```python
@server.tool()
async def fetch_data(url: str) -> dict:
    """Async tool for fetching data."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return {"status": response.status_code, "data": response.json()}
```

### Error Handling

```python
from kailash.mcp_server.errors import ToolExecutionError

@server.tool()
def divide(a: float, b: float) -> dict:
    if b == 0:
        raise ToolExecutionError(
            "Division by zero",
            details={"numerator": a, "denominator": b}
        )
    return {"result": a / b}
```

### Resource Management

```python
@server.resource()
async def system_status() -> dict:
    """Dynamic system status resource."""
    return {
        "cpu_usage": get_cpu_usage(),
        "memory": get_memory_info(),
        "uptime": get_uptime(),
        "timestamp": datetime.now().isoformat()
    }

@server.resource(cache_ttl=60)  # Cache for 60 seconds
async def configuration() -> dict:
    """Cached configuration resource."""
    return load_config()
```

## Building MCP Clients

### Client Configuration

```python
from kailash.mcp_server import MCPClient, ClientConfig

config = ClientConfig(
    timeout=30.0,
    retry_attempts=3,
    retry_delay=1.0,
    connection_pool_size=10
)

client = MCPClient("my-client", config=config)
```

### Connection Management

```python
# Basic connection
await client.connect("mcp://server:8080")

# With authentication
from kailash.mcp_server.auth import BearerTokenAuth

auth = BearerTokenAuth(token="client-token")
client = MCPClient("secure-client", auth=auth)
await client.connect("mcp://secure-server:8080")

# Connection with context manager
async with MCPClient("temp-client") as client:
    await client.connect("mcp://server:8080")
    result = await client.call_tool("echo", {"message": "test"})
```

### Tool Discovery and Usage

```python
# Discover available tools
tools = await client.list_tools()
for name, info in tools.items():
    print(f"{name}: {info['description']}")
    print(f"  Parameters: {info['parameters']}")

# Call tool with error handling
try:
    result = await client.call_tool("calculate", {
        "operation": "divide",
        "a": 10,
        "b": 2
    })
    print(f"Result: {result}")
except ToolNotFoundError:
    print("Tool not found")
except ToolExecutionError as e:
    print(f"Execution error: {e}")
```

### Resource Access

```python
# List resources
resources = await client.list_resources()

# Get specific resource
schema = await client.get_resource("database_schema")
print(f"Database schema: {schema}")
```

## Integration with LLM Agents

### Basic Agent with MCP

```python
from kailash.nodes.ai import LLMAgentNode
from kailash.core import LocalRuntime

runtime = LocalRuntime()

# Create agent with MCP
agent = LLMAgentNode(
    name="assistant",
    llm_config={
        "model": "gpt-4",
        "temperature": 0.7
    },
    mcp_servers=["mcp://tools-server:8080"],
    enable_mcp=True,
    system_prompt="You are a helpful assistant with access to calculation tools."
)

# Use agent
response = await agent.process({
    "messages": [
        {"role": "user", "content": "What's 15% of 200?"}
    ]
})
```

### Advanced Agent Patterns

#### Multi-Server Agent

```python
# Agent with multiple MCP servers
agent = LLMAgentNode(
    name="multi_server_agent",
    mcp_servers=[
        "mcp://math-server:8080",
        "mcp://data-server:8081",
        "mcp://file-server:8082"
    ],
    enable_mcp=True
)
```

#### Agent with Tool Preferences

```python
agent = LLMAgentNode(
    name="selective_agent",
    mcp_servers=["mcp://server:8080"],
    enable_mcp=True,
    tool_preferences={
        "preferred_tools": ["calculate", "analyze_data"],
        "blocked_tools": ["delete_file", "shutdown"]
    }
)
```

#### Workflow with MCP Agent

```python
from kailash.core import WorkflowBuilder

builder = WorkflowBuilder("mcp-workflow")

# Add MCP agent node
builder.add_node("agent", "LLMAgentNode", config={
    "mcp_servers": ["mcp://localhost:8080"],
    "enable_mcp": True
})

# Add result processor
builder.add_node("processor", "PythonCodeNode", config={
    "code": """
def process(data):
    # Process agent results
    return {"processed": data}
"""
})

# Connect nodes
builder.add_connection("agent", "response", "processor", "data")

workflow = builder.build()
result = await runtime.execute_workflow(workflow, input_data)
```

## Authentication & Security

### Server-Side Authentication

```python
# Bearer Token
from kailash.mcp_server.auth import BearerTokenAuth

auth = BearerTokenAuth(token="server-secret")
server = MCPServer("secure-server", auth=auth)

# API Key
from kailash.mcp_server.auth import APIKeyAuth

auth = APIKeyAuth(
    api_keys=["key1", "key2"],
    header_name="X-API-Key"
)
server = MCPServer("api-server", auth=auth)

# JWT
from kailash.mcp_server.auth import JWTAuth

auth = JWTAuth(
    secret_key="jwt-secret",
    algorithm="HS256",
    verify_exp=True
)
server = MCPServer("jwt-server", auth=auth)
```

### Custom Authentication

```python
from kailash.mcp_server.auth import AuthHandler

class CustomAuth(AuthHandler):
    async def authenticate(self, request):
        # Custom authentication logic
        api_key = request.headers.get("X-Custom-Key")

        if api_key and await self.validate_key(api_key):
            return {"user_id": "123", "permissions": ["read", "write"]}

        raise AuthenticationError("Invalid credentials")

    async def validate_key(self, key: str) -> bool:
        # Validate against database, etc.
        return key in valid_keys

server = MCPServer("custom-auth-server", auth=CustomAuth())
```

### Tool-Level Authorization

```python
@server.tool(requires_auth=True)
def sensitive_operation(data: dict, user_context: dict) -> dict:
    """Tool that requires authentication."""
    # user_context contains auth info
    if "admin" not in user_context.get("roles", []):
        raise PermissionError("Admin access required")

    # Perform sensitive operation
    return {"status": "completed"}
```

## Service Discovery

### Basic Service Registration

```python
from kailash.mcp_server.discovery import ServiceDiscovery

discovery = ServiceDiscovery()

# Register server
await discovery.register(
    name="my-mcp-server",
    host="localhost",
    port=8080,
    metadata={
        "version": "1.0",
        "capabilities": ["math", "data"]
    }
)
```

### Health Checks

```python
from kailash.mcp_server.discovery import HealthChecker

health_checker = HealthChecker(
    interval=30,  # Check every 30 seconds
    timeout=5,
    healthy_threshold=2,
    unhealthy_threshold=3
)

discovery = ServiceDiscovery(health_checker=health_checker)

# Register with health endpoint
await discovery.register(
    name="healthy-server",
    host="localhost",
    port=8080,
    health_endpoint="/health"
)
```

### Client Discovery

```python
# Discover all MCP servers
services = await discovery.discover(service_type="mcp-server")

# Filter by metadata
math_services = await discovery.discover(
    service_type="mcp-server",
    filters={"capabilities": "math"}
)

# Get only healthy services
healthy = await discovery.get_healthy_services("mcp-server")
```

## Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MCP_PORT=8080
ENV MCP_HOST=0.0.0.0

EXPOSE 8080

CMD ["python", "mcp_server.py"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      containers:
      - name: mcp-server
        image: myregistry/mcp-server:latest
        ports:
        - containerPort: 8080
        env:
        - name: MCP_AUTH_TOKEN
          valueFrom:
            secretKeyRef:
              name: mcp-secrets
              key: auth-token
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
```

### Load Balancing

```python
from kailash.mcp_server.load_balancer import LoadBalancer

# Create load balancer
lb = LoadBalancer(strategy="round-robin")

# Add backends
lb.add_backend("server1:8080")
lb.add_backend("server2:8080")
lb.add_backend("server3:8080")

# Client with load balancing
client = MCPClient("lb-client", load_balancer=lb)
```

### Monitoring

```python
# Enable metrics on server
server = MCPServer(
    "monitored-server",
    enable_metrics=True,
    metrics_config={
        "export_interval": 60,
        "include_latencies": True
    }
)

# Access metrics endpoint
# GET http://localhost:8080/metrics
```

## Best Practices

### 1. Tool Design

- Keep tools focused and single-purpose
- Use descriptive names and docstrings
- Validate inputs with Pydantic models
- Return consistent response formats

### 2. Error Handling

- Use specific error types (ToolExecutionError, ValidationError)
- Include helpful error messages and details
- Handle edge cases gracefully
- Log errors for debugging

### 3. Performance

- Use caching for expensive operations
- Implement connection pooling
- Set appropriate timeouts
- Monitor resource usage

### 4. Security

- Always use authentication in production
- Validate and sanitize inputs
- Implement rate limiting
- Use HTTPS/TLS
- Rotate secrets regularly

### 5. Testing

```python
import pytest
from kailash.mcp_server import MCPServer, MCPClient

@pytest.fixture
async def mcp_server():
    server = MCPServer("test-server")

    @server.tool()
    def add(a: int, b: int) -> dict:
        return {"result": a + b}

    await server.start(host="localhost", port=0)  # Random port
    yield server
    await server.shutdown()

async def test_mcp_tool(mcp_server):
    client = MCPClient("test-client")
    await client.connect(f"mcp://localhost:{mcp_server.port}")

    result = await client.call_tool("add", {"a": 5, "b": 3})
    assert result["result"] == 8
```

## Troubleshooting

### Common Issues

#### Connection Failed

```python
# Check server is running
try:
    await client.connect("mcp://localhost:8080")
except ConnectionError as e:
    print(f"Connection failed: {e}")
    # Check: Is server running? Correct port? Firewall?
```

#### Tool Not Found

```python
# List available tools
tools = await client.list_tools()
print(f"Available tools: {list(tools.keys())}")
```

#### Authentication Errors

```python
# Ensure client has correct auth
auth = BearerTokenAuth(token="correct-token")
client = MCPClient("client", auth=auth)
```

#### Performance Issues

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Monitor metrics
metrics = await client.call_tool("_metrics", {})
print(f"Server metrics: {metrics}")
```

### Debug Mode

```python
# Server with debug mode
server = MCPServer("debug-server", debug=True)

# Client with verbose logging
client = MCPClient("debug-client", verbose=True)
```

### Health Checks

```python
@server.tool()
def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }
```

## Example Applications

See the [MCP Tools Server](/apps/mcp_tools_server) example application for a complete implementation including:

- Multiple tool categories
- Production server setup
- Client examples
- Docker deployment
- Monitoring setup

## Next Steps

1. Explore [MCP Patterns](/sdk-users/patterns/12-mcp-patterns.md)
2. Check out example applications in `/apps/mcp_tools_server`
3. Review the [API Registry](/sdk-users/api-registry.yaml) for MCP components
4. Build your own MCP tools and servers!
