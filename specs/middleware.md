# Middleware

Enterprise middleware layer providing agent-UI communication, API gateway, authentication, real-time event streaming, MCP integration, and database-backed persistence. Built entirely on top of Kailash SDK components (nodes, workflows, runtime).

Source of truth: `src/kailash/middleware/`

## Package layout

- `core/` — `AgentUIMiddleware`, `DynamicSchemaRegistry`, `NodeSchemaGenerator`, workflow helpers
- `communication/` — `APIGateway`, `RealtimeMiddleware`, `EventStream`, event types
- `auth/` — `JWTAuthManager`, `MiddlewareAuthManager`, JWT models, access control
- `database/` — repositories and SQLAlchemy models for persistence
- `gateway/` — `DurableGateway`, `DurableRequest`, event store, deduplicator, checkpoints
- `mcp/` — `MiddlewareMCPServer`, `MCPToolNode`, `MCPResourceNode`, `MiddlewareMCPClient`

**Import constraint:** `communication/`, `auth/`, `gateway/`, and `database/` are in the kailash→nexus circular import chain (loaded during `kailash.middleware.__init__`). These modules import HTTP types from `starlette` directly, NOT from `nexus`. See `specs/nexus-core.md` § Import Architecture. `api_gateway.py` uses full FastAPI features (Depends, CORSMiddleware, app creation); `realtime.py` uses only Starlette types (Request, Response, WebSocket, StreamingResponse).

## Public exports (`src/kailash/middleware/__init__.py`)

The top-level `kailash.middleware` namespace re-exports:

```python
# Auth
from .auth.access_control import (
    MiddlewareAccessControlManager, MiddlewareAuthenticationMiddleware,
)
from .auth.auth_manager import AuthLevel, MiddlewareAuthManager
from .auth.jwt_auth import JWTAuthManager

# Communication
from .communication.api_gateway import APIGateway, create_gateway
from .communication.events import (
    EventFilter, EventPriority, EventStream, EventType,
    NodeEvent, UIEvent, WorkflowEvent,
)
from .communication.realtime import RealtimeMiddleware

# Core
from .core.agent_ui import AgentUIMiddleware
from .core.schema import DynamicSchemaRegistry, NodeSchemaGenerator
from .core.workflows import MiddlewareWorkflows, WorkflowBasedMiddleware

# Database
from .database import (
    CustomNodeModel, MiddlewareDatabaseManager,
    MiddlewareWorkflowRepository, WorkflowExecutionModel, WorkflowModel,
)

# MCP
from .mcp.client_integration import (
    MCPClientConfig, MCPServerConnection, MiddlewareMCPClient,
)
from .mcp.enhanced_server import (
    MCPResourceNode, MCPServerConfig, MCPToolNode, MiddlewareMCPServer,
)

__version__ = "1.0.0"
```

## Core (`src/kailash/middleware/core/`)

### `WorkflowSession` (`core/agent_ui.py`)

A WorkflowSession represents an active client session with isolated workflow and execution state.

```python
class WorkflowSession:
    def __init__(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc)
        self.workflows: Dict[str, Workflow] = {}    # workflow_id -> workflow
        self.executions: Dict[str, Dict] = {}        # execution_id -> execution_data
        self.active = True
```

**Methods:**

- `add_workflow(workflow_id: str, workflow: Workflow)` — register a `Workflow` instance under the given id.
- `start_execution(workflow_id: str, inputs: Optional[Dict[str, Any]] = None) -> str` — validates `workflow_id` exists in `self.workflows` (raises `ValueError` otherwise), generates a `uuid4` execution id, records an execution dict with keys `workflow_id`, `inputs`, `status="started"`, `created_at`, `progress=0.0`, `current_node=None`, `outputs={}`, `error=None`, and returns the execution id.
- `update_execution(execution_id: str, **updates)` — merges arbitrary kwargs (`status`, `progress`, `current_node`, `outputs`, `error`, etc.) into the execution record.

### `AgentUIMiddleware` (`core/agent_ui.py`)

Central orchestration hub for frontend communication.

```python
class AgentUIMiddleware:
    def __init__(
        self,
        enable_dynamic_workflows: bool = True,
        max_sessions: int = 1000,
        session_timeout_minutes: int = 60,
        enable_workflow_sharing: bool = True,
        enable_persistence: bool = True,
        database_url: Optional[str] = None,
        runtime=None,
    ):
```

**Constructor parameters** (exactly as in source — note ordering and defaults):

- `enable_dynamic_workflows: bool = True` — first positional flag; toggles runtime `WorkflowBuilder.from_dict()` support in `create_dynamic_workflow`.
- `max_sessions: int = 1000` — upper bound on concurrent sessions; beyond this, `create_session` calls `_cleanup_old_sessions` first.
- `session_timeout_minutes: int = 60` — inactive sessions older than this are eligible for cleanup.
- `enable_workflow_sharing: bool = True` — whether shared/template workflows (registered without a session_id or with `make_shared=True`) are kept in `self.shared_workflows`.
- `enable_persistence: bool = True` — toggles repository-backed persistence. Effective value is `enable_persistence and database_url is not None`; passing `enable_persistence=True` without a `database_url` disables persistence silently (it is effectively False).
- `database_url: Optional[str] = None` — connection string for `MiddlewareWorkflowRepository` and `MiddlewareExecutionRepository`.
- `runtime=None` — optional pre-constructed runtime. If provided, the middleware calls `runtime.acquire()` and takes a shared reference (`self._owns_runtime = False`). Otherwise it constructs its own `LocalRuntime(enable_async=True)` and sets `self._owns_runtime = True`.

There is NO `enable_event_streaming` parameter. Event streaming is always on — the constructor unconditionally creates `self.event_stream = EventStream(enable_batching=True)`.

**State initialized in `__init__`:**

- `self.enable_dynamic_workflows`, `self.max_sessions`, `self.session_timeout_minutes`, `self.enable_workflow_sharing`
- `self.enable_persistence = enable_persistence and database_url is not None`
- `self.event_stream = EventStream(enable_batching=True)`
- `self.runtime` (LocalRuntime or the acquired one)
- `self.node_registry = NodeRegistry()`
- `self.credential_manager = CredentialManagerNode(name="agent_ui_credentials", credential_name="agent_ui_secrets", credential_type="custom")`
- `self.data_transformer = DataTransformer(name="agent_ui_transformer")`
- If persistence is enabled: `self.workflow_repo = MiddlewareWorkflowRepository(database_url)` and `self.execution_repo = MiddlewareExecutionRepository(database_url)`
- `self.sessions: Dict[str, WorkflowSession] = {}`
- `self.shared_workflows: Dict[str, Workflow] = {}`
- `self.active_executions: Dict[str, Dict] = {}` — keyed by `execution_id`
- `self.start_time = time.time()`
- Counters: `self.sessions_created`, `self.workflows_executed`, `self.events_emitted`

Note: in the actual source, the session state (`self.sessions`, `self.shared_workflows`, `self.active_executions`, `self.start_time`, counters) is initialized AFTER the `close` method definition due to how the class body is laid out, but they are all present on a properly-constructed instance.

**Session management:**

- `async create_session(user_id: Optional[str] = None, session_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str` — generates a uuid4 if `session_id` is None; calls `_cleanup_old_sessions` if capacity hit; creates a `WorkflowSession`; emits a `workflow.started` event via `event_stream.emit_workflow_started`; returns the session id.
- `async get_session(session_id: str) -> Optional[WorkflowSession]`
- `async close_session(session_id: str)` — marks the session inactive, cancels any executions in `started`/`running` status (emitting `WORKFLOW_CANCELLED`), removes the session from `self.sessions`.
- `async _cleanup_old_sessions()` — evicts sessions whose `active=False` AND age exceeds `session_timeout_minutes`.

**Workflow management:**

- `async register_workflow(workflow_id: str, workflow: Union[Workflow, WorkflowBuilder], session_id: Optional[str] = None, make_shared: bool = False)` — if `workflow` is a builder, it is built first. If `make_shared=True` or `session_id` is None, stores in `self.shared_workflows`. Otherwise fetches the session and calls `session.add_workflow`. Raises `ValueError` if the session is not found.
- `async create_dynamic_workflow(session_id: str, workflow_config: Dict[str, Any], workflow_id: Optional[str] = None) -> str` — gated on `enable_dynamic_workflows`; raises `ValueError` if disabled or session not found. Builds the workflow via `_build_workflow_from_config` and registers it on the session.
- `async _build_workflow_from_config(config: Dict[str, Any]) -> Workflow` — calls `WorkflowBuilder.from_dict(config).build()` and `workflow.validate()`.

**Workflow execution:**

- `async execute(session_id: str, workflow_id: str, inputs: Optional[Dict[str, Any]] = None, config_overrides: Optional[Dict[str, Any]] = None) -> str` — preferred execution entry. Delegates to internal async execution helpers that use `self.runtime`.
- `async _execute_workflow_async(execution_id: str)` — internal
- `async _execute_with_sdk_runtime(...)` — internal, delegates to `self.runtime`
- `_setup_task_event_handlers(...)` — subscribes to task progress events
- `async _emit_execution_event(...)` — emits through `self.event_stream`
- `async get_execution_status(execution_id: str, session_id: str)` — returns current status/progress for the execution
- `async cancel_execution(execution_id: str, session_id: str)` — cancels a running execution

**Node discovery:**

- `async get_available_nodes() -> List[Dict[str, Any]]`
- `async _get_node_schema(node_class) -> Dict[str, Any]`

**Events and stats:**

- `get_stats() -> Dict[str, Any]` — returns counters, uptime, active sessions
- `async subscribe_to_events(...)` / `async unsubscribe_from_events(subscriber_id: str)` — passthrough to `self.event_stream`

**Lifecycle:**

- `close()` — releases the runtime reference: if `_owns_runtime` calls `runtime.close()`, otherwise `runtime.release()`. Sets `self.runtime = None`.

### `DynamicSchemaRegistry` / `NodeSchemaGenerator` (`core/schema.py`)

Exposed from `core/__init__.py`. Used by `APIGateway` for node discovery endpoints.

### `MiddlewareWorkflows` / `WorkflowBasedMiddleware` (`core/workflows.py`)

Helpers that implement some middleware operations as Kailash workflows rather than imperative Python. Re-exported via the top-level `kailash.middleware` package.

## Communication (`src/kailash/middleware/communication/`)

### `EventType` (Enum, `events.py`)

String-valued event types (`value` shown):

- Workflow: `"workflow.created"`, `"workflow.started"`, `"workflow.progress"`, `"workflow.completed"`, `"workflow.failed"`, `"workflow.cancelled"`
- Node: `"node.started"`, `"node.progress"`, `"node.completed"`, `"node.failed"`, `"node.skipped"`
- UI: `"ui.input_required"`, `"ui.approval_required"`, `"ui.choice_required"`, `"ui.confirmation_required"`
- System: `"system.status"`, `"system.error"`, `"system.warning"`
- Data: `"data.updated"`, `"data.validated"`, `"data.error"`

### `EventPriority` (Enum)

`CRITICAL`, `HIGH`, `NORMAL`, `LOW` — string-valued.

### `BaseEvent` / `WorkflowEvent` / `NodeEvent` / `UIEvent`

```python
@dataclass
class BaseEvent:
    id: str
    type: EventType
    timestamp: datetime
    priority: EventPriority = EventPriority.NORMAL
    source: Optional[str] = None
    target: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc)
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]: ...
    def to_json(self) -> str: ...


@dataclass
class WorkflowEvent(BaseEvent):
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    execution_id: Optional[str] = None
    progress_percent: Optional[float] = None
    current_node: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
```

`NodeEvent` adds `workflow_id`, `node_id`, `node_type`, `progress_percent`, `data`, `error` style fields (exact layout in source). `UIEvent` similarly adds interaction-specific fields.

### `EventFilter` (`events.py`)

```python
class EventFilter:
    def __init__(
        self,
        event_types: Optional[List[EventType]] = None,
        session_ids: Optional[List[str]] = None,
        user_ids: Optional[List[str]] = None,
        priorities: Optional[List[EventPriority]] = None,
        sources: Optional[List[str]] = None,
    ):
        ...
```

Used by `EventStream.subscribe(subscriber_id, callback, filter=...)` to filter events per subscriber.

### `EventStream`

```python
class EventStream:
    def __init__(self, enable_batching: bool = True, batch_size: int = 10):
        ...
```

Central event dispatcher. Supports subscribe/unsubscribe with filters, batched emission, and async subscribers. Exposes helpers like `emit_workflow_started(...)`, `emit_workflow_completed(...)`, `emit_node_event(...)`, etc.

### `APIGateway` (`communication/api_gateway.py`)

Pydantic request/response models defined in the same file:

- `SessionCreateRequest` — `user_id: Optional[str] = None`, `metadata: Dict[str, Any] = Field(default_factory=dict)`
- `SessionResponse` — `session_id`, `user_id`, `created_at`, `active: bool = True`
- `WorkflowCreateRequest` — `name`, `description`, `nodes: List[Dict]`, `connections: List[Dict]`, `metadata: Dict`
- `WorkflowExecuteRequest` — `workflow_id`, `inputs: Dict`, `config_overrides: Dict`
- `ExecutionResponse` — `execution_id`, `workflow_id`, `status`, `created_at`, `progress: float = 0.0`
- `NodeSchemaRequest` — `node_types: Optional[List[str]] = None`, `include_examples: bool = False`
- `WebhookRegisterRequest` — `url`, `secret`, `event_types: List[str]`, `headers: Dict[str, str]`

The gateway class:

```python
class APIGateway:
    def __init__(
        self,
        title: str = "Kailash Middleware Gateway",
        description: str = "Enhanced API gateway for agent-frontend communication",
        version: str = "1.0.0",
        cors_origins: Optional[List[str]] = None,
        enable_docs: bool = True,
        max_sessions: int = 1000,
        enable_auth: bool = True,
        auth_manager=None,
        database_url: Optional[str] = None,
    ):
```

**Constructor parameters** (exactly as in source):

- `title: str = "Kailash Middleware Gateway"` — FastAPI app title
- `description: str = "Enhanced API gateway for agent-frontend communication"`
- `version: str = "1.0.0"` — FastAPI app version
- `cors_origins: Optional[List[str]] = None` — passed to `CORSMiddleware(allow_origins=...)`. `None` is coerced to `[]` at use time.
- `enable_docs: bool = True` — toggles `/docs` and `/redoc`. When False, both are set to None on the FastAPI app.
- `max_sessions: int = 1000` — forwarded to the internal `AgentUIMiddleware(max_sessions=max_sessions)` constructed by the gateway.
- `enable_auth: bool = True` — if True and `auth_manager` is None, constructs a default `JWTAuthManager(secret_key="api-gateway-secret", algorithm="HS256", issuer="kailash-gateway", audience="kailash-api")`.
- `auth_manager=None` — dependency injection; if supplied, used directly without constructing a default.
- `database_url: Optional[str] = None` — currently wired into `_init_sdk_nodes(database_url)`; the internal `AgentUIMiddleware` is constructed WITHOUT a database_url (the gateway-level persistence is kept separate).

There are NO `agent_ui` or `realtime` constructor parameters. Both are created internally:

```python
self.agent_ui = AgentUIMiddleware(max_sessions=max_sessions)
self.realtime = RealtimeMiddleware(self.agent_ui)
```

Override after construction via assignment (e.g., `gateway.agent_ui = my_middleware; gateway.realtime = RealtimeMiddleware(my_middleware)`) — see `create_gateway()` helper below.

**State initialized:**

- `self.title`, `self.version`, `self.enable_docs`, `self.enable_auth`
- `self.data_transformer = DataTransformer(name="gateway_transformer", transformations=[])`
- `self.credential_manager = CredentialManagerNode(name="gateway_credentials", credential_name="gateway_secrets", credential_type="custom")`
- `self.agent_ui = AgentUIMiddleware(max_sessions=max_sessions)`
- `self.realtime = RealtimeMiddleware(self.agent_ui)`
- `self.schema_registry = DynamicSchemaRegistry()`
- `self.node_registry = NodeRegistry()`
- `self.auth_manager` (None if `enable_auth=False`, else as described above)
- `self.app = FastAPI(title=..., description=..., version=..., docs_url=..., redoc_url=..., lifespan=lifespan)` — with `CORSMiddleware(allow_origins=cors_origins or [], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])`
- `self.start_time = time.time()`, `self.requests_processed = 0`

**Routes** are registered by `_setup_routes()` which calls `_setup_core_routes()`, `_setup_session_routes()`, `_setup_workflow_routes()` and others. The FastAPI `lifespan` context logs startup and closes all open sessions on shutdown.

### `create_gateway` helper

```python
def create_gateway(
    agent_ui_middleware: Optional[AgentUIMiddleware] = None,
    auth_manager=None,
    **kwargs,
) -> APIGateway:
```

Convenience factory. Constructs `APIGateway(**kwargs)` (forwarding `auth_manager` if supplied). If `agent_ui_middleware` is passed, overrides `gateway.agent_ui` with the caller's instance and rebuilds `gateway.realtime = RealtimeMiddleware(agent_ui_middleware)`.

### `RealtimeMiddleware` (`communication/realtime.py`)

```python
class RealtimeMiddleware:
    def __init__(
        self,
        agent_ui_middleware: AgentUIMiddleware,
        enable_websockets: bool = True,
        enable_sse: bool = True,
        enable_webhooks: bool = True,
        latency_target_ms: int = 200,
    ):
```

Multi-transport real-time communication layer.

**State:**

- `self.agent_ui` — reference to the parent middleware
- `self.enable_websockets`, `self.enable_sse`, `self.enable_webhooks`
- `self.latency_target_ms`
- `self.connection_manager = ConnectionManager() if enable_websockets else None` — manages WebSocket connections
- `self.sse_manager = SSEManager() if enable_sse else None` — manages Server-Sent Events
- `self.webhook_manager = WebhookManager() if enable_webhooks else None` — delivers webhooks
- `self.start_time = time.time()`, `self.events_processed = 0`, `self.latency_samples = []`
- `self._event_subscription_task: Optional[asyncio.Task] = None`

**Methods:**

- `async initialize()` — creates `_subscribe_to_events` background task. Must be awaited after construction.
- `async _subscribe_to_events()` — subscribes to `agent_ui.event_stream` with an async handler that dispatches to transport managers.
- `async _process_event(event)` — routes to WebSocket / SSE / webhook managers based on enabled transports.
- Methods for adding/removing WebSocket connections, SSE clients, webhook registrations.

### Supporting transport classes (also in `realtime.py`)

- `ConnectionManager` — `__init__(self)`, tracks WebSocket connections, handles broadcast.
- `SSEManager` — `__init__(self)`, maintains SSE client queues.
- `WebhookManager` — `__init__(self, max_retries: int = 3, timeout_seconds: int = 10)`.

### `event_bus.py` / `domain_event.py` / `backends/`

Additional event distribution primitives for in-process and distributed event routing. Consumed internally by `EventStream`.

## Auth (`src/kailash/middleware/auth/`)

### Public exports

```python
from .exceptions import (
    AuthenticationError, InvalidTokenError, PermissionDeniedError,
    TokenBlacklistedError, TokenExpiredError,
)
from .jwt_auth import JWTAuthManager
from .models import AuthenticationResult, JWTConfig, TokenPair, TokenPayload, UserClaims
from .utils import generate_key_pair, generate_secret_key, parse_bearer_token

# Optional (loaded if access_control + auth_manager import cleanly)
from .access_control import (
    MiddlewareAccessControlManager, MiddlewareAuthenticationMiddleware,
)
from .auth_manager import AuthLevel, MiddlewareAuthManager
```

### `JWTConfig` (`auth/models.py`)

Dataclass/model holding JWT configuration: secret key, algorithm, RSA keys, issuer, audience, expiry, blacklist flag, etc. Used by `JWTAuthManager`.

### `JWTAuthManager` (`auth/jwt_auth.py`)

```python
class JWTAuthManager:
    def __init__(
        self,
        config: Optional[JWTConfig] = None,
        secret_key: Optional[str] = None,
        algorithm: Optional[str] = None,
        use_rsa: Optional[bool] = None,
        **kwargs,
    ):
```

**Constructor semantics:**

- Starts with `self.config = config or JWTConfig()`.
- Any direct parameters supplied (`secret_key`, `algorithm`, `use_rsa`) override the corresponding `config` fields (`config.secret_key`, `config.algorithm`, `config.use_rsa`). Passing `use_rsa=True` additionally sets `config.algorithm = "RS256"`.
- Additional `**kwargs` are applied via `setattr` to any matching attribute on `self.config`.

**State:**

- `self._private_key: Optional[Any] = None` — RSA private key when use_rsa
- `self._public_key: Optional[Any] = None`
- `self._secret_key: Optional[str] = self.config.secret_key`
- `self._key_id = str(uuid.uuid4())`
- `self._key_generated_at = datetime.now(timezone.utc)`
- `self._blacklisted_tokens: Optional[set] = set() if self.config.enable_blacklist else None`
- `self._refresh_tokens: Dict[str, Dict[str, Any]] = {}`
- `self._failed_attempts: Dict[str, List[datetime]] = {}`
- Calls `_initialize_keys()` at the end of `__init__` which dispatches to RSA key loading/generation or HS256 secret handling based on config.

Supports both HS256 (default) and RSA algorithms, refresh-token management, blacklisting, failed-attempt tracking, and audit logging.

### `MiddlewareAuthManager` (`auth/auth_manager.py`)

SDK-node–based authentication manager. Delegates crypto/auth operations to Kailash security nodes (`CredentialManagerNode`, `RotatingCredentialNode`, `PermissionCheckNode`, `SecurityEventNode`, `AuditLogNode`, `AsyncSQLDatabaseNode`).

```python
class MiddlewareAuthManager:
    def __init__(
        self,
        secret_key: Optional[str] = None,
        token_expiry_hours: int = 24,
        enable_api_keys: bool = True,
        enable_audit: bool = True,
        database_url: Optional[str] = None,
    ):
```

**Constructor parameters** (exactly as in source):

- `secret_key: Optional[str] = None` — used directly for JWT signing (stored in `self.secret_key`).
- `token_expiry_hours: int = 24` — default expiry for access tokens.
- `enable_api_keys: bool = True` — toggles the `RotatingCredentialNode` (`self.api_key_manager`) initialization.
- `enable_audit: bool = True` — toggles the `AuditLogNode` (`self.audit_logger`) initialization.
- `database_url: Optional[str] = None` — if truthy, constructs `self.db_node = AsyncSQLDatabaseNode(name="auth_database", connection_string=database_url)`.

There are NO `enable_rbac` or `jwt_config` parameters. The class uses `CredentialManagerNode` for credential storage and delegates JWT sign/verify to the `jwt` library directly.

**State initialized via `_initialize_security_nodes(secret_key or "", database_url or "")`:**

- `self.secret_key = secret_key` (raw string, not a `JWTConfig`)
- `self.credential_manager = CredentialManagerNode(credential_name="api_credentials", credential_type="api_key", name="jwt_credential_manager")`
- If `enable_api_keys`: `self.api_key_manager = RotatingCredentialNode(name="api_key_rotator")` — note per the source comment, rotation interval/credential name are NOT passed at init; they are passed at execution time.
- `self.permission_checker = PermissionCheckNode(name="middleware_permission_checker")`
- `self.security_logger = SecurityEventNode(name="middleware_security_events")`
- If `enable_audit`: `self.audit_logger = AuditLogNode(name="middleware_audit")`
- `self.token_transformer = DataTransformer(name="token_transformer")`
- If `database_url`: `self.db_node = AsyncSQLDatabaseNode(...)`
- `self.bearer_scheme = HTTPBearer(auto_error=False)` (for FastAPI dependency injection)

**Methods:**

- `async create_access_token(user_id: str, permissions: List[str] | None = None, metadata: Dict[str, Any] | None = None) -> str` — constructs a payload with `user_id`, `permissions`, `metadata`, `exp = now + token_expiry_hours`, `iat = now`; calls `jwt.encode(payload, self.secret_key, algorithm="HS256")`. Raises `HTTPException(500, ...)` on encode failure. Logs via `audit_logger.execute(user_id=..., action="create_token", ...)` if audit is enabled.
- `async verify_token(token: str) -> Dict[str, Any]` — decodes with `jwt.decode(token, self.secret_key, algorithms=["HS256"])`, checks `exp` explicitly, raises `HTTPException(401, ...)` on expiry or decode failure.
- `async create_api_key(...)` — creates via `self.api_key_manager` if enabled
- `async verify_api_key(api_key: str) -> Dict[str, Any]`
- `async check_permission(user_id, resource, action, ...)` — uses `self.permission_checker`
- `get_current_user_dependency(required_permissions: List[str] = None)` — returns a FastAPI dependency function

### `AuthLevel` (Enum)

```python
class AuthLevel(Enum):
    PUBLIC = "public"
    BASIC = "basic"
    STANDARD = "standard"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
```

### `MiddlewareAccessControlManager` / `MiddlewareAuthenticationMiddleware` (`auth/access_control.py`)

Higher-level access control building on top of `MiddlewareAuthManager`. These are conditionally imported by `auth/__init__.py` (wrapped in a `try/except ImportError` to avoid circular dependencies with communication).

### Supporting models and utilities (`auth/models.py`, `auth/utils.py`)

- `AuthenticationResult`, `TokenPair`, `TokenPayload`, `UserClaims` — dataclasses/models returned by auth operations.
- `generate_secret_key()`, `generate_key_pair()`, `parse_bearer_token(header)` — utility helpers.
- Exception hierarchy (`auth/exceptions.py`): `AuthenticationError`, `InvalidTokenError`, `TokenExpiredError`, `TokenBlacklistedError`, `PermissionDeniedError`.

## Database (`src/kailash/middleware/database/`)

### Public exports

```python
from .migrations import MiddlewareMigrationRunner
from .models import (
    AccessLogModel, Base, CustomNodeModel, NodePermissionModel,
    UserGroupMemberModel, UserGroupModel, UserPreferencesModel,
    WorkflowExecutionModel, WorkflowModel, WorkflowPermissionModel,
    WorkflowTemplateModel, WorkflowVersionModel,
)
from .repositories import (
    MiddlewareExecutionRepository, MiddlewarePermissionRepository,
    MiddlewareUserRepository, MiddlewareWorkflowRepository,
)
from .session_manager import MiddlewareDatabaseManager, get_middleware_db_session
```

### Model mixins (`database/base.py`)

- `TenantMixin` — adds tenant isolation fields
- `AuditMixin` — created_at, updated_at, created_by, updated_by
- `SoftDeleteMixin` — deleted_at, is_deleted
- `VersionMixin` — optimistic locking version
- `SecurityMixin` — encryption/classification markers
- `ComplianceMixin` — compliance metadata
- `BaseMixin(TenantMixin, AuditMixin)` — shortcut
- `EnterpriseBaseMixin` — combines several mixins

### SQLAlchemy models (`database/models.py`)

`Base` (declarative base) and the following entities: `WorkflowModel`, `WorkflowVersionModel`, `CustomNodeModel`, `WorkflowExecutionModel`, `UserPreferencesModel`, `WorkflowTemplateModel`, `WorkflowPermissionModel`, `NodePermissionModel`, `AccessLogModel`, `UserGroupModel`, `UserGroupMemberModel`. Used by the repository classes.

### `base_models.py` / `enums.py` / `migrations.py`

Supporting modules. `MiddlewareMigrationRunner` manages schema creation and upgrades against the configured database. Enums cover repository enumerations (permission types, execution status).

### Repositories (`database/repositories.py`)

- `MiddlewareWorkflowRepository(database_url)` — CRUD over `WorkflowModel` / `WorkflowVersionModel` / `WorkflowTemplateModel` using `AsyncSQLDatabaseNode`.
- `MiddlewareExecutionRepository(database_url)` — tracks `WorkflowExecutionModel` rows.
- `MiddlewareUserRepository(database_url)` — user/group CRUD.
- `MiddlewarePermissionRepository(database_url)` — workflow/node permissions, access log.

All repositories use the shared `MiddlewareDatabaseManager` for connection and transaction management.

### `MiddlewareDatabaseManager` / `get_middleware_db_session` (`database/session_manager.py`)

Connection pool and async session management for the middleware repositories. `get_middleware_db_session()` is a FastAPI-style dependency that yields an async session.

## Gateway (`src/kailash/middleware/gateway/`)

Durable-execution gateway with checkpoint/resume semantics. Key modules:

- `durable_gateway.py` — `DurableGateway` orchestrator
- `durable_request.py` — `DurableRequest` state machine
- `checkpoint_manager.py` — checkpoint lifecycle
- `deduplicator.py` — idempotency key deduplication
- `event_store.py`, `event_store_backend.py`, `event_store_sqlite.py` — event sourcing persistence
- `storage_backends.py` — pluggable storage adapters (memory, SQLite, etc.)

These classes support long-running workflow execution with resumability across process restarts: requests are checkpointed at each major transition, stored in the event store, and can be resumed from the last committed checkpoint.

## MCP (`src/kailash/middleware/mcp/`)

### Public exports

```python
from .client_integration import (
    MCPClientConfig, MCPServerConnection, MiddlewareMCPClient,
)
from .enhanced_server import (
    MCPResourceNode, MCPServerConfig, MCPToolNode, MiddlewareMCPServer,
)
```

### `MCPServerConfig` (`mcp/enhanced_server.py`)

```python
class MCPServerConfig:
    def __init__(self):
        ...
```

Plain configuration container. Holds server name, transport type, caching parameters, etc.

### `MCPToolNode` (`mcp/enhanced_server.py`)

```python
class MCPToolNode(Node):
    def __init__(
        self,
        name: str,
        ...
    ):
```

Adapter that exposes a Kailash node as an MCP tool. Inherits from `Node` so it can be added to workflows like any other node. Used by `MiddlewareMCPServer` to register tools discovered from the node registry.

### `MCPResourceNode` (`mcp/enhanced_server.py`)

```python
class MCPResourceNode(Node):
    def __init__(
        self,
        name: str,
        ...
    ):
```

Exposes a Kailash data source as an MCP resource (read-only content endpoint).

### `MiddlewareMCPServer` (`mcp/enhanced_server.py`)

```python
class MiddlewareMCPServer:
    def __init__(
        self,
        config: Optional[MCPServerConfig] = None,
        event_stream: Optional[EventStream] = None,
        agent_ui: Optional[AgentUIMiddleware] = None,
        runtime: Optional[LocalRuntime] = None,
    ):
```

**State:**

- `self.config = config or MCPServerConfig()`
- `self.event_stream` — optional shared event stream
- `self.agent_ui` — optional link back to the parent middleware
- `self.runtime` — acquired from the runtime pool if provided, else `LocalRuntime()` with `_owns_runtime=True`
- `self.workflows: Dict[str, WorkflowBuilder] = {}` — workflows registered as MCP tools
- `self.tools: Dict[str, MCPToolNode] = {}`
- `self.resources: Dict[str, MCPResourceNode] = {}`
- `self.prompts: Dict[str, Dict[str, Any]] = {}`
- `self.server_id = str(uuid.uuid4())`
- `self.started_at = None`
- `self.client_connections: Dict[str, Dict[str, Any]] = {}`
- `self.base_server` — a Kailash `MCPServer` instance if the Kailash MCP module is available, else None.
- Calls `_create_management_workflows()` in `__init__` to build internal workflows used for tool registration, resource access, etc.

### `MCPClientConfig` / `MCPServerConnection` / `MiddlewareMCPClient` (`mcp/client_integration.py`)

Client-side MCP integration. `MiddlewareMCPClient` manages connections to multiple MCP servers, with config, retry, and connection-state tracking.

## Design Notes

- `AgentUIMiddleware.__init__` has `enable_dynamic_workflows` as the FIRST positional parameter, not `enable_persistence`. Callers that rely on positional args MUST match the declared order.
- `AgentUIMiddleware`'s `enable_persistence` is conceptually "requested persistence" — the effective flag is `enable_persistence and database_url is not None`. Passing `enable_persistence=True` without a `database_url` silently disables persistence.
- `APIGateway` always constructs its own `AgentUIMiddleware` and `RealtimeMiddleware`. To inject a pre-existing middleware, either assign after construction or use `create_gateway(agent_ui_middleware=...)`.
- `MiddlewareAuthManager` uses a raw `secret_key: str` and the `jwt` library directly. For RSA/RS256 or refresh tokens, use `JWTAuthManager` instead — it owns the full `JWTConfig` contract.
- There is no top-level `event_streaming` toggle — events are always on in `AgentUIMiddleware`. To disable event delivery, subscribe with a filter that matches nothing, or ignore the `event_stream`.
- Durable execution lives in `middleware/gateway/`, not in `core/`. For long-running workflows that must survive process restarts, use `DurableGateway` rather than calling `AgentUIMiddleware.execute` directly.
