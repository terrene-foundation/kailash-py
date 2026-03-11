"""Unit tests for enhanced MCP server integration in Nexus.

Tests the integration of Core SDK's production-ready MCP server
with full protocol support (tools, resources, prompts).
"""

import json
import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Add nexus src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Test Component 1: Enhanced MCP Server Integration


class TestEnhancedMCPServerCreation:
    """Test creation of enhanced MCP server using Core SDK."""

    @patch("kailash.mcp_server.MCPServer")
    @patch("kailash.mcp_server.auth.APIKeyAuth")
    def test_create_sdk_mcp_server_without_auth(self, mock_auth, mock_server):
        """Test creating MCP server without authentication."""
        from nexus.core import Nexus

        # Create Nexus without auth but WITH HTTP transport to use Core SDK MCPServer
        app = Nexus(enable_auth=False, enable_http_transport=True)

        # Should create server without auth provider
        mock_server.assert_called_once()
        call_args = mock_server.call_args[1]

        assert call_args["name"] == "nexus-mcp"
        assert call_args["enable_cache"] is True
        assert call_args["enable_metrics"] is True
        assert call_args["auth_provider"] is None
        assert call_args["enable_streaming"] is True

    @patch("kailash.mcp_server.MCPServer")
    @patch("kailash.mcp_server.auth.APIKeyAuth")
    def test_create_sdk_mcp_server_with_auth(self, mock_auth, mock_server):
        """Test creating MCP server with authentication enabled."""
        from nexus.core import Nexus

        # Mock API keys
        mock_auth_instance = Mock()
        mock_auth.return_value = mock_auth_instance

        # Create Nexus with auth AND HTTP transport to use Core SDK MCPServer
        app = Nexus(enable_auth=True, enable_http_transport=True)

        # Should create auth provider
        mock_auth.assert_called_once()

        # Should create server with auth
        call_args = mock_server.call_args[1]
        assert call_args["auth_provider"] == mock_auth_instance

    @patch("kailash.mcp_server.MCPServer")
    def test_create_sdk_mcp_server_with_transports(self, mock_server):
        """Test creating MCP server with multiple transports."""
        from nexus.core import Nexus

        # Create with HTTP and SSE transports
        app = Nexus(enable_http_transport=True, enable_sse_transport=True)

        # Check transport configuration
        call_args = mock_server.call_args[1]
        assert call_args["enable_http_transport"] is True
        assert call_args["enable_sse_transport"] is True

    @patch("kailash.mcp_server.MCPServer")
    def test_create_sdk_mcp_server_with_rate_limiting(self, mock_server):
        """Test creating MCP server with rate limiting."""
        from nexus.core import Nexus

        rate_config = {"default": 100, "burst": 200}

        # Create with rate limiting AND HTTP transport to use Core SDK MCPServer
        app = Nexus(rate_limit_config=rate_config, enable_http_transport=True)

        # Check rate limit configuration
        call_args = mock_server.call_args[1]
        assert call_args["rate_limit_config"] == rate_config

    @patch("kailash.mcp_server.MCPServer")
    def test_create_sdk_mcp_server_with_discovery(self, mock_server):
        """Test creating MCP server with discovery enabled."""
        from nexus.core import Nexus

        # Create with discovery AND HTTP transport to use Core SDK MCPServer
        app = Nexus(enable_discovery=True, enable_http_transport=True)

        # Check discovery configuration
        call_args = mock_server.call_args[1]
        assert call_args["enable_discovery"] is True

    def test_system_resource_registration(self):
        """Test that system information resource is registered in WebSocket-only mode."""
        from nexus.core import Nexus

        # Mock the simple MCP server's _resources dict
        with patch("nexus.mcp.MCPServer") as mock_simple_server:
            mock_server_instance = Mock()
            mock_server_instance._resources = (
                {}
            )  # Simple server uses dict for resources
            mock_simple_server.return_value = mock_server_instance

            # Create Nexus in WebSocket-only mode (default)
            app = Nexus()

            # Should register system resource in simple server
            assert "system://nexus/info" in mock_server_instance._resources

            # Test the resource handler
            import asyncio

            handler = mock_server_instance._resources["system://nexus/info"]

            # Mock workflow list
            app._workflows = {"test": Mock()}

            # Call handler
            result = asyncio.run(handler("system://nexus/info"))

            assert result["mimeType"] == "application/json"

            # Parse content
            content = json.loads(result["content"])
            assert content["platform"] == "Kailash Nexus"
            assert content["version"] == "1.0.0"
            assert "test" in content["workflows"]


class TestMCPChannelIntegration:
    """Test MCP channel integration for workflow management."""

    @patch("kailash.channels.MCPChannel")
    @patch("kailash.channels.ChannelConfig")
    def test_setup_mcp_channel(self, mock_config, mock_channel):
        """Test MCP channel setup with HTTP transport enabled."""
        from nexus.core import Nexus

        # Mock config class
        mock_config_instance = Mock()
        mock_config.return_value = mock_config_instance

        # Create Nexus with HTTP transport to enable MCP channel
        app = Nexus(mcp_port=3005, enable_http_transport=True)

        # Should create channel config
        mock_config.assert_called_once()
        config_args = mock_config.call_args[1]

        assert config_args["name"] == "nexus-mcp-channel"
        assert config_args["host"] == "0.0.0.0"
        assert config_args["port"] == 3005
        assert config_args["enable_sessions"] is True

        # Should create channel with server
        mock_channel.assert_called_once_with(
            mock_config_instance, mcp_server=app._mcp_server
        )

    @patch("kailash.channels.MCPChannel")
    def test_workflow_registration_with_channel(self, mock_channel):
        """Test workflow registration with MCP channel."""
        from kailash.workflow.builder import WorkflowBuilder
        from nexus.core import Nexus

        # Mock channel instance
        mock_channel_instance = Mock()
        mock_channel.return_value = mock_channel_instance

        # Create Nexus and workflow
        app = Nexus()
        app._mcp_channel = mock_channel_instance

        workflow = WorkflowBuilder().build()

        # Register workflow
        app.register("test_workflow", workflow)

        # Should register with channel
        mock_channel_instance.register_workflow.assert_called_once_with(
            "test_workflow", workflow
        )

    def test_fallback_to_simple_server(self):
        """Test fallback to simple server when Core SDK not available with HTTP transport."""
        from nexus.core import Nexus

        # Mock import error for Core SDK when HTTP transport is enabled
        with patch("nexus.core.Nexus._create_sdk_mcp_server", side_effect=ImportError):
            with patch("nexus.mcp.MCPServer") as mock_simple_server:
                mock_server_instance = Mock()
                mock_server_instance._resources = {}  # Mock resources dict
                mock_simple_server.return_value = mock_server_instance

                # Should still create Nexus with simple server (fallback from HTTP mode)
                app = Nexus(enable_http_transport=True)

                # Should have simple server
                assert hasattr(app, "_mcp_server")
                assert app._mcp_channel is None
                mock_simple_server.assert_called_once()


class TestAPIKeyManagement:
    """Test API key management for authentication."""

    @patch.dict(
        "os.environ", {"NEXUS_API_KEY_USER1": "key1", "NEXUS_API_KEY_USER2": "key2"}
    )
    def test_get_api_keys_from_environment(self):
        """Test loading API keys from environment variables."""
        from nexus.core import Nexus

        app = Nexus()
        keys = app._get_api_keys()

        assert keys == {"user1": "key1", "user2": "key2"}

    @patch.dict("os.environ", {}, clear=True)
    def test_get_api_keys_default_development(self):
        """Test default API key in development mode."""
        from nexus.core import Nexus

        app = Nexus()
        keys = app._get_api_keys()

        # Should have default test key
        assert keys == {"test_user": "test-api-key-12345"}

    @patch.dict("os.environ", {"NEXUS_PRODUCTION": "1"}, clear=True)
    def test_get_api_keys_production_mode(self):
        """Test no default keys in production mode."""
        from nexus.core import Nexus

        app = Nexus()
        keys = app._get_api_keys()

        # Should have no keys in production
        assert keys == {}


class TestTransportConfiguration:
    """Test transport configuration for MCP server."""

    def test_get_enabled_transports_default(self):
        """Test default transport configuration."""
        from nexus.core import Nexus

        app = Nexus()
        transports = app._get_enabled_transports()

        # Should only have websocket by default
        assert transports == ["websocket"]

    def test_get_enabled_transports_all(self):
        """Test all transports enabled."""
        from nexus.core import Nexus

        app = Nexus(enable_http_transport=True, enable_sse_transport=True)
        transports = app._get_enabled_transports()

        # Should have all transports
        assert set(transports) == {"websocket", "http", "sse"}


class TestMCPServerLifecycle:
    """Test MCP server start/stop lifecycle."""

    @patch("asyncio.set_event_loop")
    @patch("asyncio.new_event_loop")
    def test_run_mcp_server_with_channel(self, mock_new_loop, mock_set_loop):
        """Test running MCP server with channel."""
        from nexus.core import Nexus

        # Mock event loop
        mock_loop = Mock()
        mock_new_loop.return_value = mock_loop

        # Create Nexus with mocked channel
        app = Nexus()
        app._mcp_channel = Mock()
        app._mcp_channel.start = AsyncMock()

        # Run server - this will catch exception due to mock
        app._run_mcp_server()

        # Should create new loop and set it
        mock_new_loop.assert_called_once()
        mock_set_loop.assert_called_once_with(mock_loop)

    @patch("asyncio.set_event_loop")
    @patch("asyncio.new_event_loop")
    def test_run_mcp_server_fallback(self, mock_new_loop, mock_set_loop):
        """Test running simple MCP server with WebSocket wrapper in WebSocket-only mode."""
        from nexus.core import Nexus

        # Mock event loop
        mock_loop = Mock()
        mock_new_loop.return_value = mock_loop

        # Create Nexus in WebSocket-only mode (no channel)
        with patch("nexus.mcp.MCPServer") as mock_simple_server:
            mock_server_instance = Mock()
            mock_server_instance._resources = {}
            mock_simple_server.return_value = mock_server_instance

            app = Nexus()  # WebSocket-only by default

        # Verify no channel was created
        assert app._mcp_channel is None
        assert app._mcp_server is not None

        # Mock WebSocket server wrapper
        with patch("nexus.mcp_websocket_server.MCPWebSocketServer") as mock_ws_server:
            mock_ws_instance = Mock()
            mock_ws_server.return_value = mock_ws_instance
            mock_loop.create_task = Mock()

            # Run server
            try:
                app._run_mcp_server()
            except Exception:
                pass  # Expected due to mocking

        # Should create new loop and set it
        mock_new_loop.assert_called_once()
        mock_set_loop.assert_called_once_with(mock_loop)

        # Should create WebSocket wrapper (not call run() directly)
        mock_ws_server.assert_called_once_with(
            app._mcp_server, host="0.0.0.0", port=app._mcp_port
        )

    def test_stop_mcp_channel(self):
        """Test stopping MCP channel."""
        from nexus.core import Nexus

        # Create running Nexus with channel
        with patch("asyncio.new_event_loop") as mock_new_loop:
            with patch("asyncio.set_event_loop") as mock_set_loop:
                mock_loop = Mock()
                mock_new_loop.return_value = mock_loop

                app = Nexus()
                app._running = True
                app._mcp_channel = Mock()
                app._mcp_channel.stop = AsyncMock()

                # Stop Nexus
                app.stop()

                # Should create loop for stopping
                assert mock_new_loop.called
                assert mock_set_loop.called

    def test_stop_mcp_server_fallback(self):
        """Test stopping simple MCP server."""
        from nexus.core import Nexus

        # Create running Nexus without channel
        with patch("asyncio.new_event_loop") as mock_new_loop:
            with patch("asyncio.set_event_loop") as mock_set_loop:
                mock_loop = Mock()
                mock_new_loop.return_value = mock_loop

                app = Nexus()
                app._running = True
                app._mcp_channel = None
                app._mcp_server = Mock()
                app._mcp_server.stop = AsyncMock()

                # Stop Nexus
                app.stop()

                # Should create loop for stopping
                assert mock_new_loop.called
                assert mock_set_loop.called


class TestErrorHandling:
    """Test error handling in MCP integration."""

    def test_mcp_server_creation_error(self):
        """Test handling of MCP server creation errors with HTTP transport enabled."""
        from nexus.core import Nexus

        # Test fallback when SDK MCP server creation fails with HTTP transport enabled
        with patch(
            "kailash.mcp_server.MCPServer",
            side_effect=ImportError("Server creation failed"),
        ):
            with patch("nexus.mcp.MCPServer") as mock_simple_server:
                mock_server_instance = Mock()
                mock_server_instance._resources = (
                    {}
                )  # Mock resources dict for simple server
                mock_simple_server.return_value = mock_server_instance

                # Should handle error gracefully and fall back to simple server
                app = Nexus(enable_http_transport=True)

                # Should fall back to simple server
                assert hasattr(app, "_mcp_server")
                assert app._mcp_channel is None
                mock_simple_server.assert_called_once()

    @patch("kailash.mcp_server.MCPServer", side_effect=ImportError)
    def test_workflow_registration_without_mcp(self, mock_server):
        """Test workflow registration when MCP is not available."""
        from kailash.workflow.builder import WorkflowBuilder
        from nexus.core import Nexus

        # Create Nexus - should fall back to simple server
        app = Nexus()

        # Should still register workflow
        workflow = WorkflowBuilder().build()
        app.register("test", workflow)

        # Workflow should be registered internally
        assert "test" in app._workflows


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
