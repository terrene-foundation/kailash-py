# MCP Integration - Model Context Protocol

## Quick Setup - LLMAgentNode with MCP
```python
from kailash import Workflow
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime

# Single node with integrated MCP
workflow = Workflow("mcp-example")
workflow.add_node("agent", LLMAgentNode())

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
        "auto_discover_tools": True
    }
})

```

## MCP Server Creation
```python
from kailash.mcp import MCPServer

# Production server with caching
server = MCPServer("my-server")

@server.tool(cache_key="expensive", cache_ttl=600)
async def expensive_operation(data: str) -> dict:
    """Cached operation."""
    return {"processed": data}

@server.tool(format_response="markdown")
async def get_status(service: str) -> dict:
    """Returns markdown-formatted status."""
    return {"service": service, "status": "healthy"}

if __name__ == "__main__":
    server.run()

```

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

## Tool Discovery
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai import LLMAgentNode

workflow = Workflow("tool-discovery")
workflow.add_node("agent", LLMAgentNode())
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
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai import LLMAgentNode

workflow = Workflow("resource-access")
workflow.add_node("agent", LLMAgentNode())
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
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai import LLMAgentNode

workflow = Workflow("tool-calling")
workflow.add_node("agent", LLMAgentNode())
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
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai import LLMAgentNode

workflow = Workflow("error-handling")
workflow.add_node("agent", LLMAgentNode())
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

### Iterative MCP Usage
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode

workflow = Workflow("iterative-mcp")
workflow.add_node("iterative", IterativeLLMAgentNode())
runtime = LocalRuntime()

# Define mcp_servers
mcp_servers = [
    {"name": "data", "transport": "stdio", "command": "mcp-server"}
]

results, run_id = runtime.execute(workflow, parameters={
    "iterative": {
        "mcp_servers": mcp_servers,
        "auto_discover_tools": True,
        "iterative_config": {
            "max_iterations": 5,
            "tool_discovery_per_iteration": True
        },
        "messages": [{"role": "user", "content": "Analyze all data sources"}]
    }
})

```

## Next Steps
- [LLM Workflows](../workflows/by-pattern/ai-ml/llm-workflows.md) - LLM patterns
- [API Integration](015-workflow-as-rest-api.md) - REST API setup
- [Production Guide](../developer/04-production.md) - Deployment
