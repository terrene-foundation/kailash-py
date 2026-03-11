"""Integration tests for Nexus components.

Tests that the core, discovery, plugins, and channels work together
as expected in a real-world scenario.
"""

import os
import socket
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


def find_free_port(start_port: int = 8000) -> int:
    """Find a free port starting from start_port."""
    for port in range(start_port, start_port + 100):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("", port))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find free port starting from {start_port}")


class TestNexusIntegration:
    """Test integration of Nexus components."""

    def setup_method(self):
        """Reset global state before each test."""
        # Reset global nexus instance
        import nexus.core

        nexus.core._nexus_instance = None

        # Reset global plugin registry
        import nexus.plugins

        nexus.plugins._registry = None

        # Reset global channel manager
        import nexus.channels

        nexus.channels._channel_manager = None

    def test_zero_config_startup(self):
        """Test that nexus starts with zero configuration."""
        from nexus import Nexus

        # Mock gateway creation to avoid actual server startup
        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.run = Mock()  # Changed from start to run
            mock_gateway.return_value = mock_gw

            # Get nexus instance with dynamic port
            n = Nexus(api_port=find_free_port(8010))

            # Should be initialized
            assert n is not None
            assert hasattr(n, "start")
            assert hasattr(n, "register")
            assert hasattr(n, "stop")

            # Start should work
            n.start()
            assert n._running is True

    def test_workflow_discovery_integration(self):
        """Test workflow discovery integrates with nexus."""
        from nexus import Nexus

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a workflow file
            workflow_file = Path(tmpdir) / "test.workflow.py"
            workflow_file.write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "agent", {"url": "https://example.com"})
"""
            )

            # Change to temp directory
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            try:
                with patch("nexus.core.create_gateway") as mock_gateway:
                    mock_gateway.return_value = Mock()

                    n = Nexus(api_port=find_free_port(8011), auto_discovery=True)
                    n.start()

                    # Should have discovered the workflow
                    assert len(n._workflows) >= 1
                    assert any("test" in name for name in n._workflows.keys())
            finally:
                os.chdir(original_cwd)

    def test_plugin_application_integration(self):
        """Test plugins can be applied to nexus."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gateway.return_value = Mock()

            n = Nexus(api_port=find_free_port(8012))

            # Apply plugins
            n.enable_auth().enable_monitoring()

            # Should have applied plugins
            assert hasattr(n, "_auth_enabled")
            assert n._auth_enabled is True
            assert hasattr(n, "_monitoring_enabled")
            assert n._monitoring_enabled is True

    def test_channel_configuration_integration(self):
        """Test channels are configured with nexus."""
        from nexus import Nexus
        from nexus.channels import get_channel_manager

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gateway.return_value = Mock()

            n = Nexus(api_port=find_free_port(8013))

            # Channels should be configured
            manager = get_channel_manager()
            status = manager._get_channel_status()

            assert status["api"] is True
            assert status["cli"] is True
            assert status["mcp"] is True

    def test_workflow_registration_across_channels(self):
        """Test workflow registration works across all channels."""
        from nexus import Nexus

        from kailash.workflow.builder import WorkflowBuilder

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.register_workflow = Mock()
            mock_gateway.return_value = mock_gw

            n = Nexus(api_port=find_free_port(8014))

            # Create and register workflow
            builder = WorkflowBuilder()
            builder.add_node("HTTPRequestNode", "agent", {"url": "https://example.com"})

            n.register("test-workflow", builder)
            n.start()

            # Should have registered with gateway
            assert "test-workflow" in n._workflows

    def test_health_check_integration(self):
        """Test health check reports correct status."""
        from nexus import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gateway.return_value = Mock()

            n = Nexus(api_port=find_free_port(8015))

            # Check health before start
            health = n.health_check()
            assert health["status"] == "stopped"

            # Start and check health
            n.start()
            health = n.health_check()
            assert health["status"] == "healthy"
            assert health["workflows"] == 0  # No workflows registered
            assert health["platform_type"] == "zero-config-workflow"
            assert health["server_type"] == "enterprise"

    def test_complete_user_flow(self):
        """Test complete user flow from zero to running workflows."""
        from nexus import Nexus

        from kailash.workflow.builder import WorkflowBuilder

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gw = Mock()
            mock_gw.run = Mock()
            mock_gw.register_workflow = Mock()
            mock_gateway.return_value = mock_gw

            # 1. User imports and creates nexus
            n = Nexus(api_port=find_free_port(8016))

            # 2. User creates a workflow
            builder = WorkflowBuilder()
            builder.add_node("HTTPRequestNode", "agent", {"url": "https://example.com"})

            # 3. User registers workflow
            n.register("hello-world", builder)

            # 4. User enables auth (optional)
            n.enable_auth()

            # 5. User starts nexus
            n.start()

            # Verify everything is working
            assert n._running is True
            assert "hello-world" in n._workflows
            assert n._auth_enabled is True

            # 6. User checks health
            health = n.health_check()
            assert health["status"] == "healthy"
            assert health["workflows"] == 1

            # 7. User stops nexus
            n.stop()
            assert n._running is False
