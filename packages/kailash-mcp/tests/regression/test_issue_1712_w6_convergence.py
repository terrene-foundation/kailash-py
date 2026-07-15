# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 Wave 6 convergence round-2 — FINDING 3
(elicitation client-scoping + fail-closed response routing).

- Elicitation pending entries now carry a bound ``client_id`` (threaded from
  ``request_input`` / resolved from the invoking ``tools/call`` via the bound
  provider) and elicitation/create is dispatched to THAT specific client, not
  broadcast.
- The shared response router (``_route_server_initiated_response``) is
  FAIL-CLOSED for a SCOPED request across ALL THREE features (roots / sampling /
  elicitation): a reply from the WRONG client — OR a None/empty responder —
  cannot resolve another client's pending request.

REAL ``MCPServer`` / ``ElicitationSystem`` objects and REAL handlers; a minimal
capturing transport double satisfies the ``send_message`` structural contract.
"""

import asyncio

import pytest
from kailash_mcp.errors import MCPError, MCPErrorCode
from kailash_mcp.server import MCPServer


class _CapturingTransport:
    """Real (non-mock) transport double capturing outbound (message, client_id)."""

    def __init__(self):
        self.sent: list = []

    async def send_message(self, message, client_id=None):
        self.sent.append((message, client_id))


def _server() -> MCPServer:
    server = MCPServer("w6-convergence-test", enable_cache=False, enable_metrics=False)
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
# Elicitation is dispatched to the bound client, NOT broadcast
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_elicitation_dispatched_to_bound_client_not_broadcast():
    """request_input inherits the invoking client (via the bound provider) and
    dispatches elicitation/create to THAT client — not a broadcast (client_id
    None). The pending entry is scoped to the same client (accessor)."""
    server = _server()
    server.client_info = {"client-A": {"capabilities": {"elicitation": {}}}}
    server.elicitation_system.bind_transport(server._transport.send_message)
    # Emulate the tools/call contextvar binding the server installs.
    server.elicitation_system.bind_client_id_provider(lambda: "client-A")

    task = asyncio.create_task(server.elicitation_system.request_input("q?", timeout=5))
    await _pump_until(lambda: bool(server._transport.sent))

    message, target = server._transport.sent[0]
    assert message["method"] == "elicitation/create"
    # Dispatched to the SPECIFIC client, never broadcast (target would be None).
    assert target == "client-A"

    rid = message["id"]
    assert server.elicitation_system.pending_client_id(rid) == "client-A"

    # Clean up the awaiting task.
    await server.elicitation_system.cancel_request(rid, reason="test cleanup")
    with pytest.raises(MCPError):
        await asyncio.wait_for(task, timeout=5)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_explicit_client_id_still_scopes_elicitation():
    """An explicit client_id on request_input still scopes the pending entry and
    dispatch (unchanged public signature — backward compatible)."""
    server = _server()
    server.client_info = {"client-A": {"capabilities": {"elicitation": {}}}}
    server.elicitation_system.bind_transport(server._transport.send_message)

    task = asyncio.create_task(
        server.elicitation_system.request_input("q?", client_id="client-A", timeout=5)
    )
    await _pump_until(lambda: bool(server._transport.sent))
    message, target = server._transport.sent[0]
    assert target == "client-A"
    assert server.elicitation_system.pending_client_id(message["id"]) == "client-A"

    await server.elicitation_system.cancel_request(message["id"], reason="cleanup")
    with pytest.raises(MCPError):
        await asyncio.wait_for(task, timeout=5)


# ---------------------------------------------------------------------------
# Wrong-client elicitation reply cannot resolve another client's request
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_elicitation_reply_from_wrong_client_cannot_resolve():
    """An elicitation reply from client B cannot resolve client A's pending
    elicitation (handled=False, the request survives)."""
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
    handled = await server._route_server_initiated_response(
        rid,
        {"jsonrpc": "2.0", "id": rid, "result": accept},
        responding_client_id="client-B",
    )
    assert handled is False
    assert not task.done()
    assert rid in server.elicitation_system._pending_requests

    # The bound client resolves it.
    handled = await server._route_server_initiated_response(
        rid,
        {"jsonrpc": "2.0", "id": rid, "result": accept},
        responding_client_id="client-A",
    )
    assert handled is True
    response = await asyncio.wait_for(task, timeout=5)
    assert response == {"answer": "Ada"}


# ---------------------------------------------------------------------------
# Fail-closed: a None responder cannot resolve ANY scoped entry
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_none_responder_cannot_resolve_scoped_roots():
    """A None responding_client_id cannot resolve a scoped roots/list request."""
    server = _server()
    task = asyncio.create_task(server.request_client_roots("client-A", timeout=5))
    await _pump_until(lambda: bool(server._pending_roots_requests))
    req_id = next(iter(server._pending_roots_requests))

    roots_result = {"roots": [{"uri": "file:///workspace"}]}
    # None responder — fail closed on a scoped entry.
    handled = await server._route_server_initiated_response(
        req_id, {"jsonrpc": "2.0", "id": req_id, "result": roots_result}
    )
    assert handled is False
    assert not task.done()
    assert req_id in server._pending_roots_requests

    # The bound client resolves it.
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
async def test_none_responder_cannot_resolve_scoped_elicitation():
    """A None responding_client_id cannot resolve a scoped elicitation request."""
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
    handled = await server._route_server_initiated_response(
        rid, {"jsonrpc": "2.0", "id": rid, "result": accept}
    )
    assert handled is False
    assert not task.done()
    assert rid in server.elicitation_system._pending_requests

    # Bound client resolves it — clean up the awaiter.
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
async def test_none_responder_cannot_resolve_scoped_sampling():
    """A None responding_client_id cannot resolve a scoped sampling request."""
    server = _server()
    server.client_info = {"client-A": {"capabilities": {"sampling": {}}}}
    server.set_sampling_approver(lambda ctx: True)

    task = asyncio.create_task(
        server._handle_sampling_create_message(
            # F4 routes sampling to the REQUESTER's own client — the requester's
            # client_id is merged into params by the WS dispatch layer.
            {"messages": [{"role": "user", "content": "hi"}], "client_id": "client-A"},
            "orig-req",
        )
    )
    await _pump_until(lambda: bool(server._transport.sent))
    sampling_msg, target = server._transport.sent[0]
    sampling_id = sampling_msg["id"]
    assert target == "client-A"

    completion = {"role": "assistant", "content": {"type": "text", "text": "hi!"}}
    # None responder — fail closed on the scoped sampling entry.
    handled = await server._route_server_initiated_response(
        sampling_id, {"jsonrpc": "2.0", "id": sampling_id, "result": completion}
    )
    assert handled is False
    assert not task.done()
    assert sampling_id in server._pending_sampling_requests

    # The bound target resolves it.
    handled = await server._route_server_initiated_response(
        sampling_id,
        {"jsonrpc": "2.0", "id": sampling_id, "result": completion},
        responding_client_id="client-A",
    )
    assert handled is True
    result = await asyncio.wait_for(task, timeout=5)
    assert result["result"] == completion
    assert result["id"] == "orig-req"


# ---------------------------------------------------------------------------
# Unscoped requests keep permissive resolution (backward compatible)
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_unscoped_elicitation_still_resolves_with_none_responder():
    """An UNSCOPED elicitation (no bound client) is still resolvable by a None
    responder — the fail-closed check applies ONLY to scoped entries."""
    server = _server()
    server.client_info = {"client-A": {"capabilities": {"elicitation": {}}}}
    server.elicitation_system.bind_transport(server._transport.send_message)

    # No client_id, no provider bound → unscoped.
    task = asyncio.create_task(server.elicitation_system.request_input("q?", timeout=5))
    await _pump_until(lambda: bool(server.elicitation_system._pending_requests))
    rid = next(iter(server.elicitation_system._pending_requests))
    assert server.elicitation_system.pending_client_id(rid) is None

    accept = {"action": "accept", "content": {"answer": "Grace"}}
    handled = await server._route_server_initiated_response(
        rid, {"jsonrpc": "2.0", "id": rid, "result": accept}
    )
    assert handled is True
    response = await asyncio.wait_for(task, timeout=5)
    assert response == {"answer": "Grace"}
