"""
Comprehensive Core Tests for Missing Coverage

Tests the specific functionality that's missing from core.py coverage
to push it over 80% threshold.
"""

import os
import sys
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))


class TestNexusLifecycle:
    """Test Nexus start/stop lifecycle methods."""

    def test_start_method(self):
        """Test the start() method."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.run = Mock()
            mock_gateway.return_value = mock_gw

            app = Nexus()

            # Test start
            app.start()

            # Verify run was called (not start - see core.py line 232)
            mock_gw.run.assert_called_once_with(host="0.0.0.0", port=8000)
            assert app._running is True

    def test_stop_method(self):
        """Test the stop() method.

        Note: Gateway shutdown is handled by FastAPI's lifespan context manager,
        not by calling .stop() on the gateway. This test verifies that stop()
        sets the _running flag to False without errors.
        """
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.start = Mock()
            # No .stop() mock needed - FastAPI handles shutdown via lifespan
            mock_gateway.return_value = mock_gw

            app = Nexus()
            app.start()

            # Test stop - should complete without AttributeError
            app.stop()

            # Verify _running flag is set to False
            assert app._running is False
            # Gateway shutdown is handled by FastAPI lifespan, not .stop() call

    def test_multiple_starts(self):
        """Test that multiple start calls are handled gracefully."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.run = Mock()
            mock_gateway.return_value = mock_gw

            app = Nexus()

            # Start multiple times
            app.start()
            app.start()
            app.start()

            # Should only call gateway run once (due to _running flag check)
            mock_gw.run.assert_called_once_with(host="0.0.0.0", port=8000)

    def test_stop_without_start(self):
        """Test stop() when not started."""
        from nexus import Nexus

        app = Nexus()

        # Should not crash
        app.stop()
        assert app._running is False


class TestNexusErrorHandling:
    """Test error handling in Nexus initialization and operations."""

    def test_gateway_initialization_failure(self):
        """Test that gateway initialization failure raises error (no fallback)."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            # Enterprise gateway fails - should raise error, no fallback
            mock_gateway.side_effect = Exception("Enterprise failed")

            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="Nexus requires enterprise gateway"):
                app = Nexus()

            # Should only call create_gateway once (no fallback)
            assert mock_gateway.call_count == 1

    def test_complete_gateway_failure(self):
        """Test enterprise gateway failure raises error (no fallback)."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            # Enterprise gateway fails
            mock_gateway.side_effect = Exception("Enterprise failed")

            # Should raise RuntimeError, no fallback attempted
            with pytest.raises(RuntimeError, match="Nexus requires enterprise gateway"):
                app = Nexus()

            # Should only call create_gateway once
            assert mock_gateway.call_count == 1

    def test_start_failure_handling(self):
        """Test handling when gateway run fails (v1.0.8: runs in main thread)."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.run = Mock(side_effect=Exception("Start failed"))
            mock_gateway.return_value = mock_gw

            app = Nexus()

            # v1.0.8: start() runs gateway in main thread, so exception is raised immediately
            with pytest.raises(RuntimeError, match="Nexus failed: Start failed"):
                app.start()

            # App should be stopped after exception (cleanup in except block)
            assert app._running is False

    def test_stop_failure_handling(self):
        """Test handling when gateway stop fails."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.run = Mock()
            mock_gw.stop = Mock(side_effect=Exception("Stop failed"))
            mock_gateway.return_value = mock_gw

            app = Nexus()
            app.start()

            # Stop failure should be handled gracefully (no exception raised)
            app.stop()

            # Should be stopped despite gateway stop failure
            assert app._running is False


class TestNexusConfigurationMethods:
    """Test Nexus configuration and attribute methods."""

    def test_enable_auth_method(self):
        """Test enable_auth() method."""
        from nexus import Nexus

        app = Nexus()
        result = app.enable_auth()

        # Should return self for chaining
        assert result is app

        # Should update auth configuration
        assert app._auth_enabled is True

    def test_enable_monitoring_method(self):
        """Test enable_monitoring() method."""
        from nexus import Nexus

        app = Nexus()
        result = app.enable_monitoring()

        # Should return self for chaining
        assert result is app

        # Should update monitoring configuration
        assert app._monitoring_enabled is True

    def test_use_plugin_method(self):
        """Test use_plugin() method."""
        from nexus import Nexus

        with patch("nexus.plugins.get_plugin_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_get_registry.return_value = mock_registry
            mock_registry.apply = Mock()

            app = Nexus()

            # Test with string plugin name
            result = app.use_plugin("test-plugin")

            # Should call registry.apply with plugin name and self
            mock_registry.apply.assert_called_once_with("test-plugin", app)

            # Should return self for chaining
            assert result is app


class TestNexusSessionMethods:
    """Test session creation and synchronization methods."""

    def test_create_session(self):
        """Test create_session() method."""
        from nexus import Nexus

        app = Nexus()

        session_id = app.create_session(channel="api")

        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    def test_sync_session(self):
        """Test sync_session() method."""
        from nexus import Nexus

        app = Nexus()

        # Create a session first
        session_id = app.create_session(channel="api")

        # Sync to different channel
        result = app.sync_session(session_id, "cli")

        assert result is not None
        assert "id" in result
        assert result["id"] == session_id
        assert "channels" in result

    def test_sync_session_invalid_id(self):
        """Test sync_session() with invalid session ID."""
        from nexus import Nexus

        app = Nexus()

        # Try to sync non-existent session
        result = app.sync_session("invalid_session", "cli")

        assert "error" in result

    def test_broadcast_event(self):
        """Test broadcast_event() method."""
        from nexus import Nexus

        app = Nexus()

        event = app.broadcast_event(
            event_type="TEST_EVENT", data={"key": "value"}, session_id="test_session"
        )

        assert event is not None
        assert event["type"] == "TEST_EVENT"
        assert event["data"]["key"] == "value"
        assert event["session_id"] == "test_session"
        assert "id" in event
        assert "timestamp" in event


class TestNexusPerformanceMetrics:
    """Test performance metrics tracking."""

    def test_get_performance_metrics(self):
        """Test get_performance_metrics() method."""
        from nexus import Nexus

        app = Nexus()

        metrics = app.get_performance_metrics()

        assert isinstance(metrics, dict)

        # Check expected metric categories
        expected_metrics = [
            "workflow_registration_time",
            "cross_channel_sync_time",
            "failure_recovery_time",
            "session_sync_latency",
        ]

        for metric in expected_metrics:
            assert metric in metrics
            assert "average" in metrics[metric]
            assert "latest" in metrics[metric]
            assert "count" in metrics[metric]
            assert "target_met" in metrics[metric]

    def test_check_performance_target(self):
        """Test _check_performance_target() method."""
        from nexus import Nexus

        app = Nexus()

        # Test workflow registration time targets
        assert app._check_performance_target("workflow_registration_time", 0.5) is True
        assert app._check_performance_target("workflow_registration_time", 1.5) is False

        # Test cross-channel sync time targets
        assert app._check_performance_target("cross_channel_sync_time", 0.02) is True
        assert app._check_performance_target("cross_channel_sync_time", 0.1) is False

    def test_track_performance_metrics(self):
        """Test that performance metrics are tracked during operations."""
        from nexus import Nexus

        from kailash.workflow.builder import WorkflowBuilder

        app = Nexus()

        # Create test workflow
        workflow = WorkflowBuilder()
        workflow.add_node("HTTPRequestNode", "test", {"url": "https://example.com"})

        # Registration should track performance
        start_time = time.time()
        app.register("test_workflow", workflow)

        # Check that metrics were recorded
        metrics = app.get_performance_metrics()
        assert metrics["workflow_registration_time"]["count"] > 0


class TestNexusChannelMethods:
    """Test channel-related methods."""

    def test_get_channel_status(self):
        """Test get_channel_status() method."""
        from nexus import Nexus

        app = Nexus()

        status = app.get_channel_status()

        assert isinstance(status, dict)
        assert "api" in status
        assert "cli" in status
        assert "mcp" in status

        for channel, data in status.items():
            assert "status" in data
            assert "registered_workflows" in data
            assert "capability" in data

    def test_register_multi_channel(self):
        """Test workflow registration with enterprise gateway."""
        from nexus import Nexus

        from kailash.workflow.builder import WorkflowBuilder

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.register_workflow = Mock()
            mock_gateway.return_value = mock_gw

            app = Nexus()

            # Create test workflow
            workflow = WorkflowBuilder()
            workflow.add_node("HTTPRequestNode", "test", {"url": "https://example.com"})

            # Register workflow - should call enterprise gateway
            app.register("test_workflow", workflow.build())

            # Verify enterprise gateway was called
            mock_gw.register_workflow.assert_called_once()
            call_args = mock_gw.register_workflow.call_args
            assert call_args[0][0] == "test_workflow"


class TestNexusWorkflowHandling:
    """Test workflow registration and handling."""

    def test_register_with_builder(self):
        """Test registering WorkflowBuilder vs Workflow."""
        from nexus import Nexus

        from kailash.workflow.builder import WorkflowBuilder

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.register_workflow = Mock()
            mock_gateway.return_value = mock_gw

            app = Nexus()

            # Test with WorkflowBuilder
            builder = WorkflowBuilder()
            builder.add_node("HTTPRequestNode", "test", {"url": "https://example.com"})

            app.register("builder_workflow", builder)

            # Should convert to Workflow and store
            assert "builder_workflow" in app._workflows
            # Should not be the builder itself
            assert app._workflows["builder_workflow"] is not builder

            # Should register with enterprise gateway
            mock_gw.register_workflow.assert_called_once()

    def test_register_invalid_workflow(self):
        """Test registration with invalid workflow raises error."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.register_workflow = Mock()
            mock_gateway.return_value = mock_gw

            app = Nexus()

            # Invalid workflow should cause error when registering with gateway
            mock_gw.register_workflow.side_effect = Exception("Invalid workflow")

            with pytest.raises(Exception, match="Invalid workflow"):
                app.register("invalid_workflow", None)

    def test_register_duplicate_name(self):
        """Test registration with duplicate name fails in enterprise gateway."""
        from nexus import Nexus

        from kailash.workflow.builder import WorkflowBuilder

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.register_workflow = Mock()
            mock_gateway.return_value = mock_gw

            app = Nexus()

            # Create two workflows
            workflow1 = WorkflowBuilder()
            workflow1.add_node(
                "HTTPRequestNode", "test1", {"url": "https://example1.com"}
            )

            workflow2 = WorkflowBuilder()
            workflow2.add_node(
                "HTTPRequestNode", "test2", {"url": "https://example2.com"}
            )

            # Register first workflow
            app.register("duplicate", workflow1)

            # Second registration should fail in enterprise gateway
            mock_gw.register_workflow.side_effect = Exception("Workflow already exists")

            with pytest.raises(Exception, match="Workflow already exists"):
                app.register("duplicate", workflow2)


class TestNexusEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_workflow_name(self):
        """Test registration with empty name."""
        from nexus import Nexus

        from kailash.workflow.builder import WorkflowBuilder

        app = Nexus()
        workflow = WorkflowBuilder()
        workflow.add_node("HTTPRequestNode", "test", {"url": "https://example.com"})

        # Empty name is allowed - stored like any other name
        app.register("", workflow)

        # Workflow is registered with empty string as key
        assert "" in app._workflows

    def test_very_long_workflow_name(self):
        """Test registration with very long name."""
        from nexus import Nexus

        from kailash.workflow.builder import WorkflowBuilder

        app = Nexus()
        workflow = WorkflowBuilder()
        workflow.add_node("HTTPRequestNode", "test", {"url": "https://example.com"})

        # Very long name
        long_name = "a" * 1000

        # Should handle gracefully
        app.register(long_name, workflow)
        assert long_name in app._workflows

    def test_special_characters_in_name(self):
        """Test registration with special characters."""
        from nexus import Nexus

        from kailash.workflow.builder import WorkflowBuilder

        app = Nexus()
        workflow = WorkflowBuilder()
        workflow.add_node("HTTPRequestNode", "test", {"url": "https://example.com"})

        # Special characters
        special_name = "test-workflow_123!@#$%^&*()"

        # Should handle special characters
        app.register(special_name, workflow)
        assert special_name in app._workflows

    def test_health_check_when_not_started(self):
        """Test health_check() when Nexus is not started."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gateway.return_value = mock_gw

            app = Nexus()

            health = app.health_check()

            assert health is not None
            assert health["status"] == "stopped"
            assert health["platform_type"] == "zero-config-workflow"
            assert health["server_type"] == "enterprise"

    def test_health_check_when_started(self):
        """Test health_check() when Nexus is started."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.run = Mock()  # Changed from start to run
            mock_gateway.return_value = mock_gw

            app = Nexus()
            app.start()

            health = app.health_check()

            assert health is not None
            assert health["status"] == "healthy"
            assert health["platform_type"] == "zero-config-workflow"
            assert health["server_type"] == "enterprise"


class TestNexusConstructorOptions:
    """Test constructor options and edge cases."""

    def test_invalid_port_values(self):
        """Test port configurations - constructor accepts any int values."""
        from nexus import Nexus

        # Constructor accepts any integer values without validation
        # Validation happens later when trying to bind
        app1 = Nexus(api_port=-1)
        assert app1._api_port == -1

        app2 = Nexus(api_port=100000)
        assert app2._api_port == 100000

        # String port would be accepted too (Python doesn't enforce type hints)
        app3 = Nexus(api_port="8000")
        assert app3._api_port == "8000"

    def test_conflicting_ports(self):
        """Test conflicting port configurations."""
        from nexus import Nexus

        # Same port for API and MCP is allowed by constructor
        # Conflict detection happens at runtime when binding
        app = Nexus(api_port=8000, mcp_port=8000)
        assert app._api_port == 8000
        assert app._mcp_port == 8000

    def test_extreme_rate_limits(self):
        """Test extreme rate limit values."""
        from nexus import Nexus

        # Very high rate limit
        app = Nexus(rate_limit=1000000)
        assert app._rate_limit == 1000000

        # Zero rate limit - _rate_limit is always set (stores value for endpoint decorator)
        app = Nexus(rate_limit=0)
        assert app._rate_limit == 0

        # Negative rate limit - accepted by constructor (no validation)
        app = Nexus(rate_limit=-1)
        assert app._rate_limit == -1
