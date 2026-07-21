# kailash-mcp Changelog

All notable changes to the Kailash MCP package will be documented in this file.

## [0.4.2] — 2026-07-19 — Dependency pin fix: require kailash>=2.56.0

### Fixed

- **`kailash>=2.50.0` pin was too low for the 0.4.1 `mask_error_text` import.**
  0.4.1 (below) made `transports.py` import `mask_error_text` from
  `kailash.utils.url_credentials` — a helper new in `kailash` 2.56.0. A user
  on core `>=2.50.0,<2.56.0` satisfied the declared pin but hit
  `ImportError` at `import kailash_mcp`. The pin now reads
  `kailash>=2.56.0`.

## [0.4.1] — 2026-07-19 — Credential-bearing exception logs sanitized (#1840)

### Security

- **SSE / StreamableHTTP / WebSocket transports no longer leak `base_url`
  credentials into logs or exception text (#1840).** A credential-bearing
  `base_url`/`url` (e.g. `https://user:secret@host?token=abc`) was
  interpolated verbatim into the "transport connected" `logger.info` line
  and into the opaque `{e}` of every `TransportError` raised on
  connect/send/receive — readable by anyone with log access. URL-value log
  lines now route through `mask_url`; opaque `{e}` strings route through the
  new `mask_error_text` helper (both from the shared
  `kailash.utils.url_credentials` module — no per-transport copies). A
  round-1 sweep also closed the same class in `_close_server_session`'s
  swallowed-exception log and the SSE / WebSocket read-loop error logs.
  `stdio` (subprocess command, no URL) and `WebSocketServerTransport` (local
  bind, no client credential) carry no credential surface and are
  unaffected.

## [0.4.0] — 2026-07-16 — Server-initiated request/response lifecycle hardening (#1712)

Completes the #1712 MCP 2025-11-25 work. The 2025-11-25 wire surface
(`sampling/createMessage`, `elicitation/create`, `roots/list`, progress,
cancellation, completion, logging) shipped in the 0.3.x line; this release makes
the **server-initiated** request/response lifecycle correct and concurrency-safe.
No new wire methods — the changes harden the existing surface.

### Fixed

- **Single-client server-initiated round-trips no longer deadlock.** The native
  WebSocket server transport now dispatches each inbound message in its own task,
  so the read loop keeps draining the socket while a tool handler awaits a
  server-initiated reply (sampling / elicitation / roots) that arrives on the SAME
  connection. Previously the handler blocked until its timeout.
- **A server-initiated reply reaches the original requester.** The model
  completion / elicitation result / roots list is routed back to the client that
  owns the pending request (previously the sampling reply could be dropped with a
  spurious `-32601`).
- **Replies are client-scoped fail-closed.** A server-initiated result is accepted
  only from the client that owns the pending request; a mismatched responder is
  rejected, never silently routed. Tool→client scope is carried via contextvars so
  it stays correct under concurrent dispatch.

### Security / hardening

Newly reachable once handlers run concurrently:

- Per-client progress tokens are namespaced by request id, so two concurrent calls
  reusing one `progressToken` value cannot cross-deliver or evict each other's
  progress.
- A server-initiated dispatch-send failure drops the pending request from every
  tracking map and cancels its future — no leaked future or FIFO entry.
- Every outbound WebSocket send for a client serializes through one per-client
  lock, so a server-initiated send and a response send cannot interleave frames.
- The pending-sampling map stays FIFO-bounded and is cleared on client disconnect.

## [0.3.2] — 2026-07-15 — JWT audience fail-closed + OAuth 2.1 client discovery + server conformance (#1712)

Second MCP 2025-11-25 spec-parity wave. Part of #1712 — the checklist remains open for later waves.

### Security

- **JWT token audience validated fail-closed** (`BearerTokenAuth` / `JWTAuth`, new
  `expected_audience` option). When set, the `aud` claim is required and matched, so
  BOTH audience-absent AND foreign-audience tokens are rejected — per the MCP 2025-11-25
  requirement that servers validate token audience fail-closed. Non-breaking: when
  `expected_audience` is unset the audience dimension is not validated (prior behaviour)
  and a one-time construction warning states it is required for spec compliance.
- **OAuth discovery SSRF hardened** — the RFC 9728 `resource_metadata` URL (carried on an
  untrusted 401 `WWW-Authenticate` header) is rejected unless same-origin as the connected
  server, BEFORE the fetch fires; discovery fetches use `allow_redirects=False`. The
  same-origin PRM constraint transitively closes the rogue-AS redirect path.
- **WebSocket request-id reuse tracking is bounded and cleared on disconnect** — closes two
  remotely-triggerable OOM/DoS vectors (an unbounded per-session id set and a per-connection
  state leak on connection churn).

### Added

- **Client-side OAuth 2.1 discovery** — `WWW-Authenticate` parse + Protected Resource
  Metadata (RFC 9728, both mechanisms + well-known fallback) + Authorization Server metadata
  (RFC 8414 with OIDC fallback), PKCE S256 verify-before-proceed (fail-closed when absent),
  the RFC 8707 `resource` indicator on all four grant requests, and Bearer token binding
  (expiry-aware) on outbound requests.
- **Server tool-result / resources/read conformance** — tool-execution failures surface as
  `isError: true` inside the result (protocol errors stay JSON-RPC); `structuredContent`
  validated against a tool's `outputSchema`; non-text content passthrough
  (image / audio / resource / resource_link); `resources/read` gains a base64 `blob` branch
  for binary content, a `mimeType` on returned contents, and RFC 3986 URI validation
  (distinct `-32602`).

### Fixed

- **WebSocket lifecycle** — a JSON-RPC notification (absent id) now receives no response;
  `ping` returns an empty result; a request id reused within a session is rejected (`-32600`).

## [0.3.1] — 2026-07-15 — fail-closed MCP local-server spawn allowlist + spec-parity fixes (#1712)

### Security

- **Fail-closed local-server spawn allowlist** (`kailash_mcp.security.validate_spawn_command`,
  `SpawnSecurityError`). An unlisted spawn command is now REJECTED by default
  (never warn-and-allowed), per the MCP 2025-11-25 local-server spawn-safety
  requirement. Wired at every process-spawn surface: the three `MCPClient` stdio
  sites, `EnhancedStdioTransport.connect`, and the discovery health-probe.

### Fixed

- **Explicit `null` JSON-RPC request id** is rejected at the parse boundary
  (`JsonRpcRequest.from_dict`), distinct from an absent id (= notification).
- **`protocolVersion` negotiation** — the server echoes a supported requested
  version, else returns the newest supported, instead of a hardcoded string.

## [0.3.0] — 2026-07-13 — real `mcp_tool_duration_seconds` histogram reaches unified `/metrics` (#1708)

Part of the coordinated 5-package #1708 observability release. Requires
`kailash>=2.50.0` (the unified `/metrics` exposition this histogram now
reaches). Minor version bump reflects a client-facing metrics-surface change
(the removed p95/p99 sample-window fields below).

### Added

- **Real `mcp_tool_duration_seconds` histogram (#1708 W2).** Tool / resource /
  prompt call duration was previously exported only as client-side p95/p99
  computed over a rolling ~100-sample in-process window — not aggregatable
  across processes and not a real histogram. Replaced with a
  `prometheus_client` Histogram (explicit second-scale buckets), observed at
  the real `track_tool_call` site, registered as a lazy singleton on the
  global `prometheus_client.REGISTRY` so it reaches any `/metrics` scrape
  (the package's own bundled Prometheus exporter had no production caller
  wiring it to an endpoint). The `tool` label is bounded by construction —
  every production call site passes a decoration-time name (`func.__name__`,
  `resource:{uri}`, `prompt:{name}`), a finite, developer-registered set, not
  a per-request or client-supplied value. New optional `monitoring` extra
  (`prometheus-client>=0.22.1`); absence silently disables the histogram
  without breaking `import kailash_mcp`.

### Changed

- **Rolling-window p95/p99 sample fields removed from tool-call stats.** The
  in-process p95/p99-over-~100-samples fields are superseded by the real
  histogram above (Prometheus-side `histogram_quantile()` over the exported
  buckets is the aggregatable replacement). `get_tool_stats()` callers
  reading the removed fields must migrate to a `/metrics` scrape.

## [0.2.15] — 2026-06-18 — chore: release un-bumped #1258 byte-vector pins

Patch release cutting the previously-unreleased `1e17d63df` source commit (#1258 —
documented + pinned non-ASCII byte-vectors for the 4 MCP canonical encoders in
`protocol/messages.py`). Documentation + test-vector pins only; zero runtime / API /
behavior change. Released to keep the package source tree and PyPI in sync.

## [0.2.14] — 2026-05-09 — hotfix: aiohttp + websockets restored to core deps

Hotfix release closing a pre-existing latent silent-None ImportError fallback in `transports/transports.py` that was masked by editable installs and exposed by the 0.2.13 clean-venv install verification (`pip install kailash-mcp==0.2.13` → `AttributeError: 'NoneType' object has no attribute 'ClientResponse'` at module-import time).

The bug existed in 0.2.12 as well — anyone who installed `pip install kailash-mcp==0.2.12` against a venv without aiohttp/websockets transitively present would have hit the same import failure. Most users were unaffected because they install `kailash-kaizen` or `kailash-dataflow` first, both of which transitively pull aiohttp.

### Fixed

- **`pip install kailash-mcp` now imports cleanly** — `aiohttp>=3.12.4` and `websockets>=12.0` are restored to **core** dependencies. `transports/transports.py:902` declares `class StreamableHTTPTransport` with a method signature `response: aiohttp.ClientResponse` (module-scope class-body type annotation, evaluated at class-definition time); `transports/transports.py:954` declares `self.websocket: Optional[websockets.WebSocketServerProtocol]`. Both references are unconditional — making aiohttp / websockets effectively required for `import kailash_mcp` to succeed. The `[http]` / `[sse]` / `[websocket]` extras retain their declarations as harmless redundancy (already-installed entries are no-ops).
- **Removed BLOCKED silent-None ImportError fallback** — `transports/transports.py:67-74` previously had `try: import aiohttp; except ImportError: aiohttp = None` (and same for websockets). Per `dependencies.md` BLOCKED Anti-Patterns, the silent-None fallback "converts a loud, fixable failure into a silent, cascading one." Replaced with bare `import aiohttp; import websockets` since these are now core deps. `auth/oauth.py` retains its guarded imports because it correctly uses the optional-extras-with-loud-failure pattern via `_require_oauth_extras()` (typed ImportError raised at call sites, not silent-None propagation).

### Notes

- **0.2.13 superseded.** `pip install kailash-mcp` now resolves to 0.2.14 by default. Users on 0.2.13 should upgrade.
- **Follow-up tracked**: the websockets ≥12.0 API deprecates `websockets.WebSocketServerProtocol` / `WebSocketServer` (moved to `websockets.legacy.server`). Current code still works via backwards-compat aliases but emits `DeprecationWarning`s. Migration to the new API is a separate workstream — out of hotfix scope.

## [0.2.13] — 2026-05-09 — slim core: orphan pydantic delete + kailash 2.16 floor (#890)

Patch release shipping kailash-mcp's slice of the kailash 2.18.0 / #890 slim-core decoupling. **No install-shape change for users** — `pydantic` was a declared core dep but had zero import sites in `src/kailash_mcp/`; it remains transitively available through `mcp[cli]` (which declares pydantic as its own runtime dependency). Users see no behavior change.

### Changed

- **Removed orphan dependency `pydantic>=2.6`** — verified zero imports in `src/kailash_mcp/` source tree. The package's runtime needs are entirely covered by `kailash` + `mcp[cli]`. `mcp[cli]` continues to declare pydantic as a transitive dep, so `import pydantic` still works for any kailash-mcp consumer that needs it directly.
- **`kailash` floor: 2.16.0** (was `2.14.0`) — aligns with the kailash 2.18.0 slim-core layout.

### Notes

- This is a **packaging cleanup release** — no public-API additions, removals, or behavior changes. Wheel content is identical to 0.2.12 except for the `__version__` constant; only the install manifest changed (one fewer declared core dep).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.12] — 2026-05-07 — ErrorAggregator orphan polish

Patch bump shipping a previously-orphaned bug fix to `ErrorAggregator.get_error_trends()` that landed in commit `5ca2f993` ("docs(w1): add §4.6 Durable Execution to specs/core-runtime.md + fix flaky aggregator") without an accompanying version bump. Caught at `/release`-time scope enumeration per `build-repo-release-discipline.md` MUST Rule 5.

### Fixed

- **`ErrorAggregator.get_error_trends()` empty-bucket on fresh errors (commit `5ca2f993`)** — when `oldest_error.timestamp ≈ now` (sub-second wall-clock skew, common in unit tests and fast services), the prior `while bucket_start < now` loop never executed and returned an empty trends list despite having recorded errors. Replaced with `do-while` semantics so a single fresh error still emits one bucket containing it.

## [0.2.11] — 2026-05-03 — sibling-release sweep (W6-002 + LOW-6 triage)

Patch release cutting PyPI for previously-unreleased commits on main per `build-repo-release-discipline.md` Rule 1 (every BUILD-repo session releases all packages whose main is ahead of PyPI). Triggered by the issue #781 cleanup release wave (kailash 2.13.4 + dataflow/kaizen/nexus/kaizen-agents siblings).

### Fixed

- **W6-002 — `ElicitationSystem._CapturingTransport.response_handler` typed as `Optional[Callable]` to clear pyright `reportAttributeAccessIssue`** (commit `427a315b`).

### Tests

- Added Tier-2 integration test for `ElicitationSystem` at `tests/integration/mcp_server/test_elicitation_integration.py` (closes Wave 6 finding F-F-32). Exercises the spec § 4.9 contract end-to-end through the `server.elicitation_system` facade across happy-path / validation-rejection / timeout / cancellation scenarios. 10 tests, all passing (commits `43a713c7` + `84437c74`).

### Triage (recap)

- Resolved 3 stub-marker findings from SWEEP-2026-04-28 LOW-6 cluster (commit `6c00ea3f`).

## [0.2.10] — 2026-04-26 — JWT iss-claim required when expected_issuer configured (#625)

Patch bump — closes Wave 4 cross-SDK security finding #625 (kailash-rs#599 sibling). Per upstream PyJWT semantics, calling `decode(token, ..., issuer=allowlist)` enforces equality only when the `iss` claim is **present**. A forged token that omits `iss` entirely passes issuer validation regardless of the allowlist. Layering `options={"require": ["exp", "iss"]}` forces presence and closes the bypass.

### Security

- **HIGH (closes #625)** — `BearerTokenAuth.__init__` accepts new optional `expected_issuer` kwarg; `_validate_jwt_token` layers `options={"require": ["exp", "iss"]}` and `issuer=` when set. PyJWT exception handlers cover `MissingRequiredClaimError` + `InvalidIssuerError`.
- **HIGH (closes #625)** — `JWTAuth.__init__` passes its `issuer` arg through to `BearerTokenAuth` as `expected_issuer`, so callers using `JWTAuth` automatically inherit the iss requirement.
- **HIGH (closes #625)** — `JWTManager.verify_access_token` / `verify_refresh_token` layer the require-claims when `self.issuer is not None`.

### Tests

- 9/9 regression tests at `packages/kailash-mcp/tests/regression/test_issue_625_jwt_iss_required.py` (acceptance B + C + extra coverage + cross-SDK semantic-parity tests).
- Registered `regression` pytest marker in `pyproject.toml`.

### Cross-SDK

- Originating issue: `esperie/kailash-rs#599`
- Rust merging PR: `kailash-rs#602` (v3.23.0)
- Python merging PR: kailash-py #632 (this release)

### Origin

- Initial fix shipped via PR #632 but was missed in the kailash-mcp version bump. This patch corrects the version to 0.2.10 so consumers can `pip install kailash-mcp==0.2.10` and receive the security fix. Per `rules/build-repo-release-discipline.md` § 1 (every src change triggers a release-cycle).

## [0.2.9] — 2026-04-24 — Security patch (issue #613)

### Changed

- **`kailash_mcp.auth.providers` correlation fingerprints** (`py/weak-sensitive-data-hashing`) — migrated `hashlib.sha256(api_key)` and `hashlib.sha256(token)` to `kailash.utils.url_credentials.fingerprint_secret(...)` (BLAKE2b, 8-char) at two sites (`APIKeyAuth.authenticate` line 199, `BearerTokenAuth._validate_opaque_token` line 335). Same rationale as kaizen 2.12.1 — the values are correlation-only `user_id` labels emitted AFTER raw-credential verification already succeeded; BLAKE2b satisfies both the scanner and the architectural intent. No migration required; neither fingerprint is persisted. Sibling fix landed same PR per `rules/agents.md` fix-immediately rule.

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
- Cross-SDK parity issue filed on the Rust SDK (#443) — Rust SDK has no elicitation surface; Python shape documented as reference for future Rust implementation.

## [0.2.5] - 2026-04-19 — oauth.py optional-extras gating (#514)

### Fixed

- **`oauth.py` module-level imports of optional extras (#514, PR #518)**: `kailash_mcp/auth/oauth.py` imported `aiohttp`, `PyJWT`, and `cryptography` at module scope. All three are declared optional under `[project.optional-dependencies] auth-oauth`. On a bare `pip install kailash-mcp` (no oauth extra), any `import kailash_mcp` transitioned to an `ImportError` through the auth sub-package. Fix: wrap the three imports in `try/except ImportError` with `None` fallbacks; add `_require_oauth_extras()` helper that raises a descriptive `ImportError` naming `pip install 'kailash-mcp[auth-oauth]'` when OAuth classes are instantiated without the extra. Module now imports cleanly without the oauth extra; OAuth classes fail loudly with an actionable error instead of silently. Aligns with `rules/dependencies.md` § "Declared = Gated Consistently" and cross-SDK parity with kailash-rs#417.

## [0.2.4] - 2026-04-14

### Fixed

- All 63 unit test warnings resolved (combined with kailash 2.8.6 release).

## [0.2.3] - 2026-04-08

### Added

- Initial platform server, auth JWT/OAuth, and MCP client/server implementations.
