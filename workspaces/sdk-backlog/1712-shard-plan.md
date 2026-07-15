# #1712 MCP 2025-11-25 Spec-Parity — Shard Plan (audit-derived 2026-07-15)

Audit workflow wyjy0wo8a: 6 clusters, evidence-backed. Shard-1 (PR #1759) already landed
spawn-allowlist + null-id + server-side protocolVersion negotiation.

## Dependency-forced waves (file-conflict map)
- server.py touched by: SRV conformance + client-features(G5) → serial
- client.py touched by: OAuth(G3) + client-features(G5) → serial
- transports.py/http.py touched by: OAuth-RS(PRM) + StreamableHTTP(G4) → serial

## WAVE 1 (parallel — disjoint files) [IN PROGRESS]
- SEC   auth/providers.py + trust/plane/mcp_server.py + trust/mcp/server.py — audience fail-closed default (SECURITY)
- SRV   server.py — tool-result(isError/structuredContent/non-text/annotations) + resources/read(blob/mimeType/RFC3986) + notification+ping + request-id-reuse

## WAVE 2 (OAuth discovery chain) — oauth.py + client.py + transports.py(PRM route)
- PRM RFC9728 publish + WWW-Authenticate 401 + client PRM discovery + AS metadata(RFC8414/OIDC) + PKCE-S256 guard + RFC8707 resource param + Bearer token binding

## WAVE 3 (Streamable HTTP) — transports.py + channels/mcp/http.py + sse.py [serial after W2]
- single-endpoint POST+GET + MCP-Protocol-Version header→400 + MCP-Session-Id lifecycle + SSE retry field

## WAVE 4 (server.py part 2) — pagination(tools/prompts/templates) + completions ranking + logging notifications/message [serial after SRV]

## WAVE 5 (client features) — sampling + roots(+validate_access TypeError bug) + elicitation 2025-11-25 shape [serial after G2+G3]

## WAVE 6 (cross-SDK lockstep) — channels/mcp/stdio.py newline wire-format (LSP→newline) — needs Rust coordination
