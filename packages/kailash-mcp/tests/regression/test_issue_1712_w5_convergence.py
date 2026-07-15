# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 Wave 5 convergence — the four cross-shard
findings from the holistic redteam:

- **F3** — a client disconnecting with a PENDING elicitation is cancelled +
  evicted (its awaiting ``request_input()`` caller gets a clean
  ``MCP_REQUEST_CANCELLED``, not a hang). An UNSCOPED elicitation (no bound
  ``client_id``) is left intact on a disconnect (backward compatible).
- **F4** — the shared server-initiated response router is CLIENT-SCOPED for
  ALL THREE features (roots, elicitation, sampling): a response from client B
  cannot resolve client A's pending request.

All tests use REAL ``MCPServer`` / ``ElicitationSystem`` objects and REAL
handlers (no SDK mocking of the class under test). A minimal capturing
transport double satisfies the ``send_message`` structural contract only.
"""

import asyncio

import pytest
from kailash_mcp.errors import MCPError, MCPErrorCode
from kailash_mcp.server import MCPServer


class _CapturingTransport:
    """Real (non-mock) transport double capturing outbound requests."""

    def __init__(self):
        self.sent: list = []

    async def send_message(self, message, client_id=None):
        self.sent.append((message, client_id))


def _server() -> MCPServer:
    server = MCPServer("w5-convergence-test", enable_cache=False, enable_metrics=False)
    server.client_info = {}
    server._transport = _CapturingTransport()
    return server


async def _pump_until(predicate, *, tries: int = 200):
    for _ in range(tries):
        await asyncio.sleep(0)
        if predicate():
            return
    raise AssertionError("condition never became true")


# ---------------------------------------------------------------------------
# F3 — elicitation disconnect eviction
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_disconnect_cancels_pending_elicitation_for_client():
    """A disconnect cancels+evicts a client's pending elicitation; the awaiting
    caller raises MCP_REQUEST_CANCELLED instead of hanging."""
    server = _server()
    server.client_info = {"client-A": {"capabilities": {"elicitation": {}}}}
    server.elicitation_system.bind_transport(server._transport.send_message)

    task = asyncio.create_task(
        server.elicitation_system.request_input(
            "your name?", client_id="client-A", timeout=30
        )
    )
    await _pump_until(lambda: bool(server.elicitation_system._pending_requests))
    rid = next(iter(server.elicitation_system._pending_requests))

    server._on_ws_disconnect("client-A")

    # Evicted immediately.
    assert rid not in server.elicitation_system._pending_requests

    # The awaiting caller gets a clean cancellation, not a hang.
    with pytest.raises(MCPError) as ei:
        await asyncio.wait_for(task, timeout=5)
    assert ei.value.error_code == MCPErrorCode.MCP_REQUEST_CANCELLED


@pytest.mark.regression
@pytest.mark.asyncio
async def test_disconnect_leaves_unscoped_elicitation_intact():
    """An UNSCOPED elicitation (no client_id) is NOT evicted on a disconnect —
    a disconnect cannot know it targeted the departing client."""
    server = _server()
    server.client_info = {"client-A": {"capabilities": {"elicitation": {}}}}
    server.elicitation_system.bind_transport(server._transport.send_message)

    task = asyncio.create_task(server.elicitation_system.request_input("q?", timeout=5))
    await _pump_until(lambda: bool(server.elicitation_system._pending_requests))
    rid = next(iter(server.elicitation_system._pending_requests))

    server._on_ws_disconnect("client-A")

    # Unscoped request survives the disconnect.
    assert rid in server.elicitation_system._pending_requests

    # Clean up: resolve it so the awaiting task does not leak.
    await server.elicitation_system.cancel_request(rid, reason="test cleanup")
    with pytest.raises(MCPError):
        await asyncio.wait_for(task, timeout=5)


# ---------------------------------------------------------------------------
# F4 — client-scoped response routing (roots / elicitation / sampling)
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_roots_response_from_wrong_client_cannot_resolve():
    """A roots/list response from client B cannot resolve client A's pending
    request; the real responder (A) still can."""
    server = _server()

    task = asyncio.create_task(server.request_client_roots("client-A", timeout=5))
    await _pump_until(lambda: bool(server._pending_roots_requests))
    req_id = next(iter(server._pending_roots_requests))

    roots_result = {"roots": [{"uri": "file:///workspace"}]}

    # Wrong client — router refuses; the pending request survives.
    handled = await server._route_server_initiated_response(
        req_id,
        {"jsonrpc": "2.0", "id": req_id, "result": roots_result},
        responding_client_id="client-B",
    )
    assert handled is False
    assert not task.done()
    assert req_id in server._pending_roots_requests

    # Correct client — resolves.
    handled = await server._route_server_initiated_response(
        req_id,
        {"jsonrpc": "2.0", "id": req_id, "result": roots_result},
        responding_client_id="client-A",
    )
    assert handled is True
    roots = await asyncio.wait_for(task, timeout=5)
    assert roots == [{"uri": "file:///workspace"}]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_elicitation_response_from_wrong_client_cannot_resolve():
    """An elicitation response from client B cannot resolve client A's pending
    request; the real responder (A) still can."""
    server = _server()
    server.client_info = {"client-A": {"capabilities": {"elicitation": {}}}}
    server.elicitation_system.bind_transport(server._transport.send_message)

    task = asyncio.create_task(
        server.elicitation_system.request_input(
            "your name?", client_id="client-A", timeout=5
        )
    )
    await _pump_until(lambda: bool(server.elicitation_system._pending_requests))
    rid = next(iter(server.elicitation_system._pending_requests))

    accept = {"action": "accept", "content": {"answer": "Ada"}}

    # Wrong client — router refuses; the pending request survives.
    handled = await server._route_server_initiated_response(
        rid,
        {"jsonrpc": "2.0", "id": rid, "result": accept},
        responding_client_id="client-B",
    )
    assert handled is False
    assert not task.done()
    assert rid in server.elicitation_system._pending_requests

    # Correct client — resolves with the collected content.
    handled = await server._route_server_initiated_response(
        rid,
        {"jsonrpc": "2.0", "id": rid, "result": accept},
        responding_client_id="client-A",
    )
    assert handled is True
    response = await asyncio.wait_for(task, timeout=5)
    assert response == {"answer": "Ada"}


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_response_from_wrong_client_cannot_resolve():
    """A sampling response from client B cannot resolve the request dispatched
    to client A; the real target (A) still can."""
    server = _server()
    server.client_info = {"client-A": {"capabilities": {"sampling": {}}}}
    server.set_sampling_approver(lambda ctx: True)

    task = asyncio.create_task(
        server._handle_sampling_create_message(
            {"messages": [{"role": "user", "content": "hi"}]},
            "orig-req",
        )
    )
    await _pump_until(lambda: bool(server._transport.sent))
    sampling_msg, target = server._transport.sent[0]
    sampling_id = sampling_msg["id"]
    assert target == "client-A"

    completion = {"role": "assistant", "content": {"type": "text", "text": "hi!"}}

    # Wrong client — router refuses; the pending request survives.
    handled = await server._route_server_initiated_response(
        sampling_id,
        {"jsonrpc": "2.0", "id": sampling_id, "result": completion},
        responding_client_id="client-B",
    )
    assert handled is False
    assert not task.done()
    assert sampling_id in server._pending_sampling_requests

    # Correct target — resolves and the requester gets the completion.
    handled = await server._route_server_initiated_response(
        sampling_id,
        {"jsonrpc": "2.0", "id": sampling_id, "result": completion},
        responding_client_id="client-A",
    )
    assert handled is True
    result = await asyncio.wait_for(task, timeout=5)
    assert result["result"] == completion
    assert result["id"] == "orig-req"
