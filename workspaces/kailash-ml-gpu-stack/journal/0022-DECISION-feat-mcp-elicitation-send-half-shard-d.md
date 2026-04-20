---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T07:56:32.458Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: ElicitationSystem send-half via injected send-callable — paired API completion (shard-D)
phase: implement
tags:
  [
    auto-generated,
    kailash-mcp,
    elicitation,
    send-callable,
    dependency-injection,
    shard-d,
  ]
related_journal: []
---

# DECISION — ElicitationSystem send-half via injected send-callable (shard-D)

## Commit

`56b3f1265ffe` — feat(mcp): implement ElicitationSystem send-half via injected send-callable (#556, shard-D)

## Body

The receive-half of `ElicitationSystem` (`provide_input`, `_pending_requests`, `_response_callbacks`) was wired, but the send-half was a `NotImplementedError` stub — a half-implemented public API per `rules/orphan-detection.md` §2a (paired-API pattern) and a `rules/zero-tolerance.md` Rule 2 violation.

**Design decision**: inject a send-callable at construction time (or via `bind_transport`) rather than coupling `ElicitationSystem` to the `BaseTransport` class hierarchy. This:

- Decouples from `BaseTransport` — testable with any async callable.
- Enables in-process send/receive pair testing without real transports.
- Matches the MCP 2025-06-18 `elicitation/create` JSON-RPC wire shape.
- Future-proofs against transport churn — new transports just need to expose `send_message(dict) -> Awaitable[None]`.

**New surface**:

- `ElicitationSystem(send: Optional[SendFn] = None)` — optional transport at construction time.
- `bind_transport(send)` — idempotent late binding.
- `has_transport()` — test/debug helper.
- `cancel_request(request_id, reason)` — receive-side handler for client decline/cancel actions; raises `MCPError(REQUEST_CANCELLED)` in the `request_input()` caller.
- `SendFn = Callable[[Dict], Awaitable[None]]` — public type alias.

`_send_elicitation_request` now builds the spec-compliant JSON-RPC message `{jsonrpc, id, method=elicitation/create, params={requestId, message, requestedSchema}}`. When no send is bound, raises `MCPError(INVALID_REQUEST)` with actionable guidance naming `bind_transport` — NOT `NotImplementedError`.

Observability: structured log points per `rules/observability.md` Mandatory §1+2. Logger field names are domain-prefixed (`elicitation_request_id`) to avoid collision with `LogRecord` reserved attribute names per `rules/observability.md` MUST 9.

Validation is single-point in `request_input` — response schema validation runs BEFORE returning to the calling tool, preventing client-supplied payloads from reaching downstream tools as trusted input.

## For Discussion

1. **Counterfactual**: The design injects a `SendFn` callable rather than a `BaseTransport` instance. If `BaseTransport` had been injected directly, and a future transport refactor changed the `send_message` signature (e.g., added a `priority` parameter), `ElicitationSystem` would have been a forced migration target. How many existing production `ElicitationSystem` call sites would have been affected by such a refactor under the old design vs the injected-callable design?

2. **Data-referenced**: When no send callable is bound, `_send_elicitation_request` raises `MCPError(INVALID_REQUEST)` with guidance naming `bind_transport`. The commit specifies this is NOT `NotImplementedError`. What is the practical difference for an MCP tool author who encounters this error — does `MCPError(INVALID_REQUEST)` reach the MCP client as a JSON-RPC error response, while `NotImplementedError` would be an unhandled exception causing the server to crash?

3. **Design**: Response schema validation runs "single-point in `request_input`" before returning to the calling tool. This means if a client sends a malformed `ElicitResult` (e.g., missing `action` field), `request_input()` raises `ValidationError` in the tool's execution context. Is the tool expected to catch `ValidationError` and handle it gracefully, or should the MCPServer's dispatch layer intercept it and return a structured error to the client?
