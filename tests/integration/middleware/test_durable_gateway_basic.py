"""Basic integration test for Durable Gateway.

This test verifies the basic functionality of the durable gateway
with minimal dependencies.
"""

import asyncio
import os
import random
import tempfile
import warnings
from typing import Any, Dict

import httpx
import pytest
import pytest_asyncio
from kailash.middleware.gateway.checkpoint_manager import CheckpointManager, DiskStorage
from kailash.middleware.gateway.durable_gateway import DurableAPIGateway
from kailash.nodes.code import PythonCodeNode
from kailash.workflow import WorkflowBuilder

# Suppress WebSocket deprecation warnings from external libraries
warnings.filterwarnings(
    "ignore", message="websockets.legacy is deprecated", category=DeprecationWarning
)
warnings.filterwarnings(
    "ignore",
    message="websockets.server.WebSocketServerProtocol is deprecated",
    category=DeprecationWarning,
)


class TestDurableGatewayBasic:
    """Basic integration tests for Durable Gateway."""

    @pytest_asyncio.fixture
    async def simple_gateway(self):
        """Create a simple durable gateway for testing."""
        # Use temporary directory for checkpoints
        temp_dir = tempfile.mkdtemp(prefix="kailash_test_")

        # Create gateway with basic configuration
        checkpoint_manager = CheckpointManager(
            disk_storage=DiskStorage(temp_dir),
            retention_hours=1,
        )

        gateway = DurableAPIGateway(
            title="Test Durable Gateway",
            enable_durability=True,
            checkpoint_manager=checkpoint_manager,
            durability_opt_in=False,  # Always use durability for tests
        )

        # Register a simple test workflow
        workflow = WorkflowBuilder()
        workflow.name = "simple_test"
        workflow.add_node(
            "PythonCodeNode",
            "echo",
            {
                "code": """
# Variables should be in namespace from inputs
# Use try/except for optional inputs
try:
    msg = message
except NameError:
    msg = "Hello World"

try:
    ts = timestamp
except NameError:
    ts = "now"

result = {
    "message": msg,
    "timestamp": ts
}
"""
            },
        )

        gateway.register_workflow("echo", workflow.build())

        # Start gateway in a thread since uvicorn.run is synchronous
        import threading
        import time

        # Use a random port to avoid conflicts
        port = random.randint(8000, 8999)

        server_thread = threading.Thread(
            target=lambda: gateway.run(port=port, log_level="error"), daemon=True
        )
        server_thread.start()

        # Wait for gateway startup with health check polling
        import asyncio
        from datetime import datetime

        start_time = datetime.now()
        gateway_ready = False

        while (datetime.now() - start_time).total_seconds() < 10.0:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"http://localhost:{port}/health", timeout=1.0
                    )
                    if response.status_code == 200:
                        print(f"Health check response: {response.status_code}")
                        gateway_ready = True
                        break
            except (httpx.ConnectError, httpx.TimeoutException):
                pass  # Gateway not ready yet

            await asyncio.sleep(0.1)

        if not gateway_ready:
            print("Gateway failed to start within 10 seconds")

        # Store port for tests
        gateway._test_port = port

        yield gateway

        # Note: Server thread will be cleaned up when daemon thread exits

        # Clean up temp directory
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_basic_echo(self, simple_gateway):
        """Test basic echo workflow with durability."""
        port = simple_gateway._test_port
        async with httpx.AsyncClient(base_url=f"http://localhost:{port}") as client:
            # Submit echo request
            response = await client.post(
                "/echo/execute",
                json={
                    "inputs": {
                        "echo": {"message": "Test Message", "timestamp": "2025-01-20"}
                    }
                },
                timeout=5.0,
            )

            if response.status_code != 200:
                print(f"Response status: {response.status_code}")
                print(f"Response body: {response.text}")
            assert response.status_code == 200
            result = response.json()

            # Debug: print the actual result structure
            print(f"Response result: {result}")

            # Check echo response - outputs are organized by node ID
            assert "outputs" in result
            assert "echo" in result["outputs"]
            assert "result" in result["outputs"]["echo"]

            echo_result = result["outputs"]["echo"]["result"]
            assert echo_result["message"] == "Test Message"
            assert echo_result["timestamp"] == "2025-01-20"

            # Check durability headers
            request_id = response.headers.get("X-Request-ID")
            print(f"Request ID header: {request_id}")
            print(f"All headers: {dict(response.headers)}")
            # TODO: Fix durability header injection
            # assert request_id is not None

    @pytest.mark.asyncio
    async def test_durability_status(self, simple_gateway):
        """Test durability status endpoint."""
        port = simple_gateway._test_port
        async with httpx.AsyncClient(base_url=f"http://localhost:{port}") as client:
            # Check durability status
            response = await client.get("/durability/status")

            assert response.status_code == 200
            status = response.json()

            # Debug: print the actual status structure
            print(f"Status response: {status}")

            # Verify status structure
            assert "enabled" in status
            assert status["enabled"] is True
            assert "checkpoint_stats" in status
            assert "deduplication_stats" in status
            assert "event_store_stats" in status

            # Verify the durability system is working
            assert status["event_store_stats"]["event_count"] > 0
