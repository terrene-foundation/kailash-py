---
type: DECISION
date: 2026-04-25
created_at: 2026-04-25T10:10:04.113Z
author: agent
session_id: c8cb11ec-e2ab-40d5-95ce-947a896a84ec
project: kailash-ml-audit
topic: MCP transport primitives (stdio/SSE/HTTP) closes #600
phase: implement
tags: [mcp, transports, ssrf, cross-sdk-parity, eatp-d6]
source_commit: 7835ebfa6fcc344843846103dbd9e20a1d8e072b
---

# DECISION — feat(mcp): add stdio/SSE/HTTP transport primitives (#600)

## What

Adds Transport ABC + 3 concrete client transports + SSRF-guarded URL validator at `src/kailash/channels/mcp/`. Closes #600 (kailash-rs ISS-20).

Surface:

- **Transport ABC**: `send` / `receive` / `close` + async context manager
- **StdioTransport**: subprocess spawn, allowlist gate, LSP framing
- **SseTransport**: HTTP POST + SSE event stream client
- **HttpTransport**: single-shot HTTP POST request/response
- **validate_url**: SSRF guard (scheme + private-host allowlist)

## Why

EATP D6 mandates cross-SDK parity for MCP transports. kailash-rs/crates/kailash-mcp/src/transport/ shipped stdio/SSE/HTTP with SSRF guards; Python had only Nexus-side WebSocket. Without these primitives a Python MCP client has no way to reach an external MCP server over the standard transports.

## Tests

35 Tier 1 unit + 4 Tier 2 integration (real subprocess + aiohttp test server). NO mocking in Tier 2 per `rules/testing.md`.

## Alternatives considered

- **Wrapping the official `mcp` Python SDK**: rejected because the ABC + SSRF guards are Foundation-specific (CARE Trust Plane requires the validator at every external-URL boundary). Wrapping would have left the SSRF surface dependent on upstream cadence.
- **Sync transports**: rejected; MCP frames are inherently streaming, sync would force every caller to manage a thread.

## Consequences

Unlocks Python-side MCP client integration tests for downstream PACT governance flows. Blocks nothing.

## For Discussion

1. The SSRF validator's private-host allowlist is configured at validator-construction time. Should production deployments with split-horizon DNS be able to override the allowlist via env var, or is module-level configuration the right scope?
2. Counterfactual: if the SSRF guard had landed AFTER the Transport ABC (say, in a follow-up PR), would the unguarded HttpTransport have been called by any pre-existing consumer? `grep -r 'HttpTransport' src/` returns 0 hits outside this PR's tests — the guard arrived before the consumers.
3. kailash-rs ISS-20 still needs the EATP D6 conformance test pair. Should we add a cross-SDK integration test that spawns a Python server + Rust client and a Rust server + Python client, or is per-SDK unit + Tier 2 sufficient for parity certification?
