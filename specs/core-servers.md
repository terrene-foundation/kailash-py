# Kailash Core SDK — Server Variants & Gateway

Version: 2.8.5
Status: Authoritative domain truth document
Parent domain: Core SDK (split from `core-sdk.md` per specs-authority Rule 8)
Scope: WorkflowServer, DurableWorkflowServer, EnterpriseWorkflowServer, server hierarchy, gateway factory, deprecated APIs

Sibling files: `core-nodes.md` (node architecture), `core-workflows.md` (builder + workflow + validation), `core-runtime.md` (execution + cycles + resilience + errors)

---

## 9. Server Variants

All servers are built on FastAPI and require the `kailash` package (which includes server dependencies).

### 9.1 WorkflowServer (Basic)

**Module**: `kailash.servers.workflow_server`
**Import**: `from kailash import WorkflowServer` (lazy import)

```python
class WorkflowServer:
    def __init__(
        self,
        title: str = "Kailash Workflow Server",
        description: str = "Multi-workflow hosting server",
        version: str = "1.0.0",
        max_workers: int = 10,
        cors_origins: list[str] | None = None,
        runtime: Any = None,
        **kwargs,
    )
```

**Features**:

- Multi-workflow hosting with dynamic registration
- REST API endpoints for workflow execution
- WebSocket support for real-time updates
- MCP server integration
- Health monitoring
- CORS support
- Rate limiting (100 requests per workflow per 60-second window)
- Coordinated shutdown via `ShutdownCoordinator`
- Signal/query support (when `runtime` is provided)

**Key methods**:

- `register_workflow(name, workflow)` -- Register a workflow for hosting
- `run(port=8000)` -- Start the server
- `app` -- The underlying FastAPI application instance

### 9.2 DurableWorkflowServer

**Module**: `kailash.servers.durable_workflow_server`
**Import**: `from kailash import DurableWorkflowServer` (lazy import)
**Extends**: `WorkflowServer`

```python
class DurableWorkflowServer(WorkflowServer):
    def __init__(
        self,
        title: str = "Kailash Durable Workflow Server",
        enable_durability: bool = True,
        checkpoint_manager: CheckpointManager | None = None,
        deduplicator: RequestDeduplicator | None = None,
        event_store: EventStore | None = None,
        durability_opt_in: bool = True,
        **kwargs,
    )
```

**Additional features** over WorkflowServer:

- Request durability and checkpointing (via `CheckpointManager`)
- Automatic request deduplication (via `RequestDeduplicator`)
- Event-sourced audit trail (via `EventStore`)
- Long-running request support
- Recovery from latest checkpoint (via `DurableRequest`)
- Opt-in durability per endpoint (`durability_opt_in=True`)

### 9.3 EnterpriseWorkflowServer

**Module**: `kailash.servers.enterprise_workflow_server`
**Import**: `from kailash import EnterpriseWorkflowServer` (lazy import)
**Extends**: `DurableWorkflowServer`

The recommended server for production deployments.

**Additional features** over DurableWorkflowServer:

- Resource registry integration (`ResourceRegistry`)
- Secret management (`SecretManager`)
- Async workflow execution (via `AsyncLocalRuntime`)
- Prometheus-compatible `/metrics` endpoint
- Comprehensive health checks
- Resource resolution in workflow inputs (`ResourceReference`)

### 9.4 Server Hierarchy

```
WorkflowServer
  +-- DurableWorkflowServer
       +-- EnterpriseWorkflowServer
```

Each level adds capabilities while maintaining backward compatibility with the level below.

---

## 10. Gateway Factory

**Module**: `kailash.servers.gateway`

### 10.1 create_gateway

```python
def create_gateway(
    title: str = "Kailash Enterprise Gateway",
    description: str = "Production-ready workflow server with enterprise features",
    version: str = "1.0.0",
    server_type: str = "enterprise",
    max_workers: int = 20,
    cors_origins: list[str] | None = None,
    enable_durability: bool = True,
    enable_resource_management: bool = True,
    enable_async_execution: bool = True,
    enable_health_checks: bool = True,
    resource_registry: ResourceRegistry | None = None,
    secret_manager: SecretManager | None = None,
    **kwargs,
) -> WorkflowServer
```

**`server_type` options**:

- `"enterprise"` (default) -- Creates `EnterpriseWorkflowServer` with all enterprise features
- `"durable"` -- Creates `DurableWorkflowServer` without full enterprise features
- `"basic"` -- Creates `WorkflowServer` for development/testing

**Raises**: `ValueError` if `server_type` is unknown.

### 10.2 Convenience Aliases

```python
def create_enterprise_gateway(**kwargs) -> EnterpriseWorkflowServer
def create_durable_gateway(**kwargs) -> DurableWorkflowServer
def create_basic_gateway(**kwargs) -> WorkflowServer
```

Each calls `create_gateway()` with the appropriate `server_type` and asserts the return type.

---

## 11. Deprecated and Removed APIs

### 11.1 Deprecated

- `WorkflowGraph` -- Deprecated alias for `Workflow`. Emits `DeprecationWarning` on access. Will be removed in v3.0.0.
- `AgentUIMiddleware`, `APIGateway`, `RealtimeMiddleware` -- No longer exported from top level. Must import from `kailash.middleware`.
- `LocalRuntime.execute()` without context manager -- Emits `DeprecationWarning`. Will become an error in v0.12.0.

### 11.2 Removed in v1.0.0

- Legacy fluent API: `add_node("node_id", NodeClass, ...)` -- Raises `WorkflowValidationError` with migration guidance
- Direct `cycle=True` in `Workflow.connect()` from external code -- Raises `WorkflowValidationError` directing to CycleBuilder API

---

## 12. Enterprise Server Usage Pattern

```python
from kailash import create_gateway

gateway = create_gateway(
    title="My Application",
    cors_origins=["http://localhost:3000"],
    max_workers=50,
)
gateway.register_workflow("pipeline", workflow.build())
gateway.run(port=8000)
```
