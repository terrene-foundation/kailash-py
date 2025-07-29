# Production MCP Server Guide

*Enterprise-grade MCP server with authentication, caching, and monitoring*

## Overview

The Production MCP Server (`MCPServer`) provides enterprise-ready Model Context Protocol server capabilities with a hybrid implementation that uses the best available MCP backend. It includes production features like authentication, caching, metrics, circuit breakers, and advanced content handling.

For prototyping and development, see the [SimpleMCPServer](#simple-server-for-prototyping) section or the [MCP Integration Cheatsheet](../cheatsheet/025-mcp-integration.md).

## Server Types

| Server Type | Use Case | Features |
|-------------|----------|----------|
| **MCPServer** | Production, enterprise | Auth, caching, metrics, rate limiting, circuit breakers |
| **SimpleMCPServer** | Prototyping, learning | Basic MCP functionality only |
| **MiddlewareMCPServer** | Kailash integration | SDK nodes, workflows, events |

## Prerequisites

- Completed [MCP Development Guide](17-mcp-development-guide.md)
- Understanding of authentication concepts
- Familiarity with caching and monitoring

## Core Features

### Enhanced Server Configuration

```python
from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth

# Production-ready server with all features
server = MCPServer(
    name="production-server",
    enable_cache=True,
    cache_ttl=300,                    # 5 minutes default
    cache_backend="memory",           # or "redis"
    enable_metrics=True,
    enable_monitoring=True,

    # Authentication
    auth_provider=APIKeyAuth(keys=["admin-key", "user-key"]),

    # Performance
    rate_limit_config={"requests_per_minute": 100},
    circuit_breaker_config={"failure_threshold": 5},

    # Transport
    enable_http_transport=True,
    enable_sse_transport=True,
    transport_timeout=30.0,
    max_request_size=10_000_000,

    # Advanced
    enable_streaming=True,
    error_aggregation=True
)
```

## Authentication Systems

### API Key Authentication

```python
from kailash.mcp_server.auth import APIKeyAuth

# Multiple API keys with permissions
auth = APIKeyAuth(keys={
    "admin-secret-key": {"permissions": ["read", "write", "admin"]},
    "user1-key": {"permissions": ["read", "write"]},
    "readonly-key": {"permissions": ["read"]}
})

server = MCPServer("auth-server", auth_provider=auth)

# Tools with permission requirements
@server.tool(required_permission="admin.write")
async def sensitive_operation(data: dict) -> dict:
    """Admin-only tool."""
    return {"result": "operation completed"}

@server.tool(required_permissions=["data.read", "reports.generate"])
async def generate_report(query: str) -> dict:
    """Multi-permission tool."""
    return {"report": "generated"}
```

### JWT Authentication

```python
from kailash.mcp_server.auth import JWTAuth

# JWT with custom claims
jwt_auth = JWTAuth(
    secret="your-jwt-secret",
    algorithm="HS256",
    required_claims=["sub", "permissions"]
)

server = MCPServer("jwt-server", auth_provider=jwt_auth)

@server.tool(required_permission="data.process")
async def process_data(items: list) -> dict:
    """JWT-protected tool."""
    return {"processed": len(items)}
```

### Basic HTTP Authentication

```python
from kailash.mcp_server.auth import BasicAuth

# Basic auth with username/password
basic_auth = BasicAuth({
    "admin": "admin_password",
    "user": "user_password",
    "readonly": "readonly_password"
})

server = MCPServer("basic-auth-server", auth_provider=basic_auth)

@server.tool(required_permission="admin")
async def admin_operation(data: dict) -> dict:
    """Admin-only operation."""
    return {"result": "admin operation completed"}

## Advanced Caching

### Memory Caching

```python
# Memory cache with automatic TTL
@server.tool(cache_key="weather_{city}", cache_ttl=600)
async def get_weather(city: str) -> dict:
    """Cached weather data."""
    # Expensive API call cached for 10 minutes
    weather_data = await fetch_weather_api(city)
    return {"weather": weather_data, "cached_at": time.time()}

# Manual cache operations
cache = server.get_cache()
await cache.set("custom_key", {"data": "value"}, ttl=300)
cached_data = await cache.get("custom_key")
```

### Redis Distributed Caching

```python
# Redis cache configuration
redis_config = {
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "password": "redis-password"
}

server = MCPServer(
    "distributed-server",
    enable_cache=True,
    cache_backend="redis",
    cache_config=redis_config
)

# Cache with stampede prevention
@server.tool(cache_key="expensive_computation_{params}")
async def expensive_computation(params: dict) -> dict:
    """Prevents multiple simultaneous computations."""
    # Only one instance computes, others wait for result
    result = await perform_computation(params)
    return {"result": result}
```

## Performance Features

### Circuit Breaker Protection

```python
# Circuit breaker configuration
circuit_config = {
    "failure_threshold": 5,      # Open after 5 failures
    "timeout": 30.0,            # Timeout requests after 30s
    "recovery_timeout": 60.0,    # Try recovery after 60s
    "expected_exception": Exception
}

server = MCPServer(
    "resilient-server",
    circuit_breaker_config=circuit_config
)

@server.tool(enable_circuit_breaker=True, timeout=10.0)
async def fragile_operation(data: dict) -> dict:
    """Protected by circuit breaker."""
    # Operation that might fail
    result = await unreliable_service(data)
    return {"result": result}

# Circuit breaker management
server.reset_circuit_breaker()  # Manual reset
state = server.get_circuit_breaker_state()
```

### Rate Limiting

```python
# Global rate limiting
rate_config = {
    "requests_per_minute": 100,
    "burst_size": 10,
    "per_client": True  # Per API key/client
}

server = MCPServer("rate-limited", rate_limit_config=rate_config)

# Per-tool rate limiting
@server.tool(rate_limit={"requests_per_minute": 10})
async def limited_tool(query: str) -> dict:
    """Tool with specific rate limit."""
    return {"result": "rate limited response"}
```

## Advanced Tool Features

### Streaming Tools

```python
@server.tool(stream_response=True)
async def large_data_processor(dataset: str) -> dict:
    """Stream large responses."""
    # Server automatically chunks large responses
    large_result = process_large_dataset(dataset)
    return {"data": large_result, "size": len(large_result)}

# Custom streaming with progress
from kailash.mcp_server.advanced_features import ProgressReporter

@server.tool()
async def progress_operation(items: list) -> dict:
    """Tool with progress reporting."""
    async with ProgressReporter("processing", total=len(items)) as progress:
        results = []
        for i, item in enumerate(items):
            result = await process_item(item)
            results.append(result)
            await progress.update(i + 1, f"Processed {i + 1}/{len(items)}")

        await progress.complete("All items processed")

    return {"results": results}
```

### Multi-Modal Content

```python
from kailash.mcp_server.advanced_features import MultiModalContent

@server.tool()
async def create_report(data: dict) -> dict:
    """Tool returning multi-modal content."""
    content = MultiModalContent()

    # Add text content
    content.add_text("## Analysis Report\n\nKey findings:")

    # Add image
    chart_data = generate_chart(data)
    content.add_image(chart_data, "image/png", "Data visualization")

    # Add file reference
    content.add_resource("file://report.pdf", "Detailed PDF report")

    return {"content": content.to_dict()}
```

## Resource Management

### Dynamic Resources

```python
@server.resource("database://schema/{table}")
async def table_schema(table: str) -> dict:
    """Dynamic table schema resource."""
    schema = await get_table_schema(table)
    return {
        "table": table,
        "columns": schema.columns,
        "indexes": schema.indexes,
        "constraints": schema.constraints
    }

# Resource with subscriptions
from kailash.mcp_server.advanced_features import ResourceTemplate

template = ResourceTemplate(
    uri_template="config://{environment}/{service}",
    supports_subscription=True
)

@server.resource(template)
async def config_resource(environment: str, service: str) -> dict:
    """Configuration that supports real-time updates."""
    config = await get_service_config(environment, service)
    return {"config": config, "version": config.version}
```

## Monitoring and Metrics

### Built-in Metrics

```python
# Server statistics
stats = server.get_server_stats()
print(f"Tools registered: {stats['registered_tools']}")
print(f"Active sessions: {stats['active_sessions']}")
print(f"Total requests: {stats['total_requests']}")

# Tool-specific metrics
tool_stats = server.get_tool_stats()
for tool_name, metrics in tool_stats.items():
    print(f"{tool_name}: {metrics['call_count']} calls, "
          f"{metrics['avg_duration']:.2f}ms avg")

# Error analysis
errors = server.get_error_trends(time_window=3600)  # Last hour
for error_type, count in errors.items():
    print(f"{error_type}: {count} occurrences")
```

### Health Checks

```python
# Built-in health check
health = server.health_check()
print(f"Status: {health['status']}")
print(f"Uptime: {health['uptime_seconds']}s")
print(f"Memory usage: {health['memory_mb']}MB")

# Custom health checks
@server.health_check("database")
async def check_database():
    """Custom health check."""
    try:
        await database.ping()
        return {"status": "healthy", "latency_ms": 5}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

## Production Management

### Server Control

```python
# Tool management
server.disable_tool("maintenance_tool")
server.enable_tool("maintenance_tool")

# Session management
sessions = server.get_active_sessions()
for session_id in sessions:
    if sessions[session_id]["idle_time"] > 300:  # 5 minutes
        server.terminate_session(session_id)

# Cache management
server.clear_cache()  # Clear all cache
server.clear_tool_cache("expensive_tool")  # Clear specific tool cache
```

### Configuration Updates

```python
# Dynamic configuration updates
server.update_rate_limit({"requests_per_minute": 200})
server.update_cache_ttl(600)  # 10 minutes

# Tool configuration
server.update_tool_config("analytics_tool", {
    "cache_ttl": 1800,  # 30 minutes
    "timeout": 60.0
})
```

## Simple Server for Prototyping

### SimpleMCPServer Overview

For prototyping, learning, and development scenarios, use `SimpleMCPServer` which provides basic MCP functionality without enterprise features:

```python
from kailash.mcp_server import SimpleMCPServer

# Lightweight server for development
server = SimpleMCPServer("my-prototype")

@server.tool("Simple greeting")
def hello(name: str) -> str:
    """Basic tool for prototyping."""
    return f"Hello, {name}!"

@server.tool("Echo data")
def echo(data: dict) -> dict:
    """Echo data for testing."""
    return {"echoed": data, "received_at": time.time()}

if __name__ == "__main__":
    server.run()
```

### When to Use SimpleMCPServer

```python
# Use SimpleMCPServer for:
# ✅ Prototyping new MCP tools
# ✅ Learning MCP concepts
# ✅ Development and testing
# ✅ Simple use cases
# ✅ Fast iteration

# Use MCPServer for:
# ✅ Production deployments
# ✅ Enterprise applications
# ✅ Authentication required
# ✅ Performance monitoring needed
# ✅ Caching and rate limiting required
```

### Migration from Simple to Production

```python
# Step 1: Start with SimpleMCPServer
simple_server = SimpleMCPServer("prototype")

@simple_server.tool()
def my_tool(data: str) -> dict:
    return {"result": data}

# Step 2: Upgrade to MCPServer for production
from kailash.mcp_server.auth import APIKeyAuth

production_server = MCPServer(
    "production",
    enable_cache=True,
    auth_provider=APIKeyAuth({"prod-key": "secret"})
)

# Same tool, now with production features
@production_server.tool(cache_ttl=300, required_permission="data.process")
async def my_tool(data: str) -> dict:
    return {"result": data}
```

## Error Handling

### Structured Errors

```python
from kailash.mcp_server.errors import (
    MCPError, ToolError, ResourceError,
    AuthenticationError, RateLimitError
)

@server.tool()
async def validated_tool(data: dict) -> dict:
    """Tool with comprehensive error handling."""
    try:
        # Validate input
        if not data.get("required_field"):
            raise ToolError(
                "VALIDATION_ERROR",
                "Missing required field",
                details={"field": "required_field"}
            )

        # Process data
        result = await process_data(data)
        return {"result": result}

    except ValueError as e:
        raise ToolError("INVALID_DATA", str(e))
    except ConnectionError as e:
        raise ResourceError("CONNECTION_FAILED", str(e))
    except Exception as e:
        raise MCPError("INTERNAL_ERROR", str(e))
```

## Integration Examples

### Workflow Integration

```python
from kailash.workflow.builder import WorkflowBuilder

# MCP server as workflow component
workflow = WorkflowBuilder()

workflow.add_node("MCPServer", "mcp_tools", {
    "server_config": {
        "name": "workflow-mcp",
        "enable_cache": True,
        "auth_provider": APIKeyAuth(keys=["workflow-key"])
    },
    "tools": ["data_processor", "report_generator"]
})

# Use MCP tools in workflow
workflow.add_node("PythonCodeNode", "process", {
    "code": """
# Call MCP tool from workflow
mcp_client = get_mcp_client("workflow-mcp")
result = await mcp_client.call_tool("data_processor", {"data": input_data})
result = {"processed": result}
"""
})
```

### Middleware Integration

```python
from kailash.middleware.mcp.enhanced_server import MiddlewareMCPServer

# Full middleware integration
enhanced_server = MiddlewareMCPServer(
    config=MCPServerConfig(
        name="middleware-mcp",
        enable_cache=True,
        enable_metrics=True
    ),
    event_stream=event_stream,
    agent_ui=agent_ui
)

# Real-time updates to UI
@enhanced_server.tool()
async def interactive_tool(query: str) -> dict:
    """Tool with real-time UI updates."""
    # Send progress to UI
    await enhanced_server.send_ui_update({
        "type": "progress",
        "message": "Processing query..."
    })

    result = await process_query(query)

    # Final update
    await enhanced_server.send_ui_update({
        "type": "complete",
        "result": result
    })

    return {"result": result}
```

## Best Practices

### 1. Security

```python
# Always use authentication in production
server = MCPServer(
    "secure-server",
    auth_provider=JWTAuth(secret=os.environ["JWT_SECRET"]),
    rate_limit_config={"requests_per_minute": 100}
)

# Validate all inputs
@server.tool(required_permission="data.write")
async def secure_tool(data: dict) -> dict:
    # Validate and sanitize inputs
    validated_data = validate_input_schema(data)
    result = await safe_operation(validated_data)
    return {"result": result}
```

### 2. Performance

```python
# Use appropriate caching
@server.tool(cache_key="computation_{hash(str(params))}", cache_ttl=3600)
async def expensive_computation(params: dict) -> dict:
    # Cache expensive operations
    pass

# Enable circuit breakers for external services
@server.tool(enable_circuit_breaker=True, timeout=30.0)
async def external_service_call(request: dict) -> dict:
    # Protected external calls
    pass
```

### 3. Monitoring

```python
# Regular health monitoring
async def monitoring_loop():
    while True:
        health = server.health_check()
        if health["status"] != "healthy":
            await send_alert(health)

        # Reset circuit breakers if needed
        if health.get("circuit_breaker_state") == "open":
            await asyncio.sleep(60)  # Wait before reset
            server.reset_circuit_breaker()

        await asyncio.sleep(30)  # Check every 30 seconds
```

## Related Guides

**Prerequisites:**
- [MCP Development Guide](17-mcp-development-guide.md) - Basic MCP concepts

**Next Steps:**
- [MCP Service Discovery Guide](24-mcp-service-discovery-guide.md) - Service registry
- [MCP Transport Layers Guide](26-mcp-transport-layers-guide.md) - Transport configuration

---

**Build production-ready MCP servers with enterprise features and monitoring!**
