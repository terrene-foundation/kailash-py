---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T07:56:32.458Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: wire ElicitationSystem into MCPServer dispatch to close orphan pattern (shard-D)
phase: implement
tags:
  [
    auto-generated,
    kailash-mcp,
    elicitation,
    mcpserver,
    orphan-detection,
    shard-d,
  ]
related_journal: []
---

# DECISION — wire ElicitationSystem into MCPServer dispatch (shard-D)

## Commit

`de5ac858db73` — feat(mcp): wire ElicitationSystem into MCPServer dispatch (#556, shard-D)

## Body

Completes the production call site for `ElicitationSystem` per `rules/orphan-detection.md` §1. Without this wiring, the `ElicitationSystem` manager would be a facade with no framework hot-path consumer — the exact orphan pattern the rule was written to prevent.

**Changes**:

- `MCPServer.__init__` constructs `self.elicitation_system = ElicitationSystem()` as a public attribute. Tools invoke `server.elicitation_system.request_input(prompt, schema, timeout)`.
- `_bind_elicitation_transport()` binds the active transport's `send_message` callable to the `ElicitationSystem`. Called from `_run_websocket()` after the transport connects. Idempotent — survives transport reconnect.
- `_route_server_initiated_response(request_id, message)` inspects inbound JSON-RPC responses (messages with `id` and `result`/`error` but no `method`) and routes them to the appropriate pending-request registry. Currently handles `ElicitationSystem`; extensible to `sampling/createMessage`.
- `_handle_websocket_message` dispatches inbound responses through `_route_server_initiated_response` BEFORE falling through to method-name routing. An inbound message whose `id` matches a pending elicitation is consumed (no further handler response) per JSON-RPC response semantics.
- `ElicitResult` action handling (MCP 2025-06-18): `accept` → `provide_input` with content payload; `decline` / `cancel` → `cancel_request` raising `MCPError(REQUEST_CANCELLED)` in the originating `request_input()` caller.

Observability: structured log fields `elicitation_request_id`, `transport_type`. Domain-prefixed to avoid `LogRecord` reserved-attribute collision (`rules/observability.md` MUST 9).

## For Discussion

1. **Counterfactual**: Without this wiring commit, `ElicitationSystem` would have been a fully-implemented class exposed as `server.elicitation_system` with no call site in the framework's hot path — exactly the Phase 5.11 orphan pattern (2,407 LOC of trust integration code never called). What would the observable symptom have been for an MCP tool author who called `server.elicitation_system.request_input(...)` — would it have raised immediately, hung, or silently returned without sending anything to the client?

2. **Data-referenced**: `_route_server_initiated_response` is described as "extensible to `sampling/createMessage`." The method currently only handles `ElicitationSystem`. If `sampling/createMessage` responses arrive before that handler is added, they would fall through to method-name routing which would reject them as unknown methods. Is this the correct fallback, or should unknown response `id` values be logged at WARN with the message dropped?

3. **Design**: `_bind_elicitation_transport()` is called from `_run_websocket()` after transport connects and is idempotent. For HTTP/SSE transports (non-WebSocket), is there an equivalent binding point, or does `ElicitationSystem` only function over WebSocket connections? The spec §4.9 Server Dispatch Wiring subsection should clarify this.
