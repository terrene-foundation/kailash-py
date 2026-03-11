"""Unit tests for MCP server implementation."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.workflow.builder import WorkflowBuilder
from nexus.mcp import MCPServer, SimpleMCPClient


class TestMCPServer:
    """Test MCP server functionality."""

    def test_mcp_server_initialization(self):
        """Test MCP server initialization."""
        server = MCPServer(host="0.0.0.0", port=3001)

        assert server.host == "0.0.0.0"
        assert server.port == 3001
        assert server._workflows == {}
        assert server._clients == set()
        assert server._server is None

    def test_register_workflow(self):
        """Test workflow registration."""
        server = MCPServer()
        workflow = MagicMock()

        server.register_workflow("test-workflow", workflow)

        assert "test-workflow" in server._workflows
        assert server._workflows["test-workflow"] == workflow

    @pytest.mark.asyncio
    async def test_handle_list_tools(self):
        """Test list tools request handling."""
        server = MCPServer()

        # Register some workflows
        workflow1 = MagicMock()
        workflow2 = MagicMock()
        server.register_workflow("workflow-1", workflow1)
        server.register_workflow("workflow-2", workflow2)

        # Handle list tools request
        response = await server.handle_list_tools()

        assert response["type"] == "tools"
        assert len(response["tools"]) == 2

        tool_names = [tool["name"] for tool in response["tools"]]
        assert "workflow-1" in tool_names
        assert "workflow-2" in tool_names

        # Check tool structure
        tool = response["tools"][0]
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool

    @pytest.mark.asyncio
    async def test_handle_call_tool_success(self):
        """Test successful tool call."""
        server = MCPServer()

        # Create a simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "compute", {"code": "result = {'sum': 10, 'product': 24}"}
        )
        server.register_workflow("calculator", workflow.build())

        # Call the tool
        request = {"type": "call_tool", "name": "calculator", "arguments": {}}

        response = await server.handle_request(request)

        assert response["type"] == "result"
        assert "result" in response
        assert response["result"]["sum"] == 10
        assert response["result"]["product"] == 24

    @pytest.mark.asyncio
    async def test_handle_call_tool_unknown(self):
        """Test calling unknown tool."""
        server = MCPServer()

        request = {"type": "call_tool", "name": "unknown-tool", "arguments": {}}

        response = await server.handle_request(request)

        assert response["type"] == "error"
        assert "Unknown tool" in response["error"]

    @pytest.mark.asyncio
    async def test_handle_unknown_request_type(self):
        """Test handling unknown request type."""
        server = MCPServer()

        request = {"type": "unknown_type"}

        response = await server.handle_request(request)

        assert response["type"] == "error"
        assert "Unknown request type" in response["error"]

    @pytest.mark.asyncio
    async def test_handle_list_resources(self):
        """Test list resources request."""
        server = MCPServer()

        # Register workflows
        server.register_workflow("data-source", MagicMock())
        server.register_workflow("processor", MagicMock())

        response = await server.handle_list_resources()

        assert response["type"] == "resources"
        assert len(response["resources"]) == 2

        # Check resource format
        resource = response["resources"][0]
        assert "uri" in resource
        assert "name" in resource
        assert "mimeType" in resource
        assert resource["mimeType"] == "application/x-workflow"

    @pytest.mark.asyncio
    async def test_client_connection_handling(self):
        """Test client connection handling."""
        server = MCPServer()

        # Mock websocket
        websocket = AsyncMock()
        websocket.__aiter__.return_value = []  # No messages

        # Handle client connection
        await server.handle_client(websocket)

        # Client should be removed after disconnect
        assert len(server._clients) == 0

    @pytest.mark.asyncio
    async def test_server_start_stop(self):
        """Test server start and stop."""
        server = MCPServer(port=3999)  # Use non-standard port

        # Mock websockets.serve
        mock_server = MagicMock()
        mock_server.close = MagicMock()
        mock_server.wait_closed = AsyncMock()

        async def mock_serve(*args, **kwargs):
            return mock_server

        with patch("websockets.serve", side_effect=mock_serve) as mock_serve_func:
            await server.start()

            # Verify serve was called with correct parameters
            mock_serve_func.assert_called_once()
            args = mock_serve_func.call_args[0]
            assert args[1] == server.host
            assert args[2] == 3999

            # Stop server
            await server.stop()
            mock_server.close.assert_called_once()


class TestSimpleMCPClient:
    """Test simple MCP client."""

    def test_client_initialization(self):
        """Test client initialization."""
        client = SimpleMCPClient(host="localhost", port=3001)

        assert client.host == "localhost"
        assert client.port == 3001
        assert client._websocket is None

    @pytest.mark.asyncio
    async def test_client_connect_disconnect(self):
        """Test client connect and disconnect."""
        client = SimpleMCPClient(
            use_transport=False
        )  # Use legacy mode for simpler test

        # Mock websocket connection
        mock_ws = AsyncMock()

        async def mock_connect(*args, **kwargs):
            return mock_ws

        with patch("websockets.connect", side_effect=mock_connect) as mock_connect_func:
            await client.connect()

            mock_connect_func.assert_called_once_with("ws://localhost:3001")
            assert client._websocket == mock_ws

            # Disconnect
            await client.disconnect()
            mock_ws.close.assert_called_once()
            assert client._websocket is None

    @pytest.mark.asyncio
    async def test_client_list_tools(self):
        """Test client list tools."""
        client = SimpleMCPClient(
            use_transport=False
        )  # Use legacy mode for simpler test

        # Mock websocket
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = json.dumps(
            {
                "type": "tools",
                "tools": [
                    {"name": "tool1", "description": "Tool 1"},
                    {"name": "tool2", "description": "Tool 2"},
                ],
            }
        )
        client._websocket = mock_ws

        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "tool1"
        assert tools[1]["name"] == "tool2"

        # Verify request was sent
        mock_ws.send.assert_called_once()
        sent_data = json.loads(mock_ws.send.call_args[0][0])
        assert sent_data["type"] == "list_tools"

    @pytest.mark.asyncio
    async def test_client_call_tool(self):
        """Test client tool call."""
        client = SimpleMCPClient(
            use_transport=False
        )  # Use legacy mode for simpler test

        # Mock websocket
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = json.dumps(
            {"type": "result", "result": {"output": "test result"}}
        )
        client._websocket = mock_ws

        result = await client.call_tool("test-tool", {"param": "value"})

        assert result == {"output": "test result"}

        # Verify request was sent
        mock_ws.send.assert_called_once()
        sent_data = json.loads(mock_ws.send.call_args[0][0])
        assert sent_data["type"] == "call_tool"
        assert sent_data["name"] == "test-tool"
        assert sent_data["arguments"] == {"param": "value"}

    @pytest.mark.asyncio
    async def test_client_error_handling(self):
        """Test client error handling."""
        client = SimpleMCPClient(
            use_transport=False
        )  # Use legacy mode for simpler test

        # Test calling without connection
        with pytest.raises(RuntimeError, match="Not connected"):
            await client.list_tools()

        # Test error response
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = json.dumps({"type": "error", "error": "Test error"})
        client._websocket = mock_ws

        with pytest.raises(RuntimeError, match="MCP error: Test error"):
            await client.list_tools()
