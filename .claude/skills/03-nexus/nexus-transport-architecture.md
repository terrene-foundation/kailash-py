---
name: nexus-transport-architecture
description: "Nexus Transport ABC, HTTPTransport, MCPTransport, and HandlerRegistry architecture. Use when asking about 'Transport ABC', 'HTTPTransport', 'MCPTransport', 'HandlerRegistry', 'HandlerDef', 'custom transport', 'transport architecture', or 'handler extraction'."
---

# Nexus Transport Architecture

Transport abstraction layer that maps registered handlers to protocol-specific dispatch.

## Quick Reference

| Component         | Purpose                                                |
| ----------------- | ------------------------------------------------------ |
| `Transport` ABC   | Base class for all transports                          |
| `HTTPTransport`   | Maps handlers to Nexus HTTP routes                     |
| `MCPTransport`    | Maps handlers to FastMCP tools                         |
| `HandlerRegistry` | Central registry for all handler definitions           |
| `HandlerDef`      | Handler metadata (name, function, params, description) |
| `HandlerParam`    | Parameter metadata (name, type, default, required)     |

## Transport ABC

```python
from nexus.transports.base import Transport

class Transport(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique transport name (e.g., 'http', 'mcp')."""

    @abstractmethod
    async def start(self, registry: HandlerRegistry) -> None:
        """Start transport, reading handlers from registry."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop transport gracefully. Must be idempotent."""

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """True if transport is currently running."""

    def on_handler_registered(self, handler_def: HandlerDef) -> None:
        """Called when a new handler is registered after start().
        Default no-op. Override for hot-reload support."""
        pass
```

## Transport Lifecycle

1. Transport instantiated with protocol-specific config
2. Registered with Nexus via `app.add_transport(transport)`
3. `Nexus.start()` calls `transport.start(registry)`
4. As handlers are registered, `on_handler_registered()` fires
5. `Nexus.stop()` calls `transport.stop()`

## Built-in Transports

### HTTPTransport

Creates Nexus HTTP routes from registered handlers:

```python
from nexus.transports.http import HTTPTransport

transport = HTTPTransport(
    port=8000,
    cors_origins=["*"],
)
```

### MCPTransport

Registers handlers as FastMCP tools:

```python
from nexus.transports.mcp import MCPTransport

transport = MCPTransport()
```

## HandlerRegistry

Central store for all handler definitions. Handlers are registered via `@app.handler()` or `app.register()`.

```python
from nexus.registry import HandlerRegistry, HandlerDef, HandlerParam

# HandlerDef contains:
handler_def = HandlerDef(
    name="greet",
    func=greet_function,
    params=[
        HandlerParam(name="name", param_type="string", default=None, required=True),
        HandlerParam(name="greeting", param_type="string", default="Hello", required=False),
    ],
    description="Greet a user",
    tags=["greeting"],
)
```

### Parameter Extraction

`_extract_params(func)` introspects Python function signatures to produce `HandlerParam` lists. It handles:

- Type annotations (str, int, float, bool, list, dict)
- Default values
- Required vs optional parameters
- `NexusFile` type detection (for file upload handling)

```python
@app.handler("upload", description="Upload a file")
async def upload(file: NexusFile, name: str = "untitled") -> dict:
    # NexusFile is detected and handled specially per transport:
    # - HTTP: multipart upload -> NexusFile.from_upload_file()
    # - CLI: file path -> NexusFile.from_path()
    # - MCP: base64 string -> NexusFile.from_base64()
    return {"size": file.size, "name": name}
```

## Custom Transport

```python
from nexus.transports.base import Transport
from nexus.registry import HandlerRegistry, HandlerDef

class WebSocketTransport(Transport):
    @property
    def name(self) -> str:
        return "websocket"

    async def start(self, registry: HandlerRegistry) -> None:
        # Read all handlers and set up WS dispatch
        for handler_def in registry.list_handlers():
            self._register_ws_handler(handler_def)
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def on_handler_registered(self, handler_def: HandlerDef) -> None:
        # Hot-reload: add handler while running
        if self._running:
            self._register_ws_handler(handler_def)
```

## Source Code

- `packages/kailash-nexus/src/nexus/transports/base.py` -- Transport ABC
- `packages/kailash-nexus/src/nexus/transports/http.py` -- HTTPTransport
- `packages/kailash-nexus/src/nexus/transports/mcp.py` -- MCPTransport
- `packages/kailash-nexus/src/nexus/registry.py` -- HandlerRegistry, HandlerDef, HandlerParam
