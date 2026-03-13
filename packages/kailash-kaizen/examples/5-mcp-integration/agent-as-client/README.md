# Agent as MCP Client Pattern - Production MCP Implementation

## ✅ Migration Complete (2025-10-04)

This example has been **fully migrated** from deprecated `kaizen.mcp` to Kailash SDK's production-ready `kailash.mcp_server` implementation using BaseAgent helpers.

## Overview
Demonstrates agents consuming external MCP (Model Context Protocol) tools using Kailash SDK's production-ready MCP implementation. This pattern uses BaseAgent helpers for simplified MCP integration with real JSON-RPC 2.0 protocol.

## Migration Summary

### What Changed

#### 1. **Imports** - Deprecated `kaizen.mcp` removed
```python
# ❌ OLD (deprecated)
from kaizen.mcp import MCPConnection, MCPRegistry, AutoDiscovery

# ✅ NEW (via BaseAgent helpers)
from kaizen.core.base_agent import BaseAgent
# kailash.mcp_server imported internally by BaseAgent
```

#### 2. **Connection Setup** - Manual → Helper-based
```python
# ❌ OLD (manual connection)
connection = MCPConnection(
    name=server_config["name"],
    url=server_config.get("url"),
    auth_type=server_config.get("auth_type"),
    auth_token=server_config.get("auth_token"),
    timeout=self.client_config.connection_timeout
)
if connection.connect():
    self.connections[server_config["name"]] = connection

# ✅ NEW (BaseAgent helper - async)
await self.setup_mcp_client(
    servers=self.client_config.mcp_servers,
    retry_strategy="circuit_breaker",
    enable_metrics=True
)
# Tools automatically available in self._available_mcp_tools
```

#### 3. **Tool Invocation** - Manual → Helper-based
```python
# ❌ OLD (manual invocation)
invocation_result = connection.call_tool(
    tool_name=tool_name,
    arguments=tool_arguments
)

# ✅ NEW (BaseAgent helper - async)
invocation_result = await self.call_mcp_tool(
    tool_id=tool_id,
    arguments=tool_arguments,
    timeout=30.0,
    store_in_memory=True  # Auto-stores in shared memory
)
```

#### 4. **Server Configuration** - URL-based → Transport-based
```python
# ❌ OLD (URL-based, limited)
mcp_servers = [
    {"name": "search-server", "url": "http://localhost:18080"},
    {"name": "compute-server", "url": "http://localhost:18081"}
]

# ✅ NEW (transport-based, multi-protocol)
mcp_servers = [
    # HTTP transport
    {
        "name": "search-tools",
        "transport": "http",
        "url": "http://localhost:8080",
        "headers": {"Authorization": "Bearer demo-key"}
    },
    # STDIO transport
    {
        "name": "compute-tools",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "mcp_compute_server"]
    }
]
```

#### 5. **Async Execution** - Sync → Async
```python
# ❌ OLD (sync methods)
def _setup_mcp_connections(self):
    # Sync connection setup

def invoke_tool(self, tool_id: str, ...):
    # Sync tool invocation

def execute_task(self, task: str, ...):
    # Sync execution

# ✅ NEW (async methods)
async def _setup_mcp_connections(self):
    # Async connection setup with await

async def invoke_tool(self, tool_id: str, ...):
    # Async tool invocation with await

async def execute_task(self, task: str, ...):
    # Async execution with await
```

### Key Benefits

✅ **Production-Ready**: Uses Kailash SDK's battle-tested MCP implementation
✅ **100% MCP Spec Compliant**: Real JSON-RPC 2.0 protocol, not mocked
✅ **Multi-Transport**: STDIO, HTTP, WebSocket, SSE support
✅ **Enterprise Features**: Auth, retry, circuit breaker, metrics
✅ **Simplified API**: BaseAgent helpers reduce boilerplate by ~60%
✅ **Async-Native**: Proper async/await for concurrent operations
✅ **Auto-Memory Storage**: Tool calls automatically stored in shared memory

## Use Case
- Agents using external specialized tools and services
- Production MCP integration with real JSON-RPC protocol
- Multi-transport MCP server connections
- Integration with third-party AI services and tools
- Building composite agent solutions from distributed services
- Leveraging community-contributed MCP tools with enterprise security

## Quick Start

### Running the Example

```bash
# Install dependencies
pip install kailash

# Run the example (requires MCP servers configured)
python workflow.py
```

### Example Output

```
======================================================================
MCP Client Agent - Production MCP Examples
======================================================================

This example demonstrates PRODUCTION MCP usage:
  • Kailash SDK's production-ready MCPClient
  • Real JSON-RPC 2.0 protocol (no mocking)
  • BaseAgent helpers (setup_mcp_client, call_mcp_tool)
  • Multi-transport support (STDIO, HTTP, WebSocket, SSE)
  • Enterprise features (auth, retry, circuit breaker, metrics)

NOTE: Requires MCP servers configured in transport configs
======================================================================

✓ MCP setup complete: 5 tools discovered

Discovered MCP Tools:
----------------------------------------------------------------------
  • search-tools:brave_search
    Description: Search the web using Brave Search
    Server: search-tools
  • compute-tools:calculate
    Description: Perform mathematical calculations
    Server: compute-tools
```

## Agent Architecture

### Production MCP Client Agent

```python
class MCPClientAgent(BaseAgent):
    """Agent that consumes external MCP tools using production MCP."""

    async def _setup_mcp_connections(self):
        """Setup MCP using BaseAgent helper."""
        await self.setup_mcp_client(
            servers=self.client_config.mcp_servers,
            retry_strategy="circuit_breaker",
            enable_metrics=True
        )

    async def invoke_tool(self, tool_id: str, ...):
        """Invoke tool using BaseAgent helper."""
        result = await self.call_mcp_tool(
            tool_id=tool_id,
            arguments=tool_arguments,
            timeout=30.0,
            store_in_memory=True
        )
        return result
```

### Kaizen Signatures

```python
class TaskAnalysisSignature(Signature):
    """Analyze task to determine required MCP tools."""
    task_description: str = InputField(desc="User task requiring external tools")
    available_tools: str = InputField(desc="JSON list of available MCP tools")
    context: str = InputField(desc="Additional context", default="")

    required_tools: str = OutputField(desc="JSON list of required tools with reasons")
    execution_plan: str = OutputField(desc="Step-by-step execution plan")
    estimated_complexity: float = OutputField(desc="Complexity score 0.0-1.0", default=0.5)

class ToolInvocationSignature(Signature):
    """Prepare tool invocation with proper arguments."""
    tool_name: str = InputField(desc="Name of MCP tool to invoke")
    tool_schema: str = InputField(desc="JSON schema of tool parameters")
    user_request: str = InputField(desc="User's original request")
    context: str = InputField(desc="Execution context", default="")

    tool_arguments: str = OutputField(desc="JSON arguments for tool invocation")
    invocation_reasoning: str = OutputField(desc="Why these arguments were chosen")
    expected_output: str = OutputField(desc="Expected output description")

class ResultSynthesisSignature(Signature):
    """Synthesize results from multiple MCP tool calls."""
    task_description: str = InputField(desc="Original user task")
    tool_results: str = InputField(desc="JSON results from MCP tools")
    execution_context: str = InputField(desc="Execution metadata", default="")

    final_answer: str = OutputField(desc="Synthesized final answer")
    confidence_score: float = OutputField(desc="Confidence in answer 0.0-1.0", default=0.8)
    tool_usage_summary: str = OutputField(desc="Summary of which tools were used")
```

## Configuration

### MCP Server Configuration (Transport-Based)

```python
@dataclass
class MCPClientConfig:
    """Configuration for MCP client agent."""
    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 1000

    # MCP server configurations (transport-based)
    mcp_servers: List[Dict[str, Any]] = field(default_factory=lambda: [
        # HTTP transport example
        {
            "name": "search-tools",
            "transport": "http",
            "url": "http://localhost:8080",
            "headers": {"Authorization": "Bearer demo-key"}
        },
        # STDIO transport example
        {
            "name": "compute-tools",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "mcp_compute_server"]
        },
    ])

    # MCP client settings
    retry_strategy: str = "circuit_breaker"
    enable_metrics: bool = True
    connection_timeout: int = 30
```

### Supported Transports

#### 1. **STDIO** - Local process communication
```python
{
    "name": "local-tools",
    "transport": "stdio",
    "command": "python",
    "args": ["-m", "my_mcp_server"],
    "env": {"DEBUG": "1"}  # Optional environment variables
}
```

#### 2. **HTTP** - REST API communication
```python
{
    "name": "api-tools",
    "transport": "http",
    "url": "http://localhost:8080",
    "headers": {"Authorization": "Bearer token123"},
    "timeout": 30
}
```

#### 3. **WebSocket** - Real-time bidirectional communication
```python
{
    "name": "ws-tools",
    "transport": "websocket",
    "url": "ws://localhost:9000/mcp",
    "headers": {"Authorization": "Bearer token123"}
}
```

#### 4. **SSE** - Server-Sent Events
```python
{
    "name": "sse-tools",
    "transport": "sse",
    "url": "http://localhost:8081/events",
    "headers": {"Authorization": "Bearer token123"}
}
```

## Technical Requirements

### Dependencies
```bash
pip install kailash  # Includes kailash.mcp_server
```

### Python Imports
```python
# Kaizen framework
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.memory import SharedMemoryPool

# Standard library
import json
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
```

## Workflow Execution

### Agent Execution Flow

```python
async def main_async():
    """Execute MCP client agent workflow."""

    # 1. Create configuration with MCP servers
    config = MCPClientConfig(
        mcp_servers=[
            {
                "name": "search-tools",
                "transport": "http",
                "url": "http://localhost:8080",
                "headers": {"Authorization": "Bearer demo-key"}
            },
            {
                "name": "compute-tools",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_compute_server"]
            }
        ]
    )

    # 2. Create agent
    agent = MCPClientAgent(config)

    # 3. Setup MCP connections (async)
    await agent._setup_mcp_connections()
    # → Connects to all configured MCP servers
    # → Discovers available tools via JSON-RPC
    # → Stores tools in self._available_mcp_tools

    # 4. Execute task (async)
    task = "Search for information about quantum computing and calculate 2^10"
    result = await agent.execute_task(task)
    # → Analyzes task to determine required tools
    # → Invokes tools via BaseAgent.call_mcp_tool()
    # → Synthesizes results into final answer

    # 5. Access results
    print(f"Answer: {result['final_answer']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Tools Used: {result['tool_usage_summary']}")

# Run async workflow
asyncio.run(main_async())
```

### Data Flow

1. **MCP Setup** (async)
   - `BaseAgent.setup_mcp_client()` establishes connections
   - Tools discovered via JSON-RPC `tools/list`
   - Available in `self._available_mcp_tools`

2. **Task Analysis** (LLM-based)
   - Analyze user task against available tools
   - Determine which tools to invoke
   - Generate execution plan

3. **Tool Invocation** (async)
   - `BaseAgent.call_mcp_tool()` for each required tool
   - Real JSON-RPC `tools/call` protocol
   - Results auto-stored in shared memory

4. **Result Synthesis** (LLM-based)
   - Combine tool results
   - Generate final answer
   - Calculate confidence score

## Enterprise Features

### Production Capabilities

✅ **Authentication**
- API Key, Bearer token, JWT support via headers
- OAuth 2.1 for advanced authentication
- Automatic credential injection

✅ **Retry Strategy**
- Circuit breaker pattern (default)
- Exponential backoff
- Custom retry policies

✅ **Monitoring & Metrics**
- Tool invocation tracking
- Performance metrics collection
- Error rate monitoring
- Success/failure analytics

✅ **Connection Management**
- WebSocket connection pooling
- Automatic reconnection
- Health monitoring
- Timeout configuration

✅ **Security**
- HTTPS/WSS for encrypted communication
- SSL/TLS certificate validation
- Secure credential storage
- Audit trail for tool usage

### Error Handling

The agent handles various MCP-specific errors:

- **Connection failures** → Automatic retry with circuit breaker
- **Authentication errors** → Clear error messages with resolution steps
- **Tool not found** → Lists available tools for user
- **Timeout errors** → Configurable timeout with fallback
- **Invalid responses** → JSON schema validation and error recovery

## Testing

### Running Tests

```bash
# Unit tests (mocked MCP)
pytest tests/unit/examples/test_agent_as_client.py

# Integration tests (real MCP servers)
pytest tests/integration/test_mcp_integration.py
```

### Test MCP Server Setup

For testing, you can use the provided mock MCP server:

```bash
# Start mock MCP server (HTTP)
python tests/mcp_test_server.py --port 8080

# Or use any MCP-compliant server
npx @modelcontextprotocol/server-filesystem ./data
```

## Troubleshooting

### Common Issues

#### 1. Import Error: `kailash.mcp_server not available`
```bash
# Solution: Install full Kailash SDK
pip install kailash --upgrade
```

#### 2. Connection Timeout
```python
# Solution: Increase timeout in config
config = MCPClientConfig(connection_timeout=60)  # 60 seconds
```

#### 3. Authentication Failures
```python
# Solution: Verify headers/auth config
{
    "transport": "http",
    "url": "http://localhost:8080",
    "headers": {"Authorization": "Bearer YOUR_TOKEN"}
}
```

#### 4. Async Execution Issues
```python
# Solution: Ensure all MCP methods use await
await agent._setup_mcp_connections()
result = await agent.invoke_tool(tool_id, request)
```

## Migration Guide for Other Examples

To migrate other MCP examples to production MCP:

1. **Remove deprecated imports**
   ```python
   # Remove: from kaizen.mcp import ...
   ```

2. **Add BaseAgent inheritance**
   ```python
   class YourAgent(BaseAgent):
       pass
   ```

3. **Use setup_mcp_client() helper**
   ```python
   async def _setup_mcp_connections(self):
       await self.setup_mcp_client(
           servers=self.config.mcp_servers,
           retry_strategy="circuit_breaker"
       )
   ```

4. **Use call_mcp_tool() helper**
   ```python
   async def invoke_tool(self, tool_id, args):
       result = await self.call_mcp_tool(
           tool_id=tool_id,
           arguments=args
       )
       return result
   ```

5. **Update server configs to transport-based**
   ```python
   mcp_servers = [
       {
           "name": "my-tools",
           "transport": "stdio",  # or "http", "websocket", "sse"
           "command": "python",
           "args": ["-m", "my_server"]
       }
   ]
   ```

6. **Make all MCP methods async**
   ```python
   async def method_name(self):
       await self.mcp_operation()
   ```

## References

- **Kailash MCP Documentation**: `
- **BaseAgent MCP Helpers**: `
- **MCP Specification**: https://modelcontextprotocol.io/docs
