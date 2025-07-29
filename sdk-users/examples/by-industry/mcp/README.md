# MCP Examples

This directory contains ready-to-run examples demonstrating Model Context Protocol (MCP) integration with the Kailash SDK.

## Examples Overview

### Basic Examples
- `01_simple_mcp_agent.py` - Basic MCP-enabled LLM agent
- `02_file_assistant.py` - Agent that can read and analyze files
- `03_multi_tool_agent.py` - Agent using multiple MCP servers

### Intermediate Examples
- `04_custom_mcp_server.py` - Create your own MCP server
- `05_database_assistant.py` - Query databases with natural language
- `06_api_integration.py` - Connect to HTTP-based MCP servers

### Advanced Examples
- `07_production_deployment.py` - Production-ready MCP setup
- `08_mcp_with_workflows.py` - Integrate MCP in complex workflows
- `09_secure_mcp_server.py` - MCP server with authentication

## Quick Start

1. Install dependencies:
```bash
pip install kailash
npm install -g @modelcontextprotocol/server-filesystem  # Optional
```

2. Run the simplest example:
```bash
python 01_simple_mcp_agent.py
```

## Example Structure

Each example follows this structure:
```python
"""
Example: [Name]
Description: [What it demonstrates]
Requirements: [Any special setup needed]
"""

# Imports
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime

# Configuration
# ... MCP server setup ...

# Main workflow
# ... Implementation ...

# Execution
if __name__ == "__main__":
    # Run the example
```

## Common MCP Server Configurations

### File System Access
```python
mcp_servers = [{
    "name": "filesystem",
    "transport": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-filesystem", "/path"]
}]
```

### SQLite Database
```python
mcp_servers = [{
    "name": "database",
    "transport": "stdio",
    "command": "mcp-server-sqlite",
    "args": ["--db-path", "database.db"]
}]
```

### HTTP API
```python
mcp_servers = [{
    "name": "api",
    "transport": "http",
    "url": "http://localhost:8080",
    "headers": {"Authorization": "Bearer TOKEN"}
}]
```

## Creating Your Own MCP Server

### Simple Server for Prototyping
```python
from kailash.mcp_server import SimpleMCPServer

server = SimpleMCPServer("my-tools")

@server.tool("Add numbers")
def add_numbers(a: int, b: int) -> dict:
    return {"result": a + b}

if __name__ == "__main__":
    server.run()
```

### Production Server
```python
from kailash.mcp_server import MCPServer

server = MCPServer("production-tools", enable_cache=True, enable_metrics=True)

@server.tool(cache_ttl=300)
async def expensive_operation(data: str) -> dict:
    # Expensive operation with caching
    return {"processed": data}

if __name__ == "__main__":
    server.run()
```

### Server Type Selection

| Use Case | Server Type |
|----------|-------------|
| Learning/prototyping | `SimpleMCPServer` |
| Production deployment | `MCPServer` |
| Kailash SDK integration | `MiddlewareMCPServer` |

## Tips for Running Examples

1. **Check Requirements**: Each example lists its requirements at the top
2. **Use Mock Mode**: Examples support mock mode for testing without real LLMs
3. **Enable Debug**: Set `DEBUG=True` to see detailed MCP interactions
4. **Customize Models**: Change the `provider` and `model` parameters as needed

## Troubleshooting

If an example doesn't work:

1. Check that required MCP servers are installed
2. Verify your API keys are set (for OpenAI, Anthropic, etc.)
3. Ensure Ollama is running if using local models
4. Check the debug output for specific errors

## Learn More

- [MCP Quick Start Guide](../../guides/mcp-quickstart.md)
- [MCP Integration Reference](../../cheatsheet/025-mcp-integration.md)
- [MCP Patterns](../../patterns/12-mcp-patterns.md)
