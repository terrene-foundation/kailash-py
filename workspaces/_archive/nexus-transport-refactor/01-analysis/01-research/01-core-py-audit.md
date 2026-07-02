# Core.py Audit — FastAPI Coupling Map

## File: `packages/kailash-nexus/src/nexus/core.py`

**Verified line count**: 2,436 lines (exact match with brief claim).

## Structure Overview

The `Nexus` class spans lines 103-2,418 (~2,315 lines of class body). A legacy `create_nexus()` function occupies lines 2,421-2,436.

### Major Sections

| Line Range | Section                                                          | FastAPI Coupled?                                           |
| ---------- | ---------------------------------------------------------------- | ---------------------------------------------------------- |
| 103-166    | `__init__()` signature and docstring                             | No (config only)                                           |
| 166-305    | `__init__()` body — config, state, presets, runtime              | Indirect (calls `_initialize_gateway`)                     |
| 307-361    | `_initialize_gateway()`                                          | **CRITICAL** — creates FastAPI app via `create_gateway()`  |
| 363-386    | `_initialize_revolutionary_capabilities()`                       | No                                                         |
| 388-443    | `_initialize_mcp_server()`                                       | No (MCP-specific)                                          |
| 444-568    | `_register_default_mcp_resources()`                              | No                                                         |
| 570-594    | `_create_mock_mcp_server()`                                      | No                                                         |
| 596-649    | `_create_sdk_mcp_server()`                                       | No                                                         |
| 651-681    | `_setup_mcp_channel()`                                           | No                                                         |
| 683-718    | `_register_workflow_as_mcp_tool()`                               | No                                                         |
| 720-752    | `_get_api_keys()`, `_get_enabled_transports()`                   | No                                                         |
| 754-820    | `register()`                                                     | Indirect (`self._gateway.register_workflow`)               |
| 824-975    | `endpoint()` decorator                                           | **CRITICAL** — raw FastAPI route registration              |
| 981-1049   | `add_middleware()`                                               | **HIGH** — `self._gateway.app.add_middleware()`            |
| 1060-1161  | `include_router()` + `_has_route_conflict()`                     | **CRITICAL** — `from fastapi import APIRouter`             |
| 1172-1295  | `add_plugin()` + lifecycle hooks                                 | No (plugin API is clean)                                   |
| 1301-1398  | CORS config helpers                                              | No (pure config)                                           |
| 1400-1427  | `_apply_cors_middleware()`                                       | **HIGH** — `from starlette.middleware.cors`                |
| 1429-1505  | `configure_cors()`, `cors_config`, `is_origin_allowed()`         | No                                                         |
| 1507-1550  | Preset system properties                                         | No                                                         |
| 1556-1653  | Handler API (`handler()`, `register_handler()`)                  | No                                                         |
| 1655-1744  | `_validate_workflow_sandbox()`                                   | No                                                         |
| 1746-1809  | `_execute_workflow()`                                            | **MEDIUM** — `from fastapi import HTTPException`           |
| 1811-1818  | `_run_gateway()`                                                 | **HIGH** — `self._gateway.run()`                           |
| 1821-1860  | `_run_mcp_server()`                                              | No (MCP-specific)                                          |
| 1862-1911  | `start()`                                                        | **CRITICAL** — `self._gateway.run()` as main blocking call |
| 1913-1927  | `_log_startup_success()`                                         | No                                                         |
| 1929-1956  | `_initialize_runtime_capabilities()`                             | No (v1.1 stubs)                                            |
| 1958-2007  | Multi-channel orchestration + revolutionary logging              | No                                                         |
| 2009-2046  | `close()`, `__del__`, `__enter__`, `__exit__`                    | No                                                         |
| 2048-2112  | `stop()`                                                         | Indirect (MCP cleanup only)                                |
| 2114-2124  | `_auto_discover_workflows()`                                     | No                                                         |
| 2126-2175  | `health_check()`, `enable_auth()`, `enable_monitoring()`         | Indirect (`self._gateway.*`)                               |
| 2176-2182  | `use_plugin()`                                                   | No                                                         |
| 2186-2417  | Revolutionary capabilities (sessions, events, metrics, channels) | No                                                         |

## FastAPI Coupling Points — Verified Line Ranges

### CRITICAL (B0b Resolution Required)

| Brief Claim | Actual Lines  | Description                                                      | Verified?          |
| ----------- | ------------- | ---------------------------------------------------------------- | ------------------ |
| 307-361     | **307-361**   | `_initialize_gateway()` — `create_gateway()` → FastAPI app       | YES, exact match   |
| 330-341     | **329-341**   | CORS via `starlette.middleware.cors.CORSMiddleware`              | YES, off by 1 line |
| 824-975     | **824-975**   | `endpoint()` decorator — FastAPI route registration              | YES, exact match   |
| 889         | **889**       | `from fastapi import HTTPException, Request` inside rate limiter | YES, exact match   |
| 943-964     | **942-964**   | Route registration via `self._gateway.app`                       | YES, off by 1      |
| 1040-1041   | **1040-1041** | `add_middleware()` delegates to `self._gateway.app`              | YES, exact match   |
| 1102-1108   | **1102-1108** | `include_router()` validates against `_APIRouter`                | YES, exact match   |
| 1400-1425   | **1400-1427** | `_apply_cors_middleware()`                                       | YES, +2 lines      |
| 1763-1771   | **1764-1771** | `_execute_workflow()` raises `fastapi.HTTPException`             | YES, off by 1      |
| 1811-1818   | **1811-1818** | `_run_gateway()` calls `self._gateway.run()`                     | YES, exact match   |
| 1899-1903   | **1899-1903** | `start()` calls `self._gateway.run()`                            | YES, exact match   |

**Verdict**: All 11 coupling points verified. Line ranges are accurate within 1-2 lines.

### Additional Coupling Points NOT in Brief

1. **Lines 347-349**: Queued middleware applied via `self._gateway.app.add_middleware()` — covered by the 307-361 range but worth noting for B0a
2. **Lines 352-357**: Queued routers applied via `self._gateway.app.include_router()` — same
3. **Line 779-785**: `self._gateway.register_workflow()` — workflow registration also goes through gateway
4. **Lines 1134-1135**: `self._gateway.app.include_router()` in the router apply path — not in brief table but within `include_router()` method
5. **Lines 1156-1159**: `self._gateway.app.routes` for conflict detection — also within `include_router()` scope
6. **Line 2062**: `if self._gateway:` check in `stop()` — minor
7. **Lines 2145-2150**: `self._gateway.health_check()` in `health_check()` — feature delegation
8. **Lines 2158-2174**: `self._gateway.enable_auth()`, `self._gateway.enable_monitoring()` — progressive enhancement delegation

## Handler Registration Flow

1. User calls `app.register(name, workflow)` or `@app.handler(name)`
2. `register()` stores workflow in `self._workflows[name]` (line 773)
3. Calls `self._gateway.register_workflow(name, workflow)` for HTTP exposure (line 781)
4. Calls `self._mcp_channel.register_workflow()` or `_register_workflow_as_mcp_tool()` for MCP (lines 788-800)
5. `@app.handler()` builds a workflow via `make_handler_workflow()` then delegates to `register()`

The `_handler_registry` dict (line 227) stores handler metadata for introspection — separate from workflow storage.

## Middleware Setup Flow

1. `__init__()` calls `_initialize_gateway()` (line 275)
2. `_initialize_gateway()` calls `create_gateway()` from `kailash.servers.gateway` (line 316)
3. CORS middleware applied directly to `self._gateway.app` (line 332)
4. Queued middleware and routers drained (lines 347-357)
5. Subsequent `add_middleware()` calls go directly to `self._gateway.app.add_middleware()` (line 1041)

## Gateway Management

The `_gateway` is created by the Core SDK's `create_gateway()` function from `kailash.servers.gateway`. It wraps a FastAPI application with enterprise features (durability, resource management, async execution, health checks). The `.app` property exposes the raw FastAPI `Application` instance, and `.run()` starts uvicorn.

## Key Internal State

```python
self._workflows: Dict[str, Workflow] = {}           # Workflow storage
self._handler_registry: Dict[str, Dict[str, Any]] = {}  # Handler metadata
self._gateway = None                                 # FastAPI wrapper (create_gateway())
self._middleware_queue: List[Tuple[type, Dict]] = []  # Pre-gateway middleware
self._middleware_stack: List[MiddlewareInfo] = []     # All registered middleware
self._router_queue: List[Tuple[Any, Dict]] = []      # Pre-gateway routers
self._routers: List[RouterInfo] = []                  # All included routers
self._plugins: Dict[str, Any] = {}                    # Installed plugins
self._startup_hooks: List[Callable] = []              # Plugin startup hooks
self._shutdown_hooks: List[Callable] = []             # Plugin shutdown hooks
self.runtime = AsyncLocalRuntime()                    # Shared runtime
self._mcp_server = None                               # MCP server (various types)
self._mcp_channel = None                              # MCP channel (SDK channel)
```

## Risk: Dead Code

Lines 1929-2007 contain substantial dead/deferred code:

- `_initialize_runtime_capabilities()` — marked "currently unused, reserved for v1.1"
- `_activate_multi_channel_orchestration()` — appears unused
- `_log_revolutionary_startup()` — duplicates `_log_startup_success()`

This code should be removed during B0a to reduce noise. The brief does not mention this cleanup.
