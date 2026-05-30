# Current Nexus surface — AST audit

## Public package layout

`packages/kailash-nexus/src/nexus/` ships these load-bearing modules (lines verified via `wc -l`):

- `core.py` — 3,732 lines; `Nexus` class, `register_websocket`, `handler`, `register_handler`, `register`, `mount`, `use_middleware`, `websocket_broadcast`, `websocket_send_to`.
- `sse.py` — 127 lines; `register_sse_endpoint(nexus)` mounts `GET /events/stream` for EventBus events.
- `files.py` — 97 lines; `NexusFile` dataclass with `from_upload_file`, `from_path`, `from_base64`, `to_dict`.
- `websocket_handlers.py` — 1,047 lines; `Connection`, `MessageHandler`, `MessageHandlerRegistry` class-based handler surface.
- `transports/{base,http,mcp,websocket,webhook}.py` — transport abstractions.
- `auth/dependencies.py` — 135 lines; FastAPI `Depends()` dependency callables (`get_current_user`, `get_optional_user`).
- `auth/rbac.py` — FastAPI-style `Depends(require_role_dep(...))` patterns.
- `registry.py` — `HandlerDef`, `HandlerParam`, `HandlerRegistry`.

## Public `__init__.py` exports (`packages/kailash-nexus/src/nexus/__init__.py`)

Lines 33-110 import + re-export. Lines 111-202 declare `__all__`. The package re-exports Starlette types (`Request`, `Response`, `StreamingResponse`, `WebSocket`, `HTTPException`) at lines 65-73 / 174-181 so consumers can `from nexus import Request` without importing Starlette directly.

Notably **absent** from `__all__`:

- No `extractors` sub-module exported.
- No `Depends` symbol — the only `Depends` in the codebase is FastAPI's, used inside `auth/dependencies.py` and `auth/rbac.py` docstrings, never re-exported.
- No `Multipart`, `UploadFile`, `Bytes`, `Body`, `Headers`, `Query` extractor namespaces.
- No `dependency_overrides` accessor on the `Nexus` class.
- No `register_sse` top-level export (only `register_sse_endpoint` from `sse.py`).
- `register_websocket` exists as a method on `Nexus` (core.py:705) but not as a top-level free function.

## Handler registration surface

The decorator pattern (`core.py:2738`) is:

```python
@app.handler("greet", description="...")
async def greet(name: str, greeting: str = "Hello") -> dict:
    return {"message": f"{greeting}, {name}!"}
```

`register_handler` (`core.py:2792`) inspects the handler function's parameter signature via `make_handler_workflow(handler_func, node_id="handler", input_mapping=input_mapping)` (line 2841, defined in `kailash.nodes.handler`). It supports `guard` for RBAC but does NOT support FastAPI-style typed extractors — every parameter is treated as a flat input mapped from the channel's input payload.

There is no extractor-trait architecture: a handler cannot today declare `async def upload(files: Multipart) -> dict` and have `files` populated from a multipart body. Type annotations are inspected for the workflow's parameter shape but not consumed as "give me the raw body bytes" / "give me the parsed multipart form" / "give me the Request context".

## `register_websocket` (core.py:705)

The method takes `(path, handler_cls, *, allowed_origins=None)` where `handler_cls` MUST be a subclass of `MessageHandler` from `websocket_handlers.py`. It is **class-based**, not the FastAPI / issue-body shape of `register_websocket("/ws", on_message=...)` with a callback. The issue's illustrative API:

```python
nexus.register_websocket("/ws", on_message=...)
```

does not match the current surface; the current surface is:

```python
@app.websocket("/ws")
class EventStream(MessageHandler):
    async def on_message(self, conn, msg): ...
```

A callback-based `register_websocket(path, on_message=...)` would be a NEW shape, not a wiring of the existing class-based surface. This is a design decision the architecture plan must resolve.

## `register_sse_endpoint` (sse.py:88)

Today's `register_sse_endpoint(nexus)` mounts a fixed `GET /events/stream` endpoint that streams `NexusEvent` objects from the EventBus. It does NOT accept a user-supplied path or an `on_subscribe` callback per the issue's illustrative API:

```python
nexus.register_sse("/events", on_subscribe=...)
```

The issue's API implies user-controlled path + per-subscription handler hook. The current `register_sse_endpoint` ties the endpoint to the EventBus exclusively — there is no per-subscription `on_subscribe` callback shape today.

## `NexusFile` (files.py:18)

`NexusFile` is the transport-agnostic file dataclass. It has `from_upload_file(starlette_upload_file)` that converts a FastAPI/Starlette upload object into the Nexus shape. This means the underlying primitive exists; what is missing is the EXTRACTOR surface that binds a multipart body to a handler parameter typed `Multipart` or `UploadFile`. There is no `Multipart` type alias, no `UploadFile` re-export, and no handler-side extraction.

## What `kailash.nexus.extractors` is

**The module does NOT exist.** `ls packages/kailash-nexus/src/nexus/extractors` → "No such file or directory". The issue's import `from kailash.nexus.extractors import Depends, Request, Bytes, Multipart, UploadFile` resolves to nothing today; the namespace must be created from scratch. There is one prior reference in the rule corpus: `.claude/rules/nexus-http-status-convention.md` § Rule 4 mentions `from kailash.nexus.extractors import Headers` and `from kailash.nexus.extractors import NexusHandlerError, Bytes` — those are forward references to a not-yet-existing module, anticipating this work.

## `dependency_overrides`

No symbol named `dependency_overrides` exists anywhere in `packages/kailash-nexus/`. FastAPI's `app.dependency_overrides: dict` is the reference pattern (a mutable mapping from dependency callable → override callable, scoped via context manager or per-test setUp/tearDown). Implementing this on Nexus requires (a) the `Depends`-based dependency resolution path (so there's something TO override), AND (b) a context manager + imperative API on the `Nexus` instance.

## Summary table

| Concept | Status today | File:line |
| --- | --- | --- |
| `kailash.nexus.extractors` module | ABSENT | — |
| `Depends` extractor | ABSENT (FastAPI's `Depends` used internally) | — |
| `Request` extractor | PARTIAL — Starlette `Request` re-exported (`__init__.py:71/176`) but not as a handler extractor | `__init__.py:71` |
| `dependency_overrides` fixture | ABSENT | — |
| `Multipart` extractor | ABSENT (`NexusFile` primitive exists) | `files.py:18` |
| `UploadFile` extractor | ABSENT (`NexusFile.from_upload_file` exists) | `files.py:45` |
| `register_sse(path, on_subscribe=...)` | PARTIAL — `register_sse_endpoint(nexus)` exists but is EventBus-only with fixed path | `sse.py:88` |
| `register_websocket(path, on_message=...)` callback shape | ABSENT (class-based `register_websocket(path, MessageHandler)` exists) | `core.py:705` |
| Migration guide | ABSENT | — |
