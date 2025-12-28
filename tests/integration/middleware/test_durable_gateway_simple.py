"""Simple integration test for Durable Gateway focusing on core functionality."""

import asyncio
import random
import tempfile
import time

import httpx
import pytest
import pytest_asyncio
from kailash.middleware.gateway.checkpoint_manager import CheckpointManager, DiskStorage
from kailash.middleware.gateway.durable_gateway import DurableAPIGateway
from kailash.workflow import WorkflowBuilder


class TestDurableGatewaySimple:
    """Simple integration tests for Durable Gateway core functionality."""

    @pytest_asyncio.fixture
    async def simple_gateway(self):
        """Create a simple durable gateway with basic workflows."""
        # Use temporary directory for checkpoints
        temp_dir = tempfile.mkdtemp(prefix="kailash_test_")

        # Create gateway with basic configuration
        checkpoint_manager = CheckpointManager(
            disk_storage=DiskStorage(temp_dir),
            retention_hours=1,
        )

        gateway = DurableAPIGateway(
            title="Simple Test Durable Gateway",
            enable_durability=True,
            checkpoint_manager=checkpoint_manager,
            durability_opt_in=False,  # Always use durability for tests
        )

        # Register simple workflows
        await self._register_simple_workflows(gateway)

        # Start gateway in a thread
        import threading

        port = random.randint(8000, 8999)
        server_thread = threading.Thread(
            target=lambda: gateway.run(port=port, log_level="error"), daemon=True
        )
        server_thread.start()
        time.sleep(2)  # Wait for startup

        gateway._test_port = port
        yield gateway

        # Clean up temp directory
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    async def _register_simple_workflows(self, gateway):
        """Register simple test workflows."""

        # 1. Simple computation workflow
        compute_workflow = WorkflowBuilder()
        compute_workflow.name = "simple_compute"
        compute_workflow.add_node(
            "PythonCodeNode",
            "compute",
            {
                "code": """
# Simple computation with input validation
try:
    x = input_value
except NameError:
    x = 10

try:
    multiplier = multiplier_value
except NameError:
    multiplier = 2

result = {
    "computed_value": x * multiplier,
    "operation": f"{x} * {multiplier}",
    "timestamp": "now"
}
"""
            },
        )
        gateway.register_workflow("compute", compute_workflow.build())

        # 2. Multi-step workflow
        multi_step_workflow = WorkflowBuilder()
        multi_step_workflow.name = "multi_step"

        multi_step_workflow.add_node(
            "PythonCodeNode",
            "step1",
            {
                "code": """
try:
    initial_value = start_value
except NameError:
    initial_value = 5

result = {
    "step1_output": initial_value + 10,
    "message": f"Step 1 processed {initial_value}"
}
"""
            },
        )

        multi_step_workflow.add_node(
            "PythonCodeNode",
            "step2",
            {
                "code": """
# step1_output comes from previous node connection
step2_result = step1_output * 3

result = {
    "step2_output": step2_result,
    "message": f"Step 2 processed {step1_output} -> {step2_result}",
    "final_result": step2_result
}
"""
            },
        )

        # Connect the steps
        multi_step_workflow.add_connection(
            "step1", "result.step1_output", "step2", "step1_output"
        )

        gateway.register_workflow("multi_step", multi_step_workflow.build())

    @pytest.mark.asyncio
    async def test_simple_compute_workflow(self, simple_gateway):
        """Test simple computation workflow."""
        port = simple_gateway._test_port
        async with httpx.AsyncClient(base_url=f"http://localhost:{port}") as client:
            # Test basic computation
            response = await client.post(
                "/compute/execute",
                json={
                    "inputs": {"compute": {"input_value": 15, "multiplier_value": 4}}
                },
                timeout=10.0,
            )

            assert response.status_code == 200
            result = response.json()

            # Check computation result
            assert "outputs" in result
            assert "compute" in result["outputs"]
            assert "result" in result["outputs"]["compute"]

            compute_result = result["outputs"]["compute"]["result"]
            assert compute_result["computed_value"] == 60  # 15 * 4
            assert compute_result["operation"] == "15 * 4"

    @pytest.mark.asyncio
    async def test_multi_step_workflow(self, simple_gateway):
        """Test multi-step workflow with node connections."""
        port = simple_gateway._test_port
        async with httpx.AsyncClient(base_url=f"http://localhost:{port}") as client:
            # Test multi-step workflow
            response = await client.post(
                "/multi_step/execute",
                json={"inputs": {"step1": {"start_value": 7}}},
                timeout=10.0,
            )

            assert response.status_code == 200
            result = response.json()

            # Check multi-step results
            assert "outputs" in result
            assert "step1" in result["outputs"]
            assert "step2" in result["outputs"]

            step1_result = result["outputs"]["step1"]["result"]
            step2_result = result["outputs"]["step2"]["result"]

            assert step1_result["step1_output"] == 17  # 7 + 10
            assert step2_result["final_result"] == 51  # 17 * 3

    @pytest.mark.asyncio
    async def test_concurrent_executions(self, simple_gateway):
        """Test concurrent workflow executions."""
        port = simple_gateway._test_port

        async def execute_workflow(client, input_val):
            response = await client.post(
                "/compute/execute",
                json={
                    "inputs": {
                        "compute": {"input_value": input_val, "multiplier_value": 2}
                    }
                },
                timeout=10.0,
            )
            return response.status_code == 200, input_val * 2

        async with httpx.AsyncClient(base_url=f"http://localhost:{port}") as client:
            # Execute multiple workflows concurrently
            tasks = [execute_workflow(client, i) for i in range(1, 11)]  # 1 to 10

            results = await asyncio.gather(*tasks)

            # Check all executions succeeded
            success_count = sum(1 for success, _ in results if success)
            assert (
                success_count >= 8
            ), f"Expected at least 8 successes, got {success_count}"

    @pytest.mark.asyncio
    async def test_durability_features(self, simple_gateway):
        """Test durability features like deduplication."""
        port = simple_gateway._test_port
        async with httpx.AsyncClient(base_url=f"http://localhost:{port}") as client:
            # Test durability status endpoint
            status_response = await client.get("/durability/status")
            assert status_response.status_code == 200

            status = status_response.json()
            assert status["enabled"] is True
            assert "checkpoint_stats" in status
            assert "deduplication_stats" in status

            # Test workflow execution with durability
            response = await client.post(
                "/compute/execute",
                json={
                    "inputs": {"compute": {"input_value": 25, "multiplier_value": 3}}
                },
                timeout=10.0,
            )

            assert response.status_code == 200
            result = response.json()

            # Verify result
            compute_result = result["outputs"]["compute"]["result"]
            assert compute_result["computed_value"] == 75  # 25 * 3
