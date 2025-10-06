"""Enhanced MCP Server Tests - No External Dependencies.

Tests for enhanced MCP server functionality without mocking external packages.
"""

from unittest.mock import Mock, patch

import pytest
from kailash.mcp_server.server import MCPServer


class TestMCPServer:
    """Test enhanced MCP server functionality."""

    def test_import_mcp_server(self):
        """Test that MCPServer can be imported."""
        from kailash.mcp_server.server import MCPServer

        assert MCPServer is not None

    def test_create_mcp_server_instance(self):
        """Test creating an MCPServer instance."""
        server = MCPServer("test-server")

        assert server.name == "test-server"
        assert server.cache is not None
        assert server.metrics is not None

    def test_enhanced_mcp_server_with_custom_cache_settings(self):
        """Test MCPServer with custom cache settings."""
        server = MCPServer("cache-test-server", enable_cache=True, cache_ttl=600)

        assert server.name == "cache-test-server"
        assert server.cache is not None
        # Cache should be enabled and TTL configured
        assert server.cache.enabled is True
        assert server.cache.default_ttl == 600

    @patch("kailash.mcp_server.server.logger")
    def test_mcp_initialization_provides_interface(self, mock_logger):
        """Test that MCP initialization provides required interface."""
        server = MCPServer("interface-test")

        # Mock the FastMCP import to avoid timeout issues
        with patch("builtins.__import__") as mock_import:

            def side_effect(name, *args, **kwargs):
                if name == "fastmcp":
                    # Simulate ImportError to test fallback behavior
                    raise ImportError("FastMCP not available")
                elif name == "mcp.server":
                    # Create a mock FastMCP class
                    mock_fastmcp_module = Mock()
                    mock_fastmcp_class = Mock()
                    mock_fastmcp_module.FastMCP = mock_fastmcp_class
                    mock_fastmcp_class.return_value = Mock()
                    return mock_fastmcp_module
                else:
                    return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect
            server._init_mcp()

        # Should have MCP interface regardless of implementation
        assert server._mcp is not None

    @pytest.mark.slow
    def test_init_mcp_idempotent(self):
        """Test that _init_mcp can be called multiple times safely."""
        server = MCPServer("idempotent-test")

        # Should be able to call multiple times without error
        server._init_mcp()
        first_mcp = server._mcp

        server._init_mcp()
        second_mcp = server._mcp

        # Should be the same instance
        assert first_mcp is second_mcp

    @pytest.mark.slow
    def test_tool_decorator_functionality(self):
        """Test that tool decorator works functionally."""
        server = MCPServer("tool-test")

        @server.tool()
        def test_tool():
            return "tool works"

        # Should initialize MCP and register tool
        assert server._mcp is not None
        assert "test_tool" in server._tool_registry

        # The decorator returns a FunctionTool, so we need to call its fn attribute
        # When FastMCP is not available, the function is returned as-is
        if hasattr(test_tool, "fn"):
            assert test_tool.fn() == "tool works"
        else:
            assert test_tool() == "tool works"

    def test_resource_decorator_functionality(self):
        """Test that resource decorator works functionally."""
        server = MCPServer("resource-test")

        @server.resource("test://resource")
        def test_resource():
            return "resource works"

        # Should initialize MCP
        assert server._mcp is not None

        # The decorator returns a FunctionResource, so we need to call its fn attribute
        # When FastMCP is not available, the function is returned as-is
        if hasattr(test_resource, "fn"):
            assert test_resource.fn() == "resource works"
        else:
            assert test_resource() == "resource works"

    def test_fastmcp_import_path(self):
        """Test that import path handling works correctly."""
        server = MCPServer("import-test")

        # Should handle imports gracefully
        server._init_mcp()
        assert server._mcp is not None

    def test_run_method(self):
        """Test that run method exists and is callable."""
        server = MCPServer("run-test")

        # Should have run method
        assert hasattr(server, "run")
        assert callable(server.run)

        # Note: We don't actually call run() since it would block


class TestMCPServerIntegration:
    """Test MCP server integration functionality."""

    def test_enhanced_mcp_server_with_real_functionality(self):
        """Test enhanced MCP server with real functionality."""
        server = MCPServer("integration-test")

        @server.tool()
        def integration_tool(data: str) -> str:
            return f"processed: {data}"

        # Should work functionally
        # When FastMCP is not available, the function is returned as-is
        if hasattr(integration_tool, "fn"):
            assert integration_tool.fn("test") == "processed: test"
        else:
            assert integration_tool("test") == "processed: test"
        assert "integration_tool" in server._tool_registry

    def test_server_provides_expected_interface(self):
        """Test that server provides expected interface."""
        server = MCPServer("interface-test")

        # Should have expected methods
        assert hasattr(server, "tool")
        assert hasattr(server, "resource")
        assert hasattr(server, "prompt")
        assert hasattr(server, "run")
        assert hasattr(server, "health_check")
        assert hasattr(server, "get_server_stats")

        # Should have expected attributes
        assert hasattr(server, "name")
        assert hasattr(server, "cache")
        assert hasattr(server, "metrics")
        assert hasattr(server, "_tool_registry")
        assert hasattr(server, "_resource_registry")
        assert hasattr(server, "_prompt_registry")
