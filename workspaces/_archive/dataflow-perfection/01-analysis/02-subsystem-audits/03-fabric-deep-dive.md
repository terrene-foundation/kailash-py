# Fabric Subsystem — Second-Pass Audit

## Preface

The first pass (`workspaces/issue-354/`) drilled into `pipeline.py` and `runtime.py:211-214` to enumerate the eight cache-related stubs/lies, the two `redis_url` wiring breaks, and the latent multi-tenant data-leak primitive in `_cache_key`. That ground is owned and not re-derived here. This second pass walks every other file under `packages/kailash-dataflow/src/dataflow/fabric/` (19 modules, ~5,750 LOC) and surfaces the rest of the iceberg: orphan classes, dead config fields, unwired endpoint surfaces, dormant background workers, security blind spots in webhook ingress, the `tenant_extractor` decorative-only flag, and the `cache_miss` strategy that exists only as input validation. By far the largest pattern this pass uncovers is **endpoint orphancy**: every fabric HTTP-shaped class (serving, health, sse, mcp_integration, webhooks) emits handlers but **no module in the whole package wires those handlers to a server** — fabric's "auto-generated REST endpoints" are dead code from the perspective of `db.start()`.

## Inherited from first pass (baseline)

These are owned by `workspaces/issue-354/` and not re-analyzed here. Listed for completeness so the master plan does not double-count:

- **CRITICAL** — `pipeline.py` Redis cache backend missing; eight stubs/lies in one file (`pipeline.py:8, 137, 140, 152, 154, 173, 175, 227, 581`).
- **CRITICAL** — `DataFlow.__init__(redis_url=...)` does not assign `self._redis_url`; `engine.py:2018` reads a never-set field; fabric layer never sees the kwarg.
- **CRITICAL** — `_cache_key(product_name, params)` has no tenant dimension despite `multi_tenant` contract (data-leak primitive).
- **HIGH** — `WebhookReceiver(redis_client=None)` at `runtime.py:211-214` — Redis nonce backend never receives a client.
- **HIGH** — `InMemoryDebouncer` defined at `pipeline.py:581` with zero instantiations.
- **HIGH** — `self._queue` (`pipeline.py:173`) only consumer is the dormant fallback at `change_detector.py:274-296`.
- **HIGH** — `_get_products_cache` walks every product with no tenant arg; serving.py + runtime.py call sites are tenant-blind.
- **HIGH** — leader-side warm-cache on election is missing (impact-verse crash-loop guard).
- **MEDIUM** — `dev_mode` accepted but inert across pipeline (every backend is in-memory regardless).
- **MEDIUM** — observability gap on `get_cached`/`set_cached` (no `mode=`, `cache_hit`, `backend=` log fields).

## New CRITICAL findings

### F-C1. The entire fabric serving stack is unwired — auto-generated routes have no caller

`FabricRuntime.start()` instantiates `FabricServingLayer` at `runtime.py:217-225`, hands it sources/products/express/consumer_registry, and stores the result on `self._serving`. **Nothing else in the dataflow package ever calls `serving.get_routes()` to actually register the routes with an HTTP server.** Grep for `serving.get_routes` across `src/dataflow/`: a single hit in `mcp_integration.py:148`, which uses it only to bridge an MCP tool call to a route handler. There is no `nexus.add_route(...)`, `app.register(...)`, `gateway.mount(...)`, or any other path that turns those route dicts into a live HTTP endpoint.

Same story for the health endpoints. `health.py` defines `get_health_handler()` and `get_trace_handler()` returning `{"method": "GET", "path": "/fabric/_health", "handler": ...}` dicts, but `runtime.py:603-609` only ever instantiates `FabricHealthManager` to serve the **programmatic** `last_trace(name)` API (in-process Python call). The HTTP-shaped handlers are never returned to any caller.

`sse.py` `SSEManager.get_sse_handler()` is in the same state: defined, returns a route dict, never called from any FabricRuntime path. `SSEManager` itself is never instantiated by FabricRuntime — `FabricRuntime` has no `_sse` field, no `broadcast_product_updated()` call, no SSE wiring at all. Every `product_updated` cache write is documented to "broadcast" via SSE, but the broadcast bus has no producer and no consumer.

`mcp_integration.register_with_mcp()` exists, but `FabricRuntime.start()` never calls it. `FabricRuntime.get_mcp_tools()` returns the tool list but does not actually register them with anything. The MCP integration is opt-in by an external user calling `register_with_mcp(db.fabric_runtime, mcp_server)` — and the docstring documentation never tells the user to do that.

**Net effect**: a user who calls `db.start()` and then expects `GET /fabric/dashboard` to work (per the README and per `fabric_reference/app.py`) gets a 404. The serving layer is constructed, the routes are generated, and they go nowhere. The entire `serving.py` (512 LOC), `health.py` (236 LOC), `sse.py` (147 LOC), and `mcp_integration.py` (194 LOC) are inert. **This is the largest stub in the fabric module, larger than the redis_url one — the difference is that there is no caller filing an issue because no one has ever run the codepath.** Failure mode: silent. Fix surface: every framework integration (Nexus, FastAPI, Flask, Starlette) needs an explicit "mount fabric routes" path, and `FabricRuntime.start()` needs to call it when `nexus=...` is provided.

### F-C2. `tenant_extractor` is dead-stored; no tenant ever flows from request to cache key or context

`runtime.py:73, 85` accepts `tenant_extractor: Optional[Callable]` and stores `self._tenant_extractor = tenant_extractor`. The **only** subsequent read of `self._tenant_extractor` is at `runtime.py:110` inside `_validate_params`, where it checks `if product.multi_tenant and self._tenant_extractor is None: raise ValueError(...)`. After that existence check it is never invoked. No path in the fabric module ever calls `self._tenant_extractor(request)` to actually extract a tenant from a live request. Grep across `src/dataflow/fabric/` for `_tenant_extractor` returns exactly two lines: the assignment and the existence check.

`FabricServingLayer.__init__` (`serving.py:91-107`) does not accept a `tenant_extractor` parameter. `_make_product_handler` (`serving.py:165-368`) builds `PipelineContext(express=..., sources=..., products_cache={})` with no `tenant_id`. `_make_batch_handler` and `_make_write_handler` are the same. Every `PipelineContext` ever constructed inside fabric/ passes `tenant_id=None` (verified across `runtime.py:338, 381, 416` and `serving.py:246, 342, 413`).

This means the runtime-level `_validate_params` raises `ValueError` if a user declares `multi_tenant=True` without supplying a callable, but **the callable is never used**. A user can pass `tenant_extractor=lambda req: req.headers["X-Tenant-Id"]` and the function is never called. The "validation" is a stub guarding an unimplemented code path.

Combined with the first-pass tenant-key gap in `_cache_key`, this is **the second leg of the multi-tenant data-leak primitive**: even if Phase 5 of the issue-354 fix plan adds `tenant_id` to `_cache_key`, the cache key receives `None` from every call site because the runtime never extracts a tenant from any request. Tenant isolation is unimplementable without rewriting `_make_product_handler` to invoke the extractor and propagate the result. **The first-pass plan must be expanded to include the entire tenant_id propagation chain across runtime → serving → context → pipeline → cache backend.**

### F-C3. `WebhookReceiver.handle_webhook` is never invoked; webhook ingress is not wired to any HTTP path

`runtime.py:211-214` instantiates `WebhookReceiver` and stores it on `self._webhook_receiver`. There is a `webhook_receiver` property at `runtime.py:633-635` that returns it. There is no other call site. Grep across `src/dataflow/` for `handle_webhook`: only the definition in `webhooks.py:196`. No HTTP route handler in fabric or anywhere else in the package calls `await receiver.handle_webhook(source_name, headers, body)`.

This compounds the first-pass `redis_client=None` finding. Even if the next PR fixes the missing redis_client, the receiver is **already** unreachable. A user who declares a `WebhookConfig(path="/hooks/github", secret_env="...")` on a source gets the path stored on `self._webhooks` but never hooked up to a server. The `RestSourceConfig.webhook` field is documented as "Webhook configuration for push-based sources" — push delivery never happens because there is no listener.

### F-C4. `webhooks.py` does not implement any of the webhook formats it claims to support

`webhooks.py` validates a single bespoke header set: `x-webhook-signature` (HMAC-SHA256 hex), `x-webhook-timestamp`, `x-webhook-delivery-id`. None of GitHub's `x-hub-signature-256: sha256=…`, GitLab's `x-gitlab-token`, Stripe's `stripe-signature: t=…,v1=…`, or Slack's `x-slack-signature` / `x-slack-request-timestamp`. The first-pass brief explicitly named GitHub/GitLab/Stripe/Slack as expected sources; the implementation supports none of them. Any third-party webhook will fail HMAC validation regardless of secret, because the signature header is missing or formatted differently.

The HMAC algorithm is hardcoded to `hashlib.sha256` (`webhooks.py:237`) — no SHA-1 support for legacy sources, no algorithm negotiation. The body-encoding strategy (`secret.encode("utf-8")` then `hmac.new(secret, body, ...)`) is correct for GitHub-style verification, but the header lookup is wrong, so even if a user manually maps `x-hub-signature-256` to `x-webhook-signature` they hit the algorithm prefix problem (`sha256=…` prefix not stripped).

Severity: CRITICAL. A user reading the docstring "Webhook Receiver — push-based source change detection" cannot integrate any real webhook source. Combined with F-C3, the entire webhook subsystem is double-broken: broken implementation behind a broken router.

## New HIGH findings

### F-H1. `cache_miss` strategy field is validated, stored, and never read

`products.py:75, 93, 115, 159-165, 193` defines, validates, and stores `cache_miss: str = "timeout"` with valid values `"timeout" | "async_202" | "inline"`. Grep across `src/dataflow/fabric/` for `cache_miss` outside `products.py`: zero results. Neither `pipeline.py` nor `serving.py` reads `product.cache_miss` to dispatch the documented strategies. `serving.py:325-365` always returns 202 for cold materialized products, always returns the 404-style empty for cold parameterized products, always inline-executes for virtual. The three strategies are aliases for the same behavior — there is no actual switch on the field.

This is a `dataflow-pool.md` Rule 3 violation ("flag set with no consumer is a stub"). Either implement the three strategies or delete the field and the validation.

### F-H2. `rate_limit.max_requests` is documented as "Request throttling configuration" but never enforced

`config.py:179` defines `RateLimit.max_requests = 100` and the docstring is "per client per minute". Grep for `max_requests` across `src/dataflow/fabric/`: only the definition. `serving.py:230` reads `product.rate_limit.max_unique_params` to clamp `limit`, which is itself a misuse — `max_unique_params` is documented as "max distinct parameter combos cached", not as a query-result limit. `max_requests` is never honored anywhere; there is no rate-limit middleware in fabric, no token bucket, no per-client tracking. The fabric product surface is unthrottled by design.

Either wire to a token-bucket store (Redis recommended for cross-replica) or delete `RateLimit.max_requests` and update the docstring.

### F-H3. `RestSourceConfig.circuit_breaker` is plumbed into the dataclass but `RestSourceAdapter` does not pass it through

`config.py:210` declares `BaseSourceConfig.circuit_breaker: CircuitBreakerConfig`. Grep for `super().__init__(name, circuit_breaker=config.circuit_breaker)` across `src/dataflow/adapters/`: present in `database_source_adapter.py:50`, `cloud_adapter.py:31`, `stream_adapter.py:29`. **Absent in `rest_adapter.py` and `file_adapter.py`** — both ignore the per-source `circuit_breaker` field and use whatever default `BaseSourceAdapter` constructs. Every REST source in the fabric runs with the framework default circuit breaker, not the one declared on its config. Configuration drift, silently.

### F-H4. Fabric scheduler is constructed only by docstring example; never instantiated by `FabricRuntime`

`scheduler.py:47` defines `FabricScheduler` with `start()`, `stop()`, supervised tasks, croniter integration, and clock-drift cap. `runtime.py` does not import scheduler at all. Grep for `from dataflow.fabric.scheduler import` across `src/`: zero matches. Grep for `FabricScheduler(` across `src/`: zero matches outside the scheduler's own usage example. `ProductRegistration.schedule` is accepted at registration time and validated against `croniter`, but no class ever reads it to schedule a refresh.

Severity HIGH because `products.py:51, 70, 110` documents the field as "Optional cron expression for time-based refresh" — the entire promise is unbacked. A user declaring `@db.product("hourly", schedule="0 * * * *")` will see the cron expression validated at registration and then **never executed**. The product refreshes only via change-detector polling or model-write events, not on the cron clock.

### F-H5. `FabricMetrics` class is defined, exported, and never instantiated

`metrics.py:43` defines `FabricMetrics` with `record_pipeline_run()`, `record_cache_hit()`, `record_cache_miss()`, etc. Grep for `FabricMetrics(` across `src/dataflow/`: only the test file at `tests/unit/fabric/test_metrics.py`. `FabricRuntime` has no `self._metrics`, `pipeline.py` does not import metrics, `serving.py` does not import metrics, `health.py` does not import metrics. Every `record_*` method is dead code from the perspective of the production code path. Prometheus scraping returns zero data points for `fabric_*` metrics under any scrape configuration, even when `prometheus_client` is installed.

This compounds with the first-pass observability gap: not only is there no `mode=` field on cache log lines, the metric collection scaffolding **exists in code but is bypassed**. The `record_cache_hit()` / `record_cache_miss()` calls expected by `dataflow-pool.md` Rule 3 are missing at every site that should emit them.

### F-H6. `serving.py` write endpoints bypass DataFlow write lifecycle (transactional and audit guarantees lost)

`_make_write_handler` (`serving.py:438-512`) routes a write directly to `self._express.create/update/delete(...)`. This is the express path and it works, but the handler bypasses several DataFlow features that fabric users would expect:

- No `WriteContext` / transaction wrapping; bulk semantics impossible.
- No DataFlow event-bus emission (it relies on the `_express.create` path firing `model.created`, which is fine, but the fabric `_on_product_refresh` callback then re-fires the same event chain via a different code path, double-triggering refresh on every write).
- Source writes via `adapter.write(path, data)` have **no allowlist** — any source registered in `self._sources` becomes a writable target if `enable_writes=True`. A user enabling fabric writes for one source implicitly enables them for all sources that implement `supports_feature("write")`. The `RestSourceAdapter`'s `write()` is a backdoor to any URL the source is configured to talk to.

The first-pass plan covered `enable_writes` validation as a `runtime.py:_validate_params` warning, but the actual handler does not enforce per-target authorization. Combined with `host="0.0.0.0"` warning being just a log line (not a refusal), a misconfigured production deployment turns the fabric serving layer into an unauthenticated write proxy.

### F-H7. `_BoundedNonceSet` legacy alias in `webhooks.py` runs `asyncio.run(...)` from sync wrapper

`webhooks.py:112-153` defines `_BoundedNonceSet` "kept for backward compatibility". Its sync `contains` and `add` methods detect the running loop and **call `asyncio.run()` if no loop is running**. This is an explicit anti-pattern: nesting `asyncio.run` from inside potentially-async test code corrupts the loop, and the inner branch that pokes `self._backend._store` directly bypasses the LRU bookkeeping. The class exists only to keep `tests/unit/fabric/test_webhooks.py:141, 147` passing — i.e., production code carries a 41-line backward-compat shim for two test cases. **Delete `_BoundedNonceSet` and update the tests to use `_InMemoryNonceBackend` directly with `pytest.mark.asyncio`.**

### F-H8. `change_detector.py` accepts `pipeline_executor: Any` and uses it only as a queue carrier

`change_detector.py:60` parameter type is `Any`. The constructor stores it as `self._pipeline_executor` and the only read is `getattr(self._pipeline_executor, "_queue", None)` at line 275. No method on `PipelineExecutor` is called. The type annotation should be `Optional[asyncio.Queue]` (or the queue should be passed directly), making the dead-by-accident dependency explicit. Otherwise the code reads as if it has a live coupling to the executor, when in reality the executor is only present so the change detector can dig into a private attribute.

This is the same `_queue` ghost the first pass flagged but viewed from the producer side: the change detector holds a reference to the entire pipeline executor for the sole purpose of `getattr`-ing into a private field. Atomic deletion (per first-pass red-team finding N1) must remove the parameter as well, not just the queue.

### F-H9. `LeaderElector` retries election forever in heartbeat loop with no jitter or back-off

`leader.py:192-219` `_heartbeat_loop` does the following on every tick: if `self._is_leader` is True, renew; if False, **try to acquire**. The retry is unconditional — there is no exponential back-off, no jitter, no maximum retry count. With N=10 followers all running `_heartbeat_loop` every 10 seconds, the SETNX traffic on the leader key is `N requests per heartbeat_interval` continuously. The leader key has TTL=30s; the renew tick is 10s. The thundering-herd window after a leader death is up to 10 seconds where all followers race on a single key with no jitter — N concurrent SETNX, only one wins, the rest spin until the next tick.

Failure mode: under network partition healing, all replicas re-acquire simultaneously. With Redis cluster failover, the followers can briefly all believe they are leader (split-brain) because they each saw their own SETNX succeed against a stale primary. There is **no fencing token** (no leader epoch, no monotonic counter). Two leaders running prewarm or pipeline execution in parallel produce duplicate writes. The cache CAS the first-pass plan adds (Phase 4.5) protects the cache layer, but does not prevent two leaders from running source-side mutations (webhook callbacks, external POSTs).

Severity HIGH because the leader-election guarantees are weaker than the docstring claims ("single-leader coordination").

### F-H10. `LeaderElector.start_heartbeat` swallows the heartbeat task; the task is never awaited

`leader.py:188-190` creates `self._heartbeat_task = asyncio.create_task(...)` and stores it. The task is cancelled in `release()` and that's it. There is no exception propagation: if `_heartbeat_loop` crashes (e.g., the Redis client raises an unrecoverable error), the exception is logged inside the loop's `except Exception` and the loop continues. But if the task is cancelled externally (loop shutdown), `release()` `await`s it via the cancel-and-await pattern, which is fine. The bug is that **`__del__` is missing**: a `LeaderElector` that is garbage-collected without `release()` leaks the heartbeat task and the Redis connection. Combined with `RedisLeaderBackend.close()` being called only when `release()` runs, every test that constructs a `LeaderElector` without an explicit `release()` leaks a Redis client. `rules/patterns.md` "Async Resource Cleanup" mandates `__del__` with `ResourceWarning`.

### F-H11. Fabric runtime `start()` is not idempotent under partial failure

`runtime.py:131-237` `start()` runs nine sequential phases. If phase 4 (`leader.try_elect`) succeeds and phase 5 (`_prewarm_products`) raises mid-product, control returns to the caller without rolling back the leader lock. The next call to `start()` short-circuits at line 144 (`if self._started: ... return`) but `self._started = True` is only set at line 230. So the flag is never set, the next call re-runs everything, and the leader has been holding the lock the whole time (up to TTL=30s). For 30 seconds the failed replica is the leader of a fabric runtime that thinks it is not started.

`_prewarm_products` (lines 317-350) catches `Exception` per product, so individual product failure is tolerated. But `_connect_sources` with `fail_fast=True` raises `ConnectionError` from a _partial_ `gather`: some sources may already have `is_connected=True` when the exception is raised, and `start()` does not call `disconnect()` on them as it unwinds. The `stop()` path is not reachable because `_started = False`. **Resource leak on every failed start.** A correct fix instruments `start()` with a try/finally that calls a `_rollback()` method on partial failure.

### F-H12. `serving.py` `consumer_registry` parameter is decorative when registry is constructed by runtime

`runtime.py:217-225` passes `self._consumer_registry` (the runtime-owned `ConsumerRegistry` instance) to the serving layer. `serving.py:99-107` accepts `consumer_registry: Optional[ConsumerRegistry] = None` and falls back to `ConsumerRegistry()` (a fresh empty one) if `None`. Now look at `health.py` and `mcp_integration.py` — neither of those receives the registry. The `register_with_mcp` flow at `mcp_integration.py:148-153` calls `serving.get_routes()` and finds the right route, so it inherits the runtime-owned registry through the route's closure. But any new fabric module that needs the consumer registry (e.g., a future SSE consumer transform) has no way to access it without going through `runtime.consumer_registry`. The split between "runtime owns the registry" and "serving accepts an optional fallback registry" creates two parallel registries in any test that constructs `FabricServingLayer` directly. Make the parameter required.

## New MEDIUM findings

### F-M1. `config.py` `AuthConfig` base class is empty and not abstract

`config.py:48-52` `AuthConfig` has a `pass` body and no abstract method. It is a marker class with no contract. Subclasses (`BearerAuth`, `ApiKeyAuth`, `OAuth2Auth`, `BasicAuth`) each add their own `get_token()` / `get_key()` / `get_credentials()` method but the base class neither declares nor enforces a common interface. A consumer trying to handle "any auth config" cannot — there is no polymorphic call. `RestSourceConfig.validate()` works around this with `isinstance` checks. Make `AuthConfig` an `ABC` with an `apply_to_request(req: httpx.Request) -> None` method, or mark the four classes with `Protocol` and remove the marker class.

### F-M2. `BaseSourceConfig` has `validate()` but `register_product` and `db.source(...)` flows don't always call it

`config.py:213-217` `BaseSourceConfig.validate()` is overridden in every subclass. Grep for `.validate()` invocations on configs in fabric/: zero matches. The validation runs only when an adapter is constructed and chooses to call `config.validate()`. `RestSourceAdapter` does not enforce validation at construction time (verified by inspection — it would have to call `config.validate()` in `__init__`). The result is that `RestSourceConfig.url = ""` is accepted at registration and only fails at first fetch with a confusing `ValueError` deep in the call stack. `register_product` (`products.py:79-204`) validates the product but does not call `validate()` on the source configs of the products' dependencies.

### F-M3. `mcp_integration._make_mcp_handler` strips `get_` prefix without verifying the route was a GET

`mcp_integration.py:139` does `product_name = tool_name[4:] if tool_name.startswith("get_") else tool_name`. If a future tool prefix changes (`list_`, `query_`), this will silently treat the prefix as part of the product name. The handler then iterates `serving.get_routes()` looking for `path == f"/fabric/{product_name}"` and `method == "GET"`. There is no namespacing — any product whose name happens to start with `get_` produces `tool_name=get_get_dashboard` for the `get_dashboard` tool, which strips back to `get_dashboard`, which is correct. But a product named `getter` produces `get_getter` → `getter` → mismatch with route `/fabric/getter`. Edge case but real.

### F-M4. `health.py` exposes `last_error` from circuit breaker without redacting full message tail

`_sanitize_error` at `health.py:32-42` truncates at 500 chars and strips connection strings via regex. The regex set covers `postgresql://`, `redis://`, `password=`, `token=`, `secret=`. **Missing**: `mongodb://`, `mysql://`, `amqp://`, `kafka://`, AWS credentials (`AWS_SECRET_ACCESS_KEY=...`), JWT tokens (`Bearer ey…`), API keys without an explicit "key=" prefix (e.g., `sk-…`, `pk_live_…`). A REST source whose `last_error` includes the raw response body containing a JWT in JSON gets the JWT exposed via the public health endpoint. Health is documented as `auth: {"roles": ["admin"]}` so it is not entirely public, but the redaction set is too narrow for an admin-public endpoint.

### F-M5. `health.py:85` `get_cached(name)` is sync; the first-pass async-cascade plan must include this file

The first-pass red-team finding N3 listed `health.py:85` as a tenant-blind site. It is also the synchronous-call-must-become-async site that the plan's Phase 5 cascade must touch. `get_health()` at line 60 is itself a sync method (it returns `Dict[str, Any]` directly), but the surrounding handler `get_health_handler()` returns an async closure. Converting `get_cached` to async forces `get_health` to async, which forces `get_health_handler.handler` to await it (which it already does). Cascade is mechanical but must be added to the modified-files list explicitly.

### F-M6. `context.py` `_MockSourceAdapter.fetch_pages` is duplicated in `testing.py.MockSource.fetch_pages` (parallel implementations)

`context.py:632-640` defines `_MockSourceAdapter.fetch_pages` as a chunked-list iterator. `testing.py:149-170` defines `MockSource.fetch_pages` with the same implementation. Two parallel mock sources, two paginators, two test fixtures. `FabricContext.for_testing()` uses `_MockSourceAdapter`; user-facing `MockSource` is the supported one. Pick one. The `_MockSourceAdapter` should be deleted and `for_testing()` should use `MockSource`.

### F-M7. `context.py` `PipelineScopedExpress` does not propagate write events to the read cache invalidation

`context.py:319-452` deduplicates reads within a pipeline run via `(operation, model, filter_json)` key. Writes (`create`, `update`, `delete`, `upsert`) are forwarded directly without invalidating the read cache. So a pipeline that does `list("User") → create("User", {...}) → list("User")` returns the **stale** first-list result for the second call, because the cache key is the same. The class docstring says "snapshot consistency" — that is correct in the sense that _reads_ see a consistent view, but _write-then-read within the same pipeline_ sees the pre-write snapshot. This is the documented contract but it is fragile and is going to bite a user. Either invalidate write-affected models from the read cache, or document the gotcha explicitly with an example.

### F-M8. `webhooks.py` timestamp parsing accepts ISO-8601 with Z suffix but timestamp clock skew window is asymmetric

`webhooks.py:248-272`: max age 300s into the past, but only 60s into the future. A webhook source whose clock is +120s from the receiver clock (NTP drift, typical in distributed systems) produces a "Timestamp is in the future" rejection. The configured `_MAX_TIMESTAMP_AGE_SECONDS = 300` is symmetric on the past side; the future-side `-60` is undocumented and not configurable. Either make both bounds equal or expose them on `WebhookConfig`. Real-world: GitLab timestamps can drift up to 90s in normal operation.

### F-M9. `ssrf.py` `_BLOCKED_NETWORKS` does not block AWS IMDS, GCP metadata, or Azure metadata endpoints by hostname

`ssrf.py:29-39` blocks IP literals in private/reserved ranges, including 169.254.0.0/16 (which catches IMDSv1 by IP). But the IMDS hostname `metadata.google.internal`, `metadata.goog`, `169.254.169.254` (also catchable by literal), and Azure's `169.254.169.254/metadata/instance` resolve via DNS in some configurations. `_check_resolved_addresses` does the right thing for `metadata.google.internal` (it resolves to 169.254.169.254 which is blocked). **But**: `socket.getaddrinfo` is called with default flags, so a hostname that returns multiple A records where some are public and some are private will be blocked only if any A record is private (the loop raises on first match). Good for SSRF defense, but: the function does not pin the resolved address — between validation and actual HTTP request, DNS rebinding can return a different address. The validation is **TOCTOU-vulnerable**. The httpx client follows fresh DNS resolution.

Mitigation: pin the resolved address at validation time and pass it as `transport=httpx.HTTPTransport(local_address=...)` or use `httpx.AsyncClient` with a custom resolver that returns the cached IP. Current implementation has the appearance of SSRF defense without the substance under DNS rebinding.

Also: `socket.gaierror` returns silently (`pass` at line 109). DNS-resolution failure is treated as "allow the request" — the comment says "let the HTTP client produce a clear connection error" but a silent allow on DNS failure is the wrong default for a security boundary. Should raise `SSRFError("Hostname resolution failed during SSRF validation")` instead.

### F-M10. `auth.py` `OAuth2TokenManager` constructs a fresh `httpx.AsyncClient` per refresh

`auth.py:180-185` creates a new `AsyncClient` inside the refresh path and discards it. Every token refresh opens a new TLS session, runs SSRF validation again, and closes the connection. For OAuth tokens with 1-hour TTL this is one extra TLS handshake per hour — fine. For tokens with 5-minute TTL (some APIs) this is wasteful. Lazy-construct one `AsyncClient` per `OAuth2TokenManager` and reuse it across refreshes. Add `aclose()` semantics.

### F-M11. `runtime.py` event-bus subscription silently swallows registration errors

`runtime.py:446-450` `_subscribe_to_events` iterates over event names and calls `self._dataflow.on(event_name, self._on_model_write)` inside a `try/except Exception: logger.debug(...)`. The DEBUG log level means the failure is invisible at INFO level, and there is no return value to indicate "subscribed N out of 5 events". A user whose DataFlow lacks an event bus (older versions, alternative implementations) sees the fabric runtime start successfully, sees no warnings, and the event-bus refresh path silently does nothing. The model-write → product-refresh chain is documented but reliability-zero.

Either log at WARN, or treat the absence of `dataflow.on` as a fatal `RuntimeError`.

### F-M12. `pipeline.py` `_traces` is `Deque[PipelineTrace]` but `health.py:117` and `health.py:181-183` treat it as `Dict` or `Deque` defensively

`pipeline.py:185` declares `self._traces: Deque[PipelineTrace] = deque(maxlen=20)`. `health.py:115-118` does `if isinstance(self._pipeline._traces, dict): for traces in self._pipeline._traces.values(): all_traces.extend(traces)`. Since `_traces` is never a `dict`, that branch is dead. The `isinstance(raw_traces, deque)` branch at `health.py:179-183` is the live path. The dead `dict` branch is presumably a leftover from an earlier per-product trace organization. Delete the dead branch.

Similarly the `traces` field on `PipelineExecutor` is exposed as `@property traces` returning a `list`, but `health.py` reaches into the private `_pipeline._traces` directly. Use the public `traces` property.

## New LOW findings

### F-L1. `__init__.py` exports a small subset of public API; orphan classes (`FabricMetrics`, `SSEManager`, `FabricScheduler`, `OAuth2TokenManager`, `ConsumerRegistry`) are not in `__all__`

`__init__.py:52-75` exports adapters, configs, auth types, and `ConsumerRegistry`. It does not export `FabricRuntime`, `PipelineExecutor`, `LeaderElector`, `WebhookReceiver`, `FabricServingLayer`, `FabricHealthManager`, `FabricMetrics`, `SSEManager`, `FabricScheduler`, `MockSource`. Half of these are intentional (`FabricRuntime` is reached via `db.fabric_runtime`), half are accidental. After F-C1/F-H4/F-H5 are addressed (instantiate the orphans or delete them), the export list should be the single source of truth for what fabric provides.

### F-L2. `pipeline.py:16` imports `time, uuid` at module top but `time.monotonic` is the only use of time and `uuid` is only used in `execute_product`

Code hygiene: nothing wrong, but a future grep for "uuid" in fabric will be misled. Inline imports inside functions reduce surprise.

### F-L3. `metrics.py:128` "fabric metrics disabled" log level is DEBUG; users wondering "why are my fabric\_\* metrics empty" never see it

The disable log line should be INFO or WARN (operator-facing). At DEBUG it is invisible to anyone running default logging.

### F-L4. `scheduler.py:96-101` croniter ImportError raises but the message says "pip install croniter" — should also mention the dataflow extras

`pip install croniter` works but the framework convention is `pip install kailash-dataflow[scheduler]` (or similar). The error message should match the pattern used by `mcp_integration.py:182-185` (`pip install kailash-mcp`).

### F-L5. `serving.py` filter operator allowlist is hard-coded; should be a class-level constant on `FabricServingLayer` so subclasses can extend

`serving.py:43` `ALLOWED_OPERATORS` is module-level. A user wanting to add `$regex` for a single product cannot subclass without monkey-patching the module. Move to a class attribute.

### F-L6. `consumers.py` `ConsumerRegistry.transform` raises `ValueError` for unknown consumer; serving.py:198-205 already returns `400` with a generic message — the registry's error string is dead path-wise

Either delete the registry's error message (return None) or use it (let serving.py propagate the registry's exact error string). Currently both layers compose error messages and the user sees only the serving-layer one.

### F-L7. `context.py:592-640` `_MockSourceAdapter` has `is_connected = True` as an instance assignment instead of going through `BaseSourceAdapter` lifecycle

`context.py:605-606` sets `self._state = SourceState.ACTIVE; self.is_connected = True` directly. If `BaseSourceAdapter` ever adds invariant checks tying `is_connected` to a state machine transition, the mock breaks. Use the public lifecycle.

## Cross-file patterns

### Pattern P1 — "build the API surface, never wire it"

The fabric module emits route dicts, handler closures, MCP tool definitions, SSE managers, metrics collectors, and circuit breakers — and **none of them are connected to a runtime**. `serving.py.get_routes()`, `health.py.get_health_handler()`, `sse.py.get_sse_handler()`, `metrics.py.FabricMetrics()`, `scheduler.py.FabricScheduler()`, `mcp_integration.py.register_with_mcp()` are six independent endpoint surfaces that are collectively orphan. This is not a coincidence — it is the same architectural failure mode as the first-pass `redis_url` stub: the author built the shape of the feature, wrote the docstring as if the feature existed, and shipped without the wiring. Six features in this pattern, all independently broken, all "documented as working".

The fix is structural: every fabric subsystem that provides an HTTP/MCP/SSE/Prometheus surface must be instantiated by `FabricRuntime.start()` and wired to a transport during the same call. The `FabricRuntime` constructor's `nexus: Optional[Any]` parameter (`runtime.py:74`) is the obvious hook — it is currently accepted, stored, and never used. When `nexus is not None`, `start()` should call `nexus.add_route(route_dict)` for every entry in `serving.get_routes() + [health, trace, sse]` and call `register_with_mcp(self, nexus.mcp_server)` if the Nexus instance has one. When `nexus is None`, the routes should be exposed via `runtime.routes` for the user to mount manually, and a WARN log should make the unwired state loud.

### Pattern P2 — "stub configuration with `_validate_params` enforcement"

`runtime.py:106-129` `_validate_params` is the only consumer of three configuration paths:

- `multi_tenant=True` requires `tenant_extractor` (validates existence, never invokes the callable — F-C2).
- `enable_writes=True` without `nexus` warns (logs and continues, no enforcement — F-H6).
- `host="0.0.0.0"` without `nexus` warns (logs and continues, no enforcement).

In all three cases the validation theatre suggests that the parameter is honored, while the actual code path never reads it. The pattern is "validate input as if it would be used; do not use it." This is a `dataflow-pool.md` Rule 3 violation in the plural — one rule, three violations.

### Pattern P3 — "the runtime stores subsystem references that the runtime never reads"

`runtime.py:74-104` declares `self._nexus`, `self._tenant_extractor`, `self._enable_writes`, `self._serving`, `self._webhook_receiver`, `self._health_manager`. Of these:

- `_nexus` is stored, never read.
- `_tenant_extractor` is stored, only read by `_validate_params`.
- `_enable_writes` is stored, read by `_validate_params` and forwarded to `FabricServingLayer.__init__`.
- `_serving` is stored, returned from `serving` property, never used inside `runtime.py`.
- `_webhook_receiver` is stored, returned from `webhook_receiver` property, never used inside `runtime.py`.
- `_health_manager` is **lazy-constructed only inside `last_trace`** and never used for the HTTP `/fabric/_health` path.

The runtime is a bag of fields. There is no main loop, no event dispatch, no orchestration beyond `start()` and `stop()`. The "ties together all fabric subsystems" docstring (`runtime.py:50`) is aspirational — the runtime constructs subsystems and immediately walks away.

### Pattern P4 — "every async resource class is missing `__del__`"

`PipelineExecutor`, `FabricRuntime`, `LeaderElector`, `RedisLeaderBackend`, `WebhookReceiver`, `_RedisNonceBackend`, `OAuth2TokenManager`, `SSEManager`, `FabricScheduler` all hold resources that need cleanup (Redis client, asyncio tasks, async queues, semaphores). None of them implement `__del__` with `ResourceWarning`. `rules/patterns.md` "Async Resource Cleanup" mandates this for all async resource classes. The first-pass plan addresses cleanup of the new `RedisFabricCacheBackend` but does not generalize. Every class in the fabric module that holds an asyncio.Task or asyncio.Queue or aioredis client should grow a `__del__`.

### Pattern P5 — "TODO-N references with no live tracker"

Eight files reference `TODO-N` markers (`TODO-09`, `-10`, `-11`, `-12`, `-18`, `-21`, `-25`, `-27`, `-28`, `-34`, `-35`, `-36`, `-38`). Grep `workspaces/data-fabric-engine/todos/` from this audit's read perspective: the directory exists but the markers are not consistently labeled with status. Several of the references point to "M5-M6 milestones" (`scheduler.py:26`, `auth.py:32`, `testing.py:23`) — milestones that may or may not be tracked. Either delete the markers from the source files (they have no in-source actionable meaning) or add a lint rule that fails if a `TODO-N` reference does not match an open file in `workspaces/data-fabric-engine/todos/active/`.

### Pattern P6 — "circuit breaker config exists; only some adapters honor it"

`config.py:210` declares the field universally. `database_source_adapter`, `cloud_adapter`, `stream_adapter` honor it. `rest_adapter` and `file_adapter` do not (F-H3). This is dialect drift inside the adapter family — a per-adapter convention rather than an enforced contract. The base class should either _require_ `circuit_breaker=config.circuit_breaker` in `super().__init__` (move into a factory method on `BaseSourceConfig`) or use a `__init_subclass__` hook to fail at import time if a subclass doesn't pass it.

## Cross-subsystem couplings

### C-1. Fabric ↔ DataFlow event bus is silent failure

`runtime.py:435-450` calls `self._dataflow.on(event_name, ...)` if the attribute exists. DataFlow's event bus implementation is in `dataflow/core/engine.py` (verify against the master plan), but if the user constructs a `DataFlow` instance from an alternate code path (e.g., a test fixture) that lacks an event bus, the silent fallback means model-write → product-refresh is broken with no signal. The fabric runtime should require event-bus presence as a hard contract, not as a `getattr`.

### C-2. Fabric ↔ Express (`_express_dataflow`) is a `getattr` fallback in three places

`runtime.py:220, 339, 382, 417` and `serving.py:247, 343, 414` all do `getattr(self._dataflow, "_express_dataflow", None)`. The express layer is supposed to be present whenever fabric is active, but every access is defensive. Either declare `_express_dataflow` as a hard requirement on the DataFlow instance the FabricRuntime accepts (constructor type-checks and raises) or document the optional path explicitly. Right now a missing express layer cascades into `None.list(...)` AttributeError deep inside a product function — confusing failure mode.

### C-3. Fabric ↔ MCP integration is a one-way bridge

`mcp_integration.register_with_mcp(fabric_runtime, mcp_server)` is the documented entry. **There is no inverse path** — when an MCP tool list changes (e.g., a new product is added at runtime via `db.product(...)` after `db.start()`), the MCP server is not notified. The product list is captured at registration time and frozen. Add a `re_register_with_mcp` or expose `fabric_runtime.on("product_added", lambda p: mcp_server.register_tool(...))`.

### C-4. Fabric ↔ Nexus serving — `nexus` parameter is purely decorative

`runtime.py:74` accepts `nexus: Optional[Any]`. It is stored and never read except by `_validate_params` (existence check for `enable_writes` and `host="0.0.0.0"`). There is no Nexus integration path. A user passing `nexus=my_nexus_instance` does not get fabric routes mounted on the Nexus app. The Nexus parameter is the obvious hook for fixing F-C1, but it is currently a placeholder.

### C-5. Fabric ↔ DataFlow pool — `_resolve_pool_size` reads `DatabaseConfig.get_pool_size("development")` if config introspection fails

`pipeline.py:194-224` falls through to `DatabaseConfig().get_pool_size("development")` (not the actual environment) on any introspection failure. This means a pool sized for production gets the dev default (5) on the fabric pipeline's DB budget, silently halving DB capacity. The fallback should at minimum read `os.environ.get("ENVIRONMENT", "development")` or refuse to start.

## Cross-SDK (kailash-rs) parallels

The first pass already filed kailash-rs as missing the entire Redis fabric path. The second pass adds the following parallels that should be folded into the same cross-SDK issue or one filed alongside it:

- **F-C1 parallel**: `kailash-rs/crates/kailash-dataflow` likely has the same "build the API surface, never wire it" pattern. Verification: grep for `get_routes` or `serving` definitions in `crates/kailash-dataflow/src/`. The Rust SDK's executor (`executor.rs:32-149`) has no fabric/serving layer at all per the first-pass red team — this is consistent with a "Python is ahead, Rust is empty" pattern, not parity.
- **F-C2 parallel**: tenant_extractor is a Python concept; the Rust equivalent is whatever pattern Rust uses for request-scoped extractors. The cross-SDK issue should call out tenant propagation as a first-class requirement of the Rust fabric port from day one, not a follow-up.
- **F-H4 parallel**: `FabricScheduler` cron-based scheduling is absent in Rust. File as a feature gap.
- **F-H5 parallel**: Prometheus metrics (Rust uses `metrics` crate or `prometheus` crate) — the Rust fabric needs metric collection from day one or it inherits the same orphan-class problem.
- **F-H10 parallel**: Resource cleanup invariants — Rust's `Drop` trait makes this enforceable, but the equivalent in async (`tokio::task::AbortHandle` cleanup, channel close) is easy to miss. Document in the cross-SDK alignment notes.

## Institutional-knowledge gaps

### G-1. The fabric module was built milestone-by-milestone with `TODO-N` markers and no closeout

The TODO-N references in pattern P5 reveal a development style where each milestone added a class file ("TODO-21: metrics", "TODO-23: SSE", "TODO-28: scheduler") **without integration into the runtime**. Each PR landed a self-contained module with its own tests. No PR was responsible for "wire metrics into pipeline" or "wire scheduler into runtime". The milestones closed individually; the integration step was assumed to happen later. It did not. This is the institutional-knowledge fault line behind F-C1, F-H4, F-H5, F-C3 simultaneously.

**Codification target**: a CO rule that says "every new fabric subsystem PR must include the FabricRuntime wiring change in the same diff, or be marked `experimental=True` in the export list and excluded from public docs until wired."

### G-2. Validation theatre is a recurring pattern

Three sites validate input as if to enforce a contract that is never enforced (`tenant_extractor`, `enable_writes`, `host="0.0.0.0"`). The pattern reads as defensive programming but functions as decoration. **Codification target**: extend `dataflow-pool.md` Rule 3 with: "If a parameter is validated, the validator MUST cite the file:line where the parameter is consumed in production code, in a comment immediately above the validator. No consumer = delete the validator and the parameter."

### G-3. Backward compatibility shims accumulate without removal plans

`_BoundedNonceSet` (F-H7) is the canonical example: 41 lines of legacy alias for two test-only callers, with `asyncio.run()` from sync wrappers. **Codification target**: every backward-compat class in fabric/ must have a removal milestone in the file header docstring (`# Deprecated since 1.x; remove after 2.0`), and the test file must be migrated atomically with the class deletion.

### G-4. The fabric README and `examples/fabric_reference/app.py` show paths that don't exist in code

This was hinted at in the first-pass blast-radius analysis but the second pass confirms the depth: `examples/fabric_reference/README.md` documents `db.start(dev_mode=True)` and shows `GET /fabric/dashboard` working. The route `/fabric/dashboard` has no live HTTP handler in the codebase (F-C1). Either the example was tested against a hand-wired Nexus server that the example does not show, or the example was tested against a now-deleted code path. **Verify the example actually runs end-to-end before the dataflow-perfection plan ships.** If the example fails, it is a stub example and falls under zero-tolerance Rule 2.

### G-5. The pattern of "subsystem defined as a class with `start()`/`stop()` then never called" is the structural signature of orphan code in Python

Five fabric classes have `start()` and `stop()` methods (`FabricRuntime`, `LeaderElector`, `ChangeDetector`, `FabricScheduler`, `WebhookReceiver`). Two of them (`FabricScheduler`, and indirectly `WebhookReceiver` via the missing handle_webhook path) are never started. **Codification target**: a lint rule that finds classes with `async def start(self)` and grep verifies that the class is instantiated and `start()` is awaited somewhere in `src/`. Zero matches → fail. This rule would have caught F-H4 at write time.

### G-6. Cache-backend orphancy mirrors leader-backend pattern but inversely

`leader.py` has a clean ABC + two backends + factory pattern (Redis, in-memory). `webhooks.py` has the same shape (`_NonceBackend`, `_RedisNonceBackend`, `_InMemoryNonceBackend`). The first-pass plan adds the same shape for the cache (`FabricCacheBackend` ABC). **The pattern is well-established in fabric/ — three subsystems use it.** The reason `pipeline.py` doesn't is not lack of template; it is lack of execution. The author had two reference implementations 200 lines away and chose not to use them. **Codification target**: a "cross-subsystem template alignment" check at `/redteam` time that asks "if a similar concern exists elsewhere in the same module, why is the implementation different?" The answer is sometimes legitimate; the question must be asked.

## Top-line severity rollup (new findings only, excludes inherited)

| Severity     | Count                   |
| ------------ | ----------------------- |
| **CRITICAL** | 4 (F-C1 through F-C4)   |
| **HIGH**     | 12 (F-H1 through F-H12) |
| **MEDIUM**   | 12 (F-M1 through F-M12) |
| **LOW**      | 7 (F-L1 through F-L7)   |

Combined with the inherited first-pass findings (3 CRITICAL, 5 HIGH, 2 MEDIUM, plus the docstring-lie cluster), the fabric module carries **7 CRITICAL, 17 HIGH, 14 MEDIUM, 7 LOW** open issues against the dataflow-perfection definition. The mandate's "perfect" target requires all to be resolved before close.

The single largest fix surface is F-C1 (unwired endpoint stack). It is larger in scope than the original #354 fix and should be a separate atomic PR. F-C2 (tenant propagation) must land **before** the issue-354 PR or in the same PR, because the issue-354 fix without F-C2 produces a "tenant_id parameter that nothing populates" — i.e., a new stub. F-C3 + F-C4 (webhook ingress + format support) must land before any production deployment claims webhook support.
