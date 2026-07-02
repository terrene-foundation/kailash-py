# Nexus Transport Refactor — Architecture

## 1. Transport Protocol Design

### Transport ABC

Every Nexus transport implements this interface. A transport connects the handler registry to a specific protocol (HTTP, CLI, WebSocket, MCP, events). Transports are started/stopped independently and receive handler invocations from the registry.

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Transport(ABC):
    """Abstract base for all Nexus transports."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique transport name (e.g., 'http', 'cli', 'mcp', 'ws')."""

    @abstractmethod
    async def start(self, registry: "HandlerRegistry") -> None:
        """Start the transport, reading handlers from the registry.

        The transport builds its dispatch mechanism from the registry
        and begins accepting connections/commands.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the transport."""

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Whether the transport is currently accepting requests."""

    def on_handler_registered(self, handler_def: "HandlerDef") -> None:
        """Called when a new handler is registered after startup.

        Default: no-op. Transports that support hot-reload override this.
        """
        pass
```

### Flow

Transports do NOT register with the registry. The flow is:

1. User registers handlers with `Nexus` (which delegates to `HandlerRegistry`)
2. User calls `app.start()`
3. `Nexus.start()` passes the `HandlerRegistry` to each registered transport's `start()` method
4. Each transport reads the registry and builds its dispatch layer

For hot-reload: the EventBus publishes `HANDLER_REGISTERED` events, and transports that support dynamic registration subscribe to these events.

## 2. HandlerRegistry (The Core)

### Data Types

```python
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class HandlerParam:
    """Parameter definition for a handler."""
    name: str
    param_type: str  # "string", "integer", "float", "bool", "object", "array", "file"
    required: bool = True
    default: Any = None
    description: str = ""


@dataclass
class HandlerDef:
    """Complete definition of a registered handler (transport-agnostic)."""
    name: str
    func: Callable  # async def handler(**params) -> Any
    params: List[HandlerParam]
    description: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### Registry Class

```python
class HandlerRegistry:
    """Central handler store. All transports read from this."""

    def __init__(self, event_bus: "EventBus"):
        self._handlers: Dict[str, HandlerDef] = {}
        self._workflows: Dict[str, Any] = {}  # Legacy workflow support
        self._event_bus = event_bus

    def register_handler(self, handler_def: HandlerDef) -> None:
        self._handlers[handler_def.name] = handler_def
        self._event_bus.publish(NexusEvent.handler_registered(handler_def.name))

    def register_workflow(self, name: str, workflow: Any) -> None:
        self._workflows[name] = workflow
        # Build a HandlerDef wrapper around the workflow

    def get_handler(self, name: str) -> Optional[HandlerDef]:
        return self._handlers.get(name)

    def list_handlers(self) -> List[HandlerDef]:
        return list(self._handlers.values())

    def get_workflow(self, name: str) -> Optional[Any]:
        return self._workflows.get(name)

    def list_workflows(self) -> List[str]:
        return list(self._workflows.keys())
```

### Integration with Nexus Class

The existing `Nexus` class delegates to `HandlerRegistry` internally:

```python
class Nexus:
    def __init__(self):
        self._event_bus = EventBus()
        self._registry = HandlerRegistry(self._event_bus)
        # ... existing initialization ...

    def register(self, name: str, workflow) -> None:
        # Delegates to registry (replaces direct _workflows dict)
        self._registry.register_workflow(name, workflow)

    def register_handler(self, name: str, func: Callable, **kwargs) -> None:
        handler_def = HandlerDef(name=name, func=func, ...)
        self._registry.register_handler(handler_def)

    def handler(self, name: str, **kwargs):
        def decorator(func):
            self.register_handler(name, func, **kwargs)
            return func
        return decorator
```

This is a pure internal refactor in B0a. Zero public API changes.

## 3. EventBus Design (janus.Queue)

### Why janus, Not asyncio.Queue

The MCP server runs in a background thread. `asyncio.Queue` is designed for a single event loop and is NOT thread-safe. If the MCP thread writes to an `asyncio.Queue`, it will corrupt internal state. `janus` provides:

- A sync-side queue (`queue.sync_q.put()`) for threads
- An async-side queue (`queue.async_q.get()`) for the event loop
- Thread-safe bridging between the two

This matches Rust's `tokio::sync::broadcast` which is `Send + Sync`.

### Event Types

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Dict, Optional


class NexusEventType(str, Enum):
    HANDLER_REGISTERED = "handler_registered"
    HANDLER_CALLED = "handler_called"
    HANDLER_COMPLETED = "handler_completed"
    HANDLER_ERROR = "handler_error"
    HEALTH_CHECK = "health_check"
    CUSTOM = "custom"


@dataclass
class NexusEvent:
    event_type: NexusEventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    data: Dict[str, Any] = field(default_factory=dict)
    handler_name: Optional[str] = None
    request_id: Optional[str] = None

    @classmethod
    def handler_registered(cls, name: str) -> "NexusEvent":
        return cls(
            event_type=NexusEventType.HANDLER_REGISTERED,
            handler_name=name,
            data={"handler_name": name},
        )
```

### EventBus Implementation

```python
import asyncio
import janus
import logging
from typing import Callable, List

logger = logging.getLogger(__name__)


class EventBus:
    """In-process pub/sub event bus using janus.Queue.

    Mirrors kailash-rs EventBus semantics:
    - publish() is non-blocking (fire-and-forget to all subscribers)
    - subscribe() returns a janus async queue
    - subscribe_filtered() returns a queue that only receives matching events
    - Bounded buffers prevent memory exhaustion
    - Thread-safe: sync publish from MCP thread, async consume from event loop
    """

    def __init__(self, capacity: int = 256):
        self._capacity = capacity
        self._subscribers: List[janus.Queue] = []
        self._filtered_subscribers: List[tuple] = []  # (janus.Queue, filter_fn)

    def publish(self, event: NexusEvent) -> None:
        """Publish an event to all subscribers. Non-blocking, thread-safe."""
        for jq in self._subscribers:
            try:
                jq.sync_q.put_nowait(event)
            except janus.SyncQueueFull:
                # Drop oldest event (lagging subscriber) — matches tokio broadcast
                try:
                    jq.sync_q.get_nowait()
                    jq.sync_q.put_nowait(event)
                except (janus.SyncQueueEmpty, janus.SyncQueueFull):
                    pass

        for jq, filter_fn in self._filtered_subscribers:
            if filter_fn(event):
                try:
                    jq.sync_q.put_nowait(event)
                except janus.SyncQueueFull:
                    try:
                        jq.sync_q.get_nowait()
                        jq.sync_q.put_nowait(event)
                    except (janus.SyncQueueEmpty, janus.SyncQueueFull):
                        pass

    def subscribe(self) -> janus.AsyncQueue:
        """Create a new subscriber that receives all events."""
        jq = janus.Queue(maxsize=self._capacity)
        self._subscribers.append(jq)
        return jq.async_q

    def subscribe_filtered(
        self, filter_fn: Callable[[NexusEvent], bool]
    ) -> janus.AsyncQueue:
        """Create a subscriber that only receives events matching the filter."""
        jq = janus.Queue(maxsize=self._capacity)
        self._filtered_subscribers.append((jq, filter_fn))
        return jq.async_q

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers) + len(self._filtered_subscribers)
```

### How Events Trigger Handlers (@app.on_event)

```python
# User API
@app.on_event("user.created")
async def notify_user(event_data: dict) -> dict:
    return {"notified": True}

# Internal: registers a handler AND subscribes to the event type
# EventTransport subscribes to EventBus, filters for matching events,
# invokes handler when event fires
```

The `EventTransport` pattern: subscribe to the EventBus, filter for events matching registered event handlers, invoke the handler function. Fundamentally the same as HTTP invoking a handler on a request, just triggered by an internal event instead of an external HTTP request.

## 4. BackgroundService Interface

```python
from abc import ABC, abstractmethod
from typing import Coroutine


class BackgroundService(ABC):
    """Lifecycle interface for non-transport background work.

    Not a Transport — scheduled jobs, webhook delivery, etc. are not
    network protocols. They fire internally via direct function invocation.
    """

    @abstractmethod
    def register(self, name: str, coro: Coroutine) -> None:
        """Register a background task."""

    @abstractmethod
    async def start(self) -> None:
        """Start the background service."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the background service."""

    @abstractmethod
    def is_healthy(self) -> bool:
        """Whether the service is running and healthy."""
```

This is ~50 lines. Concrete implementations: `SchedulerBackgroundService` (TSG-222), `WebhookDeliveryService` (TSG-226).

## 5. Migration Path: B0a then B0b

### B0a: Extract HandlerRegistry + EventBus + BackgroundService (1 session)

**Internal ordering** (if session runs long, HandlerRegistry alone unblocks Phase 2):

1. **HandlerRegistry extraction**: Create `nexus/registry.py`. Move `_workflows` and `_handler_registry` dicts from `Nexus` class to `HandlerRegistry`. All `app.register()`, `@app.handler()` methods delegate to `HandlerRegistry`. Pure refactor, testable independently.

2. **EventBus implementation**: Create `nexus/events.py`. Add `janus>=1.0` dependency. Implement `EventBus` with `NexusEvent` and `NexusEventType`. Wire into `HandlerRegistry` (publish on registration). New feature, but no public API change.

3. **BackgroundService interface**: Create `nexus/background.py`. ~50 lines, abstract interface only. Wire lifecycle into `Nexus.start()` and `Nexus.stop()`.

**Plugin audit**: Audit all existing plugins for direct `_gateway` access. Document findings in `nexus/MIGRATION.md`. This is a read operation — no code changes.

### B0b: Extract HTTPTransport + MCPTransport (2-3 sessions)

**HTTPTransport extraction**:
- Move all FastAPI/gateway code into `nexus/transports/http.py`
- `Nexus.__init__()` creates `HTTPTransport` by default
- `add_middleware()`, `include_router()`, `endpoint()` on `Nexus` delegate to `HTTPTransport`
- Expose `app.fastapi_app` property (replaces private `_gateway.app`)
- Deprecation warning on `_gateway.app` access

**MCPTransport extraction**:
- Consolidate 6 MCP implementations to single FastMCP-backed `MCPTransport`
- Delete old files: `mcp/server.py`, `mcp/transport.py`, `mcp_websocket_server.py`
- `MCPTransport.start()` receives `HandlerRegistry`, registers all handlers as FastMCP tools
- Runs in background thread (preserves existing threading model)

**Backward-compatible delegation**:
```python
# After B0b, these all delegate to HTTPTransport:
app.add_middleware()      # -> HTTPTransport.add_middleware()
app.include_router()      # -> HTTPTransport.include_router()
app.endpoint()            # -> HTTPTransport.endpoint()

# If no HTTP transport configured, raises clear error:
# "Middleware is HTTP-specific. No HTTP transport is configured."
```

## 6. Coupling Map from core.py

Every point where FastAPI/Starlette is directly coupled into Nexus, organized by extraction target:

### Moves to HTTPTransport (B0b)

| Line Range | What | Notes |
|---|---|---|
| 307-361 | `_initialize_gateway()` | Creates FastAPI app, applies all middleware |
| 330-341 | CORS middleware (`CORSMiddleware` from Starlette) | Applied via `self._gateway.app.add_middleware()` |
| 347-349 | Queued middleware application | `self._gateway.app.add_middleware()` |
| 353-356 | Queued routers application | `self._gateway.app.include_router()` |
| 824-975 | `endpoint()` decorator | FastAPI-native routes with `getattr(fastapi_app, method_lower)` |
| 889 | Rate limiter | Imports FastAPI `Request` type |
| 943-964 | Route registration | `self._gateway.app` |
| 1040-1041 | `add_middleware()` | Delegates to `self._gateway.app.add_middleware()` |
| 1102-1108 | `include_router()` | Validates against `_APIRouter` from FastAPI |
| 1134-1135 | Router application | `self._gateway.app.include_router()` |
| 1156-1159 | Route conflict detection | Reads `self._gateway.app.routes` |
| 1400-1425 | `_apply_cors_middleware()` | Starlette `CORSMiddleware` |
| 1763-1771 | `_execute_workflow()` | Imports and raises `fastapi.HTTPException` |
| 1811-1818 | `_run_gateway()` | `self._gateway.run()` (uvicorn) |
| 1899-1903 | `start()` | `self._gateway.run()` (main blocking call) |

### Already Decoupled (No Change Needed)

| File | Status | Notes |
|---|---|---|
| `cli/main.py` | HTTP client (requests lib) | Already a REST consumer |
| `mcp/server.py` | WebSocket server (websockets lib) | Independent transport, deleted in B0b |
| `mcp/transport.py` | WebSocket transport layer | Independent, deleted in B0b |
| `channels.py` | Config only | No framework imports |
| `engine.py` | Wrapper | No direct FastAPI imports |

### HTTP-Specific (Stay with HTTPTransport)

| File | Notes |
|---|---|
| `middleware/csrf.py` | Starlette `BaseHTTPMiddleware` |
| `middleware/security_headers.py` | Starlette `BaseHTTPMiddleware` |
| `openapi.py` | OpenAPI spec generation (HTTP by nature) |

## 7. NexusFile Design

### The Problem

File uploads work differently across channels:
- **HTTP**: multipart/form-data (`UploadFile`)
- **CLI**: file path on disk
- **MCP**: base64-encoded content
- **WebSocket**: base64 or chunked binary

### Solution: Transport-Agnostic File Abstraction

```python
from dataclasses import dataclass
from typing import BinaryIO
import asyncio
import base64
import io
import mimetypes
from pathlib import Path


@dataclass
class NexusFile:
    """Transport-agnostic file abstraction.

    All transports normalize file inputs to this type before
    invoking the handler. Handlers never know which transport
    delivered the file.
    """
    filename: str
    content_type: str
    size: int  # -1 if unknown (streaming)
    _reader: BinaryIO

    def read(self, n: int = -1) -> bytes:
        return self._reader.read(n)

    async def aread(self, n: int = -1) -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._reader.read, n)

    @classmethod
    def from_upload_file(cls, upload_file: "UploadFile") -> "NexusFile":
        """HTTP: FastAPI UploadFile -> NexusFile"""
        return cls(
            filename=upload_file.filename,
            content_type=upload_file.content_type or "application/octet-stream",
            size=upload_file.size or -1,
            _reader=upload_file.file,
        )

    @classmethod
    def from_path(cls, path: str) -> "NexusFile":
        """CLI: file path -> NexusFile"""
        p = Path(path)
        return cls(
            filename=p.name,
            content_type=mimetypes.guess_type(path)[0] or "application/octet-stream",
            size=p.stat().st_size,
            _reader=open(path, "rb"),
        )

    @classmethod
    def from_base64(cls, b64_content: str, filename: str = "upload") -> "NexusFile":
        """MCP/WebSocket: base64 content -> NexusFile"""
        content = base64.b64decode(b64_content)
        return cls(
            filename=filename,
            content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
            size=len(content),
            _reader=io.BytesIO(content),
        )
```

### Handler Usage

```python
@app.handler("upload_document")
async def upload_document(title: str, document: NexusFile) -> dict:
    content = await document.aread()
    return {"title": title, "size": len(content)}
```

Type annotation `NexusFile` auto-detects file parameter during handler registration. `HandlerParam(param_type="file")` is set automatically. Each transport knows to normalize its native file type when `param_type="file"`.

## 8. DataFlow-Nexus Event Bridge

### Two Separate EventBus Systems

| System | Location | Event Type | Backend | Thread Safety |
|---|---|---|---|---|
| DataFlow EventBus | `kailash.middleware.communication.event_bus` | `DomainEvent` | `InMemoryEventBus` (or Redis) | Single-thread (asyncio) |
| Nexus EventBus | `nexus/events.py` | `NexusEvent` | `janus.Queue` | Cross-thread safe |

DataFlow uses the Core SDK EventBus independently. It does NOT depend on Nexus. The bridge is an optional integration point.

### Bridge Architecture

```python
class DataFlowEventBridge:
    """Bridges DataFlow model write events to Nexus EventBus.

    Translates DomainEvent -> NexusEvent. Installed via app.integrate_dataflow(db).
    """

    def __init__(self, dataflow: "DataFlow", nexus_event_bus: "EventBus"):
        self._dataflow = dataflow
        self._nexus_event_bus = nexus_event_bus
        self._forwarded = 0

    def install(self) -> None:
        """Subscribe to DataFlow's Core SDK EventBus, forward to Nexus EventBus."""
        self._dataflow.event_bus.subscribe_all(self._translate_and_forward)

    def _translate_and_forward(self, domain_event: "DomainEvent") -> None:
        if not domain_event.event_type.startswith("dataflow."):
            return
        # Normalize tense: "dataflow.User.create" -> "dataflow.User.created"
        parts = domain_event.event_type.split(".")
        if len(parts) == 3 and not parts[2].endswith("d"):
            parts[2] = parts[2] + "d"
        normalized = ".".join(parts)

        nexus_event = NexusEvent(
            event_type=NexusEventType.CUSTOM,
            data={
                "event_type": normalized,
                "model": domain_event.data.get("model"),
                "operation": domain_event.data.get("operation"),
                "record_id": domain_event.data.get("record_id"),
            },
            handler_name=normalized,
        )
        self._nexus_event_bus.publish(nexus_event)
        self._forwarded += 1
```

### User Integration

```python
app = Nexus(auto_discovery=False)
df = DataFlow(db_url)
app.integrate_dataflow(df)  # Installs the event bridge

@app.on_event("dataflow.User.created")
async def on_user_created(event_data: dict) -> dict:
    # Fires whenever db.express.create("User", {...}) is called
    return {"notified": True}
```

### Auto-Enable Semantics

When a `DerivedModel` with `refresh="on_source_change"` is registered, DataFlow auto-enables event emission for that model's sources. Zero global opt-in required. Zero overhead on models not listed as DerivedModel sources.

## 9. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Breaking `add_middleware()` / `include_router()` | HIGH | B0b delegates to HTTPTransport, same behavior |
| `_gateway.app` direct access by users | MEDIUM | `app.fastapi_app` property + deprecation warning |
| Performance regression in handler dispatch | MEDIUM | Registry is dict lookup O(1), negligible overhead |
| Test coverage gaps from monolith split | HIGH | B0a and B0b have zero public API changes; existing tests pass unmodified |
| Plugin compatibility | MEDIUM | B0a audit identifies affected plugins; B0b adds deprecation warnings |
| Thread safety in EventBus | MEDIUM | janus.Queue provides thread-safe bridging |
| Dependency bloat from new transports | LOW | All new transports optional; use extras (`[scheduler]`, etc.) |

## 10. New Module Layout (After B0a + B0b)

```
packages/kailash-nexus/src/nexus/
    __init__.py                 # Public exports (unchanged)
    core.py                     # Nexus class (slimmed, delegates to modules)
    registry.py                 # NEW: HandlerDef, HandlerParam, HandlerRegistry
    events.py                   # NEW: NexusEvent, NexusEventType, EventBus
    background.py               # NEW: BackgroundService ABC
    types.py                    # NEW: NexusFile
    scheduler.py                # NEW: SchedulerBackgroundService
    webhooks.py                 # NEW: WebhookDeliveryService
    background_tasks.py         # NEW: BackgroundTaskManager, NexusBackground
    channels.py                 # Unchanged
    engine.py                   # Updated to use transport-aware init
    openapi.py                  # Unchanged (HTTP-specific by nature)
    MIGRATION.md                # NEW: Plugin audit findings, migration guide
    transports/
        __init__.py
        base.py                 # NEW: Transport ABC
        http.py                 # NEW: HTTPTransport (all FastAPI code)
        mcp.py                  # NEW: MCPTransport (FastMCP wrapper)
        events.py               # NEW: EventTransport
        websocket.py            # NEW: WebSocketTransport
        sse.py                  # NEW: SSETransport
    integrations/
        __init__.py
        dataflow.py             # NEW: DataFlowEventBridge
    middleware/
        csrf.py                 # Unchanged (moves under HTTPTransport scope)
        security_headers.py     # Unchanged
        cache.py                # NEW: ResponseCache
    cli/
        main.py                 # Unchanged (HTTP client)
```
