"""Tests for WebSocket transport implementations."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nexus.mcp.transport import WebSocketClientTransport, WebSocketServerTransport


@pytest.mark.asyncio
class TestWebSocketServerTransport:
    """Test WebSocketServerTransport functionality."""

    async def test_init(self):
        """Test transport initialization."""
        transport = WebSocketServerTransport(
            host="127.0.0.1", port=3002, max_message_size=1024 * 1024
        )

        assert transport.host == "127.0.0.1"
        assert transport.port == 3002
        assert transport.max_message_size == 1024 * 1024
        assert not transport._running
        assert len(transport._clients) == 0

    @patch("nexus.mcp.transport.websockets.serve")
    async def test_start(self, mock_serve):
        """Test starting the server."""

        # Create a proper mock that can be awaited
        async def mock_serve_func(*args, **kwargs):
            mock_server = MagicMock()
            mock_server.close = MagicMock()
            mock_server.wait_closed = AsyncMock()
            return mock_server

        mock_serve.side_effect = mock_serve_func

        transport = WebSocketServerTransport()
        await transport.start()

        assert transport._running
        mock_serve.assert_called_once_with(
            transport._handle_client,
            transport.host,
            transport.port,
            max_size=transport.max_message_size,
            ping_interval=20,
            ping_timeout=10,
        )

    @patch("nexus.mcp.transport.websockets.serve")
    async def test_start_already_running(self, mock_serve):
        """Test starting when already running."""
        transport = WebSocketServerTransport()
        transport._running = True

        await transport.start()

        # Should not call serve again
        mock_serve.assert_not_called()

    async def test_stop_not_running(self):
        """Test stopping when not running."""
        transport = WebSocketServerTransport()

        # Should not raise error
        await transport.stop()

    @patch("nexus.mcp.transport.websockets.serve")
    async def test_stop_with_clients(self, mock_serve):
        """Test stopping with connected clients."""
        # Create a proper mock that can be awaited
        mock_server = MagicMock()
        mock_server.close = MagicMock()
        mock_server.wait_closed = AsyncMock()

        async def mock_serve_func(*args, **kwargs):
            return mock_server

        mock_serve.side_effect = mock_serve_func

        # Mock clients
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()

        transport = WebSocketServerTransport()
        await transport.start()

        # Add mock clients
        transport._clients.add(mock_client1)
        transport._clients.add(mock_client2)

        await transport.stop()

        # Verify clients were closed
        mock_client1.close.assert_called_once()
        mock_client2.close.assert_called_once()

        # Verify server was closed
        mock_server.close.assert_called_once()
        mock_server.wait_closed.assert_called_once()

        assert not transport._running
        assert len(transport._clients) == 0

    async def test_send_message_to_client(self):
        """Test sending message to specific client."""
        transport = WebSocketServerTransport()

        mock_client = AsyncMock()
        message = {"type": "test", "data": "hello"}

        await transport.send_message(message, mock_client)

        mock_client.send.assert_called_once_with(json.dumps(message))

    async def test_send_message_broadcast(self):
        """Test broadcasting message to all clients."""
        transport = WebSocketServerTransport()

        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
        transport._clients = {mock_client1, mock_client2}

        message = {"type": "broadcast", "data": "hello all"}

        await transport.send_message(message)

        expected_json = json.dumps(message)
        mock_client1.send.assert_called_once_with(expected_json)
        mock_client2.send.assert_called_once_with(expected_json)

    async def test_broadcast_notification(self):
        """Test broadcasting notification."""
        transport = WebSocketServerTransport()

        mock_client = AsyncMock()
        transport._clients = {mock_client}

        notification = {"data": "test notification"}

        await transport.broadcast_notification(notification)

        # Check that the message was sent and contains correct fields
        mock_client.send.assert_called_once()
        sent_data = json.loads(mock_client.send.call_args[0][0])
        assert sent_data["type"] == "notification"
        assert sent_data["data"] == "test notification"

    async def test_get_connected_clients(self):
        """Test getting connected client count."""
        transport = WebSocketServerTransport()

        assert transport.get_connected_clients() == 0

        # Add mock clients
        transport._clients = {AsyncMock(), AsyncMock(), AsyncMock()}

        assert transport.get_connected_clients() == 3

    async def test_wait_for_clients_success(self):
        """Test waiting for clients successfully."""
        transport = WebSocketServerTransport()

        # Start with no clients
        assert transport.get_connected_clients() == 0

        # Simulate client connection after delay
        async def connect_client():
            await asyncio.sleep(0.1)
            transport._clients.add(AsyncMock())

        asyncio.create_task(connect_client())

        # Wait for 1 client with timeout
        result = await transport.wait_for_clients(min_clients=1, timeout=1.0)

        assert result is True
        assert transport.get_connected_clients() == 1

    async def test_wait_for_clients_timeout(self):
        """Test waiting for clients timeout."""
        transport = WebSocketServerTransport()

        # Wait for clients that never connect
        result = await transport.wait_for_clients(min_clients=2, timeout=0.1)

        assert result is False

    async def test_receive_message_returns_queued_message(self):
        """Test that receive_message returns messages from the internal queue."""
        transport = WebSocketServerTransport()

        # Put a message in the queue and verify it's returned
        test_msg = {"jsonrpc": "2.0", "method": "test", "id": 1}
        await transport._message_queue.put(test_msg)
        result = await transport.receive_message()
        assert result == test_msg


@pytest.mark.asyncio
class TestWebSocketClientTransport:
    """Test WebSocketClientTransport functionality."""

    async def test_init(self):
        """Test client transport initialization."""
        transport = WebSocketClientTransport(
            uri="ws://localhost:3001", max_message_size=2 * 1024 * 1024
        )

        assert transport.uri == "ws://localhost:3001"
        assert transport.max_message_size == 2 * 1024 * 1024
        assert not transport._running
        assert transport._websocket is None

    @patch("nexus.mcp.transport.websockets.connect")
    async def test_start(self, mock_connect):
        """Test connecting to server."""
        mock_websocket = MagicMock()
        mock_websocket.close = AsyncMock()

        async def mock_connect_func(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_func

        transport = WebSocketClientTransport("ws://localhost:3001")
        await transport.start()

        assert transport._running
        assert transport._websocket == mock_websocket

        mock_connect.assert_called_once_with(
            transport.uri,
            max_size=transport.max_message_size,
            ping_interval=20,
            ping_timeout=10,
        )

    @patch("nexus.mcp.transport.websockets.connect")
    async def test_start_already_connected(self, mock_connect):
        """Test starting when already connected."""
        transport = WebSocketClientTransport("ws://localhost:3001")
        transport._running = True

        await transport.start()

        # Should not connect again
        mock_connect.assert_not_called()

    async def test_stop_not_connected(self):
        """Test stopping when not connected."""
        transport = WebSocketClientTransport("ws://localhost:3001")

        # Should not raise error
        await transport.stop()

    @patch("nexus.mcp.transport.websockets.connect")
    async def test_stop_connected(self, mock_connect):
        """Test stopping when connected."""
        mock_websocket = MagicMock()
        mock_websocket.close = AsyncMock()

        async def mock_connect_func(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_func

        transport = WebSocketClientTransport("ws://localhost:3001")
        await transport.start()

        # Create a mock receive task
        transport._receive_task = asyncio.create_task(asyncio.sleep(10))

        await transport.stop()

        # Verify websocket was closed
        mock_websocket.close.assert_called_once()

        assert not transport._running
        assert transport._websocket is None

    @patch("nexus.mcp.transport.websockets.connect")
    async def test_send_message(self, mock_connect):
        """Test sending message to server."""
        mock_websocket = MagicMock()
        mock_websocket.send = AsyncMock()

        async def mock_connect_func(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_func

        transport = WebSocketClientTransport("ws://localhost:3001")
        await transport.start()

        message = {"type": "request", "data": "test"}
        await transport.send_message(message)

        mock_websocket.send.assert_called_once_with(json.dumps(message))

    async def test_send_message_not_connected(self):
        """Test sending message when not connected."""
        transport = WebSocketClientTransport("ws://localhost:3001")

        with pytest.raises(RuntimeError, match="Not connected"):
            await transport.send_message({"type": "test"})

    @patch("nexus.mcp.transport.websockets.connect")
    async def test_receive_message(self, mock_connect):
        """Test receiving message from server."""
        mock_websocket = MagicMock()
        mock_websocket.recv = AsyncMock()

        async def mock_connect_func(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_func

        # Mock received message
        mock_websocket.recv.return_value = '{"type": "response", "data": "test"}'

        transport = WebSocketClientTransport("ws://localhost:3001")
        await transport.start()

        message = await transport.receive_message()

        assert message == {"type": "response", "data": "test"}
        mock_websocket.recv.assert_called_once()

    async def test_receive_message_not_connected(self):
        """Test receiving message when not connected."""
        transport = WebSocketClientTransport("ws://localhost:3001")

        with pytest.raises(RuntimeError, match="Not connected"):
            await transport.receive_message()

    @patch("nexus.mcp.transport.websockets.connect")
    async def test_is_connected(self, mock_connect):
        """Test connection status check."""
        mock_websocket = MagicMock()
        mock_websocket.closed = False
        mock_websocket.close = AsyncMock()

        async def mock_connect_func(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_func

        transport = WebSocketClientTransport("ws://localhost:3001")

        # Not connected yet
        assert not transport.is_connected()

        # Connect
        await transport.start()
        assert transport.is_connected()

        # Simulate closed connection
        mock_websocket.closed = True
        assert not transport.is_connected()

        # Stop
        await transport.stop()
        assert not transport.is_connected()


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for server and client transports."""

    async def test_server_client_communication(self):
        """Test actual communication between server and client."""
        received_messages = []

        async def server_handler(message):
            """Handle server messages."""
            received_messages.append(message)
            return {"type": "response", "echo": message.get("data")}

        # Create and start server
        server = WebSocketServerTransport(
            host="127.0.0.1",
            port=0,  # Use random available port
            message_handler=server_handler,
        )

        with patch("nexus.mcp.transport.websockets.serve") as mock_serve:
            # Mock the server
            mock_server = MagicMock()
            mock_server.close = MagicMock()
            mock_server.wait_closed = AsyncMock()

            async def mock_serve_func(*args, **kwargs):
                return mock_server

            mock_serve.side_effect = mock_serve_func

            await server.start()

            # Get the actual port used
            actual_port = mock_serve.call_args[0][2]

            # Create and connect client
            client = WebSocketClientTransport(f"ws://127.0.0.1:{actual_port}")

            with patch("nexus.mcp.transport.websockets.connect") as mock_connect:
                # Mock the client connection
                mock_websocket = MagicMock()
                mock_websocket.send = AsyncMock()
                mock_websocket.close = AsyncMock()

                async def mock_connect_func(*args, **kwargs):
                    return mock_websocket

                mock_connect.side_effect = mock_connect_func

                await client.start()

                # Send test message
                test_message = {"type": "test", "data": "hello"}
                await client.send_message(test_message)

                # Verify message was sent
                mock_websocket.send.assert_called_once_with(json.dumps(test_message))

                # Clean up
                await client.stop()
                await server.stop()
