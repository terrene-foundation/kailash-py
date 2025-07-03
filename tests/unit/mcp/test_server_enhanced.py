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
            from kailash.mcp.server_enhanced import EnhancedMCPServer

            assert EnhancedMCPServer is not None
        except ImportError as e:
            pytest.fail(f"Failed to import EnhancedMCPServer: {e}")

    def test_create_enhanced_mcp_server_instance(self):
        """Test creating an instance of EnhancedMCPServer."""
        from kailash.mcp.server_enhanced import EnhancedMCPServer

        server = EnhancedMCPServer(name="test-server")
        assert server.name == "test-server"
        assert server._mcp is None  # Not initialized until first use
        assert server.cache is not None
        assert server.metrics is not None

    def test_enhanced_mcp_server_with_custom_cache_settings(self):
        """Test creating EnhancedMCPServer with custom cache settings."""
        from kailash.mcp.server_enhanced import EnhancedMCPServer

        server = EnhancedMCPServer(
            name="test-server", enable_cache=False, cache_ttl=600
        )
        assert server.name == "test-server"
        assert server.cache.enabled is False

    @patch("kailash.mcp.server_enhanced.logger")
    def test_init_mcp_import_error_handling(self, mock_logger):
        """Test that import errors are handled gracefully."""
        from kailash.mcp.server_enhanced import EnhancedMCPServer

        server = EnhancedMCPServer(name="test-server")

        # Mock the import to fail
        with patch.dict("sys.modules", {"mcp.server": None}):
            with pytest.raises(ImportError):
                server._init_mcp()

            # Verify error was logged
            mock_logger.error.assert_called_with(
                "FastMCP not available. Install with: pip install 'mcp[server]'"
            )

    def test_init_mcp_successful_import(self):
        """Test successful FastMCP initialization."""
        pytest.skip(
            "Cannot reliably mock external mcp.server.FastMCP due to namespace collision"
        )

    def test_init_mcp_idempotent(self):
        """Test that _init_mcp is idempotent."""
        from kailash.mcp.server_enhanced import EnhancedMCPServer

        server = EnhancedMCPServer(name="test-server")

        # Set a mock MCP instance
        mock_mcp = MagicMock()
        server._mcp = mock_mcp

        # Call _init_mcp again - should not create new instance
        server._init_mcp()

        # Should still be the same instance since it was already set
        assert server._mcp == mock_mcp  # Same instance

    def test_tool_decorator_initializes_mcp(self):
        """Test that using @tool decorator initializes MCP."""
        pytest.skip(
            "Cannot reliably mock external mcp.server.FastMCP due to namespace collision"
        )

    def test_resource_decorator_initializes_mcp(self):
        """Test that using @resource decorator initializes MCP."""
        pytest.skip(
            "Cannot reliably mock external mcp.server.FastMCP due to namespace collision"
        )

    def test_fastmcp_import_path(self):
        """Test that the correct import path is used for FastMCP."""
        # This test verifies the fix by checking the actual import in the code
        import inspect

        from kailash.mcp.server_enhanced import EnhancedMCPServer

        # Get the source code of _init_mcp method
        source = inspect.getsource(EnhancedMCPServer._init_mcp)

        # Verify the code uses importlib.import_module('mcp.server')
        assert (
            "importlib.import_module('mcp.server')" in source
            or 'importlib.import_module("mcp.server")' in source
        )
        # Verify the old incorrect import is NOT present
        assert "from mcp.server.fastmcp import FastMCP" not in source

    def test_run_method(self):
        """Test the run method starts the server."""
        pytest.skip(
            "Cannot reliably mock external mcp.server.FastMCP due to namespace collision"
        )


class TestEnhancedMCPServerIntegration:
    """Integration tests for EnhancedMCPServer with actual MCP package."""

    @pytest.mark.integration
    def test_enhanced_mcp_server_with_real_mcp(self):
        """Test EnhancedMCPServer with real MCP package if available."""
        try:
            # Try to import the real MCP package
            import mcp
            from mcp.server import FastMCP

            # If we get here, MCP is installed
            from kailash.mcp.server_enhanced import EnhancedMCPServer

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
                from kailash.mcp.server_enhanced import EnhancedMCPServer

                server = EnhancedMCPServer(name="test-server")

                # This should raise ImportError with helpful message
                with pytest.raises(ImportError):
                    server._init_mcp()

        finally:
            # Restore mcp modules
            sys.modules.update(mcp_modules)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
