# kailash-mcp Changelog

All notable changes to the Kailash MCP package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.8] - 2026-04-21 — MCP elicitation error code cross-SDK parity (#572)

### Fixed

- **`ElicitationSystem` now emits MCP 2025-06-18 spec-compliant JSON-RPC error codes** on the wire — matching kailash-rs byte-for-byte per `rules/cross-sdk-inspection.md` (issue #572 / kailash-rs#471). Prior releases emitted positive application codes (`REQUEST_CANCELLED = 1007`, `REQUEST_TIMEOUT = 1006`) which are NOT valid JSON-RPC wire codes; MCP clients written against the spec did not recognize them as the documented conditions. Now:
  - Client decline / cancel → `MCP_REQUEST_CANCELLED = -32800` (was `REQUEST_CANCELLED = 1007`)
  - Response timeout → `MCP_ELICITATION_TIMEOUT = -32001` (was `REQUEST_TIMEOUT = 1006`)
  - Schema validation failure → `MCP_SCHEMA_VALIDATION = -32602` (alias of existing `INVALID_PARAMS`, already correct)
- **New `MCPErrorCode` enum members** for MCP wire parity: `MCP_REQUEST_CANCELLED`, `MCP_ELICITATION_TIMEOUT`, `MCP_TRANSPORT_REBOUND`, `MCP_SCHEMA_VALIDATION`. The legacy positive codes (`REQUEST_CANCELLED`, `REQUEST_TIMEOUT`) remain for non-wire application use; wire-path code paths MUST use the `MCP_*` prefix.
- **Pin-value regression test** at `packages/kailash-mcp/tests/unit/test_elicitation_error_codes_parity.py` — nine assertions covering enum values, `MCPError` wire serialization, and a source-level grep that ElicitationSystem uses the `MCP_*` constants. If a future refactor reverts to `REQUEST_CANCELLED` / `REQUEST_TIMEOUT` on the wire the grep assertion fails loudly.

### Cross-SDK

- Canonical source: MCP specification 2025-06-18 / JSON-RPC 2.0 reserved ranges. kailash-rs landed these values first in PR #464 (Rust) with a pin-value regression test; kailash-py aligns here.
- `specs/mcp-server.md` § "Error Semantics" now documents the four wire codes and the kailash-py ↔ kailash-rs constant mapping.

## [0.2.7] - 2026-04-20 — post-release audit hotfix (SPDX headers)

Post-release `/redteam` audit of 0.2.6 (gold-standards-validator HIGH-1) surfaced missing SPDX license headers on the two files most heavily modified by the #556 ElicitationSystem redesign. 4-line docs-hygiene fix.

### Fixed

- **`advanced/features.py` + `server.py` now carry `SPDX-License-Identifier: Apache-2.0` + `Copyright 2026 Terrene Foundation`** — matching the house convention already used by the other 20 kailash-mcp production modules. Both files previously started with a bare `"""..."""` docstring per `rules/terrene-naming.md` (Apache-2.0 labeling) violation. No behavior change.

## [0.2.6] - 2026-04-20 — elicitation/create sender half (#556)

### Added

- **`ElicitationSystem.__init__(send=...)` + `bind_transport(send)`** — injected async send-callable decouples `ElicitationSystem` from the `BaseTransport` class hierarchy. Testable with any `Callable[[dict], Awaitable[None]]`. Aligns with `rules/orphan-detection.md` §1 (facade with production call site) via `MCPServer.elicitation_system` + `_bind_elicitation_transport()` hook.
- **MCP 2025-06-18 spec-compliant wire shape** — `_send_elicitation_request` now serializes `{"jsonrpc": "2.0", "id": request_id, "method": "elicitation/create", "params": {"requestId": ..., "message": prompt, "requestedSchema": schema}}` and dispatches through the bound send-fn. `ElicitResult.action == "accept"` routes to `provide_input`; `"decline"` / `"cancel"` raise `MCPError(REQUEST_CANCELLED)`.
- **`specs/mcp-server.md §4.9`** expanded from 2 lines to full contract: construction (`send=` or `bind_transport`), wire shape, error semantics, security contract (schema validation before return-to-caller prevents prompt-injection-adjacent attacks).
- **6 Tier 2 integration tests** at `tests/integration/mcp_server/test_elicitation_integration.py` covering in-process send/receive pair round-trip, unbound-send typed-error path, JSON-RPC wire-shape assertion, schema-validation-on-response, silent-send timeout, bind_transport idempotent replace.

### Changed

- **`_send_elicitation_request` error contract** — raises `MCPError(INVALID_REQUEST)` with actionable message naming `bind_transport` when no send is bound. Replaces the prior `NotImplementedError`.
- **`ElicitationSystem` constructor** — now accepts optional `send: Callable[[Dict], Awaitable[None]] | None = None` (backward-compatible; existing callers passing no arg continue to work until they invoke `request_input`).

### Fixed

- Closes #556. Half-implemented public feature (receive half wired, sender half `NotImplementedError`) per `rules/orphan-detection.md` §2a (crypto-pair pattern applied to paired APIs).
- Cross-SDK parity issue filed at `esperie-enterprise/kailash-rs#443` — Rust SDK has no elicitation surface; Python shape documented as reference for future Rust implementation.

## [0.2.5] - 2026-04-19 — oauth.py optional-extras gating (#514)

### Fixed

- **`oauth.py` module-level imports of optional extras (#514, PR #518)**: `kailash_mcp/auth/oauth.py` imported `aiohttp`, `PyJWT`, and `cryptography` at module scope. All three are declared optional under `[project.optional-dependencies] auth-oauth`. On a bare `pip install kailash-mcp` (no oauth extra), any `import kailash_mcp` transitioned to an `ImportError` through the auth sub-package. Fix: wrap the three imports in `try/except ImportError` with `None` fallbacks; add `_require_oauth_extras()` helper that raises a descriptive `ImportError` naming `pip install 'kailash-mcp[auth-oauth]'` when OAuth classes are instantiated without the extra. Module now imports cleanly without the oauth extra; OAuth classes fail loudly with an actionable error instead of silently. Aligns with `rules/dependencies.md` § "Declared = Gated Consistently" and cross-SDK parity with kailash-rs#417.

## [0.2.4] - 2026-04-14

### Fixed

- All 63 unit test warnings resolved (combined with kailash 2.8.6 release).

## [0.2.3] - 2026-04-08

### Added

- Initial platform server, auth JWT/OAuth, and MCP client/server implementations.
