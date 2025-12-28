# MCP Integration - Model Context Protocol

## 🎯 MCP Testing Results
**Comprehensive Testing Complete**: 407 tests across 8 components - 100% pass rate
- **Unit Tests**: 391 tests covering all MCP functionality
- **Integration Tests**: 14 real MCP server tests
- **E2E Tests**: 2 complete workflow scenarios
- **Test Coverage**: Client, server, tool execution, async handling, error recovery

## ✅ Simplified API v0.9.9: Always Real MCP
**All MCP nodes now use real execution with graceful fallback.**
- **Simplified Configuration**: No more mock/test mode parameters needed
- **Graceful Fallback**: Automatically handles unavailable MCP servers
- **Always Production-Ready**: Real tool execution by default with robust error handling

## 🔌 Multi-Channel MCP Integration
**NEW: Nexus Framework Integration** - MCP now available as unified channel
```python
# Use the Nexus app framework (pip install kailash-nexus)
from nexus import Nexus

# MCP as part of multi-channel platform
nexus = Nexus()

# Configure channels
nexus.enable_api(port=8000)    # REST API
nexus.enable_cli()              # Command line
nexus.enable_mcp(port=3000)     # MCP server - FULLY TESTED ✅
# With WebSocket transport support:
nexus.enable_mcp(port=3000, transport="websocket")  # WebSocket MCP server

# Workflows automatically available across all channels:
# - API: POST /api/executions
# - CLI: nexus run workflow_name
# - MCP: Call "workflow_<name>" tool
```

## Quick Setup - LLMAgentNode with MCP (v0.6.6+)
```python
from kailash.workflow.builder import WorkflowBuilderBuilder
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime

# Single node with integrated MCP
builder = WorkflowBuilder()
builder.add_node("LLMAgentNode", "agent", {})
workflow = builder.build()

# Execute with MCP servers
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [
            {"role": "user", "content": "What data is available?"}
        ],
        "mcp_servers": [
            {
                "name": "data-server",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_data_server"]
            }
        ],
        "auto_discover_tools": True,
        "auto_execute_tools": True  # Execute tools automatically
    }
})

```

## Tool Execution with MCP
```python
# Automatic tool execution
builder = WorkflowBuilder()
builder.add_node("LLMAgentNode", "agent", {})
workflow = builder.build()

results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "openai",
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Search for customer data and create a report"}
        ],
        "mcp_servers": [{
            "name": "customer-db",
            "transport": "stdio",
            "command": "mcp-customer-server"
        }],
        "auto_discover_tools": True,
        "auto_execute_tools": True,  # Execute discovered tools
        "tool_execution_config": {
            "max_rounds": 3,  # Limit execution rounds
            "timeout": 120    # 2 minute timeout
        }
    }
})

# Check execution details
print(f"Tools executed: {results['agent']['context']['tools_executed']}")
```

## MCP Server Creation

### Production Server (MCPServer)
```python
from kailash.mcp_server import MCPServer

# Production server with all features
server = MCPServer(
    "my-server",
    enable_cache=True,
    enable_metrics=True,
    cache_backend="memory",
    cache_ttl=600
)

@server.tool(cache_key="expensive", cache_ttl=600)
async def expensive_operation(data: str) -> dict:
    """Cached operation."""
    return {"processed": data}

@server.tool()
async def get_status(service: str) -> dict:
    """Get service status."""
    return {"service": service, "status": "healthy"}

if __name__ == "__main__":
    server.run()

# WebSocket production server
from kailash.mcp_server.transports import WebSocketServerTransport

ws_transport = WebSocketServerTransport(
    host="0.0.0.0",
    port=3001,
    ping_interval=30.0,
    max_message_size=5*1024*1024  # 5MB
)

ws_server = MCPServer("websocket-server", transport=ws_transport)
# Tools registered same way - automatic WebSocket support
```

### Simple Server for Prototyping (SimpleMCPServer)
```python
from kailash.mcp_server import SimpleMCPServer

# Lightweight server for development/prototyping
server = SimpleMCPServer("my-prototype", "Development prototype")

@server.tool()
def hello(name: str) -> str:
    """Basic tool without advanced features."""
    return f"Hello, {name}!"

@server.tool()
def echo(data: dict) -> dict:
    """Echo data for testing."""
    return {"echoed": data}

if __name__ == "__main__":
    server.run()
```

### When to Use Which Server

| Use Case | Server Type | Features |
|----------|-------------|----------|
| **Production APIs** | `MCPServer` | Auth, caching, metrics, rate limiting |
| **Quick prototyping** | `SimpleMCPServer` | Basic MCP functionality only |
| **Development/testing** | `SimpleMCPServer` | Fast setup, no dependencies |
| **Learning MCP** | `SimpleMCPServer` | Focus on concepts |
| **Enterprise apps** | `MCPServer` | Full production features |

## Server Configuration

### STDIO Transport (Local)
```python
mcp_servers = [
    {
        "name": "filesystem",
        "transport": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem", "/data"]
    },
    {
        "name": "sqlite",
        "transport": "stdio",
        "command": "mcp-server-sqlite",
        "args": ["--db-path", "database.db"]
    }
]

```

### HTTP Transport (Remote)
```python
mcp_servers = [
    {
        "name": "api-server",
        "transport": "http",
        "url": "http://localhost:8080",
        "headers": {
            "Authorization": "Bearer ${MCP_TOKEN}"
        }
    }
]
```

### WebSocket Transport (Real-time)
```python
# WebSocket MCP client with connection pooling
mcp_servers = [
    {
        "name": "realtime-server",
        "transport": "websocket",
        "url": "ws://localhost:3001/mcp",
        "connection_pool_config": {
            "max_connections": 10,
            "connection_timeout": 30.0,
            "ping_interval": 20.0
        }
    },
    {
        "name": "secure-server",
        "transport": "websocket",
        "url": "wss://api.company.com/mcp",
        "ping_interval": 30.0,
        "ping_timeout": 10.0
    }
]

# Direct WebSocket client for advanced usage
from kailash.mcp_server import MCPClient

client = MCPClient(
    connection_pool_config={
        "max_connections": 20,
        "connection_timeout": 30.0
    },
    enable_metrics=True
)

async with client:
    # Connection pooling automatically used
    result1 = await client.call_tool("ws://api.example.com/mcp", "search", {"query": "AI"})
    result2 = await client.call_tool("ws://api.example.com/mcp", "analyze", {"data": result1})

    # Check pool efficiency
    metrics = client.get_metrics()
    print(f"Pool efficiency: {metrics.get('websocket_pool_hits', 0)} hits")
```

## Tool Discovery
```python
from kailash.workflow.builder import WorkflowBuilderBuilder
from kailash.runtime.local import LocalRuntime

builder = WorkflowBuilder()
builder.add_node("LLMAgentNode", "agent", {})
workflow = builder.build()
runtime = LocalRuntime()

# Define mcp_servers first
mcp_servers = [
    {"name": "data", "transport": "stdio", "command": "mcp-server"}
]

# Auto-discover MCP tools
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "mcp_servers": mcp_servers,
        "auto_discover_tools": True,
        "tool_discovery_config": {
            "max_tools": 50,
            "cache_discoveries": True
        },
        "messages": [
            {"role": "user", "content": "List available tools"}
        ]
    }
})

# Check discovered tools
if results["agent"]["success"]:
    tools = results["agent"]["context"].get("tools_available", [])
    print(f"Found {len(tools)} tools")

```

## Resource Access
```python
from kailash.workflow.builder import WorkflowBuilderBuilder
from kailash.runtime.local import LocalRuntime

builder = WorkflowBuilder()
builder.add_node("LLMAgentNode", "agent", {})
workflow = builder.build()
runtime = LocalRuntime()

# Access MCP resources
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "mcp_servers": [{"name": "kb", "transport": "stdio", "command": "mcp-kb"}],
        "mcp_context": [
            "data://sales/2024",
            "resource://templates/report",
            "knowledge://policies"
        ],
        "messages": [
            {"role": "user", "content": "Create report from templates"}
        ]
    }
})

```

## Tool Calling
```python
from kailash.workflow.builder import WorkflowBuilderBuilder
from kailash.runtime.local import LocalRuntime

builder = WorkflowBuilder()
builder.add_node("LLMAgentNode", "agent", {})
workflow = builder.build()
runtime = LocalRuntime()

# Define mcp_servers
mcp_servers = [
    {"name": "data", "transport": "stdio", "command": "mcp-server"}
]

# Enable tool calling
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "temperature": 0,  # Best for tool calling
        "mcp_servers": mcp_servers,
        "auto_discover_tools": True,
        "generation_config": {
            "tool_choice": "auto",
            "max_tool_calls": 5
        },
        "messages": [
            {"role": "user", "content": "Get sales data and analyze"}
        ]
    }
})

```

## Error Handling
```python
from kailash.workflow.builder import WorkflowBuilderBuilder
from kailash.runtime.local import LocalRuntime

builder = WorkflowBuilder()
builder.add_node("LLMAgentNode", "agent", {})
workflow = builder.build()
runtime = LocalRuntime()

# Graceful failure handling
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "mcp_servers": [
            {
                "name": "data",
                "transport": "stdio",
                "command": "mcp-server",
                "timeout": 30
            }
        ],
        "mcp_config": {
            "connection_timeout": 10,
            "retry_attempts": 3,
            "fallback_on_failure": True
        },
        "messages": [{"role": "user", "content": "Get data"}]
    }
})

if not results["agent"]["success"]:
    print(f"MCP Error: {results['agent']['error']}")

```

## Best Practices

### Environment Configuration
```python
import os

# Environment-specific servers
MCP_CONFIGS = {
    "dev": [{
        "name": "local",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "local_server"]
    }],
    "prod": [{
        "name": "prod",
        "transport": "http",
        "url": "https://mcp.company.com",
        "headers": {"Authorization": f"Bearer {os.getenv('MCP_TOKEN')}"}
    }]
}

mcp_servers = MCP_CONFIGS[os.getenv("ENV", "dev")]

```

### Performance Optimization
```python
tool_discovery_config = {
    "cache_discoveries": True,
    "cache_ttl": 3600,
    "filter_by_relevance": True,
    "max_tools_per_server": 20,
    "parallel_discovery": True
}

```

### Security
```python
secure_config = {
    "validate_ssl": True,
    "allowed_commands": ["safe-cmd-1", "safe-cmd-2"],
    "sandbox_execution": True,
    "log_all_calls": True
}

```

## Common Patterns

### Multi-Server Setup
```python
# Combine multiple MCP servers
mcp_servers = [
    {"name": "knowledge", "transport": "stdio", "command": "mcp-kb"},
    {"name": "analytics", "transport": "http", "url": "http://analytics:8080"},
    {"name": "docs", "transport": "stdio", "command": "mcp-docs"}
]

```

### Iterative MCP Usage with Real Tool Execution
```python
from kailash.workflow.builder import WorkflowBuilderBuilder
from kailash.runtime.local import LocalRuntime

builder = WorkflowBuilder()
builder.add_node("IterativeLLMAgentNode", "iterative", {})
workflow = builder.build()
runtime = LocalRuntime()

# Define mcp_servers
mcp_servers = [
    {"name": "data", "transport": "stdio", "command": "mcp-server"}
]

# NEW: Real MCP tool execution with iterative refinement
results, run_id = runtime.execute(workflow, parameters={
    "iterative": {
        "provider": "openai",
        "model": "gpt-4",
        "mcp_servers": mcp_servers,
        # Real MCP execution is always enabled
        "auto_discover_tools": True,
        "auto_execute_tools": True,
        "max_iterations": 5,
        "discovery_mode": "progressive",
        "convergence_criteria": {
            "goal_satisfaction": {"threshold": 0.9},
            "quality_threshold": 0.8
        },
        "messages": [{"role": "user", "content": "Analyze all data sources and create comprehensive report"}]
    }
})

# Check execution results
if results["iterative"]["success"]:
    print(f"Completed in {len(results['iterative']['iterations'])} iterations")
    print(f"Tools executed: {results['iterative']['context']['tools_executed']}")
    print(f"Convergence reason: {results['iterative']['convergence_summary']['reason']}")

```

**Key Features (v0.6.5+)**:
- **Real MCP Tool Execution**: Actually calls MCP tools instead of mock responses
- **6-Phase Process**: Discovery → Planning → Execution → Reflection → Convergence → Synthesis
- **Test-Driven Convergence**: Only stops when deliverables actually work
- **Simplified API**: Always uses real MCP execution with graceful fallback

## Testing MCP Integration

### Unit Testing Pattern
```python
import pytest
from unittest.mock import MagicMock
from kailash.nodes.ai import LLMAgentNode

def test_mcp_tool_execution():
    """Test MCP tool execution with mocked server."""
    node = "LLMAgentNode"

    # Mock MCP response
    mock_response = {
        "tools": [{"name": "search", "description": "Search data"}],
        "result": {"data": "test results"}
    }

    # Test with mock provider
    result = node.execute(
        provider="mock",
        model="gpt-4",
        messages=[{"role": "user", "content": "Search for data"}],
        mcp_servers=[{"name": "test", "transport": "stdio", "command": "echo"}],
        auto_execute_tools=True
    )

    assert result["success"] is True
    assert "response" in result
```

### Integration Testing Pattern
```python
@pytest.mark.integration
def test_real_mcp_server():
    """Test with real MCP server running in Docker."""
    node = "LLMAgentNode"

    result = node.execute(
        provider="ollama",
        model="llama3.2",
        messages=[{"role": "user", "content": "List available tools"}],
        mcp_servers=[{
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "test_mcp_server"]
        }],
        auto_discover_tools=True
    )

    # Verify tool discovery
    assert result["context"]["tools_available"] is not None
    assert len(result["context"]["tools_available"]) > 0
```

### Testing Best Practices
1. **Mock for Unit Tests**: Use mock providers for fast, reliable tests
2. **Real Servers for Integration**: Test with actual MCP servers in Docker
3. **Async Context Handling**: Test both sync and async execution contexts
4. **Error Recovery**: Test timeout, connection failure, and tool error scenarios
5. **Tool Execution Verification**: Check both discovery and execution results

## Next Steps
- [LLM Workflows](../workflows/by-pattern/ai-ml/llm-workflows.md) - LLM patterns
- [API Integration](015-workflow-as-rest-api.md) - REST API setup
- [Production Guide](../developer/04-production.md) - Deployment
- [MCP Tool Execution Guide](../developer/22-mcp-tool-execution-guide.md) - Advanced patterns
