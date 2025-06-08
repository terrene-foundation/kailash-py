"""Unit tests for MCP (Model Context Protocol) service layer.

This test file has been updated to reflect the new MCP architecture where
MCP is a service capability, not standalone nodes.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from kailash.mcp import MCPClient
from kailash.mcp.server import SimpleMCPServer
from kailash.nodes.ai import LLMAgentNode


class TestMCPClient:
    """Test cases for MCP client service."""

    @pytest.mark.asyncio
    async def test_discover_tools(self):
        """Test tool discovery from MCP servers."""
        client = MCPClient()

        # Mock the MCP SDK imports and usage
        mock_tool = Mock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.inputSchema = {"type": "object", "properties": {}}

        mock_result = Mock()
        mock_result.tools = [mock_tool]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_result)

        # Mock at the import level within the method
        mock_client_session = MagicMock()
        mock_stdio_client = MagicMock()

        # Setup the async context managers
        mock_stdio_client.return_value.__aenter__.return_value = (Mock(), Mock())
        mock_client_session.return_value.__aenter__.return_value = mock_session

        with patch.dict(
            "sys.modules",
            {
                "mcp": MagicMock(
                    ClientSession=mock_client_session, StdioServerParameters=MagicMock()
                ),
                "mcp.client.stdio": MagicMock(stdio_client=mock_stdio_client),
            },
        ):
            # Test discovery with stdio config
            tools = await client.discover_tools(
                {
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "test_server"],
                }
            )

            assert len(tools) == 1
            assert tools[0]["name"] == "test_tool"
            assert tools[0]["description"] == "A test tool"

    @pytest.mark.asyncio
    async def test_call_tool(self):
        """Test calling a tool on MCP server."""
        client = MCPClient()

        # Mock the tool call result
        mock_result = Mock()
        mock_result.content = [Mock(text="Tool executed successfully")]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        # Mock at the import level within the method
        mock_client_session = MagicMock()
        mock_stdio_client = MagicMock()

        # Setup the async context managers
        mock_stdio_client.return_value.__aenter__.return_value = (Mock(), Mock())
        mock_client_session.return_value.__aenter__.return_value = mock_session

        with patch.dict(
            "sys.modules",
            {
                "mcp": MagicMock(
                    ClientSession=mock_client_session, StdioServerParameters=MagicMock()
                ),
                "mcp.client.stdio": MagicMock(stdio_client=mock_stdio_client),
            },
        ):
            # Test tool call
            result = await client.call_tool(
                {"transport": "stdio", "command": "python", "args": []},
                "test_tool",
                {"param": "value"},
            )

            assert result["success"] is True
            assert "Tool executed successfully" in str(result)

    @pytest.mark.asyncio
    async def test_list_resources(self):
        """Test listing resources from MCP server."""
        client = MCPClient()

        # Mock resource
        mock_resource = Mock()
        mock_resource.uri = "test://resource"
        mock_resource.name = "Test Resource"
        mock_resource.description = "A test resource"
        mock_resource.mimeType = "text/plain"

        mock_result = Mock()
        mock_result.resources = [mock_resource]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_resources = AsyncMock(return_value=mock_result)

        # Mock at the import level within the method
        mock_client_session = MagicMock()
        mock_stdio_client = MagicMock()

        # Setup the async context managers
        mock_stdio_client.return_value.__aenter__.return_value = (Mock(), Mock())
        mock_client_session.return_value.__aenter__.return_value = mock_session

        with patch.dict(
            "sys.modules",
            {
                "mcp": MagicMock(
                    ClientSession=mock_client_session, StdioServerParameters=MagicMock()
                ),
                "mcp.client.stdio": MagicMock(stdio_client=mock_stdio_client),
            },
        ):
            # Test resource listing
            resources = await client.list_resources(
                {"transport": "stdio", "command": "python", "args": []}
            )

            assert len(resources) == 1
            assert resources[0]["uri"] == "test://resource"
            assert resources[0]["name"] == "Test Resource"


class TestMCPServer:
    """Test cases for MCP server base class."""

    def test_create_server(self):
        """Test creating an MCP server."""
        # SimpleMCPServer is the concrete implementation we test
        server = SimpleMCPServer(name="test_server")

        assert server.name == "test_server"
        assert hasattr(server, "tool")
        assert hasattr(server, "resource")
        assert hasattr(server, "prompt")

    def test_add_tool_decorator(self):
        """Test adding tools to server via decorator."""
        server = SimpleMCPServer(name="test_server")

        # Mock tool function
        @server.tool()
        def test_tool(query: str) -> str:
            return f"Searched for: {query}"

        # Verify tool was registered
        assert len(server._tools) == 1
        assert server._tools[0].__name__ == "test_tool"

    def test_add_resource_decorator(self):
        """Test adding resources to server via decorator."""
        server = SimpleMCPServer(name="test_server")

        # Mock resource function
        @server.resource(uri="test://data")
        def test_resource() -> dict:
            return {"data": "test"}

        # Verify resource was registered
        assert len(server._resources) == 1
        assert server._resources[0][0] == "test://data"
        assert server._resources[0][1].__name__ == "test_resource"


class TestLLMAgentMCPIntegration:
    """Test LLMAgent integration with MCP."""

    def test_agent_discovers_tools(self):
        """Test that LLMAgentNode can discover MCP tools."""
        agent = LLMAgentNode()

        # Mock MCP client
        mock_client = Mock()
        mock_client.discover_tools = Mock(
            return_value=[
                {
                    "name": "search",
                    "description": "Search for information",
                    "parameters": {"type": "object", "properties": {}},
                }
            ]
        )

        # Mock the async call
        async def mock_discover_tools(*args, **kwargs):
            return mock_client.discover_tools(*args, **kwargs)

        mock_client.discover_tools = AsyncMock(side_effect=mock_discover_tools)

        # Also need to mock the LLM response
        mock_response = {
            "success": True,
            "response": {"content": "Using the MCP tools available"},
            "context": {"tools_available": ["search"]},
        }

        # Patch MCPClient at the import location in the method
        with patch("kailash.mcp.MCPClient", return_value=mock_client):
            # Also patch the actual LLM call since we're using provider="mock"
            with patch.object(
                agent, "_mock_llm_response", return_value=mock_response["response"]
            ):
                result = agent.run(
                    provider="mock",
                    model="mock-model",
                    messages=[{"role": "user", "content": "test"}],
                    mcp_servers=[
                        {
                            "transport": "stdio",
                            "command": "python",
                            "args": ["-m", "test_server"],
                        }
                    ],
                )

                # Verify result
                assert result["success"] is True
