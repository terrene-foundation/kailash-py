# MCP (Model Context Protocol) Development Guide

*Build AI applications with standardized tool and resource access*

## Overview

The Model Context Protocol (MCP) enables standardized communication between AI applications and external tools/resources. This guide covers building MCP-enabled applications using the Kailash SDK.

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core concepts
- Understanding of [AI Nodes](../nodes/02-ai-nodes.md)
- Basic knowledge of client-server architecture

## Core Concepts

### What is MCP?

MCP provides a standard way for:
- AI agents to discover and use tools
- Applications to expose functionality to AI
- Secure tool execution with proper authentication
- Resource sharing between AI systems

### Key Components

1. **Tools**: Functions that perform actions
2. **Resources**: Data or configuration access
3. **Authentication**: Secure access control
4. **Discovery**: Finding available tools/resources

## Building MCP Servers

### Basic Server Setup

```python
from kailash.mcp_server import MCPServer

# Create MCP server
server = MCPServer(
    name="my-tools",
    description="Custom tools for data processing"
)

# Register a simple tool
@server.tool()
def calculate_sum(a: int, b: int) -> dict:
    """Add two numbers together."""
    return {"result": a + b}

# Register a tool with more complex inputs
@server.tool()
def process_data(
    data: list,
    operation: str = "sum",
    filter_value: float = None
) -> dict:
    """Process a list of numbers with various operations."""
    if filter_value is not None:
        data = [x for x in data if x > filter_value]

    if operation == "sum":
        result = sum(data)
    elif operation == "average":
        result = sum(data) / len(data) if data else 0
    elif operation == "max":
        result = max(data) if data else None
    elif operation == "min":
        result = min(data) if data else None
    else:
        raise ValueError(f"Unknown operation: {operation}")

    return {
        "result": result,
        "operation": operation,
        "count": len(data)
    }

# Start the server
await server.start(host="0.0.0.0", port=8080)
```

### Async Tools

```python
@server.tool()
async def fetch_user_data(user_id: str) -> dict:
    """Fetch user data from database."""
    # Async database operation
    db = await get_database_connection()

    async with db.acquire() as conn:
        user = await conn.fetchone(
            "SELECT * FROM users WHERE id = $1",
            user_id
        )

    if user:
        return {
            "user": dict(user),
            "found": True
        }
    else:
        return {
            "user": None,
            "found": False,
            "error": "User not found"
        }
```

### Resource Providers

```python
# Provide access to data/configuration using resource decorator
@server.resource("database://schema")
async def database_schema() -> dict:
    """Provide current database schema."""
    return {
        "tables": {
            "users": ["id", "name", "email", "created_at"],
            "orders": ["id", "user_id", "total", "status"],
            "products": ["id", "name", "price", "stock"]
        },
        "version": "2.1.0",
        "last_updated": "2024-01-15"
    }

@server.resource("api://endpoints")
async def api_endpoints() -> dict:
    """List available API endpoints."""
    return {
        "endpoints": [
            {"path": "/users", "methods": ["GET", "POST"]},
            {"path": "/users/{id}", "methods": ["GET", "PUT", "DELETE"]},
            {"path": "/orders", "methods": ["GET", "POST"]},
            {"path": "/products", "methods": ["GET"]}
        ],
        "base_url": "https://api.example.com/v1"
    }
```

### Prompt Templates

```python
# Define reusable prompts for LLM interactions
@server.prompt("analyze_data")
async def analyze_data_prompt(data: dict) -> str:
    """Generate analysis prompt for data."""
    return f"""Analyze the following data and provide insights:

Data: {data}

Please provide:
1. Key patterns or trends
2. Any anomalies or outliers
3. Recommendations for action
"""

@server.prompt("code_review")
async def code_review_prompt(code: str, language: str = "python") -> str:
    """Generate code review prompt."""
    return f"""Review the following {language} code:

```{language}
{code}
```

Please check for:
1. Code quality and best practices
2. Potential bugs or issues
3. Performance concerns
4. Security vulnerabilities
"""
```

### Error Handling

```python
@server.tool()
async def risky_operation(params: dict) -> dict:
    """Operation that might fail."""
    try:
        # Validate inputs
        if not params.get("required_field"):
            return {
                "success": False,
                "error": "Missing required_field"
            }

        # Perform operation
        result = await perform_operation(params)

        return {
            "success": True,
            "result": result
        }

    except PermissionError:
        return {
            "success": False,
            "error": "Permission denied",
            "code": "PERMISSION_DENIED"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "code": "INTERNAL_ERROR"
        }
```

## Building MCP Clients

### Basic Client Usage

```python
from kailash.mcp_server import MCPClient

# Create client
client = MCPClient("my-app")

# Connect to server
await client.connect("mcp://localhost:8080")

# Discover available tools
tools = await client.list_tools()
for tool in tools:
    print(f"Tool: {tool['name']}")
    print(f"  Description: {tool['description']}")
    print(f"  Parameters: {tool['parameters']}")

# Call a tool
result = await client.call_tool(
    "process_data",
    {
        "data": [1, 5, 3, 8, 2],
        "operation": "average",
        "filter_value": 2
    }
)
print(f"Result: {result}")
```

### Client with Authentication

```python
# Connect with authentication
client = MCPClient("secure-app")

await client.connect(
    "mcp://api.example.com:8080",
    auth={
        "type": "bearer",
        "token": "your-api-token"
    }
)

# Or with API key
await client.connect(
    "mcp://api.example.com:8080",
    auth={
        "type": "api_key",
        "key": "your-api-key"
    }
)
```

### Resource Access

```python
# Get resources
schema = await client.get_resource("database_schema")
print(f"Tables: {schema['tables'].keys()}")

# Subscribe to resource updates
async def on_schema_update(updated_schema):
    print(f"Schema updated to version {updated_schema['version']}")

await client.subscribe_resource(
    "database_schema",
    on_schema_update
)
```

## Integration with LLM Agents

### Basic LLM Agent with MCP

```python
from kailash.nodes.ai import LLMAgentNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create agent with MCP access
workflow = WorkflowBuilder()

workflow.add_node("LLMAgentNode", "assistant", {
    "model": "gpt-4",
    "mcp_servers": ["mcp://localhost:8080"],
    "enable_mcp": True,
    "system_prompt": """You are a helpful assistant with access to calculation
    and data processing tools. Use them when needed to answer questions."""
})

# The agent can now discover and use MCP tools automatically
workflow.add_node("PythonCodeNode", "input", {
    "code": 'result = {"messages": [{"role": "user", "content": user_query}]}'
})

workflow.add_connection("input", "result", "assistant", "messages")

# Execute
runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build(), parameters={
    "input": {"user_query": "What's the average of 15, 23, 31, 19, and 27?"}
})

# Agent will automatically use the process_data tool
print(results["assistant"]["response"])
```

### Advanced Agent Configuration

```python
# Agent with multiple MCP servers and custom tool selection
agent = LLMAgentNode(
    name="advanced_agent",
    model="gpt-4",
    mcp_servers=[
        "mcp://math-tools.example.com:8080",
        "mcp://data-tools.example.com:8081",
        "mcp://api-tools.example.com:8082"
    ],
    enable_mcp=True,
    mcp_config={
        "tool_selection_strategy": "best_match",  # or "first_available"
        "max_tool_calls_per_turn": 5,
        "timeout_seconds": 30,
        "retry_failed_calls": True
    },
    system_prompt="""You have access to various tools for math, data processing,
    and API interactions. Use them efficiently to solve complex problems."""
)
```

### Tool Usage Monitoring

```python
# Monitor tool usage by agents
workflow.add_node("LLMAgentNode", "monitored_agent", {
    "model": "gpt-4",
    "mcp_servers": ["mcp://localhost:8080"],
    "enable_mcp": True,
    "enable_tool_monitoring": True
})

# After execution, access tool usage stats
results, run_id = runtime.execute(workflow.build(), parameters={...})

tool_usage = results["monitored_agent"].get("tool_usage", {})
print(f"Tools called: {tool_usage.get('total_calls', 0)}")
print(f"Unique tools: {tool_usage.get('unique_tools', [])}")
print(f"Call details: {tool_usage.get('calls', [])}")
```

## Authentication & Security

### Server-Side Authentication

```python
from kailash.mcp_server import MCPServer, require_auth

# Create server with authentication
server = MCPServer("secure-server")

# Configure authentication
server.configure_auth({
    "type": "bearer",
    "validate_token": validate_token_func
})

async def validate_token_func(token: str) -> dict:
    """Validate bearer token and return user info."""
    # Check token in database or auth service
    if token in valid_tokens:
        return {
            "user_id": "user123",
            "permissions": ["read", "write"]
        }
    return None

# Protect specific tools
@server.tool()
@require_auth(permissions=["write"])
async def delete_user(user_id: str) -> dict:
    """Delete a user (requires write permission)."""
    # Only accessible with proper authentication
    pass
```

### Rate Limiting

```python
from kailash.mcp_server import rate_limit

# Apply rate limiting to tools
@server.tool()
@rate_limit(calls=100, period="hour", per="user")
def expensive_operation(data: dict) -> dict:
    """Rate-limited expensive operation."""
    # Process data
    return {"result": "processed"}
```

## Service Discovery

### Registry-Based Discovery

```python
from kailash.mcp_server import MCPRegistry

# Register server with discovery service
registry = MCPRegistry("https://registry.example.com")

await registry.register(
    server,
    tags=["math", "data-processing"],
    metadata={
        "version": "1.0.0",
        "author": "your-team"
    }
)

# Client-side discovery
available_servers = await registry.discover(
    tags=["math"],
    max_results=10
)

for server_info in available_servers:
    print(f"Server: {server_info['name']} at {server_info['url']}")
    print(f"Tools: {server_info['tool_count']}")
```

### Local Discovery

```python
# Broadcast server availability locally
server.enable_local_discovery(
    port=5555,
    broadcast_interval=30
)

# Client discovers local servers
local_servers = await client.discover_local(
    timeout=5,
    port=5555
)
```

## Production Deployment

### Server Configuration

```python
# Production server setup
server = MCPServer(
    name="production-tools",
    description="Production MCP server",
    config={
        "max_concurrent_requests": 100,
        "request_timeout": 30,
        "enable_metrics": True,
        "metrics_port": 9090,
        "log_level": "INFO",
        "cors_origins": ["https://app.example.com"]
    }
)

# Health check endpoint
@server.health_check()
async def health():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "uptime_seconds": server.uptime
    }
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080 9090

CMD ["python", "-m", "uvicorn", "mcp_server:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: mcp-server
        image: your-registry/mcp-server:latest
        ports:
        - containerPort: 8080
          name: mcp
        - containerPort: 9090
          name: metrics
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
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          periodSeconds: 5
```

## Best Practices

### 1. Tool Design

```python
# ✅ Good - Clear, focused tools
@server.tool()
def calculate_tax(amount: float, tax_rate: float) -> dict:
    """Calculate tax for a given amount."""
    tax = amount * tax_rate
    total = amount + tax
    return {
        "tax_amount": tax,
        "total_amount": total,
        "tax_rate": tax_rate
    }

# ❌ Bad - Too generic, unclear purpose
@server.tool()
def process(data: dict) -> dict:
    """Process data."""
    # What does this do?
    return {"result": data}
```

### 2. Error Messages

```python
# ✅ Good - Informative error responses
@server.tool()
def divide(a: float, b: float) -> dict:
    """Divide two numbers."""
    if b == 0:
        return {
            "success": False,
            "error": "Division by zero",
            "suggestion": "Ensure divisor is non-zero"
        }
    return {
        "success": True,
        "result": a / b
    }
```

### 3. Documentation

```python
# ✅ Good - Comprehensive documentation
@server.tool()
def search_products(
    query: str,
    category: str = None,
    min_price: float = None,
    max_price: float = None,
    sort_by: str = "relevance"
) -> dict:
    """
    Search for products in the catalog.

    Args:
        query: Search query string
        category: Optional category filter
        min_price: Minimum price filter
        max_price: Maximum price filter
        sort_by: Sort order (relevance, price_asc, price_desc)

    Returns:
        Dictionary with 'products' list and 'total_count'
    """
    # Implementation
    pass
```

## Troubleshooting

### Connection Issues

```python
# Debug connection problems
import logging

logging.basicConfig(level=logging.DEBUG)

try:
    await client.connect("mcp://localhost:8080")
except ConnectionError as e:
    print(f"Connection failed: {e}")
    # Check server is running
    # Verify network connectivity
    # Check firewall settings
```

### Tool Discovery Issues

```python
# Verify tools are registered
tools = await client.list_tools()
if not tools:
    print("No tools found - check server registration")

# Test tool directly
try:
    result = await client.call_tool("test_tool", {})
except ToolNotFoundError:
    print("Tool not found - verify tool name and registration")
```

### Performance Issues

```python
# Monitor server performance
metrics = await server.get_metrics()
print(f"Request rate: {metrics['requests_per_second']}")
print(f"Average latency: {metrics['avg_latency_ms']}ms")
print(f"Active connections: {metrics['active_connections']}")

# Optimize for high load
server.configure({
    "max_concurrent_requests": 500,
    "connection_pool_size": 50,
    "enable_request_batching": True
})
```

## Related Guides

**Prerequisites:**
- [AI Nodes](../nodes/02-ai-nodes.md) - LLM agent basics
- [Async Workflow Builder](07-async-workflow-builder.md) - Async patterns

**Advanced Topics:**
- [Enhanced Gateway](15-enhanced-gateway-guide.md) - Gateway integration
- [Production](04-production.md) - Deployment strategies

---

**Build powerful AI applications with MCP's standardized tool and resource protocol!**
