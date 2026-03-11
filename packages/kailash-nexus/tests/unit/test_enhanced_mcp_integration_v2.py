"""Unit tests for enhanced MCP server integration in Nexus (v2).

Simplified version with better test isolation and less complex mocking.
"""

import json
import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

# Add nexus src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


class TestEnhancedMCPIntegration:
    """Test enhanced MCP server integration."""

    def test_nexus_initialization_defaults(self):
        """Test Nexus initializes with correct defaults."""
        from nexus.core import Nexus

        app = Nexus()

        # Check defaults
        assert app._api_port == 8000
        assert app._mcp_port == 3001
        assert app._enable_auth is False
        assert app._enable_monitoring is False
        assert app._enable_http_transport is False
        assert app._enable_sse_transport is False
        assert app._enable_discovery is False
        assert app.name == "nexus"

    @patch("kailash.mcp_server.auth.APIKeyAuth")
    def test_nexus_initialization_with_options(self, mock_auth):
        """Test Nexus initializes with custom options."""
        from nexus.core import Nexus

        mock_auth.return_value = Mock()

        app = Nexus(
            api_port=8080,
            mcp_port=3080,
            enable_auth=True,
            enable_monitoring=True,
            enable_http_transport=True,
            enable_sse_transport=True,
            enable_discovery=True,
        )

        # Check custom values
        assert app._api_port == 8080
        assert app._mcp_port == 3080
        assert app._enable_auth is True
        assert app._enable_monitoring is True
        assert app._enable_http_transport is True
        assert app._enable_sse_transport is True
        assert app._enable_discovery is True

    def test_get_api_keys_from_environment(self):
        """Test loading API keys from environment."""
        from nexus.core import Nexus

        # Set environment variables
        os.environ["NEXUS_API_KEY_USER1"] = "key1"
        os.environ["NEXUS_API_KEY_USER2"] = "key2"

        try:
            app = Nexus()
            keys = app._get_api_keys()

            assert keys == {"user1": "key1", "user2": "key2"}
        finally:
            # Cleanup
            del os.environ["NEXUS_API_KEY_USER1"]
            del os.environ["NEXUS_API_KEY_USER2"]

    def test_get_api_keys_default_development(self):
        """Test default API key in development mode."""
        from nexus.core import Nexus

        # Ensure no production flag
        if "NEXUS_PRODUCTION" in os.environ:
            del os.environ["NEXUS_PRODUCTION"]

        app = Nexus()
        keys = app._get_api_keys()

        # Should have default test key
        assert "test_user" in keys
        assert keys["test_user"] == "test-api-key-12345"

    def test_get_api_keys_production_mode(self):
        """Test no default keys in production mode."""
        from nexus.core import Nexus

        # Set production flag
        os.environ["NEXUS_PRODUCTION"] = "1"

        try:
            app = Nexus()
            keys = app._get_api_keys()

            # Should have no keys in production
            assert keys == {}
        finally:
            del os.environ["NEXUS_PRODUCTION"]

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

    def test_workflow_registration(self):
        """Test workflow registration."""
        from kailash.workflow.builder import WorkflowBuilder
        from nexus.core import Nexus

        app = Nexus()

        # Create a workflow
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "result = {'test': True}"})
        built_workflow = workflow.build()

        # Register workflow
        app.register("test_workflow", built_workflow)

        # Check registration
        assert "test_workflow" in app._workflows
        assert app._workflows["test_workflow"] == built_workflow

    def test_health_check(self):
        """Test health check functionality."""
        from nexus.core import Nexus

        app = Nexus()
        health = app.health_check()

        # Check health status
        assert "status" in health
        assert health["platform_type"] == "zero-config-workflow"
        assert health["server_type"] == "enterprise"
        assert health["workflows"] == 0  # No workflows registered yet
        assert health["api_port"] == 8000
        assert health["enterprise_features"]["multi_channel"] is True

    def test_performance_metrics(self):
        """Test performance metrics tracking."""
        from kailash.workflow.builder import WorkflowBuilder
        from nexus.core import Nexus

        app = Nexus()

        # Register a workflow to trigger metric tracking
        workflow = WorkflowBuilder().build()
        app.register("perf_test", workflow)

        # Check metrics
        metrics = app.get_performance_metrics()
        assert "workflow_registration_time" in metrics
        assert metrics["workflow_registration_time"]["count"] >= 1

    def test_channel_status(self):
        """Test channel status reporting."""
        from nexus.core import Nexus

        app = Nexus()
        status = app.get_channel_status()

        # Check channel status
        assert "api" in status
        assert "cli" in status
        assert "mcp" in status

        for channel in ["api", "cli", "mcp"]:
            assert "status" in status[channel]
            assert "capability" in status[channel]


class TestMCPServerCreation:
    """Test MCP server creation with mocking."""

    def test_nexus_has_mcp_server(self):
        """Test that Nexus creates an MCP server (either enhanced or simple)."""
        from nexus.core import Nexus

        # Create Nexus
        app = Nexus(enable_auth=False)

        # Should have MCP server (either enhanced or simple)
        assert hasattr(app, "_mcp_server")
        assert app._mcp_server is not None

    @patch("kailash.mcp_server.auth.APIKeyAuth")
    def test_nexus_with_auth_configuration(self, mock_auth):
        """Test creating Nexus with authentication configuration."""
        from nexus.core import Nexus

        mock_auth.return_value = Mock()

        # Set up API key
        os.environ["NEXUS_API_KEY_TESTUSER"] = "test-key"

        try:
            # Create Nexus with auth
            app = Nexus(enable_auth=True)

            # Should have auth enabled
            assert app._enable_auth is True

            # Should have API keys configured
            keys = app._get_api_keys()
            assert "testuser" in keys
            assert keys["testuser"] == "test-key"

        finally:
            del os.environ["NEXUS_API_KEY_TESTUSER"]

    @patch("kailash.mcp_server.MCPServer", side_effect=ImportError("MCP not available"))
    def test_fallback_to_simple_server(self, mock_mcp_server):
        """Test fallback to simple server when Core SDK not available."""
        from nexus.core import Nexus

        # Create Nexus - should fall back
        app = Nexus()

        # Should have simple server
        assert hasattr(app, "_mcp_server")
        assert app._mcp_channel is None


class TestResourceManagement:
    """Test resource management functionality."""

    def test_nexus_resource_manager_creation(self):
        """Test creating resource manager."""
        from nexus.resources import NexusResourceManager

        # Mock server and nexus
        mock_server = Mock()
        mock_nexus = Mock()
        mock_nexus._workflows = {}
        mock_nexus._api_port = 8000
        mock_nexus._mcp_port = 3001
        mock_nexus.enable_auth = False
        mock_nexus._get_enabled_transports = Mock(return_value=["websocket"])

        # Create resource manager
        manager = NexusResourceManager(mock_server, mock_nexus)

        assert manager.server == mock_server
        assert manager.nexus == mock_nexus

    def test_mime_type_detection(self):
        """Test MIME type detection."""
        from nexus.resources import NexusResourceManager

        # Mock dependencies
        mock_server = Mock()
        mock_nexus = Mock()
        mock_nexus._workflows = {}

        manager = NexusResourceManager(mock_server, mock_nexus)

        # Test various file types
        assert manager._get_mime_type("file.json") == "application/json"
        assert manager._get_mime_type("file.xml") == "application/xml"
        assert manager._get_mime_type("file.txt") == "text/plain"
        assert manager._get_mime_type("file.md") == "text/markdown"
        assert manager._get_mime_type("file.py") == "text/x-python"
        assert manager._get_mime_type("file.unknown") == "application/octet-stream"

    def test_resource_security_check(self):
        """Test resource access security."""
        from nexus.resources import NexusResourceManager

        # Mock dependencies
        mock_server = Mock()
        mock_nexus = Mock()

        manager = NexusResourceManager(mock_server, mock_nexus)

        # Test forbidden paths
        assert manager._is_allowed_resource("../etc/passwd") is False
        assert manager._is_allowed_resource("/etc/shadow") is False
        assert manager._is_allowed_resource(".env") is False
        assert manager._is_allowed_resource("secret_key.pem") is False
        assert manager._is_allowed_resource("passwords.txt") is False

        # Test allowed paths
        assert manager._is_allowed_resource("data/file.json") is True
        assert manager._is_allowed_resource("docs/readme.md") is True

    def test_workflow_schema_extraction(self):
        """Test extracting workflow schema."""
        from nexus.resources import NexusResourceManager

        # Mock dependencies
        mock_server = Mock()
        mock_nexus = Mock()

        manager = NexusResourceManager(mock_server, mock_nexus)

        # Mock workflow with metadata
        mock_workflow = Mock()
        mock_workflow.metadata = {
            "parameters": {
                "input1": {"type": "string", "required": True},
                "input2": {"type": "number", "default": 0},
            }
        }

        # Test extraction
        inputs = manager._extract_workflow_inputs(mock_workflow)
        assert inputs == mock_workflow.metadata["parameters"]

    def test_get_documentation(self):
        """Test documentation retrieval."""
        from nexus.resources import NexusResourceManager

        # Mock dependencies
        mock_server = Mock()
        mock_nexus = Mock()

        manager = NexusResourceManager(mock_server, mock_nexus)

        # Test known docs
        quickstart = manager._get_documentation("quickstart")
        assert quickstart is not None
        assert "# Nexus Quick Start Guide" in quickstart

        api_docs = manager._get_documentation("api")
        assert api_docs is not None
        assert "# Nexus API Reference" in api_docs

        mcp_docs = manager._get_documentation("mcp")
        assert mcp_docs is not None
        assert "# MCP Integration Guide" in mcp_docs

        # Test unknown doc
        unknown = manager._get_documentation("unknown")
        assert unknown is None


class TestSessionManagement:
    """Test session management functionality."""

    def test_create_session(self):
        """Test session creation."""
        from nexus.core import Nexus

        app = Nexus()

        # Create session
        session_id = app.create_session(channel="api")

        # Should return a session ID
        assert session_id is not None
        assert isinstance(session_id, str)

        # Check performance metric
        metrics = app.get_performance_metrics()
        assert "session_sync_latency" in metrics
        assert metrics["session_sync_latency"]["count"] >= 1

    def test_broadcast_event(self):
        """Test event broadcasting."""
        from nexus.core import Nexus

        app = Nexus()

        # Set channels as active for testing
        app._channel_registry["api"]["status"] = "active"
        app._channel_registry["cli"]["status"] = "active"
        app._channel_registry["mcp"]["status"] = "active"

        # Broadcast event
        event = app.broadcast_event("TEST_EVENT", {"data": "test"})

        # Check event structure
        assert event["type"] == "TEST_EVENT"
        assert event["data"] == {"data": "test"}
        assert "timestamp" in event
        assert "id" in event


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
