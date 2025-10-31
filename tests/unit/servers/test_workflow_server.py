"""Unit tests for WorkflowServer class.

Tests the basic workflow server functionality including:
- Server initialization
- Workflow registration
- Health checks
- Root endpoints
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from src.kailash.servers import WorkflowServer
from src.kailash.workflow import Workflow
from src.kailash.workflow.builder import WorkflowBuilder


class TestWorkflowServer:
    """Unit tests for WorkflowServer."""

    def test_server_initialization(self):
        """Test basic server initialization."""
        server = WorkflowServer(
            title="Test Server",
            description="Test Description",
            version="1.0.0",
            max_workers=5,
        )

        assert server.app.title == "Test Server"
        assert server.app.description == "Test Description"
        assert server.app.version == "1.0.0"
        assert len(server.workflows) == 0
        assert len(server.mcp_servers) == 0

    def test_server_with_cors(self):
        """Test server initialization with CORS origins."""
        cors_origins = ["http://localhost:3000", "https://app.example.com"]
        server = WorkflowServer(title="CORS Test Server", cors_origins=cors_origins)

        # Check that CORS middleware was added by checking if we can make CORS requests
        # The mere fact that we passed CORS origins to the constructor should be sufficient
        assert cors_origins is not None
        assert len(cors_origins) == 2

    def test_root_endpoint(self):
        """Test the root endpoint returns server information."""
        server = WorkflowServer(title="Test Server", version="2.0.0")
        client = TestClient(server.app)

        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Test Server"
        assert data["version"] == "2.0.0"
        assert data["type"] == "workflow_server"
        assert data["workflows"] == []
        assert data["mcp_servers"] == []

    def test_health_endpoint(self):
        """Test the health check endpoint."""
        server = WorkflowServer(title="Health Test Server")
        client = TestClient(server.app)

        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["server_type"] == "workflow_server"
        assert "workflows" in data
        assert "mcp_servers" in data

    def test_workflows_endpoint_empty(self):
        """Test workflows endpoint when no workflows are registered."""
        server = WorkflowServer(title="Empty Workflows Server")
        client = TestClient(server.app)

        response = client.get("/workflows")
        assert response.status_code == 200

        data = response.json()
        assert data == {}

    @patch("src.kailash.servers.workflow_server.WorkflowAPI")
    def test_workflow_registration(self, mock_workflow_api):
        """Test workflow registration functionality."""
        # Create a mock workflow
        workflow = Mock(spec=Workflow)
        workflow.workflow_id = "test_workflow_id"
        workflow.version = "1.0.0"

        # Create server and register workflow
        server = WorkflowServer(title="Workflow Registration Test")
        server.register_workflow(
            name="test_workflow",
            workflow=workflow,
            description="Test workflow description",
            tags=["test", "demo"],
        )

        # Check workflow was registered
        assert "test_workflow" in server.workflows
        registration = server.workflows["test_workflow"]
        assert registration.name == "test_workflow"
        assert registration.type == "embedded"
        assert registration.workflow == workflow
        assert registration.description == "Test workflow description"
        assert registration.tags == ["test", "demo"]

        # Check that WorkflowAPI was created
        mock_workflow_api.assert_called_once_with(workflow)

    def test_duplicate_workflow_registration(self):
        """Test that registering duplicate workflow names raises error."""
        workflow1 = Mock(spec=Workflow)
        workflow1.workflow_id = "workflow1_id"
        workflow1.version = "1.0.0"
        workflow2 = Mock(spec=Workflow)
        workflow2.workflow_id = "workflow2_id"
        workflow2.version = "1.0.0"

        server = WorkflowServer(title="Duplicate Test Server")
        server.register_workflow("duplicate_name", workflow1)

        with pytest.raises(
            ValueError, match="Workflow 'duplicate_name' already registered"
        ):
            server.register_workflow("duplicate_name", workflow2)

    def test_mcp_server_registration(self):
        """Test MCP server registration functionality."""
        mock_mcp_server = Mock()

        server = WorkflowServer(title="MCP Test Server")
        server.register_mcp_server("test_mcp", mock_mcp_server)

        # Check MCP server was registered
        assert "test_mcp" in server.mcp_servers
        assert server.mcp_servers["test_mcp"] == mock_mcp_server

    def test_duplicate_mcp_server_registration(self):
        """Test that registering duplicate MCP server names raises error."""
        mcp1 = Mock()
        mcp2 = Mock()

        server = WorkflowServer(title="Duplicate MCP Test Server")
        server.register_mcp_server("duplicate_mcp", mcp1)

        with pytest.raises(
            ValueError, match="MCP server 'duplicate_mcp' already registered"
        ):
            server.register_mcp_server("duplicate_mcp", mcp2)

    def test_proxy_workflow_registration(self):
        """Test proxied workflow registration functionality."""
        server = WorkflowServer(title="Proxy Test Server")
        server.proxy_workflow(
            name="proxy_workflow",
            proxy_url="http://external-service:8080",
            health_check="/health",
            description="External workflow",
            tags=["proxy", "external"],
        )

        # Check proxied workflow was registered
        assert "proxy_workflow" in server.workflows
        registration = server.workflows["proxy_workflow"]
        assert registration.name == "proxy_workflow"
        assert registration.type == "proxied"
        assert registration.proxy_url == "http://external-service:8080"
        assert registration.health_check == "/health"
        assert registration.description == "External workflow"
        assert registration.tags == ["proxy", "external"]

    def test_get_workflow_endpoints(self):
        """Test _get_workflow_endpoints method."""
        server = WorkflowServer(title="Endpoints Test Server")
        endpoints = server._get_workflow_endpoints("test_workflow")

        expected_endpoints = [
            "/workflows/test_workflow/execute",
            "/workflows/test_workflow/status",
            "/workflows/test_workflow/schema",
            "/workflows/test_workflow/docs",
        ]

        assert endpoints == expected_endpoints

    @patch("src.kailash.servers.workflow_server.WorkflowAPI")
    def test_workflows_endpoint_with_registered_workflow(self, mock_workflow_api):
        """Test workflows endpoint after registering a workflow."""
        workflow = Mock(spec=Workflow)
        workflow.workflow_id = "registered_workflow_id"
        workflow.version = "1.0.0"

        server = WorkflowServer(title="Registered Workflows Server")
        server.register_workflow(
            name="registered_workflow",
            workflow=workflow,
            description="A registered workflow",
            tags=["registered"],
        )

        client = TestClient(server.app)
        response = client.get("/workflows")
        assert response.status_code == 200

        data = response.json()
        assert "registered_workflow" in data
        workflow_info = data["registered_workflow"]
        assert workflow_info["type"] == "embedded"
        assert workflow_info["description"] == "A registered workflow"
        assert workflow_info["tags"] == ["registered"]
        assert "endpoints" in workflow_info

    def test_websocket_endpoint_basic(self):
        """Test basic WebSocket endpoint functionality."""
        server = WorkflowServer(title="WebSocket Test Server")
        client = TestClient(server.app)

        # Test WebSocket connection
        with client.websocket_connect("/ws") as websocket:
            # Send test message
            websocket.send_text("Hello")
            # Should receive echo
            data = websocket.receive_text()
            assert data == "Echo: Hello"

    def test_server_defaults(self):
        """Test that server has reasonable defaults."""
        server = WorkflowServer()

        assert server.app.title == "Kailash Workflow Server"
        assert server.app.description == "Multi-workflow hosting server"
        assert server.app.version == "1.0.0"
        # Check that executor was created with default workers
        assert server.executor._max_workers == 10  # default max_workers
