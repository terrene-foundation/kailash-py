# MCP Implementations Audit

## Brief Claim: "6 separate MCP server implementations"

### Verified MCP Server/Transport Implementations

After comprehensive search across both `packages/kailash-nexus/` and `src/kailash/`, here are ALL MCP-related server implementations:

| #   | Location                                                                                                | Type                                                     | Status                                  | Delete in B0b? |
| --- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | --------------------------------------- | -------------- |
| 1   | `nexus/mcp/server.py` — `MCPServer`                                                                     | Simple MCP server (WebSocket, manual JSON-RPC)           | WebSocket-only fallback                 | YES            |
| 2   | `nexus/mcp/transport.py` — `MCPTransport` (ABC), `WebSocketServerTransport`, `WebSocketClientTransport` | Transport layer for WebSocket MCP                        | Server+client transports                | YES            |
| 3   | `nexus/mcp_websocket_server.py` — `MCPWebSocketServer`                                                  | WebSocket wrapper for Core SDK MCP server                | Wraps MCPServer with WebSocket handling | YES            |
| 4   | `src/kailash/mcp_server/server.py` — `MCPServerBase`                                                    | Core SDK abstract MCP server (STDIO/HTTP/SSE)            | Foundation class, KEEP                  | NO             |
| 5   | `src/kailash/middleware/mcp/enhanced_server.py` — `MiddlewareMCPServer`                                 | Core SDK middleware MCP server with auth/caching/metrics | Enterprise features, KEEP               | NO             |
| 6   | `src/kailash/channels/mcp_channel.py` — `MCPChannel`                                                    | Core SDK channel wrapper                                 | Channel abstraction, KEEP               | NO             |

### Nexus-Specific MCP Code (3 files, ALL deleted in B0b)

**1. `nexus/mcp/server.py`** (430 lines)

- Simple MCP server using raw `websockets` library
- Manual JSON-RPC message handling
- Direct `self._workflows` dict, manual tool/resource registration
- No auth, no caching, no metrics
- Used as fallback when `enable_http_transport=False`

**2. `nexus/mcp/transport.py`** (380 lines)

- Abstract `MCPTransport` base class (NOT the Transport ABC from the refactor)
- `WebSocketServerTransport` — raw WebSocket server
- `WebSocketClientTransport` — client for testing
- Uses deprecated `WebSocketServerProtocol` from websockets

**3. `nexus/mcp_websocket_server.py`** (250+ lines)

- `MCPWebSocketServer` — wraps Core SDK's MCPServer with WebSocket handling
- Manual JSON-RPC parsing
- Duplicates much of `mcp/server.py` functionality

### Core SDK MCP Code (3 components, ALL kept)

**4. `src/kailash/mcp_server/server.py`** — `MCPServerBase`

- Abstract base for MCP servers with tool/resource/prompt registration
- Support for STDIO, HTTP, SSE transports
- Used as base class by various Core SDK servers

**5. `src/kailash/middleware/mcp/enhanced_server.py`** — `MiddlewareMCPServer`

- Full enterprise MCP server with auth, caching, metrics, circuit breaker
- Used in `core.py`'s `_create_sdk_mcp_server()` method (line 596)

**6. `src/kailash/channels/mcp_channel.py`** — `MCPChannel`

- Channel abstraction used when `enable_http_transport=True`
- Wraps the enhanced MCP server

### How core.py Selects MCP Server

```python
# Line 395-443: _initialize_mcp_server()
if not self._enable_http_transport:
    # WebSocket-only mode -> nexus.mcp.MCPServer (simple, #1)
    self._mcp_server = MCPServer(host, port, runtime)
else:
    try:
        # Full mode -> Core SDK's MiddlewareMCPServer (#5) + MCPChannel (#6)
        self._mcp_server = self._create_sdk_mcp_server()
        self._mcp_channel = self._setup_mcp_channel()
    except ImportError:
        # Fallback -> nexus.mcp.MCPServer (simple, #1)
        self._mcp_server = MCPServer(host, port, runtime)
```

### Verdict

The brief's "6 implementations" claim is **correct** if counting all MCP-related classes across both packages. The consolidation plan (delete #1, #2, #3; keep #4, #5, #6; replace with single FastMCP-backed `MCPTransport`) is sound.

### Risk: Deprecating `websockets` Dependency

Files #1, #2, #3 all depend on the `websockets` library. After deletion in B0b, check whether `websockets` can be removed from `kailash-nexus` dependencies (it may still be needed by Core SDK MCP code).
