"""Simplified E2E tests for Nexus platform.

Tests complete end-to-end scenarios without complex async fixture setup.
"""

import json
import socket
import threading
import time

import pytest
import requests
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


def find_free_port(start_port: int = 8000) -> int:
    """Find a free port starting from the given port."""
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError("No free ports available")


class TestNexusE2EScenarios:
    """Test complete end-to-end Nexus scenarios."""

    def setup_method(self):
        """Set up production-like environment."""
        # Use dynamic port allocation to avoid conflicts
        api_port = find_free_port(8890)
        mcp_port = find_free_port(api_port + 100)

        self.app = Nexus(
            api_port=api_port,
            mcp_port=mcp_port,
            enable_auth=False,
            enable_monitoring=True,
            enable_durability=False,  # Disable caching for consistent test results
        )

        # Register production workflows
        self._register_workflows()

        # Start server
        self.server_thread = threading.Thread(target=self.app.start, daemon=True)
        self.server_thread.start()

        # Wait for server to start
        time.sleep(3)

        # API base URL
        self.api_base = f"http://localhost:{self.app._api_port}"

    def teardown_method(self):
        """Clean up."""
        if hasattr(self, "app"):
            self.app.stop()
            time.sleep(0.5)

    def _register_workflows(self):
        """Register production-like workflows."""
        # Document processor workflow
        doc_workflow = WorkflowBuilder()
        doc_workflow.add_node(
            "PythonCodeNode",
            "preprocess",
            {
                "code": """
# Parameters are directly available as variables
# Handle missing document parameter
doc = ''
try:
    doc = document
except NameError:
    pass

result = {
    'preprocessed': doc.strip().lower(),
    'word_count': len(doc.split()),
    'char_count': len(doc)
}
"""
            },
        )
        doc_workflow.add_node(
            "PythonCodeNode",
            "analyze",
            {
                "code": """
# Parameters are directly available as variables in the namespace
# Initialize text first to ensure it exists in all scopes
text = ''
try:
    text = preprocessed
except NameError:
    pass

words = text.split()

# Check sentiment without list comprehension (to avoid scoping issues in exec)
positive_words = ['good', 'great', 'excellent']
is_positive = False
for word in positive_words:
    if word in text:
        is_positive = True
        break

result = {
    'analysis': {
        'sentiment': 'positive' if is_positive else 'neutral',
        'keywords': list(set(words))[:5],
        'summary': ' '.join(words[:10]) + '...' if len(words) > 10 else text
    }
}
"""
            },
        )
        doc_workflow.add_connection(
            "preprocess", "result.preprocessed", "analyze", "preprocessed"
        )
        self.app.register("document_processor", doc_workflow.build())

        # Data pipeline workflow
        data_workflow = WorkflowBuilder()
        data_workflow.add_node(
            "PythonCodeNode",
            "transform",
            {
                "code": """
# Parameters are directly available as variables in the namespace
# But we need to handle the case where they might not be passed
try:
    data_list = data
except NameError:
    data_list = []

result = {
    'transformed': [{'id': i, 'value': item * 2} for i, item in enumerate(data_list)],
    'count': len(data_list),
    'sum': sum(data_list) if data_list else 0
}
"""
            },
        )
        self.app.register("data_pipeline", data_workflow.build())

        # API integration workflow
        api_workflow = WorkflowBuilder()
        api_workflow.add_node(
            "PythonCodeNode",
            "fetch_data",
            {
                "code": """
# Parameters are directly available as variables in the namespace
# But we need to handle the case where they might not be passed
try:
    ep = endpoint
except NameError:
    ep = '/default'

result = {
    'api_response': {
        'status': 200,
        'data': {'message': f'Data from {ep}', 'timestamp': '2024-01-01T00:00:00Z'},
        'headers': {'content-type': 'application/json'}
    }
}
"""
            },
        )
        self.app.register("api_integration", api_workflow.build())

    def test_health_check_e2e(self):
        """Test health check endpoint."""
        response = requests.get(f"{self.api_base}/health")
        assert response.status_code == 200

        health = response.json()
        # Check for either format (SDK gateway returns different format)
        assert "status" in health or "healthy" in health
        if "status" in health:
            assert health["status"] == "healthy"

    def test_workflow_list_e2e(self):
        """Test listing available workflows."""
        response = requests.get(f"{self.api_base}/workflows")
        assert response.status_code == 200

        workflows = response.json()
        # SDK gateway returns workflows as a dict
        assert isinstance(workflows, dict)
        assert len(workflows) >= 3

        # Check our registered workflows
        assert "document_processor" in workflows
        assert "data_pipeline" in workflows
        assert "api_integration" in workflows

    def test_document_processing_e2e(self):
        """Test complete document processing scenario."""
        # Submit document for processing
        document = "This is a great example document with excellent content for testing purposes."

        response = requests.post(
            f"{self.api_base}/workflows/document_processor/execute",
            json={"inputs": {"document": document}},
        )

        assert response.status_code == 200
        result = response.json()

        # SDK gateway returns results in "outputs" key
        if "outputs" in result:
            outputs = result["outputs"]
        else:
            outputs = result

        # Verify preprocessing
        assert "preprocess" in outputs
        preprocess_result = outputs["preprocess"]["result"]

        assert preprocess_result["word_count"] > 0
        assert preprocess_result["char_count"] > 0

        # Verify analysis
        assert "analyze" in outputs
        analysis = outputs["analyze"]["result"]["analysis"]
        assert analysis["sentiment"] == "positive"  # Contains 'great' and 'excellent'
        assert len(analysis["keywords"]) > 0
        assert "summary" in analysis

    def test_data_pipeline_e2e(self):
        """Test data transformation pipeline."""
        test_data = [1, 2, 3, 4, 5]

        response = requests.post(
            f"{self.api_base}/workflows/data_pipeline/execute",
            json={"inputs": {"data": test_data}},
        )

        assert response.status_code == 200
        result = response.json()

        # SDK gateway returns results in "outputs" key
        if "outputs" in result:
            outputs = result["outputs"]
        else:
            outputs = result

        # Verify transformation
        assert "transform" in outputs
        transform_result = outputs["transform"]["result"]
        assert transform_result["count"] == 5
        assert transform_result["sum"] == 15
        assert len(transform_result["transformed"]) == 5
        assert transform_result["transformed"][0]["value"] == 2  # 1 * 2

    def test_api_integration_e2e(self):
        """Test API integration workflow."""
        response = requests.post(
            f"{self.api_base}/workflows/api_integration/execute",
            json={"inputs": {"endpoint": "/users/123"}},
        )

        assert response.status_code == 200
        result = response.json()

        # SDK gateway returns results in "outputs" key
        if "outputs" in result:
            outputs = result["outputs"]
        else:
            outputs = result

        # Verify API response
        assert "fetch_data" in outputs
        api_response = outputs["fetch_data"]["result"]["api_response"]
        assert api_response["status"] == 200
        assert api_response["data"]["message"] == "Data from /users/123"
        assert "timestamp" in api_response["data"]

    def test_workflow_chaining_e2e(self):
        """Test chaining multiple workflows."""
        # First, process a document
        doc_response = requests.post(
            f"{self.api_base}/workflows/document_processor/execute",
            json={"inputs": {"document": "Process this text for analysis"}},
        )
        assert doc_response.status_code == 200

        # Then use the word count in data pipeline
        doc_result = doc_response.json()

        # With durability disabled, we get direct response format
        if "outputs" in doc_result:
            outputs = doc_result["outputs"]
        else:
            outputs = doc_result

        # Extract word count
        assert "preprocess" in outputs
        preprocess_result = outputs["preprocess"]["result"]
        word_count = preprocess_result["word_count"]

        data_response = requests.post(
            f"{self.api_base}/workflows/data_pipeline/execute",
            json={"inputs": {"data": list(range(word_count))}},
        )
        assert data_response.status_code == 200

        # Verify chained results
        data_result = data_response.json()

        # With durability disabled, we get direct response format
        if "outputs" in data_result:
            outputs = data_result["outputs"]
        else:
            outputs = data_result
        assert outputs["transform"]["result"]["count"] == word_count

    def test_concurrent_requests_e2e(self):
        """Test handling concurrent requests."""
        import concurrent.futures

        def make_request(index):
            response = requests.post(
                f"{self.api_base}/workflows/data_pipeline/execute",
                json={"inputs": {"data": [index, index + 1, index + 2]}},
            )
            return response.status_code, response.json()

        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All requests should succeed
        assert all(status == 200 for status, _ in results)
        assert len(results) == 10

    def test_error_handling_e2e(self):
        """Test error handling in workflows."""
        # Test with missing required parameter
        response = requests.post(
            f"{self.api_base}/workflows/document_processor",
            json={},  # Missing 'document' parameter
        )

        # Should still return 200 but with empty result
        assert response.status_code == 200
        result = response.json()
        if "outputs" in result:
            outputs = result["outputs"]
        else:
            outputs = result
        assert "preprocess" in outputs

        # Test with invalid workflow
        response = requests.post(
            f"{self.api_base}/workflows/nonexistent/execute", json={"data": "test"}
        )
        assert response.status_code == 404

    def test_performance_metrics_e2e(self):
        """Test performance under load."""
        start_time = time.time()

        # Make multiple requests
        for i in range(20):
            response = requests.post(
                f"{self.api_base}/workflows/data_pipeline/execute",
                json={"data": list(range(10))},
            )
            assert response.status_code == 200

        elapsed = time.time() - start_time
        avg_response_time = elapsed / 20

        # Should handle at least 5 requests per second
        assert avg_response_time < 0.2  # 200ms max per request

        # Check Nexus performance metrics
        metrics = self.app.get_performance_metrics()
        assert "workflow_registration_time" in metrics
        assert metrics["workflow_registration_time"]["count"] >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
