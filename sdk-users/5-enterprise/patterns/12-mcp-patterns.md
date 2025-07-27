# MCP (Model Context Protocol) Patterns

## Overview

The Model Context Protocol (MCP) enables standardized communication between AI applications and external tools/resources. This guide covers implementation patterns using Kailash SDK's MCP components.

## Table of Contents

1. [Basic MCP Server Setup](#basic-mcp-server-setup)
2. [MCP Tool Registration](#mcp-tool-registration)
3. [MCP Client Integration](#mcp-client-integration)
4. [Authentication Patterns](#authentication-patterns)
5. [Service Discovery](#service-discovery)
6. [Load Balancing and HA](#load-balancing-and-ha)
7. [Resource Management](#resource-management)
8. [Error Handling](#error-handling)
9. [Production Deployment](#production-deployment)
10. [Integration with LLM Agents](#integration-with-llm-agents)

## Basic MCP Server Setup

### Prototyping with SimpleMCPServer

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.mcp_server import SimpleMCPServer

# Create lightweight server for prototyping
server = SimpleMCPServer("my-prototype")

# Register a simple tool
@server.tool("Calculate sum")
def calculate_sum(a: int, b: int) -> dict:
    """Calculate the sum of two numbers."""
    return {"result": a + b}

# Start server (no configuration needed)
server.run()
```

### Production with MCPServer

```python
from kailash.mcp_server import MCPServer

# Create production server with features
server = MCPServer(
    "production-server",
    enable_cache=True,
    cache_ttl=300,
    enable_metrics=True,
    enable_http_transport=True,
    enable_monitoring=True
)

# Register production tool with caching
@server.tool(cache_ttl=600)
async def calculate_sum_cached(a: int, b: int) -> dict:
    """Calculate sum with caching."""
    return {"result": a + b}

# Start server
await server.start(host="0.0.0.0", port=8080)
```

### Server Type Selection

```python
# Choose server type based on use case
def choose_server_type(use_case: str):
    if use_case in ["prototype", "development", "learning"]:
        return SimpleMCPServer("dev-server")
    elif use_case in ["production", "enterprise"]:
        return MCPServer("prod-server", enable_cache=True, enable_metrics=True)
    elif use_case == "middleware":
        from kailash.middleware.mcp import MiddlewareMCPServer
        return MiddlewareMCPServer()
```

## MCP Tool Registration

### Basic Tool Registration

```python
@server.tool()
def get_weather(city: str) -> dict:
    """Get weather information for a city."""
    # Implementation
    return {"temperature": 72, "conditions": "sunny"}

@server.tool()
def process_data(data: list) -> dict:
    """Process data."""
    return {"processed": len(data)}
```

### Tool with Caching

```python
# Note: Cache configuration is done at server level
server = MCPServer("my-server", enable_cache=True, cache_ttl=300)

@server.tool()
def get_weather_cached(city: str) -> dict:
    """Get weather with caching."""
    # Expensive operation will be cached by the server
    return fetch_weather_data(city)
```

### Tool with Validation

```python
from pydantic import BaseModel

class WeatherRequest(BaseModel):
    city: str
    units: str = "fahrenheit"

@server.tool()
def get_weather_validated(request: WeatherRequest) -> dict:
    """Get weather with validated input."""
    return fetch_weather(request.city, request.units)
```

## MCP Client Integration

### Basic Client Usage

```python
from kailash.mcp_server import MCPClient

# Create client
client = MCPClient("my-client")

# Connect to server
await client.connect("mcp://localhost:8080")

# Call tool
result = await client.call_tool("calculate_sum", {"a": 5, "b": 3})
print(result)  # {"result": 8}

# Discover available tools
tools = await client.list_tools()
```

### Client with Authentication

```python
from kailash.mcp_server.auth import BearerTokenAuth

# Create client with auth
auth = BearerTokenAuth(token="my-secret-token")
client = MCPClient("secure-client", auth=auth)

await client.connect("mcp://secure-server:8080")
```

### Client with Retry Logic

```python
client = MCPClient(
    "resilient-client",
    retry_attempts=3,
    retry_delay=1.0,
    timeout=30.0
)

try:
    result = await client.call_tool("process_data", {"data": [1, 2, 3]})
except Exception as e:
    logger.error(f"Failed after retries: {e}")
```

## Authentication Patterns

### Bearer Token Authentication

```python
from kailash.mcp_server.auth import BearerTokenAuth

auth = BearerTokenAuth(tokens=["secret-token"])
server = MCPServer("secure-server", auth_provider=auth)
```

### API Key Authentication

```python
from kailash.mcp_server.auth import APIKeyAuth

auth = APIKeyAuth(keys=["key1", "key2"])
server = MCPServer("api-server", auth_provider=auth)
```

### JWT Authentication

```python
from kailash.mcp_server.auth import JWTAuth

auth = JWTAuth(
    secret="jwt-secret",
    algorithm="HS256",
    expiration=3600
)
server = MCPServer("jwt-server", auth_provider=auth)
```

### Custom Authentication

```python
from kailash.mcp_server.auth import AuthHandler

class CustomAuth(AuthHandler):
    async def authenticate(self, request):
        token = request.headers.get("Authorization")
        if token and await validate_custom_token(token):
            return {"user_id": "123"}
        raise AuthenticationError("Invalid token")

server = MCPServer("custom-auth-server", auth=CustomAuth())
```

## Service Discovery

### Basic Service Discovery

```python
from kailash.mcp_server.discovery import ServiceDiscovery

discovery = ServiceDiscovery()

# Register service
await discovery.register(
    name="my-mcp-server",
    host="localhost",
    port=8080,
    metadata={"version": "1.0", "region": "us-east"}
)

# Discover services
services = await discovery.discover(service_type="mcp-server")
```

### Service Discovery with Health Checks

```python
from kailash.mcp_server.discovery import ServiceDiscovery, HealthChecker

# Create health checker
health_checker = HealthChecker(
    interval=30,
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

### Filtered Discovery

```python
# Discover services with filters
services = await discovery.discover(
    service_type="mcp-server",
    filters={
        "region": "us-east",
        "version": "1.0"
    }
)

# Get healthy services only
healthy_services = await discovery.get_healthy_services("mcp-server")
```

## Load Balancing and HA

### Round-Robin Load Balancer

```python
from kailash.mcp_server.load_balancer import LoadBalancer

# Create load balancer
lb = LoadBalancer(strategy="round-robin")

# Add backend servers
lb.add_backend("server1:8080", weight=1)
lb.add_backend("server2:8080", weight=1)
lb.add_backend("server3:8080", weight=2)  # Higher weight

# Client with load balancer
client = MCPClient("lb-client", load_balancer=lb)
```

### Least Connections Strategy

```python
lb = LoadBalancer(
    strategy="least-connections",
    health_check_interval=30
)

# Add backends with health checks
for i in range(3):
    lb.add_backend(
        f"server{i}:8080",
        health_check_path="/health"
    )
```

### Failover Configuration

```python
from kailash.mcp_server.load_balancer import FailoverConfig

failover = FailoverConfig(
    primary="server1:8080",
    secondaries=["server2:8080", "server3:8080"],
    check_interval=10,
    failure_threshold=3
)

client = MCPClient("ha-client", failover=failover)
```

## Resource Management

### Basic Resource Registration

```python
@server.resource()
async def get_database_schema():
    """Provide database schema as a resource."""
    return {
        "tables": ["users", "orders", "products"],
        "version": "1.0"
    }

@server.resource(name="config")
async def get_configuration():
    """Provide configuration resource."""
    return load_config()
```

### Dynamic Resources

```python
@server.resource()
async def get_file_list(directory: str = "/data"):
    """Provide dynamic file listing."""
    files = []
    for file in Path(directory).iterdir():
        files.append({
            "name": file.name,
            "size": file.stat().st_size,
            "modified": file.stat().st_mtime
        })
    return {"files": files}
```

### Resource with Access Control

```python
@server.resource(requires_auth=True)
async def get_sensitive_data(user_context):
    """Resource that requires authentication."""
    if user_context.get("role") != "admin":
        raise PermissionError("Admin access required")
    return load_sensitive_data()
```

## Error Handling

### Server Error Handling

```python
from kailash.mcp_server.errors import MCPError, ToolExecutionError

@server.tool()
def risky_operation(data: dict) -> dict:
    try:
        result = process_data(data)
        return {"success": True, "result": result}
    except ValueError as e:
        raise ToolExecutionError(f"Invalid data: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise MCPError("Internal server error", code=500)
```

### Client Error Handling

```python
from kailash.mcp_server.errors import (
    ConnectionError,
    AuthenticationError,
    ToolNotFoundError
)

try:
    await client.connect("mcp://server:8080")
    result = await client.call_tool("process", {"data": [1, 2, 3]})
except ConnectionError:
    logger.error("Failed to connect to MCP server")
except AuthenticationError:
    logger.error("Authentication failed")
except ToolNotFoundError as e:
    logger.error(f"Tool not found: {e.tool_name}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

### Graceful Degradation

```python
class ResilientMCPClient:
    def __init__(self, primary_url, fallback_url=None):
        self.primary = MCPClient("primary")
        self.fallback = MCPClient("fallback") if fallback_url else None
        self.primary_url = primary_url
        self.fallback_url = fallback_url

    async def call_tool_safe(self, tool_name, params):
        try:
            await self.primary.connect(self.primary_url)
            return await self.primary.call_tool(tool_name, params)
        except Exception as e:
            if self.fallback:
                logger.warning(f"Primary failed, using fallback: {e}")
                await self.fallback.connect(self.fallback_url)
                return await self.fallback.call_tool(tool_name, params)
            raise
```

## Production Deployment

### Production Server Configuration

```python
from kailash.mcp_server import MCPServer, ProductionConfig

config = ProductionConfig(
    # Server settings
    host="0.0.0.0",
    port=8080,
    workers=4,

    # Performance
    enable_cache=True,
    cache_ttl=300,
    max_connections=1000,

    # Security
    enable_auth=True,
    auth_type="jwt",
    tls_enabled=True,
    tls_cert_path="/certs/server.crt",
    tls_key_path="/certs/server.key",

    # Monitoring
    enable_metrics=True,
    enable_tracing=True,
    log_level="INFO"
)

server = MCPServer("production-server", config=config)
```

### Deployment with Docker

```python
# docker_mcp_server.py
import os
from kailash.mcp_server import MCPServer

server = MCPServer(
    "docker-server",
    config={
        "host": "0.0.0.0",
        "port": int(os.getenv("MCP_PORT", 8080)),
        "auth_token": os.getenv("MCP_AUTH_TOKEN"),
        "database_url": os.getenv("DATABASE_URL")
    }
)

# Register tools
@server.tool()
def health_check() -> dict:
    return {"status": "healthy", "timestamp": time.time()}

if __name__ == "__main__":
    import asyncio
    asyncio.run(server.start())
```

### Kubernetes Deployment

```yaml
# mcp-server-deployment.yaml
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
        - name: MCP_PORT
          value: "8080"
        - name: MCP_AUTH_TOKEN
          valueFrom:
            secretKeyRef:
              name: mcp-secrets
              key: auth-token
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
```

## Integration with LLM Agents

### LLM Agent with MCP Tools

```python
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Create runtime
runtime = LocalRuntime()

# Create LLM agent with MCP integration
agent_config = {
    "name": "mcp_agent",
    "mcp_servers": [
        "mcp://tools-server:8080",
        "mcp://data-server:8081"
    ],
    "llm_config": {
        "model": "gpt-4",
        "temperature": 0.7
    }
}

# Create workflow with MCP-enabled agent
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "mcp_agent", agent_config)

# Execute workflow
results, run_id = await runtime.execute_async(workflow.build(), parameters={
    "mcp_agent": {
        "messages": [{
            "role": "user",
            "content": "Calculate the sum of 15 and 27"
        }]
    }
})

response = results["mcp_agent"]["result"]
```

### Workflow with MCP Integration

```python
from kailash.workflow.builder import WorkflowBuilder

# Create workflow with MCP tools
builder = WorkflowBuilder()

# Add MCP-enabled agent
builder.add_node("LLMAgentNode", "agent", {
    "mcp_servers": ["mcp://localhost:8080"],
    "enable_mcp": True
})

# Add data processor that uses MCP resources
builder.add_node("PythonCodeNode", "processor", {
    "code": """
# Access MCP resources from parameters
mcp_data = parameters.get('mcp_data', {})
schema = mcp_data.get('database_schema', {})

# Process with schema
result = {"processed": True, "schema": schema}
"""
})

# Connect nodes with proper 4-parameter syntax
builder.add_connection("agent", "result", "processor", "mcp_data")

workflow = builder.build()
```

### Advanced MCP Agent Pattern

```python
class MCPAgentOrchestrator:
    """Orchestrate multiple agents with MCP tools."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.agents = {}
        self.mcp_servers = {}

    def add_mcp_server(self, name, url, auth=None):
        """Add MCP server for agents to use."""
        self.mcp_servers[name] = {
            "url": url,
            "auth": auth
        }

    def create_specialized_agent(self, name, specialty, mcp_servers):
        """Create agent specialized for specific tasks."""
        # Create workflow for specialized agent
        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", f"{name}_agent", {
            "system_prompt": f"You are a specialist in {specialty}.",
            "mcp_servers": [self.mcp_servers[s]["url"] for s in mcp_servers],
            "enable_mcp": True
        })
        self.agents[name] = workflow.build()
        return self.agents[name]

    async def route_task(self, task):
        """Route task to appropriate agent based on content."""
        # Analyze task
        if "calculate" in task or "math" in task:
            agent = self.agents.get("math", self.agents["general"])
        elif "data" in task or "analyze" in task:
            agent = self.agents.get("data", self.agents["general"])
        else:
            agent = self.agents["general"]

        # Execute with agent workflow
        results, run_id = await self.runtime.execute_async(agent, parameters={
            f"{agent.nodes[0].id}": {
                "messages": [{"role": "user", "content": task}]
            }
        })
        return results[list(results.keys())[0]]["result"]

# Usage
orchestrator = MCPAgentOrchestrator(runtime)

# Add MCP servers
orchestrator.add_mcp_server(
    "math_tools",
    "mcp://math-server:8080",
    auth=BearerTokenAuth("math-token")
)
orchestrator.add_mcp_server(
    "data_tools",
    "mcp://data-server:8081",
    auth=APIKeyAuth(["data-key"])
)

# Create specialized agents
orchestrator.create_specialized_agent(
    "math",
    "mathematical calculations and analysis",
    ["math_tools"]
)
orchestrator.create_specialized_agent(
    "data",
    "data analysis and processing",
    ["data_tools"]
)
orchestrator.create_specialized_agent(
    "general",
    "general assistance",
    ["math_tools", "data_tools"]
)

# Route tasks
result = await orchestrator.route_task("Calculate the factorial of 10")
```

## Best Practices

### 1. Tool Design

```python
# Good: Clear, focused tools
@server.tool()
def get_user_by_id(user_id: int) -> dict:
    """Get user information by ID."""
    user = db.get_user(user_id)
    if not user:
        raise ToolExecutionError(f"User {user_id} not found")
    return user.to_dict()

# Bad: Tool doing too much
@server.tool()
def user_operations(action: str, data: dict) -> dict:
    """Generic user operations."""
    if action == "get":
        return get_user(data["id"])
    elif action == "create":
        return create_user(data)
    # ... many more actions
```

### 2. Error Messages

```python
# Good: Informative error messages
@server.tool()
def divide(a: float, b: float) -> dict:
    if b == 0:
        raise ToolExecutionError(
            "Division by zero",
            details={"numerator": a, "denominator": b},
            suggestions=["Check that denominator is non-zero"]
        )
    return {"result": a / b}
```

### 3. Resource Optimization

```python
# Use caching for expensive operations
@server.tool(cache_key="report_{report_id}")
async def generate_report(report_id: str) -> dict:
    # Expensive report generation
    data = await fetch_report_data(report_id)
    report = await process_report(data)
    return {"report": report}

# Connection pooling for clients
client_pool = MCPClientPool(
    max_clients=10,
    min_clients=2,
    server_url="mcp://server:8080"
)
```

### 4. Monitoring and Observability

```python
# Enable comprehensive monitoring
server = MCPServer(
    "monitored-server",
    enable_metrics=True,
    metrics_config={
        "export_interval": 60,
        "include_latencies": True,
        "include_errors": True
    }
)

# Add custom metrics
@server.tool()
def process_order(order: dict) -> dict:
    start = time.time()
    try:
        result = process(order)
        server.metrics.increment("orders.processed")
        return result
    except Exception as e:
        server.metrics.increment("orders.failed")
        raise
    finally:
        duration = time.time() - start
        server.metrics.histogram("orders.duration", duration)
```

## Common Pitfalls and Solutions

### 1. Connection Management

```python
# Problem: Not handling connection lifecycle
client = MCPClient("bad-client")
result = await client.call_tool("tool", {})  # Fails - not connected

# Solution: Proper connection management
client = MCPClient("good-client")
try:
    await client.connect("mcp://server:8080")
    result = await client.call_tool("tool", {})
finally:
    await client.disconnect()

# Better: Use context manager
async with MCPClient("best-client") as client:
    await client.connect("mcp://server:8080")
    result = await client.call_tool("tool", {})
```

### 2. Tool Timeout Handling

```python
# Problem: No timeout handling
@server.tool()
async def long_operation(data: dict) -> dict:
    # This could hang forever
    result = await external_api_call(data)
    return {"result": result}

# Solution: Add timeouts
@server.tool(timeout=30)  # 30 second timeout
async def long_operation_safe(data: dict) -> dict:
    try:
        result = await asyncio.wait_for(
            external_api_call(data),
            timeout=25  # Leave buffer for response
        )
        return {"result": result}
    except asyncio.TimeoutError:
        raise ToolExecutionError("Operation timed out")
```

### 3. Resource Cleanup

```python
# Ensure proper cleanup with server lifecycle
async def run_mcp_server():
    server = MCPServer("my-server")

    # Setup tools and resources
    setup_tools(server)

    try:
        # Start server
        await server.start(host="0.0.0.0", port=8080)

        # Keep running until interrupted
        await server.wait_closed()
    finally:
        # Cleanup
        await server.shutdown()
        await cleanup_resources()
```

This completes the MCP patterns guide with comprehensive examples for building production-ready MCP applications using the Kailash SDK.
