# 0011 — DISCOVERY — MCP spec sibling-sweep (Shard D, #556)

Date: 2026-04-20
Scope: Parallel-release cycle Shard D — issue #556 un-stub `ElicitationSystem._send_elicitation_request`.

## Trigger

`specs/mcp-server.md` §4.9 expanded from 2 lines to ~105 lines documenting the `ElicitationSystem` construction contract, `request_input` / `provide_input` semantics, JSON-RPC wire shape, server dispatch wiring, error semantics, and security requirements. Per `rules/specs-authority.md` MUST Rule 5b, any spec edit triggers a FULL sibling-spec re-derivation sweep (not narrow-scope to the edited file).

## Sibling set enumerated

```bash
ls specs/mcp-*.md
# specs/mcp-auth.md
# specs/mcp-client.md
# specs/mcp-server.md  (edited)
```

Three-file domain. Sweep must re-derive assertions in the two unedited siblings (`mcp-auth.md`, `mcp-client.md`) against the expanded §4.9 contract.

## Re-derivation

Grep for cross-references the expansion might collide with:

```bash
grep -n "elicit\|Elicit\|interactive\|request_input\|elicitation/create" \
     specs/mcp-client.md specs/mcp-auth.md
# (empty — no prior references to the surface)
```

The expanded surface introduces:

- `SendFn = Callable[[dict], Awaitable[None]]` type alias
- `ElicitationSystem(send=...)` and `bind_transport(send)` APIs
- MCP JSON-RPC `elicitation/create` method name
- `ElicitResult { action, content }` wire shape per MCP 2025-06-18
- Typed errors: `MCPError(INVALID_REQUEST)`, `MCPError(REQUEST_TIMEOUT)`, `MCPError(REQUEST_CANCELLED)`, `ValidationError`

### mcp-client.md — assertions re-derived

- `mcp-client.md` documents `MCPClient` (client-side), transport layer, service discovery, health checks, tool hydration. Elicitation is a **server-to-client** request; the client's role would be to RECEIVE `elicitation/create` and respond with `ElicitResult`. The spec currently does NOT describe an elicitation receive handler on the client side. **Disposition**: not a drift — `mcp-client.md` §1.2 (Transport Resolution) is silent on inbound server-to-client methods, which is consistent with the current kailash-mcp client surface. Future work to add a client-side elicitation-response builder would be a new section, not a correction.
- No terminology collisions: `mcp-client.md` uses `request` / `response` exclusively for client-to-server request/response; the term `request_input` is namespaced to the server-side elicitation system.
- No field-shape divergence: `MCPClient` does not expose an elicitation-related attribute.

### mcp-auth.md — assertions re-derived

- `mcp-auth.md` documents `AuthProvider`, `AuthManager`, `PermissionManager`, `RateLimiter`. Elicitation on the server side is authenticated via the transport's existing auth chain (client has already authenticated when the server issues `elicitation/create`). The security note in the expanded §4.9 ("schema validation MUST run before returning to the calling tool") is orthogonal to auth — it's input validation, not authorization.
- No terminology collisions.
- No field-shape divergence.

### mcp-server.md — self-consistency

- §4.8 `ProgressReporter` / `CancellationContext` uses `create_progress_reporter` / `create_cancellation_context` top-level factories. `ElicitationSystem` does NOT have an equivalent factory — it's constructed directly. Consistent with the existing §4.5 (`BinaryResourceHandler`) and §4.6 (`ResourceTemplate`) style where the class is the public surface.
- §5 "Server-Side Edge Cases" has no existing elicitation-related note; the expanded §4.9 Server Dispatch Wiring subsection documents the MCPServer binding directly, avoiding a cross-reference that would need updating in §5.

## Findings

**0 HIGH, 0 MED, 0 LOW** — the expanded §4.9 surface is self-contained. The sibling specs describe orthogonal concerns (client surface, auth chain) and do not reference the elicitation system at all. No silent drift.

## Action

Continue with implementation (Shard D steps 2-5). No sibling-spec edits required.

---

Rule reference: `rules/specs-authority.md` MUST Rule 5b — full-sibling-spec re-derivation triggered by every spec edit.
Cross-SDK: kailash-rs equivalent not yet inspected (tracked as Step 6 of Shard D).

## For Discussion

1. **Counterfactual**: If this sibling-sweep had been skipped (narrow-scope, "only the file I edited"), and a future session added an `elicitation/create` handler to `mcp-client.md` using different terminology — e.g. `interactive_request` instead of `request_input` — when would the terminology collision surface, and what would the cost of retroactive normalization be?

2. **Data-referenced**: The grep against `mcp-client.md` + `mcp-auth.md` returned 0 matches for `elicit|Elicit|interactive|request_input|elicitation/create`. Does a zero-finding sweep constitute evidence that the expanded surface is well-isolated, or does it merely indicate that existing specs were written before MCP 2025-06-18 elicitation was defined (i.e., the silence is an artifact of spec age, not architectural separation)?

3. **Scope**: The sweep covered only `specs/mcp-*.md`. `specs/ml-engines.md` references `MCPServer` in its serving section (§6 series). Should the sibling-spec sweep rule extend to cross-domain specs that reference the edited package, or does that broaden the scope to the point where every spec edit triggers a full-corpus sweep?
