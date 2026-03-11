"""Integration tests for MCP server with WebSocketServerTransport."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.workflow.builder import WorkflowBuilder
from nexus.mcp import MCPServer, SimpleMCPClient


@pytest.mark.asyncio
class TestMCPTransportIntegration:
    """Test MCP server and client with transport layer."""

    @patch("nexus.mcp.transport.websockets.serve")
    @patch("nexus.mcp.transport.websockets.connect")
    async def test_mcp_server_with_transport(self, mock_connect, mock_serve):
        """Test MCP server using WebSocketServerTransport."""
        # Mock server
        mock_server = MagicMock()
        mock_server.close = MagicMock()
        mock_server.wait_closed = AsyncMock()

        async def mock_serve_func(*args, **kwargs):
            return mock_server

        mock_serve.side_effect = mock_serve_func

        # Mock client websocket
        mock_websocket = MagicMock()
        mock_websocket.send = AsyncMock()
        mock_websocket.recv = AsyncMock()
        mock_websocket.close = AsyncMock()
        mock_websocket.closed = False

        async def mock_connect_func(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_func

        # Create MCP server with transport
        server = MCPServer(port=3004, use_transport=True)

        # Register a workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "calc",
            {
                "code": "result = {'answer': parameters.get('x', 0) + parameters.get('y', 0)}"
            },
        )
        server.register_workflow("add_numbers", workflow.build())

        # Start server
        await server.start()
        assert server._transport is not None
        assert server._transport._running

        # Create client with transport
        client = SimpleMCPClient(port=3004, use_transport=True)
        await client.connect()
        assert client._transport is not None

        # Test list tools
        mock_websocket.recv.return_value = (
            '{"type": "tools", "tools": [{"name": "add_numbers"}]}'
        )
        tools = await client.list_tools()

        # Verify request was sent
        mock_websocket.send.assert_called()
        sent_data = mock_websocket.send.call_args[0][0]
        assert '{"type": "list_tools"}' in sent_data

        # Test call tool
        mock_websocket.recv.return_value = '{"type": "result", "result": {"answer": 7}}'
        result = await client.call_tool("add_numbers", {"x": 3, "y": 4})

        # Verify tool call request was sent
        calls = mock_websocket.send.call_args_list
        assert len(calls) >= 2
        last_call = calls[-1][0][0]
        assert '"type": "call_tool"' in last_call
        assert '"name": "add_numbers"' in last_call

        # Clean up
        await client.disconnect()
        await server.stop()

    @patch("nexus.mcp.server.websockets.serve")
    async def test_mcp_server_backward_compatibility(self, mock_serve):
        """Test MCP server works without transport (backward compatibility)."""
        # Mock server
        mock_server = MagicMock()
        mock_server.close = MagicMock()
        mock_server.wait_closed = AsyncMock()

        async def mock_serve_func(*args, **kwargs):
            return mock_server

        mock_serve.side_effect = mock_serve_func

        # Create MCP server without transport
        server = MCPServer(port=3005, use_transport=False)

        # Start server
        await server.start()
        assert server._transport is None
        assert server._server is not None

        # Verify websockets.serve was called directly
        mock_serve.assert_called_once()

        # Stop server
        await server.stop()
        mock_server.close.assert_called_once()

    async def test_transport_message_handler_integration(self):
        """Test transport message handler integration with MCP server."""
        from nexus.mcp.transport import WebSocketServerTransport

        # Create transport with custom handler
        received_messages = []

        async def message_handler(message):
            received_messages.append(message)
            return {"type": "echo", "original": message}

        transport = WebSocketServerTransport(port=3006, message_handler=message_handler)

        # Mock the websockets.serve
        with patch("nexus.mcp.transport.websockets.serve") as mock_serve:
            mock_server = MagicMock()
            mock_server.close = MagicMock()
            mock_server.wait_closed = AsyncMock()

            async def mock_serve_func(*args, **kwargs):
                return mock_server

            mock_serve.side_effect = mock_serve_func

            await transport.start()

            # Simulate a message from client
            test_message = {"type": "test", "data": "hello"}
            response = await message_handler(test_message)

            assert response["type"] == "echo"
            assert response["original"] == test_message
            assert len(received_messages) == 1

            await transport.stop()

    async def test_mcp_server_transport_features(self):
        """Test MCP server using advanced transport features."""
        from nexus.mcp.transport import WebSocketServerTransport

        # Create a custom transport with message tracking
        class TrackingTransport(WebSocketServerTransport):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.sent_messages = []

            async def send_message(self, message, client=None):
                self.sent_messages.append((message, client))
                await super().send_message(message, client)

        # Mock websockets
        with patch("nexus.mcp.transport.websockets.serve") as mock_serve:
            mock_server = MagicMock()
            mock_server.close = MagicMock()
            mock_server.wait_closed = AsyncMock()

            async def mock_serve_func(*args, **kwargs):
                return mock_server

            mock_serve.side_effect = mock_serve_func

            # Create transport
            transport = TrackingTransport(port=3007)

            # Create MCP server with custom transport
            server = MCPServer(port=3007, use_transport=True)
            server._transport = transport  # Replace with our tracking transport

            # Start transport
            await transport.start()

            # Test broadcasting
            await transport.broadcast_notification(
                {"event": "test_event", "data": "test_data"}
            )

            # Verify notification was tracked
            assert len(transport.sent_messages) == 1
            msg, client = transport.sent_messages[0]
            assert msg["type"] == "notification"
            assert msg["event"] == "test_event"
            assert client is None  # Broadcast to all

            # Clean up
            await transport.stop()
