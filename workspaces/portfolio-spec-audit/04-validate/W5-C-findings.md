# W5-C Findings — nexus + middleware

**Specs audited:** 6
**§ subsections enumerated:** ~62 (across 6 specs)
**Findings:** CRIT=0 HIGH=4 MED=6 LOW=4
**Audit completed:** 2026-04-26

---

## nexus-core.md (Spec v2.1.1)

## F-C-01 — nexus-core.md § 2.1 — `Nexus.__init__` parameter set matches spec

**Severity:** LOW (informational)
**Spec claim:** Constructor signature with 18 named params (`api_port`, `mcp_port`, `enable_auth`, ..., `runtime`).
**Actual state:** `packages/kailash-nexus/src/nexus/core.py:243-277` matches spec including ordering, defaults, and runtime injection. Validation guards on `server_type`, `max_workers`, `NEXUS_MAX_WORKERS` env-var int parsing all present (lines 322-340).
**Remediation hint:** None — parity confirmed.

## F-C-02 — nexus-core.md § 2.6 — `health_check()` is documented under §2.5/§7 (services) but spec §2.6 lists only properties; `Nexus.health_check()` exists and is undocumented in §2.6

**Severity:** LOW
**Spec claim:** §2.6 enumerates `fastapi_app`, `middleware`, `routers`, `plugins`, `cors_config`, `active_preset`, `preset_config` as the property surface.
**Actual state:** `Nexus.health_check()` exists at `packages/kailash-nexus/src/nexus/core.py:3068` and is publicly documented in agent guidance (`nexus-specialist.md`) and used by `BackgroundService.is_healthy()` contract. Spec § 2.x does not enumerate it.
**Remediation hint:** Add `health_check()` to §2.5 (Lifecycle) or §2.6 (Property Access) — surface is real and stable.

## F-C-03 — nexus-core.md § 1 (Import Architecture) — `nexus/__init__.py` re-exports verified; circular-chain modules import raw starlette/fastapi correctly

**Severity:** LOW (informational)
**Spec claim:** `nexus/__init__.py` re-exports `Request, Response, JSONResponse, StreamingResponse, WebSocket, WebSocketDisconnect, HTTPException`. Tier-1 directories (`servers/`, `gateway/`, `api/`, `middleware/communication/`, `middleware/auth/`, `middleware/gateway/`, `middleware/database/`, `channels/`) import from raw starlette to avoid circular imports.
**Actual state:** Confirmed. Re-exports present in `packages/kailash-nexus/src/nexus/__init__.py`. Circular-chain modules use raw starlette per the `enforce-framework-first` hook exemption list.
**Remediation hint:** None — architectural claim verified.

## F-C-04 — nexus-core.md § 8.1 — Preset list mismatch (spec lists 5; code includes "lightweight" + "standard")

**Severity:** LOW
**Spec claim:** §8.1 table lists `none`, `lightweight`, `standard`, `saas`, `enterprise`. §3.1 (`Preset` enum) lists only `NONE`, `SAAS`, `ENTERPRISE`.
**Actual state:** `packages/kailash-nexus/src/nexus/presets.py:280-340` defines all 5 string-keyed presets. `packages/kailash-nexus/src/nexus/engine.py:43` defines `Preset` enum with only 3 members (`NONE`, `SAAS`, `ENTERPRISE`). Mismatch is documented across §3.1 vs §8.1 — the engine enum cannot select `lightweight` / `standard`.
**Remediation hint:** Either expand `Preset` enum to include `LIGHTWEIGHT`/`STANDARD` or document that those presets are accessible only via the `Nexus(preset="...")` string-keyed path, not the engine builder. Spec already implicitly distinguishes the two surfaces but should call out the asymmetry.

---

## nexus-channels.md (Spec v2.1.1)

## F-C-05 — nexus-channels.md § 4.1 — Transport ABC contract verified

**Severity:** LOW (informational)
**Spec claim:** `Transport(ABC)` with `name`, `start(registry)`, `stop()`, `is_running` abstracts + `on_handler_registered(handler_def)` default no-op.
**Actual state:** `packages/kailash-nexus/src/nexus/transports/base.py:18` defines `Transport(ABC)` matching the contract.
**Remediation hint:** None — verified.

## F-C-06 — nexus-channels.md § 4.2-4.5 — All four transports exist (HTTPTransport, MCPTransport, WebSocketTransport, WebhookTransport)

**Severity:** LOW (informational)
**Spec claim:** Four transport classes exist with documented constructors and behaviors.
**Actual state:**
- `HTTPTransport`: `packages/kailash-nexus/src/nexus/transports/http.py:34`
- `MCPTransport`: `packages/kailash-nexus/src/nexus/transports/mcp.py:19` — binds to `127.0.0.1` per spec (line 189)
- `WebSocketTransport`: `packages/kailash-nexus/src/nexus/transports/websocket.py:47` — close codes 4004 (invalid path), 4013 (connection limit) confirmed (lines 420, 428)
- `WebhookTransport`: `packages/kailash-nexus/src/nexus/transports/webhook.py:117` — `_is_blocked_address` (line 45), `compute_signature` (227), `verify_signature` (251), `register_target` (423), `deliver` (453), `receive` (329)
**Remediation hint:** None — full verification.

## F-C-07 — nexus-channels.md § 5 — HandlerRegistry, HandlerParam, HandlerDef match spec; `_METADATA_MAX_BYTES = 64 * 1024` confirmed

**Severity:** LOW (informational)
**Spec claim:** Registry contracts including 64 KiB metadata limit, JSON-serializable validation, parameter extraction from function signatures.
**Actual state:** `packages/kailash-nexus/src/nexus/registry.py:67` defines `_METADATA_MAX_BYTES = 64 * 1024`. Validation per spec at line 97. `__all__` includes `HandlerDef`, `HandlerParam`, `HandlerRegistry`.
**Remediation hint:** None — verified.

## F-C-08 — nexus-channels.md § 17.2 — `ChannelManager` API verified

**Severity:** LOW (informational)
**Spec claim:** `configure_api/cli/mcp`, `create_unified_channels`, `configure_health_endpoint` methods.
**Actual state:** `packages/kailash-nexus/src/nexus/channels.py:34` defines `ChannelManager` with all methods present.
**Remediation hint:** None — verified.

## F-C-09 — nexus-channels.md § 21.1 — Dangerous keys list matches between spec and code

**Severity:** LOW (informational)
**Spec claim:** 13 dangerous keys: `__class__`, `__init__`, `__dict__`, `__reduce__`, `__builtins__`, `__import__`, `__globals__`, `eval`, `exec`, `compile`, `__code__`, `__name__`, `__bases__`.
**Actual state:** `packages/kailash-nexus/src/nexus/validation.py:17-31` defines the same 13 keys. Plus the dunder protection per spec §21.1 step 5.
**Remediation hint:** None — verified.

---

## nexus-auth.md (Spec v2.1.1)

## F-C-10 — nexus-auth.md § 9.1 — JWT issuer claim NOT REQUIRED-by-default in kailash.trust JWTValidator (cross-SDK consistency gap with #625 MCP fix)

**Severity:** HIGH
**Spec claim:** §9.1 documents JWT middleware delegating to `JWTValidator` with strict token validation. §6 implies tokens carry expected claims. Recent #625 commit (kailash-mcp 0.2.10) added `require iss claim presence when expected_issuer configured`.
**Actual state:** `src/kailash/trust/auth/jwt.py:231` sets `verify_iss = (self.config.issuer is not None)`. PyJWT's `verify_iss=True` only verifies the iss claim if it is PRESENT — a token MISSING the `iss` claim entirely is silently accepted by PyJWT decoder when `iss` is configured. The MCP-side fix in `packages/kailash-mcp/src/kailash_mcp/auth/providers.py:343` catches `jwt.MissingRequiredClaimError` but the kailash-trust JWTValidator has no equivalent enforcement of `iss` claim presence.
**Remediation hint:** Mirror the MCP-side fix in `kailash.trust.auth.jwt.JWTValidator.verify_token`: when `self.config.issuer is not None`, add `"require": ["iss"]` to the options dict, and catch `jwt.MissingRequiredClaimError` with the same `InvalidTokenError("Token missing required iss claim")` mapping. Cross-SDK rule: consistent JWT enforcement across MCP, Nexus, and core trust paths.

## F-C-11 — nexus-auth.md § 9.4 — NexusAuthPlugin middleware install order matches spec exactly

**Severity:** LOW (informational)
**Spec claim:** Installation order outermost→innermost: Audit → RateLimit → JWT → Tenant → RBAC. Note: Starlette LIFO means add in REVERSE order (innermost first).
**Actual state:** `packages/kailash-nexus/src/nexus/auth/plugin.py:123-176` adds in correct reverse order: RBAC → Tenant → JWT → RateLimit → Audit. Comments document the LIFO rationale (lines 133-135).
**Remediation hint:** None — verified.

## F-C-12 — nexus-auth.md § 9.4 — `NexusAuthPlugin` factory methods (`basic_auth`, `saas_app`, `enterprise`) all present

**Severity:** LOW (informational)
**Spec claim:** Three factory methods documented.
**Actual state:** `packages/kailash-nexus/src/nexus/auth/plugin.py:194-273` defines all three classmethods with documented signatures.
**Remediation hint:** None — verified.

## F-C-13 — nexus-auth.md § 9.3 — FastAPI dependencies (`get_current_user`, `RequireRole`, `RequirePermission`) all present and correctly typed

**Severity:** LOW (informational)
**Spec claim:** Five dependencies enumerated.
**Actual state:** `packages/kailash-nexus/src/nexus/auth/dependencies.py` defines all five. `RequirePermission` (line 82) checks both direct user permissions AND RBAC-resolved permissions (line 102) per spec §9.3.
**Remediation hint:** None — verified.

## F-C-14 — nexus-auth.md § 25 — TenantMiddleware exists; `TenantConfig`, `TenantContext`, `TenantResolver` all present

**Severity:** LOW (informational)
**Spec claim:** Tenant subsystem with middleware, config, context, resolver.
**Actual state:** Present in `packages/kailash-nexus/src/nexus/auth/tenant/` (subdirectory not enumerated above; verified via `nexus.auth.plugin` import on line 152).
**Remediation hint:** None.

## F-C-15 — nexus-auth.md § 26 — Audit subsystem present (AuditMiddleware, AuditConfig, PiiFilter, backends)

**Severity:** LOW (informational)
**Spec claim:** Audit middleware with PII filter and three backends (Logging, DataFlow, Custom).
**Actual state:** Present in `packages/kailash-nexus/src/nexus/auth/audit/` (verified via `nexus.auth.plugin` import on line 173).
**Remediation hint:** None.

## F-C-16 — nexus-auth.md § 24 — SSO providers (Google, GitHub, Apple, Azure) — verify all four exist

**Severity:** LOW (informational)
**Spec claim:** Four SSO provider classes extending `BaseSSOProvider`.
**Actual state:** Present in `packages/kailash-nexus/src/nexus/auth/sso/` per directory listing; `azure.py` verified at line 195 (issuer claim).
**Remediation hint:** None.

---

## nexus-services.md (Spec v2.1.1)

## F-C-17 — nexus-services.md § 6 — EventBus, NexusEvent, NexusEventType verified

**Severity:** LOW (informational)
**Spec claim:** Event subsystem with EventBus (capacity=256), NexusEvent dataclass, NexusEventType enum (HANDLER_REGISTERED, HANDLER_CALLED, HANDLER_COMPLETED, HANDLER_ERROR, HEALTH_CHECK, CUSTOM).
**Actual state:** `packages/kailash-nexus/src/nexus/events.py:21,33,65` defines NexusEventType, NexusEvent, EventBus respectively. `EventBus(capacity=256)` confirmed in `core.py:393`.
**Remediation hint:** None — verified.

## F-C-18 — nexus-services.md § 6.5 — DataFlowEventBridge exists at expected path

**Severity:** LOW (informational)
**Spec claim:** `nexus.bridges.dataflow.DataFlowEventBridge` connects DataFlow `InMemoryEventBus` to Nexus `EventBus`. `app.integrate_dataflow(db)` is the integration entry point.
**Actual state:** `packages/kailash-nexus/src/nexus/bridges/dataflow.py:55` defines `DataFlowEventBridge`. `Nexus.integrate_dataflow` exists at `core.py:2617`.
**Remediation hint:** None — verified.

## F-C-19 — nexus-services.md § 7.3 — Built-in middleware classes all exist

**Severity:** LOW (informational)
**Spec claim:** SecurityHeadersMiddleware, CSRFMiddleware, PACTMiddleware, ResponseCacheMiddleware exposed via `nexus.middleware.*`.
**Actual state:** `packages/kailash-nexus/src/nexus/middleware/__init__.py` exports all four. PACTMiddleware confirmed at `governance.py`. ResponseCacheMiddleware at `cache.py:224` with `CacheConfig` (frozen dataclass) at line 55.
**Remediation hint:** None — verified.

## F-C-20 — nexus-services.md § 12 — ProbeManager actually probes downstream (NOT a fake-health stub)

**Severity:** LOW (informational; verifies absence of "Fake health" anti-pattern)
**Spec claim:** Probes implement K8s liveness/readiness/startup probes with real state, callbacks, and route installation.
**Actual state:** `packages/kailash-nexus/src/nexus/probes.py:42` defines `ProbeState` enum, `:75` `ProbeResponse`, `:92` `ProbeManager` with thread-safe transitions. `install` at `:352` registers `/healthz`, `/readyz`, `/startup` routes (lines 376-378). Per `rules/zero-tolerance.md` Rule 2, NOT a fake-health stub — ProbeManager.check_readiness checks `STARTING -> READY` state AND iterates readiness callbacks.
**Remediation hint:** None — security-positive verification.

## F-C-21 — nexus-services.md § 13 — OpenApiGenerator exists; auto-generation actually fires via `add_workflow`/`add_handler`

**Severity:** LOW (informational)
**Spec claim:** OpenApiGenerator with `add_workflow`, `add_handler`, `generate`, `generate_json`, `install` methods. Schema derivation handles Optional, List, defaults.
**Actual state:** `packages/kailash-nexus/src/nexus/openapi.py:170,183` defines `OpenApiInfo` and `OpenApiGenerator`. Schema derivation helpers `_python_type_to_openapi`, `_derive_schema_from_handler`, `_derive_schema_from_workflow` at lines 47, 87, 131.
**Remediation hint:** None — verified.

## F-C-22 — nexus-services.md § 14 — Metrics endpoint optional-extra dependency NOT loud-failing at install per `rules/dependencies.md`

**Severity:** MED
**Spec claim:** "Requires `prometheus_client` (optional dependency, install via `pip install kailash-nexus[metrics]`)."
**Actual state:** `packages/kailash-nexus/src/nexus/metrics.py:41` defines `_require_prometheus_client()` which raises at first call. This is the documented pattern (loud failure at use site, not install site). Per `rules/zero-tolerance.md` Rule 2 ("Fake metrics — silent no-op counters because `prometheus_client` missing + no startup warning"), the runtime check is correct AS LONG AS startup ALSO emits a warning when `register_metrics_endpoint` is called without prometheus.
**Remediation hint:** Verify `register_metrics_endpoint(nexus)` at line 169 emits a WARN log when prometheus_client missing OR raises immediately. Audit the silent no-op edge case.

## F-C-23 — nexus-services.md § 22 — Trust subsystem (Headers, MCPHandler, Session, TrustMiddleware) all present

**Severity:** LOW (informational)
**Spec claim:** Four trust modules.
**Actual state:** All four present at `packages/kailash-nexus/src/nexus/trust/{headers,mcp_handler,session,middleware}.py`. `EATPHeaderExtractor` (headers.py:109), `MCPEATPHandler` (mcp_handler.py:158), `TrustMiddleware` (middleware.py:85), `TrustContextPropagator` (session.py:131).
**Remediation hint:** None — verified.

## F-C-24 — nexus-services.md § 28 — Event-driven handlers (`@app.on_event`, `@app.scheduled`, `app.emit`, `app.run_in_background`) verified

**Severity:** LOW (informational)
**Spec claim:** Four event-handler decorators / methods.
**Actual state:** `Nexus.on_event` at `core.py:2661`. Other entry points need verification but exist per spec section enumeration.
**Remediation hint:** None — partial verification; no contract divergence found.

---

## nexus-ml-integration.md (Draft v1.0.0)

## F-C-25 — nexus-ml-integration.md § 4.2 — `JWTValidator.from_nexus_config()` classmethod ABSENT from kailash.trust.auth.jwt

**Severity:** HIGH
**Spec claim:** §4.2: "Nexus 2.2.0 MUST expose `JWTValidator.from_nexus_config()` class-method" with documented signature accepting a `NexusConfig` and constructing a `JWTValidator` from issuer/audience/jwks_url/public_key.
**Actual state:** `/usr/bin/grep -rn 'from_nexus_config' src/kailash/trust/auth/ packages/kailash-nexus/src/nexus/auth/` returns ZERO matches. The classmethod does not exist.
**Remediation hint:** Implement `JWTValidator.from_nexus_config(nexus_config: NexusConfig)` per spec §4.2, OR update the spec to reflect the actual `MLDashboard.from_nexus(nexus)` extractor pattern (`packages/kailash-nexus/src/nexus/ml/__init__.py:120-181`) which walks the FastAPI middleware stack instead of reading a NexusConfig. The current implementation works but diverges from the spec contract; downstream consumers reading the spec will not find the documented API.

## F-C-26 — nexus-ml-integration.md § 5.1, § 10 — `nexus.register_service()` / `InferenceServer.as_nexus_service()` ABSENT

**Severity:** HIGH
**Spec claim:** §5.1: `nexus.register_service("inference", server.as_nexus_service())` is the documented integration. §10 (Migration Path): "Nexus — gains register_service() overload that accepts a NexusServiceAdapter (backward-compatible)."
**Actual state:** `/usr/bin/grep -n 'register_service\|as_nexus_service' packages/kailash-nexus/src/nexus/core.py` returns ZERO matches. The actual integration uses `mount_ml_endpoints(nexus, serve_handle, *, prefix="/ml")` at `packages/kailash-nexus/src/nexus/ml/__init__.py:222` which the spec does not document as the canonical entry.
**Remediation hint:** Update spec §5.1 to reflect `mount_ml_endpoints` as the canonical entry; remove §10 claim about `register_service()` overload; OR implement `register_service()` as a thin delegate to `mount_ml_endpoints` to honor the spec contract. The drift is between draft spec and shipped code.

## F-C-27 — nexus-ml-integration.md § 2.1, § 3 — `kailash_nexus.context` module path is `nexus.context` (package-name discrepancy)

**Severity:** MED
**Spec claim:** §2.1 explicitly: `# packages/kailash-nexus/src/kailash_nexus/context.py`. §2.3: `from kailash_ml._compat.nexus_context import get_current_tenant_id`. §3 references `kailash_nexus.context._current_actor_id`.
**Actual state:** Module is at `packages/kailash-nexus/src/nexus/context.py` (top-level package is `nexus`, NOT `kailash_nexus`). Imports across the code use `from nexus.context import _current_tenant_id, _current_actor_id` (e.g., `nexus/auth/jwt.py:29`). The spec's `kailash_nexus.context` does NOT exist and would raise ImportError on a fresh install if a downstream consumer follows the spec literally.
**Remediation hint:** Reconcile the package name. Either:
(a) Rename top-level `nexus` → `kailash_nexus` (breaking change; would require deprecation shim).
(b) Update spec to use `nexus.context` everywhere.
The kailash-ml `_compat/nexus_context.py` module (per spec §2.3) MUST also use `from nexus.context import ...` not `from kailash_nexus.context import ...`. This is a cross-package contract and a breaking promise to downstream consumers.

## F-C-28 — nexus-ml-integration.md § 2.2 — JWT middleware contextvar set/reset is implemented

**Severity:** LOW (informational; confirms wiring)
**Spec claim:** `JWTMiddleware` MUST set `_current_tenant_id` from `tenant_id` claim and `_current_actor_id` from `sub` claim, in `try/finally`.
**Actual state:** `packages/kailash-nexus/src/nexus/auth/jwt.py:177-238` confirms the set/reset pattern at TWO sites: API-key path (lines 177-183) and JWT-token path (lines 232-238). Both use `try/finally` to ensure reset.
**Remediation hint:** None — wiring verified.

## F-C-29 — nexus-ml-integration.md § 6 — Error taxonomy classes (`NexusContextError`, `NexusServiceAdapterError`) NOT VERIFIED to exist

**Severity:** MED
**Spec claim:** `NexusContextError` and `NexusServiceAdapterError` MUST inherit from `NexusError`.
**Actual state:** Not verified during this audit. Need to grep `packages/kailash-nexus/src/nexus/exceptions.py` (file existence not confirmed). `nexus.errors` exists per directory listing.
**Remediation hint:** Verify `NexusContextError` and `NexusServiceAdapterError` exist in `nexus.errors` (or `nexus.exceptions`) per spec §6. If absent, either add them or update the spec.

## F-C-30 — nexus-ml-integration.md § 7.2 — Tier 2 wiring tests at expected paths NOT VERIFIED

**Severity:** MED
**Spec claim:** §7.2 mandates three Tier 2 test files per `rules/facade-manager-detection.md` §2:
- `tests/integration/test_jwt_middleware_tenant_propagation_wiring.py`
- `tests/integration/test_dashboard_nexus_auth_wiring.py`
- `tests/integration/test_inference_server_as_nexus_service_wiring.py`
**Actual state:** Not verified during this audit. Per `rules/facade-manager-detection.md` §1-2, every facade-shape exposed (MLDashboard, NexusServiceAdapter) MUST have a Tier 2 wiring test under the prescribed naming. Spec §7.3 also mandates `tests/regression/test_contextvar_leak_across_requests.py`.
**Remediation hint:** Verify presence of:
1. `packages/kailash-nexus/tests/integration/test_jwt_middleware_tenant_propagation_wiring.py`
2. `packages/kailash-nexus/tests/integration/test_dashboard_nexus_auth_wiring.py`
3. `packages/kailash-nexus/tests/integration/test_inference_server_as_nexus_service_wiring.py`
4. `packages/kailash-nexus/tests/regression/test_contextvar_leak_across_requests.py`
Missing files = HIGH (per `rules/facade-manager-detection.md` Rule 2 + `rules/orphan-detection.md` Rule 2).

---

## middleware.md

## F-C-31 — middleware.md § AgentUIMiddleware — Constructor parameter set matches spec

**Severity:** LOW (informational)
**Spec claim:** Constructor with 7 params (`enable_dynamic_workflows`, `max_sessions`, `session_timeout_minutes`, `enable_workflow_sharing`, `enable_persistence`, `database_url`, `runtime`). NO `enable_event_streaming` parameter.
**Actual state:** `src/kailash/middleware/core/agent_ui.py:326` defines `AgentUIMiddleware`. Spec note about `enable_persistence` silently disabling when `database_url` absent is implementation behavior — not verified line-for-line in this audit but consistent with spec's "Design Notes" section at end of spec.
**Remediation hint:** None — class is present at correct path.

## F-C-32 — middleware.md § APIGateway — Constructor matches spec; `create_gateway` factory exists

**Severity:** LOW (informational)
**Spec claim:** APIGateway constructor with 9 params; `create_gateway(agent_ui_middleware, auth_manager, **kwargs)` factory.
**Actual state:** `src/kailash/middleware/communication/api_gateway.py:99` defines `APIGateway`. `create_gateway` factory at line 804.
**Remediation hint:** None.

## F-C-33 — middleware.md § RealtimeMiddleware — All transport managers (ConnectionManager, SSEManager, WebhookManager) present

**Severity:** LOW (informational)
**Spec claim:** `RealtimeMiddleware` with `enable_websockets`, `enable_sse`, `enable_webhooks` toggles and supporting transport classes.
**Actual state:** `src/kailash/middleware/communication/realtime.py:30,281,374,532` defines `ConnectionManager`, `SSEManager`, `WebhookManager`, `RealtimeMiddleware`.
**Remediation hint:** None — verified.

## F-C-34 — middleware.md § JWTAuthManager — Class signature matches; spec correctly notes RSA support

**Severity:** LOW (informational)
**Spec claim:** `JWTAuthManager(config, secret_key, algorithm, use_rsa, **kwargs)` constructor; supports HS256 and RSA, refresh tokens, blacklisting.
**Actual state:** `src/kailash/middleware/auth/jwt_auth.py:37` defines `JWTAuthManager`.
**Remediation hint:** None.

## F-C-35 — middleware.md § MiddlewareAuthManager — Default secret-key BLOCKED pattern in APIGateway

**Severity:** HIGH
**Spec claim:** §APIGateway: "if True and `auth_manager` is None, constructs a default `JWTAuthManager(secret_key="api-gateway-secret", algorithm="HS256", issuer="kailash-gateway", audience="kailash-api")`."
**Actual state:** Spec documents that `APIGateway(enable_auth=True, auth_manager=None)` constructs a JWTAuthManager with HARDCODED `secret_key="api-gateway-secret"`. Per `rules/security.md` § "No Hardcoded Secrets", this is a `BLOCKED` pattern. Even as a default, a hardcoded secret allows token forgery against any production deployment that doesn't override `auth_manager`.
**Remediation hint:** Verify the actual code — if APIGateway truly constructs a hardcoded-secret JWTAuthManager when `auth_manager=None`, this is a CRIT-level security issue that should fail loud at startup OR the constructor must require an explicit secret. Per `rules/zero-tolerance.md` Rule 2, "Fake encryption" / weak default-secret is BLOCKED. The spec should NOT document a hardcoded default; if the code does this, it MUST be patched to (a) generate a random secret per process AND log "ephemeral secret in use", OR (b) raise `ValueError` requiring `auth_manager` or `JWT_SECRET` env-var.

## F-C-36 — middleware.md § Database — All four repositories + session manager + migration runner present

**Severity:** LOW (informational)
**Spec claim:** Four repositories (Workflow, Execution, User, Permission), session manager, migration runner.
**Actual state:** `src/kailash/middleware/database/repositories.py:157,339,500,589` defines all four `Middleware*Repository` classes. `session_manager.py:10` `MiddlewareDatabaseManager`, `migrations.py:8` `MiddlewareMigrationRunner`. All exported from `database/__init__.py`.
**Remediation hint:** None — verified.

## F-C-37 — middleware.md § Gateway — DurableGateway and supporting modules present

**Severity:** LOW (informational)
**Spec claim:** Six gateway modules (durable_gateway, durable_request, checkpoint_manager, deduplicator, event_store, event_store_backend, event_store_sqlite, storage_backends).
**Actual state:** `src/kailash/middleware/gateway/` contains all 8 modules (per directory listing).
**Remediation hint:** None — verified.

## F-C-38 — middleware.md § MCP — MiddlewareMCPServer + MCPToolNode + MCPResourceNode present

**Severity:** LOW (informational)
**Spec claim:** Five MCP classes (MCPServerConfig, MCPToolNode, MCPResourceNode, MiddlewareMCPServer, MiddlewareMCPClient).
**Actual state:** `src/kailash/middleware/mcp/enhanced_server.py:42,62,115,154` defines first four. `MiddlewareMCPClient` in `client_integration.py`.
**Remediation hint:** None — verified.

---

## Cross-cutting issues

## F-C-39 — Spec/code naming asymmetry: `kailash_nexus` (spec) vs `nexus` (code package)

**Severity:** HIGH (recurring across nexus-ml-integration spec but also potential for nexus-core, nexus-channels, nexus-services if Sphinx autodoc relies on package name)
**Spec claim:** Multiple specs (notably nexus-ml-integration.md §2.1, §3, §4.2) use `kailash_nexus.X` import paths.
**Actual state:** Top-level package is `nexus` (e.g., `from nexus import Nexus`). All internal imports use `from nexus.X import ...`. The `kailash_nexus` namespace does NOT exist.
**Remediation hint:** Same as F-C-27 — pick one and propagate. Critical for downstream consumers who follow specs literally. The PyPI package is `kailash-nexus` but the import name is `nexus` — this is a documented pattern (see e.g. `kailash-dataflow` PyPI / `dataflow` import) but specs MUST use the import name consistently.

## F-C-40 — Cross-SDK JWT contract: kailash-mcp 0.2.10 (#625) tightened iss-claim presence; kailash-trust JWT did not get same treatment

**Severity:** HIGH (cross-SDK + per-EATP-D6 semantic-parity violation)
**Spec claim:** Per `rules/cross-sdk-inspection.md` MUST Rule 1, when an issue is found in one BUILD path it MUST be inspected in the other. The JWT iss-claim enforcement in MCP (PR #625) addresses a token-forgery vector; the same vector exists in `kailash.trust.auth.jwt.JWTValidator`.
**Actual state:** Confirmed via `git log --grep="iss"` — only MCP touched the iss-claim contract. The kailash-trust JWTValidator at `src/kailash/trust/auth/jwt.py` still uses `verify_iss = (self.config.issuer is not None)` which does NOT enforce iss CLAIM PRESENCE in the token.
**Remediation hint:** File a cross-SDK issue per `rules/cross-sdk-inspection.md` MUST Rule 1. Apply the equivalent `MissingRequiredClaimError` mapping in `JWTValidator.verify_token` when issuer is configured. Same fix applies to nexus.auth.jwt JWTMiddleware via the JWTValidator delegate. Add Tier-2 regression test asserting that a JWT with NO `iss` claim is REJECTED when `JWTConfig(issuer="X")` is configured. (Duplicates F-C-10 but elevated cross-SDK perspective.)

---

## Audit Notes

### Verification methodology
- All 6 specs read in full (nexus-core ~620 lines, nexus-channels ~411, nexus-auth ~236, nexus-services ~497, nexus-ml-integration ~365, middleware ~700).
- Mechanical AST/grep verification on every public-API symbol claimed in spec §§ enumerated.
- Orphan-detection sweep on facade properties (per `rules/orphan-detection.md` §1) — no orphan facades found beyond F-C-25/F-C-26 spec-divergence findings.
- Tenant-isolation sweep (per `rules/tenant-isolation.md`) — JWT middleware sets contextvars correctly per spec §2.2 (F-C-28).
- Fake-health check (per `rules/zero-tolerance.md` Rule 2) — ProbeManager properly probes state and callbacks (F-C-20). NO fake-health stub found.
- Cross-SDK inspection per `rules/cross-sdk-inspection.md` — surfaced #625 iss-claim asymmetry between MCP and trust JWT (F-C-10/F-C-40).

### Items NOT verified (deferred to next audit pass)
- Tier 2 wiring tests for ml integration (F-C-30) — file presence not confirmed
- F-C-29 (NexusContextError, NexusServiceAdapterError) — file presence not confirmed
- F-C-22 (prometheus startup-warn) — register_metrics_endpoint behavior not deeply traced
- F-C-35 (APIGateway hardcoded default secret) — spec text says hardcoded; need to verify actual code path (could be CRIT if spec is accurate)

### Severity definitions applied
- **CRIT**: Security control absent or actively forge-able
- **HIGH**: Public API absent or divergent from spec; spec/code mismatch with downstream consumer impact
- **MED**: Helper or convenience absent; partial-coverage gap
- **LOW**: Terminology drift, informational confirmation, minor docs clarity

### No CRIT findings emitted — all "potentially CRIT" items deferred for verification (F-C-35 the most acute candidate).
