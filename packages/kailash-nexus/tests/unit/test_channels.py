"""Unit tests for channel configuration.

Tests the smart defaults and configuration for API, CLI, and MCP channels.
"""

import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestChannelConfiguration:
    """Test channel configuration and smart defaults."""

    def test_configure_api_defaults(self):
        """Test API channel default configuration."""
        from nexus.channels import configure_api

        # Mock port availability to ensure we get default port
        with patch("nexus.channels.find_available_port") as mock_find_port:
            mock_find_port.return_value = 8000

            config = configure_api()

            # Check smart defaults
            assert config.host == "0.0.0.0"
            assert config.port == 8000
            assert config.enabled is True
            assert config.additional_config["docs_enabled"] is True
            assert config.additional_config["cors_enabled"] is True

    def test_configure_cli_defaults(self):
        """Test CLI channel default configuration."""
        from nexus.channels import configure_cli

        config = configure_cli()

        # Check smart defaults
        assert config.port is None  # CLI doesn't use ports
        assert config.enabled is True
        assert config.additional_config["interactive"] is True
        assert config.additional_config["color"] is True

    def test_configure_mcp_defaults(self):
        """Test MCP channel default configuration."""
        from nexus.channels import configure_mcp

        config = configure_mcp()

        # Check smart defaults
        assert config.host == "0.0.0.0"
        assert config.port == 3001
        assert config.enabled is True
        assert config.additional_config["transport"] == "stdio"
        assert config.additional_config["version"] == "1.0"

    def test_port_conflict_detection(self):
        """Test automatic port conflict detection."""
        from nexus.channels import find_available_port

        # Mock is_port_available directly
        with patch("nexus.channels.is_port_available") as mock_is_available:
            # First port is taken, second is free
            mock_is_available.side_effect = [False, True]

            port = find_available_port(8000)

            # Should find next available port
            assert port == 8001

            # Should have tried to check two ports
            assert mock_is_available.call_count == 2
            mock_is_available.assert_any_call(8000)
            mock_is_available.assert_any_call(8001)

    def test_channel_unification(self):
        """Test creating unified channel configuration."""
        from nexus.channels import create_unified_channels

        unified = create_unified_channels()

        # Should have all channels
        assert "channels" in unified
        assert "api" in unified["channels"]
        assert "cli" in unified["channels"]
        assert "mcp" in unified["channels"]

        # Should have health endpoint
        assert unified["health_endpoint"] == "/health"
        assert unified["enable_docs"] is True

    def test_health_endpoint_configuration(self):
        """Test health endpoint configuration."""
        from nexus.channels import configure_health_endpoint

        config = configure_health_endpoint("/healthz")

        assert config["path"] == "/healthz"
        assert config["methods"] == ["GET"]
        assert "response" in config
        assert config["response"]["status"] == "healthy"
        assert "channels" in config["response"]

    def test_channel_initialization_via_gateway(self):
        """Test that channels are initialized via gateway (initialize_channels removed)."""
        # NOTE: initialize_channels() removed - redundant with gateway initialization
        # Channels are now initialized by:
        # - Nexus._initialize_gateway() for API channel
        # - Nexus._initialize_mcp_server() for MCP channel
        # - CLI doesn't need server initialization
        from nexus import Nexus

        # Creating Nexus automatically initializes channels via gateway
        app = Nexus(enable_durability=False)

        # Verify gateway was created
        assert app._gateway is not None

        # Verify MCP server was created
        assert app._mcp_server is not None

        # Channel status is tracked in channel registry
        assert "api" in app._channel_registry
        assert "mcp" in app._channel_registry
        assert "cli" in app._channel_registry

    def test_workflow_registration_across_channels(self):
        """Test workflow registration makes it available on all channels (via Nexus.register())."""
        # NOTE: register_workflow_on_channels() removed - handled by Nexus.register()
        from kailash.workflow.builder import WorkflowBuilder
        from nexus import Nexus

        app = Nexus(enable_durability=False)

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "result = 'test'"})

        # Register workflow - automatically registers on all channels
        app.register("test-workflow", workflow.build())

        # Verify workflow registered
        assert "test-workflow" in app._workflows

        # Verify gateway has the workflow
        assert "test-workflow" in app._gateway.workflows

    def test_cross_channel_session_sync(self):
        """Test session synchronization across channels."""
        from nexus.channels import create_session_manager

        session_mgr = create_session_manager()

        # Create session in one channel
        session = session_mgr.create_session(session_id="test-session", channel="api")

        assert session["id"] == "test-session"
        assert session["created_by"] == "api"
        assert "api" in session["channels"]

        # Sync from another channel
        synced = session_mgr.sync_session("test-session", "cli")

        assert synced is not None
        assert "cli" in synced["channels"]
        assert "api" in synced["channels"]

    def test_channel_specific_overrides(self):
        """Test channel-specific configuration overrides."""
        from nexus.channels import configure_api

        # Mock port availability
        with patch("nexus.channels.find_available_port") as mock_find_port:
            mock_find_port.return_value = 9000

            # Test with overrides
            config = configure_api(port=9000, host="127.0.0.1", enable_docs=False)

            assert config.port == 9000
            assert config.host == "127.0.0.1"
            assert config.additional_config["enable_docs"] is False

    def test_channel_manager_singleton(self):
        """Test that channel manager is a singleton."""
        from nexus.channels import get_channel_manager

        manager1 = get_channel_manager()
        manager2 = get_channel_manager()

        # Should be the same instance
        assert manager1 is manager2

    def test_session_data_update(self):
        """Test session data updates."""
        from nexus.channels import create_session_manager

        session_mgr = create_session_manager()

        # Create session
        session_mgr.create_session("test-session", "api")

        # Update session data
        session_mgr.update_session(
            "test-session", {"user": "test-user", "role": "admin"}
        )

        # Get session
        session = session_mgr.sync_session("test-session", "cli")

        assert session["data"]["user"] == "test-user"
        assert session["data"]["role"] == "admin"

    def test_disabled_channel_handling(self):
        """Test handling of disabled channels."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        # Disable a channel
        manager._channels["mcp"].enabled = False

        # Get channel status
        status = manager._get_channel_status()

        assert status["api"] is True
        assert status["cli"] is True
        assert status["mcp"] is False

        # NOTE: initialize_channels() removed - redundant with gateway initialization
        # Channel enabled/disabled status is now used by:
        # - Nexus to determine which channels to initialize
        # - Not by ChannelManager.initialize_channels() (which was removed)
