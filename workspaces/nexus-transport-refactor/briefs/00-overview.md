# Nexus Transport Refactor — Complete Brief

## What We Are Building

A transport abstraction layer for Kailash Nexus that decouples the handler registry from any specific network protocol. Today, Nexus IS FastAPI — the `Nexus` class in `core.py` (2,436 lines) directly creates a FastAPI app, applies Starlette middleware, registers FastAPI routes, and starts uvicorn. This means every new channel (WebSocket, scheduled jobs, event-driven handlers) must integrate with the FastAPI monolith.

After this refactor, Nexus becomes a **handler registry + event bus** with pluggable transports. Handlers are registered once; each transport (HTTP, MCP, WebSocket, events, scheduler) reads the registry and builds its own dispatch layer. This is the architecture that kailash-rs already implements.

## Why We Are Doing This

FastAPI constrains Nexus in three ways:

1. **New channels require FastAPI wiring**: Adding WebSocket, scheduled jobs, or event-driven handlers means weaving more code into an already 2,436-line monolith.
2. **MCP is a parallel codebase**: The MCP server already runs as a separate transport in a background thread, but it is not abstracted — there are 6 separate MCP server implementations that need consolidation to one FastMCP-backed implementation.
3. **Background services do not fit the HTTP model**: Scheduled handlers and event-driven handlers are not network protocols. They fire internally. Forcing them through a "transport" abstraction that implies network protocol translation is a category error.

## Architecture Overview

```
User code                           Internal                                      Transports
-----------                         --------                                      ----------
app.register("workflow", wf)  -->   HandlerRegistry                  ------>      HTTPTransport (FastAPI)
@app.handler("greet")         -->     holds all HandlerDefs           ------>      MCPTransport (FastMCP)
@app.on_event("user.created") -->                                    ------>      EventTransport
@app.scheduled("cleanup")     -->   EventBus (janus.Queue)           ------>      WebSocketTransport
                                      in-process pub/sub
                                    BackgroundService                 ------>      SchedulerBackgroundService
                                      lifecycle: start/stop/health
```

## The 12 Key Architecture Decisions

These decisions were established across 3 red team rounds and 10 journal entries (0030-0039). They are final.

### 1. B0 Split: B0a (registry) + B0b (transports)

The refactor is split into two phases. **B0a** extracts HandlerRegistry + EventBus + BackgroundService from core.py in 1 session. This unblocks all Phase 2 features immediately. **B0b** extracts HTTPTransport + MCPTransport in 2-3 sessions and can run in parallel with Phase 2 features.

*Rationale*: B0a alone unblocks EventBus and new features. B0b is the larger, riskier extraction that should not block downstream work.

### 2. BackgroundService, Not SchedulerTransport

Scheduled handlers use a `BackgroundService` concept, NOT a `SchedulerTransport`. A timer is categorically different from a network protocol. HTTP receives external requests; a scheduler fires internally. BackgroundService has its own lifecycle: `register()`, `start()`, `stop()`, `is_healthy()`. No protocol translation overhead — direct function invocation.

### 3. janus.Queue for Cross-Thread EventBus Safety

The MCP server runs in a background thread. `asyncio.Queue` is not thread-safe. `janus` provides both a sync-side `put()` and an async-side `get()`, enabling the MCP thread to publish events that the async event loop can consume. This mirrors the Rust EventBus which uses `tokio::sync::broadcast` (inherently `Send + Sync`).

### 4. FastMCP as Single MCP Server Primitive

There are 6 existing MCP server implementations. They are consolidated to a single FastMCP-backed `MCPTransport`. The 5 old implementations are deleted in B0b.

### 5. Transport Protocol (ABC)

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
        pass  # Default no-op for hot-reload support
```

### 6. HandlerDef as Transport-Agnostic Core

All handlers are stored as `HandlerDef` dataclasses: `name`, `func`, `params: List[HandlerParam]`, `description`, `tags`, `metadata`. Transports read these to build their dispatch layer. No transport-specific information in the handler definition.

### 7. EventBus Mirrors kailash-rs Semantics

`publish()` is non-blocking, `subscribe()` returns a queue, `subscribe_filtered()` returns filtered queue. Bounded buffer (capacity=256). Lagging subscriber drops oldest event (matches tokio broadcast).

### 8. NexusFile for Transport-Agnostic File Parameters

File uploads differ across channels (HTTP: multipart, CLI: path, MCP: base64, WebSocket: binary). `NexusFile` normalizes all to a single type with `read()` and `aread()`. Each transport converts its native file to `NexusFile` before invoking the handler.

### 9. DataFlow-Nexus Event Bridge

DataFlow model writes auto-emit events via the Core SDK EventBus (independent of Nexus). A `DataFlowEventBridge` translates these into Nexus events, enabling `@app.on_event("dataflow.User.created")` handlers. The bridge is installed via `app.integrate_dataflow(db)`.

### 10. Two Separate EventBus Systems

DataFlow uses Core SDK EventBus (`kailash.middleware.communication.event_bus` with `DomainEvent`). Nexus has its own EventBus (`nexus/events.py` with `NexusEvent`, backed by `janus.Queue`). The DataFlow-Nexus bridge connects them. They are not the same system.

### 11. Plugin Audit Before Refactoring

B0a includes an audit of all existing plugins for direct `_gateway` access. Findings are documented in `nexus/MIGRATION.md`. Plugins that access `_gateway.app` directly receive deprecation warnings in B0b; the public `app.fastapi_app` property replaces the private access.

### 12. Background Tasks via asyncio.create_task, Not FastAPI BackgroundTasks

`asyncio.create_task()` is truly concurrent and decoupled from request lifecycle. FastAPI BackgroundTasks is tied to the HTTP response lifecycle. Since handlers can be invoked from non-HTTP transports, `asyncio.create_task()` is the correct primitive.

## Red Team Findings That Shaped the Design

### Round 1 (15 findings)
- B0 must be split to reduce single-point-of-failure risk.
- Scheduler is BackgroundService, not Transport (category error).
- janus.Queue required for MCP thread safety.
- Plugin audit must happen before core.py refactoring.

### Round 2 (8 findings)
- B0a internal ordering: HandlerRegistry -> EventBus -> BackgroundService. If session runs long, HandlerRegistry alone unblocks Phase 2.
- MCP consolidation (6 -> 1 FastMCP) happens in B0b, not B0a. B0a preserves existing MCP code.
- DataFlow event bridge: auto-enable per DerivedModel, not global opt-in.

### Round 3 (3 gaps, all resolved)
- BackgroundService is built in B0a alongside EventBus (not a separate workspace). ~50 lines, does not materially change B0a scope.
- Convergence achieved: all findings resolved.

## FastAPI Coupling Map (Current State of core.py)

These are the exact coupling points that B0a and B0b resolve:

| Location (line range) | Coupling Point | Severity | Resolved In |
|---|---|---|---|
| 307-361 | `_initialize_gateway()` — creates FastAPI app, applies middleware | Critical | B0b |
| 330-341 | CORS middleware via Starlette API | High | B0b |
| 824-975 | `endpoint()` decorator — FastAPI route registration | Critical | B0b |
| 889 | Rate limiter imports FastAPI Request type | High | B0b |
| 943-964 | Route registration via `self._gateway.app` | Critical | B0b |
| 1040-1041 | `add_middleware()` delegates to `self._gateway.app` | High | B0b |
| 1102-1108 | `include_router()` validates against `_APIRouter` | Critical | B0b |
| 1400-1425 | CORS middleware application | High | B0b |
| 1763-1771 | `_execute_workflow()` raises `fastapi.HTTPException` | Medium | B0b |
| 1811-1818 | `_run_gateway()` calls `self._gateway.run()` (uvicorn) | High | B0b |
| 1899-1903 | `start()` calls `self._gateway.run()` | Critical | B0b |

**Already decoupled** (no refactor needed):
- MCP server (`mcp/server.py`) — independent WebSocket transport, runs in background thread
- CLI (`cli/main.py`) — standalone HTTP client, already a consumer of the HTTP transport
- Channels config (`channels.py`) — no framework imports
- Engine (`engine.py`) — wrapper, no direct FastAPI imports

## Public API Surface (Must Remain Unchanged)

```python
app = Nexus()
app.register("workflow_name", workflow.build())
app.register_handler("handler_name", handler_func)

@app.handler("greet")
async def greet(name: str) -> dict: ...

@app.endpoint("/custom", methods=["POST"])
async def custom(): ...

app.add_middleware(SomeMiddleware, **kwargs)
app.include_router(some_router, prefix="/api")
app.add_plugin(some_plugin)
app.start()
app.health_check()
```

All of these must continue to work identically after both B0a and B0b. New APIs are additive: `@app.on_event()`, `@app.scheduled()`, `app.emit()`, `app.run_in_background()`, `app.integrate_dataflow()`.

## File References

Primary refactoring target:
- `packages/kailash-nexus/src/nexus/core.py` — 2,436 lines, the monolith

Supporting modules (minimal coupling):
- `packages/kailash-nexus/src/nexus/channels.py` — config only
- `packages/kailash-nexus/src/nexus/engine.py` — wrapper
- `packages/kailash-nexus/src/nexus/mcp/server.py` — separate transport (deleted in B0b)
- `packages/kailash-nexus/src/nexus/mcp/transport.py` — WebSocket transport (deleted in B0b)
- `packages/kailash-nexus/src/nexus/middleware/` — Starlette middleware (moves to HTTPTransport)

Rust reference architecture:
- `kailash-rs/crates/kailash-nexus/src/nexus.rs` — handler registry pattern
- `kailash-rs/crates/kailash-nexus/src/handler.rs` — HandlerDef/HandlerFn
- `kailash-rs/crates/kailash-nexus/src/events/mod.rs` — NexusEvent enum
- `kailash-rs/crates/kailash-nexus/src/events/bus.rs` — EventBus (tokio broadcast)
