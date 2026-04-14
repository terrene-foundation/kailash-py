# Kailash MCP Server Specification

Parent domain: MCP (Model Context Protocol). Companion files: `mcp-client.md`, `mcp-auth.md`.

Package: `kailash-mcp` v0.2.3
Install: `pip install kailash-mcp` (base) | `pip install kailash-mcp[full]` (all features)
License: Apache-2.0 | Terrene Foundation

Kailash MCP is the production-ready Model Context Protocol implementation for the Kailash SDK. It provides an MCP client, server, authentication framework, service discovery, transport layer, and a platform server for unified project introspection by AI assistants.

The package builds on the official Anthropic `mcp` Python SDK (`mcp[cli]>=1.23.0`) and extends it with authentication, caching, retry strategies, circuit breakers, metrics, service discovery, rate limiting, and a contributor plugin system for framework-specific tool registration.

This file specifies the **server side**: MCPServer, tool/resource/prompt registration, execution pipeline, platform server, contributor plugins, and the advanced server features (structured tools, multi-modal content, resource templates, subscriptions).

---

## 1. Package Structure

```
kailash_mcp/
  __init__.py            -- Public API surface, version, conditional imports
  client.py              -- MCPClient: multi-transport client with retries
  server.py              -- MCPServer, MCPServerBase, SimpleMCPServer
  errors.py              -- Error hierarchy, retry strategies, circuit breaker
  platform_server.py     -- FastMCP-based platform server with contributor plugins
  auth/
    providers.py         -- APIKeyAuth, BearerTokenAuth, JWTAuth, BasicAuth, AuthManager
    oauth.py             -- OAuth 2.1 authorization/resource server (optional extra)
  discovery/
    discovery.py         -- ServiceRegistry, FileBasedDiscovery, NetworkDiscovery, LoadBalancer
    registry_integration.py -- ServerRegistrar, NetworkAnnouncer, auto-discovery
  protocol/
    protocol.py          -- ProgressManager, CancellationManager, CompletionManager, SamplingManager
    messages.py          -- Protocol message definitions
  advanced/
    features.py          -- StructuredTool, MultiModalContent, SchemaValidator, streaming, progress
    subscriptions.py     -- ResourceSubscriptionManager, transformers
    resource_cache.py    -- Mtime-based resource cache for platform discovery
  transports/
    transports.py        -- EnhancedStdioTransport, SSETransport, StreamableHTTPTransport, WebSocketTransport
  tools/
    hydrator.py          -- ToolHydrator: BM25-based deferred tool loading for large tool sets
  contrib/
    __init__.py          -- SecurityTier enum, is_tier_enabled()
    core.py              -- Core SDK node discovery (AST-based)
    dataflow.py          -- DataFlow model discovery (AST-based)
    nexus.py             -- Nexus handler discovery (AST-based)
    kaizen.py            -- Kaizen agent discovery (AST-based)
    platform.py          -- Cross-framework platform map
    trust.py             -- Trust plane status
    pact.py              -- PACT org hierarchy
    ai_registry.py       -- AI model registry
  utils/
    cache.py             -- CacheManager, LRUCache, cached_query
    config.py            -- ConfigManager (hierarchical, env overrides)
    formatters.py        -- Response formatters (JSON, markdown, table, search)
    metrics.py           -- MetricsCollector
```

### Optional Extras

| Extra        | Packages Added                                        | Use Case                       |
| ------------ | ----------------------------------------------------- | ------------------------------ |
| `http`       | `aiohttp>=3.12.4`, `httpx>=0.25.0`                    | HTTP/Streamable HTTP transport |
| `sse`        | `aiohttp>=3.12.4`                                     | SSE transport                  |
| `websocket`  | `websockets>=12.0`                                    | WebSocket transport            |
| `auth-jwt`   | `PyJWT>=2.8`, `cryptography>=41.0`                    | JWT authentication             |
| `auth-oauth` | `PyJWT>=2.8`, `cryptography>=41.0`, `aiohttp>=3.12.4` | OAuth 2.1 server/client        |
| `server`     | `fastapi>=0.115.12`, `uvicorn>=0.31.0`                | FastAPI-based server           |
| `platform`   | `fastapi>=0.115.12`, `uvicorn>=0.31.0`                | Platform server                |
| `full`       | All of the above                                      | Everything                     |

Base dependencies: `kailash>=2.8.5`, `mcp[cli]>=1.23.0`, `pydantic>=2.6`.

---

## 2. MCPServer

`kailash_mcp.server.MCPServer` is the production server with authentication, caching, metrics, circuit breakers, and multi-transport support.

### 2.1 Constructor

```python
MCPServer(
    name: str,
    config_file: Optional[Union[str, Path]] = None,
    transport: str = "stdio",              # "stdio", "websocket", "http", "sse"
    websocket_host: str = "127.0.0.1",
    websocket_port: int = 3001,
    enable_cache: bool = True,
    cache_ttl: int = 300,
    cache_backend: str = "memory",         # "memory" or "redis"
    cache_config: Optional[Dict] = None,   # {"redis_url": "...", "prefix": "mcp:"}
    enable_metrics: bool = True,
    enable_formatting: bool = True,
    enable_monitoring: bool = False,
    auth_provider: Optional[AuthProvider] = None,
    enable_http_transport: bool = False,
    enable_sse_transport: bool = False,
    rate_limit_config: Optional[Dict] = None,
    circuit_breaker_config: Optional[Dict] = None,
    enable_discovery: bool = False,
    connection_pool_config: Optional[Dict] = None,
    error_aggregation: bool = True,
    transport_timeout: float = 30.0,
    max_request_size: int = 10_000_000,    # 10MB
    enable_streaming: bool = False,
    enable_subscriptions: bool = True,
    event_store: Optional[Any] = None,
    enable_websocket_compression: bool = False,
    compression_threshold: int = 1024,
    compression_level: int = 6,
)
```

### 2.2 Tool Registration

```python
@server.tool(
    cache_key: Optional[str] = None,
    cache_ttl: Optional[int] = None,
    format_response: Optional[str] = None,       # "json", "markdown", "table"
    required_permission: Optional[str] = None,
    required_permissions: Optional[List[str]] = None,
    rate_limit: Optional[Dict] = None,
    enable_circuit_breaker: bool = True,
    timeout: Optional[float] = None,
    retryable: bool = True,
    stream_response: bool = False,
)
```

**Contract:**

- Cannot specify both `required_permission` and `required_permissions` (raises `ValueError`).
- The decorator wraps both sync and async functions. Async detection uses `asyncio.iscoroutinefunction`.
- Each tool call gets a unique session ID for tracking.

**Execution pipeline (in order):**

1. **Authentication** -- If `auth_manager` is set and `required_permission` is specified, credentials are extracted from kwargs (fields: `api_key`, `token`, `username`, `password`, `jwt`, `authorization`, `mcp_auth`). Auth failure raises `ToolError`. For async tools, if no credentials are provided and no `mcp_*` kwargs exist, the call is allowed (development/testing mode).
2. **Rate limiting** -- If `rate_limit` is set and `auth_manager` exists, `check_rate_limit` is called for the authenticated user. Failure raises `RateLimitError`.
3. **Circuit breaker** -- If `enable_circuit_breaker=True` and a circuit breaker is configured, checks circuit state. Open circuit raises `MCPError` with code `CIRCUIT_BREAKER_OPEN`.
4. **Cache lookup** -- If `cache_key` is set and caching is enabled, checks the cache. On hit, returns immediately. Supports both memory and Redis backends. For async tools, uses `cache.get_or_compute()` with stampede prevention.
5. **Execution** -- Calls the wrapped function. For sync tools, `signal.SIGALRM` timeout is used. For async tools, `asyncio.wait_for` is used. Auth credential fields are stripped from kwargs before calling the function.
6. **Cache store** -- On success, caches the result.
7. **Metrics** -- Tracks latency, success/failure counts.
8. **Circuit breaker update** -- Records success or failure.
9. **Response formatting** -- Applies format if `format_response` is set. Optionally chunks large responses for streaming.

### 2.3 Resource Registration

```python
@server.resource(uri: str)
def handler(path: str) -> str: ...
```

Resources are registered with FastMCP's `resource(uri)` decorator. Metrics tracking is applied if enabled. URI supports patterns.

### 2.4 Prompt Registration

```python
@server.prompt(name: str)
def handler(data: str) -> str: ...
```

Prompts are registered with FastMCP's `prompt(name)` decorator. Metrics tracking is applied if enabled.

### 2.5 Server Lifecycle

```python
server.run()
```

**STDIO mode (default):** Delegates to `FastMCP.run()`.

**WebSocket mode:** Starts `WebSocketServerTransport` on `websocket_host:websocket_port`. Routes incoming JSON-RPC messages to handlers for: `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `resources/subscribe`, `resources/unsubscribe`, `resources/batch_subscribe`, `resources/batch_unsubscribe`, `prompts/list`, `prompts/get`, `logging/setLevel`, `roots/list`, `completion/complete`, `sampling/createMessage`.

**Startup sequence:**

1. Initialize FastMCP if not already done.
2. Record start time in config.
3. Perform health check (logs warnings if degraded).
4. Start transport.

**Shutdown:**

1. Clear active sessions.
2. Log final metrics.
3. Set `_running = False`.

### 2.6 FastMCP Initialization

The server tries to import FastMCP in this order:

1. `from fastmcp import FastMCP` (independent package)
2. `from mcp.server import FastMCP` (official MCP package)
3. Fallback: minimal compatible wrapper (tools/resources/prompts register but `run()` raises `NotImplementedError`)

### 2.7 Administration API

```python
server.get_tool_stats() -> Dict         # Tool registry statistics
server.get_server_stats() -> Dict       # Comprehensive server stats
server.get_resource_stats() -> Dict     # Resource registry stats
server.get_prompt_stats() -> Dict       # Prompt registry stats
server.get_active_sessions() -> Dict    # Active session info
server.health_check() -> Dict           # Component health status
server.get_error_trends() -> List       # Error trends over time
server.clear_cache(name=None)           # Clear specific or all caches
server.reset_circuit_breaker()          # Reset to closed state
server.terminate_session(session_id)    # Terminate a session
server.disable_tool(tool_name) -> bool  # Temporarily disable a tool
server.enable_tool(tool_name) -> bool   # Re-enable a disabled tool
```

### 2.8 MCPServerBase

Abstract base class for simpler custom servers:

```python
class MyServer(MCPServerBase):
    def setup(self):
        @self.add_tool()
        def calculate(a: int, b: int) -> int:
            return a + b

        @self.add_resource("data://example")
        def get_example():
            return "Example data"

        @self.add_prompt("analyze")
        def analyze_prompt(data: str) -> str:
            return f"Analyze: {data}"

server = MyServer("my-server", port=8080)
server.start()
```

Delegates to FastMCP. Provides `add_tool()`, `add_resource(uri)`, `add_prompt(name)` decorators.

---

## 3. Platform Server

The `kailash-mcp` CLI entry point (`kailash_mcp.platform_server:main`) creates a FastMCP server that auto-discovers installed Kailash frameworks and registers namespace-prefixed tools.

### 3.1 Usage

```bash
kailash-mcp                                    # STDIO transport, cwd as project root
kailash-mcp --project-root /path/to/project    # Explicit project root
kailash-mcp --transport sse --port 8900        # SSE transport
```

Project root resolution: CLI `--project-root` > `KAILASH_PROJECT_ROOT` env var > cwd.

### 3.2 Contributor Plugin System

Contributors are registered in `FRAMEWORK_CONTRIBUTORS`:

| Module                         | Namespace  | Dependency              |
| ------------------------------ | ---------- | ----------------------- |
| `kailash_mcp.contrib.core`     | `core`     | Always available        |
| `kailash_mcp.contrib.platform` | `platform` | Always available        |
| `kailash_mcp.contrib.dataflow` | `dataflow` | `kailash-dataflow`      |
| `kailash_mcp.contrib.nexus`    | `nexus`    | `kailash-nexus`         |
| `kailash_mcp.contrib.kaizen`   | `kaizen`   | `kailash-kaizen`        |
| `kailash_mcp.contrib.trust`    | `trust`    | `kailash` (trust plane) |
| `kailash_mcp.contrib.pact`     | `pact`     | `kailash-pact`          |

Each contributor implements:

```python
def register_tools(server: FastMCP, project_root: Path, namespace: str) -> None:
```

**Contract:**

- All tool names MUST start with `{namespace}.` prefix. The platform server validates this and logs warnings for violations.
- `register_tools` MUST be synchronous and non-blocking. No network calls or heavy computation during registration.
- Contributors that fail to import (framework not installed) are skipped gracefully with an INFO log.
- Contributors that raise during registration are logged at ERROR and skipped.

### 3.3 Security Tiers

```python
class SecurityTier(IntEnum):
    INTROSPECTION = 1    # Read-only discovery (always enabled)
    SCAFFOLD = 2         # Code generation scaffolds (always enabled)
    VALIDATION = 3       # Validation/linting (enabled by default)
    EXECUTION = 4        # Code execution (disabled by default)
```

Environment variable control:

- `KAILASH_MCP_ENABLE_VALIDATION=false` -- Disables Tier 3.
- `KAILASH_MCP_ENABLE_EXECUTION=true` -- Enables Tier 4.

Tiers 1 and 2 are always enabled.

### 3.4 Contributor Tools

#### Core (`core.*`)

| Tool                        | Tier | Description                                    |
| --------------------------- | ---- | ---------------------------------------------- |
| `core.list_node_types`      | 1    | All available Kailash node types (AST-scanned) |
| `core.list_node_categories` | 1    | Node categories with counts                    |
| `core.describe_node`        | 1    | Detailed info for a single node type           |
| `core.get_sdk_version`      | 1    | Kailash SDK version info                       |
| `core.validate_workflow`    | 3    | Validate workflow JSON structure               |

Node discovery uses AST parsing of `kailash.nodes` package. Caches results keyed by file mtime.

#### DataFlow (`dataflow.*`)

| Tool                      | Tier | Description                                   |
| ------------------------- | ---- | --------------------------------------------- |
| `dataflow.list_models`    | 1    | All DataFlow models (AST-scanned `@db.model`) |
| `dataflow.describe_model` | 1    | Model fields, types, relationships            |
| `dataflow.query_schema`   | 1    | Schema introspection                          |
| `dataflow.scaffold_model` | 2    | Generate model boilerplate                    |
| `dataflow.validate_model` | 3    | Validate model definitions                    |
| `dataflow.generate_tests` | 2    | Generate model test stubs                     |

Resources: `kailash://dataflow/models`, `kailash://dataflow/models/{name}/schema`, `kailash://dataflow/query-plan`.

Model discovery scans project Python files, identifies `@db.model` decorated classes, and extracts field definitions via AST. PII field detection flags fields named `phone`, `ssn`, `credit_card`, etc.

#### Nexus (`nexus.*`)

| Tool                     | Tier | Description                  |
| ------------------------ | ---- | ---------------------------- |
| `nexus.list_handlers`    | 1    | Nexus handler registrations  |
| `nexus.list_channels`    | 1    | Registered channels          |
| `nexus.scaffold_handler` | 2    | Generate handler boilerplate |
| `nexus.generate_tests`   | 2    | Generate handler test stubs  |
| `nexus.validate_handler` | 3    | Validate handler definitions |
| `nexus.test_handler`     | 4    | Execute handler tests        |

#### Kaizen (`kaizen.*`)

| Tool                    | Tier | Description                                     |
| ----------------------- | ---- | ----------------------------------------------- |
| `kaizen.list_agents`    | 1    | Kaizen agents (BaseAgent subclasses, Delegates) |
| `kaizen.describe_agent` | 1    | Agent details                                   |
| `kaizen.scaffold_agent` | 2    | Generate agent boilerplate                      |
| `kaizen.generate_tests` | 2    | Generate agent test stubs                       |
| `kaizen.test_agent`     | 4    | Execute agent tests                             |

#### Platform (`platform.*`)

| Tool                          | Tier | Description                        |
| ----------------------------- | ---- | ---------------------------------- |
| `platform.platform_map`       | 1    | Full cross-framework project graph |
| `platform.project_info`       | 1    | Project metadata                   |
| `platform.discover_tools`     | 1    | Unified tool discovery             |
| `platform.discover_resources` | 1    | Unified resource discovery         |
| `platform.get_platform_info`  | 1    | Platform metadata and capabilities |
| `platform.health`             | 1    | Server health status (built-in)    |

#### Trust (`trust.*`)

| Tool                 | Tier | Description                |
| -------------------- | ---- | -------------------------- |
| `trust.trust_status` | 1    | Current trust plane status |

#### PACT (`pact.*`)

| Tool            | Tier | Description              |
| --------------- | ---- | ------------------------ |
| `pact.org_tree` | 1    | Organizational hierarchy |

### 3.5 Middleware

#### TokenAuthMiddleware

```python
middleware = TokenAuthMiddleware(token=None)  # Reads KAILASH_MCP_AUTH_TOKEN
```

Validates `Authorization: Bearer <token>` headers. When no token is configured, passes all requests (open for local STDIO). Uses `hmac.compare_digest` for constant-time comparison.

#### RateLimitMiddleware

```python
limiter = RateLimitMiddleware(requests_per_minute=None)  # Reads KAILASH_MCP_RATE_LIMIT
```

Sliding window counter per client ID. Default: 60 requests/minute. Methods: `is_allowed(client_id)`, `remaining(client_id)`, `reset()`.

### 3.6 Health Check

```python
get_health_status(server) -> dict
```

Returns: `{"status": "healthy", "uptime_seconds": float, "server_name": str, "tools_registered": int, "resources_registered": int}`.

### 3.7 Resource Cache

`ResourceCache` provides mtime-based caching for computed MCP resource data. Watches the project directory for file modifications. When any Python file's mtime changes, cached resources are invalidated. Thread-safe via lock.

---

## 4. Advanced Server Features

### 4.1 Structured Tools

```python
@StructuredTool(
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    output_schema={"type": "object", "properties": {"results": {"type": "array"}, "count": {"type": "integer"}}},
    annotations=ToolAnnotation(is_read_only=True, estimated_duration=2.0),
    progress_reporting=True,
)
async def search(query: str) -> dict:
    return {"results": [...], "count": 5}
```

**Contract:**

- Input validation runs before function execution. Failure raises `MCPError(INVALID_PARAMS)`.
- Output validation runs after function execution. Failure raises `MCPError(INTERNAL_ERROR)`.
- Uses `jsonschema.Draft7Validator`.
- Progress reporting automatically creates and completes progress tokens.
- Handles both sync and async functions.

Convenience decorator:

```python
@structured_tool(output_schema={...})
async def my_tool(...): ...
```

### 4.2 ToolAnnotation

```python
@dataclass
class ToolAnnotation:
    is_read_only: bool = False
    is_destructive: bool = False
    is_idempotent: bool = True
    estimated_duration: Optional[float] = None
    requires_confirmation: bool = False
    security_level: str = "normal"    # "normal", "elevated", "admin"
    rate_limit: Optional[Dict] = None
```

### 4.3 SchemaValidator

Wraps `jsonschema.Draft7Validator`:

```python
validator = SchemaValidator(schema)
validator.validate(data)      # Raises ValidationError with path details
validator.is_valid(data)      # Returns bool
```

### 4.4 MultiModalContent

Container for multi-modal tool responses:

```python
content = MultiModalContent()
content.add_text("Analysis results:")
content.add_image(png_bytes, "image/png")
content.add_audio(audio_bytes, "audio/wav")
content.add_resource("files://data.csv", text="CSV content", mime_type="text/csv")
content.add_annotation("confidence", {"score": 0.95})
result = content.to_list()    # List of MCP content dicts
```

**Content types:** `TEXT`, `IMAGE`, `AUDIO`, `RESOURCE`, `ANNOTATION`.

Binary data (images, audio) is base64-encoded if provided as bytes.

### 4.5 BinaryResourceHandler

Handles binary resources with automatic base64 encoding/decoding. Supports MIME type detection from file extensions.

### 4.6 Resource Templates

```python
template = ResourceTemplate(
    uri_template="files://{path}",
    name="File Access",
    description="Access files by path",
    mime_type="text/plain",
    supports_subscription=True,
)
```

Supports change subscriptions:

```python
subscription_id = await template.subscribe(
    uri="files://documents/report.pdf",
    callback=lambda change: handle_change(change),
)
await template.notify_change(ResourceChange(
    uri="files://documents/report.pdf",
    change_type=ChangeType.UPDATED,
    content={"size": 1024},
))
await template.unsubscribe(subscription_id)
```

**ResourceChange:** `@dataclass` with `uri`, `change_type` (CREATED/UPDATED/DELETED), `content`, `timestamp`, `metadata`.

### 4.7 StreamingHandler

Handles streaming responses for large tool outputs. Chunks data and delivers it incrementally.

### 4.8 ProgressReporter / CancellationContext

High-level wrappers for progress reporting and cancellation:

```python
reporter = create_progress_reporter(operation_name, total=100)
await reporter.update(50, "Processing...")
await reporter.complete()

ctx = create_cancellation_context(request_id)
if ctx.is_cancelled():
    ctx.cleanup()
```

### 4.9 ElicitationSystem

Interactive user input system for tools that need to ask the user questions during execution.

### 4.10 Resource Subscriptions

`ResourceSubscriptionManager` manages real-time resource change notifications:

- Per-client subscriptions with URI patterns (supports glob matching via `fnmatch`).
- Batch subscribe/unsubscribe operations.
- Data enrichment transformers (`DataEnrichmentTransformer`) can add computed fields to resource data.
- Auth-aware: validates subscription permissions.
- Optional Redis backend for distributed subscription state.
- Event store for subscription audit logging.

---

## 5. Server-Side Edge Cases and Constraints

### 5.1 Server-Side

- **FastMCP fallback:** If neither `fastmcp` nor `mcp.server.FastMCP` is importable, the server creates a minimal fallback that registers tools/resources/prompts but raises `NotImplementedError` on `run()`.
- **Sync tool timeouts:** Use `signal.SIGALRM` which is Unix-only and not available on Windows.
- **Auth credential stripping:** The enhanced tool wrapper strips auth-related kwargs (`api_key`, `token`, `username`, `password`, `jwt`, `authorization`, `mcp_auth`) before calling the wrapped function.
- **Async auth bypass:** In async tools, if no credentials are provided and no `mcp_*` kwargs exist, authentication is bypassed with a DEBUG log. This enables development/testing scenarios.
- **Circuit breaker state is per-server instance**, not per-tool. All tools share the same circuit breaker.
- **WebSocket compression:** Optional gzip compression with configurable threshold (default 1024 bytes) and level (default 6).

### 5.2 Security Tiers

- Tier 4 (EXECUTION) tools can run arbitrary code. They are disabled by default and require explicit opt-in via `KAILASH_MCP_ENABLE_EXECUTION=true`.
- Tier 3 (VALIDATION) tools run linting and validation. Enabled by default but can be disabled.
- All contributor tools use `is_tier_enabled()` to gate registration.
