# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for WebSocketTransport.

Tests cover:
- Transport protocol compliance (name, is_running, start/stop)
- Connection lifecycle (connect, disconnect, tracking)
- Bidirectional message handling (send/receive, JSON-RPC dispatch)
- Error handling (parse errors, method not found, handler exceptions)
- Health check reporting
- Hot-registration of handlers at runtime
- Broadcast and targeted send
- Heartbeat / ping configuration
- Resource cleanup warnings
"""

import asyncio
import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../../src"),
)

from nexus.registry import HandlerDef, HandlerRegistry
from nexus.transports.websocket import (
    ConnectionState,
    WebSocketTransport,
    _TrackedConnection,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry():
    """Provide a fresh HandlerRegistry."""
    return HandlerRegistry()


@pytest.fixture
def transport():
    """Provide a WebSocketTransport with test-friendly defaults."""
    return WebSocketTransport(
        host="127.0.0.1",
        port=0,  # 0 would normally pick a random port; tests mock the server
        ping_interval=5.0,
        ping_timeout=5.0,
    )


@pytest.fixture
def registry_with_handler(registry):
    """Registry pre-loaded with a sample async handler."""

    async def greet(name: str, greeting: str = "Hello") -> dict:
        return {"message": f"{greeting}, {name}!"}

    registry.register_handler("greet", greet, description="Greeting handler")
    return registry


# ---------------------------------------------------------------------------
# Transport protocol compliance
# ---------------------------------------------------------------------------


class TestTransportProtocol:
    """Verify the transport satisfies the Transport ABC contract."""

    def test_name_returns_websocket(self, transport):
        assert transport.name == "websocket"

    def test_is_running_initially_false(self, transport):
        assert transport.is_running is False

    def test_port_returns_configured_port(self):
        t = WebSocketTransport(port=9999)
        assert t.port == 9999

    def test_host_returns_configured_host(self):
        t = WebSocketTransport(host="0.0.0.0")
        assert t.host == "0.0.0.0"

    def test_default_configuration(self):
        t = WebSocketTransport()
        assert t.host == "127.0.0.1"
        assert t.port == 8765
        assert t.name == "websocket"
        assert t.is_running is False
        assert t.connection_count == 0


class TestStartStop:
    """Test start / stop lifecycle with the actual websockets server."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self, registry_with_handler):
        """Starting the transport should set is_running to True."""
        # Use a random available port
        transport = WebSocketTransport(port=0)

        # We need to actually start the server to test the real lifecycle.
        # Use a high port unlikely to conflict.
        transport = WebSocketTransport(host="127.0.0.1", port=18765)
        await transport.start(registry_with_handler)
        try:
            assert transport.is_running is True
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, registry_with_handler):
        transport = WebSocketTransport(host="127.0.0.1", port=18766)
        await transport.start(registry_with_handler)
        await transport.stop()
        assert transport.is_running is False

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, registry_with_handler):
        """Calling stop() multiple times should not raise."""
        transport = WebSocketTransport(host="127.0.0.1", port=18767)
        await transport.start(registry_with_handler)
        await transport.stop()
        # Second stop should be a no-op
        await transport.stop()
        assert transport.is_running is False

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, registry_with_handler):
        """Calling start() while already running should be a no-op."""
        transport = WebSocketTransport(host="127.0.0.1", port=18768)
        await transport.start(registry_with_handler)
        try:
            # Second start should be a no-op
            await transport.start(registry_with_handler)
            assert transport.is_running is True
        finally:
            await transport.stop()


# ---------------------------------------------------------------------------
# Connection lifecycle (real server + real client)
# ---------------------------------------------------------------------------


class TestConnectionLifecycle:
    """Test client connect / disconnect with a real websockets server."""

    @pytest.mark.asyncio
    async def test_client_connect_receives_connection_id(self):
        """A connecting client should receive a 'connected' event with an ID."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18770)
        registry = HandlerRegistry()

        async def echo(text: str) -> dict:
            return {"echo": text}

        registry.register_handler("echo", echo)
        await transport.start(registry)

        try:
            async with connect(f"ws://127.0.0.1:18770/ws") as ws:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                msg = json.loads(raw)
                assert msg["event"] == "connected"
                assert "connection_id" in msg["data"]
                assert len(msg["data"]["connection_id"]) == 32  # hex uuid4
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_connection_count_tracks_clients(self):
        """connection_count should reflect the number of open connections."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18771)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18771/ws") as ws1:
                # Consume the connected event
                await asyncio.wait_for(ws1.recv(), timeout=2.0)
                # Give the server a moment to register
                await asyncio.sleep(0.1)
                assert transport.connection_count >= 1

                async with connect("ws://127.0.0.1:18771/ws") as ws2:
                    await asyncio.wait_for(ws2.recv(), timeout=2.0)
                    await asyncio.sleep(0.1)
                    assert transport.connection_count >= 2
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_disconnect_removes_tracked_connection(self):
        """After a client disconnects, connection_count should decrease."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18772)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)
        await transport.start(registry)

        try:
            ws = await connect("ws://127.0.0.1:18772/ws")
            await asyncio.wait_for(ws.recv(), timeout=2.0)
            await asyncio.sleep(0.1)
            assert transport.connection_count == 1

            await ws.close()
            # Give server time to process disconnect
            await asyncio.sleep(0.3)
            assert transport.connection_count == 0
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_on_connect_callback_fires(self):
        """Registered on_connect callbacks should fire with the connection ID."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18773)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)

        connected_ids = []

        @transport.on_connect
        async def on_conn(connection_id):
            connected_ids.append(connection_id)

        await transport.start(registry)
        try:
            async with connect("ws://127.0.0.1:18773/ws") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
                await asyncio.sleep(0.1)
                assert len(connected_ids) == 1
                assert len(connected_ids[0]) == 32
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_on_disconnect_callback_fires(self):
        """Registered on_disconnect callbacks should fire when a client leaves."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18774)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)

        disconnected_ids = []

        @transport.on_disconnect
        async def on_disc(connection_id):
            disconnected_ids.append(connection_id)

        await transport.start(registry)
        try:
            ws = await connect("ws://127.0.0.1:18774/ws")
            await asyncio.wait_for(ws.recv(), timeout=2.0)
            await ws.close()
            await asyncio.sleep(0.3)
            assert len(disconnected_ids) == 1
        finally:
            await transport.stop()


# ---------------------------------------------------------------------------
# Message send / receive (handler dispatch)
# ---------------------------------------------------------------------------


class TestMessageHandling:
    """Test JSON-RPC style request / response over WebSocket."""

    @pytest.mark.asyncio
    async def test_handler_invocation_returns_result(self):
        """Sending a valid method request should return the handler result."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18780)
        registry = HandlerRegistry()

        async def greet(name: str, greeting: str = "Hello") -> dict:
            return {"message": f"{greeting}, {name}!"}

        registry.register_handler("greet", greet, description="Greet someone")
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18780/ws") as ws:
                # Consume connected event
                await asyncio.wait_for(ws.recv(), timeout=2.0)

                # Send a handler request
                await ws.send(
                    json.dumps(
                        {
                            "id": "req-1",
                            "method": "greet",
                            "params": {"name": "Alice"},
                        }
                    )
                )
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                resp = json.loads(raw)

                assert resp["id"] == "req-1"
                assert resp["result"]["message"] == "Hello, Alice!"
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_handler_with_custom_params(self):
        """Handler should receive all provided params."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18781)
        registry = HandlerRegistry()

        async def greet(name: str, greeting: str = "Hello") -> dict:
            return {"message": f"{greeting}, {name}!"}

        registry.register_handler("greet", greet)
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18781/ws") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
                await ws.send(
                    json.dumps(
                        {
                            "id": "req-2",
                            "method": "greet",
                            "params": {"name": "Bob", "greeting": "Hi"},
                        }
                    )
                )
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                resp = json.loads(raw)
                assert resp["result"]["message"] == "Hi, Bob!"
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_method_not_found_returns_error(self):
        """Requesting a non-existent method should return error code -32601."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18782)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18782/ws") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
                await ws.send(
                    json.dumps({"id": "req-3", "method": "nonexistent", "params": {}})
                )
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                resp = json.loads(raw)
                assert "error" in resp
                assert resp["error"]["code"] == -32601
                assert "nonexistent" in resp["error"]["message"]
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_missing_method_field_returns_error(self):
        """A request without 'method' should return error code -32600."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18783)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18783/ws") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
                await ws.send(json.dumps({"id": "req-4", "params": {}}))
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                resp = json.loads(raw)
                assert resp["error"]["code"] == -32600
                assert "missing" in resp["error"]["message"].lower()
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_invalid_json_returns_parse_error(self):
        """Sending non-JSON text should return error code -32700."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18784)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18784/ws") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
                await ws.send("not valid json {{{")
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                resp = json.loads(raw)
                assert resp["error"]["code"] == -32700
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_handler_exception_returns_server_error(self):
        """If a handler raises, the client should get error code -32000."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18785)
        registry = HandlerRegistry()

        async def broken(x: str) -> dict:
            raise ValueError("something went wrong")

        registry.register_handler("broken", broken)
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18785/ws") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
                await ws.send(
                    json.dumps(
                        {"id": "req-5", "method": "broken", "params": {"x": "a"}}
                    )
                )
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                resp = json.loads(raw)
                assert resp["error"]["code"] == -32000
                assert "Internal handler error" in resp["error"]["message"]
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_non_dict_json_returns_error(self):
        """Sending a JSON array instead of an object should return -32600."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18786)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18786/ws") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
                await ws.send(json.dumps([1, 2, 3]))
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                resp = json.loads(raw)
                assert resp["error"]["code"] == -32600
        finally:
            await transport.stop()


# ---------------------------------------------------------------------------
# Broadcast and targeted send
# ---------------------------------------------------------------------------


class TestBroadcastAndSend:
    """Test server-push messaging (broadcast and send_to)."""

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_clients(self):
        """broadcast() should deliver an event to every connected client."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18790)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18790/ws") as ws1:
                await asyncio.wait_for(ws1.recv(), timeout=2.0)
                async with connect("ws://127.0.0.1:18790/ws") as ws2:
                    await asyncio.wait_for(ws2.recv(), timeout=2.0)
                    await asyncio.sleep(0.1)

                    # Broadcast from the server's event loop
                    loop = transport._loop
                    future = asyncio.run_coroutine_threadsafe(
                        transport.broadcast("test.event", {"key": "value"}), loop
                    )
                    future.result(timeout=2.0)

                    raw1 = await asyncio.wait_for(ws1.recv(), timeout=2.0)
                    raw2 = await asyncio.wait_for(ws2.recv(), timeout=2.0)

                    msg1 = json.loads(raw1)
                    msg2 = json.loads(raw2)

                    assert msg1["event"] == "test.event"
                    assert msg1["data"]["key"] == "value"
                    assert msg2["event"] == "test.event"
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_send_to_specific_client(self):
        """send_to() should deliver only to the targeted connection."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18791)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)
        await transport.start(registry)

        try:
            async with connect("ws://127.0.0.1:18791/ws") as ws1:
                raw = await asyncio.wait_for(ws1.recv(), timeout=2.0)
                conn1_id = json.loads(raw)["data"]["connection_id"]

                async with connect("ws://127.0.0.1:18791/ws") as ws2:
                    await asyncio.wait_for(ws2.recv(), timeout=2.0)
                    await asyncio.sleep(0.1)

                    loop = transport._loop
                    future = asyncio.run_coroutine_threadsafe(
                        transport.send_to(conn1_id, "private", {"secret": 42}),
                        loop,
                    )
                    sent = future.result(timeout=2.0)
                    assert sent is True

                    raw1 = await asyncio.wait_for(ws1.recv(), timeout=2.0)
                    msg = json.loads(raw1)
                    assert msg["event"] == "private"
                    assert msg["data"]["secret"] == 42

                    # ws2 should NOT have received anything (beyond its connect event)
                    with pytest.raises(asyncio.TimeoutError):
                        await asyncio.wait_for(ws2.recv(), timeout=0.3)
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_connection_returns_false(self):
        """send_to() with a bad connection_id should return False."""
        transport = WebSocketTransport(host="127.0.0.1", port=18792)
        registry = HandlerRegistry()

        async def noop(x: str) -> dict:
            return {}

        registry.register_handler("noop", noop)
        await transport.start(registry)

        try:
            loop = transport._loop
            future = asyncio.run_coroutine_threadsafe(
                transport.send_to("nonexistent", "event", {}), loop
            )
            result = future.result(timeout=2.0)
            assert result is False
        finally:
            await transport.stop()


# ---------------------------------------------------------------------------
# Hot-registration
# ---------------------------------------------------------------------------


class TestHotRegistration:
    """Test adding handlers while the transport is already running."""

    @pytest.mark.asyncio
    async def test_on_handler_registered_makes_method_available(self):
        """A handler added via on_handler_registered() should be callable."""
        from websockets.asyncio.client import connect

        transport = WebSocketTransport(host="127.0.0.1", port=18795)
        registry = HandlerRegistry()

        async def initial(x: str) -> dict:
            return {"from": "initial"}

        registry.register_handler("initial", initial)
        await transport.start(registry)

        try:
            # Hot-register a new handler
            async def late(x: str) -> dict:
                return {"from": "late"}

            late_def = HandlerDef(name="late", func=late, description="Late handler")
            transport.on_handler_registered(late_def)

            async with connect("ws://127.0.0.1:18795/ws") as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
                await ws.send(
                    json.dumps({"id": "r1", "method": "late", "params": {"x": "test"}})
                )
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                resp = json.loads(raw)
                assert resp["result"]["from"] == "late"
        finally:
            await transport.stop()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Test the health_check() reporting method."""

    def test_health_check_when_stopped(self):
        transport = WebSocketTransport(host="127.0.0.1", port=9876)
        health = transport.health_check()
        assert health["transport"] == "websocket"
        assert health["running"] is False
        assert health["port"] == 9876
        assert health["connections"] == 0

    @pytest.mark.asyncio
    async def test_health_check_when_running(self, registry_with_handler):
        transport = WebSocketTransport(host="127.0.0.1", port=18796)
        await transport.start(registry_with_handler)
        try:
            health = transport.health_check()
            assert health["running"] is True
            assert health["handlers"] >= 1
        finally:
            await transport.stop()


# ---------------------------------------------------------------------------
# Heartbeat / ping configuration
# ---------------------------------------------------------------------------


class TestHeartbeatConfig:
    """Verify ping_interval and ping_timeout are wired through."""

    def test_custom_ping_values_stored(self):
        t = WebSocketTransport(ping_interval=10.0, ping_timeout=30.0)
        assert t._ping_interval == 10.0
        assert t._ping_timeout == 30.0
        health = t.health_check()
        assert health["ping_interval"] == 10.0

    def test_default_ping_values(self):
        t = WebSocketTransport()
        assert t._ping_interval == 20.0
        assert t._ping_timeout == 20.0


# ---------------------------------------------------------------------------
# ConnectionState enum
# ---------------------------------------------------------------------------


class TestConnectionState:
    """Verify the ConnectionState enum values."""

    def test_enum_values(self):
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.OPEN.value == "open"
        assert ConnectionState.CLOSING.value == "closing"
        assert ConnectionState.CLOSED.value == "closed"


# ---------------------------------------------------------------------------
# _TrackedConnection
# ---------------------------------------------------------------------------


class TestTrackedConnection:
    """Unit tests for the _TrackedConnection internal class."""

    def test_initial_state_is_open(self):
        mock_ws = MagicMock()
        tc = _TrackedConnection(mock_ws, "abc123")
        assert tc.state == ConnectionState.OPEN
        assert tc.connection_id == "abc123"
        assert tc.ws is mock_ws

    def test_timestamps_are_set(self):
        mock_ws = MagicMock()
        before = time.monotonic()
        tc = _TrackedConnection(mock_ws, "xyz")
        after = time.monotonic()
        assert before <= tc.connected_at <= after
        assert before <= tc.last_heartbeat <= after


# ---------------------------------------------------------------------------
# Resource cleanup warning
# ---------------------------------------------------------------------------


class TestResourceCleanup:
    """Verify ResourceWarning on un-stopped transports."""

    def test_del_warns_if_running(self):
        transport = WebSocketTransport(port=19999)
        # Manually set _running to simulate a leaked transport
        transport._running = True
        with pytest.warns(ResourceWarning, match="was not stopped"):
            transport.__del__()

    def test_del_no_warning_if_stopped(self):
        transport = WebSocketTransport(port=19998)
        transport._running = False
        # Should NOT warn
        transport.__del__()  # no assertion needed, just no exception


# ---------------------------------------------------------------------------
# Handler map population from registry
# ---------------------------------------------------------------------------


class TestHandlerMapPopulation:
    """Verify that start() correctly populates the handler dispatch map."""

    @pytest.mark.asyncio
    async def test_handlers_from_registry_are_mapped(self):
        transport = WebSocketTransport(host="127.0.0.1", port=18797)
        registry = HandlerRegistry()

        async def alpha(x: str) -> dict:
            return {"a": 1}

        async def beta(x: str) -> dict:
            return {"b": 2}

        registry.register_handler("alpha", alpha)
        registry.register_handler("beta", beta)

        await transport.start(registry)
        try:
            assert "alpha" in transport._handler_map
            assert "beta" in transport._handler_map
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_workflows_from_registry_are_mapped(self):
        transport = WebSocketTransport(host="127.0.0.1", port=18798)
        registry = HandlerRegistry()

        # Register a workflow (not a handler)
        mock_workflow = MagicMock()
        registry.register_workflow("my_workflow", mock_workflow)

        # Need at least one handler for the registry (transport requires it)
        async def placeholder(x: str) -> dict:
            return {}

        registry.register_handler("_placeholder", placeholder)

        await transport.start(registry)
        try:
            assert "my_workflow" in transport._handler_map
        finally:
            await transport.stop()


# ---------------------------------------------------------------------------
# Max message size configuration
# ---------------------------------------------------------------------------


class TestMaxMessageSize:
    """Verify max_message_size is wired through to the server."""

    def test_custom_max_message_size(self):
        t = WebSocketTransport(max_message_size=512)
        assert t._max_message_size == 512

    def test_default_max_message_size(self):
        t = WebSocketTransport()
        assert t._max_message_size == 1_048_576
