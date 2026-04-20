"""Tier 2 integration tests for ElicitationSystem send/receive round-trips.

These tests exercise ElicitationSystem through the public facade
(ElicitationSystem, MCPServer.elicitation_system) with an in-process
send/receive pair acting as the transport. No mocks, no monkeypatching —
the only components substituted are the fake async send-callables that
capture or echo messages, consistent with rules/testing.md Tier 2 contract
(real infrastructure, no @patch / MagicMock / unittest.mock).

Coverage:

1. test_elicitation_in_process_pair_round_trip — happy path: fake send
   captures outbound `elicitation/create`, immediately calls provide_input,
   and request_input returns the round-tripped payload.
2. test_elicitation_unbound_send_raises_typed_error — no transport bound:
   request_input raises MCPError(INVALID_REQUEST) whose message names
   bind_transport. NOT NotImplementedError, NOT AttributeError.
3. test_elicitation_json_rpc_wire_shape — fake send records the outbound
   dict; verifies spec-compliant JSON-RPC 2.0 + MCP 2025-06-18 shape.
4. test_elicitation_schema_validation_on_response — fake send echoes an
   invalid payload; verifies request_input raises ValidationError.
5. test_elicitation_timeout_with_silent_send — fake send never triggers
   provide_input; verifies TimeoutError -> MCPError(REQUEST_TIMEOUT).
6. test_elicitation_bind_transport_replaces_prior — bind_transport called
   twice; the second send-callable receives the message, the first does not.
7. test_elicitation_cancel_request_surfaces_as_cancelled_error — fake send
   calls cancel_request; request_input raises MCPError(REQUEST_CANCELLED).
8. test_mcpserver_exposes_elicitation_system — structural invariant:
   MCPServer constructor wires ElicitationSystem as a public attribute per
   rules/orphan-detection.md §1.

Rules satisfied:
- rules/orphan-detection.md §2 (Tier 2 integration test for wired manager).
- rules/orphan-detection.md §2a (paired-API round-trip through the facade).
- rules/facade-manager-detection.md §1 (external-effect assertions, not mocks).
- rules/testing.md Tier 2 (no mocks; real in-process infrastructure).
- rules/zero-tolerance.md Rule 2 (confirms un-stub of _send_elicitation_request).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest
from kailash_mcp.advanced.features import ElicitationSystem
from kailash_mcp.errors import MCPError, MCPErrorCode, ValidationError
from kailash_mcp.server import MCPServer


@pytest.mark.asyncio
async def test_elicitation_in_process_pair_round_trip() -> None:
    """Happy path: fake send echoes a valid response via provide_input."""
    system = ElicitationSystem()

    async def echoing_send(message: Dict[str, Any]) -> None:
        # Schedule provide_input on the next tick so the caller installs its
        # response future before the callback fires.
        async def later() -> None:
            await asyncio.sleep(0)
            await system.provide_input(message["id"], {"ok": True})

        asyncio.create_task(later())

    system.bind_transport(echoing_send)
    result = await system.request_input("Confirm?", timeout=2.0)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_elicitation_unbound_send_raises_typed_error() -> None:
    """No transport bound: typed MCPError(INVALID_REQUEST), NOT NotImplementedError."""
    system = ElicitationSystem()  # no send

    with pytest.raises(MCPError) as exc_info:
        await system.request_input("Anything?", timeout=0.1)

    assert exc_info.value.error_code == MCPErrorCode.INVALID_REQUEST
    # Actionable message must name bind_transport so callers know the fix.
    assert "bind_transport" in str(exc_info.value)


@pytest.mark.asyncio
async def test_elicitation_json_rpc_wire_shape() -> None:
    """Outbound message conforms to MCP 2025-06-18 elicitation/create."""
    captured: List[Dict[str, Any]] = []
    system = ElicitationSystem()

    async def capturing_send(message: Dict[str, Any]) -> None:
        captured.append(message)

        # Feed a response so request_input returns instead of timing out.
        async def later() -> None:
            await asyncio.sleep(0)
            await system.provide_input(message["id"], "done")

        asyncio.create_task(later())

    system.bind_transport(capturing_send)
    schema = {"type": "string", "minLength": 1}
    await system.request_input("Enter name:", input_schema=schema, timeout=1.0)

    assert len(captured) == 1
    msg = captured[0]
    assert msg["jsonrpc"] == "2.0"
    assert msg["method"] == "elicitation/create"
    assert isinstance(msg["id"], str) and len(msg["id"]) > 0
    params = msg["params"]
    assert params["requestId"] == msg["id"]
    assert params["message"] == "Enter name:"
    assert params["requestedSchema"] == schema


@pytest.mark.asyncio
async def test_elicitation_requested_schema_defaults_when_omitted() -> None:
    """When input_schema is None, outbound requestedSchema defaults to {type: string}."""
    captured: List[Dict[str, Any]] = []
    system = ElicitationSystem()

    async def capturing_send(message: Dict[str, Any]) -> None:
        captured.append(message)

        async def later() -> None:
            await asyncio.sleep(0)
            await system.provide_input(message["id"], "hi")

        asyncio.create_task(later())

    system.bind_transport(capturing_send)
    await system.request_input("Say hi:", timeout=1.0)

    assert captured[0]["params"]["requestedSchema"] == {"type": "string"}


@pytest.mark.asyncio
async def test_elicitation_schema_validation_on_response() -> None:
    """Invalid response payload raises ValidationError, NOT silent return."""
    system = ElicitationSystem()
    schema = {
        "type": "object",
        "properties": {"age": {"type": "integer", "minimum": 0}},
        "required": ["age"],
    }

    async def invalid_echoer(message: Dict[str, Any]) -> None:
        async def later() -> None:
            await asyncio.sleep(0)
            # Payload violates schema: `age` is a string, not an integer.
            await system.provide_input(message["id"], {"age": "not-a-number"})

        asyncio.create_task(later())

    system.bind_transport(invalid_echoer)
    with pytest.raises(ValidationError):
        await system.request_input("Age?", input_schema=schema, timeout=1.0)


@pytest.mark.asyncio
async def test_elicitation_timeout_with_silent_send() -> None:
    """Silent send that never calls provide_input surfaces as REQUEST_TIMEOUT."""

    async def silent_send(message: Dict[str, Any]) -> None:
        # Deliberately do nothing — no provide_input, no cancel_request.
        return None

    system = ElicitationSystem(send=silent_send)

    with pytest.raises(MCPError) as exc_info:
        await system.request_input("Waiting forever?", timeout=0.1)

    assert exc_info.value.error_code == MCPErrorCode.REQUEST_TIMEOUT


@pytest.mark.asyncio
async def test_elicitation_bind_transport_replaces_prior() -> None:
    """bind_transport is idempotent-with-replace; second call wins."""
    first_captured: List[Dict[str, Any]] = []
    second_captured: List[Dict[str, Any]] = []

    async def first_send(message: Dict[str, Any]) -> None:
        first_captured.append(message)

    async def second_send(message: Dict[str, Any]) -> None:
        second_captured.append(message)

        async def later() -> None:
            await asyncio.sleep(0)
            await system.provide_input(message["id"], "ok")

        asyncio.create_task(later())

    system = ElicitationSystem(send=first_send)
    system.bind_transport(second_send)

    result = await system.request_input("Bound?", timeout=1.0)
    assert result == "ok"
    assert len(first_captured) == 0  # first send replaced, never invoked
    assert len(second_captured) == 1


@pytest.mark.asyncio
async def test_elicitation_cancel_request_surfaces_as_cancelled_error() -> None:
    """Client decline/cancel -> MCPError(REQUEST_CANCELLED) at caller."""
    system = ElicitationSystem()

    async def cancelling_send(message: Dict[str, Any]) -> None:
        async def later() -> None:
            await asyncio.sleep(0)
            await system.cancel_request(message["id"], reason="user declined")

        asyncio.create_task(later())

    system.bind_transport(cancelling_send)
    with pytest.raises(MCPError) as exc_info:
        await system.request_input("Proceed?", timeout=1.0)

    assert exc_info.value.error_code == MCPErrorCode.REQUEST_CANCELLED
    assert "user declined" in str(exc_info.value)


@pytest.mark.asyncio
async def test_elicitation_provide_input_unknown_request_id_returns_false() -> None:
    """Unknown request_id on provide_input returns False, does NOT raise."""
    system = ElicitationSystem()
    result = await system.provide_input("no-such-id", {"whatever": True})
    assert result is False


@pytest.mark.asyncio
async def test_elicitation_cancel_request_unknown_request_id_returns_false() -> None:
    """Unknown request_id on cancel_request returns False, does NOT raise."""
    system = ElicitationSystem()
    result = await system.cancel_request("no-such-id", reason="test")
    assert result is False


# -------------------------------------------------------------------------
# Structural invariant tests — wire-up between MCPServer and ElicitationSystem
# -------------------------------------------------------------------------


def test_mcpserver_exposes_elicitation_system() -> None:
    """MCPServer wires ElicitationSystem as a public attribute.

    Orphan-detection guard: if a future refactor removes
    `self.elicitation_system` from MCPServer.__init__, the manager becomes
    an orphan (class exists, no production call site). This test is the
    structural invariant.
    """
    server = MCPServer("test-server")
    assert isinstance(server.elicitation_system, ElicitationSystem)
    # No transport yet — has_transport must be False.
    assert server.elicitation_system.has_transport() is False


def test_mcpserver_bind_elicitation_transport_is_noop_without_transport() -> None:
    """_bind_elicitation_transport handles missing transport without raising."""
    server = MCPServer("test-server")
    # _transport is None at construction; call must NOT raise.
    server._bind_elicitation_transport()
    assert server.elicitation_system.has_transport() is False


@pytest.mark.asyncio
async def test_mcpserver_route_server_initiated_response_accept_action() -> None:
    """MCPServer._route_server_initiated_response delivers accept-action results."""
    captured: List[Dict[str, Any]] = []
    server = MCPServer("test-server")

    async def capturing_send(message: Dict[str, Any]) -> None:
        captured.append(message)

        # Simulate the server's dispatch receiving the client's response.
        async def later() -> None:
            await asyncio.sleep(0)
            # MCP 2025-06-18 ElicitResult with action=accept.
            response = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"action": "accept", "content": {"choice": "blue"}},
            }
            await server._route_server_initiated_response(response["id"], response)

        asyncio.create_task(later())

    server.elicitation_system.bind_transport(capturing_send)
    result = await server.elicitation_system.request_input("Pick a color:", timeout=1.0)
    assert result == {"choice": "blue"}
    # Verify wire shape captured by the fake transport.
    assert captured[0]["method"] == "elicitation/create"


@pytest.mark.asyncio
async def test_mcpserver_route_server_initiated_response_decline_action() -> None:
    """Decline/cancel action surfaces as MCPError(REQUEST_CANCELLED)."""
    server = MCPServer("test-server")

    async def declining_send(message: Dict[str, Any]) -> None:
        async def later() -> None:
            await asyncio.sleep(0)
            response = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"action": "decline"},
            }
            await server._route_server_initiated_response(response["id"], response)

        asyncio.create_task(later())

    server.elicitation_system.bind_transport(declining_send)
    with pytest.raises(MCPError) as exc_info:
        await server.elicitation_system.request_input("Proceed?", timeout=1.0)
    assert exc_info.value.error_code == MCPErrorCode.REQUEST_CANCELLED
    assert "decline" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mcpserver_route_returns_false_for_unknown_id() -> None:
    """Response for an unknown id is NOT consumed — caller falls through."""
    server = MCPServer("test-server")
    response = {
        "jsonrpc": "2.0",
        "id": "no-pending-request",
        "result": {"action": "accept", "content": "whatever"},
    }
    handled = await server._route_server_initiated_response(response["id"], response)
    assert handled is False
