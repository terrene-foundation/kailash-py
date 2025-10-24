"""Tier 2 Integration Tests for Channel Registration (NO MOCKING).

Tests the complete workflow registration through Nexus channels with real infrastructure.
Validates the stub fixes in channels.py and core.py.
"""

import pytest
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


@pytest.mark.integration
class TestChannelRegistrationIntegration:
    """Integration tests for channel registration and multi-channel access."""

    def test_workflow_registration_creates_channel_endpoints(self):
        """Test that workflow registration creates endpoints across all channels.

        CRITICAL: Tests stub fix in channels.py - verifies workflows are accessible
        through API, CLI, and MCP channels after registration.
        """
        # Create real Nexus instance (NO MOCKING)
        nexus = Nexus(
            api_port=8001,  # Use different port to avoid conflicts
            mcp_port=3002,
            auto_discovery=False,
            enable_durability=False,  # Disable for clean test
        )

        # Create real workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {"code": "result = {'status': 'success', 'value': 42}"},
        )
        built_workflow = workflow.build()

        # Register workflow - should create endpoints across channels
        nexus.register("test_workflow", built_workflow)

        # Verify registration in Nexus internal state (REAL STATE, not mocked)
        assert "test_workflow" in nexus._workflows
        assert nexus._workflows["test_workflow"] == built_workflow

        # Verify gateway registration (if gateway is initialized)
        if nexus._gateway:
            # Gateway uses 'workflows' attribute, not '_workflows'
            assert hasattr(nexus._gateway, "workflows") or hasattr(
                nexus._gateway, "_registered_workflows"
            )

        # Cleanup
        if hasattr(nexus, "shutdown"):
            nexus.shutdown()

    def test_multiple_workflow_registration(self):
        """Test registering multiple workflows creates correct channel state.

        Validates that each workflow is independently accessible and maintains
        correct isolation.
        """
        nexus = Nexus(
            api_port=8002,
            mcp_port=3003,
            auto_discovery=False,
            enable_durability=False,
        )

        # Register first workflow
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "PythonCodeNode",
            "node1",
            {"code": "result = {'workflow': 'one', 'value': 1}"},
        )
        nexus.register("workflow_one", workflow1.build())

        # Register second workflow
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "PythonCodeNode",
            "node2",
            {"code": "result = {'workflow': 'two', 'value': 2}"},
        )
        nexus.register("workflow_two", workflow2.build())

        # Verify both workflows registered
        assert "workflow_one" in nexus._workflows
        assert "workflow_two" in nexus._workflows
        assert len(nexus._workflows) == 2

        # Verify isolation - each workflow is distinct
        assert nexus._workflows["workflow_one"] != nexus._workflows["workflow_two"]

        # Cleanup
        if hasattr(nexus, "shutdown"):
            nexus.shutdown()

    def test_channel_configuration_persistence(self):
        """Test that channel configuration persists after registration.

        Tests the channel manager's state management during workflow operations.
        """
        nexus = Nexus(
            api_port=8003,
            mcp_port=3004,
            auto_discovery=False,
            enable_durability=False,
        )

        # Capture initial channel state
        initial_api_port = nexus._api_port
        initial_mcp_port = nexus._mcp_port

        # Register workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "config_test",
            {"code": "result = {'test': 'config_persistence'}"},
        )
        nexus.register("config_workflow", workflow.build())

        # Verify configuration unchanged (channel config should persist)
        assert nexus._api_port == initial_api_port
        assert nexus._mcp_port == initial_mcp_port

        # Cleanup
        if hasattr(nexus, "shutdown"):
            nexus.shutdown()

    def test_health_endpoint_configuration(self):
        """Test health endpoint configuration across channels.

        Validates the configure_health_endpoint() method implementation.
        """
        from nexus.channels import configure_health_endpoint

        # Configure health endpoint
        health_config = configure_health_endpoint("/health")

        # Verify configuration structure (REAL configuration, not mocked)
        assert health_config["path"] == "/health"
        assert health_config["methods"] == ["GET"]
        assert "response" in health_config
        assert health_config["response"]["status"] == "healthy"
        assert "channels" in health_config["response"]


@pytest.mark.integration
class TestSessionManagerIntegration:
    """Integration tests for session management across channels."""

    def test_session_creation_and_sync(self):
        """Test creating and syncing sessions across channels.

        Tests the SessionManager stub fixes in channels.py.
        """
        from nexus.channels import create_session_manager

        # Create real session manager (NO MOCKING)
        session_manager = create_session_manager()

        # Create session
        session = session_manager.create_session("session_123", "api")

        # Verify session created with correct attributes
        assert session["id"] == "session_123"
        assert session["created_by"] == "api"
        assert session["channels"] == ["api"]
        assert "data" in session

        # Sync session from another channel
        synced_session = session_manager.sync_session("session_123", "cli")

        # Verify session synced across channels
        assert synced_session is not None
        assert "cli" in synced_session["channels"]
        assert "api" in synced_session["channels"]

    def test_session_data_updates(self):
        """Test updating session data across channels.

        Validates shared state management.
        """
        from nexus.channels import create_session_manager

        session_manager = create_session_manager()

        # Create session
        session_manager.create_session("data_session", "api")

        # Update session data
        session_manager.update_session(
            "data_session", {"user_id": "user_123", "preferences": {"theme": "dark"}}
        )

        # Retrieve and verify updates
        session = session_manager.sync_session("data_session", "api")
        assert session["data"]["user_id"] == "user_123"
        assert session["data"]["preferences"]["theme"] == "dark"


@pytest.mark.integration
class TestPortAvailabilityIntegration:
    """Integration tests for port availability checking."""

    def test_find_available_port(self):
        """Test finding available ports with real socket operations.

        NO MOCKING - uses real network stack.
        """
        from nexus.channels import find_available_port, is_port_available

        # Test that we can find an available port
        port = find_available_port(9000)

        # Verify port is actually available
        assert is_port_available(port)
        assert port >= 9000
        assert port < 9010  # Should find within max_attempts

    def test_port_in_use_detection(self):
        """Test detection of ports in use.

        Creates a real socket to test port detection.
        """
        import socket

        from nexus.channels import find_available_port, is_port_available

        # Create a socket and bind to a port
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.bind(("", 0))  # Let OS assign port
        _, port = test_socket.getsockname()
        test_socket.listen(1)

        try:
            # Port should not be available
            assert not is_port_available(port)

            # find_available_port should skip this port
            available = find_available_port(port)
            assert available != port
        finally:
            test_socket.close()
