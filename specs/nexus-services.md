# Kailash Nexus Specification — Services & Observability

Version: 2.1.1
Package: `kailash-nexus`

Parent domain: Kailash Nexus (multi-channel workflow platform). This file covers the event system, middleware system, Kubernetes probes, OpenAPI generation, metrics, background services, session management, trust integration, performance targets, and event-driven handlers. See also `nexus-core.md`, `nexus-channels.md`, and `nexus-auth.md`.

---

## 6. Event System

**Module:** `nexus.events`

### 6.1 NexusEventType

```python
class NexusEventType(str, Enum):
    HANDLER_REGISTERED = "handler.registered"
    HANDLER_CALLED = "handler.called"
    HANDLER_COMPLETED = "handler.completed"
    HANDLER_ERROR = "handler.error"
    HEALTH_CHECK = "health.check"
    CUSTOM = "custom"
```

### 6.2 NexusEvent

```python
@dataclass
class NexusEvent:
    event_type: NexusEventType
    timestamp: datetime  # UTC, auto-generated
    data: Dict[str, Any]
    handler_name: Optional[str] = None
    request_id: Optional[str] = None
```

### 6.3 EventBus

In-process event bus with cross-thread safety using `janus.Queue` to bridge sync publishers (MCP thread) and async consumers (main event loop).

**Constructor:** `EventBus(capacity: int = 256)`

**Publishing:**

- `publish(event)` -- non-blocking, thread-safe. If queue is full, drops the oldest event. If no event loop is running yet, events are stored directly in history.
- `publish_handler_registered(name)` -- convenience method.
- `emit(event_type, data)` (on Nexus) -- publishes a `CUSTOM` event.

**Subscribing:**

- `subscribe() -> asyncio.Queue` -- receive all events.
- `subscribe_filtered(predicate) -> asyncio.Queue` -- receive events matching predicate.
- `subscriber_count` -- total number of active subscribers.

**History:**

- `get_history(session_id=None, event_type=None, limit=None) -> List[Dict]` -- read bounded deque (max 256 events). Returns legacy dict format for backward compatibility.

**Lifecycle:**

- `await bus.start()` -- starts async dispatch loop.
- `await bus.stop()` -- stops dispatch, closes janus queue.

**Dispatch loop:** Reads from the janus async queue and fans out to all subscribers. Lagging subscribers have events dropped (bounded queues).

**SSE endpoint:** `EventBus.sse_url()` returns `"/events/stream"` (matches kailash-rs API).

### 6.4 SSE Streaming

**Module:** `nexus.sse`

`register_sse_endpoint(nexus)` registers `GET /events/stream` on the HTTP transport.

- Query parameter: `event_type` (optional filter).
- Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`.
- Keepalive comments sent every 15 seconds.
- Subscriber cleanup on disconnect.

### 6.5 DataFlow Event Bridge

**Module:** `nexus.bridges.dataflow`

`DataFlowEventBridge` connects the DataFlow Core SDK `InMemoryEventBus` (emitting `DomainEvent` on model writes) to the Nexus `EventBus` (using `NexusEvent`).

**Subscribed operations:** `create`, `update`, `delete`, `upsert`, `bulk_create`, `bulk_update`, `bulk_delete`, `bulk_upsert`.

**Event naming:** `dataflow.{ModelName}.{action}` (e.g., `dataflow.User.create`).

**Installation:**

```python
app.integrate_dataflow(db)
# or manually:
bridge = DataFlowEventBridge()
bridge.install(nexus_event_bus, db)
```

**Contract:** Two separate event systems are connected by this bridge. They are NOT merged. Each maintains its own subscriber lists independently.

---

## 7. Middleware System

### 7.1 Adding Middleware

```python
def add_middleware(self, middleware_class: type, **kwargs) -> Nexus
```

- Middleware executes in LIFO order (last added = outermost = runs first on request). This follows Starlette's onion model.
- Can be called before or after `start()`. If gateway is not ready, middleware is queued.
- Validates that `middleware_class` is a class (not an instance).
- Warns on duplicate middleware class (non-blocking).
- Returns `self` for chaining.

### 7.2 Including Routers

```python
def include_router(
    self,
    router: APIRouter,
    prefix: str = "",
    tags: Optional[List[str]] = None,
    dependencies: Optional[List[Any]] = None,
    **kwargs,
) -> Nexus
```

- Validates that `router` is a FastAPI `APIRouter` instance.
- Warns on potential route prefix conflicts.
- Can be called before or after `start()` (queued if gateway not ready).

### 7.3 Built-in Middleware

#### SecurityHeadersMiddleware

**Module:** `nexus.middleware.security_headers`

Adds standard security headers to all HTTP responses:

| Header                      | Default Value                                                                                                            |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `Content-Security-Policy`   | `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains`                                                                                    |
| `X-Content-Type-Options`    | `nosniff`                                                                                                                |
| `X-Frame-Options`           | `DENY`                                                                                                                   |
| `X-XSS-Protection`          | `1; mode=block`                                                                                                          |
| `Referrer-Policy`           | `strict-origin-when-cross-origin`                                                                                        |
| `Permissions-Policy`        | `camera=(), microphone=(), geolocation=(), payment=()`                                                                   |

Configurable via `SecurityHeadersConfig(exclude_paths=(...))`. Excluded paths bypass header injection.

#### CSRFMiddleware

**Module:** `nexus.middleware.csrf`

Stateless CSRF protection via Origin/Referer header validation.

- Safe methods (`GET`, `HEAD`, `OPTIONS`, `TRACE`) bypass validation.
- Unsafe methods (`POST`, `PUT`, `DELETE`, `PATCH`) require Origin or Referer matching `allowed_origins`.
- `allow_missing_origin=True` permits requests without Origin AND Referer (for non-browser API clients).
- `exempt_paths` for webhook endpoints etc.
- Returns `403` with `{"error": "CSRF validation failed"}` on failure.

#### PACTMiddleware (Governance)

**Module:** `nexus.middleware.governance`

PACT authorization enforcement at the request boundary.

**Pipeline position:** `client -> [security headers] -> [CSRF] -> [auth] -> [PACTMiddleware] -> handler`

**Constructor:**

```python
PACTMiddleware(
    app,
    governance_engine: GovernanceEngine,  # MUST NOT be None
    exempt_paths: Optional[Iterable[str]] = None,
    role_address_state_key: str = "pact_role_address",
    require_role_address: bool = True,
)
```

**Behavior per request:**

1. Generate or propagate correlation ID (`X-Request-ID`).
2. Extract `role_address` from `scope["state"]["pact_role_address"]` or `X-PACT-Role-Address` header.
3. Derive structural action: `{method}:{first_path_segment}` (e.g., `post:api`).
4. Call `governance_engine.verify_action(role_address, action, context)`.
5. If allowed: pass through. If flagged: pass through with WARN log. If denied: 403 (blocked) or 429 (held).

**Fail-closed:** Missing `governance_engine` raises `PACTGovernanceError`. Any exception during verification returns 403. Missing `role_address` with `require_role_address=True` returns 403.

**Default exempt paths:** `/health`, `/healthz`, `/ready`, `/readyz`, `/live`, `/livez`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`.

**Cost context:** Reads `scope["state"]["pact_cost_usd"]`, validates with `math.isfinite()` (defeats NaN/Inf bypass).

#### ResponseCacheMiddleware

**Module:** `nexus.middleware.cache`

TTL-based response cache with LRU eviction, ETag support, and Cache-Control header parsing.

```python
@dataclass(frozen=True)
class CacheConfig:
    default_ttl: int = 60        # seconds
    max_entries: int = 1000
    no_cache_handlers: FrozenSet[str] = frozenset()
```

Features: TTL-based expiration, LRU eviction, ETag generation (SHA-256), Cache-Control parsing, per-handler exemption, thread-safe, cache statistics, programmatic invalidation.

#### RequestMetricsMiddleware

**Module:** `nexus.middleware.request_metrics`

Pure-ASGI middleware that records per-request HTTP metrics (`nexus_http_requests_total` + `nexus_http_request_duration_seconds`, see §14) into the prometheus default registry, so they surface on the existing `/metrics` endpoint.

**Constructor:**

```python
RequestMetricsMiddleware(
    app,
    *,
    exclude_paths=("/metrics", "/healthz", "/readyz", "/startup"),
)
```

**Behavior:**

- Opt-in via `NexusConfig.metrics_enabled` (default `False`); wired LAST in the `standard` / `saas` / `enterprise` preset chains so it is outermost (LIFO) and measures total request latency including all other middleware.
- Records each request under labels `method` / `route` / `status`. The `route` label is the matched route TEMPLATE (`/users/{id}` from `scope["route"]`), never the concrete path, with an `__unmatched__` sentinel when no route matched — bounding Prometheus label cardinality against path-scanning DoS.
- An unhandled handler exception (no `http.response.start` emitted) is recorded with `status="500"`, then re-propagated (the middleware does not swallow exceptions).
- Detects `prometheus_client` availability once at construction; when absent it is a cheap pass-through and logs a one-time WARNING naming `pip install kailash-nexus[metrics]`.
- Requests to `exclude_paths` are passed through without a metric (so the scrape path and probes do not pollute route labels).

---

## 12. Kubernetes Probes

**Module:** `nexus.probes`

### 12.1 ProbeState

```python
class ProbeState(Enum):
    STARTING = "starting"
    READY = "ready"
    DRAINING = "draining"
    FAILED = "failed"
```

**Allowed transitions (monotonic during normal operation):**

- `STARTING -> READY`
- `STARTING -> FAILED`
- `READY -> DRAINING`
- `READY -> FAILED`
- `DRAINING -> FAILED`
- `FAILED` is terminal (only `reset()` can recover).

### 12.2 ProbeManager

Thread-safe state management with atomic transitions (`threading.Lock`).

**State transitions:**

- `mark_ready() -> bool` -- STARTING -> READY.
- `mark_draining() -> bool` -- READY -> DRAINING.
- `mark_failed(reason) -> bool` -- any state -> FAILED.
- `reset()` -- any state -> STARTING (for recovery/testing).

**Probe checks:**

- `check_liveness() -> ProbeResponse` -- 200 for all states except FAILED. Includes `uptime_seconds`.
- `check_readiness() -> ProbeResponse` -- 200 only in READY state AND all readiness callbacks pass. Includes `workflows` count.
- `check_startup() -> ProbeResponse` -- 200 once past STARTING state. Includes `startup_duration_seconds`.

**Readiness callbacks:** `add_readiness_check(callback)` registers a sync callable returning `bool`. All must return `True` for readiness.

### 12.3 Endpoints

`probes.install(app)` adds routes to a FastAPI/Starlette application:

| Endpoint       | Probe     | K8s Probe Type   |
| -------------- | --------- | ---------------- |
| `GET /healthz` | Liveness  | `livenessProbe`  |
| `GET /readyz`  | Readiness | `readinessProbe` |
| `GET /startup` | Startup   | `startupProbe`   |

---

## 13. OpenAPI Generation

**Module:** `nexus.openapi`

### 13.1 OpenApiInfo

```python
@dataclass
class OpenApiInfo:
    title: str = "Kailash Nexus API"
    version: str = "1.0.0"
    description: str = "Auto-generated API specification for Nexus workflows"
    terms_of_service: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    license_name: str = "Apache-2.0"
    license_url: str = "https://www.apache.org/licenses/LICENSE-2.0"
```

### 13.2 OpenApiGenerator

```python
class OpenApiGenerator:
    def __init__(
        self,
        info: Optional[OpenApiInfo] = None,
        title: Optional[str] = None,
        version: Optional[str] = None,
        servers: Optional[List[Dict[str, str]]] = None,
    )
```

**Registration methods:**

- `add_workflow(name, workflow, description="", tags=None)` -- auto-derives request schema from workflow metadata/node parameters.
- `add_handler(name, handler_func, description="", tags=None)` -- auto-derives request schema from function signature.

**Schema derivation:**

- Python type -> OpenAPI type: `str -> "string"`, `int -> "integer"`, `float -> "number"`, `bool -> "boolean"`, `list -> "array"`, `dict -> "object"`, `bytes -> "string" (format: binary)`.
- Handles `Optional[X]` (Union with None).
- Handles `List[X]` (array with items schema).
- Parameters with defaults are optional; without defaults are required.

**Output:**

- `generate() -> Dict[str, Any]` -- returns OpenAPI 3.0.3 spec dict.
- `generate_json(indent=2) -> str` -- returns JSON string.
- `install(app)` -- mounts `GET /openapi.json` on a FastAPI/Starlette app.

**Thread safety:** `generate()` produces an immutable spec from current state. Registration methods are not thread-safe (call during startup only).

---

## 14. Metrics

**Module:** `nexus.metrics`

`register_metrics_endpoint(nexus)` registers `GET /metrics` on the HTTP transport, replacing the gateway's existing `/metrics` route.

**Requires:** `prometheus_client` (optional dependency, install via `pip install kailash-nexus[metrics]`).

**Prometheus metrics registered:**

| Metric                                | Type      | Description                                      |
| ------------------------------------- | --------- | ------------------------------------------------ |
| `nexus_workflow_registration_seconds` | Histogram | Time to register a workflow.                     |
| `nexus_cross_channel_sync_seconds`    | Histogram | Time to sync state across channels.              |
| `nexus_failure_recovery_seconds`      | Histogram | Time to recover from a workflow failure.         |
| `nexus_session_sync_latency_seconds`  | Histogram | Latency of session synchronization.              |
| `nexus_active_sessions`               | Gauge     | Number of currently active sessions.             |
| `nexus_registered_workflows`          | Gauge     | Number of registered workflows.                  |
| `nexus_http_requests_total`           | Counter   | Total HTTP requests by method/route/status.      |
| `nexus_http_request_duration_seconds` | Histogram | Per-request HTTP latency by method/route/status. |

The first six metrics are synced from Nexus's internal performance deques on every `/metrics` scrape. Each deque value is observed exactly once (tracked via per-instance offset dict).

The two `nexus_http_*` metrics are recorded by `RequestMetricsMiddleware` (module `nexus.middleware.request_metrics`) — opt-in via `NexusConfig.metrics_enabled` (default `False` because `prometheus_client` is optional), wired LAST in the `standard` / `saas` / `enterprise` preset chains so it is the outermost middleware (LIFO) and measures total request latency including all other middleware. The `route` label is the matched route TEMPLATE (e.g. `/users/{id}`), never the concrete path, with an `__unmatched__` sentinel for unmatched traffic — bounding Prometheus label cardinality against path-scanning DoS. They surface on the same `/metrics` endpoint because they live in the prometheus default registry; an unhandled handler exception is recorded with `status="500"`.

---

## 15. Background Services

**Module:** `nexus.background`

```python
class BackgroundService(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def is_healthy(self) -> bool: ...
```

**Lifecycle contract:**

1. Service is instantiated and configured.
2. Registered with `app.add_background_service(service)`.
3. `Nexus.start()` calls `service.start()`.
4. Service runs until `Nexus.stop()` calls `service.stop()`.
5. `is_healthy()` is polled during health checks.

**Contract:** `start()` and `stop()` must be idempotent. `stop()` must complete within a reasonable timeout (default 30s). `is_healthy()` must be fast (no I/O).

---

## 16. Session Management

### 16.1 Cross-Channel Sessions

```python
def create_session(self, session_id: str = None, channel: str = "api") -> str
```

Creates a cross-channel synchronized session. Auto-generates UUID if `session_id` is `None`. Lazily initializes the `SessionManager`.

```python
def sync_session(self, session_id: str, channel: str) -> dict
```

Syncs session data across channels. Returns session data or `{"error": "Session not found"}`.

### 16.2 SessionManager

**Module:** `nexus.channels`

```python
class SessionManager:
    def create_session(self, session_id: str, channel: str) -> Dict[str, Any]
    def sync_session(self, session_id: str, channel: str) -> Optional[Dict[str, Any]]
    def update_session(self, session_id: str, data: Dict[str, Any]) -> None
```

Session data structure:

```python
{
    "id": session_id,
    "created_by": channel,
    "data": {},
    "channels": [channel],
}
```

Sync adds the requesting channel to the session's channel list.

---

## 22. Trust Integration

**Module:** `nexus.trust`

### 22.1 Headers

Provides trust-plane header injection and extraction for HTTP requests.

### 22.2 MCP Handler

Trust-plane integration for MCP tool invocations.

### 22.3 Session

Trust-aware session management that carries trust context across channels.

### 22.4 Trust Middleware

HTTP middleware that injects trust-plane context into requests.

---

## 27. Performance Targets

Nexus tracks internal performance metrics in bounded deques (max 10,000 entries per metric):

| Metric                       | Target      |
| ---------------------------- | ----------- |
| `workflow_registration_time` | < 1 second  |
| `cross_channel_sync_time`    | < 50ms      |
| `failure_recovery_time`      | < 5 seconds |
| `session_sync_latency`       | < 50ms      |

Access via `app.get_performance_metrics()`.

---

## 28. Event-Driven Handlers

### 28.1 @app.on_event

```python
@app.on_event("user.created")
async def on_user_created(event):
    print(f"User created: {event.data}")
```

Registers an event-driven handler invoked when a matching event is published to the EventBus.

### 28.2 @app.scheduled

```python
@app.scheduled("5m")
async def cleanup():
    await remove_expired_sessions()
```

Registers a periodic handler. Interval format: `{value}{unit}` where unit is `s` (seconds), `m` (minutes), `h` (hours), `d` (days). Value must be positive.

### 28.3 app.emit

```python
app.emit("order.completed", {"order_id": "123"})
```

Non-blocking custom event emission to the EventBus.

### 28.4 app.run_in_background

```python
task = app.run_in_background(send_email(user))
```

Runs a coroutine as a background task via `asyncio.create_task()`. Truly concurrent and decoupled from any HTTP request lifecycle. Task errors are logged, not propagated. Returns the `asyncio.Task` (can be cancelled).

## 29. FastAPI Lifespan + `fastapi_app` Property

Origin: GitHub issue #712 (2026-04-30). Downstream consumers needed an async startup hook (DataFlow `await db.create_tables_async()`, cache warming, upstream connection pre-open) and reached for `nexus.fastapi_app.on_event("startup")`. The property returned `None` immediately after `Nexus(...)` because the enterprise gateway is built lazily, and the downstream `.on_event(...)` raised `AttributeError`. The fix is documented here so consumers can pick the right surface.

### 29.1 `fastapi_app` Lazy-Init Timing Trap

`Nexus.fastapi_app` returns the underlying `FastAPI` app once the enterprise gateway is initialized — and `None` until then. Gateway init is **lazy**: it fires on the first `Nexus.register(...)` call or, failing that, at `Nexus.start()`. The state machine:

| Lifecycle event                          | `nexus.fastapi_app` returns          |
| ---------------------------------------- | ------------------------------------ |
| `Nexus(...)` (constructor only)          | `None`                               |
| `nexus.register("workflow", w)`          | `FastAPI` instance (lazy init fires) |
| `nexus.start()` (without prior register) | `FastAPI` instance (lazy init fires) |
| After `start()`                          | `FastAPI` instance                   |

Code that accesses `fastapi_app` immediately after `Nexus(...)` therefore sees `None`; any downstream attribute access (e.g. `nexus.fastapi_app.on_event("startup")`) raises `AttributeError: 'NoneType' object has no attribute 'on_event'`.

**Recommended pattern** for one-off async startup/shutdown hooks: `Nexus.add_startup_handler(func)` / `Nexus.add_shutdown_handler(func)` (see `specs/nexus-core.md` §10.3). Both methods queue the handler in `_startup_hooks` / `_shutdown_hooks` BEFORE the gateway is initialized, so they're safe to call immediately after `Nexus(...)`.

**Direct `on_event` is supported** — but only after a `register()` or `start()` has triggered gateway construction. Authors who hold a reference to `fastapi_app` early MUST either gate on `nexus.fastapi_app is not None` or migrate to `add_startup_handler`.

### 29.2 Lifespan-Handler Chain Order

When a Nexus consumer wraps the FastAPI app in a custom lifespan (the documented "I want to add my own startup logic" pattern), the chain MUST drive every registered handler list in the canonical order. The shared helper module `kailash.utils.lifespan` (issue #712 / S1) exposes the two drivers Nexus and every sibling FastAPI gateway uses:

```python
from kailash.utils import (
    drive_router_lifespan_startup,
    drive_router_lifespan_shutdown,
)
```

**Canonical lifespan chain** (Nexus's own lifespan implements this; custom lifespans MUST mirror it):

1. **`app.router.on_startup`** — driven via `drive_router_lifespan_startup(app)`. Iterates the SAME list Starlette's default `_DefaultLifespan` walks. Without this step, every handler registered via `@app.on_event("startup")` or `app.router.on_startup.append(...)` is silently dropped (the #500 bug pattern).
2. **Plugin / handler `_startup_hooks`** — populated by `add_plugin` (`specs/nexus-core.md` §10.2), `add_startup_handler` (§10.3), and Nexus's own internal init. Run in registration order. Per-hook exceptions are isolated; the FIRST captured exception is re-raised after all hooks complete.
3. **User code inside the lifespan body** (between Nexus's startup and shutdown halves).
4. **Plugin / handler `_shutdown_hooks`** — REVERSE registration order (last-registered runs first), mirroring resource (open, close) LIFO.
5. **`app.router.on_shutdown`** — driven via `drive_router_lifespan_shutdown(app, propagate_errors=False)`. The `propagate_errors=False` flag is correct for shutdown: cleanup paths are best-effort and a later handler MUST run even if an earlier one raises.

**`drive_router_lifespan_startup` / `_shutdown` contract:**

- Iterate `app.router.on_startup` / `app.router.on_shutdown` in registration order.
- Sync handlers (return `None`) are accepted; async handlers (return a coroutine) are awaited.
- Per-handler exceptions are isolated: if handler N raises, handlers N+1, N+2, ... still run.
- After all handlers complete, the FIRST captured exception is re-raised when `propagate_errors=True` (startup default — preserves uvicorn fail-fast). `propagate_errors=False` logs failures and returns normally (shutdown convention).

**Why a shared helper:** four sibling FastAPI sites (`WorkflowServer`, `KailashAPIGateway`, `WorkflowAPIGateway`, `WorkflowAPI`) each construct `FastAPI(lifespan=...)` and historically hand-rolled the iteration. Three of them shipped with the iteration missing entirely (the #500 silent-drop bug). Routing every site through one helper localizes the cross-version invariant per `rules/framework-first.md` § "Drive The Data, Not The Dispatch" — `app.router.on_startup` is the data structure FastAPI's own internal dispatcher walks, and is strictly more stable than any dispatch method name.

**Example — custom lifespan honoring router hooks:**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from kailash.utils import (
    drive_router_lifespan_startup,
    drive_router_lifespan_shutdown,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await drive_router_lifespan_startup(app)
    try:
        yield
    finally:
        await drive_router_lifespan_shutdown(app, propagate_errors=False)

app = FastAPI(lifespan=lifespan)

@app.on_event("startup")
async def warm_cache(): ...
```

**Cross-reference:**

- `specs/nexus-core.md` §10.3 `add_startup_handler` / `add_shutdown_handler` — the recommended Nexus-level surface for one-off hooks.
- `kailash.utils.lifespan` (`src/kailash/utils/lifespan.py`) — the shared driver module.
- `rules/framework-first.md` § "Drive The Data, Not The Dispatch" — the version-stable rationale.
