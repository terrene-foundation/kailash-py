"""Comprehensive test coverage for nexus.core module.

This test file specifically targets the uncovered lines in core.py
to bring coverage above 80% as required by feature-implementation.md.
"""

import logging
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from nexus.core import Nexus, NexusConfig


class TestNexusConfig:
    """Test NexusConfig class."""

    def test_nexus_config_initialization(self):
        """Test NexusConfig initialization with default values."""
        config = NexusConfig()
        assert config.strategy is None
        assert config.interval == 30
        assert config.cors_enabled is True
        assert config.docs_enabled is True


class TestNexusInitialization:
    """Test Nexus class initialization paths."""

    @patch("nexus.core.create_gateway")
    def test_default_initialization(self, mock_create_gateway):
        """Test Nexus initialization with default parameters."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # Verify default parameters are set
        assert nexus._api_port == 8000
        assert nexus._mcp_port == 3001
        assert nexus._auto_discovery_enabled is False
        assert nexus._workflows == {}
        assert nexus._running is False

        # Verify config objects are created
        assert nexus.auth is not None
        assert nexus.monitoring is not None
        assert nexus.api is not None
        assert nexus.mcp is not None

        # Verify gateway creation was called
        mock_create_gateway.assert_called_once()
        call_args = mock_create_gateway.call_args[1]
        assert call_args["title"] == "Kailash Nexus - Zero-Config Workflow Platform"
        assert call_args["server_type"] == "enterprise"
        assert call_args["enable_durability"] is True
        assert call_args["enable_resource_management"] is True
        assert call_args["enable_async_execution"] is True
        assert call_args["enable_health_checks"] is True
        assert call_args["cors_origins"] is None  # Nexus handles CORS natively

    @patch("nexus.core.create_gateway")
    def test_custom_port_initialization(self, mock_create_gateway):
        """Test Nexus initialization with custom ports."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus(api_port=9000, mcp_port=4001)

        assert nexus._api_port == 9000
        assert nexus._mcp_port == 4001

    @patch("nexus.core.create_gateway")
    @patch("kailash.mcp_server.auth.APIKeyAuth")
    def test_enterprise_features_enabled(self, mock_auth, mock_create_gateway):
        """Test Nexus initialization with enterprise features enabled."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway
        mock_auth.return_value = Mock()

        nexus = Nexus(
            enable_auth=True,
            enable_monitoring=True,
            rate_limit=100,
            auto_discovery=False,
        )

        # Check enterprise features are configured
        assert hasattr(nexus, "_auth_enabled")
        assert nexus._auth_enabled is True
        assert hasattr(nexus, "_monitoring_enabled")
        assert nexus._monitoring_enabled is True
        assert hasattr(nexus, "_rate_limit")
        assert nexus._rate_limit == 100
        assert nexus._auto_discovery_enabled is False

    @patch("nexus.core.create_gateway")
    def test_initialization_with_none_rate_limit(self, mock_create_gateway):
        """Test Nexus initialization with None rate limit (coverage of conditional)."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus(rate_limit=None)

        # _rate_limit is always set (stores the value for endpoint decorator)
        assert nexus._rate_limit is None


class TestNexusRevolutionaryCapabilities:
    """Test revolutionary capabilities initialization."""

    @patch("nexus.core.create_gateway")
    def test_revolutionary_capabilities_initialization(self, mock_create_gateway):
        """Test that revolutionary capabilities are initialized."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        with patch.object(
            Nexus, "_initialize_revolutionary_capabilities"
        ) as mock_init_rev:
            nexus = Nexus()

            # Verify revolutionary capabilities initialization was called
            mock_init_rev.assert_called_once()


class TestNexusGatewayIntegration:
    """Test gateway integration and startup methods."""

    @patch("nexus.core.create_gateway")
    def test_gateway_creation_error_handling(self, mock_create_gateway):
        """Test error handling during gateway creation."""
        mock_create_gateway.side_effect = Exception("Gateway creation failed")

        # Should raise RuntimeError (enterprise required)
        with pytest.raises(RuntimeError, match="Nexus requires enterprise gateway"):
            nexus = Nexus()

        # Should only try to create gateway once (no fallback)
        assert mock_create_gateway.call_count == 1

    @patch("nexus.core.create_gateway")
    def test_start_method_starts_gateway(self, mock_create_gateway):
        """Test that start method starts the gateway."""
        mock_gateway = Mock()
        mock_gateway.run = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # Mock the start method to test it's called correctly
        nexus.start()

        # Verify gateway run was called with correct parameters
        mock_gateway.run.assert_called_once_with(host="0.0.0.0", port=8000)

    @patch("nexus.core.create_gateway")
    def test_start_method_with_custom_port(self, mock_create_gateway):
        """Test start method with custom API port."""
        mock_gateway = Mock()
        mock_gateway.run = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus(api_port=9000)
        nexus.start()

        # Wait for thread to start
        import time

        time.sleep(0.1)

        mock_gateway.run.assert_called_once_with(host="0.0.0.0", port=9000)


class TestNexusWorkflowManagement:
    """Test workflow registration and management."""

    @patch("nexus.core.create_gateway")
    def test_workflow_registration(self, mock_create_gateway):
        """Test workflow registration functionality."""
        mock_gateway = Mock()
        mock_gateway.register_workflow = Mock(return_value={"status": "registered"})
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # Create a mock workflow without build method but with proper nodes attr
        mock_workflow = Mock()
        mock_workflow.validate = Mock(return_value=True)
        mock_workflow.nodes = {}  # For _validate_workflow_sandbox
        mock_workflow._node_instances = {}  # For _validate_workflow_sandbox
        # Ensure it doesn't have a build method
        del mock_workflow.build

        # Test workflow registration (register method takes name, workflow only)
        nexus.register("test-workflow", mock_workflow)

        # Verify workflow is stored internally
        assert "test-workflow" in nexus._workflows
        assert nexus._workflows["test-workflow"] == mock_workflow

    @patch("nexus.core.create_gateway")
    def test_workflow_registration_with_workflow_builder(self, mock_create_gateway):
        """Test workflow registration with WorkflowBuilder."""
        mock_gateway = Mock()
        mock_gateway.register_workflow = Mock(return_value={"status": "registered"})
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # Test with WorkflowBuilder mock
        from kailash.workflow.builder import WorkflowBuilder

        with patch.object(WorkflowBuilder, "build") as mock_build:
            mock_workflow = Mock()
            mock_workflow.nodes = {}  # For _validate_workflow_sandbox
            mock_workflow._node_instances = {}  # For _validate_workflow_sandbox
            mock_build.return_value = mock_workflow

            builder = WorkflowBuilder()
            nexus.register("test-workflow", builder)

            # Verify builder.build() was called
            mock_build.assert_called_once()

            # Verify workflow is stored
            assert "test-workflow" in nexus._workflows
            assert nexus._workflows["test-workflow"] == mock_workflow


class TestNexusConfigurationObjects:
    """Test Nexus configuration objects and attribute access."""

    @patch("nexus.core.create_gateway")
    def test_config_objects_creation(self, mock_create_gateway):
        """Test that config objects are properly created."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # All config objects should be NexusConfig instances
        assert isinstance(nexus.auth, NexusConfig)
        assert isinstance(nexus.monitoring, NexusConfig)
        assert isinstance(nexus.api, NexusConfig)
        assert isinstance(nexus.mcp, NexusConfig)

    @patch("nexus.core.create_gateway")
    def test_config_attribute_modification(self, mock_create_gateway):
        """Test modification of config attributes."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # Test modifying config attributes
        nexus.auth.strategy = "rbac"
        nexus.monitoring.interval = 60
        nexus.api.cors_enabled = False

        assert nexus.auth.strategy == "rbac"
        assert nexus.monitoring.interval == 60
        assert nexus.api.cors_enabled is False


class TestNexusErrorHandling:
    """Test error handling scenarios."""

    @patch("nexus.core.create_gateway")
    def test_workflow_registration_error_handling(self, mock_create_gateway):
        """Test error handling during workflow registration."""
        mock_gateway = Mock()
        mock_gateway.register_workflow = Mock(
            side_effect=Exception("Registration failed")
        )
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()
        mock_workflow = Mock()
        mock_workflow.nodes = {}  # For _validate_workflow_sandbox
        mock_workflow._node_instances = {}  # For _validate_workflow_sandbox
        # Ensure it doesn't have a build method
        del mock_workflow.build

        # Registration should raise error (enterprise gateway required)
        with pytest.raises(Exception, match="Registration failed"):
            nexus.register("test-workflow", mock_workflow)

    @patch("nexus.core.create_gateway")
    def test_invalid_workflow_handling(self, mock_create_gateway):
        """Test handling of invalid workflow objects."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # Register method accepts any object without validation
        # Test with None workflow
        nexus.register("test-workflow", None)
        assert "test-workflow" in nexus._workflows

        # Test with invalid object
        nexus.register("test-workflow", "not-a-workflow")
        assert nexus._workflows["test-workflow"] == "not-a-workflow"


class TestNexusStateManagement:
    """Test Nexus internal state management."""

    @patch("nexus.core.create_gateway")
    def test_internal_state_initialization(self, mock_create_gateway):
        """Test internal state is properly initialized."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # Check internal state
        assert isinstance(nexus._workflows, dict)
        assert nexus._workflows == {}
        assert nexus._gateway is mock_gateway
        assert nexus._running is False

    @patch("nexus.core.create_gateway")
    def test_workflows_dictionary_management(self, mock_create_gateway):
        """Test workflows dictionary management."""
        mock_gateway = Mock()
        mock_gateway.register_workflow = Mock(return_value={"status": "registered"})
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # Register multiple workflows
        mock_workflow1 = Mock()
        mock_workflow2 = Mock()
        mock_workflow1.nodes = {}  # For _validate_workflow_sandbox
        mock_workflow1._node_instances = {}
        mock_workflow2.nodes = {}  # For _validate_workflow_sandbox
        mock_workflow2._node_instances = {}
        # Ensure they don't have build methods
        del mock_workflow1.build
        del mock_workflow2.build

        nexus.register("workflow1", mock_workflow1)
        nexus.register("workflow2", mock_workflow2)

        # Check workflows are stored correctly
        assert len(nexus._workflows) == 2
        assert "workflow1" in nexus._workflows
        assert "workflow2" in nexus._workflows
        assert nexus._workflows["workflow1"] == mock_workflow1
        assert nexus._workflows["workflow2"] == mock_workflow2


class TestNexusLogging:
    """Test logging functionality."""

    @patch("nexus.core.create_gateway")
    def test_initialization_logging(self, mock_create_gateway):
        """Test that initialization produces appropriate log messages."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        with patch("nexus.core.logger") as mock_logger:
            nexus = Nexus()

            # Check that info logs were called
            assert mock_logger.info.call_count >= 1

            # Check for specific log messages
            call_args_list = [call[0][0] for call in mock_logger.info.call_args_list]

            # Should contain initialization message
            assert any("Nexus initialized" in msg for msg in call_args_list)


class TestNexusMultipleInstances:
    """Test multiple Nexus instances (FastAPI-style)."""

    @patch("nexus.core.create_gateway")
    @patch("kailash.mcp_server.auth.APIKeyAuth")
    def test_multiple_independent_instances(self, mock_auth, mock_create_gateway):
        """Test that multiple Nexus instances are independent."""
        mock_gateway1 = Mock()
        mock_gateway2 = Mock()
        mock_create_gateway.side_effect = [mock_gateway1, mock_gateway2]
        mock_auth.return_value = Mock()

        # Create two instances with different configurations
        nexus1 = Nexus(api_port=8000, enable_auth=True)
        nexus2 = Nexus(api_port=9000, enable_monitoring=True)

        # Verify they are independent
        assert nexus1._api_port == 8000
        assert nexus2._api_port == 9000

        assert hasattr(nexus1, "_auth_enabled")
        assert not hasattr(nexus2, "_auth_enabled")
        assert not hasattr(nexus1, "_monitoring_enabled")
        assert hasattr(nexus2, "_monitoring_enabled")

        # Verify separate gateway instances
        assert nexus1._gateway == mock_gateway1
        assert nexus2._gateway == mock_gateway2

        # Verify separate workflow storage
        mock_workflow1 = Mock()
        mock_workflow2 = Mock()
        mock_workflow1.nodes = {}  # For _validate_workflow_sandbox
        mock_workflow1._node_instances = {}
        mock_workflow2.nodes = {}  # For _validate_workflow_sandbox
        mock_workflow2._node_instances = {}
        del mock_workflow1.build  # Prevent register() from calling .build()
        del mock_workflow2.build

        with patch.object(mock_gateway1, "register_workflow"):
            with patch.object(mock_gateway2, "register_workflow"):
                nexus1.register("workflow1", mock_workflow1)
                nexus2.register("workflow2", mock_workflow2)

        assert "workflow1" in nexus1._workflows
        assert "workflow1" not in nexus2._workflows
        assert "workflow2" in nexus2._workflows
        assert "workflow2" not in nexus1._workflows


class TestNexusAdvancedFeatures:
    """Test advanced Nexus features and edge cases."""

    @patch("nexus.core.create_gateway")
    def test_gateway_attribute_access(self, mock_create_gateway):
        """Test access to gateway attributes."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        nexus = Nexus()

        # Should be able to access gateway
        assert nexus._gateway == mock_gateway

    @patch("nexus.core.create_gateway")
    @patch("kailash.mcp_server.auth.APIKeyAuth")
    def test_boolean_configuration_flags(self, mock_auth, mock_create_gateway):
        """Test boolean configuration flags are properly handled."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway
        mock_auth.return_value = Mock()

        # Test all combinations of boolean flags
        nexus1 = Nexus(enable_auth=False, enable_monitoring=False, auto_discovery=False)
        nexus2 = Nexus(enable_auth=True, enable_monitoring=True, auto_discovery=True)

        # First instance should not have enterprise features
        assert not hasattr(nexus1, "_auth_enabled")
        assert not hasattr(nexus1, "_monitoring_enabled")
        assert nexus1._auto_discovery_enabled is False

        # Second instance should have enterprise features
        assert nexus2._auth_enabled is True
        assert nexus2._monitoring_enabled is True
        assert nexus2._auto_discovery_enabled is True


class TestNexusThreadSafety:
    """Test thread safety considerations."""

    @patch("nexus.core.create_gateway")
    def test_multiple_threads_initialization(self, mock_create_gateway):
        """Test that Nexus can be safely initialized from multiple threads."""
        mock_gateway = Mock()
        mock_create_gateway.return_value = mock_gateway

        results = {}
        errors = {}

        def create_nexus(thread_id):
            try:
                nexus = Nexus(api_port=8000 + thread_id)
                results[thread_id] = nexus
            except Exception as e:
                errors[thread_id] = e

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_nexus, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        assert len(errors) == 0
        assert len(results) == 5

        # Verify each instance has correct port
        for i in range(5):
            assert results[i]._api_port == 8000 + i
