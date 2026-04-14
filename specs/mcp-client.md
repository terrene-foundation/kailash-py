# Kailash MCP Client Specification

Parent domain: MCP (Model Context Protocol). Companion files: `mcp-server.md`, `mcp-auth.md`.

Package: `kailash-mcp` v0.2.3
Install: `pip install kailash-mcp` (base) | `pip install kailash-mcp[full]` (all features)
License: Apache-2.0 | Terrene Foundation

This file specifies the **client side** of Kailash MCP: MCPClient, transport layer, service discovery, health checks, and tool hydration. See `mcp-server.md` for package layout/extras and `mcp-auth.md` for authentication providers consumed by the client.

---

## 1. MCPClient

`kailash_mcp.client.MCPClient` is the primary client for connecting to MCP servers.

### 1.1 Constructor

```python
MCPClient(
    config: Optional[Dict[str, Any]] = None,
    auth_provider: Optional[AuthProvider] = None,
    retry_strategy: Union[str, RetryStrategy] = "simple",
    enable_metrics: bool = False,
    enable_http_transport: bool = True,
    connection_timeout: float = 30.0,
    connection_pool_config: Optional[Dict[str, Any]] = None,
    enable_discovery: bool = False,
    circuit_breaker_config: Optional[Dict[str, Any]] = None,
)
```

**Parameters:**

- `config` -- Dictionary configuration; values are extracted as fallbacks for other constructor parameters. Keys: `auth_provider`, `enable_metrics`, `enable_http_transport`, `connection_timeout`.
- `auth_provider` -- An `AuthProvider` instance (APIKeyAuth, BearerTokenAuth, JWTAuth, BasicAuth). When set, the client wraps calls in an `AuthManager` with default `PermissionManager` and `RateLimiter`.
- `retry_strategy` -- One of `"simple"` (no retries), `"exponential"` (exponential backoff), `"circuit_breaker"`, or a `RetryStrategy` instance.
- `enable_metrics` -- Track request counts, failure counts, tool calls, resource accesses, average response time, and transport usage.
- `enable_http_transport` -- Allow HTTP/SSE transports (default `True`).
- `connection_timeout` -- Timeout in seconds for transport connections (default 30.0).
- `connection_pool_config` -- WebSocket connection pool settings. Keys: `max_connections` (default 10).
- `enable_discovery` -- Enable service discovery integration.
- `circuit_breaker_config` -- Passed to `CircuitBreakerRetry` constructor: `failure_threshold`, `timeout`, `success_threshold`.

### 1.2 Transport Resolution

The client auto-detects transport type from the server config:

| Config Shape                                 | Transport                |
| -------------------------------------------- | ------------------------ |
| String starting with `ws://` or `wss://`     | `websocket`              |
| String starting with `http://` or `https://` | `sse`                    |
| String (other)                               | `stdio`                  |
| Dict with `transport` key                    | Value of `transport` key |
| Dict without `transport` key                 | `stdio`                  |

### 1.3 Tool Discovery

```python
tools = await client.discover_tools(
    server_config: Union[str, Dict[str, Any]],
    force_refresh: bool = False,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]
```

Returns a list of tool definitions, each with keys: `name`, `description`, `parameters` (JSON Schema from `inputSchema`).

**Contract:**

- Results are cached by server key. Pass `force_refresh=True` to bypass cache.
- Each transport variant (STDIO, SSE, HTTP, WebSocket) creates a session, initializes it, calls `session.list_tools()`, and normalizes the result.
- If the retry operation is configured, discovery is wrapped in the retry strategy.
- On failure, returns an empty list (does not raise).
- Metrics are updated if enabled.

**STDIO server config shape:**

```python
{"command": "uvx", "args": ["mcp-server-sqlite"], "env": {"KEY": "val"}}
```

**SSE/HTTP server config shape:**

```python
{"url": "http://localhost:8080/mcp", "transport": "sse", "auth": {"type": "bearer", "token": "..."}}
```

### 1.4 Tool Execution

```python
result = await client.call_tool(
    server_config: Union[str, Dict[str, Any]],
    tool_name: str,
    arguments: Dict[str, Any],
    timeout: Optional[float] = None,
) -> Dict[str, Any]
```

**Return shape:**

```python
{"success": True, "content": "...", "result": <raw MCP result>, "tool_name": "..."}
# or on failure:
{"success": False, "error": "...", "tool_name": "..."}
```

**Contract:**

- If `auth_manager` is set, credentials are extracted from `server_config` and validated against `tools.execute` permission before the call proceeds.
- Authentication failure returns a dict with `success: False` and `error_code`, does not raise.
- Content is extracted from `result.content` items: text items are joined with newlines, non-text items are stringified.
- The retry operation wraps the transport-specific call if configured.
- On unhandled exception, returns `{"success": False, "error": "..."}`.

### 1.5 Resource Access

```python
resources = await client.list_resources(session: ClientSession) -> list[dict[str, Any]]
content = await client.read_resource(session: ClientSession, uri: Any) -> Any
```

These are session-based methods -- the caller must provide an active MCP `ClientSession`.

`list_resources` returns dicts with keys: `uri`, `name`, `description`, `mimeType`.

`read_resource` returns a list of content items. Each item is either `{"type": "text", "text": "..."}` or `{"type": "blob", "data": "..."}` depending on the content type.

### 1.6 Prompt Access

```python
prompts = await client.list_prompts(session: ClientSession) -> list[dict[str, Any]]
prompt = await client.get_prompt(session: ClientSession, name: str, arguments: dict) -> dict
```

`list_prompts` returns dicts with keys: `name`, `description`, `arguments` (list of `{name, description, required}`).

`get_prompt` returns `{"name": "...", "messages": [{"role": "...", "content": "..."}], "arguments": {...}}`.

### 1.7 Health Check

```python
health = await client.health_check(server_config) -> Dict[str, Any]
```

Returns `{"status": "healthy"|"unhealthy", "server": "...", "tools_available": N, "transport": "...", "metrics": ...}`.

Internally calls `discover_tools(force_refresh=True)` as the health probe.

### 1.8 WebSocket Connection Pooling

For WebSocket transport, the client maintains a connection pool keyed by URL.

- Pool capacity is bounded by `connection_pool_config["max_connections"]` (default 10).
- Unhealthy connections are evicted and replaced.
- LRU eviction when pool is full.
- Metrics track pool hits, pool misses, connections created, and connections reused.
- On error during a pooled call, the connection is removed from the pool.

### 1.9 Metrics

When `enable_metrics=True`, `client.get_metrics()` returns:

```python
{
    "requests_total": int,
    "requests_failed": int,
    "tools_called": int,
    "resources_accessed": int,
    "avg_response_time": float,
    "transport_usage": {"stdio": N, "sse": N, ...},
    "uptime": float,
    "start_time": float,
    # WebSocket pool metrics when applicable:
    "websocket_pool_hits": int,
    "websocket_pool_misses": int,
    "websocket_connections_created": int,
    "websocket_connections_reused": int,
}
```

---

## 2. Service Discovery

### 2.1 ServerInfo

```python
@dataclass
class ServerInfo:
    name: str
    transport: str                    # "stdio", "sse", "http"
    capabilities: List[str]           # Tool names or capability strings
    metadata: Dict[str, Any]
    id: Optional[str]                 # Auto-generated if None
    endpoint: Optional[str]           # URL or command
    command: Optional[str]            # STDIO transport
    args: Optional[List[str]]         # STDIO transport
    url: Optional[str]                # HTTP/SSE transport
    health_endpoint: Optional[str]
    health_status: str                # "healthy", "unhealthy", "unknown"
    health: Optional[Dict[str, Any]]
    last_seen: float                  # Auto-set to current time
    response_time: Optional[float]
    version: str                      # Default: "1.0.0"
    auth_required: bool               # Default: False
```

**Methods:**

- `is_healthy(max_age=300.0)` -- Checks health status and staleness. Server must have `health_status == "healthy"` and `last_seen` within `max_age` seconds.
- `matches_capability(capability)` -- Checks if server provides the capability.
- `matches_filter(**filters)` -- Matches against capability, transport, name, metadata, and arbitrary attributes.
- `get_priority_score()` -- Returns float score for load balancing. Factors: health (+0.5/-0.5), response time (+0.3/-0.3), age penalty (up to -0.4). Minimum score: 0.1.

### 2.2 DiscoveryBackend (Abstract)

```python
class DiscoveryBackend(ABC):
    async def register_server(self, server_info: ServerInfo) -> bool
    async def deregister_server(self, server_id: str) -> bool
    async def get_servers(self, **filters) -> List[ServerInfo]
    async def update_server_health(self, server_id, health_status, response_time=None) -> bool
```

### 2.3 FileBasedDiscovery

Persists server registry as a JSON file (`mcp_registry.json` by default). File format:

```json
{
    "servers": {"server_id": {...ServerInfo dict...}},
    "last_updated": 1234567890.0,
    "version": "1.0"
}
```

Creates the registry file on initialization if it doesn't exist. Reads and writes are synchronous (file I/O). Thread-safety is NOT guaranteed for concurrent writes.

### 2.4 NetworkDiscovery

UDP-based network discovery. Scans networks for MCP servers by broadcasting/probing. Supports:

- Network scanning (`scan_network(cidr)`)
- Specific port probing
- Multicast announcements
- mDNS-style discovery

### 2.5 ServiceRegistry

Aggregates multiple discovery backends:

```python
registry = ServiceRegistry(backends=[
    FileBasedDiscovery("registry.json"),
    NetworkDiscovery(),
])
```

Provides unified `register_server`, `deregister_server`, `discover_servers`, and `update_health` across all backends.

### 2.6 HealthChecker

Periodic health checking for registered servers. Configurable check interval and timeout. Updates server health status in the registry.

### 2.7 LoadBalancer

Selects servers from the registry based on priority scores (from `ServerInfo.get_priority_score()`). Supports:

- Weighted random selection
- Round-robin
- Least-connections
- Health-aware filtering

### 2.8 ServiceMesh

High-level abstraction combining registry, health checker, and load balancer:

```python
mesh = ServiceMesh(registry)
client = await mesh.get_client_for_capability("weather.get")
```

### 2.9 ServerRegistrar

Auto-registers an MCP server with the discovery system:

```python
registrar = ServerRegistrar(
    server: MCPServer,
    registry: Optional[ServiceRegistry] = None,
    auto_announce: bool = True,
    announce_interval: float = 30.0,
    enable_network_discovery: bool = False,
    server_metadata: Optional[Dict] = None,
)
registrar.start_with_registration()
```

Features:

- Automatic registration on startup.
- Periodic health announcements (default every 30s).
- Graceful deregistration on shutdown (atexit + signal handlers).
- Optional UDP network announcements via `NetworkAnnouncer`.

### 2.10 Convenience Functions

```python
registry = create_default_registry()          # FileBasedDiscovery("mcp_registry.json")
servers = discover_mcp_servers(**filters)      # Discover from default registry
client = get_mcp_client(capability="...")      # Get MCPClient for a capability
```

---

## 3. Transport Layer

Requires `pip install kailash-mcp[full]` (or specific transport extras).

### 3.1 TransportSecurity

URL validation utility:

```python
TransportSecurity.validate_url(url, allow_localhost=False)
```

- Validates URL scheme against allowed set: `http`, `https`, `ws`, `wss`.
- Blocks dangerous hosts: `169.254.169.254` (AWS metadata), `localhost`, `127.0.0.1` (unless `allow_localhost=True`).
- Basic DNS rebinding protection.

### 3.2 EnhancedStdioTransport

```python
transport = EnhancedStdioTransport(
    command="python",
    args=["-m", "my_server"],
    environment_filter=["PATH", "PYTHONPATH"],
)
async with transport:
    session = await transport.create_session()
```

Features: proper subprocess management, environment filtering, timeout handling.

### 3.3 SSETransport

```python
transport = SSETransport(
    base_url="https://api.example.com/mcp",
    auth_header="Bearer token123",
    validate_origin=True,
)
```

Server-Sent Events transport. Requires `aiohttp`.

### 3.4 StreamableHTTPTransport

```python
transport = StreamableHTTPTransport(
    base_url="https://api.example.com/mcp",
    session_management=True,
    streaming_threshold=1024,
)
```

HTTP transport with session management and streaming support. Uses `httpx` for the HTTP client.

### 3.5 WebSocketTransport / WebSocketServerTransport

Client-side WebSocket transport for connecting to WS-based MCP servers. Server-side `WebSocketServerTransport` handles incoming WebSocket connections with:

- Message routing to handler callbacks.
- Auth provider integration.
- Configurable timeout and max message size.
- Metrics collection.
- Gzip compression support (optional, with configurable threshold and level).

### 3.6 TransportManager

Manages multiple transports:

```python
manager = get_transport_manager()
```

---

## 4. Tool Hydration

`ToolHydrator` (in `tools/hydrator.py`) solves the problem of large tool sets overwhelming the LLM context.

### 4.1 How It Works

When total tool count exceeds the threshold (default 30):

1. **Base tools** (~15, configurable) are always sent to the LLM. Default base set: `file_read`, `file_write`, `file_edit`, `glob`, `grep`, `bash`, `search_tools`.
2. **Deferred tools** are indexed but not sent until the LLM calls `search_tools`.
3. Search uses BM25 scoring (stdlib-only implementation) to rank deferred tools by relevance.

Below threshold, all tools are passed directly.

### 4.2 BM25 Scoring

Each tool is indexed as a document with tokens from its name and description. Queries are tokenized and scored using the BM25 formula with parameters `k1=1.5`, `b=0.75`. The hydrator returns the top-N matches.

---

## 5. Client-Side Edge Cases and Constraints

### 5.1 Client-Side

- **Empty tool discovery:** Returns empty list `[]` on any error, never raises. Caller must check list length.
- **Tool call failure:** Returns `{"success": False, ...}` dict, never raises. Caller must check `success` key.
- **WebSocket pool exhaustion:** LRU eviction when `max_connections` is reached. Evicted connections are closed asynchronously via `asyncio.create_task` to avoid cross-task errors.
- **Timeout handling:** All transport-specific calls support `asyncio.wait_for` with the configured timeout.

### 5.2 Discovery

- **FileBasedDiscovery:** Not thread-safe for concurrent writes. Suitable for single-process scenarios.
- **NetworkDiscovery:** UDP-based, unreliable by nature. Use file-based discovery for production.
- **Health staleness:** `ServerInfo.is_healthy()` has a default `max_age` of 300 seconds. Servers not seen within this window are considered unhealthy regardless of last known status.

### 5.3 Tool Hydration

- Below threshold (30 tools), hydration is inactive -- all tools pass through.
- BM25 scoring is pure stdlib (no external dependency). Tokenization splits on `[a-z0-9]+` boundaries.
- The `search_tools` meta-tool is always in the base set.
