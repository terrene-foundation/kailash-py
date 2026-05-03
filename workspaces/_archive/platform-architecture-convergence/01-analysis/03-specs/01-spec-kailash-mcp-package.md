# SPEC-01: kailash-mcp Package

**Status**: DRAFT
**Implements**: ADR-004 (kailash-mcp package boundary)
**Cross-SDK issues**: TBD (filed before implementation per ADR-008)
**Priority**: Phase 1 — unblocks all other convergence work

## §1 Overview

Extract all MCP (Model Context Protocol) code from inline locations across kailash-py into a new `packages/kailash-mcp/` package. Consolidate the 2 parallel client implementations into 1, move the platform server, create canonical protocol types shared with kailash-rs, and establish backward-compat shims at old import paths.

### What moves

| Source                                                                | Destination                                                              | Action                                     |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------ |
| `src/kailash/mcp_server/client.py` (1,288 LOC)                        | `packages/kailash-mcp/src/kailash_mcp/client.py`                         | MOVE (primary client)                      |
| `src/kailash/mcp_server/server.py` (2,924 LOC)                        | `packages/kailash-mcp/src/kailash_mcp/server.py`                         | MOVE                                       |
| `src/kailash/mcp_server/protocol.py` (1,152 LOC)                      | `packages/kailash-mcp/src/kailash_mcp/protocol/`                         | MOVE + split                               |
| `src/kailash/mcp_server/transports.py` (1,481 LOC)                    | `packages/kailash-mcp/src/kailash_mcp/transports/`                       | MOVE + split                               |
| `src/kailash/mcp_server/auth.py` (813 LOC)                            | `packages/kailash-mcp/src/kailash_mcp/auth/`                             | MOVE + split                               |
| `src/kailash/mcp_server/discovery.py` (1,636 LOC)                     | `packages/kailash-mcp/src/kailash_mcp/discovery/`                        | MOVE                                       |
| `src/kailash/mcp_server/advanced_features.py` (1,023 LOC)             | `packages/kailash-mcp/src/kailash_mcp/advanced/`                         | MOVE                                       |
| `src/kailash/mcp_server/errors.py` (673 LOC)                          | `packages/kailash-mcp/src/kailash_mcp/errors.py`                         | MOVE                                       |
| `src/kailash/mcp_server/oauth.py` (1,730 LOC)                         | `packages/kailash-mcp/src/kailash_mcp/auth/oauth.py`                     | MOVE                                       |
| `src/kailash/mcp_server/subscriptions.py` (1,578 LOC)                 | `packages/kailash-mcp/src/kailash_mcp/advanced/subscriptions.py`         | MOVE                                       |
| `src/kailash/mcp_server/resource_cache.py` (128 LOC)                  | `packages/kailash-mcp/src/kailash_mcp/advanced/resource_cache.py`        | MOVE                                       |
| `src/kailash/mcp_server/registry_integration.py` (587 LOC)            | `packages/kailash-mcp/src/kailash_mcp/discovery/registry_integration.py` | MOVE                                       |
| `src/kailash/mcp_server/ai_registry_server.py` (737 LOC)              | `packages/kailash-mcp/src/kailash_mcp/contrib/ai_registry.py`            | MOVE                                       |
| `src/kailash/mcp/platform_server.py` (470 LOC)                        | `packages/kailash-mcp/src/kailash_mcp/platform_server.py`                | MOVE                                       |
| `src/kailash/mcp/contrib/` (~500 LOC)                                 | `packages/kailash-mcp/src/kailash_mcp/contrib/`                          | MOVE                                       |
| `src/kailash/trust/plane/mcp_server.py` (~200 LOC)                    | `packages/kailash-mcp/src/kailash_mcp/contrib/trust.py`                  | MOVE (or keep standalone, see §8)          |
| `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` (509 LOC)  | DELETED                                                                  | replaced by `kailash_mcp.client.MCPClient` |
| `packages/kaizen-agents/src/kaizen_agents/delegate/tools/hydrator.py` | `packages/kailash-mcp/src/kailash_mcp/tools/hydrator.py`                 | MOVE                                       |
| `src/kailash/api/mcp_integration.py` (~200 LOC)                       | DELETED                                                                  | zero consumers (verified)                  |
| `src/kailash/channels/mcp_channel.py` (~150 LOC)                      | REFACTORED to import from `kailash_mcp`                                  |                                            |
| `src/kailash/middleware/mcp/enhanced_server.py` (613 LOC)             | AUDITED and either MOVE or DELETE                                        |                                            |
| `src/kailash/middleware/mcp/client_integration.py` (648 LOC)          | AUDITED and either MOVE or DELETE                                        |                                            |
| `packages/kailash-nexus/src/nexus/mcp/__init__.py`                    | DELETED (already deprecated)                                             |                                            |

### What stays in Core SDK (as glue)

| File                                                      | Purpose                                   | Action                                |
| --------------------------------------------------------- | ----------------------------------------- | ------------------------------------- |
| `src/kailash/nodes/enterprise/mcp_executor.py` (430 LOC)  | Workflow node for executing MCP tools     | Refactor to import from `kailash_mcp` |
| `src/kailash/nodes/mixins/mcp.py` (233 LOC)               | Node mixin for MCP capability declaration | Refactor to import from `kailash_mcp` |
| `src/kailash/adapters/mcp_platform_adapter.py` (~150 LOC) | Platform adapter                          | Refactor to import from `kailash_mcp` |

## §2 Wire Types / API Contracts

### §2.1 JSON-RPC Protocol Types (Canonical)

These are the SINGLE source of truth for JSON-RPC types. Both Python and Rust MUST produce and consume these exact shapes.

```python
# packages/kailash-mcp/src/kailash_mcp/protocol/jsonrpc.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union


@dataclass
class JsonRpcRequest:
    """JSON-RPC 2.0 request.

    Wire format:
    {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "read_file", "arguments": {"path": "/tmp/x.txt"}},
        "id": 42
    }

    `id` is None for notifications (no response expected).
    `params` is None when the method takes no arguments.
    """
    method: str
    params: Optional[dict[str, Any]] = None
    id: Optional[Union[int, str]] = None
    jsonrpc: Literal["2.0"] = "2.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            d["params"] = self.params
        if self.id is not None:
            d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcRequest:
        return cls(
            method=data["method"],
            params=data.get("params"),
            id=data.get("id"),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )


@dataclass
class JsonRpcError:
    """JSON-RPC 2.0 error object.

    Standard error codes:
    -32700: Parse error
    -32600: Invalid request
    -32601: Method not found
    -32602: Invalid params
    -32603: Internal error
    -32000 to -32099: Server error (implementation-defined)
    """
    code: int
    message: str
    data: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcError:
        return cls(
            code=data["code"],
            message=data["message"],
            data=data.get("data"),
        )

    # Standard error factories
    @classmethod
    def parse_error(cls, data: Any = None) -> JsonRpcError:
        return cls(code=-32700, message="Parse error", data=data)

    @classmethod
    def invalid_request(cls, data: Any = None) -> JsonRpcError:
        return cls(code=-32600, message="Invalid Request", data=data)

    @classmethod
    def method_not_found(cls, method: str) -> JsonRpcError:
        return cls(code=-32601, message=f"Method not found: {method}")

    @classmethod
    def invalid_params(cls, message: str) -> JsonRpcError:
        return cls(code=-32602, message=message)

    @classmethod
    def internal_error(cls, message: str = "Internal error") -> JsonRpcError:
        return cls(code=-32603, message=message)


@dataclass
class JsonRpcResponse:
    """JSON-RPC 2.0 response.

    Exactly one of `result` or `error` MUST be present (not both, not neither).
    `id` MUST match the request id (null for notification responses, which shouldn't happen).
    """
    id: Optional[Union[int, str]]
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None
    jsonrpc: Literal["2.0"] = "2.0"

    def __post_init__(self):
        if self.result is not None and self.error is not None:
            raise ValueError("JsonRpcResponse cannot have both result and error")
        if self.result is None and self.error is None:
            raise ValueError("JsonRpcResponse must have either result or error")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcResponse:
        error_data = data.get("error")
        return cls(
            id=data.get("id"),
            result=data.get("result"),
            error=JsonRpcError.from_dict(error_data) if error_data else None,
            jsonrpc=data.get("jsonrpc", "2.0"),
        )

    @classmethod
    def success(cls, id: Union[int, str], result: Any) -> JsonRpcResponse:
        return cls(id=id, result=result)

    @classmethod
    def failure(cls, id: Optional[Union[int, str]], error: JsonRpcError) -> JsonRpcResponse:
        return cls(id=id, error=error)
```

### §2.2 MCP Protocol Types

```python
# packages/kailash-mcp/src/kailash_mcp/protocol/types.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class McpToolInfo:
    """MCP tool definition (discovered via tools/list)."""
    name: str
    description: str
    input_schema: dict[str, Any]                  # JSON Schema

    # Metadata preserved through conversion pipeline
    # (This is what was MISSING in tool_formatters.py — #339 root cause)
    server_name: Optional[str] = None             # which server owns this tool
    server_config: Optional[dict[str, Any]] = None # how to reach the server

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.server_name:
            d["_server_name"] = self.server_name
        if self.server_config:
            d["_server_config"] = self.server_config
        return d


@dataclass
class McpResourceInfo:
    """MCP resource definition (discovered via resources/list)."""
    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"


@dataclass
class ServerInfo:
    """MCP server identity and capabilities."""
    name: str
    version: str
    capabilities: ServerCapabilities = field(default_factory=lambda: ServerCapabilities())


@dataclass
class ServerCapabilities:
    """MCP server declared capabilities."""
    tools: bool = True
    resources: bool = False
    prompts: bool = False
    sampling: bool = False
    roots: bool = False
    progress: bool = False
```

### §2.3 MCPClient Public API

```python
# packages/kailash-mcp/src/kailash_mcp/client.py

from __future__ import annotations
from typing import Any, AsyncContextManager, Optional
from kailash_mcp.protocol.types import McpToolInfo, McpResourceInfo, ServerInfo
from kailash_mcp.protocol.jsonrpc import JsonRpcRequest, JsonRpcResponse


class MCPClient:
    """Production-grade MCP client with pluggable transports.

    This is the SINGLE MCP client implementation in kailash-py.
    All consumers (BaseAgent, Delegate, Nexus, etc.) use this class.

    Features:
    - Pluggable transports: stdio, HTTP, SSE, WebSocket, in-memory (testing)
    - Authentication: API key, JWT, OAuth 2.1, Basic
    - Retry: exponential backoff, circuit breaker
    - Discovery: ServiceRegistry, LoadBalancer, HealthChecker
    - Metrics: request count, latency, error rate
    - Resource subscriptions: real-time updates
    - Multi-modal content: images, audio in tool results

    Usage:

        # Direct connection to a single server
        client = MCPClient(
            transport=StdioTransport(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            )
        )
        async with client:
            tools = await client.list_tools()
            result = await client.call_tool("read_file", {"path": "/tmp/x.txt"})

        # Multi-server with discovery
        client = MCPClient(
            discovery=ServiceRegistry([
                MCPServerConfig(name="fs", command="npx", args=[...]),
                MCPServerConfig(name="db", command="python", args=["db_server.py"]),
            ]),
            retry=ExponentialBackoffRetry(max_retries=3),
        )
        async with client:
            tools = await client.list_tools()  # aggregated from all servers
            result = await client.call_tool("fs__read_file", {"path": "/tmp/x"})
    """

    def __init__(
        self,
        *,
        transport: Optional[MCPTransport] = None,
        discovery: Optional[ServiceRegistry] = None,
        auth: Optional[AuthProvider] = None,
        retry: Optional[RetryStrategy] = None,
        metrics: bool = False,
        timeout: float = 30.0,
    ):
        """Create an MCPClient.

        Args:
            transport: Single-server transport (stdio, http, sse, websocket).
                Mutually exclusive with `discovery`.
            discovery: Multi-server registry with load balancing and health checking.
                Mutually exclusive with `transport`.
            auth: Authentication provider (API key, JWT, OAuth, Basic).
            retry: Retry strategy (exponential backoff, circuit breaker).
            metrics: Enable metrics collection (request count, latency, error rate).
            timeout: Default request timeout in seconds.
        """
        ...

    # ─── Lifecycle ─────────────────────────────────────────────────────

    async def __aenter__(self) -> MCPClient:
        """Start the client (connect to servers, perform handshake)."""
        ...

    async def __aexit__(self, *exc) -> None:
        """Stop the client (close connections, terminate subprocesses)."""
        ...

    async def start(self) -> None:
        """Explicit start (alternative to async context manager)."""
        ...

    async def stop(self) -> None:
        """Explicit stop."""
        ...

    # ─── Tool operations ───────────────────────────────────────────────

    async def list_tools(self) -> list[McpToolInfo]:
        """Discover all tools from connected servers.

        Returns a list of McpToolInfo with server_name and server_config
        populated (preserving the metadata needed for execution).

        If using ServiceRegistry with multiple servers, tools from all
        servers are aggregated. Tool names are prefixed with server name
        to prevent collisions: `{server_name}__{tool_name}`.
        """
        ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> str:
        """Execute a tool on the appropriate server.

        Args:
            name: Tool name (may include server prefix if using multi-server).
            arguments: Tool arguments matching the tool's input_schema.
            timeout: Per-call timeout override (defaults to client timeout).

        Returns:
            Tool result as a string. If the result contains multiple content
            blocks, they are joined with newlines.

        Raises:
            McpToolNotFoundError: Tool name not in discovered tool list.
            McpToolExecutionError: Server returned an error for the tool call.
            McpTimeoutError: Call exceeded timeout.
            McpTransportError: Transport-level failure (connection lost, etc.).
        """
        ...

    # ─── Resource operations ───────────────────────────────────────────

    async def list_resources(self) -> list[McpResourceInfo]:
        """Discover all resources from connected servers."""
        ...

    async def read_resource(self, uri: str) -> str:
        """Read a resource by URI."""
        ...

    # ─── Prompt operations ─────────────────────────────────────────────

    async def get_prompt(
        self, name: str, arguments: Optional[dict[str, str]] = None
    ) -> str:
        """Get a prompt template from the server."""
        ...

    # ─── Tool registration into ToolRegistry ───────────────────────────

    async def discover_and_register(
        self,
        registry: ToolRegistry,
        *,
        name_prefix: str = "",
    ) -> list[McpToolInfo]:
        """Discover tools and register them into a ToolRegistry.

        Each discovered tool is registered with:
        - name: `{name_prefix}{tool_name}` (or `{server_name}__{tool_name}` if multi-server)
        - description: from MCP tool definition
        - parameters: from MCP input_schema (JSON Schema)
        - executor: async closure that calls self.call_tool(name, args)

        This is the bridge between MCP and the Kaizen tool system.
        Both JSON schema (for BaseAgent Signature matching) and callable
        executor (for AgentLoop TAOD execution) are registered.

        Args:
            registry: The unified ToolRegistry to register tools into.
            name_prefix: Optional prefix for all tool names.

        Returns:
            List of discovered McpToolInfo instances.
        """
        tools = await self.list_tools()

        for tool in tools:
            qualified_name = f"{name_prefix}{tool.name}" if name_prefix else tool.name

            # Closure captures the client and tool name for execution
            async def _executor(
                _client: MCPClient = self,
                _tool_name: str = tool.name,
                **kwargs: Any,
            ) -> str:
                return await _client.call_tool(_tool_name, kwargs)

            registry.register(
                name=qualified_name,
                description=tool.description,
                parameters=tool.input_schema,   # JSON Schema for Signature matching
                executor=_executor,              # Callable for TAOD execution
            )

        return tools

    # ─── Introspection ─────────────────────────────────────────────────

    @property
    def server_info(self) -> Optional[ServerInfo]:
        """Server identity and capabilities (set after handshake)."""
        ...

    @property
    def is_connected(self) -> bool:
        """Whether the client is connected and initialized."""
        ...
```

### §2.4 MCPTransport Protocol

```python
# packages/kailash-mcp/src/kailash_mcp/transports/base.py

from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class MCPTransport(Protocol):
    """Transport protocol for MCP communication.

    Implementations handle the physical layer:
    - StdioTransport: subprocess stdin/stdout with JSON-RPC line-delimited or Content-Length framing
    - HTTPTransport: HTTP POST requests
    - SSETransport: Server-Sent Events (unidirectional server → client)
    - WebSocketTransport: bidirectional WebSocket
    - InMemoryTransport: for testing (FIFO queue)
    """

    async def connect(self) -> None:
        """Establish the transport connection."""
        ...

    async def disconnect(self) -> None:
        """Close the transport connection."""
        ...

    async def send(self, message: str) -> str:
        """Send a JSON-RPC message and wait for the response.

        Args:
            message: JSON-encoded request string.

        Returns:
            JSON-encoded response string.

        Raises:
            McpTransportError: Connection failure, timeout, etc.
        """
        ...

    @property
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""
        ...
```

### §2.5 Unified ToolRegistry

```python
# packages/kailash-mcp/src/kailash_mcp/tools/registry.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class ToolDef:
    """A tool definition with both schema (for LLM) and executor (for runtime).

    This unified type resolves the capability split between BaseAgent (JSON schemas)
    and Delegate (callable executors). Both shapes are stored simultaneously.
    """
    name: str
    description: str
    parameters: dict[str, Any]                                     # JSON Schema
    executor: Optional[Callable[..., Awaitable[str]]] = None       # Async callable (None for schema-only tools)
    danger_level: str = "safe"                                      # safe | moderate | dangerous
    category: str = "general"

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling format for LLM provider."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Unified tool registry supporting both JSON schema and callable execution.

    This registry replaces:
    - BaseAgent's tool system (JSON schemas for Signature matching)
    - Delegate's ToolRegistry (callable executors for AgentLoop)

    Both shapes are stored in a single ToolDef, so any consumer can use
    either the schema (for LLM function declaration) or the executor
    (for tool invocation) without conversion.

    Usage:

        registry = ToolRegistry()

        # Register with executor (for MCP tools, builtin tools)
        registry.register(
            name="read_file",
            description="Read a file's contents",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            executor=async_read_file,
        )

        # Register schema-only (for tools that don't need execution — rare)
        registry.register(
            name="external_api",
            description="Documented external API tool",
            parameters={...},
        )

        # Get OpenAI format for LLM
        openai_tools = registry.get_openai_tools()

        # Execute a tool
        result = await registry.execute("read_file", {"path": "/tmp/x.txt"})
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        executor: Optional[Callable[..., Awaitable[str]]] = None,
        danger_level: str = "safe",
        category: str = "general",
    ) -> None:
        """Register a tool.

        Args:
            name: Unique tool name.
            description: Human-readable description (shown to LLM).
            parameters: JSON Schema for input validation.
            executor: Async callable for tool execution. Pass None for schema-only.
            danger_level: Tool risk level (safe/moderate/dangerous).
            category: Tool category for organization.

        Raises:
            ValueError: If name is already registered with a different definition.
        """
        self._tools[name] = ToolDef(
            name=name,
            description=description,
            parameters=parameters,
            executor=executor,
            danger_level=danger_level,
            category=category,
        )

    def get(self, name: str) -> Optional[ToolDef]:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Get all tools in OpenAI function-calling format for LLM provider."""
        return [tool.to_openai_format() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result as string (or JSON string for structured results).

        Raises:
            ToolNotFoundError: No tool with that name.
            ToolNotExecutableError: Tool is schema-only (no executor).
            ToolExecutionError: Executor raised an exception.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{name}' not found in registry")
        if tool.executor is None:
            raise ToolNotExecutableError(
                f"Tool '{name}' is schema-only (no executor registered). "
                f"Register with executor= to enable execution."
            )
        try:
            return await tool.executor(**arguments)
        except Exception as e:
            raise ToolExecutionError(f"Tool '{name}' execution failed: {e}") from e

    def names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def count(self) -> int:
        """Number of registered tools."""
        return len(self._tools)

    def has_executor(self, name: str) -> bool:
        """Whether the named tool has a callable executor."""
        tool = self._tools.get(name)
        return tool is not None and tool.executor is not None
```

## §3 Semantics

### §3.1 Tool Name Qualification

When using `MCPClient` with `ServiceRegistry` (multi-server), tool names are qualified:

```
{server_name}__{tool_name}
```

Example: `filesystem__read_file`, `database__query`, `kaizen__search_tools`.

Single-server mode does NOT qualify names (backward compat with existing Delegate usage).

### §3.2 Server Lifecycle

1. **start()** → Connect transport → Send `initialize` (JSON-RPC) → Receive `ServerInfo` → Send `notifications/initialized`
2. **list_tools()** → Send `tools/list` → Receive tool definitions → Populate `McpToolInfo` with server metadata
3. **call_tool(name, args)** → Send `tools/call` → Receive result → Parse content blocks → Return string
4. **stop()** → Send SIGTERM to subprocess (if stdio) → Wait 5s → SIGKILL if still alive → Cancel pending futures

### §3.3 Error Semantics

```python
# packages/kailash-mcp/src/kailash_mcp/errors.py

class McpError(Exception):
    """Base MCP error."""

class McpTransportError(McpError):
    """Transport-level failure (connection lost, subprocess died, timeout)."""

class McpProtocolError(McpError):
    """Protocol-level error (invalid JSON-RPC, unexpected response shape)."""

class McpToolNotFoundError(McpError):
    """Tool name not in discovered tool list."""

class McpToolExecutionError(McpError):
    """Server returned an error for a tool call."""

class McpTimeoutError(McpError):
    """Request exceeded timeout."""

class McpAuthenticationError(McpError):
    """Authentication failed (invalid key, expired token, etc.)."""

class ToolNotFoundError(McpError):
    """Tool not in ToolRegistry."""

class ToolNotExecutableError(McpError):
    """Tool is schema-only (no executor)."""

class ToolExecutionError(McpError):
    """Executor raised an exception."""
```

### §3.4 How This Fixes #339

**Sub-issue 1** (tool_formatters strips mcp_server_config): `McpToolInfo` now has `server_name` and `server_config` fields. `MCPClient.list_tools()` populates them. When tools are registered into `ToolRegistry`, the executor closure captures the client instance — the server_config is implicit in the closure, not carried as metadata on the JSON schema.

**Sub-issue 2** (\_execute_regular_tool stub): Eliminated. All tools in the unified `ToolRegistry` have executors (or are explicitly schema-only and raise `ToolNotExecutableError` rather than returning fake success).

**Sub-issue 3** (system prompt text-based tool instructions): The system prompt no longer needs to inject text-based tool calling instructions because the unified `ToolRegistry.get_openai_tools()` produces the correct function-declaration format for every provider. The `_generate_system_prompt()` extension point (deprecated per ADR-001) no longer appends ReAct-style tool instructions.

**Sub-issue 4** (BaseAgent uses broken MCPClient): After extraction, `BaseAgent.configure_mcp()` calls `MCPClient.discover_and_register()` which uses the production-grade client with callable executors. The broken `kailash.mcp_server.MCPClient` pathway through `tool_formatters` is replaced by the unified one.

## §4 Backward Compatibility

Per ADR-009 Layer 1 (re-export shims):

```python
# src/kailash/mcp_server/__init__.py (v2.x backward-compat shim)
import warnings as _warnings

_warnings.warn(
    "kailash.mcp_server is deprecated since v2.next. "
    "Use `from kailash_mcp import ...` instead. "
    "This shim will be removed in v3.0 (earliest: 2026-10-01).",
    DeprecationWarning,
    stacklevel=2,
)

from kailash_mcp import (
    MCPClient, MCPServer,
    JsonRpcRequest, JsonRpcResponse, JsonRpcError,
    McpError, McpTransportError, McpProtocolError,
    McpToolNotFoundError, McpToolExecutionError, McpTimeoutError,
    McpToolInfo, McpResourceInfo, ServerInfo, ServerCapabilities,
    ToolRegistry, ToolDef,
)
from kailash_mcp.auth import APIKeyAuth, JWTAuth, BasicAuth
from kailash_mcp.transports import (
    MCPTransport, StdioTransport, HTTPTransport, SSETransport, WebSocketTransport,
    InMemoryTransport,
)
from kailash_mcp.discovery import ServiceRegistry, LoadBalancer, HealthChecker
from kailash_mcp.retry import ExponentialBackoffRetry, CircuitBreakerRetry
```

**Import path migration**:

| Old                                                              | New                                          |
| ---------------------------------------------------------------- | -------------------------------------------- |
| `from kailash.mcp_server import MCPClient`                       | `from kailash_mcp import MCPClient`          |
| `from kailash.mcp_server.auth import APIKeyAuth`                 | `from kailash_mcp.auth import APIKeyAuth`    |
| `from kailash.mcp_server.client import MCPClient`                | `from kailash_mcp import MCPClient`          |
| `from kaizen_agents.delegate.mcp import McpClient`               | `from kailash_mcp import MCPClient`          |
| `from kaizen_agents.delegate.mcp import McpServerConfig`         | `from kailash_mcp import MCPServerConfig`    |
| `from kaizen_agents.delegate.tools.hydrator import ToolHydrator` | `from kailash_mcp.tools import ToolHydrator` |

## §5 Security Considerations

1. **SSRF protection**: `MCPClient` validates all HTTP base_url values against a metadata endpoint blocklist (AWS, GCP, Azure, Alibaba Cloud metadata IPs). This check already exists in the production client and MUST be preserved during extraction.

2. **Subprocess security**: `StdioTransport` spawns MCP server subprocesses. The command comes from user config (`.kz/config.toml`, `Delegate(mcp_servers=[...])`, etc.). Per security rules, subprocess commands are logged at INFO level for audit. No shell=True.

3. **API key handling**: API keys are NEVER logged. The `auth` module uses constant-time comparison for key validation. Keys are stored in memory only (not written to disk).

4. **Per-request credentials**: BYOK multi-tenant mode supports per-request `api_key` and `base_url` overrides via kwargs. The `BYOKClientCache` manages client instances per key with TTL expiry to prevent credential leakage.

5. **Tool execution sandboxing**: `ToolRegistry.execute()` catches ALL exceptions and wraps them in `ToolExecutionError`. Tool executors MUST NOT be able to escape the error boundary.

## §6 Examples

### Basic single-server usage

```python
from kailash_mcp import MCPClient, MCPServerConfig
from kailash_mcp.transports import StdioTransport

async def main():
    client = MCPClient(
        transport=StdioTransport(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        )
    )

    async with client:
        tools = await client.list_tools()
        print(f"Discovered {len(tools)} tools")

        result = await client.call_tool("read_file", {"path": "/tmp/example.txt"})
        print(result)
```

### Multi-server with discovery

```python
from kailash_mcp import MCPClient, MCPServerConfig
from kailash_mcp.discovery import ServiceRegistry

async def main():
    registry = ServiceRegistry([
        MCPServerConfig(name="fs", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]),
        MCPServerConfig(name="db", command="python", args=["my_db_server.py"]),
    ])

    client = MCPClient(discovery=registry)

    async with client:
        tools = await client.list_tools()
        # tools: [McpToolInfo(name="fs__read_file", ...), McpToolInfo(name="db__query", ...)]

        result = await client.call_tool("fs__read_file", {"path": "/tmp/x.txt"})
```

### Integration with BaseAgent

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kailash_mcp import MCPServerConfig

config = BaseAgentConfig(model="claude-sonnet-4-5")
agent = BaseAgent(config=config, signature=MySig)

# Discover MCP tools and register into agent's ToolRegistry
agent.configure_mcp([
    MCPServerConfig(name="fs", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]),
])

result = agent.run(query="Read /tmp/example.txt and summarize it")
# MCP tool is called natively (no text-based ReAct instructions)
# Structured output is parsed from Signature
```

### Integration with Delegate (unchanged API)

```python
from kaizen_agents import Delegate
from kailash_mcp import MCPServerConfig

delegate = Delegate(
    model="claude-sonnet-4-5",
    signature=MySig,
    mcp_servers=[
        MCPServerConfig(name="fs", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]),
    ],
    budget_usd=10.0,
)

async for event in delegate.run(prompt="Read /tmp/example.txt and summarize it"):
    print(event)
```

## §7 Interop Test Vectors

### 7.1 JsonRpcRequest (basic tool call)

Both Python and Rust MUST produce this exact JSON when serializing:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": { "path": "/tmp/x.txt" }
  },
  "id": 42
}
```

**Test**: `test_jsonrpc_request_tool_call_roundtrip`

### 7.2 JsonRpcRequest (notification — no id)

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

Note: `params` and `id` are omitted (not null).

**Test**: `test_jsonrpc_notification_roundtrip`

### 7.3 JsonRpcResponse (success)

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "content": [{ "type": "text", "text": "Hello, World!" }]
  }
}
```

**Test**: `test_jsonrpc_response_success_roundtrip`

### 7.4 JsonRpcResponse (error)

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "error": {
    "code": -32601,
    "message": "Method not found: unknown/method"
  }
}
```

**Test**: `test_jsonrpc_response_error_roundtrip`

### 7.5 McpToolInfo (with server metadata)

```json
{
  "name": "read_file",
  "description": "Read a file's contents",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "File path to read" }
    },
    "required": ["path"]
  },
  "_server_name": "filesystem",
  "_server_config": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  }
}
```

**Test**: `test_mcp_tool_info_roundtrip`

## §8 Implementation Notes

### TrustPlane MCP server decision

The TrustPlane MCP server (`src/kailash/trust/plane/mcp_server.py`) is the cleanest MCP server in the codebase. Options:

**A**: Move to `packages/kailash-mcp/src/kailash_mcp/contrib/trust.py` — keeps everything in one package.

**B**: Keep at current location, refactor to import types from `kailash_mcp.protocol` — minimal disruption, TrustPlane remains independent.

**Recommendation**: **Option B** for now. TrustPlane is architecturally clean and standalone. It should import canonical types from `kailash_mcp` but doesn't need to move physically. The `trustplane-mcp` CLI entry point stays in the main `kailash` pyproject.toml.

### middleware/mcp/enhanced_server.py decision

This 613-line file uses SDK components (NodeParameter, PythonCodeNode, WorkflowBuilder) to define MCP server tools. It's an unusual pattern (building tools from workflow nodes).

**Options**:

- **A**: Move to `kailash-mcp` as an advanced server builder pattern
- **B**: Delete if zero production consumers

**Action**: Read the file during implementation, decide based on consumer count. Track in the /todos phase.

### oauth.py (1,730 LOC) decision

The second-largest MCP file. Contains OAuth 2.1 with JWTManager, AuthorizationServer, TokenRevocation.

**Options**:

- **A**: Move to `packages/kailash-mcp/src/kailash_mcp/auth/oauth.py` (keeps MCP auth consolidated)
- **B**: Move to `kailash.trust.auth.oauth` (OAuth is a trust concern, not MCP-specific)

**Recommendation**: **Option A** for now. OAuth in this context is specifically for MCP server authentication. If `kailash.trust` gains a canonical OAuth module later, the MCP auth layer can delegate to it.

## §9 Migration Order

1. **Create package skeleton** (`packages/kailash-mcp/pyproject.toml`, directory structure, empty `__init__.py`)
2. **Move protocol types** (`protocol/jsonrpc.py`, `protocol/types.py`, `errors.py`) — no external dependencies
3. **Move transport base** (`transports/base.py`) — just the protocol, no implementations yet
4. **Move transport implementations** (`transports/stdio.py`, `transports/http.py`, `transports/sse.py`, `transports/websocket.py`)
5. **Move client** (`client.py`) — the production-grade MCPClient
6. **Move auth** (`auth/api_key.py`, `auth/jwt.py`, `auth/oauth.py`, `auth/basic.py`)
7. **Move discovery** (`discovery/service_registry.py`, `discovery/load_balancer.py`, `discovery/health_checker.py`)
8. **Move retry** (`retry/exponential.py`, `retry/circuit_breaker.py`)
9. **Move advanced** (`advanced/subscriptions.py`, `advanced/resource_cache.py`, `advanced/structured_tools.py`, `advanced/multimodal.py`)
10. **Move server** (`server.py`) — the MCPServer base
11. **Create unified ToolRegistry** (`tools/registry.py`) — merges BaseAgent's JSON schema approach with Delegate's callable approach
12. **Move ToolHydrator** (`tools/hydrator.py`) — from `kaizen_agents/delegate/tools/`
13. **Move platform server** (`platform_server.py`) + contrib tools
14. **Add backward-compat shims** at `src/kailash/mcp_server/__init__.py` and all old import paths
15. **Migrate BaseAgent** (`base_agent.py:40`) to import from `kailash_mcp` — fixes #339
16. **Delete `kaizen_agents/delegate/mcp.py`** — replaced by `kailash_mcp.MCPClient`
17. **Delete `src/kailash/api/mcp_integration.py`** — verified zero consumers
18. **Refactor `src/kailash/channels/mcp_channel.py`** — import from `kailash_mcp`
19. **Audit + decide on `src/kailash/middleware/mcp/`** (enhanced_server.py, client_integration.py)
20. **Refactor `src/kailash/nodes/enterprise/mcp_executor.py`** — import from `kailash_mcp`
21. **Refactor `src/kailash/nodes/mixins/mcp.py`** — import from `kailash_mcp`
22. **Run full test suite** — verify zero regressions
23. **Add new tests** for unified ToolRegistry, cross-SDK interop vectors

## §10 Test Migration

### Existing tests to migrate

| Old location                                             | New location                              | Notes                           |
| -------------------------------------------------------- | ----------------------------------------- | ------------------------------- |
| `tests/integration/mcp_server/` (7 files)                | `packages/kailash-mcp/tests/integration/` | Core client/server tests        |
| `tests/unit/mcp_server/` (4 files)                       | `packages/kailash-mcp/tests/unit/`        | Client, server, connection pool |
| `tests/e2e/mcp_server/` (2 files)                        | `packages/kailash-mcp/tests/e2e/`         | Deployment, HA scenarios        |
| `tests/trust/` (2 MCP-related)                           | Stay (trust-specific tests)               | But update imports              |
| `packages/kailash-kaizen/tests/unit/core/` (5 MCP tests) | Update imports to `kailash_mcp`           | BaseAgent MCP integration       |
| `packages/kaizen-agents/tests/unit/delegate/test_mcp.py` | DELETE (replaced by `kailash-mcp/tests/`) | Delegate McpClient tests        |

### New tests to add

1. **Unified ToolRegistry tests** — register with executor, register schema-only, execute, get_openai_tools, tool not found, tool not executable
2. **MCPClient + ToolRegistry integration** — `discover_and_register()` end-to-end with InMemoryTransport
3. **Cross-SDK interop vectors** — all 5 test vectors from §7 as parameterized tests
4. **Backward-compat shim tests** — verify `from kailash.mcp_server import MCPClient` still works and emits DeprecationWarning

## §11 Related Specs

- **SPEC-02** (Provider layer): providers use `ToolRegistry.get_openai_tools()` to declare tools to LLM
- **SPEC-03** (Composition wrappers): `StreamingAgent` uses `ToolRegistry.execute()` during TAOD loop
- **SPEC-04** (BaseAgent slimming): `BaseAgent.configure_mcp()` uses `MCPClient.discover_and_register()`
- **SPEC-05** (Delegate facade): `Delegate(mcp_servers=[...])` creates `MCPClient` internally
- **SPEC-09** (Cross-SDK parity): canonical JSON-RPC types shared with Rust `crates/kailash-mcp/`

## §12 pyproject.toml

```toml
[project]
name = "kailash-mcp"
version = "0.1.0"
description = "Kailash MCP (Model Context Protocol) — canonical client, server, and tools"
readme = "README.md"
license = {text = "Apache-2.0"}
requires-python = ">=3.11"
authors = [{name = "Terrene Foundation", email = "info@terrene.foundation"}]

dependencies = [
    # Minimal core — just the protocol types and stdio transport
]

[project.optional-dependencies]
http = ["httpx>=0.27"]
sse = ["sse-starlette>=1.8"]
websocket = ["websockets>=12"]
auth-jwt = ["pyjwt>=2.8"]
auth-oauth = ["authlib>=1.3"]
server = ["mcp>=1.0"]  # official MCP Python SDK (FastMCP)
platform = ["kailash-mcp[server]"]  # platform server with contrib tools
full = ["kailash-mcp[http,sse,websocket,auth-jwt,auth-oauth,server,platform]"]

[project.scripts]
kailash-mcp = "kailash_mcp.platform_server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## §13 Rust Parallel (for cross-SDK alignment per ADR-008)

Rust crate structure (see `02-rs-research/01-rs-mcp-audit.md` for details):

```
crates/kailash-mcp/
├── Cargo.toml
├── src/
│   ├── lib.rs
│   ├── protocol/
│   │   ├── mod.rs                    // Canonical JsonRpcRequest/Response/Error
│   │   ├── jsonrpc.rs
│   │   └── types.rs                  // McpToolInfo, ServerInfo
│   ├── client.rs                     // McpClient<T: McpTransport>
│   ├── server/
│   │   ├── mod.rs                    // McpServerCore trait
│   │   └── dispatch.rs
│   ├── transport/
│   │   ├── mod.rs                    // McpTransport trait
│   │   ├── stdio.rs
│   │   ├── http.rs
│   │   └── sse.rs
│   ├── auth/
│   │   ├── mod.rs
│   │   ├── api_key.rs
│   │   └── jwt.rs
│   └── tools/
│       ├── mod.rs
│       ├── registry.rs               // Unified ToolRegistry
│       └── hydrator.rs               // BM25 hydrator
```

The canonical JSON-RPC types MUST serialize identically between Python and Rust (per §7 interop test vectors). Field ordering in JSON output MUST match the order specified in §7 (achieved via insertion-ordered dict in Python and `#[serde(rename_all = "camelCase")]` in Rust).
