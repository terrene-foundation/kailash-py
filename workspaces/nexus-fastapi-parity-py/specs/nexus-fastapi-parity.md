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

## Surface contract

### `kailash.nexus.extractors`

New file `packages/kailash-nexus/src/nexus/extractors/__init__.py`. MUST NOT import `from __future__ import annotations`. Exports:

| Symbol | Kind | Source | Purpose |
| --- | --- | --- | --- |
| `Depends` | Class | New (this module) | Marker for dependency-injection. `x = Depends(callable)`. |
| `Request` | Re-export | `starlette.requests.Request` | Handler annotation; bound to the originating HTTP request. |
| `UploadFile` | Re-export | `starlette.datastructures.UploadFile` | Single-file upload extractor. |
| `Multipart` | Type alias | `list[UploadFile]` | Multi-file upload extractor. |
| `NexusHandlerError` | Class | New (this module) | Typed status return per `rules/nexus-http-status-convention.md` MUST Rule 4. Carries `status_code: int` + `body: dict \| str`. |
| `Bytes` | Class | New (this module) | Raw-bytes body extractor (named in issue body). |

`__all__` enumerates ALL of the above. PEP 562 not required — no callable-module shape here.

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

Thread-safety: `DependencyOverrideMap` is protected by a per-instance lock. Per `rules/python-environment.md` Rule 5, the lock is constructed via `threading.Lock()` factory and the captured type is used for any `isinstance` checks (no direct `isinstance(x, threading.Lock)` — TypeError on 3.11+).

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

Detection: at registration, the resolver attempts `typing.get_type_hints(func, globalns=func.__globals__)`. If the resolved hints are strings (not types), raise `ExtractorPEP563Error` with the file path and line number of the handler.

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

## Cross-SDK marker

Per `rules/cross-sdk-inspection.md` Rule 2, the implementation PR MUST cross-reference the rs sibling tracker (user-provided link, per Q5 in `02-plans/01-architecture.md`). PR body includes:

> Cross-SDK alignment: this is the Python equivalent of <kailash-rs tracker URL>.

The kailash-rs sibling parity surface is OUT OF SCOPE for this analysis per `rules/repo-scope-discipline.md`.

## Implementation gates

Per `rules/agents.md` § Quality Gates — `/implement` is a MUST gate; reviewer + security-reviewer run as parallel background agents at the end of each shard. Reviewer mechanical sweeps:

- `grep -c 'from __future__ import annotations' packages/kailash-nexus/src/nexus/extractors/` → 0 (the extractor module itself must not use PEP 563).
- `grep -rn 'fastapi' packages/kailash-nexus/pyproject.toml` → no NEW top-level dep (FastAPI is allowed as a transitive of the existing `kailash` core).
- `pytest --collect-only packages/kailash-nexus/tests/` → exit 0 (collection gate per `rules/orphan-detection.md` MUST Rule 5).
- `pip check` after Shard 5's bump → clean (per `rules/dependencies.md`).

## Open scope decisions (Q1-Q5 — user gates before /todos)

The five open questions live in `02-plans/01-architecture.md` § "Open questions for the user". The spec assumes the recommended dispositions; if the user widens scope (Q1 → Pydantic in scope; Q3 → Headers / Query / Body in scope), the spec is amended in the same `/todos` round.
