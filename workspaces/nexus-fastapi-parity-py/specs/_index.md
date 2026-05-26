# Specs index — Nexus FastAPI parity (workspace-local)

This index lists the workspace-local specs that govern the Nexus FastAPI parity implementation. Per `rules/specs-authority.md` § MUST Rule 7, specialist delegation prompts in `/todos` and `/implement` MUST include the spec content inline.

## Specs

- `nexus-fastapi-parity.md` — Canonical surface contract for `kailash.nexus.extractors`, `Nexus.handler_extract`, `Nexus.dependency_overrides`, `Nexus.register_sse`, and the `register_websocket` callback overload. Authority for the implementation phase.

## Cross-references

The spec cites baseline rules by path (per `rules/cross-cli-artifact-hygiene.md`):

- `rules/zero-tolerance.md` — Rule 3d (dual-shape return + structural guard), Rule 4 (no SDK workarounds), Rule 6 (implement fully).
- `rules/framework-first.md` — Nexus owns HTTP gateway; no new top-level FastAPI dependency.
- `rules/worktree-isolation.md` — Sharding discipline; § 5 (merge-base check), § 6 (branch name match).
- `rules/agents.md` — § Parallel-Worktree Package Ownership Coordination (Shard 5 = version owner).
- `rules/nexus-http-status-convention.md` — MUST Rule 4 (extractor-based handlers return typed status); the new `NexusHandlerError` type lives in `nexus.extractors`.
- `rules/cross-sdk-inspection.md` — Rule 2 (cross-SDK alignment marker required at implementation time).
- `rules/python-environment.md` — Rule 5 (`threading.Lock` is a factory in 3.11+; `DependencyOverrideMap` thread-safety uses captured type constants).

## Cited evidence (audit findings)

- `packages/kailash-nexus/src/nexus/__init__.py:65-110` — Starlette type re-exports; baseline for the extractor surface.
- `packages/kailash-nexus/src/nexus/sse.py:88` — Existing `register_sse_endpoint(nexus)` becomes a higher-level shim over the new primitive.
- `packages/kailash-nexus/src/nexus/core.py:705` — Existing `register_websocket(path, MessageHandler)` extended with callback overload.
- `packages/kailash-nexus/src/nexus/core.py:2738` — Existing `@app.handler` decorator; the new `handler_extract` is a sibling path, not a replacement.
- `packages/kailash-nexus/src/nexus/files.py:18` — `NexusFile` primitive; `Multipart` / `UploadFile` extractors bind to this dataclass for transport-agnostic file handling.
- `packages/kailash-nexus/src/nexus/auth/dependencies.py:5-9` — PEP 563 footgun documentation; the same constraint propagates to all user handler files using `nexus.extractors`.
