# Risks and cross-cutting concerns

## Risk 1: Extractor architecture is a new surface, not a wrapper

The current `register_handler` (`core.py:2792-2862`) is parameter-name-driven: handler params are flat inputs in the workflow. Adding an EXTRACTOR-AWARE registration path requires inspecting parameter annotations + default values (where `Depends(...)` lives) at registration time, building a per-handler resolver chain, and running that chain on every invocation before the handler body executes. This is fundamentally a new code path, not a small wrapper over `make_handler_workflow`. Implementation surface is meaningful (estimated 300–500 LOC of load-bearing logic for the resolver + dispatch + override map).

The implication for sharding: AC-1 + AC-2 + AC-3 + AC-4 share the resolver chain (every extractor flows through the same registration path). They cannot be cleanly split across worktrees branched from independent SHAs — the resolver lives in one file, and parallel shards editing it would re-introduce the merge-loss class the per-shard plan must avoid (per `rules/worktree-isolation.md` § 5).

## Risk 2: PEP 563 / `from __future__ import annotations` is a footgun

`auth/dependencies.py:5-9` documents the gotcha: FastAPI inspects parameter annotations at RUNTIME to identify special types. PEP 563 turns them into strings; FastAPI cannot resolve `Request` as a type. Every Nexus extractor module + every user handler module that uses extractors MUST NOT import `from __future__ import annotations`. The architecture plan needs to:

- State this explicitly in the migration guide.
- Add a `/redteam` mechanical sweep that greps for `from __future__ import annotations` in any file that imports from `kailash.nexus.extractors`.
- Document in the extractor module's own docstring + the handler-extraction protocol.

## Risk 3: `Pydantic` typed bodies — scope creep

The issue's "Migration guide covering FastAPI APIRouter → Nexus handler re-authoring (auth, typed bodies, file uploads, SSE/WebSocket)" mentions typed bodies. Pydantic body parsing is a sub-feature with non-trivial implementation: FastAPI uses Pydantic schemas for request validation + automatic OpenAPI generation. Nexus has an `OpenApiGenerator` (`openapi.py`) that could integrate. Decision required: is Pydantic body parsing in scope for this shard, or deferred? Recommendation in the architecture plan: defer Pydantic parsing to a follow-up; ship the migration guide with `Body[dict]` as the immediate-term shape and link the Pydantic follow-up issue.

## Risk 4: `register_websocket` overload — type-dispatch on positional argument

The Option A approach in `02-fastapi-parity-gaps.md` AC-6 overloads the second positional argument of `register_websocket`. Today it's `handler_cls` (a class). Tomorrow it would dispatch on `isinstance(arg, type) and issubclass(arg, MessageHandler)` vs. `on_message` keyword present. Two implication classes:

- **API ambiguity** — if a user passes `register_websocket("/ws", SomeRandomClass)` where `SomeRandomClass` is NOT a `MessageHandler` subclass, the error surface matters. Today it raises at handler invocation; with dispatch, it could raise at registration or fall through unpredictably.
- **`rules/zero-tolerance.md` Rule 3d** — Dual-shape return + structural guard = silent fallback. The dispatch here is symmetrical (Dual-shape PARAMETER + structural guard) and triggers the same failure-mode class. The fix per the rule is: dispatch on a discriminator (isinstance check on the SECOND arg with a clear error path), NOT a `hasattr` / duck-type check.

## Risk 5: Cross-SDK parity tracking

Issue #1174 is filed as a parity tracker so the two SDKs (kailash-py and kailash-rs) converge on this surface. Per `rules/cross-sdk-inspection.md`, the resolution disposition MUST inspect whether the same gap exists in the sibling SDK. This analysis cannot do that (the worktree is scoped to kailash-py per `rules/repo-scope-discipline.md`), but the implementation MUST file a cross-SDK alignment marker per `rules/cross-sdk-inspection.md` Rule 2. The byte-vector pin discipline (Rule 4) does NOT apply here — this is API-shape parity, not hash-helper byte parity.

## Risk 6: FastAPI dependency — do not add as a top-level Nexus dependency

Per the Framework-First mandate in `rules/framework-first.md`: Nexus IS the FastAPI replacement. Adding FastAPI as a top-level dependency for the extractor surface would invert the relationship. The HTTP transport already uses FastAPI internally (`transports/http.py`); the extractor surface MUST NOT introduce a new top-level FastAPI requirement. Re-exporting Starlette types (which FastAPI is built on) is fine — Starlette is the ASGI foundation, not the FastAPI brand surface.

## Cross-cutting concern: sub-package boundary

This is `packages/kailash-nexus/` work — the kailash-nexus sub-package is the version owner (per `rules/agents.md` § Parallel-Worktree Package Ownership Coordination). The implementation MUST NOT edit `src/kailash/` core SDK files unless a hot-path dependency surfaces (e.g., `kailash.nodes.handler::make_handler_workflow` may need an extractor-aware variant). If a core SDK change is required, it is a separate shard with version-owner discipline applied.

## Cross-cutting concern: migration guide is docs-only

AC-7 is documentation. Per `rules/zero-tolerance.md` Rule 6: implement fully, no half-implementations. The migration guide MUST cover all five surfaces (auth, typed bodies, file uploads, SSE, WebSocket); landing it as a stub with "Pydantic section TBD" is BLOCKED. If Pydantic body parsing is deferred (Risk 3), the migration guide ships with the deferred-section documented as deferred and a link to the follow-up issue.

## Pros and cons of doing this work at all

Per `rules/recommendation-quality.md` MUST-3 (symmetric pros and cons):

**Pros.**

- Closes the single-gateway-consolidation gap explicitly named in the issue. FastAPI codebases consolidate by import re-pointing, not re-authoring.
- Establishes the extractor architecture as a Nexus surface, opening the door to follow-on extractors (`Query`, `Headers`, `Body[Model]`, `Form`, etc.) that other consumers want.
- The `register_sse(path, on_subscribe)` primitive is a useful generalization of the EventBus-locked `register_sse_endpoint` — both shape and EventBus-fixed-path consumers benefit.
- Aligns with the rs sibling's parity tracker (EATP D6 cross-SDK semantics convergence).

**Cons.**

- Adds an extractor architecture that becomes a maintenance burden as FastAPI evolves — every new FastAPI extractor type users want (`File`, `Form`, `Header`, `Cookie`, ...) becomes a follow-up shard.
- The `register_websocket` overload (Risk 4) is a structural ambiguity that needs careful API design; getting it wrong means the FastAPI-shape and class-shape diverge in invocation semantics.
- Migration-guide upkeep tracks two surfaces (FastAPI's evolving APIs + Nexus's parity) — every FastAPI minor release that adds an extractor type leaves the guide stale until a sync pass.
- Adds dependency surface area to test (Pydantic, multipart parsing, SSE async-iterator semantics, WebSocket-callback handshake). Tier 2 coverage expectation grows proportionally.

The cons are real but bounded; the pros directly close the parity gap the issue was filed to fix. Recommendation in the architecture plan: proceed, with Pydantic body parsing scoped OUT of this shard.
