"""Comprehensive tests to boost middleware.communication.realtime coverage from 16% to >80%."""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import Request, WebSocket


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.accepted = False
        self.closed = False
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def close(self):
        self.closed = True

    async def send_text(self, data: str):
        self.messages.append(data)

    async def send_json(self, data: dict):
        self.messages.append(json.dumps(data))


class MockEvent:
    """Mock event for testing."""

    def __init__(
        self, event_type="test.event", data=None, session_id=None, user_id=None
    ):
        self.event_type = event_type
        self.data = data or {}
        self.session_id = session_id
        self.user_id = user_id
        self.timestamp = datetime.now(timezone.utc)
        self.event_id = str(uuid.uuid4())

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "user_id": self.user_id,
        }


class TestConnectionManager:
    """Test ConnectionManager functionality."""

    def test_connection_manager_init(self):
        """Test ConnectionManager initialization."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            assert isinstance(manager.connections, dict)
            assert isinstance(manager.session_connections, dict)
            assert isinstance(manager.user_connections, dict)

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_connect_websocket(self):
        """Test WebSocket connection."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            websocket = MockWebSocket()
            connection_id = "conn_123"

            async def test_async():
                await manager.connect(
                    websocket=websocket,
                    connection_id=connection_id,
                    session_id="session_1",
                    user_id="user_1",
                )

                assert websocket.accepted is True
                assert connection_id in manager.connections
                connection = manager.connections[connection_id]
                assert connection["websocket"] == websocket
                assert connection["session_id"] == "session_1"
                assert connection["user_id"] == "user_1"
                assert "session_1" in manager.session_connections
                assert "user_1" in manager.user_connections

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_connect_websocket_without_session_user(self):
        """Test WebSocket connection without session or user ID."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            websocket = MockWebSocket()
            connection_id = "conn_123"

            async def test_async():
                await manager.connect(websocket=websocket, connection_id=connection_id)

                assert websocket.accepted is True
                assert connection_id in manager.connections
                connection = manager.connections[connection_id]
                assert connection["session_id"] is None
                assert connection["user_id"] is None

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_disconnect_websocket(self):
        """Test WebSocket disconnection."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            websocket = MockWebSocket()
            connection_id = "conn_123"

            async def test_async():
                # First connect
                await manager.connect(
                    websocket=websocket,
                    connection_id=connection_id,
                    session_id="session_1",
                    user_id="user_1",
                )

                # Then disconnect
                await manager.disconnect(connection_id)

                assert websocket.closed is True
                assert connection_id not in manager.connections
                assert "session_1" not in manager.session_connections
                assert "user_1" not in manager.user_connections

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_disconnect_nonexistent_connection(self):
        """Test disconnecting non-existent connection."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()

            async def test_async():
                # Should not raise error
                await manager.disconnect("nonexistent")

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_send_to_connection(self):
        """Test sending message to specific connection."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            websocket = MockWebSocket()
            connection_id = "conn_123"

            async def test_async():
                await manager.connect(websocket, connection_id)

                message = {"type": "test", "data": "hello"}
                result = await manager.send_to_connection(connection_id, message)

                assert result is True
                assert len(websocket.messages) == 1
                sent_message = json.loads(websocket.messages[0])
                assert sent_message == message

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_send_to_nonexistent_connection(self):
        """Test sending message to non-existent connection."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()

            async def test_async():
                message = {"type": "test", "data": "hello"}
                result = await manager.send_to_connection("nonexistent", message)
                assert result is False

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_send_to_session(self):
        """Test sending message to all connections in a session."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            websocket1 = MockWebSocket()
            websocket2 = MockWebSocket()

            async def test_async():
                await manager.connect(websocket1, "conn_1", session_id="session_1")
                await manager.connect(websocket2, "conn_2", session_id="session_1")

                message = {"type": "session_update", "data": "broadcast"}
                count = await manager.send_to_session("session_1", message)

                assert count == 2
                assert len(websocket1.messages) == 1
                assert len(websocket2.messages) == 1

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_send_to_user(self):
        """Test sending message to all connections for a user."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            websocket1 = MockWebSocket()
            websocket2 = MockWebSocket()

            async def test_async():
                await manager.connect(websocket1, "conn_1", user_id="user_1")
                await manager.connect(websocket2, "conn_2", user_id="user_1")

                message = {"type": "user_notification", "data": "alert"}
                count = await manager.send_to_user("user_1", message)

                assert count == 2
                assert len(websocket1.messages) == 1
                assert len(websocket2.messages) == 1

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_broadcast_message(self):
        """Test broadcasting message to all connections."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            websocket1 = MockWebSocket()
            websocket2 = MockWebSocket()

            async def test_async():
                await manager.connect(websocket1, "conn_1")
                await manager.connect(websocket2, "conn_2")

                message = {"type": "system_announcement", "data": "maintenance"}
                count = await manager.broadcast(message)

                assert count == 2
                assert len(websocket1.messages) == 1
                assert len(websocket2.messages) == 1

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_broadcast_with_filter(self):
        """Test broadcasting with event filter."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            websocket1 = MockWebSocket()
            websocket2 = MockWebSocket()

            # Mock event filter
            filter1 = Mock()
            filter1.matches.return_value = True
            filter2 = Mock()
            filter2.matches.return_value = False

            async def test_async():
                await manager.connect(websocket1, "conn_1", event_filter=filter1)
                await manager.connect(websocket2, "conn_2", event_filter=filter2)

                event = MockEvent()
                message = {"type": "filtered_event", "data": "test"}
                count = await manager.broadcast(message, event=event)

                assert count == 1  # Only connection 1 should receive
                assert len(websocket1.messages) == 1
                assert len(websocket2.messages) == 0

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")

    def test_get_stats(self):
        """Test getting connection statistics."""
        try:
            from kailash.middleware.communication.realtime import ConnectionManager

            manager = ConnectionManager()
            websocket1 = MockWebSocket()
            websocket2 = MockWebSocket()

            async def test_async():
                await manager.connect(websocket1, "conn_1", session_id="session_1")
                await manager.connect(websocket2, "conn_2", user_id="user_1")

                stats = manager.get_stats()

                assert stats["total_connections"] == 2
                assert stats["session_connections"] == 1
                assert stats["user_connections"] == 1

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("ConnectionManager not available")


class TestSSEManager:
    """Test SSEManager functionality."""

    def test_sse_manager_init(self):
        """Test SSEManager initialization."""
        try:
            from kailash.middleware.communication.realtime import SSEManager

            manager = SSEManager()
            assert isinstance(manager.streams, dict)
            assert isinstance(manager.session_streams, dict)

        except ImportError:
            pytest.skip("SSEManager not available")

    def test_create_sse_stream(self):
        """Test creating SSE stream."""
        try:
            from kailash.middleware.communication.realtime import SSEManager

            manager = SSEManager()
            request = Mock()

            stream = manager.create_stream(
                request=request,
                stream_id="stream_123",
                session_id="session_1",
                user_id="user_1",
            )

            assert "stream_123" in manager.streams
            stream_info = manager.streams["stream_123"]
            assert stream_info["session_id"] == "session_1"
            assert stream_info["user_id"] == "user_1"
            assert "session_1" in manager.session_streams

        except ImportError:
            pytest.skip("SSEManager not available")

    def test_send_to_sse_stream(self):
        """Test sending message to SSE stream."""
        try:
            from kailash.middleware.communication.realtime import SSEManager

            manager = SSEManager()
            request = Mock()

            async def test_async():
                stream = manager.create_stream(request, "stream_123")

                message = {"type": "update", "data": "test"}
                result = await manager.send_to_stream("stream_123", message)

                assert result is True

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("SSEManager not available")

    def test_send_to_session_streams(self):
        """Test sending message to all streams in a session."""
        try:
            from kailash.middleware.communication.realtime import SSEManager

            manager = SSEManager()
            request1 = Mock()
            request2 = Mock()

            async def test_async():
                manager.create_stream(request1, "stream_1", session_id="session_1")
                manager.create_stream(request2, "stream_2", session_id="session_1")

                message = {"type": "session_update", "data": "broadcast"}
                count = await manager.send_to_session_streams("session_1", message)

                assert count == 2

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("SSEManager not available")

    def test_close_sse_stream(self):
        """Test closing SSE stream."""
        try:
            from kailash.middleware.communication.realtime import SSEManager

            manager = SSEManager()
            request = Mock()

            async def test_async():
                stream = manager.create_stream(
                    request, "stream_123", session_id="session_1"
                )

                await manager.close_stream("stream_123")

                assert "stream_123" not in manager.streams
                assert "stream_1" not in manager.session_streams

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("SSEManager not available")


class TestWebhookManager:
    """Test WebhookManager functionality."""

    def test_webhook_manager_init(self):
        """Test WebhookManager initialization."""
        try:
            from kailash.middleware.communication.realtime import WebhookManager

            manager = WebhookManager(max_retries=5, timeout_seconds=30)
            assert manager.max_retries == 5
            assert manager.timeout_seconds == 30
            assert isinstance(manager.webhooks, dict)

        except ImportError:
            pytest.skip("WebhookManager not available")

    def test_register_webhook(self):
        """Test webhook registration."""
        try:
            from kailash.middleware.communication.realtime import WebhookManager

            manager = WebhookManager()

            manager.register_webhook(
                webhook_id="hook_123",
                url="https://example.com/webhook",
                secret="secret_key",
                event_types=["workflow.completed", "node.failed"],
                headers={"Authorization": "Bearer token"},
            )

            assert "hook_123" in manager.webhooks
            webhook = manager.webhooks["hook_123"]
            assert webhook["url"] == "https://example.com/webhook"
            assert webhook["secret"] == "secret_key"
            assert webhook["event_types"] == ["workflow.completed", "node.failed"]
            assert webhook["headers"]["Authorization"] == "Bearer token"

        except ImportError:
            pytest.skip("WebhookManager not available")

    def test_unregister_webhook(self):
        """Test webhook unregistration."""
        try:
            from kailash.middleware.communication.realtime import WebhookManager

            manager = WebhookManager()

            manager.register_webhook("hook_123", "https://example.com/webhook")
            assert "hook_123" in manager.webhooks

            manager.unregister_webhook("hook_123")
            assert "hook_123" not in manager.webhooks

        except ImportError:
            pytest.skip("WebhookManager not available")

    def test_deliver_event_to_webhook(self):
        """Test delivering event to webhook."""
        try:
            from kailash.middleware.communication.realtime import WebhookManager

            manager = WebhookManager()

            # Register webhook
            manager.register_webhook(
                webhook_id="hook_123",
                url="https://example.com/webhook",
                event_types=["test.event"],
            )

            # Mock HTTP request
            with patch.object(manager, "_deliver_to_webhook") as mock_deliver:
                mock_deliver.return_value = True

                async def test_async():
                    event = MockEvent(event_type="test.event")
                    await manager.deliver_event(event)

                    mock_deliver.assert_called_once()

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("WebhookManager not available")

    def test_deliver_event_filtered_out(self):
        """Test delivering event that doesn't match webhook filters."""
        try:
            from kailash.middleware.communication.realtime import WebhookManager

            manager = WebhookManager()

            # Register webhook for specific event types
            manager.register_webhook(
                webhook_id="hook_123",
                url="https://example.com/webhook",
                event_types=["workflow.completed"],
            )

            with patch.object(manager, "_deliver_to_webhook") as mock_deliver:

                async def test_async():
                    # Event type doesn't match webhook filter
                    event = MockEvent(event_type="node.started")
                    await manager.deliver_event(event)

                    # Should not be delivered
                    mock_deliver.assert_not_called()

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("WebhookManager not available")


class TestRealtimeMiddleware:
    """Test RealtimeMiddleware functionality."""

    def test_realtime_middleware_init(self):
        """Test RealtimeMiddleware initialization."""
        try:
            from kailash.middleware.communication.realtime import RealtimeMiddleware

            # Mock AgentUIMiddleware
            mock_agent_ui = Mock()
            mock_agent_ui.event_stream = Mock()

            middleware = RealtimeMiddleware(
                agent_ui=mock_agent_ui,
                enable_websocket=True,
                enable_sse=True,
                enable_webhooks=True,
            )

            assert middleware.agent_ui == mock_agent_ui
            assert middleware.enable_websocket is True
            assert middleware.enable_sse is True
            assert middleware.enable_webhooks is True

        except ImportError:
            pytest.skip("RealtimeMiddleware not available")

    def test_realtime_middleware_init_minimal(self):
        """Test RealtimeMiddleware initialization with minimal config."""
        try:
            from kailash.middleware.communication.realtime import RealtimeMiddleware

            mock_agent_ui = Mock()
            mock_agent_ui.event_stream = Mock()

            middleware = RealtimeMiddleware(mock_agent_ui)

            # Should have default values
            assert middleware.enable_websocket is True
            assert middleware.enable_sse is True
            assert middleware.enable_webhooks is True

        except ImportError:
            pytest.skip("RealtimeMiddleware not available")

    def test_handle_websocket_connection(self):
        """Test WebSocket connection handling."""
        try:
            from kailash.middleware.communication.realtime import RealtimeMiddleware

            mock_agent_ui = Mock()
            mock_agent_ui.event_stream = Mock()
            middleware = RealtimeMiddleware(mock_agent_ui)

            websocket = MockWebSocket()

            # Mock WebSocket disconnect exception
            class MockWebSocketDisconnect(Exception):
                pass

            async def test_async():
                with patch(
                    "kailash.middleware.communication.realtime.WebSocketDisconnect",
                    MockWebSocketDisconnect,
                ):
                    # Mock receive to simulate disconnect
                    websocket.receive_text = Mock(side_effect=MockWebSocketDisconnect())

                    # Should handle connection gracefully
                    await middleware.handle_websocket(
                        websocket=websocket, session_id="session_1", user_id="user_1"
                    )

                    assert websocket.accepted is True

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("RealtimeMiddleware not available")

    def test_create_sse_stream(self):
        """Test SSE stream creation."""
        try:
            from kailash.middleware.communication.realtime import RealtimeMiddleware

            mock_agent_ui = Mock()
            mock_agent_ui.event_stream = Mock()
            middleware = RealtimeMiddleware(mock_agent_ui)

            request = Mock()
            request.client.host = "127.0.0.1"

            response = middleware.create_sse_stream(
                request=request,
                session_id="session_1",
                user_id="user_1",
                event_types=["workflow.completed"],
            )

            # Should return StreamingResponse
            from fastapi.responses import StreamingResponse

            assert isinstance(response, StreamingResponse)

        except ImportError:
            pytest.skip("RealtimeMiddleware not available")

    def test_register_webhook(self):
        """Test webhook registration."""
        try:
            from kailash.middleware.communication.realtime import RealtimeMiddleware

            mock_agent_ui = Mock()
            mock_agent_ui.event_stream = Mock()
            middleware = RealtimeMiddleware(mock_agent_ui)

            middleware.register_webhook(
                webhook_id="hook_123",
                url="https://example.com/webhook",
                secret="secret",
                event_types=["workflow.completed"],
                headers={"Authorization": "Bearer token"},
            )

            # Should be registered in webhook manager
            assert "hook_123" in middleware.webhook_manager.webhooks

        except ImportError:
            pytest.skip("RealtimeMiddleware not available")

    def test_unregister_webhook(self):
        """Test webhook unregistration."""
        try:
            from kailash.middleware.communication.realtime import RealtimeMiddleware

            mock_agent_ui = Mock()
            mock_agent_ui.event_stream = Mock()
            middleware = RealtimeMiddleware(mock_agent_ui)

            # First register
            middleware.register_webhook("hook_123", "https://example.com/webhook")
            assert "hook_123" in middleware.webhook_manager.webhooks

            # Then unregister
            middleware.unregister_webhook("hook_123")
            assert "hook_123" not in middleware.webhook_manager.webhooks

        except ImportError:
            pytest.skip("RealtimeMiddleware not available")

    def test_get_stats(self):
        """Test getting middleware statistics."""
        try:
            from kailash.middleware.communication.realtime import RealtimeMiddleware

            mock_agent_ui = Mock()
            mock_agent_ui.event_stream = Mock()
            middleware = RealtimeMiddleware(mock_agent_ui)

            stats = middleware.get_stats()

            assert "events_processed" in stats
            assert "websocket_stats" in stats
            assert "sse_stats" in stats
            assert "webhook_stats" in stats

        except ImportError:
            pytest.skip("RealtimeMiddleware not available")

    def test_initialize_middleware(self):
        """Test middleware initialization."""
        try:
            from kailash.middleware.communication.realtime import RealtimeMiddleware

            mock_agent_ui = Mock()
            mock_agent_ui.event_stream = Mock()
            middleware = RealtimeMiddleware(mock_agent_ui)

            async def test_async():
                await middleware.initialize()
                # Should complete without errors

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("RealtimeMiddleware not available")

    def test_process_event(self):
        """Test event processing."""
        try:
            from kailash.middleware.communication.realtime import RealtimeMiddleware

            mock_agent_ui = Mock()
            mock_agent_ui.event_stream = Mock()
            middleware = RealtimeMiddleware(mock_agent_ui)

            # Mock connection and webhook managers
            middleware.connection_manager.broadcast = AsyncMock()
            middleware.sse_manager.send_to_session_streams = AsyncMock()
            middleware.webhook_manager.deliver_event = AsyncMock()

            async def test_async():
                event = MockEvent(event_type="test.event", session_id="session_1")
                await middleware._process_event(event)

                # Should process event through all channels
                middleware.connection_manager.broadcast.assert_called_once()
                middleware.webhook_manager.deliver_event.assert_called_once()

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("RealtimeMiddleware not available")
