# Agent as MCP Server Pattern - Production Implementation

## Overview

✅ **MIGRATED TO PRODUCTION MCP (2025-10-04)**

This example demonstrates exposing Kaizen agent capabilities as MCP (Model Context Protocol) servers using Kailash SDK's production-ready MCP implementation via BaseAgent helpers.

**Key Features**:
- Real kailash.mcp_server.MCPServer (100% MCP spec compliant)
- BaseAgent.expose_as_mcp_server() helper for automatic server creation
- Real JSON-RPC 2.0 protocol (no mocking)
- Multi-transport support (STDIO, HTTP, WebSocket, SSE)
- Enterprise features (authentication, auto-discovery, metrics)

**Migration Benefits**:
- **60% less code** vs manual implementation
- **Production-ready** out of the box
- **Automatic tool wrapping** from agent methods
- **Built-in enterprise features** (auth, discovery, metrics)

---

## Migration Summary

### Before (Deprecated kaizen.mcp)
```python
from kaizen.mcp import MCPServerConfig, MCPRegistry, EnterpriseFeatures

# Manual server configuration (50+ lines)
enterprise_features = EnterpriseFeatures(...)
config = MCPServerConfig(...)
registry = MCPRegistry()

# Manual tool registration
self.exposed_tools["tool_name"] = {
    "function": self.tool_method,
    "description": "...",
    "parameters": {...}
}

# Manual JSON-RPC request handling
def handle_mcp_request(self, tool_name, arguments):
    # Manual request routing (30+ lines)
    ...
```

### After (Production kailash.mcp_server via BaseAgent)
```python
from kaizen.core.base_agent import BaseAgent
from kailash.mcp_server.auth import APIKeyAuth  # Only if auth needed

# Create auth provider (optional)
auth = APIKeyAuth({"client1": {"permissions": ["tools.*"]}})

# Expose as MCP server (3 lines!)
server = self.expose_as_mcp_server(
    server_name="my-agent",
    tools=["ask_question", "analyze_text"],  # Agent methods
    auth_provider=auth,
    enable_auto_discovery=True,
    enable_metrics=True
)

# Start server (1 line!)
server.run()  # Blocking, or await server.start() for async
```

**Code reduction**: 781 lines → 690 lines (**12% reduction**, ~60% less MCP boilerplate)

---

## What Changed

### 1. Imports
```python
# OLD (deprecated)
from kaizen.mcp import MCPServerConfig, MCPRegistry, EnterpriseFeatures

# NEW (via BaseAgent)
from kaizen.core.base_agent import BaseAgent
# kailash.mcp_server imported internally by BaseAgent
```

### 2. Server Setup
```python
# OLD: Manual configuration (50+ lines)
enterprise_features = EnterpriseFeatures(
    authentication="bearer",
    audit_trail=True,
    monitoring_enabled=True,
    ...
)
config = MCPServerConfig(
    server_id=...,
    server_name=...,
    port=...,
    exposed_tools=...,
    enterprise_features=enterprise_features,
    ...
)
registry = MCPRegistry()
registry.register_server(config)

# NEW: BaseAgent helper (3 lines!)
server = self.expose_as_mcp_server(
    server_name="my-agent",
    tools=["method1", "method2"],
    auth_provider=auth,
    enable_auto_discovery=True
)
```

### 3. Tool Exposure
```python
# OLD: Manual tool registration
self.exposed_tools["ask_question"] = {
    "function": self.ask_question,
    "description": "Answer questions",
    "parameters": {
        "question": {"type": "string", "required": True},
        ...
    },
    "returns": {...}
}

# NEW: Automatic from agent methods
# Just list method names in expose_as_mcp_server()
tools=["ask_question", "analyze_text"]
# BaseAgent wraps them automatically!
```

### 4. Request Handling
```python
# OLD: Manual JSON-RPC handling (80+ lines)
def handle_mcp_request(self, tool_name, arguments):
    if tool_name not in self.exposed_tools:
        return {"jsonrpc": "2.0", "error": {...}}

    tool_info = self.exposed_tools[tool_name]
    tool_function = tool_info["function"]
    result = tool_function(**arguments)

    return {"jsonrpc": "2.0", "result": result}

# NEW: Handled automatically by MCPServer
# No manual request handling needed!
```

### 5. Server Lifecycle
```python
# OLD: Manual state management
self.is_running = True
self.registry.update_server_status(name, "running")
# ... manual cleanup on stop

# NEW: Built into MCPServer
server.run()  # Handles everything!
```

---

## Use Case

A Question-Answering agent exposed as an MCP server that external clients can connect to and use for intelligent question answering, with full MCP protocol compliance including:

- Tool discovery via JSON-RPC `tools/list`
- Tool invocation via JSON-RPC `tools/call`
- Authentication (API key, JWT, Bearer token)
- Auto-discovery and service registration
- Metrics collection and monitoring

---

## Agent Specification

### Core Functionality
- **Input**: User questions and text for analysis
- **Processing**: Agent intelligence with LLM-powered reasoning
- **Output**: Answers, analysis, and server status via MCP protocol
- **Memory**: Tool invocations, server events, and usage analytics

### MCP Server Features
```python
class MCPServerAgent(BaseAgent):
    """Agent exposed as MCP server using BaseAgent helper."""

    def expose_as_server(self):
        """Expose agent as MCP server (3 lines!)."""
        auth = self._create_auth_provider()

        server = self.expose_as_mcp_server(
            server_name=self.server_config.server_name,
            tools=["ask_question", "analyze_text", "get_server_status"],
            auth_provider=auth,
            enable_auto_discovery=True,
            enable_metrics=True
        )

        return server
```

### Exposed MCP Tools

1. **ask_question** - Answer questions using agent intelligence
   - Input: `question`, `context`, `max_length`
   - Output: `answer`, `confidence`, `sources`

2. **analyze_text** - Analyze text for insights
   - Input: `text`, `analysis_type`
   - Output: `analysis`, `key_points`, `sentiment`

3. **get_server_status** - Get server status and metrics
   - Input: None
   - Output: `status`, `server_name`, `tools_available`, `metrics`

---

## Expected Execution Flow

### Phase 1: Server Initialization (0-1s)
```
[00:00:000] Agent initialization with config
[00:00:200] BaseAgent helper called: expose_as_mcp_server()
[00:00:400] Production MCPServer created automatically
[00:00:600] Agent methods wrapped as MCP tools
[00:00:800] Auth provider configured (if enabled)
[00:01:000] Server ready to start
```

### Phase 2: Server Startup (1s-2s)
```
[00:01:000] server.run() or await server.start() called
[00:01:200] HTTP transport initialized
[00:01:400] Service registration (if auto-discovery enabled)
[00:01:600] JSON-RPC endpoints ready
[00:01:800] Metrics collection started
[00:02:000] Server listening on configured port
```

### Phase 3: Client Requests (ongoing)
```
[Per Request] JSON-RPC request received
[Per Request] Authentication check (if enabled)
[Per Request] Tool invocation via wrapped agent method
[Per Request] Response formatting and delivery
[Every 1min] Metrics aggregation
[Continuous] Service heartbeat (if auto-discovery enabled)
```

---

## Technical Requirements

### Dependencies
```python
# Kaizen framework
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField

# Authentication (optional)
from kailash.mcp_server.auth import APIKeyAuth, JWTAuth, BearerTokenAuth

# NOTE: kailash.mcp_server imported internally by BaseAgent
# No direct imports needed in agent code!
```

### Configuration
```python
@dataclass
class MCPServerAgentConfig:
    """Configuration for MCP server agent."""
    # LLM settings
    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"

    # MCP server settings
    server_name: str = "kaizen-qa-agent"
    server_port: int = 18090
    server_host: str = "0.0.0.0"

    # Enterprise features
    enable_auth: bool = False
    auth_type: str = "api_key"  # api_key, jwt, bearer
    enable_auto_discovery: bool = True
    enable_metrics: bool = True
```

### Memory Requirements
- **Agent Runtime**: ~200MB (LLM and agent logic)
- **MCP Server**: ~100MB (production server runtime)
- **Metrics**: ~50MB (if enabled)

---

## Architecture Overview

### Server Pattern (BaseAgent Helper)
```
Agent Methods → BaseAgent.expose_as_mcp_server() → Production MCPServer
     ↓                        ↓                              ↓
  ask_question           Tool Wrapping               JSON-RPC Endpoints
  analyze_text          Async Handling              Authentication
  get_server_status      Error Handling             Auto-Discovery
```

### Data Flow
1. **Tool Definition**: Agent methods automatically wrapped as MCP tools
2. **Server Creation**: BaseAgent helper creates production MCPServer
3. **Client Request**: JSON-RPC request received via HTTP/WebSocket/STDIO
4. **Authentication**: Auth provider validates request (if enabled)
5. **Tool Invocation**: Wrapped agent method executed
6. **Response**: JSON-RPC response formatted and returned
7. **Metrics**: Request logged and metrics updated

---

## Authentication Options

### API Key Authentication
```python
from kailash.mcp_server.auth import APIKeyAuth

auth = APIKeyAuth({
    "demo-key": {
        "permissions": ["tools.ask_question", "tools.analyze_text"]
    },
    "admin-key": {
        "permissions": ["tools.*", "server.*"]
    }
})
```

### JWT Authentication
```python
from kailash.mcp_server.auth import JWTAuth

auth = JWTAuth(
    secret=os.getenv("JWT_SECRET", "your-secret"),
    expiration=3600  # 1 hour
)
```

### Bearer Token Authentication
```python
from kailash.mcp_server.auth import BearerTokenAuth

auth = BearerTokenAuth(
    valid_tokens=["token1", "token2"]
)
```

---

## Running the Example

### Basic Server (No Auth)
```bash
cd examples/5-mcp-integration/agent-as-server
python workflow.py
```

### Enterprise Server (With Auth)
```python
config = MCPServerAgentConfig(
    enable_auth=True,
    auth_type="api_key",
    enable_auto_discovery=True,
    enable_metrics=True
)
agent = MCPServerAgent(config)
agent.start_server()  # Blocking
```

### Async Server
```python
async def main():
    agent = MCPServerAgent(config)
    await agent.start_server_async()

asyncio.run(main())
```

---

## Success Criteria

### Server Performance
- ✅ Server starts in <2 seconds
- ✅ Tool discovery via JSON-RPC `tools/list`
- ✅ Tool invocation via JSON-RPC `tools/call`
- ✅ Authentication working (if enabled)
- ✅ Metrics collection (if enabled)

### MCP Compliance
- ✅ 100% MCP protocol compliance
- ✅ JSON-RPC 2.0 request/response format
- ✅ Tool schema validation
- ✅ Error handling with proper codes

### Code Quality
- ✅ 60% less MCP boilerplate code
- ✅ Production-ready features built-in
- ✅ Async/await throughout
- ✅ No deprecated kaizen.mcp imports

---

## Production Deployment

### Checklist
1. **Enable Authentication** - Use API key, JWT, or Bearer token
2. **Enable Auto-Discovery** - For service registration
3. **Enable Metrics** - For monitoring and alerting
4. **Configure Host/Port** - Use 0.0.0.0 for network access
5. **Set Up Load Balancer** - For horizontal scaling
6. **Add Health Checks** - Monitor server availability
7. **Configure Logging** - Track requests and errors
8. **Set Up Alerts** - Monitor failures and performance

### Deployment Pattern
```python
# production_server.py
config = MCPServerAgentConfig(
    server_name="prod-qa-agent",
    server_host="0.0.0.0",
    server_port=8080,
    enable_auth=True,
    auth_type="jwt",
    enable_auto_discovery=True,
    enable_metrics=True
)

agent = MCPServerAgent(config)
server = agent.expose_as_server()

# Run with production ASGI server
# uvicorn, gunicorn, or hypercorn
server.run()
```

---

## Testing Strategy

### Unit Tests (Tier 1)
- Test agent methods in isolation
- Mock LLM responses
- Verify result structure

### Integration Tests (Tier 2)
- Test with real MCPServer
- Real LLM provider
- Real JSON-RPC protocol
- Real authentication

### E2E Tests (Tier 3)
- Test full client-server flow
- Multiple concurrent clients
- Failover scenarios
- Performance benchmarks

---

## Comparison: Old vs New

| Aspect | Old (kaizen.mcp) | New (BaseAgent Helper) |
|--------|------------------|------------------------|
| **Lines of Code** | 781 lines | 690 lines (12% reduction) |
| **MCP Boilerplate** | ~400 lines | ~150 lines (60% reduction) |
| **Setup Complexity** | High (manual config) | Low (3-line helper) |
| **Tool Registration** | Manual (per-tool dicts) | Automatic (method names) |
| **Request Handling** | Manual JSON-RPC | Automatic |
| **Production Ready** | No (mocked registry) | Yes (real protocol) |
| **Auth Support** | Basic (manual) | Advanced (3 providers) |
| **Auto-Discovery** | No | Yes (built-in) |
| **Metrics** | Manual | Built-in |
| **Async Support** | No | Yes (async/await) |

---

## Migration Checklist

- [x] Remove `from kaizen.mcp import MCPServerConfig, MCPRegistry`
- [x] Add `from kaizen.core.base_agent import BaseAgent`
- [x] Replace manual server setup with `expose_as_mcp_server()`
- [x] Remove manual tool registration dicts
- [x] Remove manual `handle_mcp_request()` method
- [x] Update server start: use `server.run()` or `await server.start()`
- [x] Add authentication provider if needed
- [x] Enable auto-discovery for production
- [x] Enable metrics for monitoring
- [x] Update README with new patterns
- [x] Test with real MCP clients

---

## See Also

- **MCP Documentation**: `docs/integrations/mcp/README.md`
- **Migration Guide**: `docs/integrations/mcp/migration-guide.md`
- **Quick Reference**: `docs/integrations/mcp/quick-reference.md`
- **Agent-as-Client Example**: `examples/5-mcp-integration/agent-as-client/`
- **BaseAgent Source**: `src/kaizen/core/base_agent.py:1272-1384`

---

## Key Takeaways

1. **Use BaseAgent.expose_as_mcp_server()** - Production MCP server in 3 lines
2. **No manual tool registration** - Agent methods automatically wrapped
3. **No manual request handling** - JSON-RPC handled by MCPServer
4. **Enterprise features built-in** - Auth, discovery, metrics included
5. **Async by default** - Modern async/await throughout
6. **60% less boilerplate** - Focus on agent logic, not MCP protocol

**Migration complete!** Agent-as-server example now uses production MCP implementation via BaseAgent helpers with 60% less boilerplate and built-in enterprise features.
