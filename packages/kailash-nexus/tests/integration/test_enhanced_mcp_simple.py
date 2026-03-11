"""Simplified integration tests for enhanced MCP features.

Tests core MCP functionality without complex async fixture setup.
"""

import socket
import threading
import time
from contextlib import closing

import pytest
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


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


class TestNexusMCPIntegration:
    """Test Nexus MCP integration with real components."""

    def setup_method(self):
        """Set up test environment."""
        # Find free ports dynamically
        self.api_port = find_free_port(9300)
        self.mcp_port = find_free_port(self.api_port + 100)

        # Create Nexus instance
        self.app = Nexus(
            api_port=self.api_port,
            mcp_port=self.mcp_port,
            enable_auth=False,
            enable_monitoring=True,
        )

        # Register test workflows
        self._register_test_workflows()

        # Start server in background thread
        self.server_thread = threading.Thread(target=self.app.start, daemon=True)
        self.server_thread.start()

        # Wait for server to start with retry
        max_retries = 10
        for i in range(max_retries):
            try:
                with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                    s.settimeout(0.5)
                    s.connect(("localhost", self.api_port))
                    break
            except (ConnectionRefusedError, socket.timeout):
                if i == max_retries - 1:
                    pytest.fail(f"Server failed to start on port {self.api_port}")
                time.sleep(0.5)

    def teardown_method(self):
        """Clean up test environment."""
        if hasattr(self, "app"):
            try:
                self.app.stop()
                time.sleep(0.5)  # Allow time for cleanup
            except Exception:
                pass  # Ignore cleanup errors

    def _register_test_workflows(self):
        """Register test workflows."""
        # Echo workflow
        echo_workflow = WorkflowBuilder()
        echo_workflow.add_node(
            "PythonCodeNode",
            "echo",
            {"code": "result = {'echo': parameters.get('message', 'Hello')}"},
        )
        self.app.register("echo", echo_workflow.build())

        # Math workflow
        math_workflow = WorkflowBuilder()
        math_workflow.add_node(
            "PythonCodeNode",
            "math",
            {
                "code": """
a = parameters.get('a', 0)
b = parameters.get('b', 0)
result = {'sum': a + b, 'product': a * b}
"""
            },
        )
        self.app.register("math", math_workflow.build())

    def test_nexus_creates_mcp_server(self):
        """Test that Nexus creates an MCP server."""
        assert hasattr(self.app, "_mcp_server")
        assert self.app._mcp_server is not None

    def test_nexus_mcp_configuration(self):
        """Test MCP server configuration."""
        assert self.app._mcp_port == self.mcp_port
        assert self.app._enable_monitoring is True

    def test_workflows_registered(self):
        """Test that workflows are registered."""
        assert "echo" in self.app._workflows
        assert "math" in self.app._workflows

    def test_health_check_includes_workflows(self):
        """Test health check includes workflow information."""
        health = self.app.health_check()

        assert health["status"] == "healthy"
        assert health["workflows"] == 2
        assert health["api_port"] == self.api_port
        assert health["enterprise_features"]["multi_channel"] is True

    def test_channel_status(self):
        """Test channel status reporting."""
        status = self.app.get_channel_status()

        assert "api" in status
        assert "cli" in status
        assert "mcp" in status

        # Check MCP channel specifically
        mcp_status = status["mcp"]
        assert "status" in mcp_status
        assert "capability" in mcp_status
        assert "AI agent tools" in mcp_status["capability"]

    def test_performance_metrics(self):
        """Test performance metrics tracking."""
        metrics = self.app.get_performance_metrics()

        # Should have workflow registration metrics
        assert "workflow_registration_time" in metrics
        reg_metrics = metrics["workflow_registration_time"]
        assert reg_metrics["count"] >= 2  # We registered 2 workflows
        assert reg_metrics["average"] > 0

    def test_session_creation(self):
        """Test cross-channel session creation."""
        session_id = self.app.create_session(channel="api")

        assert session_id is not None
        assert isinstance(session_id, str)

        # Check session sync metrics
        metrics = self.app.get_performance_metrics()
        assert "session_sync_latency" in metrics
        assert metrics["session_sync_latency"]["count"] >= 1

    def test_event_broadcasting(self):
        """Test event broadcasting capability."""
        event = self.app.broadcast_event(
            "WORKFLOW_STARTED", {"workflow": "echo", "session": "test-123"}
        )

        assert event["type"] == "WORKFLOW_STARTED"
        assert event["data"]["workflow"] == "echo"
        assert "timestamp" in event
        assert "id" in event


class TestNexusResourceManager:
    """Test Nexus resource management functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.app = Nexus(api_port=8890, mcp_port=3890)

        # Create mock workflow for testing
        workflow_builder = WorkflowBuilder()
        workflow_builder.add_node(
            "PythonCodeNode", "test", {"code": "result = {'test': True}"}
        )

        # Build workflow and then set metadata on the built workflow
        workflow = workflow_builder.build()
        workflow.metadata = {
            "description": "Test workflow",
            "parameters": {"input": {"type": "string", "required": True}},
        }
        self.app.register("test_workflow", workflow)

    def test_has_resource_manager(self):
        """Test that resource manager is available."""
        # When Phase 2 is implemented, resource manager should be created
        # For now, we test that the infrastructure is ready
        assert hasattr(self.app, "_mcp_server")

        # Check if we're using enhanced or simple server
        if hasattr(self.app, "_mcp_channel") and self.app._mcp_channel:
            # Enhanced server with channel
            assert self.app._mcp_channel is not None
        else:
            # Simple server fallback
            assert self.app._mcp_server is not None

    def test_workflow_metadata_available(self):
        """Test that workflow metadata is accessible."""
        workflow = self.app._workflows.get("test_workflow")
        assert workflow is not None
        assert hasattr(workflow, "metadata")
        assert workflow.metadata["description"] == "Test workflow"
        assert "parameters" in workflow.metadata


class TestNexusAuthIntegration:
    """Test Nexus authentication integration."""

    def test_auth_disabled_by_default(self):
        """Test that auth is disabled by default."""
        app = Nexus()
        assert app._enable_auth is False

    def test_auth_enabled_configuration(self):
        """Test creating Nexus with auth enabled."""
        import os

        # Set test API key
        os.environ["NEXUS_API_KEY_TESTUSER"] = "test-key-12345"

        try:
            app = Nexus(enable_auth=True)

            assert app._enable_auth is True

            # Check API keys loaded
            keys = app._get_api_keys()
            assert "testuser" in keys
            assert keys["testuser"] == "test-key-12345"

        finally:
            del os.environ["NEXUS_API_KEY_TESTUSER"]

    def test_production_mode_no_default_keys(self):
        """Test that production mode has no default keys."""
        import os

        os.environ["NEXUS_PRODUCTION"] = "1"

        try:
            app = Nexus()
            keys = app._get_api_keys()
            assert keys == {}  # No default keys in production

        finally:
            del os.environ["NEXUS_PRODUCTION"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
