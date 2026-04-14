# Kailash Nexus Specification — Core

Version: 2.0.1
Package: `kailash-nexus`
Install: `pip install kailash-nexus`

Parent domain: Kailash Nexus (multi-channel workflow platform). This file covers the core Nexus class, NexusEngine builder, preset system, plugin system, and complete usage examples. See also `nexus-channels.md`, `nexus-auth.md`, and `nexus-services.md`.

Nexus is a zero-configuration multi-channel workflow platform. A single `Nexus()` call creates a production-ready server that exposes registered workflows simultaneously as REST API endpoints, CLI commands, and MCP tools for AI agents. Nexus owns authentication (login, sessions, JWT middleware). PACT owns authorization (RBAC, policy, access control).

---

## 1. Architecture Overview

```
                     +-----------+
                     |   Nexus   |
                     |  (core)   |
                     +-----+-----+
                           |
         +-----------------+-----------------+
         |                 |                 |
   +-----+------+   +-----+------+   +------+-----+
   | HTTPTransport | MCPTransport | WebSocketTransport |
   | (FastAPI)     | (FastMCP)    | (websockets)       |
   +-----+------+   +-----+------+   +------+-----+
         |                 |                 |
    REST/OpenAPI     MCP Tools/       JSON-RPC over
    + CORS/Auth      Resources        WebSocket frames
```

### Component Ownership

| Component                 | Owner                     | Purpose                                              |
| ------------------------- | ------------------------- | ---------------------------------------------------- |
| `Nexus`                   | `core.py`                 | Orchestrator: lifecycle, registration, configuration |
| `NexusEngine`             | `engine.py`               | Builder-pattern wrapper with enterprise presets      |
| `HandlerRegistry`         | `registry.py`             | Central store for handlers and workflows             |
| `EventBus`                | `events.py`               | In-process event system with cross-thread safety     |
| `Transport` (ABC)         | `transports/base.py`      | Protocol adapter interface                           |
| `HTTPTransport`           | `transports/http.py`      | FastAPI/Starlette via Core SDK gateway               |
| `MCPTransport`            | `transports/mcp.py`       | FastMCP tool registration                            |
| `WebSocketTransport`      | `transports/websocket.py` | Bidirectional real-time JSON-RPC                     |
| `WebhookTransport`        | `transports/webhook.py`   | Inbound/outbound webhook delivery                    |
| `ProbeManager`            | `probes.py`               | Kubernetes health/readiness/startup probes           |
| `OpenApiGenerator`        | `openapi.py`              | OpenAPI 3.0.3 spec generation                        |
| `BackgroundService` (ABC) | `background.py`           | Non-transport lifecycle components                   |
| Preset system             | `presets.py`              | Pre-configured middleware stacks                     |
| Channel system            | `channels.py`             | Channel configuration and session management         |

### Layer Hierarchy

Nexus sits at the **Primitives** layer. `NexusEngine` sits at the **Engine** layer. Applications use `NexusEngine.builder()` by default; drop to `Nexus()` only when the engine cannot express the behavior.

---

## 2. Nexus Class

**Module:** `nexus.core`
**Import:** `from nexus import Nexus`

### 2.1 Constructor

```python
class Nexus:
    def __init__(
        self,
        api_port: int = 8000,
        mcp_port: int = 3001,
        enable_auth: Optional[bool] = None,
        enable_monitoring: bool = False,
        rate_limit: Optional[int] = 100,
        auto_discovery: bool = False,
        enable_http_transport: bool = False,
        enable_sse_transport: bool = False,
        enable_discovery: bool = False,
        rate_limit_config: Optional[Dict[str, Any]] = None,
        enable_durability: bool = True,
        server_type: str = "enterprise",
        max_workers: Optional[int] = None,
        preset: Optional[str] = None,
        cors_origins: Optional[List[str]] = None,
        cors_allow_methods: Optional[List[str]] = None,
        cors_allow_headers: Optional[List[str]] = None,
        cors_allow_credentials: bool = False,
        cors_expose_headers: Optional[List[str]] = None,
        cors_max_age: int = 600,
        runtime=None,
    )
```

**Parameters:**

| Parameter                | Type                          | Default        | Description                                                                                                                            |
| ------------------------ | ----------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `api_port`               | `int`                         | `8000`         | HTTP server port.                                                                                                                      |
| `mcp_port`               | `int`                         | `3001`         | MCP server port.                                                                                                                       |
| `enable_auth`            | `Optional[bool]`              | `None`         | `None` = auto (off in dev, on in prod). `True` = force on. `False` = force off (warns in production).                                  |
| `enable_monitoring`      | `bool`                        | `False`        | Enable monitoring features.                                                                                                            |
| `rate_limit`             | `Optional[int]`               | `100`          | Requests per minute. `None` = disabled (logs security warning).                                                                        |
| `auto_discovery`         | `bool`                        | `False`        | Scan filesystem for workflow files on start.                                                                                           |
| `enable_http_transport`  | `bool`                        | `False`        | Enable HTTP transport for MCP server.                                                                                                  |
| `enable_sse_transport`   | `bool`                        | `False`        | Enable SSE transport for MCP server.                                                                                                   |
| `enable_discovery`       | `bool`                        | `False`        | Enable MCP service discovery.                                                                                                          |
| `rate_limit_config`      | `Optional[Dict]`              | `None`         | Advanced rate limiting configuration.                                                                                                  |
| `enable_durability`      | `bool`                        | `True`         | Enable workflow checkpointing. Set `False` for testing.                                                                                |
| `server_type`            | `str`                         | `"enterprise"` | Gateway type: `"enterprise"`, `"durable"`, `"basic"`. Override via `NEXUS_SERVER_TYPE` env var.                                        |
| `max_workers`            | `Optional[int]`               | `None`         | Thread pool size. `None` = `min(4, cpu_count)`. Override via `NEXUS_MAX_WORKERS` env var.                                              |
| `preset`                 | `Optional[str]`               | `None`         | Middleware preset name.                                                                                                                |
| `cors_origins`           | `Optional[List[str]]`         | `None`         | CORS allowed origins. Defaults to `["*"]` in dev. Wildcard blocked in production.                                                      |
| `cors_allow_methods`     | `Optional[List[str]]`         | `None`         | CORS allowed methods.                                                                                                                  |
| `cors_allow_headers`     | `Optional[List[str]]`         | `None`         | CORS allowed headers.                                                                                                                  |
| `cors_allow_credentials` | `bool`                        | `False`        | Allow cookies/auth headers in CORS.                                                                                                    |
| `cors_expose_headers`    | `Optional[List[str]]`         | `None`         | CORS response headers exposed to browser.                                                                                              |
| `cors_max_age`           | `int`                         | `600`          | Preflight cache duration in seconds.                                                                                                   |
| `runtime`                | `Optional[AsyncLocalRuntime]` | `None`         | Shared runtime. If provided, Nexus acquires a reference (caller retains ownership). If `None`, Nexus creates and owns its own runtime. |

**Environment Variables:**

| Variable            | Effect                                                                                                    |
| ------------------- | --------------------------------------------------------------------------------------------------------- |
| `NEXUS_ENV`         | `"production"` auto-enables auth, rejects wildcard CORS origins. `"development"` (default) is permissive. |
| `NEXUS_SERVER_TYPE` | Overrides `server_type` parameter.                                                                        |
| `NEXUS_MAX_WORKERS` | Overrides `max_workers` parameter. Must be a positive integer.                                            |
| `NEXUS_API_KEY_*`   | Environment variables prefixed with `NEXUS_API_KEY_` are loaded as API keys (suffix becomes user ID).     |
| `NEXUS_PRODUCTION`  | When set, suppresses the default test API key.                                                            |

**Raises:**

- `ValueError` if `server_type` is not one of `{"enterprise", "durable", "basic"}`.
- `ValueError` if `max_workers < 1`.
- `ValueError` if `NEXUS_MAX_WORKERS` is not a valid integer.
- `ValueError` if `cors_origins=["*"]` in production environment.
- `RuntimeError` if the enterprise gateway fails to initialize.

**Construction Sequence:**

1. Validate and store configuration.
2. Determine auth mode based on `NEXUS_ENV`.
3. Create `EventBus(capacity=256)` and `HandlerRegistry(event_bus=...)`.
4. Create `HTTPTransport` with CORS and auth settings.
5. Create or acquire `AsyncLocalRuntime`.
6. Initialize the Core SDK enterprise gateway via `create_gateway()`.
7. Apply CORS middleware to the gateway.
8. Flush any queued middleware and routers.
9. Apply preset if specified.
10. Initialize revolutionary capabilities (session manager, performance tracking, channel registry).
11. Initialize MCP server (if `enable_http_transport=True` and `kailash_mcp` is available).

**Context Manager Protocol:**

```python
with Nexus() as app:
    app.register("my_workflow", workflow.build())
    app.start()
# close() called automatically on exit
```

**Resource Cleanup:**

`close()` releases MCP servers, then releases or closes the runtime. Idempotent. `__del__` emits `ResourceWarning` if the runtime was not released.

### 2.2 Workflow Registration

```python
def register(
    self,
    name: str,
    workflow: Workflow,
    metadata: Optional[Dict[str, Any]] = None,
) -> None
```

Registers a workflow for exposure on all channels simultaneously.

**Behavior:**

- If `workflow` has a `.build()` method (i.e., is a `WorkflowBuilder`), it is built automatically.
- Metadata is validated: must be JSON-serializable and under 64 KiB.
- The workflow is registered with the `HandlerRegistry`, the HTTP gateway, and the MCP channel/server.
- PythonCodeNode sandbox validation runs at registration time (logs warnings for blocked imports).
- Performance metrics track registration time.

**Endpoint Mapping:**

- `POST /workflows/{name}/execute` -- execute the workflow
- `GET /workflows/{name}/workflow/info` -- workflow metadata
- `GET /workflows/{name}/health` -- workflow health
- MCP tool: `workflow_{name}`
- CLI: `nexus execute {name}`

**Raises:**

- `ValueError` if metadata is not JSON-serializable or exceeds 64 KiB.
- Propagates gateway registration errors.

### 2.3 Handler Registration

```python
def handler(
    self,
    name: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Decorator
```

Decorator form. Registers an async/sync function as a multi-channel workflow, bypassing the PythonCodeNode sandbox. The function's signature is inspected to derive workflow parameters automatically.

```python
def register_handler(
    self,
    name: str,
    handler_func: Callable,
    description: str = "",
    tags: Optional[List[str]] = None,
    input_mapping: Optional[Dict[str, str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None
```

Non-decorator equivalent. Builds a `HandlerNode` workflow from the function and delegates to `register()`.

**Validation:**

- Workflow name is validated against dangerous characters, path separators, and length (max 128).
- `handler_func` must be callable and accept at least one parameter.
- Duplicate handler names raise `ValueError`.

**Contract:** The handler is exposed on all channels just like workflows registered via `register()`.

### 2.4 Custom Endpoint Registration

```python
def endpoint(
    self,
    path: str,
    methods: Optional[List[str]] = None,
    rate_limit: Optional[int] = None,
    **fastapi_kwargs,
) -> Decorator
```

Decorator for API-only custom REST endpoints (not exposed on CLI or MCP). Requires the gateway to be running.

```python
def register_endpoint(
    self,
    path: str,
    methods: List[str],
    handler: Callable,
    **fastapi_kwargs: Any,
) -> None
```

Programmatic equivalent. Works before `start()` by queueing on the `HTTPTransport`. This is the canonical hook used by DataFlow's fabric runtime to expose product/health/SSE/webhook handlers.

**Raises:**

- `ValueError` if `methods` is empty.
- `RuntimeError` if HTTP transport is not initialized.

### 2.5 Lifecycle

```python
def start(self) -> None  # Blocking
```

Starts the platform. Auto-discovers workflows if enabled, starts MCP server in a background thread, calls plugin startup hooks, then runs the HTTP gateway in the main thread (blocking). Stops on `KeyboardInterrupt` or `.stop()`.

```python
def stop(self) -> None
```

Graceful shutdown. Calls plugin shutdown hooks (reverse order), stops MCP channel/server, releases shared runtime.

```python
def close(self) -> None
```

Releases MCP servers and the shared runtime. Idempotent. Called by `stop()` and `__exit__`.

### 2.6 Property Access

| Property        | Type                    | Description                               |
| --------------- | ----------------------- | ----------------------------------------- |
| `fastapi_app`   | `FastAPI` or `None`     | The underlying FastAPI application.       |
| `middleware`    | `List[MiddlewareInfo]`  | List of registered middleware (copy).     |
| `routers`       | `List[RouterInfo]`      | List of included routers (copy).          |
| `plugins`       | `Dict[str, Any]`        | Installed plugins by name (copy).         |
| `cors_config`   | `Dict[str, Any]`        | Current CORS configuration.               |
| `active_preset` | `Optional[str]`         | Name of the active preset.                |
| `preset_config` | `Optional[NexusConfig]` | Configuration used for the active preset. |

---

## 3. NexusEngine

**Module:** `nexus.engine`
**Import:** `from nexus import NexusEngine, Preset`

Engine-layer wrapper around `Nexus` providing a builder-pattern API that matches `kailash-rs` for cross-SDK parity.

### 3.1 Preset Enum

```python
class Preset(Enum):
    NONE = "none"
    SAAS = "saas"
    ENTERPRISE = "enterprise"
```

### 3.2 EnterpriseMiddlewareConfig

```python
@dataclass(frozen=True)
class EnterpriseMiddlewareConfig:
    enable_csrf: bool = True
    enable_audit: bool = True
    enable_metrics: bool = True
    enable_error_handler: bool = True
    enable_security_headers: bool = True
    enable_structured_logging: bool = True
    enable_rate_limiting: bool = True
    rate_limit_rpm: int = 100
    enable_cors: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
```

Preset defaults:

- `SAAS`: CSRF off, audit off, metrics on, rate limit 200 RPM.
- `ENTERPRISE`: Everything on, rate limit 100 RPM.

### 3.3 Builder API

```python
engine = (
    NexusEngine.builder()
    .preset(Preset.SAAS)
    .bind("0.0.0.0:8080")
    .enterprise(EnterpriseMiddlewareConfig(...))  # Optional: overrides preset
    .config(enable_monitoring=True)                # Extra Nexus kwargs
    .governance(governance_engine, exempt_paths=["/health"])  # PACT authZ
    .build()
)
```

| Builder Method                 | Description                                                                              |
| ------------------------------ | ---------------------------------------------------------------------------------------- |
| `preset(p: Preset)`            | Set middleware preset.                                                                   |
| `enterprise(config)`           | Set explicit enterprise config (overrides preset).                                       |
| `bind(addr: str)`              | Set bind address (e.g., `"0.0.0.0:8080"`). Default: `"0.0.0.0:3000"`.                    |
| `config(**kwargs)`             | Pass additional kwargs to `Nexus()`.                                                     |
| `governance(engine, **kwargs)` | Register `PACTMiddleware`. Added AFTER auth middleware in LIFO order so auth runs first. |
| `build() -> NexusEngine`       | Build the engine.                                                                        |

### 3.4 NexusEngine Instance

| Property/Method                      | Description                                          |
| ------------------------------------ | ---------------------------------------------------- |
| `nexus`                              | Read-only access to the underlying `Nexus` instance. |
| `bind_addr`                          | Configured bind address.                             |
| `enterprise_config`                  | Enterprise middleware config, if set.                |
| `governance_engine`                  | Registered PACT `GovernanceEngine`, if any.          |
| `register(name, workflow, **kwargs)` | Delegates to `nexus.register()`.                     |
| `start(**kwargs)`                    | Delegates to `nexus.start()`.                        |
| `start_async(**kwargs)`              | Async start.                                         |
| `close()`                            | Delegates to `nexus.close()`.                        |

---

## 8. Preset System

**Module:** `nexus.presets`

### 8.1 Available Presets

| Preset          | Description                | Middleware                                                     | Plugins                               |
| --------------- | -------------------------- | -------------------------------------------------------------- | ------------------------------------- |
| `"none"`        | Bare instance              | --                                                             | --                                    |
| `"lightweight"` | Development/internal tools | CORS + Security Headers                                        | --                                    |
| `"standard"`    | Public APIs without auth   | CORS + Security Headers + CSRF + Rate Limiting + Error Handler | --                                    |
| `"saas"`        | Full SaaS stack            | Same as standard                                               | JWT + RBAC + Tenant Isolation + Audit |
| `"enterprise"`  | Enterprise features        | Same as standard                                               | Same as SaaS + SSO + Feature Flags    |

### 8.2 NexusConfig (Preset Configuration)

```python
@dataclass
class NexusConfig:
    cors_origins: List[str] = ["*"]
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]
    cors_allow_credentials: bool = False
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_audience: Optional[str] = None
    jwt_issuer: Optional[str] = None
    rbac_config: Optional[Dict] = None
    tenant_header: str = "X-Tenant-ID"
    tenant_required: bool = True
    rate_limit: Optional[int] = 100
    rate_limit_config: Optional[Dict] = None
    audit_enabled: bool = True
    audit_log_bodies: bool = False
    sso_provider: Optional[str] = None
    sso_config: Optional[Dict] = None
    feature_flags_provider: Optional[str] = None
    feature_flags_config: Optional[Dict] = None
    environment: str = "development"
```

**Security:** `__repr__` redacts secrets (jwt_secret, any key matching `secret|key|token|password|credential|private|certificate` patterns in sso_config).

### 8.3 Usage

```python
# Via constructor
app = Nexus(preset="saas", cors_origins=["https://app.example.com"])

# Inspecting
app.describe_preset()
# Returns: {"preset": "saas", "description": "...", "middleware": [...], "plugins": [...]}
```

---

## 10. Plugin System

**Module:** `nexus.plugins`

### 10.1 NexusPluginProtocol

```python
@runtime_checkable
class NexusPluginProtocol(Protocol):
    @property
    def name(self) -> str: ...
    def install(self, app: Nexus) -> None: ...
    # Optional:
    # def on_startup(self) -> None: ...
    # def on_shutdown(self) -> None: ...
```

### 10.2 add_plugin

```python
def add_plugin(self, plugin: Any) -> Nexus
```

- Validates that plugin has `name` and `install` attributes.
- Rejects duplicate plugin names (`ValueError`).
- Calls `plugin.install(self)` immediately.
- Registers `on_startup` and `on_shutdown` hooks if present.
- Returns `self` for chaining.

**Startup hooks:** Called in registration order during `start()`. Errors are logged but do not prevent other hooks.

**Shutdown hooks:** Called in reverse registration order during `stop()`.

---

## 29. Complete Usage Examples

### 29.1 Zero-Config

```python
from nexus import Nexus

app = Nexus()
app.register("my_workflow", workflow.build())
app.start()
```

### 29.2 With Preset

```python
app = Nexus(preset="saas", cors_origins=["https://app.example.com"])
app.register("pipeline", pipeline.build())
app.start()
```

### 29.3 Handler-Based

```python
app = Nexus()

@app.handler("greet", description="Greet a user")
async def greet(name: str, greeting: str = "Hello") -> dict:
    return {"message": f"{greeting}, {name}!"}

app.start()
```

### 29.4 NexusEngine (Engine Layer)

```python
from nexus import NexusEngine, Preset

engine = (
    NexusEngine.builder()
    .preset(Preset.ENTERPRISE)
    .bind("0.0.0.0:8080")
    .governance(governance_engine)
    .build()
)
engine.register("workflow", workflow.build())
engine.start()
```

### 29.5 DataFlow Integration

```python
app = Nexus()
db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: int
    name: str

app.integrate_dataflow(db)

@app.on_event("dataflow.User.create")
async def on_user_created(event):
    print(f"New user: {event.data['payload']}")
```

### 29.6 Full Enterprise

```python
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from kailash.trust.auth.jwt import JWTConfig
from nexus.probes import ProbeManager
from nexus.metrics import register_metrics_endpoint
from nexus.sse import register_sse_endpoint

app = Nexus(
    preset="enterprise",
    cors_origins=["https://app.example.com"],
    enable_auth=True,
)

# Auth
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret="..."),
    rbac={"admin": ["*"], "user": ["read:*"]},
    rate_limit=RateLimitConfig(requests_per_minute=200),
    tenant_isolation=TenantConfig(header="X-Tenant-ID"),
    audit=AuditConfig(backend="dataflow"),
)
app.add_plugin(auth)

# Probes
probes = ProbeManager()
probes.install(app.fastapi_app)
probes.mark_ready()

# Metrics & SSE
register_metrics_endpoint(app)
register_sse_endpoint(app)

# Register workflows
app.register("pipeline", pipeline.build())
app.start()
```
