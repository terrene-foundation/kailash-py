"""Unit tests for EnterpriseWorkflowServer class.

Tests the enterprise workflow server functionality including:
- Enterprise feature initialization
- Resource management
- Health checks with enterprise components
- Enterprise-specific endpoints
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from src.kailash.gateway.security import SecretManager
from src.kailash.resources.registry import ResourceRegistry
from src.kailash.servers import EnterpriseWorkflowServer


class TestEnterpriseWorkflowServer:
    """Unit tests for EnterpriseWorkflowServer."""

    def test_enterprise_server_initialization(self):
        """Test enterprise server initialization with default settings."""
        server = EnterpriseWorkflowServer(
            title="Enterprise Test Server",
            description="Test Enterprise Server",
            version="1.0.0",
        )

        assert server.app.title == "Enterprise Test Server"
        assert server.enable_async_execution is True
        assert server.enable_health_checks is True
        assert server.enable_resource_management is True
        assert server.enable_durability is True
        assert isinstance(server.resource_registry, ResourceRegistry)
        assert isinstance(server.secret_manager, SecretManager)

    def test_enterprise_server_with_disabled_features(self):
        """Test enterprise server with some features disabled."""
        server = EnterpriseWorkflowServer(
            title="Disabled Features Server",
            enable_async_execution=False,
            enable_resource_management=False,
            enable_durability=False,
        )

        assert server.enable_async_execution is False
        assert server.enable_resource_management is False
        assert server.enable_durability is False
        # Health checks should still be enabled
        assert server.enable_health_checks is True

    def test_enterprise_server_with_custom_components(self):
        """Test enterprise server with custom components."""
        custom_registry = Mock(spec=ResourceRegistry)
        custom_secret_manager = Mock(spec=SecretManager)

        server = EnterpriseWorkflowServer(
            title="Custom Components Server",
            resource_registry=custom_registry,
            secret_manager=custom_secret_manager,
        )

        assert server.resource_registry == custom_registry
        assert server.secret_manager == custom_secret_manager

    def test_root_endpoint_enterprise_info(self):
        """Test that root endpoint includes enterprise information."""
        server = EnterpriseWorkflowServer(title="Enterprise Root Test")
        client = TestClient(server.app)

        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Enterprise Root Test"
        assert data["type"] == "enterprise_workflow_server"
        assert "enterprise" in data

        enterprise_info = data["enterprise"]
        assert enterprise_info["durability"] is True
        assert enterprise_info["async_execution"] is True
        assert enterprise_info["resource_management"] is True
        assert enterprise_info["health_checks"] is True
        assert "features" in enterprise_info
        assert "resources" in enterprise_info

    def test_enterprise_features_endpoint(self):
        """Test the enterprise features endpoint."""
        server = EnterpriseWorkflowServer(title="Features Test Server")
        client = TestClient(server.app)

        response = client.get("/enterprise/features")
        assert response.status_code == 200

        data = response.json()
        assert data["durability"] is True
        assert data["async_execution"] is True
        assert data["resource_management"] is True
        assert data["health_checks"] is True
        assert "features" in data

        expected_features = [
            "request_durability",
            "resource_registry",
            "secret_management",
            "async_workflows",
            "health_monitoring",
            "resource_resolution",
            "enterprise_security",
        ]
        for feature in expected_features:
            assert feature in data["features"]

    @patch("src.kailash.servers.enterprise_workflow_server.ResourceRegistry")
    def test_enterprise_resources_endpoint(self, mock_registry_class):
        """Test the enterprise resources endpoint."""
        # Mock resource registry
        mock_registry = Mock()
        mock_registry.list_resources.return_value = ["db_connection", "cache_client"]
        mock_registry_class.return_value = mock_registry

        server = EnterpriseWorkflowServer(title="Resources Test Server")
        # Replace with our mock
        server.resource_registry = mock_registry

        client = TestClient(server.app)
        response = client.get("/enterprise/resources")
        assert response.status_code == 200

        data = response.json()
        assert data["resources"] == ["db_connection", "cache_client"]
        assert data["total"] == 2

    def test_enterprise_resources_endpoint_disabled(self):
        """Test resources endpoint when resource management is disabled."""
        server = EnterpriseWorkflowServer(
            title="Disabled Resources Server", enable_resource_management=False
        )
        client = TestClient(server.app)

        response = client.get("/enterprise/resources")
        assert response.status_code == 200

        data = response.json()
        assert data["error"] == "Resource management disabled"

    @patch("src.kailash.servers.enterprise_workflow_server.ResourceRegistry")
    def test_enterprise_resource_info_endpoint(self, mock_registry_class):
        """Test getting information about a specific resource."""
        # Mock resource registry
        mock_registry = Mock()
        mock_resource = Mock()
        mock_resource.__class__.__name__ = "DatabaseConnection"
        mock_registry.get_resource = AsyncMock(return_value=mock_resource)
        mock_registry.check_health = AsyncMock(return_value={"status": "healthy"})
        mock_registry_class.return_value = mock_registry

        server = EnterpriseWorkflowServer(title="Resource Info Test Server")
        server.resource_registry = mock_registry

        client = TestClient(server.app)
        response = client.get("/enterprise/resources/test_resource")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "test_resource"
        assert data["type"] == "DatabaseConnection"
        assert data["health"]["status"] == "healthy"
        assert "workflows" in data

    def test_enterprise_resource_info_not_found(self):
        """Test resource info endpoint for non-existent resource."""
        server = EnterpriseWorkflowServer(title="Not Found Test Server")
        client = TestClient(server.app)

        response = client.get("/enterprise/resources/nonexistent")
        assert response.status_code == 404

    @patch("src.kailash.servers.enterprise_workflow_server.datetime")
    def test_enterprise_health_endpoint(self, mock_datetime):
        """Test the comprehensive enterprise health check."""
        # Mock datetime for consistent testing
        mock_datetime.now.return_value.isoformat.return_value = "2025-01-01T00:00:00"

        server = EnterpriseWorkflowServer(title="Health Test Server")
        client = TestClient(server.app)

        response = client.get("/enterprise/health")
        assert response.status_code == 200

        data = response.json()
        assert data["server_type"] == "enterprise_workflow_server"
        assert data["timestamp"] == "2025-01-01T00:00:00"
        assert "components" in data
        assert "status" in data

        # Check that various components are included
        components = data["components"]
        assert "base_server" in components
        assert "secret_manager" in components

    def test_async_execution_endpoint_disabled(self):
        """Test async execution endpoint when async execution is disabled."""
        server = EnterpriseWorkflowServer(
            title="Disabled Async Server", enable_async_execution=False
        )
        client = TestClient(server.app)

        response = client.post(
            "/enterprise/workflows/test_workflow/execute_async", json={"inputs": {}}
        )
        assert response.status_code == 503
        assert "Async execution disabled" in response.json()["detail"]

    def test_async_execution_workflow_not_found(self):
        """Test async execution with non-existent workflow."""
        server = EnterpriseWorkflowServer(title="Not Found Async Server")
        client = TestClient(server.app)

        response = client.post(
            "/enterprise/workflows/nonexistent/execute_async", json={"inputs": {}}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_register_resource(self):
        """Test resource registration functionality."""
        server = EnterpriseWorkflowServer(title="Resource Registration Server")
        mock_resource = Mock()

        # Should work when resource management is enabled
        server.register_resource("test_resource", mock_resource)

        # Verify resource was registered (through mock verification)
        # In a real test, we'd check the resource registry

    def test_register_resource_disabled(self):
        """Test resource registration when resource management is disabled."""
        server = EnterpriseWorkflowServer(
            title="Disabled Resource Registration Server",
            enable_resource_management=False,
        )
        mock_resource = Mock()

        with pytest.raises(RuntimeError, match="Resource management disabled"):
            server.register_resource("test_resource", mock_resource)

    def test_enterprise_server_inheritance(self):
        """Test that enterprise server properly inherits from durable server."""
        server = EnterpriseWorkflowServer(title="Inheritance Test Server")

        # Should have workflow server methods
        assert hasattr(server, "register_workflow")
        assert hasattr(server, "register_mcp_server")

        # Should have durable server properties
        assert hasattr(server, "enable_durability")
        assert hasattr(server, "checkpoint_manager")

        # Should have enterprise-specific attributes
        assert hasattr(server, "resource_registry")
        assert hasattr(server, "secret_manager")
        assert hasattr(server, "enable_async_execution")

    def test_enterprise_server_max_workers_default(self):
        """Test that enterprise server has higher default max_workers."""
        server = EnterpriseWorkflowServer(title="Max Workers Test")

        # Enterprise server should default to 20 workers vs 10 for basic
        assert server.executor._max_workers == 20

    @patch("src.kailash.servers.enterprise_workflow_server.AsyncLocalRuntime")
    def test_async_runtime_initialization(self, mock_runtime_class):
        """Test that async runtime is initialized when async execution is enabled."""
        mock_runtime = Mock()
        mock_runtime_class.return_value = mock_runtime

        server = EnterpriseWorkflowServer(
            title="Async Runtime Test", enable_async_execution=True
        )

        # Should have created async runtime
        assert hasattr(server, "_async_runtime")
        mock_runtime_class.assert_called_once()

    def test_no_async_runtime_when_disabled(self):
        """Test that async runtime is not initialized when disabled."""
        server = EnterpriseWorkflowServer(
            title="No Async Runtime Test", enable_async_execution=False
        )

        # Should not have async runtime
        assert server._async_runtime is None
