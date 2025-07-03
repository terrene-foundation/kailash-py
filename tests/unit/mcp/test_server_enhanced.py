"""Unit tests for EnhancedMCPServer to verify FastMCP import fix."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestEnhancedMCPServer:
    """Test EnhancedMCPServer functionality and imports."""

    def test_import_enhanced_mcp_server(self):
        """Test that EnhancedMCPServer can be imported without errors."""
        try:
            from kailash.mcp_server.server import EnhancedMCPServer

            assert EnhancedMCPServer is not None
        except ImportError as e:
            pytest.fail(f"Failed to import EnhancedMCPServer: {e}")

    def test_create_enhanced_mcp_server_instance(self):
        """Test creating an instance of EnhancedMCPServer."""
        from kailash.mcp_server.server import EnhancedMCPServer

        server = EnhancedMCPServer(name="test-server")
        assert server.name == "test-server"
        assert server._mcp is None  # Not initialized until first use
        assert server.cache is not None
        assert server.metrics is not None

    def test_enhanced_mcp_server_with_custom_cache_settings(self):
        """Test creating EnhancedMCPServer with custom cache settings."""
        from kailash.mcp_server.server import EnhancedMCPServer

        server = EnhancedMCPServer(
            name="test-server", enable_cache=False, cache_ttl=600
        )
        assert server.name == "test-server"
        assert server.cache.enabled is False

    @patch("kailash.mcp_server.server.logger")
    def test_init_mcp_import_error_handling(self, mock_logger):
        """Test that import errors are handled gracefully."""
        from kailash.mcp_server.server import EnhancedMCPServer

        server = EnhancedMCPServer(name="test-server")

        # Mock the import to fail
        with patch.dict("sys.modules", {"mcp.server": None}):
            with pytest.raises(ImportError):
                server._init_mcp()

            # Verify error was logged
            mock_logger.error.assert_called_with(
                "FastMCP not available. Install with: pip install 'mcp[server]'"
            )

    @patch("mcp.server.FastMCP")
    def test_init_mcp_successful_import(self, mock_fastmcp_class):
        """Test successful FastMCP initialization."""
        from kailash.mcp_server.server import EnhancedMCPServer

        # Create mock FastMCP instance
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp

        server = EnhancedMCPServer(name="test-server")

        # Should be None initially
        assert server._mcp is None

        # Initialize MCP
        server._init_mcp()

        # Should now be set to our mock
        assert server._mcp is mock_fastmcp
        mock_fastmcp_class.assert_called_once_with("test-server")

    def test_init_mcp_idempotent(self):
        """Test that _init_mcp is idempotent."""
        from kailash.mcp_server.server import EnhancedMCPServer

        server = EnhancedMCPServer(name="test-server")

        # Set a mock MCP instance
        mock_mcp = MagicMock()
        server._mcp = mock_mcp

        # Call _init_mcp again - should not create new instance
        server._init_mcp()

        # Should still be the same instance since it was already set
        assert server._mcp == mock_mcp  # Same instance

    @patch("mcp.server.FastMCP")
    def test_tool_decorator_initializes_mcp(self, mock_fastmcp_class):
        """Test that using @tool decorator initializes MCP."""
        from kailash.mcp_server.server import EnhancedMCPServer

        # Create mock FastMCP instance
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp

        # Mock the tool decorator to return the original function
        mock_fastmcp.tool.return_value = lambda func: func

        server = EnhancedMCPServer(name="test-server")

        # Should be None initially
        assert server._mcp is None

        # Use tool decorator - should initialize MCP
        @server.tool()
        def test_tool():
            return "test"

        # Should now be initialized
        assert server._mcp is mock_fastmcp
        mock_fastmcp_class.assert_called_once_with("test-server")

    @patch("mcp.server.FastMCP")
    def test_resource_decorator_initializes_mcp(self, mock_fastmcp_class):
        """Test that using @resource decorator initializes MCP."""
        from kailash.mcp_server.server import EnhancedMCPServer

        # Create mock FastMCP instance
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp

        # Mock the resource decorator to return the original function
        mock_fastmcp.resource.return_value = lambda func: func

        server = EnhancedMCPServer(name="test-server")

        # Should be None initially
        assert server._mcp is None

        # Use resource decorator - should initialize MCP
        @server.resource("test://resource")
        def test_resource():
            return "test data"

        # Should now be initialized
        assert server._mcp is mock_fastmcp
        mock_fastmcp_class.assert_called_once_with("test-server")

    def test_fastmcp_import_path(self):
        """Test that the correct import path is used for FastMCP."""
        # This test verifies the fix by checking the actual import in the code
        import inspect

        from kailash.mcp_server.server import EnhancedMCPServer

        # Get the source code of _init_mcp method
        source = inspect.getsource(EnhancedMCPServer._init_mcp)

        # Verify the code uses standard import (namespace collision resolved)
        assert "from mcp.server import FastMCP" in source
        # Verify the old incorrect import is NOT present
        assert "from mcp.server.fastmcp import FastMCP" not in source

    @patch("mcp.server.FastMCP")
    def test_run_method(self, mock_fastmcp_class):
        """Test the run method starts the server."""
        from kailash.mcp_server.server import EnhancedMCPServer

        # Create mock FastMCP instance
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp

        # Mock run to not block
        mock_fastmcp.run = MagicMock()

        server = EnhancedMCPServer(name="test-server")

        # Should initialize and call run
        server.run()

        # Verify FastMCP was initialized and run called
        mock_fastmcp_class.assert_called_once_with("test-server")
        mock_fastmcp.run.assert_called_once()


class TestEnhancedMCPServerIntegration:
    """Integration tests for EnhancedMCPServer with actual MCP package."""

    @pytest.mark.integration
    def test_enhanced_mcp_server_with_real_mcp(self):
        """Test EnhancedMCPServer with real MCP package if available."""
        try:
            # Try to import the real MCP package
            import mcp

            # If we get here, MCP is installed
            from kailash.mcp_server.server import EnhancedMCPServer
            from mcp.server import FastMCP

            server = EnhancedMCPServer(name="integration-test-server")

            # Define a test tool
            @server.tool()
            def test_tool(query: str) -> str:
                """A test tool."""
                return f"Processed: {query}"

            # Verify the server was initialized
            assert server._mcp is not None
            assert isinstance(server._mcp, FastMCP)

            # Verify the tool was registered
            # Note: This depends on the MCP implementation

        except ImportError:
            # MCP not installed, skip this test
            pytest.skip("MCP package not installed")

    @pytest.mark.integration
    def test_import_error_message_accuracy(self):
        """Test that the import error message is accurate."""
        # Temporarily remove mcp from modules if it exists
        mcp_modules = {}
        for key in list(sys.modules.keys()):
            if key.startswith("mcp"):
                mcp_modules[key] = sys.modules.pop(key)

        try:
            # Mock the import to fail
            with patch.dict("sys.modules", {"mcp.server": None}):
                from kailash.mcp_server.server import EnhancedMCPServer

                server = EnhancedMCPServer(name="test-server")

                # This should raise ImportError with helpful message
                with pytest.raises(ImportError):
                    server._init_mcp()

        finally:
            # Restore mcp modules
            sys.modules.update(mcp_modules)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
