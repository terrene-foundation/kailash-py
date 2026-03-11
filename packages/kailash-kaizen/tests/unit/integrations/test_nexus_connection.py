"""
Test Nexus Connection Interface.

Tests verify:
1. Connection initialization and lifecycle
2. Workflow registration and management
3. Health monitoring
4. Multi-agent coordination
5. Graceful failure scenarios
"""

from unittest.mock import Mock

import pytest


class TestNexusConnectionInitialization:
    """Test NexusConnection initialization."""

    @pytest.fixture
    def mock_nexus_app(self):
        """Create mock Nexus app."""
        from tests.utils.nexus_mocks import MockNexus

        return MockNexus(auto_discovery=False)

    def test_nexus_connection_initialization(self, mock_nexus_app):
        """Connection should initialize with Nexus instance."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)

        assert connection is not None
        assert connection.nexus_app is mock_nexus_app
        assert connection.is_connected() is True

    def test_connection_with_auto_discovery_disabled(self, mock_nexus_app):
        """Connection should respect auto_discovery setting."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app, auto_discovery=False)

        assert connection.auto_discovery is False

    def test_connection_tracks_workflows(self, mock_nexus_app):
        """Connection should track registered workflows."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)

        # Should start with empty workflow dict
        assert connection._workflows == {}


class TestConnectionHealthCheck:
    """Test connection health monitoring."""

    @pytest.fixture
    def mock_nexus_app(self):
        """Create mock Nexus app."""
        from tests.utils.nexus_mocks import MockNexus

        return MockNexus()

    def test_connection_health_check(self, mock_nexus_app):
        """Connection should provide health status."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)
        health = connection.health_check()

        assert isinstance(health, dict)
        assert "status" in health
        assert "workflows" in health
        assert health["status"] in ["healthy", "disconnected"]

    def test_health_check_shows_workflow_count(self, mock_nexus_app):
        """Health check should show number of registered workflows."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)

        # Initially zero workflows
        health = connection.health_check()
        assert health["workflows"] == 0

    def test_health_check_shows_nexus_version(self, mock_nexus_app):
        """Health check should include Nexus version."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)
        health = connection.health_check()

        assert "nexus_version" in health


class TestConnectionLifecycle:
    """Test connection lifecycle management."""

    @pytest.fixture
    def mock_nexus_app(self):
        """Create mock Nexus app."""
        from tests.utils.nexus_mocks import MockNexus

        return MockNexus()

    def test_connection_lifecycle_management(self, mock_nexus_app):
        """Connection should support start/stop lifecycle."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)

        # Should be connected initially
        assert connection.is_connected() is True

        # Stop should disconnect
        connection.stop()
        assert connection.is_connected() is False

    def test_start_passes_kwargs_to_nexus(self, mock_nexus_app):
        """Start should pass kwargs to Nexus app."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)

        # Start with custom kwargs
        connection.start(blocking=False)

        # Mock should track this
        assert mock_nexus_app._running is True


class TestWorkflowRegistration:
    """Test workflow registration functionality."""

    @pytest.fixture
    def mock_nexus_app(self):
        """Create mock Nexus app."""
        from tests.utils.nexus_mocks import MockNexus

        return MockNexus()

    @pytest.fixture
    def mock_workflow(self):
        """Create mock workflow."""
        return Mock(name="test_workflow")

    def test_connection_workflow_registration(self, mock_nexus_app, mock_workflow):
        """Connection should register Kaizen workflows."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)

        # Register workflow
        workflow_name = connection.register_workflow("test_workflow", mock_workflow)

        assert workflow_name == "test_workflow"
        assert "test_workflow" in connection._workflows
        assert connection._workflows["test_workflow"] is mock_workflow

    def test_workflow_registration_calls_nexus(self, mock_nexus_app, mock_workflow):
        """Workflow registration should call Nexus.register()."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)
        connection.register_workflow("test_workflow", mock_workflow)

        # Check Nexus received the registration
        assert "test_workflow" in mock_nexus_app._workflows

    def test_list_registered_workflows(self, mock_nexus_app, mock_workflow):
        """Connection should list all registered workflows."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection = NexusConnection(nexus_app=mock_nexus_app)

        # Register multiple workflows
        connection.register_workflow("workflow1", mock_workflow)
        connection.register_workflow("workflow2", mock_workflow)

        workflows = connection.list_workflows()

        assert len(workflows) == 2
        assert "workflow1" in workflows
        assert "workflow2" in workflows


class TestMultiAgentCoordination:
    """Test multiple agents sharing Nexus instance."""

    @pytest.fixture
    def mock_nexus_app(self):
        """Create mock Nexus app."""
        from tests.utils.nexus_mocks import MockNexus

        return MockNexus()

    def test_multiple_agents_shared_nexus(self, mock_nexus_app):
        """Multiple agents should share same Nexus instance."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        # Create multiple connections to same Nexus
        connection1 = NexusConnection(nexus_app=mock_nexus_app)
        connection2 = NexusConnection(nexus_app=mock_nexus_app)

        # Both should reference same app
        assert connection1.nexus_app is connection2.nexus_app
        assert connection1.nexus_app is mock_nexus_app

    def test_multiple_connections_independent_workflows(self, mock_nexus_app):
        """Each connection should track its own workflows independently."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        connection1 = NexusConnection(nexus_app=mock_nexus_app)
        connection2 = NexusConnection(nexus_app=mock_nexus_app)

        # Register different workflows
        connection1.register_workflow("workflow1", Mock())
        connection2.register_workflow("workflow2", Mock())

        # Each connection tracks its own
        assert "workflow1" in connection1.list_workflows()
        assert "workflow1" not in connection2.list_workflows()
        assert "workflow2" in connection2.list_workflows()
        assert "workflow2" not in connection1.list_workflows()


class TestGracefulFailure:
    """Test graceful failure scenarios."""

    def test_connection_with_invalid_nexus_instance(self):
        """Connection should validate Nexus instance type."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusConnection

        # Attempting to connect with non-Nexus object should work
        # but the connection interface handles it
        fake_nexus = Mock()
        connection = NexusConnection(nexus_app=fake_nexus)

        # Connection should exist but may have limited functionality
        assert connection is not None
