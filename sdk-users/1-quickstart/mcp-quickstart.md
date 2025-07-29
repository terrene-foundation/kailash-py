# MCP (Model Context Protocol) Quick Start Guide

Welcome to the MCP Quick Start Guide! This guide will help you get started with Model Context Protocol integration in the Kailash SDK in under 5 minutes.

## What is MCP?

Model Context Protocol (MCP) is a standardized protocol that enables AI models to interact with external tools and resources. With MCP, your AI agents can:
- Execute tools and functions
- Access external data sources
- Integrate with third-party services
- Share context between different systems

## Quick Example - Your First MCP-Enabled Agent

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime

# Create a simple workflow with MCP
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {}))

# Execute with MCP server
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [
            {"role": "user", "content": "What tools are available?"}
        ],
        "mcp_servers": [{
            "name": "filesystem",
            "transport": "stdio",
            "command": "npx",
            "args": ["@modelcontextprotocol/server-filesystem", "/tmp"]
        }],
        "auto_discover_tools": True
    }
})

print(results["agent"]["response"])
```

## Step-by-Step Setup

### 1. Install Required Packages

```bash
# Install Kailash SDK
pip install kailash

# Install MCP servers (optional - for testing)
npm install -g @modelcontextprotocol/server-filesystem
```

### 2. Create Your First MCP Workflow

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime

# Initialize
workflow = WorkflowBuilder()
runtime = LocalRuntime()

# Add an LLM agent with MCP
workflow.add_node("LLMAgentNode", "assistant", {}))

# Configure and run
results, run_id = runtime.execute(workflow, parameters={
    "assistant": {
        "provider": "openai",  # or "ollama", "anthropic"
        "model": "gpt-4",      # or "llama3.2", "claude-3"
        "messages": [
            {"role": "user", "content": "List all files in the current directory"}
        ],
        "mcp_servers": [{
            "name": "fs",
            "transport": "stdio",
            "command": "npx",
            "args": ["@modelcontextprotocol/server-filesystem", "."]
        }],
        "auto_discover_tools": True,
        "auto_execute_tools": True  # Let the agent execute tools
    }
})

# Print the response
print(results["assistant"]["response"])
```

### 3. Common MCP Server Configurations

#### Local File System Access
```python
mcp_servers = [{
    "name": "filesystem",
    "transport": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-filesystem", "/data"]
}]
```

#### SQLite Database Access
```python
mcp_servers = [{
    "name": "database",
    "transport": "stdio",
    "command": "mcp-server-sqlite",
    "args": ["--db-path", "my_database.db"]
}]
```

#### HTTP API Server
```python
mcp_servers = [{
    "name": "api",
    "transport": "http",
    "url": "http://localhost:8080",
    "headers": {
        "Authorization": "Bearer YOUR_TOKEN"
    }
}]
```

#### Custom Python MCP Server
```python
mcp_servers = [{
    "name": "custom",
    "transport": "stdio",
    "command": "python",
    "args": ["-m", "my_mcp_server"]
}]
```

## Creating Your Own MCP Server

Here's a minimal MCP server in Python:

### Quick Prototype Server

```python
# my_simple_server.py
from kailash.mcp_server import SimpleMCPServer

# Create lightweight server for prototyping
server = SimpleMCPServer("my-tools")

# Add simple tools
@server.tool("Add numbers")
def add_numbers(a: int, b: int) -> dict:
    """Add two numbers together."""
    return {"result": a + b}

@server.tool("Get weather")
def get_weather(city: str) -> dict:
    """Get weather for a city."""
    # In real implementation, call weather API
    return {
        "city": city,
        "temperature": 72,
        "conditions": "sunny"
    }

# Run the server (no configuration needed)
if __name__ == "__main__":
    server.run()
```

### Production Server

```python
# my_production_server.py
from kailash.mcp_server import MCPServer

# Create production server with features
server = MCPServer(
    "my-tools-prod",
    enable_cache=True,
    enable_metrics=True
)

# Add production tools with caching
@server.tool(cache_ttl=300)  # Cache for 5 minutes
async def add_numbers(a: int, b: int) -> dict:
    """Add two numbers together."""
    return {"result": a + b}

@server.tool(cache_ttl=600)  # Cache for 10 minutes
async def get_weather(city: str) -> dict:
    """Get weather for a city."""
    # In real implementation, call weather API
    return {
        "city": city,
        "temperature": 72,
        "conditions": "sunny"
    }

# Run the server
if __name__ == "__main__":
    server.run()
```

### When to Use Which Server

| Use Case | Server Type | Why |
|----------|-------------|-----|
| **Learning MCP** | `SimpleMCPServer` | Focus on concepts, not infrastructure |
| **Prototyping** | `SimpleMCPServer` | Fast iteration, minimal setup |
| **Production** | `MCPServer` | Authentication, caching, monitoring |
| **Enterprise** | `MCPServer` | Full production features required |

## Key MCP Parameters

### Essential Parameters
- `mcp_servers`: List of MCP server configurations
- `auto_discover_tools`: Automatically discover available tools (default: False)
- `auto_execute_tools`: Allow agent to execute tools automatically (default: False)

### Advanced Parameters
```python
parameters = {
    "agent": {
        # ... other parameters ...
        "mcp_servers": [...],
        "tool_discovery_config": {
            "max_tools": 50,           # Limit number of tools
            "cache_discoveries": True,  # Cache tool discovery
            "timeout": 30              # Discovery timeout
        },
        "tool_execution_config": {
            "max_rounds": 3,           # Max tool execution rounds
            "timeout": 120,            # Execution timeout
            "parallel": True           # Allow parallel execution
        }
    }
}
```

## Common Use Cases

### 1. File Analysis Assistant
```python
# Agent that can read and analyze files
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [
            {"role": "user", "content": "Analyze the Python files in this directory"}
        ],
        "mcp_servers": [{
            "name": "fs",
            "transport": "stdio",
            "command": "npx",
            "args": ["@modelcontextprotocol/server-filesystem", "."]
        }],
        "auto_discover_tools": True,
        "auto_execute_tools": True
    }
})
```

### 2. Database Query Assistant
```python
# Agent that can query databases
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "openai",
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Show me all users who joined this month"}
        ],
        "mcp_servers": [{
            "name": "db",
            "transport": "stdio",
            "command": "mcp-server-sqlite",
            "args": ["--db-path", "users.db"]
        }],
        "auto_discover_tools": True,
        "auto_execute_tools": True
    }
})
```

### 3. Multi-Tool Assistant
```python
# Agent with multiple MCP servers
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "anthropic",
        "model": "claude-3",
        "messages": [
            {"role": "user", "content": "Get weather data and save it to a file"}
        ],
        "mcp_servers": [
            {
                "name": "weather",
                "transport": "http",
                "url": "http://weather-mcp:8080"
            },
            {
                "name": "filesystem",
                "transport": "stdio",
                "command": "npx",
                "args": ["@modelcontextprotocol/server-filesystem", "./output"]
            }
        ],
        "auto_discover_tools": True,
        "auto_execute_tools": True
    }
})
```

## Best Practices

### 1. Security
- Only connect to trusted MCP servers
- Use authentication when available
- Limit file system access to specific directories
- Review tool permissions before enabling `auto_execute_tools`

### 2. Performance
- Enable tool discovery caching for repeated use
- Set appropriate timeouts for tool execution
- Use connection pooling for HTTP transports

### 3. Error Handling
```python
# Always check for success
if results["agent"]["success"]:
    print(results["agent"]["response"])
else:
    print(f"Error: {results['agent']['error']}")

# Check tool execution results
if "tools_executed" in results["agent"]["context"]:
    for tool_result in results["agent"]["context"]["tools_executed"]:
        print(f"Tool: {tool_result['tool']}")
        print(f"Result: {tool_result['result']}")
```

## Troubleshooting

### Common Issues

1. **"MCP server not found"**
   - Ensure the command exists in PATH
   - Check that required packages are installed
   - Verify the command syntax

2. **"Tool discovery failed"**
   - Check MCP server is running
   - Verify network connectivity for HTTP transport
   - Check authentication credentials

3. **"Tool execution timeout"**
   - Increase timeout in `tool_execution_config`
   - Check if the tool is hanging
   - Verify server resources

### Debug Mode
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Add debug info to parameters
parameters = {
    "agent": {
        # ... other parameters ...
        "debug": True,
        "log_tool_calls": True
    }
}
```

## Next Steps

Now that you've learned the basics of MCP:

1. **Explore More Examples**: Check out [examples/mcp/](../examples/mcp/) for more complex scenarios
2. **Deep Dive**: Read the full [MCP Integration Guide](../cheatsheet/025-mcp-integration.md)
3. **Production Patterns**: Study [MCP Patterns](../patterns/12-mcp-patterns.md) for production use
4. **Build Custom Servers**: See [MCP Development Guide](../developer/22-mcp-development-guide.md)

## Quick Reference Card

```python
# Minimal MCP setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {}))
runtime = LocalRuntime()

results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [{"role": "user", "content": "Your prompt"}],
        "mcp_servers": [{"name": "server", "transport": "stdio", "command": "cmd"}],
        "auto_discover_tools": True,
        "auto_execute_tools": True
    }
})
```

Happy building with MCP! 🚀
