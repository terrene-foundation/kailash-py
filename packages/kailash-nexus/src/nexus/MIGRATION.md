# Nexus Transport Refactor -- Migration Guide

## B0a: Internal Registry Extraction (v1.7.0)

### Summary

B0a is a pure internal refactor. All public APIs remain unchanged.
Three new modules were extracted from `core.py`:

- `nexus/registry.py` -- `HandlerRegistry`, `HandlerDef`, `HandlerParam`
- `nexus/events.py` -- `EventBus`, `NexusEvent`, `NexusEventType`
- `nexus/background.py` -- `BackgroundService` ABC

Dead code removed from `core.py`:

- `_initialize_runtime_capabilities()` (explicitly marked "currently unused")
- `_activate_multi_channel_orchestration()` (no callers)
- `_log_revolutionary_startup()` (duplicated `_log_startup_success()`)

### Behavioral Changes

#### Event History (Minor)

`get_events()` now returns at most the 256 most recent events.
Previously, all events were retained indefinitely (potential memory leak
in long-running processes). The bounded buffer is an improvement.

If you depend on complete event history, use `EventBus.subscribe()` to
receive all events in real-time and maintain your own storage.

### New Public Types

These types are available from `nexus` package imports:

- `HandlerDef` -- Transport-agnostic handler definition
- `HandlerParam` -- Parameter definition for a handler
- `HandlerRegistry` -- Central handler/workflow registry
- `EventBus` -- In-process pub/sub event system
- `NexusEvent` -- Event dataclass
- `NexusEventType` -- Event type enum
- `BackgroundService` -- ABC for lifecycle services

### New Dependency

- `janus>=1.0` -- Thread-safe async/sync queue bridge (MIT license)

### Plugin Authors

Direct access to `app._gateway` is deprecated. In B0b, accessing
`_gateway` will emit a deprecation warning. Use `app.fastapi_app`
(property, available after B0b) instead of `app._gateway.app`.

**Current plugin audit findings:**

- Only `AuthPlugin` accesses `_gateway` (dead code path, guarded by `hasattr`)
- External plugins that access `_gateway` directly will receive
  deprecation warnings in B0b

## B0b: Transport Layer Extraction (v1.8.0)

### Summary

B0b extracts HTTP and MCP transport code from `core.py` into dedicated
transport modules. The Nexus class becomes a handler registry + event bus
coordinator with pluggable transports.

### Breaking Changes

**None for public API users.** All existing code continues to work:

- `app.register()`, `@app.handler()`, `app.register_handler()` -- unchanged
- `app.add_middleware()`, `app.include_router()`, `@app.endpoint()` -- unchanged
- `app.start()`, `app.stop()`, `app.health_check()` -- unchanged

### Deprecations

#### `app._gateway` (deprecated, will be removed in v2.0)

Direct access to `app._gateway` now emits a `DeprecationWarning`.

**Migration:**

```python
# Before (deprecated):
fastapi_app = app._gateway.app

# After:
fastapi_app = app.fastapi_app
```

### New Public Types

- `Transport` -- ABC for transport implementations
- `HTTPTransport` -- FastAPI-backed HTTP transport
- `MCPTransport` -- FastMCP-backed MCP transport
- `NexusFile` -- Transport-agnostic file parameter type

### New APIs

- `@app.on_event("event_type")` -- register event-driven handler
- `@app.scheduled("5m")` -- register scheduled handler
- `app.emit("event_type", data)` -- publish event to EventBus
- `app.run_in_background(coro)` -- run background coroutine
- `app.fastapi_app` -- access the FastAPI application
- `app.add_transport(transport)` -- register custom transport
- `app.add_background_service(service)` -- register background service
