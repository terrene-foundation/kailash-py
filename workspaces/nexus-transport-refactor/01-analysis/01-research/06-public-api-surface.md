# Public API Surface

## Goal: Document the complete current public API that must remain unchanged

Source: `packages/kailash-nexus/src/nexus/__init__.py` + `core.py` class methods.

## Exported from `__init__.py`

```python
__all__ = [
    "Nexus", "create_nexus",                         # Core
    "NexusEngine", "Preset", "EnterpriseMiddlewareConfig",  # Engine
    "MiddlewareInfo", "RouterInfo", "NexusPluginProtocol",  # Types
    "NexusConfig", "PresetConfig", "PRESETS", "get_preset", "apply_preset",  # Presets
    "ProbeManager", "ProbeState", "ProbeResponse",    # Probes
    "OpenApiGenerator", "OpenApiInfo",                 # OpenAPI
]
```

## Nexus Class — Public Methods and Properties

### Construction

- `Nexus(api_port, mcp_port, enable_auth, enable_monitoring, rate_limit, auto_discovery, enable_http_transport, enable_sse_transport, enable_discovery, rate_limit_config, enable_durability, preset, cors_origins, cors_allow_methods, cors_allow_headers, cors_allow_credentials, cors_expose_headers, cors_max_age, runtime)` — 18 constructor parameters

### Workflow Registration

- `app.register(name: str, workflow: Workflow)` — register workflow for all channels
- `app.register_handler(name, handler_func, description, tags, input_mapping)` — register function as handler
- `@app.handler(name, description, tags)` — decorator version of `register_handler`

### HTTP-Specific (Must Remain, Delegate to HTTPTransport in B0b)

- `@app.endpoint(path, methods, rate_limit, **fastapi_kwargs)` — custom REST endpoint
- `app.add_middleware(middleware_class, **kwargs) -> Nexus` — Starlette middleware
- `app.include_router(router, prefix, tags, dependencies, **kwargs) -> Nexus` — FastAPI router
- `app.middleware` (property) — list of registered middleware
- `app.routers` (property) — list of included routers

### Plugin System

- `app.add_plugin(plugin) -> Nexus` — install NexusPluginProtocol
- `app.use_plugin(plugin_name: str) -> Nexus` — load by name from registry
- `app.plugins` (property) — dict of installed plugins

### CORS Configuration

- `app.configure_cors(allow_origins, allow_methods, allow_headers, allow_credentials, expose_headers, max_age) -> Nexus`
- `app.cors_config` (property) — current CORS config
- `app.is_origin_allowed(origin: str) -> bool`

### Preset System

- `app.active_preset` (property) — name or None
- `app.preset_config` (property) — config object or None
- `app.describe_preset() -> Dict`

### Lifecycle

- `app.start()` — blocking server start
- `app.stop()` — graceful shutdown
- `app.close()` — release resources
- Context manager: `with Nexus() as app: ...`

### Health & Monitoring

- `app.health_check() -> Dict`
- `app.get_performance_metrics() -> Dict`
- `app.get_channel_status() -> Dict`

### Session Management

- `app.create_session(session_id, channel) -> str`
- `app.sync_session(session_id, channel) -> Dict`

### Events (v1.0 — Log Only)

- `app.broadcast_event(event_type, data, session_id) -> Dict`
- `app.get_events(session_id, event_type, limit) -> List[Dict]`

### Progressive Enhancement

- `app.enable_auth() -> Nexus`
- `app.enable_monitoring() -> Nexus`

### Internal (Accessed by Plugins)

- `app._gateway` — used by AuthPlugin (plugins.py line 91)
- `app.runtime` — shared AsyncLocalRuntime
- `app._workflows` — workflow dict (accessed by MCP resource handlers)
- `app._handler_registry` — handler metadata dict

## New APIs (Additive, from Architecture)

These are NEW methods that B0a/B0b/Phase 1 will add:

- `@app.on_event(event_type)` — event handler decorator (Phase 1, B2)
- `@app.scheduled(interval)` — scheduled handler decorator (Phase 1, B1)
- `app.emit(event_type, data)` — publish event (Phase 1, B2)
- `app.run_in_background(coro)` — one-shot background task (Phase 1, B9)
- `app.integrate_dataflow(db)` — DataFlow event bridge (Phase 2, B7)
- `app.fastapi_app` (property) — public access to FastAPI app (B0b, replaces `_gateway.app`)

## Contract: What Must Not Break

Every method listed in the "Nexus Class — Public Methods and Properties" section above must continue to work identically after both B0a and B0b. The critical ones:

1. `app.register()` + `@app.handler()` — handlers available on all channels
2. `@app.endpoint()` — custom HTTP routes work as before
3. `app.add_middleware()` — Starlette middleware applies correctly
4. `app.include_router()` — FastAPI routers work as before
5. `app.add_plugin()` — plugins install correctly
6. `app.start()` — server starts and serves HTTP + MCP
7. `app.health_check()` — returns health status
8. `Nexus(preset="saas")` — presets work as before
9. `NexusEngine.builder().preset(Preset.ENTERPRISE).build()` — engine builder works

## Test Coverage for Public API

Existing test files and approximate coverage:

| Test File                          | Lines | Covers                                                                   |
| ---------------------------------- | ----- | ------------------------------------------------------------------------ |
| `test_core_coverage.py`            | 508   | Core Nexus methods: register, handler, middleware, router, CORS, presets |
| `test_nexus_core_revolutionary.py` | 403   | Sessions, events, channels, performance metrics                          |
| `test_handler_registration.py`     | 357   | Handler registration, validation, MCP tool registration                  |
| `test_plugins.py`                  | 265   | Plugin system: add_plugin, lifecycle hooks, validation                   |

Total: ~1,533 lines of test code covering the public API. This is moderate coverage — sufficient for regression detection during B0a (pure refactor), but gaps exist in integration scenarios (e.g., middleware + handler + MCP interaction).
