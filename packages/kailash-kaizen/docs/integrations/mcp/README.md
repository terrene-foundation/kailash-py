# MCP Integration Guide for Kaizen

**Model Context Protocol (MCP) Integration using Kailash SDK**

## Overview

Kaizen integrates with the Model Context Protocol (MCP) through Kailash SDK's production-ready implementation. This guide shows how to use MCP in Kaizen applications for agent-to-agent communication, tool sharing, and service orchestration.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Builtin Server](#builtin-server)
3. [Architecture](#architecture)
4. [Implementation Patterns](#implementation-patterns)
5. [Testing Guide](#testing-guide)
6. [Migration Guide](#migration-guide)
7. [Reference Documentation](#reference-documentation)

---

## Quick Start

### Installation

MCP is included with Kailash SDK (no additional installation needed):

```bash
pip install kailash  # Includes kailash.mcp_server
```

### Basic Client (3 lines)

```python
from kailash.mcp_server import MCPClient

client = MCPClient(enable_metrics=True)
result = await client.call_tool(server_config, "tool_name", {"arg": "value"})
```

### Basic Server (5 lines)

```python
from kailash.mcp_server import SimpleMCPServer

server = SimpleMCPServer("my-tools")

@server.tool()
def add(a: int, b: int) -> dict:
    return {"result": a + b}

server.run()
```

---

## Builtin Server

**Kaizen includes a builtin MCP server** that provides 12 essential tools automatically available to all agents:

### Available Tools (12 total)
- **File operations (5)**: `read_file`, `write_file`, `delete_file`, `list_directory`, `file_exists`
- **HTTP requests (4)**: `http_get`, `http_post`, `http_put`, `http_delete`
- **Shell commands (1)**: `bash_command`
- **Web scraping (2)**: `fetch_url`, `extract_links`

### Auto-Connection

All BaseAgent instances automatically connect to the builtin server:

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
agent = BaseAgent(config=config, signature=MySignature())

# Automatically connected to kaizen_builtin server
# All 12 tools immediately available

# Use tools directly
result = await agent.execute_mcp_tool("read_file", {"path": "/data.txt"})
```

### Disable Auto-Connection

To disable MCP integration:

```python
# Pass empty list to disable
agent = BaseAgent(config=config, signature=MySignature(), mcp_servers=[])
```

**📖 See**: [Builtin Server Guide](builtin-server-guide.md) for complete tool reference, danger levels, and approval workflow.

### Danger-Level Based Security

All builtin tools are classified by danger level with automatic approval workflows:

- **SAFE tools** (6): Execute immediately without approval
  - `read_file`, `file_exists`, `list_directory`, `fetch_url`, `extract_links`, `http_get`
- **MEDIUM tools** (3): Require approval if `control_protocol` configured
  - `write_file`, `http_post`, `http_put`
- **HIGH tools** (3): Always require approval
  - `delete_file`, `http_delete`, `bash_command`

```python
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

# Enable approval workflow with control protocol
transport = CLITransport()
protocol = ControlProtocol(transport=transport)
await protocol.start()

# Agent automatically requests approval for MEDIUM/HIGH danger tools
agent = BaseAgent(config=config, signature=sig, control_protocol=protocol)

# SAFE tools execute immediately
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__read_file",
    {"path": "/data.txt"}
)

# MEDIUM/HIGH tools request approval from user
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__delete_file",  # HIGH danger
    {"path": "/temp.txt"}
)
# User sees: "Agent wants to delete file: /temp.txt. Approve?"
```

**📖 See**: [Builtin Server Guide - Security Features](builtin-server-guide.md#security-features) for complete danger level reference.

---

## Architecture

### Design Principle

**Kaizen uses Kailash SDK's MCP implementation** - we extend, not recreate.

```
┌─────────────────────────────────────┐
│   Kaizen Application Layer          │
│   (BaseAgent + MCP integration)     │
├─────────────────────────────────────┤
│   Kailash MCP Server                │
│   (kailash.mcp_server)               │
│   - MCPClient, MCPServer             │
│   - ServiceRegistry, ServiceMesh     │
│   - Auth, Discovery, Load Balancing  │
├─────────────────────────────────────┤
│   Official Anthropic MCP SDK        │
│   (mcp package)                      │
│   - Protocol implementation          │
│   - JSON-RPC 2.0                     │
│   - STDIO/SSE/HTTP/WebSocket         │
└─────────────────────────────────────┘
```

### Key Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **MCPClient** | Connect to MCP servers, invoke tools | `kailash.mcp_server.MCPClient` |
| **MCPServer** | Expose tools/resources/prompts | `kailash.mcp_server.MCPServer` |
| **SimpleMCPServer** | Lightweight server for prototyping | `kailash.mcp_server.SimpleMCPServer` |
| **ServiceRegistry** | Service discovery & registration | `kailash.mcp_server.ServiceRegistry` |
| **ServiceMesh** | Load balancing & failover | `kailash.mcp_server.ServiceMesh` |

### Why Use Kailash SDK MCP?

✅ **100% MCP Spec Compliant**:
- Tools (`tools/list`, `tools/call`)
- Resources (`resources/list`, `resources/read`, `resources/subscribe`)
- Prompts (`prompts/list`, `prompts/get`)
- Progress, Cancellation, Completion, Sampling, Roots

✅ **Production-Ready**:
- 407 tests (100% pass rate)
- Multiple transports (STDIO, HTTP, SSE, WebSocket)
- Enterprise auth (API Key, JWT, OAuth 2.1, Bearer Token)
- Service discovery (file-based + network)
- Load balancing, circuit breaker, retry strategies
- Metrics, health checks, connection pooling, caching

✅ **Official SDK Foundation**:
- Built on Anthropic's MCP Python SDK
- Uses FastMCP framework
- Maintained as part of Kailash SDK releases

---

## Implementation Patterns

### Pattern 1: Kaizen Agent as MCP Client

**Use Case**: Kaizen agent consumes external MCP tools

```python
from kaizen.core.base_agent import BaseAgent
from kailash.mcp_server import MCPClient, discover_mcp_servers

class ResearchAgent(BaseAgent):
    async def setup_mcp(self):
        """Setup MCP client with service discovery."""
        # Create production client
        self.mcp_client = MCPClient(
            retry_strategy="circuit_breaker",
            enable_metrics=True,
            circuit_breaker_config={
                "failure_threshold": 5,
                "recovery_timeout": 30
            }
        )

        # Discover servers
        servers = await discover_mcp_servers(capability="search")

        # Discover tools
        for server in servers:
            tools = await self.mcp_client.discover_tools(
                server,
                force_refresh=True
            )
            self.tools.extend(tools)

    async def research(self, query: str) -> dict:
        """Research using MCP tools."""
        # Call tool via MCP
        result = await self.mcp_client.call_tool(
            self.search_server,
            "web_search",
            {"query": query},
            timeout=30.0
        )

        return result
```

### Pattern 2: Kaizen Agent as MCP Server

**Use Case**: Expose Kaizen agent capabilities as MCP tools

#### Option A: BaseAgent Helper (Recommended)

```python
from kaizen.core.base_agent import BaseAgent
from kailash.mcp_server.auth import APIKeyAuth

class AnalysisAgent(BaseAgent):
    def start_as_server(self):
        """Expose agent as MCP server using BaseAgent helper."""
        # Create authentication
        auth = APIKeyAuth({"client1": "secret-key"})

        # Use BaseAgent helper (fixed in v0.9.19+)
        server = self.expose_as_mcp_server(
            server_name="analysis-agent",
            tools=["analyze_text", "summarize"],  # Agent methods to expose
            auth_provider=auth,
            enable_auto_discovery=True,
            enable_http_transport=True,
            enable_metrics=True
        )

        # Start server with auto-discovery
        if hasattr(self, '_mcp_registrar'):
            self._mcp_registrar.start_with_registration()
        else:
            server.run()

    async def analyze_text(self, text: str) -> dict:
        """Analyze text using agent (exposed as MCP tool)."""
        result = self.run(input_text=text)
        return {"analysis": result}

    async def summarize(self, text: str) -> dict:
        """Summarize text (exposed as MCP tool)."""
        result = self.run(input_text=text)
        return {"summary": result}
```

#### Option B: Direct MCPServer API (Full Control)

```python
from kaizen.core.base_agent import BaseAgent
from kailash.mcp_server import MCPServer, enable_auto_discovery
from kailash.mcp_server.auth import APIKeyAuth

class AnalysisAgent(BaseAgent):
    def expose_as_mcp_server(self):
        """Expose agent as MCP server with direct API."""
        # Create production server
        auth = APIKeyAuth({"client1": "secret-key"})

        server = MCPServer(
            name="analysis-agent",
            auth_provider=auth,
            enable_metrics=True,
            enable_http_transport=True
        )

        # Register agent methods as tools
        @server.tool()
        async def analyze_text(text: str) -> dict:
            """Analyze text using agent."""
            result = self.run(input_text=text)
            return {"analysis": result}

        # Enable auto-discovery
        registrar = enable_auto_discovery(
            server,
            enable_network_discovery=True
        )

        # Store references
        self._mcp_server = server
        self._mcp_registrar = registrar

        return server

    def start_server(self):
        """Start MCP server with auto-discovery."""
        if hasattr(self, '_mcp_registrar'):
            self._mcp_registrar.start_with_registration()
        elif hasattr(self, '_mcp_server'):
            self._mcp_server.run()
```

**When to Use Each**:
- **Option A (Helper)**: Quick setup, automatic tool registration, less boilerplate
- **Option B (Direct API)**: Fine-grained control, custom decorators, complex server setup

### Pattern 3: Service Discovery & Load Balancing

**Use Case**: Intelligent routing across multiple MCP servers

```python
from kailash.mcp_server import ServiceRegistry, ServiceMesh

class MultiServerAgent(BaseAgent):
    async def setup_service_mesh(self):
        """Setup service mesh for load balancing."""
        # Create service registry
        self.registry = ServiceRegistry()

        # Create service mesh
        self.mesh = ServiceMesh(self.registry)

        # Discover and register servers
        servers = await discover_mcp_servers(capability="compute")
        for server in servers:
            await self.registry.register(server)

    async def compute_with_failover(self, expression: str) -> dict:
        """Compute with automatic failover."""
        result = await self.mesh.call_with_failover(
            capability="compute",
            tool_name="calculate",
            arguments={"expression": expression},
            max_retries=3
        )

        return result
```

### Pattern 4: LLM Agent with Auto MCP Integration

**Use Case**: LLM automatically discovers and uses MCP tools (Built into LLMAgentNode)

```python
from kailash.nodes.llm_agent import LLMAgentNode

# Just configure - MCP integration is automatic
parameters = {
    "agent": {
        "llm_provider": "openai",
        "model": "gpt-4",

        # MCP configuration
        "mcp_servers": [
            {
                "name": "search-tools",
                "transport": "stdio",
                "command": "python",
                "args": ["search_server.py"]
            }
        ],

        # Auto-discovery features
        "auto_discover_tools": True,  # Discover tools automatically
        "auto_execute_tools": True,   # Execute tools when needed
        "tool_selection_strategy": "capability_match"
    }
}

# Agent automatically uses MCP tools
agent = LLMAgentNode(parameters=parameters)
```

---

## Testing Guide

### Unit Tests (Tier 1)

Test with mock MCP servers (fast, no external dependencies):

```python
import pytest
from kailash.mcp_server import SimpleMCPServer

@pytest.fixture
def mock_mcp_server():
    """Create mock MCP server for testing."""
    server = SimpleMCPServer("test-server")

    @server.tool()
    def add(a: int, b: int) -> dict:
        return {"result": a + b}

    return server

def test_agent_uses_mcp_tool(mock_mcp_server):
    """Test agent can use MCP tool."""
    # Test implementation
    pass
```

### Integration Tests (Tier 2)

Test with real MCP servers and real LLM providers:

```python
import pytest
from kailash.mcp_server import MCPClient

@pytest.mark.asyncio
async def test_real_mcp_integration():
    """Test real MCP client-server integration."""
    # Start real MCP server (in fixture)
    # Create real MCP client
    client = MCPClient(enable_metrics=True)

    # Discover tools
    tools = await client.discover_tools(server_config)
    assert len(tools) > 0

    # Call tool
    result = await client.call_tool(
        server_config,
        "add",
        {"a": 5, "b": 3}
    )

    assert result["success"]
    assert result["result"] == 8
```

### E2E Tests (Tier 3)

Test complete workflows with real infrastructure:

```python
@pytest.mark.e2e
async def test_agent_mcp_workflow():
    """Test complete agent workflow with MCP."""
    # Setup real MCP server
    # Setup Kaizen agent with MCP client
    # Execute real workflow
    # Verify results
    pass
```

See [testing-guide.md](./testing-guide.md) for comprehensive testing patterns.

---

## Migration Guide

### Migrating from `kaizen.mcp` to `kailash.mcp_server`

If you're using the deprecated `kaizen.mcp` module, migrate to `kailash.mcp_server`:

#### Before (Deprecated - Mocked Implementation)

```python
from kaizen.mcp import MCPConnection, MCPRegistry

# Mocked connection (string matching)
connection = MCPConnection(name="search-server", url="http://...")
connection.connect()  # No real connection

# Tools discovered via string matching
if "search" in connection.name:
    # Adds hardcoded tools
    pass

# Hardcoded responses
result = connection.call_tool("search", {"query": "AI"})
```

#### After (Recommended - Real Implementation)

```python
from kailash.mcp_server import MCPClient, discover_mcp_servers

# Real MCP client with production features
client = MCPClient(
    retry_strategy="circuit_breaker",
    enable_metrics=True
)

# Real service discovery
servers = await discover_mcp_servers(capability="search")

# Real tool discovery via JSON-RPC
tools = await client.discover_tools(servers[0])

# Real tool invocation
result = await client.call_tool(
    servers[0],
    "search",
    {"query": "AI"},
    timeout=30.0
)
```

### Breaking Changes

1. **Async API**: All MCP methods are now async (use `await`)
2. **Server Config Format**: Use dict or ServerInfo objects
3. **Tool Discovery**: Returns proper MCP tool schemas
4. **Error Handling**: Structured error codes and retry strategies

See [migration-guide.md](./migration-guide.md) for step-by-step migration instructions.

---

## Reference Documentation

### Core Guides

- **[Architecture](./architecture.md)** - MCP architecture and design decisions
- **[Implementation Guide](./implementation-guide.md)** - Detailed implementation patterns
- **[Quick Reference](./quick-reference.md)** - Common patterns and code snippets
- **[Testing Guide](./testing-guide.md)** - Comprehensive testing strategies
- **[Migration Guide](./migration-guide.md)** - Migrate from kaizen.mcp to kailash.mcp_server

### Kailash SDK Documentation

For comprehensive Kailash SDK MCP documentation, refer to the main Kailash repository:

- **MCP Server Implementation** - `src/kailash/mcp_server/` in Kailash SDK repository
- **API Reference** - Import docstrings: `from kailash.mcp_server import MCPClient, MCPServer`
- **Test Examples** - `tests/integration/mcp_server/` in Kailash SDK repository

### Example Implementations

- **[Agent-as-Client](../../../examples/5-mcp-integration/agent-as-client/)** - Agent consuming MCP tools
- **[Agent-as-Server](../../../examples/5-mcp-integration/agent-as-server/)** - Agent exposing MCP tools
- **[Auto-Discovery-Routing](../../../examples/5-mcp-integration/auto-discovery-routing/)** - Service discovery patterns
- **[Multi-Server-Orchestration](../../../examples/5-mcp-integration/multi-server-orchestration/)** - Load balancing & failover

---

## FAQ

### Q: Why use Kailash SDK MCP instead of creating our own?

**A**: Kailash SDK MCP is:
- Built on official Anthropic MCP SDK
- 100% MCP spec compliant
- Production-ready (407 tests, 100% pass rate)
- Includes enterprise features (auth, discovery, load balancing)
- Actively maintained as part of Kailash SDK

Following the principle "extend, not recreate" - we use the proven implementation.

### Q: Can I use MCP with synchronous code?

**A**: MCP protocol is async. For synchronous code, wrap async calls:

```python
import asyncio

def sync_call_tool(server, tool, args):
    """Synchronous wrapper for async MCP call."""
    return asyncio.run(client.call_tool(server, tool, args))
```

### Q: How do I authenticate with MCP servers?

**A**: Use auth providers:

```python
from kailash.mcp_server import MCPClient
from kailash.mcp_server.auth import APIKeyAuth

auth = APIKeyAuth({"user": "secret-key"})
client = MCPClient(auth_provider=auth)
```

### Q: How do I handle MCP server failures?

**A**: Use circuit breaker and retry strategies:

```python
client = MCPClient(
    retry_strategy="circuit_breaker",
    circuit_breaker_config={
        "failure_threshold": 5,
        "recovery_timeout": 30
    }
)
```

### Q: Can I use multiple MCP servers?

**A**: Yes, use ServiceMesh for load balancing:

```python
from kailash.mcp_server import ServiceRegistry, ServiceMesh

registry = ServiceRegistry()
mesh = ServiceMesh(registry)

result = await mesh.call_with_failover(
    capability="search",
    tool_name="web_search",
    arguments={"query": "AI"},
    max_retries=3
)
```

---

## Support

- **Issues**: [GitHub Issues](https://github.com/kailash/kaizen/issues)
- **Discussions**: [GitHub Discussions](https://github.com/kailash/kaizen/discussions)
- **Slack**: #kaizen-mcp channel

---

## Version Compatibility

| Kaizen Version | Kailash SDK Version | MCP Spec Version |
|---------------|---------------------|------------------|
| 0.9.x         | 0.9.19+            | 1.0              |
| 1.0.x         | 1.0.0+             | 1.0              |

**Last Updated**: 2025-10-04
**Maintainer**: Kaizen Team
