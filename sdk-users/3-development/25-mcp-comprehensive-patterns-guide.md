# MCP Comprehensive Patterns Guide

*Complete collection of production MCP patterns for all deployment scenarios*

## Overview

This guide provides a comprehensive collection of MCP patterns tested in production environments. It consolidates all MCP-related patterns from across the documentation into a single, authoritative reference for developers building with the Model Context Protocol.

## Prerequisites

- Completed [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md)
- Understanding of MCP core concepts
- Familiarity with async programming patterns

## Core MCP Patterns

### Basic Server Pattern

#### Production Server
```python
from kailash.mcp_server import MCPServer

# Create production server with features
server = MCPServer(
    name="my-production-server",
    enable_cache=True,
    enable_metrics=True
)

@server.tool()
async def get_weather(location: str) -> dict:
    """Get current weather for a location."""
    return {"location": location, "temperature": 72, "condition": "sunny"}

@server.tool()
async def get_calendar(date: str) -> dict:
    """Get calendar events for a date."""
    return {"date": date, "events": ["Meeting at 2pm"]}

# Start server
await server.start()
```

#### Simple Development Server
```python
from kailash.mcp_server import SimpleMCPServer

# Create lightweight server for development
server = SimpleMCPServer("my-dev-server")

@server.tool("Get weather")
def get_weather(location: str) -> dict:
    """Simple weather tool for development."""
    return {"location": location, "temperature": 72}

# Start server
server.run()
```

### Tool Registration Patterns

```python
# Pattern 1: Decorator-based registration
@server.tool(
    name="get_weather",
    description="Get current weather for a location"
)
async def get_weather(location: str) -> dict:
    return {"location": location, "temperature": 72, "condition": "sunny"}

# Pattern 2: Class-based tools
class WeatherTool(BaseMCPTool):
    def __init__(self):
        super().__init__(
            name="weather",
            description="Weather information tools"
        )

    async def execute(self, operation: str, **kwargs):
        if operation == "current":
            return await self.get_current_weather(**kwargs)
        elif operation == "forecast":
            return await self.get_forecast(**kwargs)

# Pattern 3: Dynamic tool registration
async def register_dynamic_tools(server):
    tools_config = await load_tools_config()
    for tool_def in tools_config:
        tool = create_tool_from_config(tool_def)
        server.add_tool(tool)
```

## Client Integration Patterns

### Basic Client Pattern

```python
from kailash.mcp_server.client import MCPClient

# Standard client setup
client = MCPClient(
    server_url="http://localhost:8080",
    timeout=30,
    max_retries=3
)

await client.connect()

# Tool execution
result = await client.call_tool(
    tool_name="get_weather",
    arguments={"location": "San Francisco"}
)
```

### Workflow Integration Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.mcp import MCPToolNode

# Integrate MCP tools into workflows
workflow = WorkflowBuilder()

# Add MCP tool node
workflow.add_node("MCPToolNode", "mcp_weather", {}))

# Chain with other nodes
workflow.add_node("PythonCodeNode", "process_weather", {}):
    return {
        "summary": f"It's {weather_data['condition']} and {weather_data['temperature']}°F",
        "alert": weather_data['temperature'] > 90
    }
""",
    function_name="process_weather"
))

workflow.add_connection("mcp_weather", "process_weather", "result", "weather_data")
```

## Resource Management Patterns

### Resource Provider Pattern

```python
from kailash.mcp_server.resources import ResourceProvider

class FileResourceProvider(ResourceProvider):
    def __init__(self, base_path: str):
        super().__init__()
        self.base_path = Path(base_path)

    async def list_resources(self, prefix: str = None) -> List[ResourceInfo]:
        resources = []
        for file_path in self.base_path.glob("**/*"):
            if file_path.is_file():
                resource = ResourceInfo(
                    uri=f"file://{file_path}",
                    name=file_path.name,
                    mime_type=self.get_mime_type(file_path),
                    size=file_path.stat().st_size
                )
                resources.append(resource)
        return resources

    async def read_resource(self, uri: str) -> bytes:
        file_path = Path(uri.replace("file://", ""))
        return file_path.read_bytes()

# Register with server
server.add_resource_provider(FileResourceProvider("/data"))
```

### Resource Subscription Pattern

```python
# Client subscribes to resource changes
async def handle_resource_change(resource_uri: str, change_type: str):
    print(f"Resource {resource_uri} {change_type}")

await client.subscribe_to_resource(
    "file:///data/config.json",
    handler=handle_resource_change
)
```

## Authentication and Security Patterns

### JWT Authentication Pattern

```python
from kailash.mcp_server.auth import JWTAuth

# Server-side JWT authentication
jwt_auth = JWTAuth(
    secret_key="your-secret-key",
    algorithm="HS256",
    expiration_hours=24
)

server = MCPServer(
    name="secure-server",
    auth_provider=jwt_auth
)

# Client-side authentication
client = MCPClient(
    server_url="http://localhost:8080",
    auth_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
)
```

### API Key Authentication Pattern

```python
from kailash.mcp_server.auth import APIKeyAuth

# Server-side API key authentication
api_auth = APIKeyAuth(
    api_keys={"client1": "key123", "client2": "key456"},
    header_name="X-API-Key"
)

server = MCPServer(
    name="api-server",
    auth_provider=api_auth
)

# Client-side API key
client = MCPClient(
    server_url="http://localhost:8080",
    headers={"X-API-Key": "key123"}
)
```

## Error Handling Patterns

### Robust Error Handling Pattern

```python
from kailash.mcp_server.errors import MCPError, ToolExecutionError

class RobustMCPTool(BaseMCPTool):
    async def execute(self, **kwargs):
        try:
            return await self.do_work(**kwargs)
        except ValidationError as e:
            raise MCPError(
                code=-1001,
                message=f"Invalid input: {e}",
                data={"field": e.field, "value": e.value}
            )
        except ExternalServiceError as e:
            raise ToolExecutionError(
                code=-2001,
                message="External service unavailable",
                retry_after=60
            )
        except Exception as e:
            logger.exception("Unexpected error in tool execution")
            raise MCPError(
                code=-3000,
                message="Internal server error"
            )

# Client-side error handling
try:
    result = await client.call_tool("my_tool", **args)
except MCPError as e:
    if e.code == -2001:  # Service unavailable
        await asyncio.sleep(e.retry_after)
        result = await client.call_tool("my_tool", **args)
    else:
        logger.error(f"MCP Error: {e.message}")
```

## Performance Optimization Patterns

### Connection Pool Pattern

```python
from kailash.mcp_server.client import MCPConnectionPool

# Client-side connection pooling
pool = MCPConnectionPool(
    server_url="http://localhost:8080",
    min_connections=2,
    max_connections=10,
    connection_timeout=30
)

# Use pool for multiple concurrent requests
async def process_batch(items):
    tasks = []
    for item in items:
        task = pool.call_tool("process_item", item=item)
        tasks.append(task)

    results = await asyncio.gather(*tasks)
    return results
```

### Caching Pattern

```python
from kailash.mcp_server.caching import MCPCache

# Server-side caching
cache = MCPCache(
    backend="redis",
    host="localhost",
    port=6379,
    default_ttl=300
)

class CachedWeatherTool(BaseMCPTool):
    async def execute(self, location: str):
        cache_key = f"weather:{location}"

        # Check cache first
        cached_result = await cache.get(cache_key)
        if cached_result:
            return cached_result

        # Fetch fresh data
        result = await self.fetch_weather(location)

        # Cache result
        await cache.set(cache_key, result, ttl=300)
        return result
```

## Monitoring and Observability Patterns

### Metrics Collection Pattern

```python
from kailash.mcp_server.monitoring import MCPMetrics

# Enable comprehensive metrics
metrics = MCPMetrics(
    collect_request_duration=True,
    collect_tool_execution_stats=True,
    collect_error_rates=True
)

server = MCPServer(
    name="monitored-server",
    enable_metrics=True
)

# Access metrics
stats = await metrics.get_stats()
print(f"Total requests: {stats.total_requests}")
print(f"Average response time: {stats.avg_response_time}ms")
print(f"Error rate: {stats.error_rate:.2%}")
```

### Health Check Pattern

```python
from kailash.mcp_server.health import HealthChecker

class CustomHealthChecker(HealthChecker):
    async def check_health(self) -> dict:
        checks = {}

        # Database connectivity
        checks["database"] = await self.check_database()

        # External services
        checks["weather_api"] = await self.check_weather_api()

        # Resource availability
        checks["disk_space"] = await self.check_disk_space()

        overall_status = all(check["status"] == "healthy" for check in checks.values())

        return {
            "status": "healthy" if overall_status else "unhealthy",
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat()
        }

server.add_health_checker(CustomHealthChecker())
```

## Testing Patterns

### Unit Testing Pattern

```python
import pytest
from kailash.mcp_server.testing import MCPTestClient

@pytest.fixture
async def test_client():
    server = MyMCPServer()
    client = MCPTestClient(server)
    await client.connect()
    yield client
    await client.disconnect()

@pytest.mark.asyncio
async def test_weather_tool(test_client):
    result = await test_client.call_tool(
        "get_weather",
        arguments={"location": "Test City"}
    )

    assert result["location"] == "Test City"
    assert "temperature" in result
    assert "condition" in result
```

### Integration Testing Pattern

```python
from kailash.testing import WorkflowTester

@pytest.mark.asyncio
async def test_mcp_workflow_integration():
    # Start real MCP server for testing
    server = MyMCPServer()
    await server.start()

    try:
        # Test workflow with MCP integration
        tester = WorkflowTester()
        workflow = create_weather_workflow()

        result = await tester.test_workflow(
            workflow,
            parameters={"location": "San Francisco"},
            expected_outputs={"weather_summary": str}
        )

        assert result.success
        assert "San Francisco" in result.outputs["weather_summary"]

    finally:
        await server.stop()
```

## Deployment Patterns

### Docker Deployment Pattern

```dockerfile
# Dockerfile for MCP server
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080
CMD ["python", "-m", "my_mcp_server"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  mcp-server:
    build: .
    ports:
      - "8080:8080"
    environment:
      - SERVER_NAME=my-mcp-server
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Kubernetes Deployment Pattern

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
        image: mycompany/mcp-server:latest
        ports:
        - containerPort: 8080
        env:
        - name: SERVER_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Best Practices Summary

1. **Tool Design**: Keep tools focused and single-purpose
2. **Error Handling**: Always provide meaningful error messages with codes
3. **Authentication**: Use appropriate auth method for your security requirements
4. **Performance**: Implement connection pooling and caching for high-load scenarios
5. **Monitoring**: Add comprehensive metrics and health checks
6. **Testing**: Write both unit and integration tests
7. **Documentation**: Document all tools, their inputs, outputs, and error codes

## See Also

- [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md) - Core server implementation
- [MCP Service Discovery Guide](24-mcp-service-discovery-guide.md) - Service discovery patterns
- [MCP Transport Layers Guide](25-mcp-transport-layers-guide.md) - Transport configuration
- [MCP Advanced Features Guide](27-mcp-advanced-features-guide.md) - Advanced capabilities
