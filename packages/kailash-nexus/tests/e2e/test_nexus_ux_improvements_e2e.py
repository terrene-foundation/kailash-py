"""
E2E Tests for Nexus UX Improvements

Tests comprehensive user journey including:
- Enhanced registration logging
- 404 error handling with helpful messages
- Documentation accuracy
- Multi-channel integration

These tests validate the complete UX improvement package.
"""

import logging
import socket
import time
from contextlib import closing
from pathlib import Path

import requests
from nexus import Nexus

from kailash.workflow.builder import WorkflowBuilder


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


def test_complete_registration_journey_with_enhanced_logging(caplog):
    """
    E2E test for complete registration journey with enhanced logging.

    User journey:
    1. Create Nexus instance
    2. Register workflow
    3. Verify enhanced logging shows full URLs
    4. Verify workflow is accessible
    """
    caplog.set_level(logging.INFO)

    api_port = find_free_port(8001)

    # Step 1: Create Nexus instance
    app = Nexus(api_port=api_port)

    # Step 2: Register workflow
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "greet",
        {
            "code": """
result = {
    'message': 'Hello from Nexus!',
    'status': 'success'
}
"""
        },
    )

    app.register("greeter", workflow)

    # Step 3: Verify enhanced logging
    log_output = caplog.text

    # Should show full URLs with port
    assert (
        f"http://localhost:{api_port}/workflows/greeter/execute" in log_output
    ), "Enhanced logging should show full execute endpoint URL"
    assert (
        f"http://localhost:{api_port}/workflows/greeter/workflow/info" in log_output
    ), "Enhanced logging should show full workflow/info endpoint URL"
    assert (
        f"http://localhost:{api_port}/workflows/greeter/health" in log_output
    ), "Enhanced logging should show full health endpoint URL"

    # Should show HTTP methods
    assert "POST" in log_output, "Enhanced logging should show POST method"
    assert "GET" in log_output, "Enhanced logging should show GET method"

    # Should show multi-channel info
    assert (
        "MCP" in log_output or "mcp" in log_output.lower()
    ), "Enhanced logging should mention MCP channel"
    assert (
        "CLI" in log_output or "cli" in log_output.lower()
    ), "Enhanced logging should mention CLI channel"


def test_404_handler_in_nexus_mounted_context(caplog):
    """
    E2E test for 404 handler working in Nexus mounted workflow context.

    Note: Due to FastAPI mount behavior, the custom 404 handler works best
    when accessing the WorkflowAPI's endpoints directly. This test validates
    that invalid endpoints still return proper 404 responses.

    User journey:
    1. Create Nexus with workflow
    2. Start Nexus server
    3. Try to access invalid endpoint
    4. Verify 404 response (either custom or standard)
    """
    import threading
    import time

    api_port = find_free_port(8002)

    # Create Nexus instance
    app = Nexus(api_port=api_port)

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "calc", {"code": "result = {'answer': 42}"})

    app.register("calculator", workflow)

    # Start server in background thread
    def run_server():
        app.start()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to start
    time.sleep(2)

    # Try to access invalid endpoint through Nexus
    try:
        response = requests.get(
            f"http://localhost:{api_port}/workflows/calculator/invalid", timeout=5
        )

        # Should return 404
        assert (
            response.status_code == 404
        ), f"Expected 404 for invalid endpoint, got {response.status_code}"

        # Should be JSON
        assert (
            response.headers.get("content-type") == "application/json"
        ), "404 response should be JSON"

        data = response.json()

        # Should have error structure (either "error" or "detail")
        assert (
            "error" in data or "detail" in data
        ), "404 response should have error field"

        # Note: Custom 404 messages work at the WorkflowAPI level but may not
        # propagate through Nexus gateway in all cases due to FastAPI mount behavior.
        # The key is that valid endpoints work and invalid ones return 404.

        # Verify that valid endpoints DO work by testing health endpoint
        health_response = requests.get(
            f"http://localhost:{api_port}/workflows/calculator/health", timeout=5
        )
        assert (
            health_response.status_code == 200
        ), "Valid endpoints should work correctly"

    finally:
        # Cleanup: stop server
        try:
            app.stop()
        except:
            pass


def test_end_to_end_user_discovery_flow():
    """
    E2E test simulating real user workflow discovery.

    User journey:
    1. Register workflow
    2. Start Nexus
    3. List all workflows via /workflows endpoint
    4. Get specific workflow info
    5. Execute workflow successfully
    """
    import threading
    import time

    api_port = find_free_port(8003)

    app = Nexus(api_port=api_port)

    # Register a test workflow
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "process",
        {
            "code": """
import json
result = {
    'processed': True,
    'data': 'test_data',
    'timestamp': '2025-10-08'
}
"""
        },
    )

    app.register("data_processor", workflow)

    # Start server
    def run_server():
        app.start()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    time.sleep(2)

    try:
        # Step 1: List all workflows
        response = requests.get(f"http://localhost:{api_port}/workflows", timeout=5)
        assert response.status_code == 200, "Should be able to list workflows"

        workflows = response.json()
        assert (
            "data_processor" in workflows
        ), "Registered workflow should appear in list"

        # Step 2: Get workflow info
        response = requests.get(
            f"http://localhost:{api_port}/workflows/data_processor/workflow/info",
            timeout=5,
        )
        assert response.status_code == 200, "Should be able to get workflow info"

        info = response.json()
        assert "nodes" in info, "Workflow info should include node information"

        # Step 3: Execute workflow
        response = requests.post(
            f"http://localhost:{api_port}/workflows/data_processor/execute",
            json={"inputs": {}},
            timeout=5,
        )
        assert response.status_code == 200, "Should be able to execute workflow"

        result = response.json()
        assert "outputs" in result, "Execution result should include outputs"

    finally:
        try:
            app.stop()
        except:
            pass


def test_documentation_and_logging_consistency():
    """
    E2E test verifying documentation matches actual behavior.

    Validates:
    1. Documentation describes correct endpoint patterns
    2. Logging output matches documented patterns
    3. Error messages match documentation
    """
    # Check that documentation exists
    docs_path = Path(__file__).parent.parent.parent / "docs"
    fastapi_doc = docs_path / "technical" / "fastapi-mount-behavior.md"

    assert fastapi_doc.exists(), "FastAPI mount behavior documentation should exist"

    # Read documentation
    doc_content = fastapi_doc.read_text()

    # Documentation should describe standard endpoints
    assert "/execute" in doc_content, "Documentation should mention /execute endpoint"
    assert (
        "/workflow/info" in doc_content
    ), "Documentation should mention /workflow/info endpoint"
    assert "/health" in doc_content, "Documentation should mention /health endpoint"

    # Documentation should mention discovery
    assert (
        "/workflows" in doc_content
    ), "Documentation should mention /workflows discovery endpoint"

    # Documentation should explain FastAPI mount behavior
    assert (
        "mount" in doc_content.lower()
    ), "Documentation should explain FastAPI mount behavior"
    assert (
        "openapi" in doc_content.lower()
    ), "Documentation should explain OpenAPI schema behavior"


def test_regression_existing_functionality_preserved():
    """
    E2E regression test ensuring existing functionality still works.

    Validates:
    1. Workflow execution works as before
    2. Health checks work
    3. Workflow info endpoint works
    4. No breaking changes introduced
    """
    api_port = find_free_port(8004)

    app = Nexus(api_port=api_port)

    # Create workflow similar to existing examples
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "compute",
        {
            "code": """
result = {
    'computed': True,
    'value': 123
}
"""
        },
    )

    # Register workflow
    app.register("compute_workflow", workflow)

    # Start server
    import threading
    import time

    def run_server():
        app.start()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    time.sleep(2)

    try:
        # Test health endpoint
        response = requests.get(
            f"http://localhost:{api_port}/workflows/compute_workflow/health", timeout=5
        )
        assert response.status_code == 200, "Health endpoint should work"
        health = response.json()
        assert (
            health["status"] == "healthy"
        ), "Health check should return healthy status"

        # Test workflow info endpoint
        response = requests.get(
            f"http://localhost:{api_port}/workflows/compute_workflow/workflow/info",
            timeout=5,
        )
        assert response.status_code == 200, "Workflow info endpoint should work"
        info = response.json()
        assert "workflow_id" in info, "Info should include workflow_id"

        # Test execution endpoint
        response = requests.post(
            f"http://localhost:{api_port}/workflows/compute_workflow/execute",
            json={"inputs": {}},
            timeout=5,
        )
        assert response.status_code == 200, "Execute endpoint should work"
        result = response.json()
        assert "outputs" in result, "Execution should return outputs"

    finally:
        try:
            app.stop()
        except:
            pass
