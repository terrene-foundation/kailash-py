# Architecture plan — Nexus FastAPI parity (issue #1174)

## Goal

Ship the seven acceptance criteria of issue #1174 in `packages/kailash-nexus/` such that a FastAPI codebase can re-author its handlers against `kailash.nexus.extractors` and Nexus's `register_sse` / `register_websocket` callback shapes, retaining auth, typed bodies (where in scope), file uploads, SSE, and WebSocket surfaces. Ship a migration guide that walks a user through the re-authoring step-by-step.

## Brief corrections

The brief in `briefs/00-brief.md` is accurate against the audited Nexus surface. One semantic clarification surfaced during the audit (recorded here for the `/todos` phase):

1. **`register_sse` is a NEW primitive, not a rewrite.** The existing `register_sse_endpoint(nexus)` in `sse.py` is EventBus-locked with a fixed path. The issue's `register_sse(path, on_subscribe)` is a new lower-level primitive. The existing endpoint stays as a higher-level shim. No removal, no breaking change.
2. **`register_websocket` is an OVERLOAD, not a replacement.** The current class-based `register_websocket(path, MessageHandler)` (core.py:705) stays. The new callback shape `register_websocket(path, on_message=...)` is a sibling overload dispatching on the second positional argument's type.
3. **The issue's illustrative `Request` import** matches Starlette's `Request` (already re-exported at `nexus/__init__.py:71`). The extractor surface adds a `Request` re-export under `nexus.extractors` for ergonomics; a new `NexusRequest` cross-transport context object is an additional follow-up (out of scope for this shard unless cross-transport request context surfaces in implementation).

## Invariants (the architecture MUST hold these)

Holding 6 invariants across the implementation (within the autonomous-execution §1 ≤5–10 budget):

1. **Extractor resolver is one chain.** Every extractor (`Depends`, `Request`, `Multipart`, `UploadFile`, `Body`, `Headers`, `Query`) flows through one resolver. Per-handler the resolver is built once at registration; per-invocation the resolver runs once before handler dispatch.
2. **`dependency_overrides` consults the override map before resolving every `Depends`.** No exceptions; the override map is the single dispatch point for test injection.
3. **PEP 563 incompatibility is loud, not silent.** Files that use `from __future__ import annotations` AND import from `nexus.extractors` MUST raise at registration with a typed error naming the file, not silently mis-resolve.
4. **Existing surfaces stay backwards-compatible.** `register_handler` / `@app.handler` continue to work for non-extractor handlers (flat input mapping). `register_websocket(path, MessageHandler)` continues to work. `register_sse_endpoint(nexus)` continues to work.
5. **Sub-package version-owner discipline.** All changes land in `packages/kailash-nexus/`. Bumps to `pyproject.toml` + `nexus/__init__.py::__version__` + CHANGELOG land in one shard's commit (designated version-owner).
6. **No new top-level FastAPI dependency.** Re-exports from Starlette are fine; the package MUST NOT add `fastapi` as a direct top-level dependency of the extractor surface.

## Surface contracts (what ships, exactly)

### `kailash.nexus.extractors` module

New module `packages/kailash-nexus/src/nexus/extractors/__init__.py`:

```python
# extractor sentinel — used as default value: x = Depends(callable)
class Depends:
    def __init__(self, callable_: Callable[..., Any]) -> None: ...

# re-exports for handler annotation
from starlette.requests import Request  # noqa: F401
from starlette.datastructures import UploadFile  # noqa: F401

# typed alias for multipart-list
Multipart = list[UploadFile]

# Optional: NexusHandlerError + typed-status returns
# (referenced in rules/nexus-http-status-convention.md MUST Rule 4)
class NexusHandlerError(Exception):
    def __init__(self, status_code: int, body: dict | str) -> None: ...

# Optional extractors for completeness (NOT all required by AC):
# Bytes, Headers, Query, Body — scope decision at /todos
```

`__all__` enumerates: `Depends`, `Request`, `UploadFile`, `Multipart`, `NexusHandlerError`. Bytes/Headers/Query/Body are RECOMMENDED additions for completeness but not load-bearing for the AC; final scope decision at `/todos`.

### `Nexus.handler_extract` registration path

New method on `Nexus` (alongside the existing `register_handler` / `@app.handler`):

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
) -> None: ...
```

Inspects `func`'s parameter list. For each parameter:

- If the default is a `Depends(callable)` instance → schedule dependency resolution.
- If the annotation is `Request` / `UploadFile` / `Multipart` / `NexusFile` → schedule extractor binding from the request.
- Otherwise → treat as a flat input (existing `register_handler` semantics).

Builds a per-handler `ResolverChain` that runs at every invocation. Hooks into the same HandlerNode workflow path as `register_handler` but with the resolver wrapping the handler body.

### `Nexus.dependency_overrides`

New attribute on `Nexus`:

```python
class DependencyOverrideMap:
    def override(self, real: Callable, mock: Callable) -> ContextManager: ...
    def set(self, real: Callable, mock: Callable) -> None: ...
    def clear(self, real: Callable) -> None: ...
    def clear_all(self) -> None: ...
    def __contains__(self, real: Callable) -> bool: ...
    def __getitem__(self, real: Callable) -> Callable: ...

class Nexus:
    dependency_overrides: DependencyOverrideMap
```

The `Depends` resolver checks `nexus.dependency_overrides` first; if a real → mock mapping is present, resolves to the mock instead. Thread-safe (per `rules/python-environment.md` Rule 5).

### `Nexus.register_sse`

New method:

```python
async def register_sse(
    self,
    path: str,
    on_subscribe: Callable[[Request], AsyncIterator[dict]],
    *,
    keepalive_interval: int = 15,
) -> None: ...
```

Implementation mirrors `sse.py:_sse_generator` (existing 127-line module). The user-supplied `on_subscribe(request)` returns an async iterator of dicts; each dict serializes to a `data: {...}\n\n` SSE frame. Keepalive comments fire at `keepalive_interval` seconds. SSE-canonical headers (Content-Type: text/event-stream, Cache-Control: no-cache, X-Accel-Buffering: no). The existing `register_sse_endpoint(nexus)` is refactored to call `register_sse` with an EventBus-backed `on_subscribe` — internally consolidating the implementation.

### `Nexus.register_websocket` callback overload

Existing method at `core.py:705`. Extend with callback shape:

```python
def register_websocket(
    self,
    path: str,
    handler_cls_or_none: type | None = None,
    *,
    on_message: Optional[Callable[[Connection, dict], Awaitable[None]]] = None,
    on_connect: Optional[Callable[[Connection], Awaitable[None]]] = None,
    on_disconnect: Optional[Callable[[Connection], Awaitable[None]]] = None,
    allowed_origins: Optional[List[str]] = None,
) -> Any: ...
```

Dispatch logic at the top:

- If `handler_cls_or_none` is provided AND is a class subclass of `MessageHandler` → existing class-based path.
- If `on_message` is provided AND `handler_cls_or_none` is None → synthesize a `MessageHandler` subclass with the provided callbacks; register via the existing path.
- If both / neither → raise `ValueError` with a clear message naming the BLOCKED case (per `rules/zero-tolerance.md` Rule 3d — dispatch on a discriminator, not a structural guard).

### Migration guide

New file `packages/kailash-nexus/docs/migration-fastapi.md` (Sphinx-rendered). One section per surface:

1. **Auth** — FastAPI `Depends(get_current_user)` → Nexus `Depends(get_current_user)` re-imported from `nexus.extractors`.
2. **Typed bodies** — `Body[dict]` immediate path; Pydantic `Model` deferred to follow-up.
3. **File uploads** — FastAPI `UploadFile = File(...)` → Nexus `file: UploadFile`. FastAPI `List[UploadFile]` → Nexus `files: Multipart`.
4. **SSE** — FastAPI `EventSourceResponse` from `sse-starlette` → Nexus `register_sse(path, on_subscribe)`.
5. **WebSocket** — FastAPI `@app.websocket("/ws")` + `WebSocket` parameter → Nexus `register_websocket(path, on_message=...)` callback OR existing `@app.websocket(path)` class-based.
6. **Tests** — FastAPI `app.dependency_overrides[real] = mock` → Nexus `with nexus.dependency_overrides.override(real, mock):`.

Each section: ~30-line FastAPI snippet, ~30-line Nexus equivalent, prose explaining the mapping. ~300-400 lines total.

## Sharding (per `rules/autonomous-execution.md` § Per-Session Capacity Budget)

Five shards. Dependency arrows below; the version-owner shard (Shard 1) bumps `pyproject.toml` + `__version__` + CHANGELOG once at the end (release-prep PR per `rules/git.md` § Release-Prep PRs).

### Shard 1 — Extractor module + `Request` extractor + `Depends` extractor + handler_extract path

**Surface.** New `nexus/extractors/__init__.py` (~80 LOC). New `Nexus.handler_extract` method (~150 LOC). Resolver chain primitive (~200 LOC). Total: ~430 LOC of load-bearing logic. Within the ≤500 LOC + ≤5–10 invariants budget.

**Invariants held.** Invariants 1, 3, 4, 6 from the list above.

**Tests.** Tier 2 — register `async def whoami(request: Request) -> dict` + `async def auth(user=Depends(get_user)) -> dict`; invoke via HTTP; assert correct binding. PEP 563 rejection test (a fixture file with `from __future__ import annotations` raises at registration).

**Value anchor.** Issue #1174 ACs 1 + 2.

### Shard 2 — `dependency_overrides` test fixture

**Surface.** New `DependencyOverrideMap` class (~80 LOC). Wire into `Depends` resolution (~30 LOC of changes in Shard 1's resolver). Total: ~110 LOC. Well within budget.

**Depends on.** Shard 1 (the `Depends` resolver path is where override is consulted).

**Invariants held.** Invariant 2.

**Tests.** Tier 2 — context-manager override; imperative set / clear; restore after exit; thread-safety (concurrent overrides on the same instance from two threads).

**Value anchor.** Issue #1174 AC 3.

### Shard 3 — `Multipart` + `UploadFile` extractors

**Surface.** Add `Multipart` + `UploadFile` to `nexus/extractors/__init__.py`. Wire HTTP-transport multipart parsing into the resolver chain (~120 LOC, mostly transport-bridge code reading the multipart form via Starlette's existing parser). Total: ~150 LOC. Within budget.

**Depends on.** Shard 1 (resolver chain).

**Invariants held.** Invariants 1, 4.

**Tests.** Tier 2 — POST a multipart body with 3 files; assert `Multipart` parameter is a list of 3 `UploadFile`. Single-file `UploadFile` test.

**Value anchor.** Issue #1174 AC 4.

### Shard 4 — `register_sse` + `register_websocket` callback overload

**Surface.** New `Nexus.register_sse(path, on_subscribe)` (~80 LOC, mostly mirroring `sse.py:_sse_generator`). Refactor `register_sse_endpoint` to call `register_sse` (~20 LOC). Extend `register_websocket` with callback overload + dispatch logic (~80 LOC). Total: ~180 LOC. Within budget.

**Independent of Shard 1-3.** Streaming primitives are orthogonal to the extractor surface — they can land in parallel.

**Invariants held.** Invariants 4, 6.

**Tests.** Tier 2 — SSE endpoint streams 3 events; WebSocket callback echoes a message. Both use the existing test infrastructure at `tests/integration/test_sse_streaming.py` + `test_websocket_message_handlers.py`.

**Value anchor.** Issue #1174 ACs 5 + 6.

### Shard 5 — Migration guide + version-owner bump

**Surface.** New `packages/kailash-nexus/docs/migration-fastapi.md` (~350 LOC of prose + code samples). Bump `pyproject.toml` from current version + `nexus/__init__.py::__version__` + CHANGELOG entry. Docs-only + metadata; ~400 LOC total but all docs/metadata, none load-bearing.

**Depends on.** Shards 1, 2, 3, 4 all landed (the guide cites all six surfaces).

**Invariants held.** Invariant 5 (version-owner discipline — this shard IS the version owner).

**Tests.** Documentation lint (sphinx-build or markdown-lint per the project's docs convention). No code tests required for docs.

**Value anchor.** Issue #1174 AC 7.

### Sharding summary

```
Shard 1 (extractor + Depends + Request + handler_extract)  ─┐
                                                            ├─► Shard 5 (guide + version bump)
Shard 2 (dependency_overrides)                              │
                                                            │
Shard 3 (Multipart + UploadFile)                            │
                                                            │
Shard 4 (register_sse + register_websocket callback) ────────┘
```

Shards 1 + 4 can run in parallel from the same base SHA (different files; resolver vs streaming). Shards 2 + 3 each depend on Shard 1. Shard 5 depends on all four. Wave plan:

- **Wave 1.** Shards 1 + 4 in parallel (2 worktrees, both from current main HEAD).
- **Wave 2.** Shards 2 + 3 in parallel after Wave 1 merges (2 worktrees, from new main HEAD post-Wave-1).
- **Wave 3.** Shard 5 (version owner; docs-only).

Per `rules/worktree-isolation.md` § 4 — waves of ≤3 satisfy the burst limit. Per § 5 — every worktree branches from the CURRENT main HEAD at launch (waves are sequential at the wave boundary).

## Total LOC estimate

| Shard | Load-bearing LOC | Test LOC | Docs LOC |
| --- | --- | --- | --- |
| 1 | ~430 | ~200 | ~50 |
| 2 | ~110 | ~150 | ~30 |
| 3 | ~150 | ~150 | ~30 |
| 4 | ~180 | ~200 | ~30 |
| 5 | 0 (metadata only) | 0 | ~400 |
| **Total** | **~870 load-bearing** | **~700 test** | **~540 docs** |

The ~870 LOC of load-bearing logic exceeds one session's per-shard budget if landed as a single shard — exactly why the five-shard split exists.

## Open questions for the user (gate before /todos)

Q1 and Q3 below are CLOSED (resolved with named primary recommendation); Q2 and Q4 are RETAINED as yes/no confirmations; Q5 is converted to a USER-ACTION-REQUIRED gate per HIGH-R3 of the R1 amendments.

1. **Pydantic body parsing — Q1 CLOSED, recommendation:** ship `Body[T]` extractor accepting any object with `model_validate(...)` classmethod OR `__init__(**dict)` shape, matching the existing `Decoder` protocol pattern at `packages/kailash-nexus/src/nexus/typed_service_client.py:284` (the `Decoder = Callable[[Any, Type[Any]], Any]` alias) and the per-instance `register_decoder` mechanism (`typed_service_client.py:330`). Pydantic remains OPTIONAL — SDK users can use dataclasses, attrs, msgspec, OR Pydantic. The `Body[T]` extractor invokes the registered decoder OR falls back to `T(**dict)` for dataclass-shape models. **Confirm Pydantic-optional via Decoder protocol (y/n)?**

   - Pro: keeps the extractor surface lean and library-agnostic; mirrors an existing Nexus convention so SDK users learn one decoder model.
   - Con: SDK users on Pydantic ship two lines per model to register the decoder; library-agnostic comes with library-specific glue per model.

2. **`NexusRequest` cross-transport context.** RETAINED as real two-layer decision. Recommendation: ship HTTP-only Starlette `Request` re-export in `nexus.extractors` for this shard; introduce a `NexusRequest` cross-transport context object in a follow-up issue WHEN WebSocket / SSE / CLI handler-extract surfaces land. The current shard does not need cross-transport unification — `register_websocket` callback handlers receive `Connection` (not `Request`), and `register_sse`'s `on_subscribe(request)` is HTTP-bound by definition. **Confirm two-layer staging — HTTP-only `Request` now, `NexusRequest` follow-up later (y/n)?**

   - Pro: simpler resolver in Shard 1; the cross-transport context only matters when handlers cross channels, which the current AC set does not require.
   - Con: the migration guide cannot promise "the same handler signature works on every channel" until `NexusRequest` ships.

3. **Extractor surface scope — Q3 CLOSED, recommendation:** ship `Headers` + `Bytes` + `NexusHandlerError` alongside `Depends` + `Request` + `Multipart` + `UploadFile` in Shard 1. Per `rules/nexus-http-status-convention.md` MUST Rule 4 (canonical extractor surface), `Headers`, `Bytes`, and `NexusHandlerError` are NAMED as committed surface symbols — they are not optional. `Query` and `Body` are additional and out of scope for this shard; defer to a follow-up issue if not in the 7 ACs of issue #1174. **Confirm Headers + Bytes + NexusHandlerError land in Shard 1 per rules/nexus-http-status-convention.md MUST-4; Query + Body deferred to follow-up (y/n)?**

   - Pro: closes the surface contract the typed-status convention already commits to; SDK users get one ergonomic shape on day one.
   - Con: Shard 1 is closer to its budget ceiling — consider splitting per MED-R1 below.

4. **`register_websocket` overload signature stability.** RETAINED as A vs B confirm. Recommendation: Option A (single-method overload with discriminator dispatch per `rules/zero-tolerance.md` Rule 3d — `isinstance(arg2, type) and issubclass(arg2, MessageHandler)` for the class path; `on_message is not None and arg2 is None` for the callback path; both / neither raises `ValueError`). **Confirm Option A — single-method overload (y/n)?**

   - Pro: API surface doesn't grow (one method, two shapes); existing callers' import line is unchanged; FastAPI-parity ergonomics for new callers.
   - Con: dispatch logic carries failure-mode risk if implemented carelessly — both branches MUST have direct Tier-2 tests per `rules/testing.md` § "One Direct Test Per Variant In Every Delegating Pair" (BLOCKED to ship only the class-path test and assume callback is covered by delegation).

5. **Cross-SDK marker — USER-ACTION-REQUIRED gate at /todos.** Per HIGH-R3 of the R1 amendments + `rules/repo-scope-discipline.md`, this session does NOT reach into `terrene-foundation/kailash-rs` to discover or create the tracker URL. At /todos approval, the user EITHER provides the existing rs tracker URL (which the implementation PR will cite) OR confirms "no rs sibling tracker yet, ship without the cross-SDK marker." Per `rules/spec-accuracy.md`, literal `<placeholder>` text is BLOCKED in a spec — Q5 is resolved when the user provides the URL or the no-tracker confirmation, NOT by the agent inferring it.

## /todos disposition

This analysis ships an architecture plan; it does NOT mark the workspace as ready-for-todos. Q1 and Q3 are CLOSED in this R1 amendment pass; Q2, Q4, and Q5 retain yes/no confirms or the USER-ACTION-REQUIRED gate for cross-SDK. Recommendation: schedule a `/todos` gate after the user resolves Q2, Q4, and Q5.

## Brief verification cycle

Per `rules/agents.md` § Parallel Brief-Claim Verification, this session ran parallel deep-dive verification against all 7 ACs in the brief. Results were recorded in the R1 reviewer pass: analyst confirmed all 7 ACs TRUE against the audited Nexus surface with minor cosmetic line-number drift in `01-analysis/02-fastapi-parity-gaps.md` (`__init__.py:71` → `:70`, `:176` → `:174`, `files.py:18` → `:19`). All drift amended in this R1 pass.

## Shard 1 split note (MED-R1)

Consider splitting Shard 1 into:

- **Shard 1a (~80 LOC).** Extractor module skeleton (`packages/kailash-nexus/src/nexus/extractors/__init__.py`) + `Request` re-export + `Headers` + `Bytes` + `NexusHandlerError`. These are committed names per `rules/nexus-http-status-convention.md` MUST Rule 4 and ship without the resolver chain.
- **Shard 1b (~350 LOC).** `Depends` resolver + per-handler `ResolverChain` + `handler_extract` registration path. Depends on Shard 1a's `Headers` and `Bytes` symbols.

Decision deferred to /todos. Per `rules/autonomous-execution.md` MUST Rule 1, the split MUST be made before /implement if any of the per-shard budget thresholds (≤500 LOC load-bearing, ≤5–10 invariants, ≤3–4 call-graph hops) would otherwise be exceeded.
