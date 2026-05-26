# Per-AC gap analysis — FastAPI parity

Each subsection covers one of the seven acceptance criteria in issue #1174: current state, gap, recommended approach.

## AC-1: `Depends` extractor on the public Nexus extractor surface

**Current state — ABSENT.** No `Depends` symbol is exported from `nexus`. The codebase uses FastAPI's `Depends` internally at `auth/dependencies.py:25-91` and `auth/rbac.py:100-148`, but those imports are FastAPI's, not a Nexus extractor.

**Gap.** A Nexus extractor `Depends(callable)` that, when present as a default value on a handler parameter, resolves the callable's return value before invoking the handler. The callable may itself take extractors (recursive dependency resolution), and the result MUST be cacheable per-request when the same dependency is referenced multiple times in one handler.

**Recommended approach.** Create `packages/kailash-nexus/src/nexus/extractors/__init__.py` that exports `Depends`. The implementation is a small marker class storing the wrapped callable; the actual resolution happens in a new `handler_extract` registration path (see § AC-5 in the migration-guide section) that inspects parameter defaults at registration time and builds a resolver chain. Because the existing `register_handler` already inspects signatures via `make_handler_workflow`, the extractor surface either layers on top (extractor-aware wrapper) or creates a sibling registration method (`register_handler_extract` / `handler_extract`).

**Test.** Tier 2 integration — register a handler with `user: dict = Depends(get_current_user)`; invoke through the HTTP transport; assert the dependency's return value reaches the handler. Recursive case: `Depends(A)` where A itself takes `Depends(B)`.

## AC-2: `Request`-equivalent context extractor

**Current state — PARTIAL.** Starlette's `Request` is re-exported from `nexus` (`__init__.py:70` import, line 174 in `__all__`). It is not yet a handler EXTRACTOR — a handler today cannot declare `async def h(request: Request)` and receive the Starlette Request object on every transport. On the HTTP transport, FastAPI-style injection works because the gateway is FastAPI-backed, but the typed-extractor surface across transports is missing.

**Gap.** A `Request` extractor that, when annotated on a handler parameter, populates that parameter with a transport-agnostic request context. Per `auth/dependencies.py:6-9` docstring: "Do NOT use `from __future__ import annotations` in this module. FastAPI inspects parameter annotations at runtime to recognize special types like Request. PEP 563 deferred annotations turn them into strings, which prevents FastAPI from injecting the Request object". The same constraint propagates to the Nexus extractor surface.

**Recommended approach.** Two-layer:

1. Re-export Starlette `Request` from `nexus.extractors` for the HTTP transport (already done at the package root; re-add to the extractor namespace for ergonomics: `from kailash.nexus.extractors import Request`).
2. For transport agnosticism, add a `NexusRequest` context object that wraps `headers`, `query_params`, `path_params`, `body`, and the originating transport name (`"http"` / `"cli"` / `"mcp"` / `"websocket"`). The handler-extraction layer maps each transport's native request shape into `NexusRequest`. For pure HTTP-shape handlers, `Request` from Starlette stays the canonical type; `NexusRequest` is the cross-channel option.

**Test.** Tier 2 — register `async def whoami(request: Request) -> dict: return {"ua": request.headers.get("user-agent")}`; invoke via HTTP; assert headers reach the handler. Critical: the test MUST NOT use `from __future__ import annotations`.

## AC-3: `dependency_overrides` test fixture

**Current state — ABSENT.** No `dependency_overrides` accessor on `Nexus`. The pattern works on FastAPI as `app.dependency_overrides[real_dep] = mock_dep`; the override is consulted at every `Depends` resolution.

**Gap.** Two surfaces on the `Nexus` instance:

1. Context-manager form — `with nexus.dependency_overrides.override(real_dep, mock_dep): ...` scopes the override to the block.
2. Imperative form — `nexus.dependency_overrides.set(real_dep, mock_dep)` + `nexus.dependency_overrides.clear(real_dep)` (or `.clear_all()`).

**Recommended approach.** Implement `DependencyOverrideMap` as a mutable mapping with a context-manager method. Wire into the `Depends` resolution path so that every `Depends(callable)` first checks the override map and resolves to the override if present, otherwise resolves the original. Thread-safe per-instance (per `rules/python-environment.md` Rule 5 — `threading.Lock` is a factory in 3.11+; use `_LOCK_TYPES = type(threading.Lock())` if isinstance checks are needed).

**Test.** Tier 2 — define a handler with `Depends(get_current_user)`; in the test, override `get_current_user` to return a fixed mock user via both the context-manager AND the imperative form; invoke the handler; assert the mocked user reaches the handler. After exiting the context manager, assert the original dependency is restored.

## AC-4: `Multipart` + `UploadFile` body extractors

**Current state — ABSENT (primitive present).** `NexusFile` (`files.py:19` class definition; line 18 is the `@dataclass` decorator) is the transport-agnostic file dataclass; `NexusFile.from_upload_file(starlette_upload_file)` (line 45) converts a Starlette `UploadFile` into Nexus shape. What is missing is the EXTRACTOR layer that binds a multipart-encoded HTTP body to a handler parameter typed `Multipart` (a list of files) or `UploadFile` (a single file).

**Gap.** Two extractor type aliases / classes in `kailash.nexus.extractors`:

- `Multipart` — typed alias for `list[UploadFile]`; when annotated, the handler-extraction layer reads the multipart form from the request and populates the parameter with a list of `UploadFile` objects.
- `UploadFile` — single-file equivalent. Re-export Starlette's `UploadFile` or wrap as `NexusUploadFile`. The wrapped form has API parity with FastAPI's `UploadFile` (`filename`, `content_type`, `read()`, `aread()`, `seek()`).

**Recommended approach.** Re-export `UploadFile` from Starlette into `nexus.extractors`; alias `Multipart = list[UploadFile]`. Wire the HTTP transport's multipart parsing into the extractor resolution path. For non-HTTP transports (MCP, CLI), define a transport-specific mapping — MCP can receive base64-encoded file data per `NexusFile.from_base64` (`files.py:73`), CLI can receive file paths per `NexusFile.from_path` (`files.py:60`). The handler signature stays the same; the transport adapter does the conversion.

**Test.** Tier 2 — register `async def upload(files: Multipart) -> dict: return {"count": len(files)}`; POST a multipart body with 3 files to the HTTP endpoint; assert the response is `{"count": 3}`.

## AC-5: `register_sse` streaming primitive

**Current state — PARTIAL.** `register_sse_endpoint(nexus)` in `sse.py:88` mounts a fixed `GET /events/stream` endpoint tied to the Nexus EventBus. It does NOT accept a user-supplied path or an `on_subscribe` callback. The issue's illustrative API is `nexus.register_sse("/events", on_subscribe=...)`.

**Gap.** A new `Nexus.register_sse(path, on_subscribe)` method where `on_subscribe(request) -> AsyncIterator[dict]` is the user's per-subscription handler. The current `register_sse_endpoint` is a higher-level convenience built on top of the EventBus; the new `register_sse` is the lower-level primitive that the EventBus convenience is one consumer of.

**Recommended approach.** Add `register_sse(self, path: str, on_subscribe: Callable[[Request], AsyncIterator[dict]])` to the `Nexus` class. Internal implementation mirrors `sse.py:_sse_generator` but invokes `on_subscribe(request)` instead of subscribing to the EventBus. Preserve the keepalive interval (`_KEEPALIVE_INTERVAL = 15` seconds, `sse.py:32`) and the SSE framing headers (Content-Type, Cache-Control, X-Accel-Buffering — `sse.py:111-116`). The existing `register_sse_endpoint` stays as a higher-level shim that calls the new primitive with an EventBus-backed `on_subscribe`.

**Test.** Tier 2 — register an SSE endpoint at `/events`; the `on_subscribe` yields 3 events; client connects, reads 3 SSE frames + keepalive, disconnects; server cleans up the subscription. Use the existing `tests/integration/test_sse_streaming.py` harness pattern.

## AC-6: `register_websocket` streaming primitive

**Current state — PARTIAL (class-based exists).** `Nexus.register_websocket(path, handler_cls, *, allowed_origins=None)` at `core.py:705` registers a class-based `MessageHandler` subclass. The issue's illustrative API `nexus.register_websocket("/ws", on_message=...)` is a CALLBACK shape, distinct from the class shape.

**Gap.** A callback-based registration shape that is ergonomically lighter than defining a class. Options:

- **Option A (recommended).** Add a callback overload: `register_websocket(path, on_message=..., on_connect=None, on_disconnect=None, allowed_origins=None)` that internally synthesizes a `MessageHandler` subclass with those callbacks as methods. Both shapes coexist; the class shape stays canonical, the callback shape is the FastAPI-parity convenience.
- **Option B.** Add a new method `register_websocket_callback(path, on_message=..., ...)` that does not overload the class-based path. Cleaner API surface but two names for one concept.

Option A preserves the existing import (`from kailash.nexus import Nexus; nexus.register_websocket(...)`) and dispatches by inspecting the second positional / keyword args.

**Recommended approach.** Option A. Dispatch logic at the top of `register_websocket`: if the second argument is a class (subclass of `MessageHandler`), use the current path; if `on_message` is provided, synthesize the handler class internally.

**Test.** Tier 2 — register `nexus.register_websocket("/ws", on_message=lambda conn, msg: conn.send_json({"echo": msg}))`; connect a client via the WebSocket transport; send a message; assert the echo is received. Use the existing `tests/integration/test_websocket_message_handlers.py` pattern.

## AC-7: Migration guide

**Current state — ABSENT.** There is a `packages/kailash-nexus/src/nexus/MIGRATION.md` (referenced in `__init__.py` directory listing) but it covers internal Nexus migration (engine vs. core), not FastAPI → Nexus.

**Gap.** A migration guide at `packages/kailash-nexus/docs/migration-fastapi.md` (or `docs/guides/fastapi-to-nexus.md` — depends on Sphinx layout) covering:

- Auth: FastAPI `Depends(get_current_user)` → Nexus `Depends(get_current_user)` (same import path semantically; the migration is the `kailash.nexus.extractors` import line).
- Typed bodies: FastAPI `body: Pydantic Model` → Nexus handler parameter typed with the model. Inspect whether Pydantic body parsing is in scope; if not, document `Body[dict]` as the immediate path.
- File uploads: FastAPI `UploadFile = File(...)` → Nexus `file: UploadFile`. FastAPI `List[UploadFile]` → Nexus `files: Multipart`.
- SSE: FastAPI `EventSourceResponse` from `sse-starlette` → Nexus `register_sse(path, on_subscribe)`.
- WebSocket: FastAPI `@app.websocket("/ws")` with `WebSocket` parameter → Nexus `register_websocket(path, on_message=...)` callback OR `@app.websocket(path)` class-based (existing).
- Dependency overrides for tests: FastAPI `app.dependency_overrides[real] = mock` → Nexus `with nexus.dependency_overrides.override(real, mock):`.

**Recommended approach.** Author at `packages/kailash-nexus/docs/migration-fastapi.md`. One section per parity surface above. Include a "before / after" code block per section showing the FastAPI shape and the Nexus shape side-by-side. Cap at ~400 lines (per `rules/rule-authoring.md` doc-length norms; migration guides can be longer than rule files).
