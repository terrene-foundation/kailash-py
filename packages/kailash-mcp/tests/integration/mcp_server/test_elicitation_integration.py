# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 integration tests for MCP ElicitationSystem (closes F-F-32).

Per ``specs/mcp-server.md`` § 4.9 (ElicitationSystem). The spec promises the
file ``packages/kailash-mcp/tests/integration/mcp_server/test_elicitation_integration.py``
exercises the elicitation end-to-end behavior. This file delivers that contract.

These tests construct a real ``MCPServer`` instance and exercise the
elicitation pipeline through the server's production dispatch path
(``_route_server_initiated_response``) wired to the
``ElicitationSystem`` instance the server owns at ``server.elicitation_system``.

Per ``rules/testing.md`` § Tier 2:

- NO mocking (``@patch``, ``MagicMock``, ``unittest.mock``) — BLOCKED.
- The in-process ``async def`` send-callable used here is a
  Protocol-Satisfying Deterministic Adapter (rules/testing.md § Tier 2
  Exception). It conforms to the ``SendFn`` protocol declared in
  ``kailash_mcp.advanced.features`` (``Callable[[dict], Awaitable[None]]``)
  and produces deterministic output — it captures outbound JSON-RPC
  ``elicitation/create`` requests, allows the test to inspect them, and
  delivers responses through the SAME production code path the server
  uses for real client transports.

Per ``rules/orphan-detection.md`` § 1 + § 2 (and the manager-shape sibling
in ``rules/facade-manager-detection.md`` § 1):

- ElicitationSystem is exposed as ``server.elicitation_system`` and wired
  into ``MCPServer._route_server_initiated_response``. These tests import
  through that facade — NOT directly via
  ``kailash_mcp.advanced.features.ElicitationSystem`` — so the production
  call site is the one being exercised.

Scenarios covered (matching the spec § 4.9 contract):

1. **Happy-path** — server requests user input via ``request_input``, an
   accept-action response with ``content`` is delivered back through the
   server's dispatch path, the response is validated against the optional
   schema, and the validated payload is returned to the calling tool.

2. **Server-side validation rejection** — client sends a content payload
   that fails the JSON Schema, raising ``ValidationError`` (the typed
   exception declared in spec § 4.9 Error Semantics). Per the spec,
   validation is the single-point concern of ``request_input`` after the
   response future resolves; ``provide_input`` does NOT validate.

3. **Client-side timeout** — server requests; client never responds
   within the configured timeout; ``request_input`` raises
   ``MCPError(MCP_ELICITATION_TIMEOUT)`` (-32001) and pending-request
   bookkeeping is cleaned up in the ``finally`` block per spec § 4.9
   step 8.

4. **Cancellation** — server requests; client returns an action of
   ``decline`` or ``cancel`` (per MCP 2025-06-18 ``ElicitResult``); the
   server's dispatch path routes this to ``cancel_request`` which raises
   ``MCPError(MCP_REQUEST_CANCELLED)`` (-32800) to the calling tool.

The four error codes pinned here MUST match ``kailash-rs`` byte-for-byte
per spec § 4.9 Cross-SDK Parity table (kailash-rs#471, kailash-py#572).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from kailash_mcp.errors import MCPError, MCPErrorCode, ValidationError
from kailash_mcp.server import MCPServer


# ---------------------------------------------------------------------------
# Protocol-satisfying deterministic adapter — NOT a mock.
# ---------------------------------------------------------------------------
#
# Conforms to the ``SendFn`` protocol declared in
# ``kailash_mcp.advanced.features`` (``Callable[[dict], Awaitable[None]]``).
# Captures every outbound JSON-RPC message and exposes hooks for the test
# body to deliver inbound responses through the server's PRODUCTION
# dispatch path (``server._route_server_initiated_response``).
class _CapturingTransport:
    """In-process transport adapter for elicitation tests.

    The adapter exposes a ``send_message`` coroutine matching the
    ``SendFn`` protocol that ``ElicitationSystem._send_elicitation_request``
    awaits. Outbound messages are captured for the test body to inspect
    AND optionally trigger an inbound response routed back through the
    server's production dispatch path.

    Behavior matrix is set per-test via ``response_handler`` — a plain
    ``async def`` callable that receives the outbound message and the
    bound server, and decides what (if any) inbound response to deliver.
    None = no response (used for the timeout scenario).
    """

    def __init__(self) -> None:
        self.outbound: List[Dict[str, Any]] = []
        self.server: MCPServer | None = None
        self.response_handler = None  # type: ignore[assignment]

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Conforms to ``SendFn`` — receive an outbound JSON-RPC message."""
        self.outbound.append(message)
        # Schedule an asynchronous response so request_input has the
        # opportunity to install its response future before delivery.
        if self.response_handler is not None and self.server is not None:
            asyncio.get_running_loop().call_soon(
                lambda: asyncio.create_task(self.response_handler(message, self.server))
            )


@pytest.fixture
def server() -> MCPServer:
    """Real MCPServer instance with bound in-process transport.

    Per ``rules/facade-manager-detection.md`` § 1 — the test imports the
    framework facade (``server.elicitation_system``), not the manager class
    directly. The constructor wires ``ElicitationSystem`` per the spec
    § 4.9 Server Dispatch Wiring contract.
    """
    srv = MCPServer(
        name="test-elicitation-server",
        transport="stdio",  # No real transport startup — we bind a test transport below.
        enable_cache=False,  # Reduce construction noise.
        enable_metrics=False,
        enable_subscriptions=False,
    )
    return srv


@pytest.fixture
def transport(server: MCPServer) -> _CapturingTransport:
    """Bind a deterministic in-process transport to the server's elicitation system."""
    t = _CapturingTransport()
    t.server = server
    server.elicitation_system.bind_transport(t.send_message)
    return t


# ---------------------------------------------------------------------------
# Scenario 1 — Happy-path elicitation.
# ---------------------------------------------------------------------------
class TestHappyPath:
    """Server requests input; client returns accept; validated payload returned."""

    async def test_request_input_returns_validated_accept_payload(
        self, server: MCPServer, transport: _CapturingTransport
    ) -> None:
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "minimum": 0}},
            "required": ["age"],
        }

        async def reply_with_accept(outbound: Dict[str, Any], srv: MCPServer) -> None:
            # Build a wire-shaped inbound MCP elicitation/response: the
            # production dispatch path expects `result.action` + `result.content`
            # per spec § 4.9 JSON-RPC Wire Shape.
            inbound = {
                "jsonrpc": "2.0",
                "id": outbound["id"],
                "result": {"action": "accept", "content": {"age": 25}},
            }
            # Route through the SAME code path used for real client responses.
            await srv._route_server_initiated_response(inbound["id"], inbound)

        transport.response_handler = reply_with_accept

        result = await server.elicitation_system.request_input(
            prompt="What is your age?",
            input_schema=schema,
            timeout=5.0,
        )

        # External observable: validated payload returned to the tool caller.
        assert result == {"age": 25}

        # External observable: the outbound JSON-RPC message has the
        # spec-mandated wire shape.
        assert len(transport.outbound) == 1
        msg = transport.outbound[0]
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "elicitation/create"
        assert msg["params"]["message"] == "What is your age?"
        assert msg["params"]["requestedSchema"] == schema
        assert msg["params"]["requestId"] == msg["id"]

        # External observable: pending-request bookkeeping cleaned up
        # per spec § 4.9 step 8 (finally-block cleanup).
        assert server.elicitation_system._pending_requests == {}
        assert server.elicitation_system._response_callbacks == {}

    async def test_default_schema_when_caller_omits_input_schema(
        self, server: MCPServer, transport: _CapturingTransport
    ) -> None:
        """Spec § 4.9: ``requestedSchema`` defaults to ``{"type": "string"}`` on the wire."""

        async def reply_with_accept(outbound: Dict[str, Any], srv: MCPServer) -> None:
            inbound = {
                "jsonrpc": "2.0",
                "id": outbound["id"],
                "result": {"action": "accept", "content": "freeform-string"},
            }
            await srv._route_server_initiated_response(inbound["id"], inbound)

        transport.response_handler = reply_with_accept

        result = await server.elicitation_system.request_input(
            prompt="Free text?",
            input_schema=None,
            timeout=5.0,
        )

        assert result == "freeform-string"
        # Spec-mandated default on the wire.
        assert transport.outbound[0]["params"]["requestedSchema"] == {"type": "string"}


# ---------------------------------------------------------------------------
# Scenario 2 — Server-side validation rejection.
# ---------------------------------------------------------------------------
class TestValidationRejection:
    """Spec § 4.9 step 6: schema validation failure raises ValidationError.

    Validation is the single-point concern of ``request_input`` after the
    response future resolves; ``provide_input`` does NOT validate (spec
    § 4.9 ``provide_input`` paragraph).
    """

    async def test_invalid_response_payload_raises_validation_error(
        self, server: MCPServer, transport: _CapturingTransport
    ) -> None:
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "minimum": 0}},
            "required": ["age"],
        }

        async def reply_with_invalid(outbound: Dict[str, Any], srv: MCPServer) -> None:
            # ``age`` is the wrong type — schema requires integer ≥ 0.
            inbound = {
                "jsonrpc": "2.0",
                "id": outbound["id"],
                "result": {
                    "action": "accept",
                    "content": {"age": "not-an-integer"},
                },
            }
            await srv._route_server_initiated_response(inbound["id"], inbound)

        transport.response_handler = reply_with_invalid

        with pytest.raises(ValidationError) as excinfo:
            await server.elicitation_system.request_input(
                prompt="What is your age?",
                input_schema=schema,
                timeout=5.0,
            )

        # External observable: typed validation error, not silent return.
        assert "validation failed" in str(excinfo.value).lower()

        # External observable: pending bookkeeping still cleaned up (finally block).
        assert server.elicitation_system._pending_requests == {}
        assert server.elicitation_system._response_callbacks == {}

    async def test_missing_required_field_raises_validation_error(
        self, server: MCPServer, transport: _CapturingTransport
    ) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        async def reply_with_empty(outbound: Dict[str, Any], srv: MCPServer) -> None:
            inbound = {
                "jsonrpc": "2.0",
                "id": outbound["id"],
                # ``content`` lacks the required ``name`` field.
                "result": {"action": "accept", "content": {}},
            }
            await srv._route_server_initiated_response(inbound["id"], inbound)

        transport.response_handler = reply_with_empty

        with pytest.raises(ValidationError):
            await server.elicitation_system.request_input(
                prompt="What is your name?",
                input_schema=schema,
                timeout=5.0,
            )


# ---------------------------------------------------------------------------
# Scenario 3 — Client-side timeout.
# ---------------------------------------------------------------------------
class TestTimeout:
    """Spec § 4.9 step 7 + Error Semantics row 2:
    timeout raises MCPError(MCP_ELICITATION_TIMEOUT, code=-32001).
    """

    async def test_no_response_within_timeout_raises_typed_timeout(
        self, server: MCPServer, transport: _CapturingTransport
    ) -> None:
        # No response_handler → outbound message is captured, but no inbound is delivered.
        transport.response_handler = None

        with pytest.raises(MCPError) as excinfo:
            await server.elicitation_system.request_input(
                prompt="Will time out",
                input_schema=None,
                timeout=0.1,  # Short timeout for fast test execution.
            )

        # External observable: the wire code is the spec-mandated -32001
        # (cross-SDK parity contract — kailash-rs#471 / kailash-py#572).
        assert excinfo.value.error_code == MCPErrorCode.MCP_ELICITATION_TIMEOUT
        assert excinfo.value.error_code.value == -32001
        assert "timed out" in str(excinfo.value).lower()

        # External observable: outbound was sent before the timeout fired.
        assert len(transport.outbound) == 1
        assert transport.outbound[0]["method"] == "elicitation/create"

        # External observable: pending-request bookkeeping cleaned up
        # per spec § 4.9 step 8 — the finally block runs even on timeout.
        assert server.elicitation_system._pending_requests == {}
        assert server.elicitation_system._response_callbacks == {}
        assert server.elicitation_system._cancel_callbacks == {}


# ---------------------------------------------------------------------------
# Scenario 4 — Cancellation (client decline / cancel action).
# ---------------------------------------------------------------------------
class TestCancellation:
    """Spec § 4.9: client returns ``decline`` or ``cancel`` action; server
    dispatch routes to ``cancel_request`` which raises
    MCPError(MCP_REQUEST_CANCELLED, code=-32800) to the calling tool.

    Per spec § 4.9 JSON-RPC Wire Shape paragraph: 'A decline/cancel should
    be surfaced to the calling tool as a distinct value (or exception) —
    the current implementation treats any non-accept response as
    cancellation by raising MCPError(REQUEST_CANCELLED) to the tool caller.'
    """

    async def test_client_decline_raises_typed_cancelled(
        self, server: MCPServer, transport: _CapturingTransport
    ) -> None:
        async def reply_with_decline(outbound: Dict[str, Any], srv: MCPServer) -> None:
            inbound = {
                "jsonrpc": "2.0",
                "id": outbound["id"],
                "result": {"action": "decline"},
            }
            await srv._route_server_initiated_response(inbound["id"], inbound)

        transport.response_handler = reply_with_decline

        with pytest.raises(MCPError) as excinfo:
            await server.elicitation_system.request_input(
                prompt="Confirm operation?",
                input_schema=None,
                timeout=5.0,
            )

        # External observable: the wire code is the spec-mandated -32800.
        assert excinfo.value.error_code == MCPErrorCode.MCP_REQUEST_CANCELLED
        assert excinfo.value.error_code.value == -32800
        assert "cancel" in str(excinfo.value).lower()

        # External observable: pending bookkeeping cleaned up.
        assert server.elicitation_system._pending_requests == {}

    async def test_client_cancel_action_raises_typed_cancelled(
        self, server: MCPServer, transport: _CapturingTransport
    ) -> None:
        async def reply_with_cancel(outbound: Dict[str, Any], srv: MCPServer) -> None:
            inbound = {
                "jsonrpc": "2.0",
                "id": outbound["id"],
                "result": {"action": "cancel"},
            }
            await srv._route_server_initiated_response(inbound["id"], inbound)

        transport.response_handler = reply_with_cancel

        with pytest.raises(MCPError) as excinfo:
            await server.elicitation_system.request_input(
                prompt="Continue?",
                input_schema=None,
                timeout=5.0,
            )

        assert excinfo.value.error_code == MCPErrorCode.MCP_REQUEST_CANCELLED
        assert excinfo.value.error_code.value == -32800

    async def test_client_error_response_routes_to_cancel(
        self, server: MCPServer, transport: _CapturingTransport
    ) -> None:
        """Per server dispatch path: an inbound response carrying ``error``
        is treated as cancellation with the error message as reason.
        """

        async def reply_with_error(outbound: Dict[str, Any], srv: MCPServer) -> None:
            inbound = {
                "jsonrpc": "2.0",
                "id": outbound["id"],
                "error": {"code": -32600, "message": "client refused"},
            }
            await srv._route_server_initiated_response(inbound["id"], inbound)

        transport.response_handler = reply_with_error

        with pytest.raises(MCPError) as excinfo:
            await server.elicitation_system.request_input(
                prompt="Confirm?",
                input_schema=None,
                timeout=5.0,
            )

        assert excinfo.value.error_code == MCPErrorCode.MCP_REQUEST_CANCELLED
        assert "client refused" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Negative-path bookkeeping: provide_input on unknown request_id.
# ---------------------------------------------------------------------------
class TestUnknownRequestId:
    """Spec § 4.9 ``provide_input`` paragraph: 'Unknown request_id → False;
    the caller logs a elicitation.response.unknown WARN but does not error.'
    """

    async def test_provide_input_returns_false_for_unknown_id(
        self, server: MCPServer
    ) -> None:
        # No request_input has been called — pending registry is empty.
        delivered = await server.elicitation_system.provide_input(
            "no-such-request-id",
            {"any": "data"},
        )
        assert delivered is False

    async def test_cancel_request_returns_false_for_unknown_id(
        self, server: MCPServer
    ) -> None:
        cancelled = await server.elicitation_system.cancel_request(
            "no-such-request-id",
            reason="late",
        )
        assert cancelled is False
