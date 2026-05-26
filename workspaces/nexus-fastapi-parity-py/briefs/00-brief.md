# Brief — Nexus FastAPI Parity (issue #1174)

GitHub issue: `terrene-foundation/kailash-py#1174` — "feat(nexus): expose Depends/Request/dependency_overrides + Multipart/SSE/WebSocket on the Python Nexus shim".

## Parity rationale

A FastAPI application that wants to consolidate onto Nexus as its gateway today loses five surfaces simultaneously: dependency injection (`Depends()`), the request-context object the dependencies bind to (`Request`), the per-test override fixture (`dependency_overrides`), file-upload extractors (`Multipart` / `UploadFile`), and the streaming primitives (`register_sse` / `register_websocket`). The current Python Nexus shim has partial coverage for the streaming primitives (SSE is wired to the EventBus; class-based WebSocket handlers exist) but no public extractor namespace, no dependency injection surface, and no file-upload extractors. Without these surfaces, consolidation requires re-authoring every FastAPI handler — which is exactly the migration friction this issue closes.

The platform value is **single-gateway consolidation**: one Nexus instance serves API + CLI + MCP, with the same handler shape FastAPI users already know. Closing the parity gap means a FastAPI codebase migrates by re-importing extractors from `kailash.nexus.extractors`, not by re-authoring auth, body parsing, file uploads, and streaming end-to-end.

## Severity

MEDIUM — parity item, not a runtime defect. Blocks single-gateway consolidation for FastAPI-based Python consumers.

## Acceptance criteria (verbatim)

- `Depends` extractor on the public Nexus extractor surface, with a test.
- `Request`-equivalent context extractor, with a test.
- `dependency_overrides` test fixture (context-manager + imperative set/clear), with tests.
- `Multipart` + `UploadFile` body extractors, with a test.
- `register_sse` streaming primitive, with a test.
- `register_websocket` streaming primitive, with a test.
- Migration guide covering FastAPI `APIRouter` → Nexus handler re-authoring (auth, typed bodies, file uploads, SSE/WebSocket).
