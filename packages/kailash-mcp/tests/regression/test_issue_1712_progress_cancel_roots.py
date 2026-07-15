# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 Wave 3 - progress/cancellation + roots
(MCP revision 2025-11-25).

Behavioral pins (call the real handler / real ``MCPServer`` / real
``RootsManager`` - never source-grep, per ``rules/testing.md``) for the two
gaps:

* **B3 progress & cancellation**
  - B3.1 ``_meta.progressToken`` echo: ``notifications/progress`` emitted for a
    tools/call carry the client-supplied token; NONE emitted when absent (opt-in).
  - B3.2 inbound ``notifications/cancelled`` drives cancellation of the
    referenced in-flight request id via the shared ``CancellationManager``.
  - B3.3 a ``notifications/cancelled`` targeting the ``initialize`` request is
    ignored (initialize is non-cancellable).
  - B3.4 cancelling an already-completed id is a graceful no-op.

* **E2 roots**
  - E2.1 ``RootsManager.validate_access`` accepts ``user_context`` (regression
    for the latent ``TypeError`` at the ``_handle_roots_list`` call site).
  - E2.2 server-initiated ``roots/list`` falls back to no-roots on a ``-32601``.
  - E2.3 ``notifications/roots/list_changed`` refreshes the cached roots.
  - E2.4 root-URI matching is path-SEGMENT based: ``file:///workspace`` does NOT
    authorize ``file:///workspace-evil`` (security.md).
"""

import asyncio

import pytest
from kailash_mcp.protocol.protocol import (
    RootsManager,
    cancel_request,
    get_protocol_manager,
    is_cancelled,
)
from kailash_mcp.server import MCPServer


def _make_server() -> MCPServer:
    """A minimal MCPServer with no cache/metrics/auth for handler pins."""
    return MCPServer(
        "w3-progress-cancel-roots-test",
        enable_cache=False,
        enable_metrics=False,
    )


class _CapturingTransport:
    """Real (non-mock) transport double that captures outbound messages and can
    auto-reply to a server-initiated ``roots/list`` request.

    Satisfies the ``send_message`` structural contract the server calls; NOT a
    ``unittest.mock`` object. ``roots_reply`` is the ``result``/``error`` dict
    the client would send back for a ``roots/list`` request.
    """

    def __init__(self, server=None, roots_reply=None):
        self.sent: list = []
        self._server = server
        self._roots_reply = roots_reply

    async def send_message(self, message, client_id=None):
        self.sent.append((message, client_id))
        if (
            self._server is not None
            and isinstance(message, dict)
            and message.get("method") == "roots/list"
            and "id" in message
            and self._roots_reply is not None
        ):
            reply = {"jsonrpc": "2.0", "id": message["id"], **self._roots_reply}
            # Schedule the client's response on the same loop; request_client_roots
            # is awaiting the pending Future and will resolve when this runs. The
            # reply carries the responding client_id (the client the roots/list was
            # dispatched to) — the response router is fail-closed for scoped
            # requests (W6 FINDING 3), so a None responder would be refused.
            asyncio.get_event_loop().create_task(
                self._server._route_server_initiated_response(
                    reply["id"], reply, responding_client_id=client_id
                )
            )


@pytest.fixture(autouse=True)
def _clean_protocol_state():
    """Reset the process-global protocol manager roots/cancellation/progress
    between tests (get_protocol_manager returns a singleton)."""
    from collections import deque

    mgr = get_protocol_manager()
    mgr.roots._roots = []
    mgr.cancellation._cancelled_requests = set()
    mgr.cancellation._cancelled_order = deque()
    mgr.cancellation._cancellation_callbacks = {}
    mgr.cancellation._request_cleanup = {}
    mgr.cancellation._cancellation_reasons = {}
    mgr.progress._active_progress = {}
    mgr.progress._progress_callbacks = {}
    yield


# --------------------------------------------------------------------------- #
# B3.1 — progressToken echo (opt-in)
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_progress_token_echoed_on_notifications_progress():
    server = _make_server()
    server._transport = _CapturingTransport()
    server._tool_registry["echo"] = {
        "function": lambda **kw: {"echoed": True},
        "call_count": 0,
        "error_count": 0,
        "last_called": None,
    }

    result = await server._handle_call_tool(
        {"name": "echo", "arguments": {}, "_meta": {"progressToken": "tok-42"}},
        "req-1",
        client_id="client-A",
    )
    assert "result" in result

    progress = [
        msg
        for (msg, _cid) in server._transport.sent
        if msg.get("method") == "notifications/progress"
    ]
    assert progress, "a notifications/progress MUST be emitted when a token is supplied"
    assert all(
        m["params"]["progressToken"] == "tok-42" for m in progress
    ), "every progress notification MUST carry the client-supplied token"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_no_progress_notification_when_token_absent():
    server = _make_server()
    server._transport = _CapturingTransport()
    server._tool_registry["echo"] = {
        "function": lambda **kw: {"echoed": True},
        "call_count": 0,
        "error_count": 0,
        "last_called": None,
    }

    # No _meta.progressToken -> progress is opt-in -> NO progress notification.
    await server._handle_call_tool(
        {"name": "echo", "arguments": {}}, "req-2", client_id="client-A"
    )
    progress = [
        msg
        for (msg, _cid) in server._transport.sent
        if msg.get("method") == "notifications/progress"
    ]
    assert progress == [], "no progressToken supplied -> no progress notification"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_progress_token_type_preserved_integer():
    """A client MAY supply an integer progressToken (spec allows string|int);
    the echoed token preserves the exact value/type."""
    server = _make_server()
    server._transport = _CapturingTransport()
    server._tool_registry["echo"] = {
        "function": lambda **kw: {"echoed": True},
        "call_count": 0,
        "error_count": 0,
        "last_called": None,
    }

    await server._handle_call_tool(
        {"name": "echo", "arguments": {}, "_meta": {"progressToken": 7}},
        "req-3",
        client_id="client-A",
    )
    progress = [
        msg
        for (msg, _cid) in server._transport.sent
        if msg.get("method") == "notifications/progress"
    ]
    assert progress and progress[0]["params"]["progressToken"] == 7


# --------------------------------------------------------------------------- #
# B3.2 / B3.3 / B3.4 — notifications/cancelled
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cancelled_notification_cancels_in_flight_request():
    server = _make_server()
    # Dispatch a notification (request_id=None) so the notification path runs.
    ret = await server._dispatch_ws_method(
        "notifications/cancelled",
        {"requestId": "in-flight-9", "reason": "user aborted"},
        None,
        "client-A",
    )
    assert ret is None, "a notification MUST NOT produce a response body"
    # Cancellation is now recorded under the CLIENT-SCOPED composite key so a
    # cancellation from one client cannot cancel another's identical request id.
    assert is_cancelled(server._cancel_key("client-A", "in-flight-9")) is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_initialize_is_non_cancellable():
    server = _make_server()
    # Record the initialize request id for this client (as _handle_initialize does).
    await server._handle_initialize(
        {"protocolVersion": "2025-11-25", "capabilities": {}},
        "init-req-1",
        "client-A",
    )
    await server._dispatch_ws_method(
        "notifications/cancelled",
        {"requestId": "init-req-1"},
        None,
        "client-A",
    )
    assert (
        is_cancelled("init-req-1") is False
    ), "initialize MUST NOT be cancellable (spec 2025-11-25)"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cancel_after_complete_is_graceful_noop():
    server = _make_server()
    key = server._cancel_key("client-A", "done-1")
    # First cancellation marks the id; a completed request has no callbacks and
    # no in-flight task, so this is a graceful no-op that still records the id.
    await server._handle_cancelled_notification(
        {"requestId": "done-1", "reason": "late"}, "client-A"
    )
    assert is_cancelled(key) is True
    # A SECOND cancellation of the same (already-finished) id must not raise.
    await server._handle_cancelled_notification(
        {"requestId": "done-1", "reason": "even later"}, "client-A"
    )
    assert is_cancelled(key) is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cancelled_notification_missing_request_id_is_ignored():
    server = _make_server()
    # No requestId -> nothing to cancel, no crash.
    await server._handle_cancelled_notification({"reason": "noop"}, "client-A")


# --------------------------------------------------------------------------- #
# E2.1 — validate_access accepts user_context (TypeError regression)
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_validate_access_accepts_user_context_no_typeerror():
    """The exact call shape ``_handle_roots_list`` uses MUST NOT raise TypeError."""
    roots = RootsManager()
    roots.add_root("file:///workspace")
    allowed = await roots.validate_access(
        "file:///workspace/doc.txt",
        operation="list",
        user_context={"user_id": "u1", "capabilities": {}},
    )
    assert allowed is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_validate_access_forwards_user_context_to_validator():
    """A 3-arg validator receives the user_context; consent decision uses it."""
    roots = RootsManager()
    roots.add_root("file:///workspace")
    seen = {}

    async def validator(uri, operation, user_context):
        seen["ctx"] = user_context
        return user_context.get("user_id") == "u1"

    roots.add_access_validator(validator)
    allowed = await roots.validate_access(
        "file:///workspace/a", operation="read", user_context={"user_id": "u1"}
    )
    assert allowed is True
    assert seen["ctx"] == {"user_id": "u1"}

    denied = await roots.validate_access(
        "file:///workspace/a", operation="read", user_context={"user_id": "other"}
    )
    assert denied is False


@pytest.mark.regression
@pytest.mark.asyncio
async def test_validate_access_two_arg_validator_still_supported():
    """Legacy (uri, operation) validators keep working (backward compat)."""
    roots = RootsManager()
    roots.add_root("file:///workspace")

    def legacy_validator(uri, operation):
        return "workspace" in uri

    roots.add_access_validator(legacy_validator)
    assert await roots.validate_access("file:///workspace/a") is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_handle_roots_list_real_validate_access_path():
    """End-to-end: _handle_roots_list with an auth_manager set drives the REAL
    validate_access(user_context=...) call site that previously raised TypeError."""
    server = _make_server()
    server.auth_manager = object()  # truthy -> access-control branch runs
    mgr = get_protocol_manager()
    mgr.roots.add_root("file:///workspace")
    client_id = "client-A"
    server.client_info[client_id] = {
        "capabilities": {"roots": {"listChanged": True}},
        "user_id": "u1",
    }
    result = await server._handle_roots_list({"client_id": client_id}, "req-roots-1")
    assert "result" in result
    assert any(r["uri"] == "file:///workspace" for r in result["result"]["roots"])


# --------------------------------------------------------------------------- #
# E2.4 — path-SEGMENT root-URI matching (security)
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_path_segment_matching_rejects_prefix_sibling():
    roots = RootsManager()
    roots.add_root("file:///workspace")
    # Exact root and true descendants are authorized.
    assert await roots.validate_access("file:///workspace") is True
    assert await roots.validate_access("file:///workspace/sub/file.txt") is True
    # A sibling sharing the name PREFIX is a different directory -> denied.
    assert await roots.validate_access("file:///workspace-evil") is False
    assert await roots.validate_access("file:///workspace-evil/secret") is False


@pytest.mark.regression
def test_find_root_for_uri_is_path_segment():
    roots = RootsManager()
    roots.add_root("file:///workspace")
    assert roots.find_root_for_uri("file:///workspace/a")["uri"] == "file:///workspace"
    assert roots.find_root_for_uri("file:///workspace-evil") is None


# --------------------------------------------------------------------------- #
# E2.2 — server-initiated roots/list + -32601 fallback
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_request_client_roots_unsupported_falls_back_to_empty():
    server = _make_server()
    server._transport = _CapturingTransport(
        server=server,
        roots_reply={"error": {"code": -32601, "message": "roots not supported"}},
    )
    roots = await server.request_client_roots("client-A", timeout=2.0)
    assert roots == [], "-32601 -> capability absent -> no roots"
    # A roots/list request was actually sent to the client.
    assert any(m.get("method") == "roots/list" for (m, _cid) in server._transport.sent)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_request_client_roots_success_caches():
    server = _make_server()
    server._transport = _CapturingTransport(
        server=server,
        roots_reply={"result": {"roots": [{"uri": "file:///client-root"}]}},
    )
    roots = await server.request_client_roots("client-A", timeout=2.0)
    assert roots == [{"uri": "file:///client-root"}]
    assert server._client_roots["client-A"] == [{"uri": "file:///client-root"}]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_request_client_roots_no_transport_returns_empty():
    server = _make_server()
    server._transport = None
    assert await server.request_client_roots("client-A") == []


# --------------------------------------------------------------------------- #
# E2.3 — notifications/roots/list_changed refreshes the cache
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_roots_list_changed_refreshes_cache():
    server = _make_server()
    # Prime a stale cache entry.
    server._client_roots["client-A"] = [{"uri": "file:///stale"}]
    server._transport = _CapturingTransport(
        server=server,
        roots_reply={"result": {"roots": [{"uri": "file:///fresh"}]}},
    )
    await server._dispatch_ws_method(
        "notifications/roots/list_changed", {}, None, "client-A"
    )
    assert server._client_roots["client-A"] == [{"uri": "file:///fresh"}]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_roots_list_changed_without_client_id_is_ignored():
    server = _make_server()
    # Should not raise even with no client_id.
    await server._handle_roots_list_changed(None)


# --------------------------------------------------------------------------- #
# FINDING 2 — cross-client progressToken isolation (same token value)
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_progress_token_isolated_across_clients_same_value():
    """Two clients using the SAME progressToken value get ISOLATED progress:
    A's updates route ONLY to A, and A's completion does NOT delete B's entry.

    The process-global ProgressManager keys a ProgressToken by ``value`` only
    (``__hash__`` = ``hash(self.value)``); without the (client_id, token)
    namespacing the two clients collide (A's notifications reach B; A's
    completion evicts B)."""
    server = _make_server()
    server._transport = _CapturingTransport()
    mgr = get_protocol_manager()

    tok_a = server._begin_progress({"_meta": {"progressToken": "1"}}, "client-A", "op")
    tok_b = server._begin_progress({"_meta": {"progressToken": "1"}}, "client-B", "op")
    assert tok_a is not None and tok_b is not None
    # Same client token value, DISTINCT internal keys.
    assert tok_a.value != tok_b.value
    assert mgr.progress.get_progress_info(tok_a) is not None
    assert mgr.progress.get_progress_info(tok_b) is not None

    # An update on A's token routes ONLY to client-A, carrying the RAW token.
    await mgr.progress.update_progress(tok_a, progress=50)
    updates = [
        (cid, msg)
        for (msg, cid) in server._transport.sent
        if msg.get("method") == "notifications/progress"
    ]
    assert updates, "A's update MUST emit a progress notification"
    assert all(cid == "client-A" for cid, _ in updates), "A's update MUST NOT reach B"
    assert all(msg["params"]["progressToken"] == "1" for _, msg in updates)

    # Completing A must NOT delete B's still-active entry.
    await server._finish_progress(tok_a, "completed")
    assert mgr.progress.get_progress_info(tok_a) is None
    assert (
        mgr.progress.get_progress_info(tok_b) is not None
    ), "B's progress entry MUST survive A's completion"


# --------------------------------------------------------------------------- #
# FINDING 3 (server-side) — cancellation actually stops the tool + is scoped
# --------------------------------------------------------------------------- #


def _register_blocking_tool(server, name, started, release, completed):
    async def _tool(**kwargs):
        started.set()
        await release.wait()  # cancellation interrupts here
        completed["ran_to_end"] = True
        return {"done": True}

    server._tool_registry[name] = {
        "function": _tool,
        "call_count": 0,
        "error_count": 0,
        "last_called": None,
    }


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cancelled_in_flight_tool_stops_and_sends_no_response():
    """An inbound notifications/cancelled STOPS a running tool; the tools/call
    handler returns NO normal response (cancellation is a real control action,
    not an inert flag)."""
    server = _make_server()
    server._transport = _CapturingTransport()
    started = asyncio.Event()
    release = asyncio.Event()  # never set -> tool blocks until cancelled
    completed = {"ran_to_end": False}
    _register_blocking_tool(server, "slow", started, release, completed)

    call = asyncio.ensure_future(
        server._handle_call_tool(
            {"name": "slow", "arguments": {}}, "req-cancel-1", client_id="client-A"
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2.0)
    key = server._cancel_key("client-A", "req-cancel-1")
    assert key in server._inflight_tasks, "the running tool MUST be tracked in-flight"

    await server._handle_cancelled_notification(
        {"requestId": "req-cancel-1", "reason": "user aborted"}, "client-A"
    )
    result = await asyncio.wait_for(call, timeout=2.0)

    assert result is None, "a cancelled request MUST receive NO normal response"
    assert completed["ran_to_end"] is False, "the tool MUST NOT run to completion"
    assert key not in server._inflight_tasks, "in-flight entry MUST be popped on exit"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cancellation_is_client_scoped_across_clients():
    """A notifications/cancelled from client B MUST NOT cancel client A's
    identically-numbered in-flight request (per-client isolation)."""
    server = _make_server()
    server._transport = _CapturingTransport()
    started = asyncio.Event()
    release = asyncio.Event()
    completed = {"ran_to_end": False}
    _register_blocking_tool(server, "slow", started, release, completed)

    # client-A starts request id "5".
    call = asyncio.ensure_future(
        server._handle_call_tool(
            {"name": "slow", "arguments": {}}, "5", client_id="client-A"
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2.0)
    key_a = server._cancel_key("client-A", "5")
    assert key_a in server._inflight_tasks

    # client-B cancels ITS request id "5" — A's task must be untouched.
    await server._handle_cancelled_notification({"requestId": "5"}, "client-B")
    assert key_a in server._inflight_tasks, "B's cancel MUST NOT touch A's request"
    assert not server._inflight_tasks[key_a].done()

    # Let A's tool finish normally -> a real response is returned.
    release.set()
    result = await asyncio.wait_for(call, timeout=2.0)
    assert result is not None and "result" in result
    assert completed["ran_to_end"] is True


# --------------------------------------------------------------------------- #
# FINDING 1 — percent-encoded traversal denial
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_percent_encoded_traversal_denied():
    """A percent-encoded ``../`` (``%2e%2e``) MUST NOT escape a granted root
    (decode-then-reject-traversal, security.md)."""
    roots = RootsManager()
    roots.add_root("file:///workspace")
    # Plain and percent-encoded traversal are BOTH denied.
    assert await roots.validate_access("file:///workspace/../../etc/passwd") is False
    assert (
        await roots.validate_access("file:///workspace/%2e%2e/%2e%2e/etc/passwd")
        is False
    )
    assert await roots.validate_access("file:///workspace/%2e%2e/etc") is False
    # A legitimate descendant is still allowed.
    assert await roots.validate_access("file:///workspace/sub/file.txt") is True


# --------------------------------------------------------------------------- #
# FINDING 4 — disconnect evicts all per-client server state
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_disconnect_evicts_per_client_state():
    """``_on_ws_disconnect`` MUST drop this client's roots cache, log level,
    pending roots Futures, in-flight tool tasks, and cancelled-request state."""
    server = _make_server()
    cid = "client-A"

    server._client_roots[cid] = [{"uri": "file:///r"}]
    server._client_log_levels[cid] = "DEBUG"

    loop = asyncio.get_event_loop()
    fut: "asyncio.Future" = loop.create_future()
    server._pending_roots_requests["rid-1"] = fut
    server._pending_roots_clients["rid-1"] = cid

    async def _block():
        await asyncio.Event().wait()

    task = asyncio.ensure_future(_block())
    server._inflight_tasks[server._cancel_key(cid, "req-1")] = task

    await cancel_request(server._cancel_key(cid, "old-req"))
    assert is_cancelled(server._cancel_key(cid, "old-req")) is True

    server._on_ws_disconnect(cid)

    assert cid not in server._client_roots
    assert cid not in server._client_log_levels
    assert "rid-1" not in server._pending_roots_requests
    assert "rid-1" not in server._pending_roots_clients
    assert fut.cancelled(), "a pending roots Future for this client MUST be cancelled"
    assert server._cancel_key(cid, "req-1") not in server._inflight_tasks
    assert (
        is_cancelled(server._cancel_key(cid, "old-req")) is False
    ), "this client's cancelled-request state MUST be evicted"

    # The in-flight task was cancelled; drain it to avoid a pending-task warning.
    with pytest.raises(asyncio.CancelledError):
        await task


# --------------------------------------------------------------------------- #
# FINDING 5 — _handle_roots_list reflects the client's declared roots (cache read)
# --------------------------------------------------------------------------- #


@pytest.mark.regression
@pytest.mark.asyncio
async def test_handle_roots_list_reflects_client_declared_roots():
    """A client that has declared roots (cached in ``_client_roots`` via a
    server-initiated roots/list) has them reflected by ``_handle_roots_list`` —
    the cache + the list_changed refresh now have an observable consumer."""
    server = _make_server()
    cid = "client-A"
    server.client_info[cid] = {"capabilities": {"roots": {"listChanged": True}}}
    server._client_roots[cid] = [{"uri": "file:///client-home"}]

    mgr = get_protocol_manager()
    mgr.roots.add_root("file:///server-root")

    result = await server._handle_roots_list({"client_id": cid}, "req-roots-x")
    uris = [r["uri"] for r in result["result"]["roots"]]
    assert (
        "file:///client-home" in uris
    ), "the client's declared roots MUST be reflected"
    assert "file:///server-root" in uris, "server roots remain present (merge)"
