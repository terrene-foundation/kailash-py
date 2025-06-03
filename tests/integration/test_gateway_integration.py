"""Integration tests for Multi-Workflow API Gateway."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from kailash.api.gateway import WorkflowAPIGateway, WorkflowOrchestrator
from kailash.api.mcp_integration import MCPIntegration, MCPToolNode
from kailash.nodes.code import PythonCodeNode
from kailash.workflow import Workflow


class TestGatewayIntegration:
    """Integration tests for the workflow gateway."""

    def create_data_processing_workflow(self) -> Workflow:
        """Create a data processing workflow for testing."""
        workflow = Workflow(
            workflow_id="data_proc_001",
            name="Data Processing",
            description="Process and validate data",
        )

        # Validation node
        validator = PythonCodeNode(
            name="validator",
            code="""
# data is provided directly as an input
errors = []

if not isinstance(data, list):
    errors.append("Data must be a list")
elif len(data) == 0:
    errors.append("Data cannot be empty")

result = {
    'valid': len(errors) == 0,
    'errors': errors,
    'data': data if len(errors) == 0 else None
}
""",
        )
        workflow.add_node("validate", validator)

        # Transform node
        transformer = PythonCodeNode(
            name="transformer",
            code="""
# data is provided directly as an input
if isinstance(data, dict) and 'data' in data:
    items = data['data']
elif isinstance(data, list):
    items = data
else:
    items = []

transformed = []
for item in items:
    if isinstance(item, dict):
        transformed_item = item.copy()
        transformed_item['processed'] = True
        transformed_item['value'] = transformed_item.get('value', 0) * 2
        transformed.append(transformed_item)
    else:
        transformed.append({'original': item, 'processed': True})

result = {
    'transformed_data': transformed,
    'count': len(transformed)
}
""",
        )
        workflow.add_node("transform", transformer)

        # Connect nodes with explicit mapping
        # The validate node outputs 'result' which contains a 'data' field
        # We need to pass the entire result to transform node
        workflow.connect("validate", "transform", mapping={"result": "data"})

        return workflow

    def create_analytics_workflow(self) -> Workflow:
        """Create an analytics workflow for testing."""
        workflow = Workflow(
            workflow_id="analytics_001", name="Analytics", description="Analyze data"
        )

        # Aggregation node
        aggregator = PythonCodeNode(
            name="aggregator",
            code="""
# data is provided directly as an input
total = 0
count = 0

for item in data:
    if isinstance(item, dict) and 'value' in item:
        total += item['value']
        count += 1

result = {
    'total': total,
    'count': count,
    'average': total / count if count > 0 else 0
}
""",
        )
        workflow.add_node("aggregate", aggregator)

        return workflow

    def test_basic_gateway_functionality(self):
        """Test basic gateway setup and operation."""
        # Create gateway
        gateway = WorkflowAPIGateway(
            title="Test Gateway", description="Integration test gateway", max_workers=5
        )

        # Register workflows
        gateway.register_workflow(
            "process",
            self.create_data_processing_workflow(),
            description="Data processing workflow",
            tags=["data", "validation"],
        )

        gateway.register_workflow(
            "analyze",
            self.create_analytics_workflow(),
            description="Analytics workflow",
            tags=["analytics", "aggregation"],
        )

        # Test with client
        client = TestClient(gateway.app)

        # Test root endpoint
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Gateway"
        assert set(data["workflows"]) == {"process", "analyze"}

        # Test workflow listing
        response = client.get("/workflows")
        assert response.status_code == 200
        data = response.json()
        assert "process" in data
        assert "analyze" in data
        assert data["process"]["description"] == "Data processing workflow"
        assert data["analyze"]["tags"] == ["analytics", "aggregation"]

    def test_workflow_execution_through_gateway(self):
        """Test executing workflows through the gateway."""
        gateway = WorkflowAPIGateway()
        gateway.register_workflow("process", self.create_data_processing_workflow())

        client = TestClient(gateway.app)

        # Execute workflow
        test_data = [
            {"id": 1, "value": 10},
            {"id": 2, "value": 20},
            {"id": 3, "value": 30},
        ]

        response = client.post(
            "/process/execute", json={"inputs": {"validate": {"data": test_data}}}
        )

        if response.status_code != 200:
            print(f"Response: {response.status_code}")
            print(f"Body: {response.json()}")

        assert response.status_code == 200
        result = response.json()
        assert "outputs" in result
        assert result["outputs"]["validate"]["result"]["valid"] is True
        assert result["outputs"]["transform"]["result"]["count"] == 3
        assert all(
            item["processed"]
            for item in result["outputs"]["transform"]["result"]["transformed_data"]
        )

    def test_mcp_integration_with_gateway(self):
        """Test MCP server integration with gateway."""
        # Create MCP server
        mcp = MCPIntegration("tools", "Test Tools")

        def calculate_stats(data: list) -> dict:
            """Calculate statistics."""
            values = [item.get("value", 0) for item in data if isinstance(item, dict)]
            return {
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
                "sum": sum(values),
                "count": len(values),
            }

        mcp.add_tool("stats", calculate_stats, "Calculate statistics")

        # Create workflow using MCP tool
        workflow = Workflow("stats_001", "Statistics Workflow")
        stats_node = MCPToolNode("tools", "stats")
        workflow.add_node("calculate_stats", stats_node)

        # Create gateway and register
        gateway = WorkflowAPIGateway()
        gateway.register_mcp_server("tools", mcp)
        gateway.register_workflow("statistics", workflow)

        # Set MCP integration on nodes
        for node_name, node in workflow._node_instances.items():
            if isinstance(node, MCPToolNode):
                node.set_mcp_integration(mcp)

        # Test execution
        client = TestClient(gateway.app)

        test_data = [{"value": 10}, {"value": 20}, {"value": 30}, {"value": 40}]

        response = client.post(
            "/statistics/execute",
            json={"inputs": {"calculate_stats": {"data": test_data}}},
        )

        assert response.status_code == 200
        result = response.json()
        stats = result["outputs"]["calculate_stats"]
        assert stats["min"] == 10
        assert stats["max"] == 40
        assert stats["sum"] == 100
        assert stats["count"] == 4

    def test_multiple_workflow_isolation(self):
        """Test that workflows are isolated from each other."""
        gateway = WorkflowAPIGateway()

        # Create two workflows with same node names
        workflow1 = Workflow("wf1", "Workflow 1")
        node1 = PythonCodeNode(
            name="processor", code="result = {'workflow': 1, 'input': test}"
        )
        workflow1.add_node("process", node1)

        workflow2 = Workflow("wf2", "Workflow 2")
        node2 = PythonCodeNode(
            name="processor", code="result = {'workflow': 2, 'input': test}"
        )
        workflow2.add_node("process", node2)

        # Register both
        gateway.register_workflow("first", workflow1)
        gateway.register_workflow("second", workflow2)

        client = TestClient(gateway.app)

        # Execute first workflow
        response1 = client.post(
            "/first/execute", json={"inputs": {"process": {"test": "data1"}}}
        )
        assert response1.status_code == 200
        result1 = response1.json()
        assert result1["outputs"]["process"]["result"]["workflow"] == 1

        # Execute second workflow
        response2 = client.post(
            "/second/execute", json={"inputs": {"process": {"test": "data2"}}}
        )
        assert response2.status_code == 200
        result2 = response2.json()
        assert result2["outputs"]["process"]["result"]["workflow"] == 2

    def test_gateway_health_monitoring(self):
        """Test health monitoring across workflows."""
        gateway = WorkflowAPIGateway()

        # Register multiple workflows
        for i in range(3):
            workflow = Workflow(f"wf_{i}", f"Workflow {i}")
            node = PythonCodeNode(name=f"node_{i}", code=f"result = 'result_{i}'")
            workflow.add_node("process", node)
            gateway.register_workflow(f"workflow{i}", workflow)

        client = TestClient(gateway.app)

        # Check health
        response = client.get("/health")
        assert response.status_code == 200
        health = response.json()

        assert health["status"] == "healthy"
        assert len(health["workflows"]) == 3
        for i in range(3):
            assert f"workflow{i}" in health["workflows"]
            assert health["workflows"][f"workflow{i}"] == "healthy"

    def test_concurrent_workflow_execution(self):
        """Test concurrent execution of multiple workflows."""
        gateway = WorkflowAPIGateway(max_workers=10)

        # Create a slow workflow
        slow_workflow = Workflow("slow", "Slow Workflow")
        slow_node = PythonCodeNode(
            name="slow_process",
            code="""
# Simulate slow processing with computation
total = 0
for i in range(10000000):  # Increased to make it slower
    total += i % 100
result = {'processed': data, 'result': total}
""",
        )
        slow_workflow.add_node("process", slow_node)

        # Create a fast workflow
        fast_workflow = Workflow("fast", "Fast Workflow")
        fast_node = PythonCodeNode(
            name="fast_process", code="result = {'processed': data, 'fast': True}"
        )
        fast_workflow.add_node("process", fast_node)

        gateway.register_workflow("slow", slow_workflow)
        gateway.register_workflow("fast", fast_workflow)

        client = TestClient(gateway.app)

        # Execute workflows concurrently
        results = []

        def execute_slow():
            response = client.post(
                "/slow/execute", json={"inputs": {"process": {"data": "slow"}}}
            )
            results.append(("slow", response.json()))

        def execute_fast():
            response = client.post(
                "/fast/execute", json={"inputs": {"process": {"data": "fast"}}}
            )
            results.append(("fast", response.json()))

        # Start slow workflow first
        slow_thread = threading.Thread(target=execute_slow)
        slow_thread.start()

        # Give it a small head start
        time.sleep(0.1)

        # Start fast workflow
        fast_thread = threading.Thread(target=execute_fast)
        fast_thread.start()

        # Wait for both
        slow_thread.join()
        fast_thread.join()

        # Fast should complete first despite starting second
        assert len(results) == 2
        assert results[0][0] == "fast"  # Fast completed first
        assert results[1][0] == "slow"  # Slow completed second

    def test_workflow_error_handling(self):
        """Test error handling in workflows."""
        gateway = WorkflowAPIGateway()

        # Create workflow with error
        error_workflow = Workflow("error", "Error Workflow")
        error_node = PythonCodeNode(
            name="error_node",
            code="""
# This will raise an error
result = 1 / 0
output = result
""",
        )
        error_workflow.add_node("divide", error_node)

        gateway.register_workflow("error", error_workflow)

        client = TestClient(gateway.app)

        # Execute workflow with error
        response = client.post("/error/execute", json={"inputs": {"divide": {}}})

        # Should still return 200 but with error in output
        assert response.status_code == 200
        result = response.json()
        assert "outputs" in result or "error" in result

    @pytest.mark.asyncio
    async def test_websocket_functionality(self):
        """Test WebSocket functionality."""
        gateway = WorkflowAPIGateway()

        # Register a workflow
        workflow = Workflow("ws_test", "WebSocket Test")
        node = PythonCodeNode(
            name="processor", code="output = {'message': 'processed'}"
        )
        workflow.add_node("process", node)
        gateway.register_workflow("wstest", workflow)

        client = TestClient(gateway.app)

        # Test WebSocket connection
        with client.websocket_connect("/ws") as websocket:
            # Send subscription
            websocket.send_json({"type": "subscribe", "workflow": "wstest"})

            # Receive acknowledgment
            data = websocket.receive_json()
            assert data["type"] == "ack"

            # Send another message
            websocket.send_json({"type": "status", "workflow": "wstest"})

            # Receive response
            data = websocket.receive_json()
            assert data["type"] == "ack"

    def test_workflow_orchestrator(self):
        """Test WorkflowOrchestrator functionality."""
        gateway = WorkflowAPIGateway()

        # Create simple workflows
        workflow1 = Workflow("wf1", "First")
        node1 = PythonCodeNode(
            name="add_one", code="output = {'value': input_data.get('value', 0) + 1}"
        )
        workflow1.add_node("process", node1)

        workflow2 = Workflow("wf2", "Second")
        node2 = PythonCodeNode(
            name="multiply_two",
            code="output = {'value': input_data.get('value', 0) * 2}",
        )
        workflow2.add_node("process", node2)

        gateway.register_workflow("first", workflow1)
        gateway.register_workflow("second", workflow2)

        # Create orchestrator
        orchestrator = WorkflowOrchestrator(gateway)

        # Create chain
        orchestrator.create_chain("increment_and_double", ["first", "second"])

        assert "increment_and_double" in orchestrator.chains
        assert orchestrator.chains["increment_and_double"] == ["first", "second"]

        # Test invalid chain
        with pytest.raises(ValueError, match="Workflow 'invalid' not registered"):
            orchestrator.create_chain("bad_chain", ["first", "invalid"])

    def test_gateway_with_proxy_workflow(self):
        """Test gateway with proxied workflow configuration."""
        gateway = WorkflowAPIGateway()

        # Register embedded workflow
        embedded = Workflow("embedded", "Embedded Workflow")
        node = PythonCodeNode(name="proc", code="output = 'embedded'")
        embedded.add_node("process", node)
        gateway.register_workflow("embedded", embedded)

        # Register proxied workflow
        gateway.proxy_workflow(
            "external",
            "http://external-service:8080",
            health_check="/health",
            description="External ML Service",
        )

        # Check registrations
        assert len(gateway.workflows) == 2
        assert gateway.workflows["embedded"].type == "embedded"
        assert gateway.workflows["external"].type == "proxied"
        assert gateway.workflows["external"].proxy_url == "http://external-service:8080"

        client = TestClient(gateway.app)

        # List workflows
        response = client.get("/workflows")
        assert response.status_code == 200
        data = response.json()

        assert data["embedded"]["type"] == "embedded"
        assert data["external"]["type"] == "proxied"
        assert "/embedded/docs" in data["embedded"]["endpoints"]
        assert (
            "/external/docs" not in data["external"]["endpoints"]
        )  # No docs for proxied

    def test_performance_under_load(self):
        """Test gateway performance under load."""
        gateway = WorkflowAPIGateway(max_workers=20)

        # Create a simple workflow
        workflow = Workflow("perf", "Performance Test")
        node = PythonCodeNode(
            name="compute",
            code="""
# Simulate some computation
result = sum(range(1000))
output = {'result': result, 'input': input_data}
""",
        )
        workflow.add_node("compute", node)
        gateway.register_workflow("perf", workflow)

        client = TestClient(gateway.app)

        # Execute many requests concurrently
        num_requests = 50
        executor = ThreadPoolExecutor(max_workers=10)

        def make_request(i):
            response = client.post(
                "/perf/execute", json={"inputs": {"compute": {"id": i}}}
            )
            return response.status_code == 200

        start_time = time.time()
        futures = [executor.submit(make_request, i) for i in range(num_requests)]
        results = [f.result() for f in futures]
        end_time = time.time()

        # All requests should succeed
        assert all(results)

        # Should complete in reasonable time
        duration = end_time - start_time
        assert duration < 10  # 50 requests in under 10 seconds

        # Calculate throughput
        throughput = num_requests / duration
        print(f"Throughput: {throughput:.2f} requests/second")

        executor.shutdown()
