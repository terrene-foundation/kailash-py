"""#1712 convergence round-3 (Wave 7): concurrency-hardening regressions.

All three were newly reachable once the WS transport began dispatching handlers
CONCURRENTLY (Wave 6 F2). Each pins a fix so a future refactor cannot silently
re-open it.
"""

import asyncio

import pytest
from kailash_mcp.server import MCPServer
from kailash_mcp.transports.transports import WebSocketServerTransport


class _FailTransport:
    async def send_message(self, message, client_id=None):
        raise RuntimeError("socket dropped mid-dispatch")

    def has_client(self, client_id):
        return True


class _NoopTransport:
    async def send_message(self, message, client_id=None):
        return None

    def has_client(self, client_id):
        return True


@pytest.mark.regression
def test_progress_token_namespaced_by_request_id():
    """F1: two CONCURRENT same-client calls reusing one progressToken value get
    DISTINCT internal ProgressManager keys (namespaced by request_id), so they
    cannot corrupt each other's progress under concurrent WS dispatch."""
    server = MCPServer("w7")
    server.client_info["cA"] = {}
    server._transport = _NoopTransport()
    params = {"_meta": {"progressToken": "1"}}
    t1 = server._begin_progress(params, "cA", "op", "req-1")
    t2 = server._begin_progress(params, "cA", "op", "req-2")
    assert t1 is not None and t2 is not None
    assert t1.value != t2.value  # request_id disambiguates the shared token "1"
    assert "req-1" in t1.value and "req-2" in t2.value


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_dispatch_send_failure_no_pending_leak():
    """F2: a dispatch send failure drops the pending sampling entry from ALL
    three maps (no leaked Future, no dead id seeding the FIFO deque)."""
    server = MCPServer("w7")
    server.set_sampling_approver(lambda ctx: True)
    server.client_info = {"cA": {"capabilities": {"sampling": {}}}}
    server._transport = _FailTransport()
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}], "client_id": "cA"},
        "req-x",
    )
    assert result["error"]["code"] == -32603
    assert server._pending_sampling_requests == {}
    assert len(server._pending_sampling_order) == 0
    assert server._pending_sampling_clients == {}


@pytest.mark.regression
@pytest.mark.asyncio
async def test_roots_dispatch_send_failure_no_pending_leak():
    """F2: a roots/list dispatch send failure drops the pending roots entry and
    falls back to an empty list."""
    server = MCPServer("w7")
    server._transport = _FailTransport()
    roots = await server.request_client_roots("cA", timeout=1.0)
    assert roots == []
    assert server._pending_roots_requests == {}
    assert server._pending_roots_clients == {}


@pytest.mark.regression
def test_per_client_send_lock_shared_and_distinct():
    """F3: the WS transport's send lock is ONE lock per client_id (shared by the
    response path AND every server-initiated send), stable across calls and
    distinct per client."""
    transport = WebSocketServerTransport()
    a1 = transport._get_send_lock("cA")
    a2 = transport._get_send_lock("cA")
    b1 = transport._get_send_lock("cB")
    assert a1 is a2  # same client -> same lock (serializes all its sends)
    assert a1 is not b1  # different clients -> independent locks
