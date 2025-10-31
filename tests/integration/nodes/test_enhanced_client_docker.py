"""Docker-based integration tests for enhanced client - NO MOCKS."""

import asyncio
import json
import threading
import time
from datetime import datetime

import aiohttp
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from kailash.client.enhanced_client import KailashClient, WorkflowResult

from tests.integration.docker_test_base import DockerIntegrationTestBase


@pytest.mark.integration
@pytest.mark.requires_docker
class TestEnhancedClientDocker(DockerIntegrationTestBase):
    """Test enhanced client with real API server."""

    @pytest_asyncio.fixture
    async def kailash_api_server(self):
        """Create a real Kailash API server for testing."""
        app = FastAPI()

        # Track state for testing
        server_state = {
            "executions": {},
            "delay": 0,
            "fail_next": False,
            "auth_required": False,
            "execution_counter": 0,
        }

        @app.post("/api/v1/workflows/{workflow_id}/execute")
        async def execute_workflow(
            workflow_id: str, request: dict, authorization: str = Header(None)
        ):
            """Execute a workflow."""
            if server_state["auth_required"] and not authorization:
                raise HTTPException(status_code=401, detail="Authentication required")

            if server_state["fail_next"]:
                server_state["fail_next"] = False
                raise HTTPException(status_code=500, detail="Simulated server error")

            # Simulate delay
            if server_state["delay"] > 0:
                await asyncio.sleep(server_state["delay"])

            execution_id = f"exec_{server_state['execution_counter']}"
            server_state["execution_counter"] += 1

            # Create execution result
            result = {
                "request_id": execution_id,
                "workflow_id": workflow_id,
                "status": "completed",
                "result": {"output": "Workflow executed successfully"},
                "execution_time": 1.5,
            }

            server_state["executions"][execution_id] = result

            return result

        @app.get("/api/v1/workflows/{workflow_id}/status/{request_id}")
        async def get_workflow_status(
            workflow_id: str, request_id: str, authorization: str = Header(None)
        ):
            """Get workflow execution status."""
            if request_id not in server_state["executions"]:
                raise HTTPException(status_code=404, detail="Execution not found")

            return server_state["executions"][request_id]

        @app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}

        # Start server on a dynamic port
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)

        thread = threading.Thread(target=server.run)
        thread.daemon = True
        thread.start()

        # Wait for server to start
        await asyncio.sleep(0.5)

        # Verify server is running
        async with aiohttp.ClientSession() as session:
            for _ in range(10):
                try:
                    async with session.get(f"http://localhost:{port}/health") as resp:
                        if resp.status == 200:
                            break
                except:
                    await asyncio.sleep(0.1)

        server_state["port"] = port
        yield server_state

    @pytest_asyncio.fixture
    async def kailash_client(self, kailash_api_server):
        """Create KailashClient instance."""
        client = KailashClient(
            base_url=f"http://localhost:{kailash_api_server['port']}",
            api_key="test_key",
            timeout=30,
        )
        yield client
        try:
            await client.close()
        except RuntimeError:
            # Ignore event loop issues during teardown
            pass

    @pytest.mark.asyncio
    async def test_workflow_execution_basic(self, kailash_client, kailash_api_server):
        """Test basic workflow execution with real API."""
        workflow_id = "test_workflow_123"
        inputs = {"input_data": "test_value"}

        result = await kailash_client.execute_workflow(
            workflow_id=workflow_id,
            inputs=inputs,
            wait=False,  # Don't wait for completion
        )

        assert result.workflow_id == workflow_id
        assert result.status == "completed"
        assert result.result["output"] == "Workflow executed successfully"
        assert result.execution_time == 1.5
        assert result.is_success is True
        assert result.is_failed is False

    @pytest.mark.asyncio
    async def test_workflow_execution_with_resources(
        self, kailash_client, kailash_api_server
    ):
        """Test workflow execution with resources."""
        workflow_id = "test_workflow_resources"
        inputs = {"data": "test"}
        resources = {"db_connection": "postgresql://localhost/test"}
        context = {"user_id": "test_user"}

        result = await kailash_client.execute_workflow(
            workflow_id=workflow_id,
            inputs=inputs,
            resources=resources,
            context=context,
            wait=False,
        )

        assert result.workflow_id == workflow_id
        assert result.status == "completed"
        assert result.is_success is True

    @pytest.mark.asyncio
    async def test_workflow_status_retrieval(self, kailash_client, kailash_api_server):
        """Test retrieving workflow status."""
        workflow_id = "test_workflow_status"
        inputs = {"data": "test"}

        # Execute workflow
        result = await kailash_client.execute_workflow(
            workflow_id=workflow_id, inputs=inputs, wait=False
        )

        # Get status
        status = await kailash_client.get_workflow_status(
            workflow_id, result.request_id
        )

        assert status.workflow_id == workflow_id
        assert status.request_id == result.request_id
        assert status.status == "completed"

    @pytest.mark.asyncio
    async def test_error_handling_server_error(
        self, kailash_client, kailash_api_server
    ):
        """Test error handling when server returns error."""
        kailash_api_server["fail_next"] = True

        workflow_id = "test_workflow_error"
        inputs = {"data": "test"}

        try:
            result = await kailash_client.execute_workflow(
                workflow_id=workflow_id, inputs=inputs, wait=False
            )
            # If we get here, check if the server error was handled differently
            assert False, f"Expected exception but got result: {result}"
        except aiohttp.ClientResponseError as e:
            assert e.status == 500
        except Exception as e:
            # Accept any exception that indicates server error
            assert "500" in str(e) or "error" in str(e).lower()

    @pytest.mark.asyncio
    async def test_timeout_handling(self, kailash_client, kailash_api_server):
        """Test timeout handling for slow responses."""
        # Set server delay
        kailash_api_server["delay"] = 0.5

        workflow_id = "test_workflow_timeout"
        inputs = {"data": "test"}

        # Should complete within timeout
        result = await kailash_client.execute_workflow(
            workflow_id=workflow_id, inputs=inputs, wait=False
        )

        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_authentication_handling(self, kailash_client, kailash_api_server):
        """Test authentication handling."""
        kailash_api_server["auth_required"] = True

        workflow_id = "test_workflow_auth"
        inputs = {"data": "test"}

        # Should work with API key
        result = await kailash_client.execute_workflow(
            workflow_id=workflow_id, inputs=inputs, wait=False
        )

        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_concurrent_executions(self, kailash_client, kailash_api_server):
        """Test concurrent workflow executions."""
        workflow_id = "test_workflow_concurrent"

        # Execute multiple workflows concurrently
        tasks = []
        for i in range(5):
            task = kailash_client.execute_workflow(
                workflow_id=f"{workflow_id}_{i}",
                inputs={"data": f"test_{i}"},
                wait=False,
            )
            tasks.append(task)

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

        # Verify all succeeded
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result.workflow_id == f"{workflow_id}_{i}"
            assert result.status == "completed"
            assert result.is_success is True

    @pytest.mark.asyncio
    async def test_context_manager_usage(self, kailash_api_server):
        """Test using client as context manager."""
        workflow_id = "test_workflow_context"
        inputs = {"data": "test"}

        async with KailashClient(
            base_url=f"http://localhost:{kailash_api_server['port']}"
        ) as client:
            result = await client.execute_workflow(
                workflow_id=workflow_id, inputs=inputs, wait=False
            )

            assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_workflow_result_properties(self, kailash_client, kailash_api_server):
        """Test WorkflowResult properties."""
        workflow_id = "test_workflow_props"
        inputs = {"data": "test"}

        result = await kailash_client.execute_workflow(
            workflow_id=workflow_id, inputs=inputs, wait=False
        )

        # Test properties
        assert result.is_success is True
        assert result.is_failed is False
        assert result.is_running is False
        assert result.request_id.startswith("exec_")
        assert result.workflow_id == workflow_id
        assert result.execution_time == 1.5
        assert result.result["output"] == "Workflow executed successfully"
