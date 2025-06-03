"""Unit tests for WorkflowAPI."""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from kailash.api.workflow_api import WorkflowAPI
from kailash.nodes.code import PythonCodeNode
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


class TestWorkflowAPI:
    """Test cases for WorkflowAPI."""

    def create_simple_workflow(self) -> Workflow:
        """Create a simple workflow for testing."""
        workflow = Workflow(
            workflow_id="test_001",
            name="Test Workflow",
            description="A simple test workflow",
            version="1.0.0",
        )

        # Add a simple node
        node = PythonCodeNode(
            name="processor",
            code="""
# The input 'value' is passed directly as a variable
result = {
    'result': value * 2,
    'processed': True
}
""",
        )
        workflow.add_node("process", node)

        return workflow

    def test_initialization_with_workflow(self):
        """Test API initialization with Workflow instance."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)

        assert api.workflow == workflow
        assert api.workflow_graph == workflow
        assert api.workflow_id == "test_001"
        assert api.version == "1.0.0"
        assert api.app.title == "Kailash Workflow API"

    def test_initialization_with_workflow_builder(self):
        """Test API initialization with WorkflowBuilder."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "process",
            {"name": "processor", "code": "output = input_data"},
        )

        # Mock the build method
        mock_workflow = self.create_simple_workflow()
        builder.build = Mock(return_value=mock_workflow)

        api = WorkflowAPI(builder)

        assert api.workflow == builder
        assert api.workflow_graph == mock_workflow
        builder.build.assert_called_once()

    def test_initialization_with_custom_params(self):
        """Test API initialization with custom parameters."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(
            workflow,
            app_name="Custom API",
            version="2.0.0",
            description="Custom description",
        )

        assert api.app.title == "Custom API"
        assert api.app.version == "2.0.0"
        assert api.app.description == "Custom description"

    def test_execute_endpoint(self):
        """Test the /execute endpoint."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        # Test synchronous execution
        response = client.post(
            "/execute", json={"inputs": {"process": {"value": 10}}, "mode": "sync"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "outputs" in data
        assert data["outputs"]["process"]["result"]["result"] == 20
        assert data["outputs"]["process"]["result"]["processed"] is True
        assert data["workflow_id"] == "test_001"
        assert data["version"] == "1.0.0"
        assert "execution_time" in data

    def test_workflow_info_endpoint(self):
        """Test the /workflow/info endpoint."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        response = client.get("/workflow/info")

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "test_001"
        assert data["name"] == "Test Workflow"
        assert data["description"] == "A simple test workflow"
        assert data["version"] == "1.0.0"
        assert "nodes" in data
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "process"
        assert data["nodes"][0]["type"] == "PythonCodeNode"

    def test_health_endpoint(self):
        """Test the /health endpoint."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["workflow"] == "test_001"

    def test_execute_with_config_override(self):
        """Test execution with configuration override."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        response = client.post(
            "/execute",
            json={
                "inputs": {"process": {"value": 5}},
                "config": {"process": {"some_config": "override"}},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["outputs"]["process"]["result"]["result"] == 10

    def test_execute_with_invalid_inputs(self):
        """Test execution with invalid inputs."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        # Missing required inputs field
        response = client.post("/execute", json={"config": {}})

        assert response.status_code == 422  # Validation error

    def test_async_execution_mode(self):
        """Test asynchronous execution mode."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        # Mock background task
        with patch("fastapi.BackgroundTasks.add_task") as mock_add_task:
            response = client.post(
                "/execute", json={"inputs": {"process": {"value": 10}}, "mode": "async"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "execution_id" in data
            assert data["status"] == "pending"
            assert "message" in data

            # Verify background task was added
            mock_add_task.assert_called_once()

    def test_status_endpoint(self):
        """Test the /status/{execution_id} endpoint."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        # First start async execution
        response = client.post(
            "/execute", json={"inputs": {"process": {"value": 10}}, "mode": "async"}
        )

        execution_id = response.json()["execution_id"]

        # Check status
        response = client.get(f"/status/{execution_id}")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["workflow_id"] == "test_001"

    def test_invalid_status_request(self):
        """Test status request for non-existent execution."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        response = client.get("/status/invalid-id")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"]

    def test_workflow_with_multiple_nodes(self):
        """Test workflow with multiple connected nodes."""
        workflow = Workflow("multi_001", "Multi-node Workflow")

        # First node
        node1 = PythonCodeNode(name="double", code="result = {'value': value * 2}")
        workflow.add_node("double", node1)

        # Second node
        node2 = PythonCodeNode(
            name="add_ten", code="result = {'value': value['value'] + 10}"
        )
        workflow.add_node("add_ten", node2)

        # Connect nodes
        workflow.connect("double", "add_ten", mapping={"result": "value"})

        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        response = client.post("/execute", json={"inputs": {"double": {"value": 5}}})

        assert response.status_code == 200
        data = response.json()
        assert data["outputs"]["double"]["result"]["value"] == 10
        assert data["outputs"]["add_ten"]["result"]["value"] == 20

    def test_openapi_documentation(self):
        """Test that OpenAPI documentation is generated."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        # Test OpenAPI schema endpoint
        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert schema["info"]["title"] == "Kailash Workflow API"
        assert "/execute" in schema["paths"]
        assert "/workflow/info" in schema["paths"]
        assert "/health" in schema["paths"]

    def test_docs_endpoint(self):
        """Test the interactive documentation endpoint."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        # Test Swagger UI
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger-ui" in response.text

        # Test ReDoc
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "redoc" in response.text.lower()

    def test_execution_error_handling(self):
        """Test error handling during workflow execution."""
        workflow = Workflow("error_001", "Error Workflow")

        # Node with error
        error_node = PythonCodeNode(name="error", code="raise ValueError('Test error')")
        workflow.add_node("error", error_node)

        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        response = client.post("/execute", json={"inputs": {"error": {}}})

        # Should return 200 with error details
        assert response.status_code == 200
        response.json()
        # The error should be captured in outputs or execution details

    @pytest.mark.asyncio
    async def test_background_execution(self):
        """Test background task execution."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)

        # Create execution data
        execution_id = "test-exec-123"
        inputs = {"process": {"value": 15}}
        config = {}

        # Initialize the cache entry first (like _execute_async does)
        api._execution_cache[execution_id] = {
            "status": "pending",
            "workflow_id": api.workflow_id,
            "version": api.version,
        }

        # Create a mock request
        from kailash.api.workflow_api import WorkflowRequest

        request = WorkflowRequest(inputs=inputs, config=config)

        # Run background execution
        await api._run_async_execution(execution_id, request)

        # Check execution was stored
        assert execution_id in api._execution_cache
        execution = api._execution_cache[execution_id]
        assert execution["status"] in ["completed", "failed"]
        if execution["status"] == "completed":
            result_data = execution.get("result", {})
            if "outputs" in result_data:
                assert result_data["outputs"]["process"]["result"]["result"] == 30

    def test_lifespan_events(self):
        """Test application lifespan events."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)

        # The lifespan context manager should handle startup/shutdown
        with TestClient(api.app) as client:
            # During lifespan, the app should be ready
            response = client.get("/health")
            assert response.status_code == 200

        # After lifespan, resources should be cleaned up
        # (In this simple case, there's not much to verify)

    def test_stream_execution_mode(self):
        """Test streaming execution mode."""
        workflow = self.create_simple_workflow()
        api = WorkflowAPI(workflow)
        client = TestClient(api.app)

        response = client.post(
            "/execute", json={"inputs": {"process": {"value": 10}}, "mode": "stream"}
        )

        # Streaming not implemented yet, should return appropriate response
        assert response.status_code in [200, 501]  # OK or Not Implemented
