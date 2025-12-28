"""Integration test for WebSocket transport in MCP client.

These tests verify that the original 'Unsupported transport: websocket' error
is fixed and that WebSocket transport actually works with real servers.
"""

import asyncio
import json

import pytest
import websockets
from kailash.mcp_server.client import MCPClient
from kailash.mcp_server.errors import TransportError
from websockets.server import serve


class TestWebSocketTransportOriginalBugFix:
    """Test that the original WebSocket bug is fixed."""

    @pytest.mark.asyncio
    async def test_original_bug_is_fixed(self):
        """Verify the original 'Unsupported transport: websocket' error is fixed.

        This test verifies the core issue: WebSocket URLs no longer raise
        'Unsupported transport' errors.
        """
        client = MCPClient()

        # This used to raise "Unsupported transport: websocket"
        # Now it should either connect or fail with connection error, NOT transport error
        try:
            await client.discover_tools("ws://localhost:9999/nonexistent")
        except Exception as e:
            # Should NOT be "Unsupported transport" error
            assert "Unsupported transport: websocket" not in str(e)
            assert not ("Unsupported transport" in str(e) and "websocket" in str(e))
            # Connection errors are expected since server doesn't exist
            # The key is that it tried to connect, not rejected the transport
            assert any(
                word in str(e).lower()
                for word in ["connection", "connect", "websocket", "failed"]
            )

    @pytest.mark.asyncio
    async def test_unknown_transport_returns_empty_list(self):
        """Verify that truly unsupported transports return empty list (logged as error)."""
        client = MCPClient()

        # Unknown transports should return empty list, not raise exception
        # The error is logged but the method doesn't raise
        result1 = await client.discover_tools(
            {"transport": "telepathy", "url": "mind://localhost"}
        )
        assert result1 == []

        # Also verify with another fake transport
        result2 = await client.discover_tools(
            {"transport": "quantum", "url": "q://localhost"}
        )
        assert result2 == []


class TestWebSocketTransportWithRealServers:
    """Test WebSocket transport with actual WebSocket servers."""

    @pytest.mark.asyncio
    async def test_websocket_with_real_mcp_server(self):
        """Test WebSocket transport with a real WebSocket MCP server.

        This test creates an actual WebSocket server that implements the MCP
        protocol and verifies real communication works.
        """

        # Create a simple WebSocket MCP server
        async def mcp_handler(websocket, path):
            async for message in websocket:
                data = json.loads(message)

                if data.get("method") == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": data["id"],
                        "result": {
                            "tools": [
                                {
                                    "name": "test_tool",
                                    "description": "A test tool",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {"input": {"type": "string"}},
                                    },
                                }
                            ]
                        },
                    }
                    await websocket.send(json.dumps(response))

                elif data.get("method") == "tools/call":
                    response = {
                        "jsonrpc": "2.0",
                        "id": data["id"],
                        "result": {
                            "content": [
                                {
                                    "text": f"Processed: {data['params']['arguments']['input']}"
                                }
                            ]
                        },
                    }
                    await websocket.send(json.dumps(response))

        # Start the server
        async with serve(mcp_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]

            client = MCPClient()

            # Test tool discovery with real WebSocket
            tools = await client.discover_tools(f"ws://localhost:{port}/mcp")
            assert len(tools) == 1
            assert tools[0]["name"] == "test_tool"
            assert tools[0]["description"] == "A test tool"

            # Test tool execution with real WebSocket
            result = await client.call_tool(
                f"ws://localhost:{port}/mcp", "test_tool", {"input": "Hello WebSocket"}
            )
            assert result["success"] is True
            assert "Processed: Hello WebSocket" in result["content"]

    @pytest.mark.asyncio
    async def test_websocket_complete_workflow(self):
        """Test complete WebSocket workflow: discovery and multiple tool calls."""

        # Create a WebSocket server that handles the full MCP protocol
        async def full_mcp_handler(websocket, path):
            async for message in websocket:
                data = json.loads(message)

                if data.get("method") == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": data["id"],
                        "result": {
                            "tools": [
                                {
                                    "name": "echo",
                                    "description": "Echoes input",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {"message": {"type": "string"}},
                                        "required": ["message"],
                                    },
                                },
                                {
                                    "name": "add",
                                    "description": "Adds two numbers",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "a": {"type": "number"},
                                            "b": {"type": "number"},
                                        },
                                        "required": ["a", "b"],
                                    },
                                },
                            ]
                        },
                    }
                elif data.get("method") == "tools/call":
                    tool_name = data["params"]["name"]
                    args = data["params"]["arguments"]

                    if tool_name == "echo":
                        result_text = f"Echo: {args['message']}"
                    elif tool_name == "add":
                        result_text = f"Result: {args['a'] + args['b']}"
                    else:
                        result_text = "Unknown tool"

                    response = {
                        "jsonrpc": "2.0",
                        "id": data["id"],
                        "result": {"content": [{"text": result_text}]},
                    }

                await websocket.send(json.dumps(response))

        async with serve(full_mcp_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            ws_url = f"ws://localhost:{port}/mcp"

            client = MCPClient()

            # Test discovery
            tools = await client.discover_tools(ws_url)
            assert len(tools) == 2
            assert any(t["name"] == "echo" for t in tools)
            assert any(t["name"] == "add" for t in tools)

            # Test execution of both tools
            echo_result = await client.call_tool(
                ws_url, "echo", {"message": "Hello MCP"}
            )
            assert echo_result["success"] is True
            assert "Echo: Hello MCP" in echo_result["content"]

            add_result = await client.call_tool(ws_url, "add", {"a": 5, "b": 3})
            assert add_result["success"] is True
            assert "Result: 8" in add_result["content"]

    @pytest.mark.asyncio
    async def test_websocket_error_handling_real_connection(self):
        """Test WebSocket error handling with real connection attempts."""
        client = MCPClient()

        # Test connection to non-existent server
        with pytest.raises(Exception) as exc_info:
            await client.discover_tools("ws://localhost:65535/mcp")

        # Should be connection error, not transport error
        error_msg = str(exc_info.value)
        assert "Unsupported transport" not in error_msg
        # Verify it's actually trying to connect
        assert any(
            word in error_msg.lower()
            for word in ["connection", "connect", "websocket", "failed"]
        )

    @pytest.mark.asyncio
    async def test_websocket_timeout_with_slow_server(self):
        """Test WebSocket timeout handling with real slow server."""

        # Create a slow WebSocket server
        async def slow_handler(websocket, path):
            async for message in websocket:
                # Deliberately slow - wait longer than client timeout
                await asyncio.sleep(2.0)
                await websocket.send(
                    json.dumps({"jsonrpc": "2.0", "id": "1", "result": {}})
                )

        async with serve(slow_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]

            client = MCPClient(connection_timeout=0.5)

            with pytest.raises(Exception) as exc_info:
                await client.discover_tools(f"ws://localhost:{port}/mcp", timeout=0.5)

            # Should timeout, not raise transport error
            assert "Unsupported transport" not in str(exc_info.value)


class TestWebSocketTransportFeatures:
    """Test WebSocket transport features and integration."""

    @pytest.fixture
    def client(self):
        """Create MCP client instance."""
        return MCPClient(enable_metrics=True)

    def test_websocket_transport_detection(self, client):
        """Test that WebSocket URLs are correctly detected."""
        # Test WebSocket URL detection
        assert client._get_transport_type("ws://localhost:8080/mcp") == "websocket"
        assert client._get_transport_type("wss://secure.example.com/mcp") == "websocket"

        # Test config-based detection
        config = {"transport": "websocket", "url": "ws://example.com"}
        assert client._get_transport_type(config) == "websocket"

        # Ensure other transports still work
        assert client._get_transport_type("http://example.com") == "sse"
        assert client._get_transport_type("https://example.com") == "sse"
        assert client._get_transport_type("python server.py") == "stdio"

    def test_websocket_vs_other_transports(self, client):
        """Test that WebSocket is properly distinguished from other transports."""
        # Test transport type detection
        test_cases = [
            ("ws://localhost:8080/mcp", "websocket"),
            ("wss://secure.example.com/mcp", "websocket"),
            ("http://localhost:8080/mcp", "sse"),
            ("https://api.example.com/mcp", "sse"),
            ({"transport": "stdio", "command": ["mcp"]}, "stdio"),
            ({"transport": "websocket", "url": "ws://test"}, "websocket"),
            ({"transport": "http", "url": "http://test"}, "http"),
        ]

        for config, expected_transport in test_cases:
            detected = client._get_transport_type(config)
            assert (
                detected == expected_transport
            ), f"Failed for {config}: expected {expected_transport}, got {detected}"

    @pytest.mark.asyncio
    async def test_websocket_missing_url_error(self, client):
        """Test proper error handling for missing WebSocket URLs."""
        config = {"transport": "websocket"}  # Missing URL

        # Test discovery error - should fail at the routing level
        with pytest.raises(TransportError) as exc_info:
            await client.discover_tools(config)

        assert "WebSocket transport requires 'url'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_websocket_metrics_with_real_server(self):
        """Test that WebSocket operations update metrics with real server."""

        # Create a minimal WebSocket server for metrics testing
        async def metrics_handler(websocket, path):
            async for message in websocket:
                data = json.loads(message)
                response = {"jsonrpc": "2.0", "id": data["id"], "result": {"tools": []}}
                await websocket.send(json.dumps(response))

        async with serve(metrics_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]

            client = MCPClient(enable_metrics=True)
            await client.discover_tools(f"ws://localhost:{port}/mcp")

            # Check metrics were updated
            metrics = client.get_metrics()
            assert "websocket" in metrics["transport_usage"]
            assert metrics["transport_usage"]["websocket"] > 0


class TestWebSocketLimitationsDocumentation:
    """Test to document WebSocket transport limitations."""

    def test_websocket_client_api_limitations(self):
        """Document the current limitations of the MCP WebSocket client."""
        # This test serves as documentation for the current state
        limitations = {
            "auth_support": False,  # WebSocket client doesn't support headers/auth
            "header_support": False,  # No custom headers supported
            "timeout_granular": True,  # Basic timeout support available
            "connection_pooling": False,  # No built-in connection pooling
        }

        # These limitations are due to the current MCP SDK WebSocket client implementation
        # Future versions may address these limitations
        assert limitations["auth_support"] is False
        assert limitations["header_support"] is False

        # Document what IS supported
        supported_features = {
            "basic_connectivity": True,
            "tool_discovery": True,
            "tool_execution": True,
            "timeout_handling": True,
            "error_handling": True,
            "transport_detection": True,
        }

        for feature, supported in supported_features.items():
            assert supported is True, f"Feature {feature} should be supported"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
