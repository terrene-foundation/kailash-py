"""
Test Channels System - Realistic Coverage

Tests the actual channels implementation to improve coverage
without testing non-existent classes or methods.
"""

import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global singletons before each test to prevent cross-test pollution."""
    import nexus.channels
    import nexus.plugins

    nexus.channels._channel_manager = None
    nexus.plugins._registry = None
    yield
    # Also reset after test to leave clean state
    nexus.channels._channel_manager = None
    nexus.plugins._registry = None


class TestChannelManager:
    """Test the actual ChannelManager class functionality."""

    def test_channel_manager_initialization(self):
        """Test ChannelManager initialization."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()
        assert manager is not None
        assert hasattr(manager, "_channels")
        assert isinstance(manager._channels, dict)

        # Check default channels are initialized
        assert "api" in manager._channels
        assert "cli" in manager._channels
        assert "mcp" in manager._channels

    @patch("nexus.channels.is_port_available", return_value=True)
    def test_configure_api(self, mock_port):
        """Test API channel configuration."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        # Test basic configuration
        config = manager.configure_api(docs_enabled=False)
        assert config is not None
        assert config.additional_config["docs_enabled"] is False

        # Test port configuration
        original_port = config.port
        config = manager.configure_api(port=8080)
        # Port might be adjusted if 8080 is not available
        assert config.port >= 8080

    def test_configure_cli(self):
        """Test CLI channel configuration."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        config = manager.configure_cli(interactive=False, color=False)
        assert config is not None
        assert config.additional_config["interactive"] is False
        assert config.additional_config["color"] is False

    def test_configure_mcp(self):
        """Test MCP channel configuration."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        config = manager.configure_mcp(transport="websocket", version="2.0")
        assert config is not None
        assert config.additional_config["transport"] == "websocket"
        assert config.additional_config["version"] == "2.0"

    def test_get_channel_config(self):
        """Test getting channel configuration."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        # Test valid channels
        api_config = manager.get_channel_config("api")
        assert api_config is not None
        assert api_config.port == 8000  # Default API port

        cli_config = manager.get_channel_config("cli")
        assert cli_config is not None
        assert cli_config.port is None  # CLI doesn't use ports

        mcp_config = manager.get_channel_config("mcp")
        assert mcp_config is not None
        assert mcp_config.port == 3001  # Default MCP port

        # Test invalid channel
        invalid_config = manager.get_channel_config("invalid")
        assert invalid_config is None

    def test_create_unified_channels(self):
        """Test unified channel configuration creation."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        unified = manager.create_unified_channels()
        assert isinstance(unified, dict)
        assert "channels" in unified
        assert "health_endpoint" in unified
        assert "enable_docs" in unified

        # Check all channels are included
        assert "api" in unified["channels"]
        assert "cli" in unified["channels"]
        assert "mcp" in unified["channels"]

        # Check API channel configuration
        api_config = unified["channels"]["api"]
        assert api_config["enabled"] is True
        assert "port" in api_config
        assert "docs_enabled" in api_config

    def test_channel_configuration(self):
        """Test channel configuration (initialize_channels removed - redundant with gateway)."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        # Test that channel configs are created
        api_config = manager.get_channel_config("api")
        assert api_config is not None
        assert api_config.enabled is True

        cli_config = manager.get_channel_config("cli")
        assert cli_config is not None
        assert cli_config.enabled is True

        mcp_config = manager.get_channel_config("mcp")
        assert mcp_config is not None
        assert mcp_config.enabled is True

        # NOTE: Actual channel initialization is handled by Nexus._initialize_gateway()
        # and Nexus._initialize_mcp_server(), not by ChannelManager

    def test_configure_health_endpoint(self):
        """Test health endpoint configuration."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        health_config = manager.configure_health_endpoint()
        assert isinstance(health_config, dict)
        assert health_config["path"] == "/health"
        assert "GET" in health_config["methods"]
        assert "response" in health_config
        assert "channels" in health_config["response"]

    def test_workflow_registration_via_nexus(self):
        """Test workflow registration (register_workflow_on_channels removed - handled by Nexus.register())."""
        # NOTE: Workflow registration across channels is now handled by Nexus.register()
        # which calls:
        # - gateway.register_workflow() for API channel
        # - mcp_channel.register_workflow() for MCP channel
        # - CLI access is automatic via gateway's workflow registry
        #
        # This test verifies that the architecture correctly delegates to Nexus
        from nexus import Nexus

        app = Nexus(enable_durability=False)  # Disable caching for test

        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "result = 'ok'"})

        # Register workflow - this should handle all channels
        app.register("test_workflow", workflow.build())

        # Verify workflow is registered
        assert "test_workflow" in app._workflows

    def test_create_session_manager(self):
        """Test session manager creation."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        session_manager = manager.create_session_manager()
        assert session_manager is not None

        # Should return same instance on subsequent calls
        session_manager2 = manager.create_session_manager()
        assert session_manager is session_manager2


class TestSessionManager:
    """Test the SessionManager class."""

    def test_session_manager_initialization(self):
        """Test SessionManager initialization."""
        from nexus.channels import SessionManager

        manager = SessionManager()
        assert manager is not None
        assert hasattr(manager, "_sessions")
        assert hasattr(manager, "_sync_enabled")
        assert manager._sync_enabled is True

    def test_create_session(self):
        """Test session creation."""
        from nexus.channels import SessionManager

        manager = SessionManager()

        session = manager.create_session("test_session", "api")
        assert session is not None
        assert session["id"] == "test_session"
        assert session["created_by"] == "api"
        assert "api" in session["channels"]
        assert isinstance(session["data"], dict)

    def test_sync_session(self):
        """Test session synchronization."""
        from nexus.channels import SessionManager

        manager = SessionManager()

        # Create a session first
        manager.create_session("test_session", "api")

        # Sync to different channel
        synced_session = manager.sync_session("test_session", "cli")
        assert synced_session is not None
        assert "api" in synced_session["channels"]
        assert "cli" in synced_session["channels"]

        # Test non-existent session
        non_existent = manager.sync_session("non_existent", "cli")
        assert non_existent is None

    def test_update_session(self):
        """Test session data updates."""
        from nexus.channels import SessionManager

        manager = SessionManager()

        # Create a session first
        manager.create_session("test_session", "api")

        # Update session data
        update_data = {"key": "value", "user_id": 123}
        manager.update_session("test_session", update_data)

        # Verify data was updated
        session = manager._sessions["test_session"]
        assert session["data"]["key"] == "value"
        assert session["data"]["user_id"] == 123

    def test_sync_disabled(self):
        """Test session sync when disabled."""
        from nexus.channels import SessionManager

        manager = SessionManager()
        manager._sync_enabled = False

        # Create a session first
        manager.create_session("test_session", "api")

        # Sync should return None when disabled
        result = manager.sync_session("test_session", "cli")
        assert result is None


class TestUtilityFunctions:
    """Test utility functions."""

    def test_is_port_available(self):
        """Test port availability checking."""
        from nexus.channels import is_port_available

        # Test with a port that should be available (high number)
        available = is_port_available(60000)
        assert isinstance(available, bool)

        # Test with a port that might be in use (low number)
        busy_result = is_port_available(80)
        assert isinstance(busy_result, bool)

    def test_find_available_port(self):
        """Test finding available ports."""
        from nexus.channels import find_available_port

        # Should find a port starting from a high number
        port = find_available_port(60000)
        assert isinstance(port, int)
        assert port >= 60000

        # Should handle port conflicts by finding next available
        port2 = find_available_port(60000)
        assert isinstance(port2, int)
        assert port2 >= 60000

    def test_find_available_port_failure(self):
        """Test port finding failure scenario."""
        from nexus.channels import find_available_port

        # Mock all ports as unavailable
        with patch("nexus.channels.is_port_available", return_value=False):
            with pytest.raises(RuntimeError, match="No available ports found"):
                find_available_port(60000, max_attempts=3)


class TestGlobalChannelManager:
    """Test global channel manager functions."""

    def test_get_channel_manager(self):
        """Test global channel manager getter."""
        from nexus.channels import get_channel_manager

        manager1 = get_channel_manager()
        assert manager1 is not None

        # Should return same instance (singleton behavior)
        manager2 = get_channel_manager()
        assert manager1 is manager2

    @patch("nexus.channels.is_port_available", return_value=True)
    def test_convenience_functions(self, mock_port):
        """Test convenience configuration functions."""
        from nexus.channels import configure_api, configure_cli, configure_mcp

        # Test API configuration
        api_config = configure_api(docs_enabled=False)
        assert api_config is not None
        assert api_config.additional_config["docs_enabled"] is False

        # Test CLI configuration
        cli_config = configure_cli(interactive=False)
        assert cli_config is not None
        assert cli_config.additional_config["interactive"] is False

        # Test MCP configuration
        mcp_config = configure_mcp(transport="websocket")
        assert mcp_config is not None
        assert mcp_config.additional_config["transport"] == "websocket"

    def test_create_unified_channels_global(self):
        """Test global unified channels creation."""
        from nexus.channels import create_unified_channels

        unified = create_unified_channels()
        assert isinstance(unified, dict)
        assert "channels" in unified
        assert "api" in unified["channels"]
        assert "cli" in unified["channels"]
        assert "mcp" in unified["channels"]


class TestChannelConfig:
    """Test ChannelConfig dataclass."""

    def test_channel_config_creation(self):
        """Test ChannelConfig initialization."""
        from nexus.channels import ChannelConfig

        # Test default values
        config = ChannelConfig()
        assert config.enabled is True
        assert config.port is None
        assert config.host == "0.0.0.0"
        assert config.additional_config == {}

        # Test custom values
        config = ChannelConfig(
            enabled=False,
            port=8080,
            host="localhost",
            additional_config={"test": "value"},
        )
        assert config.enabled is False
        assert config.port == 8080
        assert config.host == "localhost"
        assert config.additional_config["test"] == "value"

    def test_channel_config_post_init(self):
        """Test ChannelConfig post-initialization."""
        from nexus.channels import ChannelConfig

        # Test with None additional_config
        config = ChannelConfig(additional_config=None)
        assert config.additional_config == {}

        # Test with existing additional_config
        config = ChannelConfig(additional_config={"existing": "value"})
        assert config.additional_config["existing"] == "value"


class TestErrorHandling:
    """Test error handling in channels."""

    def test_channel_initialization_via_nexus_failure(self):
        """Test handling of gateway initialization failures (initialize_channels removed)."""
        # NOTE: initialize_channels() removed - handled by Nexus
        # Test that Nexus handles gateway initialization failures
        from nexus import Nexus

        # Nexus should raise exception if gateway initialization fails
        # (currently it wraps gateway in _initialize_gateway)
        try:
            app = Nexus(enable_durability=False)
            # If we get here, gateway initialized successfully
            assert app._gateway is not None
        except RuntimeError as e:
            # Expected if gateway fails to initialize
            assert "gateway" in str(e).lower()

    def test_port_conflict_handling(self):
        """Test port conflict resolution."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        # Configure API with a potentially busy port
        config = manager.configure_api(port=80)  # HTTP port, likely busy

        # Should either get port 80 or find alternative
        assert config.port >= 80

    def test_invalid_configuration(self):
        """Test handling of invalid configurations."""
        from nexus.channels import ChannelManager

        manager = ChannelManager()

        # Test with invalid channel name
        config = manager.get_channel_config("invalid_channel")
        assert config is None
