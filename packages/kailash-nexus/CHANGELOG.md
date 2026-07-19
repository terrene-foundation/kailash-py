# Nexus Changelog

## [2.14.0] — 2026-07-20 — PKCE + id_token nonce across the SSO provider suite (#1834)

### Added (Security)

- **PKCE + id_token nonce enforcement across the SSO provider suite, with
  state-store persistence of `code_verifier`/`nonce` (#1834).**
  `initiate_sso_login` now stores the per-flow PKCE `code_verifier` and OIDC
  `nonce` alongside the CSRF state token; `complete_sso_login` reads them back
  from the state store to complete the token exchange (`code_verifier`) and
  verify the returned `id_token`'s `nonce` claim against JWKS-verified claims
  (fail-closed on mismatch).
  **Migration (BREAKING for custom `SSOStateStore` implementers):**
  `SSOStateStore.store()` gained keyword-only parameters `code_verifier` and
  `nonce`; `initiate_sso_login` now calls
  `store.store(state, code_verifier=..., nonce=...)`. A custom store
  implementing the old `def store(self, state)` signature will raise
  `TypeError` at login — add `*, code_verifier=None, nonce=None` to your
  `store()` signature. The `validate_and_consume` return-shape change is
  backward-tolerant: a legacy store still returning a bare `bool` is treated
  as carrying no PKCE verifier/nonce (never a silent downgrade of a flow that
  did mint them), while a dict-returning store's stored values are used.

## [2.13.0] — 2026-07-19 — `WebhookTransport.receive()` fails closed on missing secret (#1836)

### Fixed (Security)

- **`WebhookTransport.receive()` now fails closed when no signing secret is
  configured (#1836).** `receive()` guarded signature verification with
  `if self._secret is not None`, so a deployment with no webhook signing
  secret SKIPPED verification entirely and silently accepted any forged
  inbound webhook event. #1814 (2.12.1) hardened `verify_signature` /
  `verify_signature_for_request` to fail closed but left this `receive()`
  path as an intentional unsigned-mode contract; this closes it.
  **Behavior change:** with no secret configured, `receive()` now raises a
  typed `ValueError` by default. Deployments that intentionally run
  unsigned webhooks (or verify signatures at an edge proxy/gateway) must
  pass `allow_unsigned=True` to `WebhookTransport(...)` to opt back into the
  prior unsigned-accept behavior.

## [2.12.1] — 2026-07-19 — Webhook signature verification fails closed (#1814)

### Fixed (Security)

- **`WebhookTransport.verify_signature` / `verify_signature_for_request` now
  fail closed when no signing secret is configured (#1814).** Previously,
  reaching either verification method with a signature but no secret
  configured returned `True` — accepting ANY signature as valid, including
  a forged or absent one. Both methods now raise
  `ValueError("Cannot verify signature: no secret configured")` instead,
  matching the existing fail-closed behavior of `compute_signature`.
  **Behavior change:** any
  caller relying on the prior fail-open default (an unconfigured secret
  silently accepting all webhooks) now gets a typed `ValueError` at
  verification time — configure a signing secret, or catch the error to
  reject the request explicitly.

## [2.12.0] — 2026-07-13 — HTTP metrics label bounding + core-gateway route coverage (#1708)

Part of the coordinated 5-package #1708 observability release. Requires
`kailash>=2.50.0` (the unified `/metrics` exposition this fix reaches).

### Fixed

- **HTTP request-duration histogram now covers mounted core-gateway routes
  (#1708 W5).** `RequestMetricsMiddleware` previously matched routes only
  against Nexus's own registered handler table; requests served through a
  mounted Core SDK gateway sub-app fell through to the `__unmatched__`
  cardinality-safety sentinel instead of their real route template. The
  middleware now resolves the matched template for mounted-gateway routes as
  well, so `nexus_http_request_duration_seconds` reports real per-route
  latency for the full request surface, not just Nexus-native routes.
- **HTTP `method` label bounded to a fixed allowlist (#1708 redteam).** The
  `method` label on `nexus_http_requests_total` /
  `nexus_http_request_duration_seconds` previously echoed the raw HTTP method
  string from the request; a malformed or attacker-supplied method could grow
  label cardinality without bound. The label is now bounded to the standard
  HTTP method allowlist, with a fixed `_other` bucket for anything else.

## [2.11.0] — 2026-06-17 — Per-request HTTP metrics middleware (#1336)

### Added

- **Per-request HTTP metrics middleware (#1336).** `RequestMetricsMiddleware` (module `nexus.middleware.request_metrics`) emits `nexus_http_requests_total` (Counter) + `nexus_http_request_duration_seconds` (Histogram) — labelled by `method` / `route` (matched route template) / `status` — for every HTTP request, on the existing `/metrics` Prometheus endpoint. Opt-in via `NexusConfig.metrics_enabled` (default False because `prometheus_client` is an optional dep); auto-wired LAST (outermost, so it measures total request latency including all other middleware) in the `standard`, `saas`, and `enterprise` preset chains. The route label is the matched TEMPLATE (`/users/{id}`), never the concrete path, with an `__unmatched__` sentinel for unmatched traffic — bounding Prometheus label cardinality against path-scanning DoS. Closes the last gateway HTTP-middleware-parity gap with the Rust engine. The middleware is a pure-ASGI implementation (not Starlette `BaseHTTPMiddleware`) and is a cheap pass-through when `prometheus_client` is absent.

## [2.10.0] — 2026-06-17 — Preset auto-wiring: rate-limit + CSP passthrough (#1336)

### Added

- **Rate-limit preset auto-wiring (#1336, parity #1345).** The `standard`, `saas`, and `enterprise` presets now auto-attach the built `RateLimitMiddleware` (token-bucket + 429 body + `X-RateLimit-*` / `Retry-After` headers) using a `RateLimitConfig` derived from `NexusConfig.rate_limit` (per-minute limit) and `NexusConfig.rate_limit_config` (a dict of further `RateLimitConfig` fields — `burst_size`, `backend`, `route_limits`, …). Previously the preset factory was a placeholder that logged "not yet implemented (coming in WS02)" and attached nothing; the rate limiter had to be wired manually via `add_middleware`. Setting `rate_limit=None` still omits the middleware.
- **Consumer CSP + security-header passthrough (#1336, parity #1348).** `NexusConfig` gains `csp: Optional[str]` (a custom Content-Security-Policy string) and `security_header_overrides: Optional[Dict[str, Any]]` (per-field overrides — `frame_options`, `hsts_*`, `referrer_policy`, …), both threaded into the `SecurityHeadersConfig` the security-headers preset constructs. Previously the preset hardcoded the config and ignored consumer settings; a custom CSP required an explicit `add_middleware(SecurityHeadersMiddleware, config=...)` call. Defaults are unchanged when neither field is set.

### Removed

- **Dead `_error_handler_middleware_factory` preset placeholder (#1336).** Removed the WS02 placeholder factory (it always returned `None`). The exception → canonical-error-envelope contract ships via the HTTP transport's `NexusError` handler (`transports/http.py::_install_exception_handlers`, installed at transport startup), not a preset middleware — so the placeholder was dead. No behavior change (it attached nothing).

## [2.9.1] — 2026-06-12 — `Nexus.close()` cascade-closes internal AsyncLocalRuntimes (#1285)

### Fixed

- **`Nexus.close()` now releases every internal `AsyncLocalRuntime` (#1285).** Previously every Nexus app/test emitted `ResourceWarning: Unclosed AsyncLocalRuntime (ref_count=1)` at GC even when `close()` was called, because three runtime references were never released on the synchronous teardown path: (1) the HTTP gateway (`EnterpriseWorkflowServer`) acquires `Nexus.runtime` at construction and was never released; (2) each registered workflow's `WorkflowAPI` owns its own runtime, never tracked/closed (the Core SDK half, fixed in kailash 2.29.4); (3) the MCP/WebSocket transports lazily acquire a `_shared_runtime` on tool invocation and released it only in async `stop()`. `Nexus.close()` now closes the gateway (cascading to every per-workflow runtime) and iterates `self._transports` to release each `_shared_runtime`; the base `Transport` gains a no-op `close()`, and `MCPTransport`/`WebSocketTransport` override it with their async `stop()` delegating to it. Verified clean on every teardown path (explicit `close()`, context-manager `__exit__`, `__del__`/GC, double-close). Requires `kailash>=2.28.4` (the Core SDK `WorkflowServer`/`WorkflowAPIGateway` half ships in kailash 2.29.4).

## [2.9.0] — 2026-06-01 — WebSocket pre-upgrade handshake rejection + subprotocol echo + typed-status gateway (#1216, #1217, #1218)

Three deferred follow-ups of the #1174 FastAPI-parity work. Requires `kailash>=2.28.4` (the #1218 typed-status gateway fix lives in the Core SDK `WorkflowAPI`).

### Added

- **WebSocket pre-upgrade handshake rejection via `process_request` (#1216)** — `register_websocket`'s handshake-auth `dependencies` now resolve in a `serve(process_request=...)` callback **before** the WebSocket Upgrade. An unauthenticated handshake is rejected with a clean pre-upgrade HTTP **401/403** + JSON envelope (`{"error": ..., "code": "WS_HANDSHAKE_REJECTED"}`), the RFC-correct form, instead of the prior post-upgrade WS close **1008**. The security boundary is unchanged — rejection still happens before `on_connect`/any application surface — and is now fail-closed at two layers (the callback maps any auth raise to a rejection Response; the `websockets` library rejects with HTTP 500 if the callback itself errors). The rejection body never echoes credentials; the server-side WARN log carries only `path` + `status` + exception type.
- **WebSocket subprotocol echo per RFC 6455 §4.2.2 (#1217)** — `register_websocket` wires a `serve(select_subprotocol=...)` callback that confirms the accepted subprotocol back to the client via the `Sec-WebSocket-Protocol` response header (`ws.subprotocol` is now the negotiated value). Negotiation stays reject-only at the allowlist — an unlisted offer still closes with code **1002**, and `select_subprotocol` only ever echoes a value already in the per-path allowlist (never reflects an arbitrary client offer).

### Fixed

- **`/workflows/{name}/execute` honors `NexusHandlerError` typed status (#1218)** — a workflow node raising `NexusHandlerError(status_code=422, body=...)` over the gateway-execute path now maps to the typed HTTP status + body instead of collapsing to a generic 500. The fix lives in the Core SDK gateway (`kailash` 2.28.4, `src/kailash/api/workflow_api.py`); the floor is bumped to `kailash>=2.28.4` so the typed-status behavior ships with this release. Genuine internal errors still collapse to the canonical 500 with no raw-error leak.

### Internal

- Single shared `serve()`-callback rewiring of the transport (`transports/websocket.py::WebSocketTransport._serve` / `_connection_handler`) addresses both #1216 and #1217; the handshake-auth resolution moved fully pre-upgrade and the redundant post-upgrade resolver was removed. Tier-2 coverage: `test_register_websocket_security.py` (pre-upgrade 401/403 + no-lifecycle-on-reject), `test_register_websocket_subprotocol_echo.py` (echo + 1002-on-unlisted), `test_workflow_execute_typed_status_wiring.py`.

## [2.8.0] — 2026-05-31 — FastAPI-parity handler extractors + SSE/WebSocket callbacks (#1174)

FastAPI-shaped ergonomics for Nexus handlers so SDK users migrating from FastAPI keep the same handler shape. Six surface additions, all backwards-compatible (existing `register_handler` / `@app.handler` / class-based `register_websocket` / `register_sse_endpoint` paths are unchanged). No new top-level `fastapi` dependency — extractor types are Starlette re-exports.

### Added

- **`nexus.extractors` sub-module (#1174 ACs 1-4)** — `Depends`, `Request`, `UploadFile`, `Multipart`, `Bytes`, `Headers`, `NexusHandlerError`. Annotation-driven parameter binding for handlers registered via the new `Nexus.handler_extract(name, func)` method. `Depends(callable)` defaults resolve a dependency-injection chain (recursively); `Request` / `Bytes` / `Headers` annotations bind request data; `Multipart` / `UploadFile` bind file uploads. The extractor module MUST NOT use `from __future__ import annotations` — PEP 563 stringized annotations raise a typed `ExtractorPEP563Error` at registration naming the offending handler module.
- **`Nexus.handler_extract(name, func, *, description, tags, metadata, guard)` (#1174 ACs 1-2)** — registers a handler whose parameter annotations/defaults drive a per-handler resolver chain. Resolver built once at registration, runs once per invocation. Dependency errors split client-visible (500 + correlation ID) from server-visible (full traceback) per the resolver error-path contract.
- **`Nexus.dependency_overrides` test-injection map (#1174 AC 3)** — `DependencyOverrideMap` with `override(real, mock)` context manager (auto-restores), plus imperative `set` / `clear` / `clear_all`. Test-only surface; production-time mutation during an active request raises `DependencyOverrideRuntimeMutationError`.
- **`Nexus.register_sse(path, on_subscribe, *, keepalive_interval=15, dependencies=None, max_queue_depth=1000, max_event_bytes=65536, slow_consumer_timeout=30.0)` (#1174 AC 5)** — SSE endpoint primitive. `on_subscribe(request)` is an async generator yielding dicts; each frames as `data: {json}\n\n`. Auth via `dependencies` resolved on subscribe; bounded queue with `QUEUE_OVERFLOW` close; `EVENT_TOO_LARGE` drop-and-continue; slow-consumer disconnect. The existing `register_sse_endpoint(app)` is now a thin shim over this primitive.
- **`Nexus.register_websocket` callback overload (#1174 AC 6)** — adds `on_message` / `on_connect` / `on_disconnect` / `allowed_origins` / `subprotocols` / `dependencies` kwargs alongside the existing class-based `handler_cls` path. Discriminator dispatch (not structural). Callback path synthesizes a `MessageHandler` subclass routed through the same origin-allowlist + handshake-auth validation as the class path.
- **Migration guide** — `packages/kailash-nexus/docs/migration-fastapi.md` walks FastAPI users through auth, typed bodies, file uploads, SSE, WebSocket, and `dependency_overrides`-based tests, with the shipped-surface equivalents.

### Notes

- Typed-body extraction via `Body[T]` and a `Query` extractor are deferred to a follow-up (see migration guide §9). Today, non-extractor handler parameters receive HTTP-body fields via flat-input mapping, and `Bytes` delivers the raw body for manual decode.

## [2.7.0] — 2026-05-29 — scheduler admin HTTP panel + typed-error wiring (#937)

### Added

- **`nexus.admin.register_scheduler_admin(app, admin, *, role="scheduler-admin")` (#937)** — exposes the existing `kailash.runtime.scheduler_admin.SchedulerAdminAPI` over six HTTP routes: `GET /admin/schedules`, `GET /admin/schedules/{id}`, `PATCH /admin/schedules/{id}/{disable,enable,cron}`, `DELETE /admin/schedules/{id}`. Every route runs behind `RequireRole("scheduler-admin")`; the audit `actor` is the authenticated JWT subject (never a request-body field). `ScheduleNotFound → 404`, `ValueError → 400`. `ScheduleView` Pydantic model documents the OpenAPI response shape. See `specs/scheduling.md` §12.

### Fixed

- **Typed `NexusError` now maps to its declared HTTP status (#937)** — `errors.py` documented that the HTTP transport catches `NexusError` subclasses, but no exception handler was ever installed: raising a typed error from a `register_endpoint` handler produced an unhandled 500. `HTTPTransport` now installs the handler (idempotent, from `_initialize_gateway` so it covers the TestClient path); 4xx return `to_response_dict()`, 5xx log the detail server-side and return a generic body.

## [2.6.4] — 2026-05-28 — eliminate `@app.handler` instance-API UserWarning (#1012)

Patch release fixing a startup-log noise issue that fired N `UserWarning("Instance-based API usage detected...")` lines on `@app.handler` registration. No public API change; the warning is now correctly scoped to genuine consumer misuse only.

### Fixed

- **`@app.handler` registration no longer emits `UserWarning` (#1012 → PR #1194)** — `make_handler_workflow` in `src/kailash/nodes/handler.py` builds a `HandlerNode` instance and registers it via `builder.add_node_instance()`. Pre-fix, the call omitted `_internal=True`, causing the workflow builder to emit a `UserWarning("Instance-based API usage detected...")` for every `@app.handler` registration — N handlers = N warnings polluting startup logs and pytest output. Fix: pass `_internal=True` to `add_node_instance()` at `src/kailash/nodes/handler.py:295`. The `_internal` flag narrows the advisory to genuine consumer misuse only. Consumers calling `add_node_instance` directly without `_internal=True` still receive the warning — the flag does NOT suppress the warning globally. Why not `warnings.filterwarnings`: suppression hides genuine consumer misuse elsewhere in the codebase, defeating the purpose of the advisory. Why not string-based `add_node("HandlerNode", id, config)`: `HandlerNode` wraps a Python callable that cannot be expressed as a JSON-serialisable config dict; instance-based registration is the only structurally correct path here. Regression test (4 cases): single `@app.handler` emits zero instance-API warnings; N `@app.handler` registrations emit zero instance-API warnings; handler with optional params emits no warning; direct consumer `add_node_instance` (without `_internal=True`) still warns.

### Dependencies

- `kailash>=2.28.0` (was `kailash>=2.16.0`) — pins the floor to the companion `kailash 2.28.0` release that ships the #1182 audit-chain fix + #1185 async durable resume fix.

### Notes

- The Nexus diff is `src/kailash/nodes/handler.py:295` + new regression test + `pyproject.toml` version + `src/nexus/__init__.py::__version__` + this CHANGELOG entry. No behavior change to the Nexus public API; consumer startup logs are now clean of the spurious instance-API advisory.
- Companion `kailash 2.28.0` release ships #1182 (delegate audit-chain HIGH) and #1185 (async durable resume HIGH).

## [2.6.3] — 2026-05-09 — slim-core decoupling + PyPI install resolvability (#890)

Patch release shipping the kailash-nexus side of the kailash 2.18.0 slim-core decoupling. No behavior change to the Nexus public API; only the dependency manifest is updated so `pip install kailash-nexus` resolves cleanly against the published kailash 2.18.0 wheel.

### Fixed

- **`pip install kailash-nexus` now resolves against PyPI** — pre-2.6.3 declared `kailash[server]>=2.16.0` which did not resolve because the `[server]` extra did not exist on PyPI for kailash 2.16.x / 2.17.x (the extras layout landed with kailash 2.18.0 / #890). The dependency declaration is now an explicit list of the server middleware stack (PyJWT, bcrypt, sqlalchemy, cryptography, etc.) rather than an extras-resolution that PyPI could not satisfy. Result: clean-venv `pip install kailash-nexus` succeeds against the currently-published kailash wheel.

### Dependencies

- Declares the server middleware stack directly (PyJWT, bcrypt, sqlalchemy, cryptography, structlog, prometheus_client, opentelemetry-api/sdk, requests, redis) rather than relying on `kailash[server]`. The set matches the contents of `kailash[server]` as of kailash 2.18.0; downstream consumers see no change in installed packages.
- `kailash>=2.16.0` (was `kailash[server]>=2.16.0`).

### Notes

- Nexus 2.6.3 ships no Python source changes — diff is strictly `pyproject.toml`, `__init__.py::__version__`, and this CHANGELOG entry. The release pairs with the kailash 2.18.0 slim-core layout so `pip install kailash-nexus` works cleanly on a fresh environment.

## [2.6.2] — 2026-05-06 — fix MCP WebSocket transport binding (#816)

Wires the MCP WebSocket transport so AI agents can actually connect to a Nexus instance over `ws://host:mcp_port`. Prior to this fix the MCP server was constructed in stdio mode and never bound a TCP listener — every WebSocket connect attempt failed with a connection-refused error.

### Fixed

- **MCP WebSocket transport bound on `_mcp_port` (#816)** — `Nexus._initialize_mcp_server` now constructs `kailash_mcp.MCPServer` with `transport="websocket"`, `websocket_host="0.0.0.0"`, and `websocket_port=self._mcp_port`. Previously the server defaulted to `transport="stdio"` and dispatched through `MCPServerBase.start()` (hardcoded to stdio); the `_mcp_port` attribute was never actually bound. AI agents connecting via `ws://localhost:<mcp_port>` now reach a real WebSocket listener that handles MCP 2025-06-18 JSON-RPC dispatch (`tools/list`, `resources/list`, `tools/call`, `resources/read`, etc.).
- **WebSocket-only mode supported** — `enable_http_transport=False AND enable_sse_transport=False` is now a first-class deployment shape (the canonical AI-agent-only configuration). Previously `_initialize_mcp_server` early-exited and set `_mcp_server = None` whenever HTTP was disabled, leaving the WebSocket transport orphaned. The HTTP/SSE flags now correctly gate only the **additional** sub-transports inside the MCP server, not the always-on WebSocket listener.
- **Workflow-as-MCP-tool registration via the proper decorator path** — `_register_workflow_as_mcp_tool` now registers via `mcp_server.tool()(workflow_tool)` instead of writing to `mcp_server._tools[name]` directly. The previous direct write populated only the FastMCP-shim dict (which the MCPServer's JSON-RPC handlers do NOT read); the decorator path populates `_tool_registry` which `tools/list` actually iterates. Workflows registered before this fix never appeared in `tools/list` over WebSocket.
- **Workflow inputs forwarded under `parameters` key** — `workflow_tool` now passes `inputs={"parameters": params}` to `execute_workflow_async`, matching the on-wire convention shared with the HTTP `/execute` endpoint. PythonCodeNode workflows reading `parameters.get(...)` now receive their args correctly. Previously args arrived as direct top-level keys, raising `NameError: name 'parameters' is not defined`.
- **JSON response payloads** — `workflow_tool` and resource handlers now return JSON strings rather than Python dicts. `MCPServer._handle_call_tool` and `_handle_read_resource` wrap return values via `str(...)`; returning a dict produced Python repr() (single-quoted keys), invalid JSON for downstream MCP clients. Single-node workflow results are unwrapped from `{"<node_id>": {"result": {...}}}` to the inner dict so agents see `{"echo": "hello"}` not `{"echo": {"result": {...}}}`.
- **`workflow://<name>` resources registered per-workflow** — `Nexus.register()` now installs a `workflow://<name>` MCP resource alongside the tool registration. `resources/list` returns the workflow descriptor URIs and `resources/read workflow://<name>` returns a JSON-encoded summary of the workflow's nodes and schema.
- **Default MCP resources wired** — `_register_default_mcp_resources()` (previously orphan code, never called) now registers `docs://quickstart`, `config://platform`, and `help://getting-started` via the proper `@server.resource()` decorator path so they appear in `resources/list`. `system://nexus/info` returns a JSON string instead of a dict-with-content-field.
- **Circuit-breaker disabled in MCP server** — Removed `circuit_breaker_config={"failure_threshold": 5}` from `MCPServer` construction. The kailash_mcp circuit-breaker pre-check synthesizes `MCPError("Circuit breaker check")` with the default `retryable=False`, which causes `should_retry()` to return False on the very first tool call in the closed state. The `circuit_breaker_config=None` default disables the pre-check until the upstream behavior is corrected.

### Tests

- `packages/kailash-nexus/tests/integration/test_mcp_websocket_discovery.py` — new Tier-2 sibling test covering the MCP WebSocket discovery contract (5 tests: tools/list, resources/list, system info JSON, tools/call JSON payload, workflow resource read). Independent of `tests/e2e/test_ai_agent_workflows.py` so an E2E flake does not lose discovery-contract coverage.
- All 7 tests under `tests/e2e/test_ai_agent_workflows.py::TestAIAgentScenarios` (using the `production_nexus` fixture) now pass.

### Internal

- `_run_mcp_server` calls `MCPServer.run()` (which dispatches on the `transport` attribute) instead of `MCPServer.start()` (which hardcodes stdio).
- MCPChannel is bypassed in WebSocket-only mode — its `_server_loop` only sleeps and binds nothing, so it adds no value when HTTP/SSE sub-transports are off.

## [2.6.1] — 2026-05-03 — issue #781 hygiene release (T4)

Patch release cutting PyPI for T4 (nexus TODO-NNN comment-strip) of the issue #781 cleanup workstream.

### Changed (T4 of #781 — comment-only, packages/kailash-nexus/src/)

- Stripped 16 `TODO-NNN` markers in `nexus/core.py` (5 hits — public-API section banners) + `nexus/auth/` subsystem (11 hits across plugin, audit/middleware, audit/backends/{base,custom,dataflow,logging}, audit/{config,pii_filter,record}, audit/**init**) per the ratified disposition catalog (5 Class 1a section banners, 11 Class 1b module docstring provenance).

### Notes

- Comment-only diff: zero changes to imports, signatures, control flow, or types. The bump cuts PyPI per `build-repo-release-discipline.md` Rule 1.

## [2.6.0] — 2026-04-30 — WebSocket Origin allowlist + `Connection.headers` (#673)

Minor release closing the WebSocket Origin-header bypass: every `register_websocket(...)` registration now hoists Origin-allowlist enforcement to the framework so consumer handlers no longer have to re-implement the check (and silently drop it on copy-paste).

### Added

- **`Nexus.websocket(allowed_origins=...)` + `register_websocket(allowed_origins=...)` (#673)** — opt-in per-route Origin allowlist. The Origin validator runs before the handler is invoked; mismatched / missing Origin closes the socket with WebSocket close code `1008 (policy violation)` and emits a structured WARN log keyed on the request id.
- **`Connection.headers` (#673)** — the request `Headers` mapping is now exposed on the `Connection` object so handlers needing per-request header inspection (auth tokens, correlation IDs) no longer parse the raw scope dict.
- Tier 1 unit suite for the Origin validator and `Connection.headers` plumbing.
- Tier 2 regression suite for end-to-end allowlist enforcement on a live `register_websocket` registration.

### Dependencies

- `kailash>=2.13.1` (was `>=2.11.0`).

## [2.5.0] — 2026-04-30 — `Nexus.add_startup_handler` / `add_shutdown_handler` (the v2.13.0 cluster: closes #712)

Minor release adding the canonical "run-once at server start" hook surface so consumers no longer need to reach for `nexus.fastapi_app.on_event(...)` (which has the lazy-init timing trap — `fastapi_app` returns `None` until the enterprise gateway is initialized) or author a full `NexusPluginProtocol` implementation for a single callback.

### Added

- **`Nexus.add_startup_handler(func)` (#712 / S3)** — registers a zero-argument callable (sync `def` or `async def`) that fires during the FastAPI lifespan startup phase, in registration order, inside uvicorn's event loop. Appends to the same internal `_startup_hooks` list that powers the plugin protocol's `on_startup` lifecycle hook (§10.2). Returns `self` for chaining. Raises `TypeError` on non-callables and `RuntimeError` if called after `Nexus.start()` (the lifespan has already fired or is firing; a late append cannot be guaranteed to run). The canonical pattern for "run DataFlow async DDL at server start" — `app.add_startup_handler(create_schema)` where `create_schema` is `async def create_schema(): await db.create_tables_async()`.
- **`Nexus.add_shutdown_handler(func)` (#712 / S3)** — symmetric to `add_startup_handler`. Appends to `_shutdown_hooks`. Hooks fire in REVERSE registration order — the last installed runs first — so pairs of (open_resource, close_resource) registered in init order tear down LIFO. Same validation contract.

### Documented

- **`fastapi_app` lazy-init timing trap (issue #712)** — the `fastapi_app` property returns `None` until the enterprise gateway has been initialized; gateway init is lazy (fires on the first `register()` call, or at `start()` if no `register()` was called first). Code that accesses `fastapi_app` immediately after `Nexus(...)` therefore sees `None` and any downstream attribute access (e.g. `nexus.fastapi_app.on_event("startup")`) raises `AttributeError: 'NoneType' object has no attribute 'on_event'`. Docstring on `fastapi_app` now warns explicitly and points to `add_startup_handler` as the safe pre-init surface. See `specs/nexus-services.md` §29 for the full timing contract.

### Tests

- `tests/regression/test_issue_712_consumer_startup_patterns.py` — Tier 2 regression (in the kailash root repo) verifying the new API against real DataFlow async DDL + sibling FastAPI lifespan sites.

### Cross-SDK

- kailash-rs uses axum + tokio; no equivalent custom-lifespan footgun. No companion issue.

## [2.4.1] — 2026-04-29 — `MountInfo` exported in `__all__`

Patch release closing the build-repo-release-discipline.md Rule 5 drift from PR #720. `MountInfo` (`nexus/core.py`) was already imported at module-scope in `nexus/__init__.py` but absent from `__all__`, triggering `pyright` "MountInfo is not accessed" and violating `orphan-detection.md` Rule 6 (Module-Scope Public Imports Appear In `__all__`). No behavioral change; pure public-API contract repair.

### Fixed

- `MountInfo` added to `__all__` alongside its sibling middleware-API entries (`MiddlewareInfo`, `RouterInfo`, `NexusPluginProtocol`). Pre-existing oversight surfaced during the 2.4.0 release-prep cycle; deferred to this patch per `git.md` § release-branch metadata-only convention.

## [2.4.0] — 2026-04-29 — Pluggable WebhookSigner + Twilio support + ML mount-path canonicalization

Minor release adding pluggable webhook signature verification (PR #717, closes #687), canonicalizing the ML mount path documentation (W6-009, closes F-C-26), and registering the long-standing `regression` pytest marker. Backward-compatible: every existing `WebhookTransport(secret=...)` caller sees zero behavior change (default signer preserves the historical `sha256=<hex>` HMAC-SHA256 raw-body shape).

### Added

- **Pluggable webhook signature verification (#687)**: `WebhookTransport` accepts a `signer: WebhookSigner` parameter. Built-in `HmacSha256Signer` (default — preserves prior behavior, output `sha256=<hex>`) and `TwilioSigner` (HMAC-SHA1 over `request_url + sorted(key+value)`-canonicalized form params, base64 raw digest, no prefix). Custom signers — Stripe, GitHub, Slack, Shopify — implement the `WebhookSigner` Protocol as user-defined classes. Backward-compatible: existing `WebhookTransport(secret=...)` callers see zero behavior change. New URL-canonicalized entry points `compute_signature_for_request(*, url, form_params, payload_bytes=b"")` / `verify_signature_for_request(*, signature, url, form_params, payload_bytes=b"")` for request-aware signers. Twilio canonical test vector pinned in `tests/unit/transports/test_webhook_signer.py` (auth token `12345`, URL `https://mycompany.com/myapp.php?foo=1&bar=2`, params `{CallSid, Caller, Digits, From, To}` → signature `RSOYDt4T1cUTdK1PDd93/VVr8B8=`). Verify-failure emits a structured WARN log with `signer_class` field per `rules/observability.md`; secret and provided signature are NEVER logged per `rules/security.md`. Cross-SDK alignment to be filed against `esperie/kailash-rs`.

### Documentation

- **W6-009 — Canonicalized ML mount path on `mount_ml_endpoints()` (closes F-C-26)**: `specs/nexus-ml-integration.md` previously cited `nexus.register_service("inference", server.as_nexus_service())` and an `InferenceServer.as_nexus_service()` API that were never shipped. The canonical entry — verified at `packages/kailash-nexus/src/nexus/ml/__init__.py:222` — is `nexus.ml.mount_ml_endpoints(nexus, serve_handle, *, prefix="/ml")`. Spec sections §5.1, §5.2, §6 (error class), §7.2 (Tier-2 test name), §10 (Migration Path), and §12 (Cross-References) updated to reference the shipped surface; absent legacy names retracted per `rules/orphan-detection.md` §3 (Removed = Deleted, Not Deprecated).

### Tests

- **`tests/integration/test_mount_ml_endpoints.py` (new)**: structural-invariant Tier-2 regression test pinning `mount_ml_endpoints(nexus, serve_handle, *, prefix="/ml")` as the canonical entry. Asserts (a) signature shape; (b) absence of `Nexus.register_service` and `InferenceServer.as_nexus_service`; (c) end-to-end JWT-claim propagation into the predictor against a real Nexus + Protocol-satisfying ServeHandle (per `rules/testing.md` § Tier 2 "Protocol-Satisfying Deterministic Adapters" — no mocks). 7/7 passing locally.

### Internal

- `packages/kailash-nexus/pytest.ini` — register the `regression` marker (already in use by `tests/regression/test_issue_211.py`) to clear pre-existing `PytestUnknownMarkWarning` per `rules/zero-tolerance.md` Rule 1.

## [2.3.0] - 2026-04-25 — WebSocket per-connection unicast + on_message reply delivery (#618)

### Added

- **`MessageHandler.on_message` / `on_text` return values are auto-delivered (#618)**: when a class-based WebSocket handler returns a non-`None` value from `on_message` or `on_text`, the registry sends it back to the originating client on the same connection — no need for the handler to call `await conn.send_json(...)` explicitly. Type contract: `dict`/`list` → JSON via `send_json`, `str` → raw text via `send_text`, `bytes` → UTF-8 decoded then `send_text` (invalid UTF-8 logged at WARN and dropped), `None` → no auto-reply (handler-owned send). Tenant-safe by construction — the auto-reply CAN ONLY reach the originating socket. Cross-SDK parity with `kailash-rs#589`.
- **`Nexus.websocket_send_to(path, connection_id, payload) -> bool` (#618)**: per-connection unicast push from external publishers. Use this when an external producer (DataFlow change stream, message-queue consumer, scheduled job) needs to address ONE specific client by its `connection_id`, not the broadcast set. Dispatch is scoped to the named connection — no other client receives the frame, so per-tenant push is safe by construction. Returns `False` (no raise) for unknown path, unknown `connection_id`, or already-closed socket. Mirrors `MessageHandlerRegistry.send_to` with the same name on the `Nexus` facade for parity with `websocket_broadcast`.
- **`MessageHandlerRegistry.send_to(path, connection_id, payload)`**: the registry-level primitive. Reuses `Connection.send_json` / `send_text` so the wire frame matches `on_message` auto-replies bit-for-bit.

### Changed

- `MessageHandler.on_message` / `on_text` return type widened from `None` to `Any` (with documented per-shape delivery semantics). Backward-compatible — handlers returning `None` continue to behave as before.

### Migration

- 2.2.x → 2.3.0 is additive. No required handler changes. Handlers that already call `await conn.send_json(...)` and return `None` keep working unchanged. Handlers that previously had to duplicate their reply payload (return + explicit send) MAY now drop the explicit send and rely on the return-value contract.

## [2.2.0] - 2026-04-23 — ML bridge: tenant/actor ContextVars, MLDashboard auth, ml-endpoint mount (W31.c)

### Added

- **`nexus.context` module**: request-scoped `ContextVar`s for cross-engine tenant/actor propagation. `JWTMiddleware` now sets `_current_tenant_id` from the `tenant_id` JWT claim (optional) and `_current_actor_id` from the `sub` claim (required) on every validated request, with reset-in-`finally` so an exception inside `call_next` cannot leak state into the next request on the same worker. Downstream engines (kailash-ml, kailash-dataflow, kailash-kaizen) read ambient context via `get_current_tenant_id()` / `get_current_actor_id()` without extracting JWT claims themselves. Per `specs/nexus-ml-integration.md` §§2–3.
- **`nexus.ml.MLDashboard`**: Nexus-auth adapter for `kailash_ml.dashboard.MLDashboard(auth="nexus")`. Reuses the Nexus instance's JWT config (issuer / audience / JWKS URL / public key) via `MLDashboard.from_nexus(nexus)` so the dashboard does NOT store key material independently. Returns a frozen `DashboardPrincipal(actor_id, tenant_id, scopes)` on verification. Per spec §4.
- **`nexus.ml.mount_ml_endpoints(nexus, serve_handle)`**: mounts REST + MCP + WebSocket routes for a kailash-ml `ServeHandle` behind Nexus. Ambient tenant/actor from the JWT middleware's ContextVars propagate into every `predict()` call; endpoint registration is lazy (works before `start()`). Routes: `POST /ml/predict`, `GET /ml/describe`, `GET /ml/healthz`, `POST /ml/mcp/predict`, WebSocket `/ml/ws`. Per spec §5 + §1.1 item 4.
- **`nexus.ml.dashboard_embed(port)`**: returns an HTML iframe snippet for embedding the ML dashboard behind Nexus auth.

### Changed

- `JWTMiddleware.dispatch` now sets `nexus.context._current_tenant_id` / `_current_actor_id` ContextVars on both the JWT-validated path and the API-key path, with matching reset tokens released in `finally:`. No signature change, no new required claims — `tenant_id` is optional, `sub` is already mandatory per RFC 7519 §4.1.2.

### Migration

- 2.1.x → 2.2.0 is additive. `JWTMiddleware.__init__` is unchanged. `JWTValidator` gains no new required config. Users relying on `specs/nexus-auth.md` §9.1 behavior are unaffected. Optional: switch from `request.state.user.tenant_id` extraction to `get_current_tenant_id()` (simpler, same value, not required).

## [2.1.1] - 2026-04-19 — CRITICAL hotfix: lifespan crash on FastAPI router dispatch method (#531, PR #533)

### Fixed

- **CRITICAL: Every production Nexus 2.1.0 service crashed at uvicorn lifespan startup** (#531): `WorkflowServer.__init__` called `app.router.startup()` in the custom FastAPI lifespan, relying on a dispatch method name that does not exist in all FastAPI versions. Production environments with a FastAPI build that exposes `_startup` (not `startup`) raised `AttributeError: 'APIRouter' object has no attribute 'startup'` at lifespan entry — before any request could be served. Fix: iterate `router.on_startup` / `router.on_shutdown` lists directly, awaiting coroutine results in order. This matches what FastAPI's own `_DefaultLifespan` does internally and is stable across all FastAPI versions. Rollback to 2.0.3 (the workaround reporters were using) is no longer needed — upgrade directly to 2.1.1.

## [2.1.0] - 2026-04-19 — HttpClient + ServiceClient + TypedServiceClient + lifespan hooks (#464 #465 #473 #500 #501)

### Added

- **`HttpClient` + `ServiceClient` with SSRF-aware config (#464 #473, PR #505)**: `nexus.HttpClient` is a thin wrapper around `httpx.AsyncClient` with a `HttpClientConfig` that enforces SSRF-aware defaults (no private IP ranges, connection timeouts, redirect limits). `nexus.ServiceClient` builds on `HttpClient` and provides a named-service abstraction with structured error types (`ServiceClientError`, `ServiceClientHttpError`, `ServiceClientHttpStatusError`, `ServiceClientDeserializeError`, `ServiceClientInvalidHeaderError`, `ServiceClientInvalidPathError`).
- **`TypedServiceClient` wrapper for S2S JSON APIs (#465, PR #507)**: `nexus.TypedServiceClient` adds Pydantic-model-driven request/response serialization on top of `ServiceClient`. Callers declare `RequestModel` and `ResponseModel` types; `TypedServiceClient` validates, serializes, deserializes, and raises typed errors on schema mismatch. Covers the common S2S JSON API pattern without manual `json.loads` / Pydantic `.model_validate`.
- **`post_webhook` + `probe_remote_health` outbound helpers (PR #509)**: `nexus.post_webhook(url, payload, *, secret)` fires a signed outbound webhook using HMAC-SHA256 over the raw JSON bytes (not re-serialized). `nexus.probe_remote_health(url, *, timeout)` performs a lightweight GET health probe and returns a structured `RemoteHealthResult`.

### Fixed

- **Custom FastAPI lifespan silently ignored `app.router.on_startup` / `app.router.on_shutdown` handlers** (#500): `WorkflowServer.__init__` passed a custom `lifespan` to `FastAPI()`, which replaces (not wraps) Starlette's default `_DefaultLifespan` — the only code path that iterated the router-level hooks. Any user registering a handler via the documented FastAPI pattern `app.fastapi_app.router.on_startup.append(fn)` saw `fn` silently dropped. Fix: the lifespan now explicitly invokes `await app.router._startup()` on entry and `await app.router._shutdown()` on exit.
- **Plugin `on_startup` async hooks cancelled scheduled background tasks** (#501): `Nexus.start()` called `_call_startup_hooks()` BEFORE uvicorn booted. For async hooks, the sync path used `asyncio.run(hook())` which created a throwaway event loop, ran the hook (commonly scheduling `asyncio.create_task(periodic_job())`), then CLOSED the loop — cancelling every task the hook had just created. Uvicorn then booted its own loop and the tasks were gone. Fix: plugin startup hooks now run via `_call_startup_hooks_async` inside the FastAPI lifespan context manager, which executes on uvicorn's own event loop. Tasks scheduled by a plugin hook therefore survive for the server's lifetime. The pre-uvicorn invocation in `Nexus.start()` was removed; shutdown hooks are now called inside the lifespan via `_call_shutdown_hooks_async` (with an idempotency flag so the sync `stop()` path doesn't double-fire).
- **Partial-startup crash leaked `ShutdownCoordinator`-registered resources** (#500/#501 round-2 sec H1): the lifespan's `try:` only wrapped `yield`, so an exception from `router.startup()` or `startup_hook()` skipped the `finally:` block. The `ThreadPoolExecutor` registered at `WorkflowServer.__init__` never shut down, and any Nexus plugin whose earlier `on_startup` had run saw its paired `on_shutdown` silently skipped. Fix: the `try:` now wraps every startup step, so the shutdown branch runs on every path — graceful exit, startup exception, or timeout. Each teardown step (`shutdown_hook` / `router.shutdown` / `ShutdownCoordinator.shutdown`) is wrapped in its own `try/except` so one failing cleanup cannot block the next.
- **`_shutdown_hooks_fired` TOCTOU between sync `stop()` and async lifespan path** (#500/#501 round-2 sec H2): the idempotency flag was checked and set without a lock. When a signal handler invoked `Nexus.stop()` while uvicorn's lifespan was concurrently running the async shutdown path, both paths could read `False`, both could set `True`, and both could iterate the hook list — firing every `on_shutdown` twice (counter-increment plugins corrupt; token-revocation plugins panic). Fix: added `_shutdown_hooks_fired_lock` (`threading.Lock`) protecting the check-and-set across both paths. CPython's GIL makes the individual load and store atomic; the lock makes the compound check-then-set atomic, which is what the idempotency contract requires.
- **Pre-existing `asyncio.iscoroutinefunction` deprecation sites in `nexus/core.py` L209 (`_wrap_with_guard`) and L1611 (`use_middleware`)** (#500/#501 round-2 MED-2 / zero-tolerance Rule 1): Python 3.14 deprecated the `asyncio` form in favor of `inspect.iscoroutinefunction`. Round-1 swapped the four hook drivers; round-2 swapped the two remaining sites so no deprecation fires from any Nexus code path.

### Added

- `startup_hook` / `shutdown_hook` kwargs on `WorkflowServer.__init__` and `create_gateway()` so upstream wrappers (Nexus) can route lifecycle hooks through the FastAPI lifespan without re-implementing it.
- `startup_hook_timeout` kwarg on `WorkflowServer.__init__` and `create_gateway()` (default `None` = unbounded, matching historical behavior). When set to a finite value, the lifespan wraps `startup_hook()` in `asyncio.wait_for` so a hung plugin `on_startup` cannot pin uvicorn forever and prevent it from accepting connections. On timeout the shutdown branch still runs so partial startup state is torn down. Addresses the DoS vector described in round-2 sec M2.
- `Nexus._call_startup_hooks_async` / `Nexus._call_shutdown_hooks_async`: awaitable hook drivers invoked from the lifespan. Errors logged via `logger.exception` (preserves traceback, zero-tolerance Rule 3); failures in one hook do not prevent later hooks, `router._shutdown`, or the `ShutdownCoordinator` from running.
- Regression tests `tests/regression/test_issue_500_router_on_startup.py` + `tests/regression/test_issue_501_hook_task_lifetime.py` (minimal reproductions, `@pytest.mark.regression`, never deleted).
- Tier 2 wiring tests `tests/integration/nexus/test_router_on_startup_fires.py`, `test_plugin_on_startup_task_survives.py`, `test_shutdown_symmetric.py`, `test_shutdown_idempotency.py` (2 tests covering both path orderings), `test_partial_startup_teardown.py` (crashed-startup teardown), `test_startup_hook_timeout.py` (2 tests covering bounded + unbounded modes) — real uvicorn boot, real FastAPI lifespan, real asyncio tasks; no mocks.

### Changed

- Lifespan log lines now use structured-kwargs form per `observability.md` MUST Rule 3 (`logger.info("workflow_server.lifespan.startup", extra={"title": title, "version": version})` instead of f-strings). Each startup/shutdown step emits a dedicated event name (`startup`, `shutdown`, `shutdown_hook_failed`, `router_shutdown_failed`, `coordinator_shutdown_failed`, `shutdown_complete`, `startup_hook.timeout`) for grep-able operational tracing.

## [1.7.2] - 2026-04-03

### Fixed

- **Nexus auth security hardening** (#226): API key auth validation, token age checking, stale session detection hook
- Auth JWT module refactored for security (constant-time comparison, bounded token cache)

## [1.7.1] - 2026-04-01

### Fixed

- **Connection stampede on Docker Desktop** (#211, #212): Nexus enterprise gateway created a duplicate `AsyncLocalRuntime` independently from Nexus's own runtime, doubling the connection pool footprint. Gateway now shares Nexus's runtime via `runtime=` injection.
- **Hardcoded `server_type="enterprise"` and `max_workers=20`**: Both are now configurable via constructor params (`server_type`, `max_workers`) and env vars (`NEXUS_SERVER_TYPE`, `NEXUS_MAX_WORKERS`). Default auto-detects `min(4, cpu_count)`.
- **Input validation**: `server_type` validates against `{"enterprise", "durable", "basic"}` at construction. `max_workers` rejects `< 1` and non-numeric env var values.
- **MCP transport orphan runtime**: `MCPTransport` now accepts an optional `runtime` parameter to share the parent's pool instead of creating its own.
- **Pre-existing test failures**: 2 tests that required `enable_http_transport=True` for MCP server initialization now pass.

### Added

- 8 regression tests in `tests/regression/test_issue_211.py` covering dual runtime elimination, configurable gateway, and env var overrides.

## [1.7.0] - 2026-04-01

### Added

- **Transport ABC**: Abstract base class for pluggable transport implementations. Clean separation of protocol handling from business logic.
- **HTTPTransport**: Production HTTP transport replacing the monolithic gateway. Supports middleware, CORS, and streaming.
- **MCPTransport**: Dedicated MCP transport with proper protocol handling, resource management, and tool dispatch.
- **HandlerRegistry**: Centralized handler registration and dispatch. Type-safe handler resolution with middleware support.
- **EventBus**: Internal event system for cross-component communication. Publish/subscribe with typed events.
- **BackgroundService**: Managed background task lifecycle with graceful shutdown, health monitoring, and restart policies.
- **Phase 2 APIs**: File serving, bridge patterns, and extended handler capabilities.

### Changed

- Transport layer refactored from monolithic gateway to pluggable architecture. Existing APIs remain backward-compatible.

### Test Results

- 1,153 tests passed, 0 failures

## [1.6.1] - 2026-03-31

### Fixed

- `__del__` finalizer safety for 3 Nexus classes.

## [1.4.1] - 2026-02-22

### V4 Audit Hardening Patch

Post-release reliability hardening from V4 final audit.

### Fixed

- **Stale Transport Test**: Updated `test_receive_message_not_implemented` to test actual queue-based message receiving behavior instead of expecting `NotImplementedError` from implemented method

### Test Results

- Nexus: 1,027 passed

## [1.4.0] - 2026-02-21

### Quality Milestone Release - V4 Audit Cleared

This release completes 4 rounds of production quality audits (V1-V4) with all Nexus-specific gaps remediated.

### Changed

- **Transport Error Sanitization**: WebSocket error messages now return only `type(e).__name__` instead of raw `str(e)` to prevent internal detail leakage
- **JSON Error Messages**: Invalid JSON errors now return generic message instead of parse details

### Security

- Error messages sanitized before sending to WebSocket clients
- Max message size limits enforced on transport
- V4 audit: 0 CRITICAL, 0 HIGH findings

### Test Results

- 638 unit tests passed (+1 pre-existing)

## [1.1.1] - 2025-10-24

### Release Quality

Production-ready release with comprehensive stub implementation fixes and documentation updates.

#### Key Improvements

- All 10 stub implementations replaced with production-quality code
- Zero silent success cases remaining
- Zero breaking changes - fully backward compatible
- 385/411 tests passing (93.7%), 100% stub-related tests passing
- Enterprise production quality maintained

See v1.1.0 changelog entry below for detailed fixes.

## [1.1.0] - 2025-10-24

### CRITICAL: Stub Implementation Fixes

All 10 stub implementations have been fixed with production-ready solutions:

#### CRITICAL Fixes (Silent Success Issues)

1. **Channel Initialization - REMOVED** (was returning success without initialization)
   - Deleted redundant `ChannelManager.initialize_channels()` method
   - Channels now initialized correctly via `Nexus._initialize_gateway()` and `Nexus._initialize_mcp_server()`
   - Added architecture comments explaining ownership

2. **Workflow Registration - REMOVED** (was logging success without registration)
   - Deleted redundant `ChannelManager.register_workflow_on_channels()` method
   - Multi-channel registration handled properly by `Nexus.register()`
   - Single source of truth for workflow registration

3. **Event Broadcasting - UPDATED** (claimed to broadcast but didn't)
   - Updated `Nexus.broadcast_event()` with honest implementation
   - v1.0: Events logged to `_event_log` (retrieve with `get_events()`)
   - v1.1 (planned): Real-time WebSocket/SSE broadcasting
   - Changed logging from INFO to DEBUG with clear capability documentation

#### HIGH Priority Fixes

4. **Resource Configuration** - Fixed AttributeError
   - Changed `self.nexus.enable_auth` → `self.nexus._enable_auth`
   - MCP `config://platform` resource now works correctly

5. **Event Stream Initialization** - Honest Logging
   - Removed fake "✅ initialized" messages
   - Changed logging level from INFO to DEBUG
   - Added clear v1.1 deferral documentation

6. **Workflow Schema Extraction** - Metadata-based
   - Implemented metadata-based schema extraction
   - Returns empty dict when metadata not provided
   - v1.1 (planned): Automatic schema inference from nodes

7. **Plugin Error Handling** - Specific Exceptions
   - Replaced bare `except:` with specific exception handling
   - TypeError logged as warning (constructor args required)
   - Other exceptions logged as errors with full context

#### MEDIUM Priority Fixes

8. **Discovery Error Handling** - Improved Logging
   - Added debug-level logging for discovery failures
   - Differentiates "not a workflow" from "error calling function"

9. **Plugin Validation** - Basic Validation
   - Validates plugin has `name` and `apply` method
   - Returns False for invalid plugins

10. **Shutdown Cleanup** - Error Logging
    - Added error logging during shutdown
    - Graceful handling of cleanup failures

### Documentation Updates

- All methods now have honest docstrings reflecting v1.0 vs v1.1 capabilities
- Architecture comments explain initialization and registration ownership
- Clear roadmap for v1.1 features (WebSocket broadcasting, auto schema inference)

### Test Updates

- 248/248 unit tests passing
- Updated tests to verify actual architecture (not stubs)
- Tests now check real initialization, not just return values

### Breaking Changes

**None** - All fixes are internal improvements with no API changes

### Migration Guide

No migration needed - existing code continues to work unchanged

### Known Limitations (v1.0)

- Event broadcasting only logs events (no real-time broadcast)
- Workflow schema extraction requires explicit metadata
- Events retrievable via `get_events()` helper method

### Planned for v1.1

- Real-time event broadcasting via WebSocket/SSE
- Automatic workflow schema inference
- Enhanced MCP resource capabilities

## [1.0.8] - 2025-10-09

### CRITICAL HOTFIX

- Fixed server startup failure where daemon threads were killed on process exit
- `start()` method now blocks until Ctrl+C (like FastAPI/Flask behavior)
- API server now starts correctly and accepts requests

### Fixed

- Server never starting due to daemon thread + immediate return pattern
- Version string mismatch (`__version__` now correctly set to package version)
- Process exiting immediately after `start()` call
- Port never binding because daemon thread died before uvicorn started

### Changed

- **BREAKING**: `start()` method now blocks until stopped (Ctrl+C or `.stop()`)
- For background execution, run in a thread: `Thread(target=app.start).start()`
- Gateway runs in main thread instead of daemon thread
- Updated docstring to document blocking behavior

### Migration Guide

**BEFORE (v1.0.7 - BROKEN)**:

```python
from nexus import Nexus

app = Nexus()
app.register("my_workflow", workflow.build())
app.start()  # Returned immediately, server never started
# Process exited here - daemon threads were killed
# Result: Connection refused on all requests
```

**AFTER (v1.0.8 - FIXED)**:

```python
# Option 1: Production usage (recommended)
from nexus import Nexus

app = Nexus()
app.register("my_workflow", workflow.build())
app.start()  # Now blocks until Ctrl+C - server stays running!
# Server runs here, handling requests until you press Ctrl+C
```

```python
# Option 2: Background/testing (if needed)
import threading
import time
from nexus import Nexus

app = Nexus()
app.register("my_workflow", workflow.build())

# Run in background thread
thread = threading.Thread(target=app.start, daemon=True)
thread.start()
time.sleep(2)  # Wait for startup

# ... your test code here ...

app.stop()  # Clean shutdown when done
```

**Rollback if needed**:

```bash
# If v1.0.8 causes issues (unlikely)
pip install kailash-nexus==1.0.6  # Last working version before v1.0.7
```

**Key Changes**:

- `start()` now blocks (like FastAPI's `uvicorn.run()`)
- Server stays running until explicit stop (Ctrl+C or `app.stop()`)
- No more daemon thread bug - main thread runs the gateway
- Works correctly on all platforms (Unix, Windows, macOS)

### Technical Details

- Removed `_server_thread` daemon thread for gateway
- Gateway now runs via direct `gateway.run()` call in main thread
- MCP server still runs in background daemon thread (non-critical path)
- Improved error handling with automatic `stop()` on exceptions
- Added graceful KeyboardInterrupt (Ctrl+C) handling
- Added "Press Ctrl+C to stop" message to startup logs

### Testing

- Added 4 new integration tests for real-world startup scenarios
- All tests verify server actually starts and stays running
- Tests confirm port binding and request handling work correctly
- All existing E2E tests pass with no modifications needed

## [1.0.7] - 2025-10-08

### Added

- FastAPI mount behavior documentation
- Enhanced logging with full endpoint URLs
- Custom 404 error handler with helpful guidance
- Better startup logging showing all available endpoints

### Known Issues

- **CRITICAL BUG**: Server never starts due to daemon thread issue
- Process exits immediately after `start()` call
- Port never binds, all requests get "Connection refused"
- This version is non-functional in production
- **Fixed in v1.0.8**

## [1.0.3] - 2025-07-22

### Added

- Comprehensive documentation validation and testing infrastructure
- WebSocket transport implementation for MCP protocol integration
- Full test coverage validation (77% overall coverage achieved)
- Real infrastructure testing for all code examples

### Fixed

- CLAUDE.md documentation examples now work correctly (100% validation rate)
- Corrected `list_workflows()` references to use `app._workflows`
- Fixed `start()` method documentation (corrected async/sync specification)
- All constructor options and enterprise configuration patterns validated

### Improved

- Test quality with non-trivial infrastructure requirements
- Edge case coverage and error scenario validation
- WebSocket client management and concurrent connection handling
- MCP protocol message processing and response handling

### Technical

- 248 unit tests passing with robust timeout enforcement
- Comprehensive WebSocket transport validation
- Real Nexus instance testing without mocking
- Complete API correctness verification

## [1.0.2] - 2025-07-20

### Fixed

- Version mismatch between setup.py/pyproject.toml (1.0.1) and **init**.py (1.0.0)
- Updated CLI module imports in integration tests from `kailash.nexus.cli` to `nexus.cli`

### Changed

- Updated Kailash SDK dependency to >= 0.8.5 to ensure compatibility with removal of `src/kailash/nexus`
- All versions now synchronized at 1.0.2

### Notes

- No breaking changes for Nexus users
- The removal of `src/kailash/nexus` from core SDK does not affect the Nexus app framework
- Users should continue to use `from nexus import Nexus` as documented

## [1.0.1] - Previous Release

### Added

- Zero-configuration multi-channel orchestration
- Unified API, CLI, and MCP interfaces
- Cross-channel session management
- Enterprise features (auth, monitoring)

## [1.0.0] - Initial Release

- First stable release of Nexus framework
- Complete multi-channel platform
- Production-ready with enterprise features
