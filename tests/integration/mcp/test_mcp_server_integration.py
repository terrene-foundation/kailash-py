"""Integration tests for MCP server functionality including FastMCP fix verification."""

import asyncio
import os
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.mcp_server.server import EnhancedMCPServer
from kailash.nodes.ai.llm_agent import LLMAgentNode


@pytest.mark.integration
class TestMCPServerIntegration:
    """Test MCP server integration with LLMAgentNode."""

    def setup_method(self):
        """Set up test environment."""
        # Enable real MCP for tests
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        self.original_ollama_url = os.environ.get("OLLAMA_BASE_URL")
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11435"

    def teardown_method(self):
        """Clean up test environment."""
        os.environ.pop("KAILASH_USE_REAL_MCP", None)
        if self.original_ollama_url:
            os.environ["OLLAMA_BASE_URL"] = self.original_ollama_url
        else:
            os.environ.pop("OLLAMA_BASE_URL", None)

    def test_enhanced_mcp_server_creation(self):
        """Test that EnhancedMCPServer can be created without import errors."""
        # This tests the FastMCP import fix
        try:
            server = EnhancedMCPServer(name="test-integration-server")
            assert server is not None
            assert server.name == "test-integration-server"
        except ImportError as e:
            pytest.fail(f"FastMCP import fix failed: {e}")

    @patch("mcp.server.FastMCP")
    def test_mcp_server_with_tools(self, mock_fastmcp_class):
        """Test MCP server with tools registration."""
        # Create mock FastMCP instance
        mock_fastmcp = MagicMock()
        mock_tool_decorator = MagicMock()

        # Make the decorator return the original function
        def tool_decorator_impl(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        mock_fastmcp.tool = tool_decorator_impl
        mock_fastmcp_class.return_value = mock_fastmcp

        # Create server and register tools
        server = EnhancedMCPServer(name="tool-test-server")

        @server.tool()
        def search_data(query: str) -> dict:
            """Search for data."""
            return {"results": f"Found data for: {query}"}

        @server.tool()
        def process_data(data: dict) -> dict:
            """Process data."""
            return {"processed": data}

        # Verify server initialized
        assert server._mcp is not None

        # Test the tools work
        result = search_data("test query")
        assert result == {"results": "Found data for: test query"}

        result = process_data({"test": "data"})
        assert result == {"processed": {"test": "data"}}

    @patch("mcp.server.FastMCP")
    def test_mcp_server_with_resources(self, mock_fastmcp_class):
        """Test MCP server with resources registration."""
        # Create mock FastMCP instance
        mock_fastmcp = MagicMock()

        # Make the decorator return the original function
        def resource_decorator_impl(uri):
            def decorator(func):
                return func

            return decorator

        mock_fastmcp.resource = resource_decorator_impl
        mock_fastmcp_class.return_value = mock_fastmcp

        # Create server and register resources
        server = EnhancedMCPServer(name="resource-test-server")

        @server.resource("data://test/resource")
        def test_resource():
            return {"content": "Test resource content"}

        @server.resource("file://config/settings")
        def config_resource():
            return {"content": {"setting1": "value1", "setting2": "value2"}}

        # Verify server initialized
        assert server._mcp is not None

        # Test the resources work
        result = test_resource()
        assert result == {"content": "Test resource content"}

        result = config_resource()
        assert result == {"content": {"setting1": "value1", "setting2": "value2"}}

    def test_llm_agent_with_mcp_server(self):
        """Test LLMAgentNode integration with MCP server."""
        # Create an LLMAgentNode
        agent = LLMAgentNode(name="mcp-integration-agent")

        # Configure MCP servers
        mcp_servers = [
            {
                "name": "test-server",
                "transport": "stdio",
                "command": "echo",
                "args": ["test"],
            }
        ]

        # Test that MCP context retrieval works without async errors
        try:
            result = agent.run(
                provider="mock",
                model="gpt-4",
                messages=[{"role": "user", "content": "Test MCP integration"}],
                mcp_servers=mcp_servers,
                mcp_context=["resource://test"],
            )

            assert result["success"] is True
            assert "response" in result
            # No async warnings should have been raised

        except RuntimeWarning as e:
            if "coroutine" in str(e) and "never awaited" in str(e):
                pytest.fail(f"Async bug not fixed: {e}")
            raise

    def test_mcp_server_in_threaded_environment(self):
        """Test MCP server in multi-threaded environment."""
        results = {"errors": []}

        def run_mcp_test(thread_id):
            """Run MCP test in a thread."""
            try:
                server = EnhancedMCPServer(name=f"thread-{thread_id}-server")

                # This should not raise import errors
                @server.tool()
                def thread_tool(data: str) -> str:
                    return f"Thread {thread_id}: {data}"

                # Verify it works
                result = thread_tool("test")
                assert f"Thread {thread_id}: test" == result

            except Exception as e:
                results["errors"].append(f"Thread {thread_id}: {e}")

        # Run in multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=run_mcp_test, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=5)

        # Check for errors
        if results["errors"]:
            pytest.fail(f"Thread errors: {results['errors']}")

    @pytest.mark.asyncio
    async def test_mcp_server_async_compatibility(self):
        """Test MCP server works in async context."""
        # This tests that the FastMCP import works in async environments

        async def create_and_use_server():
            server = EnhancedMCPServer(name="async-test-server")

            @server.tool()
            async def async_tool(query: str) -> dict:
                """An async tool."""
                await asyncio.sleep(0.1)  # Simulate async work
                return {"result": f"Async processed: {query}"}

            # Test the tool
            result = await async_tool("test query")
            return result

        # Run the async test
        result = await create_and_use_server()
        assert result == {"result": "Async processed: test query"}

    def test_mcp_error_handling(self):
        """Test MCP server error handling."""
        # Test with missing MCP package scenario
        with patch.dict("sys.modules", {"mcp.server": None}):
            server = EnhancedMCPServer(name="error-test-server")

            # Should raise ImportError with helpful message
            with pytest.raises(ImportError) as exc_info:
                server._init_mcp()

            # The error should mention the pip install command
            assert (
                "pip install" in str(exc_info.value)
                or "FastMCP not available" in server.__class__.__module__
            )

    def test_mcp_server_with_llm_tool_discovery(self):
        """Test LLMAgentNode discovers tools from MCP server."""
        agent = LLMAgentNode(name="tool-discovery-agent")

        # Mock MCP client for tool discovery
        with patch("kailash.mcp_server.MCPClient") as mock_mcp_client_class:
            mock_client = MagicMock()
            mock_mcp_client_class.return_value = mock_client

            # Mock discover_tools to return test tools
            mock_client.discover_tools = AsyncMock(
                return_value=[
                    {
                        "name": "search",
                        "description": "Search for information",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                    },
                    {
                        "name": "calculate",
                        "description": "Perform calculations",
                        "parameters": {
                            "type": "object",
                            "properties": {"expression": {"type": "string"}},
                        },
                    },
                ]
            )

            # Configure MCP servers
            mcp_servers = [
                {
                    "name": "tool-server",
                    "transport": "http",
                    "url": "http://localhost:8891",
                }
            ]

            # Discover tools
            tools = agent._discover_mcp_tools(mcp_servers=mcp_servers)

            # Verify tools were discovered
            assert len(tools) == 2
            assert tools[0]["type"] == "function"
            assert tools[0]["function"]["name"] == "search"
            assert tools[0]["function"]["mcp_server"] == "tool-server"
            assert tools[1]["function"]["name"] == "calculate"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
