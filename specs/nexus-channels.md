# Kailash Nexus Specification — Channels & Transports

Version: 2.1.1
Package: `kailash-nexus`

Parent domain: Kailash Nexus (multi-channel workflow platform). This file covers transport system (HTTP/MCP/WebSocket/Webhook), handler registry, channel configuration, CLI channel, service discovery, NexusFile, and input validation. See also `nexus-core.md`, `nexus-auth.md`, and `nexus-services.md`.

---

## 4. Transport System

### 4.1 Transport ABC

**Module:** `nexus.transports.base`

```python
class Transport(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def start(self, registry: HandlerRegistry) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @property
    @abstractmethod
    def is_running(self) -> bool: ...

    def on_handler_registered(self, handler_def: HandlerDef) -> None:
        pass  # Default no-op; override for hot-reload support
```

**Lifecycle contract:**

1. Transport instantiated with protocol-specific config.
2. Registered with `app.add_transport(transport)`.
3. `Nexus.start()` calls `transport.start(registry)`.
4. New handlers trigger `on_handler_registered()`.
5. `Nexus.stop()` calls `transport.stop()`.

### 4.2 HTTPTransport

**Module:** `nexus.transports.http`

Encapsulates all FastAPI/Starlette coupling. Creates the enterprise gateway, applies middleware, registers routes, and runs uvicorn.

**Key behaviors:**

- Gateway is created eagerly (during `Nexus.__init__`) so middleware/routers/endpoints can be applied before `start()`.
- Middleware, routers, and endpoints are queued if the gateway is not yet ready, then applied during `start()`.
- `run_blocking(host)` starts uvicorn in the current thread (called by `Nexus.start()`).
- `health_check()` returns transport status dict.

**Properties:**

- `app` -- the underlying FastAPI app (`None` before gateway creation).
- `gateway` -- the Core SDK gateway object.
- `port` -- the HTTP port.

### 4.3 MCPTransport

**Module:** `nexus.transports.mcp`

Registers all Nexus handlers as MCP tools with a namespace prefix (default `"nexus"`) to avoid collisions. Runs FastMCP in a background thread with its own event loop.

**Constructor:**

```python
MCPTransport(
    port: int = 3001,
    namespace: str = "nexus",
    server_name: str = "kailash-nexus",
    runtime=None,
)
```

**Tool naming:** `{namespace}_{handler_name}` (e.g., `nexus_greet`).

**Runtime sharing:** If an injected runtime is provided, acquires from it instead of creating a new pool (prevents orphan connection pools).

**Binding:** Binds to `127.0.0.1` only (security hardening).

### 4.4 WebSocketTransport

**Module:** `nexus.transports.websocket`

Bidirectional real-time communication over WebSocket using JSON-RPC style messages.

**Constructor:**

```python
WebSocketTransport(
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str = "/ws",
    ping_interval: float = 20.0,
    ping_timeout: float = 20.0,
    max_connections: Optional[int] = None,
    max_message_size: int = 1_048_576,  # 1 MiB
    runtime=None,
)
```

**Message Protocol (JSON over text frames):**

Request:

```json
{"id": "<uuid>", "method": "<handler-name>", "params": {...}}
```

Response:

```json
{"id": "<uuid>", "result": {...}}
```

Error:

```json
{ "id": "<uuid>", "error": { "code": -32601, "message": "Method not found" } }
```

Server push:

```json
{"event": "<type>", "data": {...}}
```

**Error codes:** `-32700` (parse error), `-32600` (invalid request), `-32601` (method not found), `-32000` (internal handler error).

**Connection lifecycle:**

1. Client opens WS to `ws://host:port/ws`.
2. Server assigns a connection ID, sends `{"event": "connected", "data": {"connection_id": "..."}}`.
3. Client sends JSON requests; server dispatches to handlers.
4. Either side may close; server cleans up.

**Max connections enforcement:** Returns close code `4013` with message `"Connection limit reached"` when exceeded.

**Path validation:** Returns close code `4004` with message `"Invalid path"` for requests to paths other than the configured path.

**Public API:**

- `on_connect(callback)` -- decorator for connect callbacks (receives `connection_id`).
- `on_disconnect(callback)` -- decorator for disconnect callbacks.
- `broadcast(event, data)` -- send event to all connected clients.
- `send_to(connection_id, event, data) -> bool` -- send to a specific client.
- `connection_count` -- number of active connections.
- `connections` -- read-only view of tracked connections.

**Resource cleanup:** `__del__` emits `ResourceWarning` if transport was not stopped.

#### 4.4.1 Class-based MessageHandler API

For per-connection state, subscription fanout, or any pattern that exceeds stateless request/response, register a `MessageHandler` subclass at a path via `Nexus.websocket(path)` decorator or `Nexus.register_websocket(path, handler_cls)`. The `MessageHandlerRegistry` (`app.websocket_handlers`) routes incoming frames to the handler's lifecycle hooks and tracks `Connection` objects with isolated `state: SimpleNamespace`.

**Lifecycle hooks (override in subclass, all async):**

- `async on_connect(self, conn)` — fired after handshake; initialize `conn.state.*`.
- `async on_message(self, conn, msg) -> Any` — fired per JSON-decoded frame; **return value contract** (issue #618):
  - `None` → no auto-reply (handler-owned `await conn.send_*`).
  - `dict` / `list` → auto-sent as JSON text frame via `conn.send_json`.
  - `str` → auto-sent as raw text frame via `conn.send_text`.
  - `bytes` → UTF-8 decoded then `conn.send_text`; invalid UTF-8 logged at WARN and dropped.
  - any other → best-effort `conn.send_json` with `default=str`; `TypeError`/`ValueError` logged at WARN.
- `async on_text(self, conn, text) -> Any` — same return-value contract as `on_message`.
- `async on_disconnect(self, conn)` — fired after socket close; `conn` already removed from `self.connections`.
- `async on_event(self, event)` — fanout hook called by `broadcast_event` (NOT by the framework directly).

**Tenant safety:** `on_message` auto-replies are scoped to the originating socket — no broadcast leakage. Per-connection unicast push from external publishers uses `Nexus.websocket_send_to(path, connection_id, payload)` (issue #618), which scopes dispatch to one tracked connection.

**Server-originated dispatch entry points (on `Nexus`):**

- `await app.websocket_broadcast(path, event)` — fires `on_event` on the handler at `path`; raises `KeyError` if no handler is registered. The handler decides which connections receive the event (typically by iterating `self.connections` and filtering by `conn.state`).
- `await app.websocket_send_to(path, connection_id, payload) -> bool` (issue #618) — sends `payload` to a single tracked connection. Returns `True` on successful send; `False` if path has no handler, `connection_id` is unknown, or the socket is closed / send failed. Payload typing: `dict`/`list` → JSON, `str` → text frame, `bytes` → UTF-8 decoded text frame.

**Cross-SDK parity (issue #618):** Both the `on_message` return-value contract and the `send_to(path, connection_id, payload)` primitive match the Rust kailash-rs#589 surface semantically per EATP D6.

### 4.5 WebhookTransport

**Module:** `nexus.transports.webhook`

Inbound webhook reception and outbound delivery with retry logic.

**Constructor:**

```python
WebhookTransport(
    secret: Optional[str] = None,
    signature_header: str = "X-Webhook-Signature",
    idempotency_header: str = "X-Idempotency-Key",
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    idempotency_ttl: float = 3600.0,
    max_idempotency_keys: int = 10000,
    max_deliveries: int = 10000,
)
```

**Inbound features:**

- HMAC-SHA256 signature verification (constant-time comparison).
- Idempotency key deduplication with TTL-based expiration.
- Response caching for duplicate requests.

**Outbound features:**

- Retry with exponential backoff (capped at `max_delay`).
- DNS pinning to prevent DNS rebinding attacks.
- SSRF prevention: rejects URLs resolving to private/internal IP ranges (RFC 1918, IPv4-mapped IPv6, loopback).
- HMAC-SHA256 signature on outbound payloads when `secret` is set.
- 2xx = success. 4xx (except 429) = permanent failure (no retry). 429 and 5xx trigger retries.

**Key methods:**

- `receive(handler_name, payload, ...)` -- process an inbound webhook.
- `deliver(handler_name, payload, target_url, send_func=None)` -- deliver payload with retry.
- `register_target(handler_name, url)` -- register outbound target.
- `compute_signature(payload_bytes) -> str` -- compute `sha256=<hex>` signature.
- `verify_signature(payload_bytes, signature) -> bool` -- constant-time verify.

---

## 5. Handler Registry

**Module:** `nexus.registry`

### 5.1 HandlerParam

```python
@dataclass
class HandlerParam:
    name: str
    param_type: str = "string"  # string, integer, float, bool, object, array, file
    required: bool = True
    default: Any = None
    description: str = ""
```

### 5.2 HandlerDef

```python
@dataclass
class HandlerDef:
    name: str
    func: Optional[Callable] = None
    params: List[HandlerParam] = field(default_factory=list)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 5.3 HandlerRegistry

Central registry for all handlers and workflows. Transports read from this registry.

**Metadata validation:** Workflow metadata must be JSON-serializable and under 64 KiB (`_METADATA_MAX_BYTES`). Metadata is shallow-copied on store to isolate caller-side top-level mutations.

**Parameter extraction:** Parameters are derived from function signatures via `inspect.signature()`. Type annotations are mapped: `str -> "string"`, `int -> "integer"`, `float -> "float"`, `bool -> "bool"`, `dict -> "object"`, `list -> "array"`, `NexusFile -> "file"`.

**Handler registration contract:**

- Name must be unique (raises `ValueError` on duplicate).
- `func` must be callable.
- Function must accept at least one parameter.

---

## 17. Channel Configuration

**Module:** `nexus.channels`

### 17.1 ChannelConfig

```python
@dataclass
class ChannelConfig:
    enabled: bool = True
    port: Optional[int] = None
    host: str = "0.0.0.0"
    additional_config: Dict[str, Any] = None
```

### 17.2 ChannelManager

Default ports: API = 8000, MCP = 3001, CLI = None.

Methods:

- `configure_api(**kwargs) -> ChannelConfig`
- `configure_cli(**kwargs) -> ChannelConfig`
- `configure_mcp(**kwargs) -> ChannelConfig`
- `create_unified_channels() -> Dict[str, Any]`
- `configure_health_endpoint(endpoint="/health") -> Dict[str, Any]`

Port auto-detection: `find_available_port(preferred_port, max_attempts=10)` scans ports starting from the preferred port.

---

## 18. CLI Channel

**Module:** `nexus.cli.main`

Command-line client that connects to a running Nexus server via HTTP.

**Entry point:** `python -m nexus.cli`

**Commands:**

- `list` -- list available workflows.
- `run <workflow> [--param key=value ...]` -- execute a workflow.

**Options:**

- `--url <base_url>` -- server URL (default `http://localhost:8000`).

**Parameter parsing:** `key=value` format. Values are parsed as JSON first; if parsing fails, treated as strings.

---

## 19. Service Discovery

**Module:** `nexus.discovery`

### 19.1 WorkflowDiscovery

Auto-discovers workflows from the filesystem when `auto_discovery=True`.

**Scan patterns:**

- `workflows/*.py`
- `*.workflow.py`
- `workflow_*.py`
- `*_workflow.py`
- `src/workflows/*.py`
- `app/workflows/*.py`

**Excluded files:** `__init__.py`, `setup.py`, `conftest.py`, `__pycache__`.

**Detection:** Finds `Workflow` instances, `WorkflowBuilder` instances, and zero-argument factory functions that return either.

**Naming:** Uses `{file_stem}.{object_name}` unless the object name is generic (`workflow`, `builder`, `wf`), in which case just the file stem is used.

---

## 20. NexusFile

**Module:** `nexus.files`

Transport-agnostic file parameter that normalizes file data across transports.

```python
@dataclass
class NexusFile:
    filename: str
    content_type: str = "application/octet-stream"
    size: int = 0
    _data: bytes = b""
```

**Factory methods:**

- `NexusFile.from_upload_file(upload_file)` -- from FastAPI/Starlette `UploadFile`.
- `NexusFile.from_path(path)` -- from local file path.
- `NexusFile.from_base64(data, filename, content_type=None)` -- from base64 (MCP transport).

**Reading:** `read() -> bytes` (sync), `aread() -> bytes` (async).

Handlers receive `NexusFile` regardless of transport. When a handler parameter is annotated as `NexusFile`, the `HandlerRegistry` maps it to `param_type="file"`.

---

## 21. Input Validation

**Module:** `nexus.validation`

### 21.1 validate_workflow_inputs

```python
def validate_workflow_inputs(
    inputs: Any,
    max_size: int = 10 * 1024 * 1024,  # 10MB
) -> Dict[str, Any]
```

**Checks (in order):**

1. Type validation: must be `dict`.
2. Size limit: JSON serialized size must be under `max_size`.
3. Dangerous key blocking: rejects `__class__`, `__init__`, `__dict__`, `__reduce__`, `__builtins__`, `__import__`, `__globals__`, `eval`, `exec`, `compile`, `__code__`, `__name__`, `__bases__`.
4. Key length: max 256 characters.
5. Dunder protection: keys starting with `__` are rejected.

### 21.2 validate_workflow_name

```python
def validate_workflow_name(name: str) -> str
```

**Checks:**

1. Must be a non-empty string.
2. No path separators (`/` or `\`).
3. No dangerous characters (`< > | & ; $ \` ! \* ?`).
4. Max length: 128 characters.
