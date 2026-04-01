# Nexus Transport Refactor — Implementation Plan

## Phase Overview

```
Phase 0 (Foundation)          Phase 1 (Features, parallel)         Phase 2 (Integration)
─────────────────────         ─────────────────────────────        ─────────────────────
B0a: Registry+EventBus  ───>  B2: @app.on_event (TSG-220)    ───>  B7: DataFlow bridge (TSG-250)
     + BackgroundService       B1: @app.scheduled (TSG-222)
     (TSG-210, 1 session)      B3: WebSocket (TSG-221)
         │                     B4: NexusFile (TSG-223)
         │                     B5: ResponseCache (TSG-224)
         v                     B6: SSE (TSG-225)
B0b: HTTPTransport        B8: Webhooks (TSG-226) [needs B2]
     + MCPTransport            B9: Background tasks (TSG-227)
     (TSG-211, 2-3 sessions)
     (parallel with Phase 1)
```

## Phase 0: Foundation (B0a + B0b)

### B0a: HandlerRegistry + EventBus + BackgroundService (TSG-210)

**Effort**: 1 autonomous session
**Dependencies**: None
**Blocks**: ALL subsequent Nexus work

This is the single keystone. It extracts three non-transport lifecycle abstractions from `core.py` into dedicated modules while keeping all public APIs unchanged.

**Internal ordering** (priority order if session runs long):

1. **HandlerRegistry extraction** — Create `nexus/registry.py`. Move `_workflows` and `_handler_registry` dicts from `Nexus` class. All `app.register()`, `@app.handler()` delegate to `HandlerRegistry`. Pure refactor, testable independently.

2. **EventBus implementation** — Create `nexus/events.py`. Add `janus>=1.0` dependency. Implement `EventBus` with `NexusEvent` and `NexusEventType`. Wire into `HandlerRegistry` (publish on registration).

3. **BackgroundService interface** — Create `nexus/background.py`. ~50 lines, abstract interface only. Wire lifecycle into `Nexus.start()` and `Nexus.stop()`.

4. **Plugin audit** — Audit all existing plugins for direct `_gateway` access. Document findings in `nexus/MIGRATION.md`.

**New files created**:
- `packages/kailash-nexus/src/nexus/registry.py`
- `packages/kailash-nexus/src/nexus/events.py`
- `packages/kailash-nexus/src/nexus/background.py`
- `packages/kailash-nexus/src/nexus/MIGRATION.md`

**Modified files**:
- `packages/kailash-nexus/src/nexus/core.py` — import and use new modules internally
- `packages/kailash-nexus/pyproject.toml` — add `janus>=1.0` dependency

**Validation**: ALL existing tests must pass unchanged. Zero public API changes.

### B0b: HTTPTransport + MCPTransport (TSG-211)

**Effort**: 2-3 autonomous sessions
**Dependencies**: B0a (TSG-210)
**Blocks**: Nothing in Phase 1 (can run in parallel with Phase 1 features)

Extracts HTTP and MCP transport code from `core.py` into dedicated transport classes.

**Session 1**: Transport ABC + HTTPTransport extraction
- Create `nexus/transports/base.py` with `Transport` ABC
- Create `nexus/transports/http.py` with `HTTPTransport`
- Move all FastAPI coupling points (see architecture.md coupling map) into `HTTPTransport`
- Wire `Nexus.add_middleware()`, `include_router()`, `endpoint()` to delegate to `HTTPTransport`
- Add `app.fastapi_app` property, deprecation warning on `_gateway.app`

**Session 2**: MCPTransport + FastMCP consolidation
- Create `nexus/transports/mcp.py` with `MCPTransport` wrapping FastMCP
- Audit and consolidate 6 MCP server implementations into one
- Delete old files: `mcp/server.py`, `mcp/transport.py`, `mcp_websocket_server.py`
- Verify tool registration matches current behavior

**Session 3** (if needed): Gateway refactor + NexusEngine update
- Replace `_initialize_gateway()` with `HTTPTransport` initialization
- Replace `_run_gateway()` / `start()` with transport-based startup
- Update `NexusEngine` builder for transport-aware initialization
- Run full test suite, fix any breakage

**New files created**:
- `packages/kailash-nexus/src/nexus/transports/__init__.py`
- `packages/kailash-nexus/src/nexus/transports/base.py`
- `packages/kailash-nexus/src/nexus/transports/http.py`
- `packages/kailash-nexus/src/nexus/transports/mcp.py`

**Files deleted**:
- `packages/kailash-nexus/src/nexus/mcp/server.py`
- `packages/kailash-nexus/src/nexus/mcp/transport.py`
- `packages/kailash-nexus/src/nexus/mcp_websocket_server.py` (if exists)

**Validation**: ALL existing tests must pass unchanged. `app.register()`, `@app.handler()`, `app.start()`, `app.health_check()`, `app.add_middleware()`, `app.include_router()`, `app.endpoint()` work as before.

---

## Phase 1: Features (Parallel after B0a)

All Phase 1 features depend only on TSG-210 (B0a). They can be implemented in parallel with B0b and with each other.

### B2: EventBus Handler Triggering (TSG-220)

**Effort**: 1 session
**Dependencies**: TSG-210
**Blocks**: TSG-250 (DataFlow bridge), TSG-226 (webhooks), TSG-227 (background tasks pattern)

Implements `@app.on_event()` decorator and `app.emit()` method. Creates `EventTransport` that subscribes to EventBus, filters for matching events, invokes handlers.

**Key implementation details**:
- `@app.on_event("user.created")` stores handler in `HandlerRegistry` with `metadata["event_type"]`
- `EventTransport.start()` subscribes to EventBus for all registered event types
- Wildcard matching via `fnmatch.fnmatch()`
- Handler invocation via `asyncio.create_task()` — non-blocking, errors logged not propagated

### B1: Scheduled Handlers (TSG-222)

**Effort**: 0.5 sessions
**Dependencies**: TSG-210

Implements `@app.scheduled()` decorator using `SchedulerBackgroundService` (not a Transport).

**Key implementation details**:
- Interval parsing: `"6h"` -> 21600, `"30m"` -> 1800, `"45s"` -> 45
- Cron parsing via `croniter` (optional dependency: `kailash-nexus[scheduler]`)
- Each handler runs as `asyncio.create_task()` loop
- Errors logged, scheduler continues running

### B3: WebSocket Channel (TSG-221)

**Effort**: 1 session
**Dependencies**: TSG-210

Adds WebSocket as the 4th Nexus channel.

**Key implementation details**:
- JSON message protocol: `{"handler": "name", "params": {...}, "request_id": "..."}`
- Registers `/ws` route with FastAPI app
- Reuses `HandlerRegistry` for dispatch — no handler duplication
- Connection state management via `WebSocketManager`

### B4: NexusFile Abstraction (TSG-223)

**Effort**: 0.5 sessions
**Dependencies**: TSG-210

Implements transport-agnostic file parameter handling.

**Key implementation details**:
- `NexusFile` dataclass with factory classmethods: `from_upload_file()`, `from_path()`, `from_base64()`
- Type annotation auto-detection: `document: NexusFile` in handler signature sets `param_type="file"`
- Each transport normalizes its native file type before handler invocation

### B5: ResponseCache Middleware (TSG-224)

**Effort**: 0.5 sessions
**Dependencies**: TSG-210

Adds HTTP response caching as Starlette middleware.

**Key implementation details**:
- `app.add_middleware(ResponseCache, ttl=300)` for global caching
- Per-handler TTL via `@app.handler("search", cache_ttl=60)`
- Model-scoped cache keys, `X-Cache: HIT/MISS` headers
- Auto-detects Redis or falls back to InMemoryCache
- SSE and non-200 responses excluded from caching

### B6: SSE Formalization (TSG-225)

**Effort**: 0.5 sessions
**Dependencies**: TSG-210

Formalizes Server-Sent Events as an explicit channel.

**Key implementation details**:
- `@app.sse_handler("stream/events")` decorator
- AsyncGenerator handler yields SSE event dicts
- Hand-rolled SSE formatting (30 lines, zero new dependencies)
- Heartbeat keepalive to prevent proxy timeouts

### B8: Webhook Delivery (TSG-226)

**Effort**: 0.5 sessions
**Dependencies**: TSG-210, TSG-220 (needs EventBus handler triggering)

Implements outbound webhook delivery triggered by EventBus events.

**Key implementation details**:
- `app.add_webhook("user.created", url="https://...")` registration
- HMAC-SHA256 signature in `X-Nexus-Signature` header
- Retry with exponential backoff (1s, 5s, 30s)
- `WebhookDeliveryService` implements `BackgroundService` ABC
- Uses `httpx.AsyncClient` for delivery

### B9: Background Tasks (TSG-227)

**Effort**: 0.5 sessions
**Dependencies**: TSG-210

Implements one-shot background task API.

**Key implementation details**:
- `app.run_in_background(coro)` via `asyncio.create_task()`
- `NexusBackground` injectable in handler signatures
- `BackgroundTaskManager` tracks running tasks, handles graceful shutdown
- Configurable shutdown timeout (default 30s)

---

## Phase 2: Integration

### B7: DataFlow-Nexus Event Bridge (TSG-250)

**Effort**: 1 session
**Dependencies**: TSG-101 (DataFlow on_source_change), TSG-201 (DataFlow EventMixin), TSG-220 (Nexus event handlers)
**Blocks**: Nothing

Cross-package integration connecting DataFlow write events to Nexus event handlers.

**Key implementation details**:
- `DataFlowEventBridge` translates `DomainEvent` -> `NexusEvent`
- Installed via `app.integrate_dataflow(db)`
- Auto-enable per DerivedModel — zero global opt-in
- Two separate EventBus systems connected by the bridge

---

## Session Effort Summary

| Todo | Description | Effort | Depends On | Phase |
|---|---|---|---|---|
| TSG-210 | B0a: Registry + EventBus + BackgroundService | 1 session | None | 0 |
| TSG-211 | B0b: HTTPTransport + MCPTransport | 2-3 sessions | TSG-210 | 0 |
| TSG-220 | B2: @app.on_event handler triggering | 1 session | TSG-210 | 1 |
| TSG-222 | B1: @app.scheduled handlers | 0.5 sessions | TSG-210 | 1 |
| TSG-221 | B3: WebSocket channel | 1 session | TSG-210 | 1 |
| TSG-223 | B4: NexusFile abstraction | 0.5 sessions | TSG-210 | 1 |
| TSG-224 | B5: ResponseCache middleware | 0.5 sessions | TSG-210 | 1 |
| TSG-225 | B6: SSE formalization | 0.5 sessions | TSG-210 | 1 |
| TSG-226 | B8: Webhook delivery | 0.5 sessions | TSG-210, TSG-220 | 1 |
| TSG-227 | B9: Background tasks | 0.5 sessions | TSG-210 | 1 |
| TSG-250 | B7: DataFlow-Nexus event bridge | 1 session | TSG-101, TSG-201, TSG-220 | 2 |

**Total**: ~9-10 autonomous sessions

**Critical path**: B0a (1 session) -> B0b (2-3 sessions, parallel with Phase 1) -> B7 (1 session, after DataFlow events ready)

**With full parallelization**: Phase 0 B0a (1 session) + Phase 1 all features (parallelized, ~1-2 sessions wall clock) + B0b (parallel, 2-3 sessions) + Phase 2 B7 (1 session) = ~4-5 sessions wall clock.

## Implementation Order (Recommended)

If implementing sequentially (single agent):

1. **TSG-210** (B0a) — Must be first. Unblocks everything.
2. **TSG-220** (B2) — EventBus handler triggering. Unblocks TSG-226, TSG-250.
3. **TSG-222** (B1) — Scheduled handlers. Quick win, 0.5 sessions.
4. **TSG-223** (B4) — NexusFile. Quick win, 0.5 sessions.
5. **TSG-227** (B9) — Background tasks. Quick win, 0.5 sessions.
6. **TSG-224** (B5) — ResponseCache. Quick win, 0.5 sessions.
7. **TSG-225** (B6) — SSE. Quick win, 0.5 sessions.
8. **TSG-211** (B0b) — HTTPTransport + MCPTransport. Largest item, 2-3 sessions.
9. **TSG-221** (B3) — WebSocket channel. 1 session.
10. **TSG-226** (B8) — Webhooks. 0.5 sessions. Needs TSG-220.
11. **TSG-250** (B7) — DataFlow bridge. 1 session. Needs DataFlow event work (TSG-101, TSG-201).

The rationale: B0a first (mandatory), then quick-win features to build momentum, then the larger B0b extraction, then features that depend on B0b or cross-package work.
