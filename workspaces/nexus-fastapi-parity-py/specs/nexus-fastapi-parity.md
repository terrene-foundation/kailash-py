# Spec — Nexus FastAPI parity (canonical surface contract)

Authority for the implementation phase of issue #1174. Per `rules/specs-authority.md` § MUST Rule 5, this spec is updated at first instance whenever the implementation surfaces a new architectural decision.

## Scope

Five surface additions and one new sub-module on `packages/kailash-nexus/`:

1. `kailash.nexus.extractors` — new sub-module exposing `Depends`, `Request`, `UploadFile`, `Multipart`, `NexusHandlerError`. Possibly also `Bytes` (issue body names it); `Headers` / `Query` / `Body` depend on Q3 scope decision.
2. `Nexus.handler_extract(name, func, ...)` — new registration method that inspects parameter annotations + defaults to build a per-handler resolver chain.
3. `Nexus.dependency_overrides` — new attribute (`DependencyOverrideMap`) with context-manager + imperative set / clear API.
4. `Nexus.register_sse(path, on_subscribe, *, keepalive_interval=15)` — new method; the existing `register_sse_endpoint(nexus)` becomes a shim.
5. `Nexus.register_websocket(path, ..., on_message=..., on_connect=..., on_disconnect=..., allowed_origins=...)` — existing class-based path stays; callback shape is a sibling overload.
6. `packages/kailash-nexus/docs/migration-fastapi.md` — new migration guide.

Out of scope for this shard (deferred to follow-up issues):

- Pydantic body parsing.
- Cross-transport `NexusRequest` context object.
- `Headers` / `Query` / `Body[Model]` extractors (unless Q3 widens scope).
- OpenAPI generation from extractor-annotated handlers.

## Design rationale — FastAPI parity framing

The extractor surface names (`Depends`, `Request`, `UploadFile`, `Multipart`, `dependency_overrides`) match FastAPI's surface BECAUSE: (a) FastAPI is the de-facto open-source Python web framework, so SDK users coming from FastAPI expect these names; (b) the Nexus extractor module is motivated by SDK-user migration ergonomics (the issue body's stated single-gateway consolidation rationale), not by competition with or derivation from FastAPI.

FastAPI is open-source (MIT License) and is NOT a commercial product. Per `rules/independence.md` § "No Commercial References", the Foundation Independence policy applies to commercial / proprietary products — naming parity with an open-source framework at the API-surface layer does NOT fire `rules/independence.md` or `rules/terrene-naming.md`. The naming is parity at the API-surface layer only; semantics, transport, dispatch, and the resolver chain are Nexus-native (`packages/kailash-nexus/src/nexus/`). Kailash Python SDK remains an independent open-source product owned by the Terrene Foundation; FastAPI is one of many ecosystems whose users migrate to Nexus, not a parent project.

Per `rules/independence.md` § "Describe Kailash on its own terms" — this spec describes Nexus's extractor surface as the Foundation's open-source workflow orchestration platform's ergonomic input layer. The migration guide describes the FastAPI → Nexus walk for SDK users coming from that ecosystem; it does NOT describe Nexus as derivative.

This section is included at the top of the canonical spec so the downstream `/codify` cc-architect review has the explicit framing on first read — preventing a misclassification of the FastAPI-parity-named symbols as a commercial-product reference.

## Surface contract

### `kailash.nexus.extractors`

New file `packages/kailash-nexus/src/nexus/extractors/__init__.py`. MUST NOT import `from __future__ import annotations`. Exports:

| Symbol | Kind | Source | Purpose |
| --- | --- | --- | --- |
| `Depends` | Class | New (this module) | Marker for dependency-injection. `x = Depends(callable)`. |
| `Request` | Re-export | `starlette.requests.Request` | Handler annotation; bound to the originating HTTP request. Untrusted proxy headers (`X-Forwarded-For`, `X-Forwarded-Proto`, `X-Real-IP`) are NOT trusted by default. (MED-S1: see "Trusted proxy posture" below.) |
| `UploadFile` | Re-export | `starlette.datastructures.UploadFile` | Single-file upload extractor. |
| `Multipart` | Type alias | `list[UploadFile]` | Multi-file upload extractor. Default list-length cap 100 files per `Nexus(max_multipart_files=100)`; configurable. (MED-S2; rejection envelope per MED-3 below) |
| `NexusHandlerError` | Class | New (this module) | Typed status return per `rules/nexus-http-status-convention.md` MUST Rule 4. Carries `status_code: int` + `body: dict \| str`. |
| `Bytes` | Class | New (this module) | Raw-bytes body extractor (named in issue body). |
| `Headers` | Class | New (this module) | Case-insensitive read-only mapping of inbound HTTP headers. Contract section below. |
| `Body[T]` | Generic class | New (this module) | Typed-body extractor; the resolver invokes the registered `Decoder` for `T` (or the `T(**dict)` fallback for dataclass-shape models). Subject to the mass-assignment policy in the section below. |

`__all__` enumerates ALL of the above. PEP 562 not required — no callable-module shape here.

#### Body[T] — mass-assignment policy (HIGH-S6, OWASP A04:2021)

The `Body[T]` extractor accepts a typed model `T` whose instance is constructed from the decoded JSON body. Untrusted client input populating fields the handler did not declare is canonical **OWASP A04:2021 (Insecure Design — Mass Assignment)**: a client posts `{"is_admin": true, "id": 1, ...}` against a handler typed `Body[User]` and lifts privilege-bearing fields into the model that the handler never intended to expose to the wire. The resolver MUST close this class structurally. Per `rules/security.md` § Input Validation + § Output Encoding (the BLOCKED-fields list applies — never echo VALUES of unknown fields; surface only their NAMES).

1. **Pydantic models — registration-time policy gate.** The resolver MUST verify `T.model_config.get("extra", "allow") == "forbid"` at `nexus.handler_extract` registration time via reflection on `T.model_config`. Registering a handler whose `Body[T]` model declares `extra='allow'` OR `extra='ignore'` (Pydantic's default behaviors that silently absorb extras) MUST raise `BodyExtraPolicyError` AT REGISTRATION (server-launch-fails-loud), NOT at first request — fail-closed at boot is the structural defense the silent-default-equals-vulnerable failure mode requires. Pydantic's default `extra='ignore'` is by definition the insecure default for this surface.
2. **Dataclasses / attrs / plain classes — request-time key check.** The fallback path is NOT a naive `T(**dict)`. Instead: the resolver MUST introspect declared `__init__` parameters via `inspect.signature(T.__init__).parameters`, intersect dict keys against the declared parameter set, and if `unknown_keys = set(dict.keys()) - set(param_set)` is non-empty, raise `BodyExtraKeysError` listing the unknown keys. Silent forwarding to `T(**dict)` (which would either accept the extras into `**kwargs` or raise an opaque `TypeError`) is BLOCKED. `**kwargs`-accepting dataclasses MUST be explicitly registered via a custom decoder (point 3) — the introspection-based fallback does not accept them by default.
3. **Custom decoders.** Decoders registered via `register_decoder(T, decoder)` (per the existing `Decoder` protocol at `packages/kailash-nexus/src/nexus/typed_service_client.py:284`) are caller-responsible-for-security. The decoder contract MUST document that decoders accepting extras carry the mass-assignment risk and that strict-mode validation is the caller's responsibility. The canonical Pydantic-decoder example in the migration guide (`02-plans/02-migration-guide-outline.md` § Section 2) MUST use `T.model_validate(dict, strict=True)` against a `T` whose `model_config = ConfigDict(extra="forbid")` — see NEW-LOW-1 below.
4. **Error envelopes per `rules/nexus-http-status-convention.md` MUST Rule 2.**
   - `BodyExtraPolicyError` (registration-time) is a startup failure — Nexus refuses to start when ANY `Body[T]` handler has not declared `extra='forbid'` (Pydantic) or is not introspectable for `__init__` parameters (dataclass/plain-class path). The error message names the handler + the offending `T` + the policy gap. There is no HTTP surface for this error — it never reaches a client.
   - `BodyExtraKeysError` (request-time, dataclass/plain-class path) MUST surface as HTTP **400 Bad Request** with body `{"error": "request body contains unknown fields", "code": "BODY_UNKNOWN_FIELDS", "unknown_fields": [...]}`. The `unknown_fields` list MUST contain only the field NAMES (not the values); field names are safe to surface at this boundary (they are not credentials), but echoing the VALUES would reflect attacker-controlled bytes back to the client and violate `rules/security.md` § Output Encoding. For Pydantic models declared with `extra='forbid'`, Pydantic's own `ValidationError` is mapped to the same envelope shape by the resolver — same 400 + `BODY_UNKNOWN_FIELDS` code + sanitized `unknown_fields` list.
5. **Regression test contract (Tier-2 — `rules/testing.md`).** `packages/kailash-nexus/tests/integration/nexus/test_body_extra_policy.py` covers four scenarios: (a) registering a `Body[T]` handler whose Pydantic `T` declares `extra='allow'` raises `BodyExtraPolicyError` at registration; (b) a Pydantic `T` with `extra='forbid'` receiving a body carrying extra fields surfaces HTTP 400 + `BODY_UNKNOWN_FIELDS` envelope; (c) a dataclass `T` receiving a body with extra keys raises `BodyExtraKeysError` → HTTP 400 + envelope; (d) end-to-end mass-assignment scenario — `{"is_admin": true}` against a `Body[User]` handler whose `User` dataclass does NOT declare `is_admin` — MUST surface HTTP 400 and the handler MUST NOT see `is_admin` as a model attribute.

The structural defense closes the class: there is no path by which a `Body[T]` handler silently absorbs an unknown field into the model. Either the model declares `extra='forbid'` (Pydantic, registration-time gate) or `__init__` introspection enumerates the accepted set (dataclass/plain, request-time gate). The decoder protocol fence (point 3) bounds the surface a custom decoder author can widen — they MUST opt-out explicitly, not via the silent-default.

#### Multipart / UploadFile — input-validation MUSTs

The HTTP-transport multipart resolver MUST enforce the following input-validation contract before any handler body sees an `UploadFile` / `Multipart` value. Per `rules/security.md` § Input Validation:

1. **Total-body cap.** Default `Nexus(max_request_body_bytes=10_485_760)` (10 MiB). When the inbound `Content-Length` (or accumulated streaming-decoded bytes) exceeds the cap, the resolver MUST reject with HTTP **413 Payload Too Large** carrying `{"error": "request body exceeds configured cap", "code": "BODY_TOO_LARGE"}` per `rules/nexus-http-status-convention.md` MUST Rule 2 shape. Configurable per `Nexus` instance.
2. **Per-file size cap.** Default `Nexus(max_upload_file_bytes=10_485_760)` (10 MiB). Each individual file in the multipart form MUST be size-checked at parse time; the first file exceeding the cap rejects the entire request with HTTP **413** (no partial acceptance). Configurable per `Nexus` instance.
3. **`UploadFile.filename` is UNTRUSTED client input.** The resolver MUST treat the client-provided `filename` as untrusted bytes and sanitize before any filesystem use via `pathlib.PurePosixPath(name).name` — this strips path-traversal sequences (`../`, leading `/`), Windows-style separators (`\\`), and reserved directory names. Handlers receiving an `UploadFile` see the sanitized `.filename`; the original raw client value is dropped at the resolver boundary, NOT preserved as a sibling attribute. Per `rules/security.md` § Input Validation — path-traversal attacks (`../../../etc/passwd`) are the canonical exploit and MUST be structurally blocked at the resolver, not deferred to handler code.
4. **MIME-type derivation.** The resolver MUST derive `UploadFile.content_type` from a libmagic-style content-sniff of the first 4 KiB of the file body, NOT from the client-provided `Content-Type` header alone. The client header is captured as `UploadFile.client_declared_content_type` for audit but MUST NOT be the value handlers see in `.content_type`. Per `rules/security.md` § Input Validation — client-declared MIME is an attacker-controllable string and trusting it for dispatch (e.g., extension-based virus scanner routing) opens a known bypass class.
5. **Tempfile lifecycle.** The resolver MUST use Starlette's spooled-to-disk threshold (1 MiB default; tunable via `Nexus(multipart_spool_threshold=...)`). Cleanup is mandatory in BOTH branches: (a) on successful request completion, the resolver MUST call `await upload_file.close()` for every parsed file in a `finally` block keyed to the request lifecycle; (b) on exception (handler raise, transport disconnect, timeout), the same `finally` block MUST fire — silent leak of spooled tempfiles is BLOCKED. Per `rules/testing.md` § "Fixtures Yield + Cleanup, Never Return" — the cleanup contract is symmetric with the test-fixture rule.
6. **File-count cap rejection envelope (MED-3).** When a client multipart submission exceeds `Nexus(max_multipart_files=...)` (default 100, configurable per MED-S2), the resolver MUST reject with HTTP **413 Payload Too Large** carrying `{"error": "multipart request exceeds configured file-count cap", "code": "TOO_MANY_FILES", "limit": <int>}` per `rules/nexus-http-status-convention.md` MUST Rule 2 envelope shape. The `limit` field surfaces the configured cap so SDK users can adjust client-side batching without an out-of-band ops query. Rejection MUST fire as soon as the parser observes the (cap+1)th file, not after parsing the entire body — early rejection bounds memory cost when a malicious client batches 10000 files.

Tier-2 regression test contract for the path-traversal defense: `packages/kailash-nexus/tests/integration/nexus/test_multipart_path_traversal.py` POSTs a multipart body with `filename="../../../etc/passwd"`; asserts the handler sees `filename == "passwd"` (sanitized) AND that the resolver did not invoke any filesystem `open()` call against the unsanitized value (subprocess-level audit). Per `rules/testing.md` § Regression Testing.

#### Headers extractor contract (NEW-MED-1)

The `Headers` extractor surfaces the inbound HTTP headers as a case-insensitive, read-only mapping. Per RFC 7230 §3.2 (HTTP/1.1 message syntax) and `rules/security.md` § Input Validation:

1. **Case-insensitive access.** `Headers["X-Foo"]`, `Headers["x-foo"]`, `Headers["X-FOO"]`, and `Headers.get("x-Foo")` MUST return the same value. The mapping internally normalizes keys to lowercase ASCII per RFC 7230 §3.2 (header field names are case-insensitive).
2. **Duplicate-value handling per RFC 7230 §3.2.2.** HTTP headers MAY appear multiple times in a single message. The `Headers` extractor MUST provide BOTH access shapes: (a) `Headers["X-Foo"]` returns the values joined by `, ` (per RFC 7230 §3.2.2 — "a recipient MAY combine multiple header fields with the same field name into one"); (b) `Headers.getlist("X-Foo")` returns the list of raw values in insertion order. The scalar form covers the common case; the list form serves SDK users who need the structured shape (e.g., parsing a comma-bearing `Set-Cookie` correctly).
3. **Insertion-order preservation.** `iter(Headers)`, `Headers.keys()`, and `Headers.items()` MUST preserve the insertion order from the original request — NOT re-sort alphabetically. This preserves debuggability of header-order-sensitive client behaviors.
4. **Read-only at the handler boundary.** `Headers.__setitem__`, `Headers.__delitem__`, and any mutation method MUST raise `TypeError` with a clear message. The handler MUST NOT mutate request headers; the response-construction path is a separate surface.

#### Bytes extractor contract (NEW-MED-1)

The `Bytes` extractor surfaces the full inbound request body as raw bytes. Per `rules/security.md` § Input Validation:

1. **Inbound size cap inheritance.** `Bytes` inherits `Nexus(max_request_body_bytes=10_485_760)` (10 MiB default, configurable per HIGH-S1 above). The resolver MUST short-circuit BEFORE reading the body fully: if `Content-Length` declares > cap, reject with HTTP **413** + `BODY_TOO_LARGE` envelope immediately (no body read); if the body streams without `Content-Length` and the accumulator exceeds the cap mid-stream, reject with HTTP **413** AND close the stream connection.
2. **Full-body delivery (not a generator).** A handler signature `async def f(body: Bytes) -> ...` receives the FULL (capped) body as `bytes` — NOT a generator or stream object. The resolver buffers the body up to the cap, then delivers the `bytes` value to the handler. SDK users needing streaming access use a different surface (out of scope for this shard).
3. **Log hygiene per HIGH-S4 split-visibility contract.** The resolver MUST NOT echo the body bytes into server logs (the body MAY contain credentials, PII, attack payloads). Per `rules/security.md` MUST NOT § "No secrets in logs" — only the body LENGTH is logged for observability; never the bytes.

### `Nexus.handler_extract`

```python
def handler_extract(
    self,
    name: str,
    func: Callable,
    *,
    description: str = "",
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    guard: Any = None,
) -> None:
    """Register `func` as a multi-channel handler with extractor support.

    Inspects `func`'s parameter list:
    - If annotation is Request / UploadFile / Bytes / Multipart — schedule
      extractor binding at invocation time.
    - If default is Depends(callable) — schedule dependency resolution
      with override-map consultation.
    - Otherwise — flat input mapping (same semantics as register_handler).

    Raises:
        TypeError: func not callable, or annotation resolution fails
            (likely caused by `from __future__ import annotations` in
            the handler's module — see migration guide §8).
    """
```

The resolver builds at registration time and runs at every invocation. The handler is wrapped in a `ResolverChain` that:

1. Constructs each `Depends`-bound parameter by consulting `nexus.dependency_overrides` first; if not overridden, invokes the wrapped callable (which may itself take extractors → recursive resolution).
2. Extracts each annotation-typed parameter from the originating request (HTTP path: read body / multipart / headers; other transports: per-transport adapter).
3. Invokes the handler body with the resolved kwargs.

Dependency-resolution cache: per-invocation, each `Depends(callable)` is resolved once. If two handler parameters reference the same dependency callable, the result is memoized for the duration of the invocation.

#### Resolver error-path discipline — no PII / internals leakage

When a callable wrapped by `Depends(...)` raises during resolution, the resolver MUST split client-visible vs server-visible information:

1. **Server-side logging.** The resolver MUST log the full exception context server-side: exception type, full traceback, the resolved request correlation ID (`X-Request-ID` or a server-minted UUID), the handler name, the dependency callable's `__qualname__`, AND the request-context fields per `rules/observability.md`. This log entry is the operator's only audit trail when an end-user reports an error.
2. **Client-visible response.** The resolver MUST surface to the client ONLY: HTTP **500 Internal Server Error** (or the typed status if the raised exception is a `NexusHandlerError` per `rules/nexus-http-status-convention.md` MUST Rule 4) AND the request correlation ID. The response body shape: `{"error": "internal error", "code": "INTERNAL_ERROR", "correlation_id": "<uuid>"}`. Per `rules/nexus-http-status-convention.md` MUST Rule 2 — every 4xx/5xx body MUST carry the canonical shape.
3. **BLOCKED in client-visible response.** The resolver MUST NOT include in the HTTP response body: `str(exception)`, the exception's `__class__.__name__`, traceback fields, request-data echoes (header values, body fragments, query parameters), file paths from the traceback, environment-variable values, OR any other server-internal context. Per `rules/security.md` MUST NOT § "No secrets in logs" — the inverse applies to client surfaces: no internals leak BACK to clients. The correlation ID is the operator's lookup key in the server log; the client receives no other detail.

Per `rules/zero-tolerance.md` Rule 3 — silent swallow of dependency errors is BLOCKED; the server-side log is mandatory. The split-visibility contract converts a resolver failure from "client sees stack trace with internal class names" (the FastAPI default failure mode) into "client sees correlation ID, operator looks up the full context server-side".

### `Nexus.dependency_overrides`

```python
class DependencyOverrideMap:
    def override(self, real: Callable, mock: Callable) -> ContextManager[None]:
        """Context-manager scope: override real → mock for the block,
        restore on exit (including exception)."""
    def set(self, real: Callable, mock: Callable) -> None:
        """Imperative set; persists until clear()."""
    def clear(self, real: Callable) -> None:
        """Remove a single override; idempotent."""
    def clear_all(self) -> None:
        """Remove every override."""
    def __contains__(self, real: Callable) -> bool: ...
    def __getitem__(self, real: Callable) -> Callable:
        """Raises KeyError if not overridden."""

class Nexus:
    dependency_overrides: DependencyOverrideMap  # attribute, initialized in __init__
```

Concurrency contract: `DependencyOverrideMap` is a **TEST-ONLY** surface. Production code paths MUST NOT mutate it during request processing. Test fixtures mutate it at setup/teardown only.

- **Production read path.** During request processing, the `Depends` resolver reads the override map. Reads are safe under concurrent in-flight requests because the map is never written during a request — Python's GIL guarantees dict-read atomicity, no extra locking required for the read path. Per `rules/zero-tolerance.md` Rule 3 — adding production-time mutation hooks is BLOCKED; this is the structural defense against tests-as-production-config drift.
- **Test setup/teardown.** The map is mutated in test fixtures BETWEEN requests (not during). The rare cross-thread test-setup pattern (e.g., `pytest-xdist`) uses `threading.Lock` for atomicity of multi-step setup; per `rules/python-environment.md` Rule 5, the lock is constructed via `threading.Lock()` factory and the captured type is used for any `isinstance` checks (no direct `isinstance(x, threading.Lock)` — TypeError on 3.11+).
- **Production-time mutation guard (MED-1 — actionable error message).** Any call to `DependencyOverrideMap.override()` / `.set()` / `.clear()` / `.clear_all()` DURING an active request (detected via the request-context registry) MUST raise `DependencyOverrideRuntimeMutationError` with an actionable, three-field message naming (a) the specific overridden callable's `__qualname__`, (b) the active request's `correlation_id`, AND (c) an operator-audit lookup hint pointing to the server log. The canonical format: `f"DependencyOverrideMap.{op}({callable.__qualname__}) called during active request {correlation_id}; overrides may only be mutated at test setup/teardown — see server log entry for the request stack."` Per `rules/zero-tolerance.md` Rule 3 (silent fallback BLOCKED) + Rule 3a (typed delegate guards MUST be actionable, not generic): a generic "BLOCKED case" message blocks the symptom without naming what the user changed or where to look. Three fields convert a five-minute incident-triage into a one-line fix instruction. Symmetric with `rules/zero-tolerance.md` Rule 3a's typed-error contract (the JWTMiddleware example).

The dependency-overrides surface IS the test-injection mechanism; treating it as a production-time DI container is BLOCKED.

### `Nexus.register_sse`

```python
async def register_sse(
    self,
    path: str,
    on_subscribe: Callable[[Request], AsyncIterator[dict]],
    *,
    keepalive_interval: int = 15,
) -> None:
    """Register an SSE endpoint at `path`.

    `on_subscribe(request) -> AsyncIterator[dict]` yields events;
    each dict serializes to `data: {json}\n\n` per the SSE spec.
    Keepalive comments (`: keepalive\n\n`) fire every
    `keepalive_interval` seconds.

    Headers set on every response:
    - Content-Type: text/event-stream
    - Cache-Control: no-cache
    - X-Accel-Buffering: no

    Cleanup: on client disconnect, the async iterator is cancelled
    via asyncio.CancelledError; on_subscribe MUST handle the
    cancellation gracefully (close DB connections, release resources).
    """
```

Implementation mirrors `sse.py:_sse_generator` (lines 35-85) but parameterizes the source. The existing `register_sse_endpoint(nexus)` (`sse.py:88`) is refactored to call `register_sse("/events/stream", on_subscribe=_eventbus_subscribe)` — internally collapsed into one implementation, no behavior change for existing consumers.

#### register_sse — auth + rate-limit + backpressure MUSTs

Per `rules/security.md` § Input Validation + DoS prevention, `register_sse` is a long-lived streaming endpoint and MUST carry the same authn/authz + rate-limit + resource-bound posture as a plain HTTP handler. The signature is extended:

```python
async def register_sse(
    self,
    path: str,
    on_subscribe: Callable[[Request], AsyncIterator[dict]],
    *,
    keepalive_interval: int = 15,
    dependencies: list[Depends] = [],
    max_queue_depth: int = 1000,
    max_event_bytes: int = 65_536,
    slow_consumer_timeout: float = 30.0,
) -> None: ...
```

MUST clauses:

1. **Auth delegation through the resolver chain.** SSE endpoints MUST accept `dependencies: list[Depends] = []` parameter — every `Depends` in the list resolves on subscribe through the SAME resolver chain as HTTP `handler_extract` (Shard 1). A `Depends(get_current_user)` that raises `Unauthorized` MUST close the stream with HTTP **401** BEFORE the SSE handshake completes — never emit a partial `event-stream` body to an unauthenticated client. Test contract: a subscriber missing the bearer token receives 401 + JSON body per `rules/nexus-http-status-convention.md` MUST Rule 2, NOT an empty `text/event-stream` response.
2. **Bounded queue depth.** Default 1000 events; configurable. The resolver MUST maintain a per-subscription `asyncio.Queue(maxsize=max_queue_depth)`. When `on_subscribe` yields faster than the client consumes, the queue fills; on overflow the resolver MUST close the stream with SSE `event: error\ndata: {"code": "QUEUE_OVERFLOW"}\n\n` then EOF — silent drop of events is BLOCKED per `rules/zero-tolerance.md` Rule 3.
3. **Max event size.** Default 65 536 bytes (64 KiB) per event after JSON serialization; configurable. An event exceeding the cap MUST be dropped with a structured server-side log (correlation ID + size + cap) and the stream MUST emit an SSE `event: error\ndata: {"code": "EVENT_TOO_LARGE"}\n\n` to the subscriber, then continue with the next event (NOT close the stream — a single oversized event is recoverable). Per `rules/security.md` § Input Validation.
4. **Slow-consumer disconnect.** Default 30 seconds; configurable via `slow_consumer_timeout`. When the resolver cannot flush the next event to the underlying transport within the timeout (TCP window full, client unreachable), the resolver MUST close the stream with code 1011 (server error) and release all per-subscription state (queue, on_subscribe iterator, auth context). Per `rules/security.md` — slow-consumer DoS is the canonical SSE exhaustion vector.
5. **Rate-limit integration.** The SSE endpoint MUST honor `nexus.auth.rate_limit` hooks on the SUBSCRIBE event (NOT per emitted event — rate-limiting per-event would defeat the streaming primitive). The hook fires once at handshake; rate-limit refusal MUST close the connection with HTTP **429 Too Many Requests** per `rules/nexus-http-status-convention.md` MUST Rule 2 shape BEFORE the SSE upgrade. Per `rules/security.md` Kailash-Specific Security § Nexus — "Rate limiting" applies symmetrically to streaming endpoints.
6. **`on_subscribe` exception handling (MED-S4).** Per `rules/zero-tolerance.md` Rule 3, silent swallow of `on_subscribe` exceptions is BLOCKED. The resolver MUST distinguish:
   - `asyncio.CancelledError` (client disconnect / server shutdown): expected; release per-subscription resources and exit silently.
   - Any other exception: log the full exception context server-side (correlation ID + traceback + handler name) AND close the stream with an explicit SSE `event: error\ndata: {"code": "INTERNAL_ERROR", "correlation_id": "<uuid>"}\n\n` frame, then EOF. The client MUST receive an explicit error event — silent close ("the stream just stopped") is BLOCKED because clients cannot distinguish server crash from normal completion.

### `Nexus.register_websocket` (callback overload)

```python
def register_websocket(
    self,
    path: str,
    handler_cls: Optional[type] = None,
    *,
    on_message: Optional[Callable[[Connection, dict], Awaitable[None]]] = None,
    on_connect: Optional[Callable[[Connection], Awaitable[None]]] = None,
    on_disconnect: Optional[Callable[[Connection], Awaitable[None]]] = None,
    allowed_origins: Optional[List[str]] = None,
) -> Any:
    """Register a WebSocket endpoint at `path`.

    Two shapes:
    1. Class-based (existing): pass a MessageHandler subclass as `handler_cls`.
    2. Callback (new): pass `on_message` (required) plus optional
       `on_connect` / `on_disconnect`. Internally synthesizes a
       MessageHandler subclass.

    Dispatch (per rules/zero-tolerance.md Rule 3d — discriminator,
    not structural):
    - handler_cls is not None AND issubclass(handler_cls, MessageHandler)
      → class-based path.
    - handler_cls is None AND on_message is not None → callback path.
    - Both / neither → ValueError naming the BLOCKED case.

    Returns: the instantiated handler (same as existing behavior).
    """
```

The class-based code path at `core.py:705-775` stays as-is for the class shape. The new dispatch logic is added at the top; the callback path synthesizes a class internally via `type("_CallbackHandler", (MessageHandler,), {...})` and routes through the same `_ws_message_handlers.register` call.

#### register_websocket callback — origin allowlist + WS security MUSTs

The callback overload synthesizes an internal `MessageHandler` subclass that MUST register through the SAME `_ws_message_handlers.register` invocation as the class path AND carry identical security posture. Per `rules/security.md` Kailash-Specific Security § Nexus + the existing DNS-rebinding defense at `packages/kailash-nexus/src/nexus/websocket_origin.py` (issue #673):

1. **Origin allowlist parity.** The synthesized handler MUST enforce `allowed_origins` through the SAME `validate_origin_allowlist` + `origin_matches_allowlist` call sites in `packages/kailash-nexus/src/nexus/websocket_origin.py` that the class path uses. The callback path MUST NOT introduce a parallel codepath bypassing the existing origin validation — every handshake routes through one validator. Mismatched origins close with WebSocket code 1008 (policy violation) and a fingerprinted reason (sha256(origin)[:8] per `rules/observability.md` Rule 6 + Rule 8) that does NOT echo the raw Origin back to the client.
2. **Subprotocol allowlist.** New parameter `subprotocols: list[str] = []` on both class and callback shapes. The handshake MUST default-reject any client-offered subprotocol not in the list. When `subprotocols=[]` (the default) AND the client offers a subprotocol, the handshake closes with code 1002 (protocol error). Per `rules/security.md` § Input Validation — accepting an arbitrary client-offered subprotocol opens a known fingerprint-evasion vector.
3. **Max message size.** Default 1 MiB per inbound frame after decode; configurable via `Nexus(max_websocket_message_bytes=...)`. Frames exceeding the cap MUST close the connection with code 1009 (message too big). Per `rules/security.md` — unbounded message size is a DoS vector.
4. **Auth at handshake.** The callback overload MUST accept `dependencies: list[Depends] = []` symmetric to `register_sse` HIGH-S2 above; `Depends` resolves at handshake (BEFORE the WebSocket upgrade completes) and a raising dependency closes with HTTP **401** or **403** per `rules/nexus-http-status-convention.md` MUST Rule 2 — NEVER complete the upgrade then close mid-stream.

Tier-2 regression test contract: `packages/kailash-nexus/tests/integration/nexus/test_register_websocket_callback_origin.py` asserts that `register_websocket(path, on_message=..., allowed_origins=["https://app.example.com"])` rejects a handshake from `Origin: https://attacker.example.com` with close code 1008 + fingerprinted reason — IDENTICAL behavior to the class path's existing test at `tests/integration/test_websocket_origin_allowlist.py`. Per `rules/testing.md` § "One Direct Test Per Variant In Every Delegating Pair".

## Trusted proxy posture (MED-S1, extended by MED-2)

Per `rules/security.md` § Input Validation + RFC 7239 §6.3, Nexus does NOT trust client-controllable proxy headers by default. The full forwarded-header surface MUST be defended — not just `X-Forwarded-For` / `X-Forwarded-Proto`. Production reverse-proxy deployments span multiple conventions: nginx defaults to `X-Real-IP`; Caddy and modern AWS ALBs emit RFC 7239 `Forwarded`. Defending only the two original headers leaves the other two as bypass surfaces.

Defaults (no operator opt-in):

- `Request.client.host` MUST be the immediate TCP peer's IP address — NEVER an `X-Forwarded-For` / `X-Real-IP` / RFC 7239 `Forwarded` derivation.
- `Request.url.scheme` MUST be derived from the TLS termination state of the immediate connection — NEVER from `X-Forwarded-Proto` / `Forwarded; proto=...`.

When Nexus is deployed behind a trusted reverse proxy (Caddy, nginx, ALB), the operator opts in via `Nexus(trusted_proxy_cidrs=["10.0.0.0/8", "192.168.0.0/16"])`. The resolver MUST verify the immediate peer's identity AND consult headers in priority order:

1. **Peer CIDR check (structural).** Verify the immediate TCP peer is in `trusted_proxy_cidrs` via `ipaddress.ip_network(cidr).supernet_of(ipaddress.ip_network(peer + "/32"))` for each declared CIDR. The check is structural (`ipaddress.IPv4Network`/`IPv6Network` set arithmetic) — NOT a substring/prefix match on `peer.startswith(...)` which would silently misclassify `10.0.0.1` and `100.0.0.1`.
2. **If peer trusted — header priority order per RFC 7239 §6.3.**
   - **First** consult RFC 7239 `Forwarded` (the canonical, IETF-standardized header) — parse the right-most untrusted hop per §6.3.
   - **Second** fall back to `X-Forwarded-For` (legacy de-facto standard, comma-separated; take the right-most untrusted entry).
   - **Third** fall back to `X-Real-IP` (nginx default; single-value).
3. **If peer untrusted — IGNORE all forwarded headers.** `request.client.host` is the originating identity. The forwarded headers are NOT consulted for any security-sensitive decision (rate-limit key, audit subject, geofencing, IP-allowlist).

Default `trusted_proxy_cidrs=[]` (empty list) means no forwarded headers are honored — the safest posture for direct-internet-facing deployments. Per `rules/security.md` MUST NOT § "No eval() on user input" — by extension, no trust of client-attacker-controllable header strings for security-sensitive decisions without an explicit operator opt-in PLUS the structural CIDR check above.

## PEP 563 incompatibility — typed error at registration time

When `handler_extract` inspects a handler's signature and the handler's module uses `from __future__ import annotations`, the annotation values are strings, not types. The resolver MUST detect this and raise a typed error:

```python
class ExtractorPEP563Error(TypeError):
    """Raised when a handler's module uses `from __future__ import annotations`
    AND the handler uses extractor types.

    Fix: remove `from __future__ import annotations` from the handler's
    module. See packages/kailash-nexus/docs/migration-fastapi.md § 8.
    """
```

Detection: at registration, the resolver attempts `typing.get_type_hints(func, globalns=func.__globals__)`. If the resolved hints are strings (not types), raise `ExtractorPEP563Error` with the WORKSPACE-RELATIVE file path and line number of the handler.

**Error message PII hygiene (LOW-S1).** The `ExtractorPEP563Error` message MUST cite a workspace-relative path (e.g., `packages/my-app/src/handlers/users.py:42`), NEVER an absolute path that leaks user-system tenant identifiers (e.g., `/Users/<operator>/repos/<consumer-app>/src/handlers/users.py:42`). Per `rules/security.md` MUST NOT § "No secrets in logs" extended to error-message content — exception messages reach client error-tracking SaaS (Sentry, Rollbar, Bugsnag) and the absolute path leaks the operator's home directory layout. The relative path is sufficient for the operator to locate the file from their repo root.

## Test contract

Per `rules/testing.md` Tier 2 (real infrastructure, no mocking) — every AC ships with a Tier 2 test in `packages/kailash-nexus/tests/integration/`:

| AC | Test file | Scenario |
| --- | --- | --- |
| 1 (`Depends`) | `test_extractor_depends_wiring.py` | Handler with `Depends(get_user)`; HTTP invocation; assert resolved user reaches handler. Recursive case: `Depends(A)` where A takes `Depends(B)`. |
| 2 (`Request`) | `test_extractor_request_wiring.py` | Handler with `request: Request`; HTTP POST with custom header; assert handler sees the header. PEP 563 rejection test (fixture module with `from __future__ import annotations` raises `ExtractorPEP563Error` at registration). |
| 3 (`dependency_overrides`) | `test_dependency_overrides_wiring.py` | Context-manager override; imperative set / clear / clear_all; restore after exit (including exception path); concurrent overrides from two threads. |
| 4 (`Multipart` + `UploadFile`) | `test_extractor_multipart_wiring.py` | POST multipart body with 3 files; assert `Multipart` parameter is `list[UploadFile]` of length 3, each file's `read()` returns the original bytes. Single-file variant with `UploadFile`. |
| 5 (`register_sse`) | `test_register_sse_wiring.py` | Register SSE endpoint; `on_subscribe` yields 3 events; client connects, reads 3 SSE frames + keepalive; client disconnect → server cancels iterator gracefully. |
| 6 (`register_websocket` callback) | `test_register_websocket_callback_wiring.py` | Callback registration; client connects, sends message, asserts echo; lifecycle callbacks (`on_connect` / `on_disconnect`) fire. Dispatch ambiguity test: both `handler_cls` and `on_message` raises ValueError. |

Per `rules/facade-manager-detection.md` MUST Rule 2 — every manager-shape class (`DependencyOverrideMap`, `ResolverChain` if it qualifies) gets a Tier 2 wiring test named `test_<lowercase_manager_name>_wiring.py`.

**PEP 563 test coverage clarification (MED-R2).** The PEP 563 rejection test fires at FIRST registration of ANY extractor-using handler from a PEP-563-affected module — the detection path is shared across ALL extractor types (`Depends` / `Request` / `Multipart` / `UploadFile` / `Bytes` / `Headers` / `NexusHandlerError`). ONE Tier-2 test covering the detection contract (typically asserting `pytest.raises(ExtractorPEP563Error)` from a fixture module that uses `from __future__ import annotations`) covers all extractors. Per `rules/testing.md` § "Test-Once Protocol" — duplicating the test per extractor type is overhead with no marginal coverage benefit; one shared test against the resolver's PEP-563 gate is sufficient.

**Probe-driven verification posture (MED-R3).** Per `rules/probe-driven-verification.md` Rule 3, all assertions in this spec's test contract are STRUCTURAL (HTTP transport behavior, status codes, response shape, exception types, fixture file existence, byte-equality on file uploads); no LLM-judge probes are required. Structural assertions keep regex / direct equality per Rule 3. The Tier-2 tests for `Depends` (recursive resolution), `Multipart` (path-traversal sanitization), `register_sse` (queue overflow), and `register_websocket` (origin rejection) ALL have deterministic structural oracles (status code, response body shape, log lines via `caplog`).

## Sibling spec impact

Per `rules/specs-authority.md` MUST Rule 5b, every spec edit triggers full sibling-spec re-derivation. The Nexus FastAPI parity surface touches three loom-side sibling specs whose mandates depend on the surfaces this workspace spec defines. At /implement time, each MUST be amended in the same PR that lands the corresponding code shard:

| Sibling spec | Current state (cited at HEAD) | Required amendment at /implement |
| --- | --- | --- |
| `specs/nexus-channels.md` §4.4.1 (lines 159, 173, 185, 422) | Documents `register_websocket(path, handler_cls, *, allowed_origins=None)` as canonical surface; allowlist enforcement at `nexus.websocket_origin` (issue #673); cross-SDK kailash-rs parity row | ADD callback-overload section after the class-based path. Document the synthesized `MessageHandler` subclass, the `allowed_origins` / `subprotocols` / `max_websocket_message_bytes` / handshake-`Depends` parameters, and the regression test asserting parity with the class path's existing origin-rejection test. |
| `specs/nexus-core.md` §"Enterprise preset usage" (lines 652, 677) | Documents `register_sse_endpoint(app)` as the canonical SSE wiring under the enterprise preset | REFACTOR the example to delegate to `Nexus.register_sse(path, on_subscribe, dependencies=[...])` as the lower-level primitive; document `register_sse_endpoint(app)` as the higher-level shim that calls `register_sse` with an EventBus-backed `on_subscribe`. Surface the new `dependencies` / `max_queue_depth` / `max_event_bytes` / `slow_consumer_timeout` parameters in the example. |
| `specs/nexus-channels.md` §"Cross-SDK parity" (line 185 vicinity) | Asserts kailash-rs is expected to ship semantic parity for the WebSocket surface per EATP D6 | EXTEND the parity row to cover the callback overload AND the new SSE primitive AND the extractor surface. The kailash-rs sibling tracker is gated at /todos per HIGH-R3 below. |

The mechanical sweep for /implement Shard 1 + Shard 4 reviewers MUST include `grep -n "register_websocket\|register_sse_endpoint\|allowed_origins" specs/nexus-channels.md specs/nexus-core.md` to surface every callsite that needs updating in the same PR. Per `rules/specs-authority.md` MUST Rule 5 — spec edits land at first instance, NOT batched.

The workspace-local `specs/_index.md` carries a sibling-specs cross-reference table pointing to the loom-side specs above.

## Cross-SDK marker

Per `rules/cross-sdk-inspection.md` Rule 2, the implementation PR MUST cross-reference the kailash-rs sibling tracker IF one exists. The equivalent rs tracker URL is gated at /todos approval per HIGH-R3 of the R1 amendments: the user EITHER provides the URL (which the implementation PR body cites) OR confirms "no rs sibling tracker yet — ship without the cross-SDK alignment marker." Per `rules/spec-accuracy.md`, literal `<placeholder>` text is BLOCKED in a spec — every citation resolves at merge OR the section is dropped, never left as a tombstone.

Per `rules/repo-scope-discipline.md`, this session does NOT reach into `terrene-foundation/kailash-rs` to discover or create the URL. The cross-SDK alignment marker is a maintainer concern that the user resolves at the /todos gate; the kailash-py implementation PR cites whichever resolution the user provides.

## Implementation gates

Per `rules/agents.md` § Quality Gates — `/implement` is a MUST gate; reviewer + security-reviewer run as parallel background agents at the end of each shard. Reviewer mechanical sweeps:

- `grep -c 'from __future__ import annotations' packages/kailash-nexus/src/nexus/extractors/` → 0 (the extractor module itself must not use PEP 563).
- `grep -rn 'fastapi' packages/kailash-nexus/pyproject.toml` → no NEW top-level dep (FastAPI is allowed as a transitive of the existing `kailash` core).
- `pytest --collect-only packages/kailash-nexus/tests/` → exit 0 (collection gate per `rules/orphan-detection.md` MUST Rule 5).
- `pip check` after Shard 5's bump → clean (per `rules/dependencies.md`).

## Open scope decisions (Q1-Q5 — user gates before /todos)

The five open questions live in `02-plans/01-architecture.md` § "Open questions for the user". The spec assumes the recommended dispositions; if the user widens scope (Q1 → Pydantic in scope; Q3 → Headers / Query / Body in scope), the spec is amended in the same `/todos` round.
