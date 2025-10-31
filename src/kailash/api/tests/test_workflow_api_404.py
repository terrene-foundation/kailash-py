"""
Tests for WorkflowAPI Custom 404 Handler

Tests that WorkflowAPI provides helpful 404 error messages
with available endpoints when wrong paths are accessed.

These tests follow TDD: They will FAIL initially until the 404 handler is implemented.
This is expected behavior - we write tests FIRST, then implement.
"""

import pytest
from fastapi.testclient import TestClient
from kailash.api.workflow_api import WorkflowAPI
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
def simple_workflow_api():
    """Simple WorkflowAPI for testing"""
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode", "test", {"code": "result = {'message': 'test'}"}
    )
    api = WorkflowAPI(workflow.build())
    return api


def test_404_returns_helpful_json(simple_workflow_api):
    """Test that 404 errors return helpful JSON with available endpoints."""
    client = TestClient(simple_workflow_api.app)

    # Try to access non-existent path
    response = client.get("/nonexistent")

    # Should return 404
    assert response.status_code == 404

    # Should be JSON
    assert response.headers["content-type"] == "application/json"

    # Should have helpful error message
    data = response.json()
    assert "error" in data or "detail" in data, "404 response should have error field"

    # Should mention endpoints or provide helpful info
    response_str = str(data).lower()
    has_endpoint_info = (
        "endpoint" in response_str
        or "available" in response_str
        or "path" in response_str
    )
    assert has_endpoint_info, "404 response should mention endpoints or paths"


def test_404_lists_available_endpoints(simple_workflow_api):
    """Test that 404 response includes list of available endpoints."""
    client = TestClient(simple_workflow_api.app)

    # Try to access non-existent path
    response = client.get("/invalid_path")

    assert response.status_code == 404

    data = response.json()

    # Should have some reference to available endpoints
    response_str = str(data)
    endpoints = []

    # Check if standard endpoints are mentioned
    if "/execute" in response_str:
        endpoints.append("/execute")
    if "/workflow/info" in response_str or "/info" in response_str:
        endpoints.append("/workflow/info")
    if "/health" in response_str:
        endpoints.append("/health")

    # Should mention at least 2 of the 3 standard endpoints
    assert (
        len(endpoints) >= 2
    ), f"404 response should mention available endpoints. Found: {endpoints}"


def test_404_provides_helpful_hint(simple_workflow_api):
    """Test that 404 response provides actionable hint."""
    client = TestClient(simple_workflow_api.app)

    # Try wrong path
    response = client.get("/wrong")

    assert response.status_code == 404

    data = response.json()
    response_str = str(data).lower()

    # Should have hint, message, or suggestion
    has_helpful_content = (
        "hint" in response_str
        or "try" in response_str
        or "use" in response_str
        or "most common" in response_str
        or "suggestion" in response_str
        or "did you mean" in response_str
    )

    assert (
        has_helpful_content
    ), "404 response should provide helpful hints or suggestions"


def test_404_includes_documentation_link(simple_workflow_api):
    """Test that 404 response includes link to documentation."""
    client = TestClient(simple_workflow_api.app)

    response = client.get("/missing")

    assert response.status_code == 404
    data = response.json()

    # Should have docs link or path
    response_str = str(data).lower()
    has_docs_reference = (
        "docs" in response_str
        or "documentation" in response_str
        or "/docs" in response_str
    )
    assert has_docs_reference, "404 response should reference documentation"


def test_404_handler_for_root_path(simple_workflow_api):
    """Test 404 handler when accessing root path with wrong method."""
    client = TestClient(simple_workflow_api.app)

    # Try to GET root (only POST is typically defined for execute)
    response = client.get("/")

    # Could be 404 or 405 Method Not Allowed
    assert response.status_code in [
        404,
        405,
    ], f"Expected 404 or 405, got {response.status_code}"

    # If 404, should have helpful info
    if response.status_code == 404:
        data = response.json()
        response_str = str(data).lower()

        # Should mention execute or available methods
        has_helpful_info = (
            "execute" in response_str
            or "post" in response_str
            or "endpoint" in response_str
        )
        assert (
            has_helpful_info
        ), "404 on root should mention execute endpoint or POST method"


def test_404_handler_preserves_fastapi_routes(simple_workflow_api):
    """Test that valid routes still work after adding 404 handler."""
    client = TestClient(simple_workflow_api.app)

    # Valid route should work
    response = client.get("/health")

    # Health endpoint should return 200
    assert (
        response.status_code == 200
    ), "Valid routes should still work after adding 404 handler"

    # Should return JSON
    assert response.headers["content-type"] == "application/json"


def test_404_response_format_consistency(simple_workflow_api):
    """Test that 404 responses have consistent format."""
    client = TestClient(simple_workflow_api.app)

    # Try multiple invalid paths
    paths = ["/invalid1", "/wrong/path", "/nonexistent/endpoint"]

    for path in paths:
        response = client.get(path)
        assert response.status_code == 404

        # All should return JSON
        assert (
            response.headers["content-type"] == "application/json"
        ), f"404 response for {path} should be JSON"

        # All should have error structure
        data = response.json()
        assert isinstance(
            data, dict
        ), f"404 response for {path} should be a JSON object"

        # Should have at least one error-related field
        has_error_field = any(key in data for key in ["error", "detail", "message"])
        assert (
            has_error_field
        ), f"404 response for {path} should have error/detail/message field"
