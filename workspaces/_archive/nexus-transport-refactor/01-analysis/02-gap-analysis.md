# Gap Analysis — Brief Claims vs Actual State

## Claims Verified

| Brief Claim                                      | Status   | Notes                                                                                      |
| ------------------------------------------------ | -------- | ------------------------------------------------------------------------------------------ |
| core.py is 2,436 lines                           | VERIFIED | Exact match                                                                                |
| 11 FastAPI coupling points                       | VERIFIED | All line ranges accurate within 1-2 lines                                                  |
| 6 MCP server implementations                     | VERIFIED | 3 in Nexus (delete), 3 in Core SDK (keep)                                                  |
| Two separate EventBus systems                    | VERIFIED | Core SDK EventBus exists; Nexus EventBus is proposed (current state is a simple event log) |
| channels.py has no framework imports             | VERIFIED | Pure config                                                                                |
| engine.py has no direct FastAPI imports          | VERIFIED | Only imports from nexus.core                                                               |
| CLI is standalone HTTP client                    | VERIFIED | Uses requests library                                                                      |
| kailash-rs has HandlerRegistry/EventBus patterns | VERIFIED | handler.rs, events/bus.rs match proposed Python design                                     |

## Hidden Coupling Points Not Mentioned in Brief

### 1. `_gateway.register_workflow()` (Line 781)

The brief only mentions `_gateway.app.*` coupling (FastAPI-level). But `self._gateway.register_workflow()` is a gateway-level call that doesn't go through the FastAPI app directly. When HTTPTransport is extracted in B0b, this call must be routed to the transport, not just the FastAPI app.

**Impact**: Medium. B0b must handle workflow registration on the HTTP transport, not just route registration.

### 2. `_gateway.health_check()` (Line 2147)

The `health_check()` method delegates to the gateway for health status. After B0b, this should aggregate health from all transports, not just HTTP.

**Impact**: Low. Health check can be extended additively.

### 3. `_gateway.enable_auth()` and `_gateway.enable_monitoring()` (Lines 2158-2174)

These progressive enhancement methods delegate to the gateway. After B0b, they should apply to the HTTP transport specifically (auth and monitoring are HTTP concerns).

**Impact**: Low. Already guarded by `hasattr`.

### 4. Dead Code in core.py (Lines 1929-2007)

Three methods appear unused or deferred:

- `_initialize_runtime_capabilities()` — "currently unused, reserved for v1.1"
- `_activate_multi_channel_orchestration()` — no callers found
- `_log_revolutionary_startup()` — duplicates `_log_startup_success()`

**Impact**: None for correctness, but increases maintenance burden during refactor. Should be cleaned up in B0a.

### 5. `broadcast_event()` / `get_events()` Compete with EventBus

The existing event log methods (lines 2254-2349) will conflict conceptually with the new EventBus. They use different data structures (list vs janus.Queue) and different event types (plain dict vs NexusEvent).

**Impact**: Medium. Must be migrated or deprecated during B0a to avoid confusion.

### 6. `create_gateway()` is from Core SDK

The `create_gateway()` function (line 26, imported from `kailash.servers.gateway`) is a Core SDK function. B0b needs to understand what it returns and what `.app` exposes. This is a cross-package dependency.

**Impact**: Medium. Need to verify that HTTPTransport can wrap or replace the gateway cleanly.

## Risk of Breaking the Public API

### LOW Risk (B0a)

B0a is a pure internal refactor. No public API changes. The main risk is:

- **Incorrect delegation**: If `HandlerRegistry` doesn't faithfully replicate the current behavior of `self._workflows` and `self._handler_registry` dicts, handlers may not register correctly.
- **Mitigation**: B0a tests must cover register(), handler(), register_handler() and verify MCP tool registration still works.

### MEDIUM Risk (B0b)

B0b moves FastAPI code into HTTPTransport. Public API methods that delegate to the gateway (`add_middleware`, `include_router`, `endpoint`) must continue working. The risks:

- **Middleware ordering**: Starlette's LIFO middleware ordering must be preserved.
- **Router validation**: `include_router()` validates against `FastAPI.APIRouter` — this import must still work.
- **Endpoint decorator timing**: `endpoint()` requires the gateway to exist at decoration time. If HTTPTransport is not yet created, this breaks.

### MEDIUM-HIGH Risk: External Plugins

External plugins loaded by `PluginLoader` may access `_gateway` directly. We cannot audit these. The deprecation warning + `app.fastapi_app` property is the correct mitigation, but some breakage is possible.

## B0a vs B0b Split Feasibility

### B0a Feasibility: HIGH

B0a creates 3 new files (registry.py, events.py, background.py) and modifies core.py to use them internally. No public API changes. The existing tests should pass unchanged.

**Concern**: The "1 session" estimate is aggressive. The full scope includes:

1. HandlerRegistry extraction (50-70 lines of new code, substantial refactoring of core.py)
2. EventBus implementation (100-150 lines of new code)
3. BackgroundService interface (50 lines)
4. Plugin audit (read-only)
5. Wire EventBus into HandlerRegistry
6. Wire BackgroundService into Nexus lifecycle
7. Migrate broadcast_event/get_events to use EventBus
8. Run full test suite

Items 1-4 are straightforward. Items 5-7 add integration complexity. Item 8 may reveal failures.

**Revised estimate**: 1 focused session if items 5-7 are deferred to a follow-up. Full scope is 1.5 sessions.

### B0b Feasibility: HIGH but Risky

B0b is the larger, riskier extraction. The 2-3 session estimate is reasonable.

**Main risk**: The `create_gateway()` function and its return type. HTTPTransport must either:

- Wrap the existing gateway (lowest risk, but doesn't fully decouple)
- Replace the gateway entirely (cleanest, but requires understanding Core SDK internals)

The brief suggests wrapping: `Nexus.__init__()` creates HTTPTransport, which internally uses `create_gateway()`. This is the right approach for B0b.
