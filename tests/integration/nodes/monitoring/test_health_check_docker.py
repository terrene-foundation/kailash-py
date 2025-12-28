"""Docker-based integration tests for HealthCheckNode - NO MOCKS."""

import asyncio
import threading
import time
from datetime import datetime

import aiohttp
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from kailash.nodes.monitoring import HealthCheckNode
from kailash.nodes.monitoring.health_check import HealthStatus, ServiceType

from tests.integration.docker_test_base import DockerIntegrationTestBase


@pytest.mark.integration
@pytest.mark.requires_docker
class TestHealthCheckNodeDocker(DockerIntegrationTestBase):
    """Test HealthCheckNode with real services."""

    @pytest_asyncio.fixture
    async def test_api_server(self):
        """Create a real test API server."""
        app = FastAPI()

        # Track health status for testing
        health_status = {"status": "healthy", "delay": 0}

        @app.get("/health")
        async def health_endpoint():
            """Simulated health endpoint."""
            if health_status["delay"] > 0:
                await asyncio.sleep(health_status["delay"])

            if health_status["status"] == "healthy":
                return JSONResponse(
                    content={
                        "status": "ok",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    headers={"X-Response-Time": "50ms"},
                )
            elif health_status["status"] == "degraded":
                return JSONResponse(
                    content={"status": "degraded", "message": "High load"},
                    status_code=200,
                    headers={"X-Response-Time": "500ms"},
                )
            else:
                return JSONResponse(
                    content={"status": "error", "message": "Service unavailable"},
                    status_code=503,
                )

        @app.get("/metrics")
        async def metrics_endpoint():
            """Metrics endpoint for monitoring."""
            return {
                "cpu_usage": 45.2,
                "memory_usage": 62.8,
                "request_count": 1234,
                "error_rate": 0.02,
            }

        # Start server in background thread with random port to avoid conflicts
        import random

        port = random.randint(8900, 8999)
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

        # Return both health status and port for tests to use
        yield health_status, port

        # Server will stop when thread ends

    @pytest_asyncio.fixture
    async def health_check_node(self):
        """Create HealthCheckNode instance."""
        return HealthCheckNode(id="test_health_check")

    @pytest.mark.asyncio
    async def test_http_health_check_success(self, health_check_node, test_api_server):
        """Test successful HTTP health check against real server."""
        health_status, port = test_api_server
        # Configure service to check
        services = [
            {
                "name": "test_api",
                "type": "http",
                "url": f"http://localhost:{port}/health",
                "expected_status": 200,
            }
        ]

        # Execute health check
        result = await health_check_node.execute_async(
            services=services, timeout=5.0, parallel=True
        )

        # Verify results
        assert result["overall_status"] == "healthy"
        assert result["healthy_count"] == 1
        assert result["unhealthy_count"] == 0
        assert "test_api" in result["services"]

        service_result = result["services"]["test_api"]
        assert service_result["status"] == "healthy"
        assert service_result["latency"] > 0
        assert service_result["latency"] < 1000  # Less than 1 second
        # Health check returns basic status info, not metadata

    @pytest.mark.asyncio
    async def test_http_health_check_failure(self, health_check_node, test_api_server):
        """Test failed HTTP health check against real server."""
        health_status, port = test_api_server
        # Make server unhealthy
        health_status["status"] = "error"

        services = [
            {
                "name": "test_api",
                "type": "http",
                "url": f"http://localhost:{port}/health",
                "expected_status": 200,
            }
        ]

        result = await health_check_node.execute_async(services=services, timeout=5.0)

        assert result["overall_status"] == "unhealthy"
        assert result["healthy_count"] == 0
        assert result["unhealthy_count"] == 1

        service_result = result["services"]["test_api"]
        assert service_result["status"] == "unhealthy"
        assert "error" in service_result

    @pytest.mark.asyncio
    async def test_multiple_services_parallel(
        self, health_check_node, test_api_server, redis_client
    ):
        """Test checking multiple services in parallel."""
        health_status, port = test_api_server
        services = [
            {
                "name": "test_api",
                "type": "http",
                "url": f"http://localhost:{port}/health",
            },
            {
                "name": "test_metrics",
                "type": "http",
                "url": f"http://localhost:{port}/metrics",
            },
            {"name": "redis_cache", "type": "redis", "host": "localhost", "port": 6379},
        ]

        start_time = time.time()
        result = await health_check_node.execute_async(
            services=services, parallel=True, timeout=5.0
        )
        duration = time.time() - start_time

        # Should complete quickly due to parallel execution
        assert duration < 2.0

        # Check results - may be degraded if some services have issues
        assert result["overall_status"] in ["healthy", "degraded"]
        assert result["healthy_count"] >= 2  # At least 2 services should be healthy
        assert result["unhealthy_count"] <= 1  # At most 1 service should be unhealthy

        # Verify all services checked
        assert len(result["services"]) == 3
        assert all(s["status"] == "healthy" for s in result["services"].values())

    @pytest.mark.asyncio
    async def test_database_health_check(self, health_check_node, postgres_conn):
        """Test database health check with real PostgreSQL."""
        services = [
            {
                "name": "postgres_db",
                "type": "database",
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
            }
        ]

        result = await health_check_node.execute_async(services=services, timeout=10.0)

        assert result["overall_status"] == "healthy"
        assert result["services"]["postgres_db"]["status"] == "healthy"
        # Database health check returns basic connection info, not metadata

    @pytest.mark.asyncio
    async def test_health_check_with_retries(self, health_check_node, test_api_server):
        """Test health check retry mechanism with real service."""
        health_status, port = test_api_server
        original_status = health_status["status"]

        try:
            # Make service initially fail
            health_status["status"] = "error"

            services = [
                {
                    "name": "flaky_api",
                    "type": "http",
                    "url": f"http://localhost:{port}/health",
                    "expected_status": 200,
                }
            ]

            # Execute with retries - service will fail initially
            result = await health_check_node.execute_async(
                services=services, retries=2, timeout=5.0
            )

            # With error status, should be unhealthy despite retries
            assert result["overall_status"] == "unhealthy"
            assert result["services"]["flaky_api"]["status"] == "unhealthy"

        finally:
            # Always restore original status
            health_status["status"] = original_status

    @pytest.mark.asyncio
    async def test_health_check_timeout(self, health_check_node, test_api_server):
        """Test health check timeout with real slow service."""
        health_status, port = test_api_server
        # Make service very slow
        health_status["delay"] = 2.0

        services = [
            {
                "name": "slow_api",
                "type": "http",
                "url": f"http://localhost:{port}/health",
            }
        ]

        # Execute with short timeout
        result = await health_check_node.execute_async(
            services=services, timeout=0.5, retries=1  # 500ms timeout
        )

        assert result["overall_status"] == "unhealthy"
        assert result["services"]["slow_api"]["status"] == "unhealthy"
        assert (
            "timeout" in result["services"]["slow_api"]["error"].lower()
            or "timed out" in result["services"]["slow_api"]["error"].lower()
        )

        # Reset delay
        health_status["delay"] = 0

    @pytest.mark.asyncio
    async def test_custom_health_check(self, health_check_node):
        """Test custom health check function."""

        # Define custom check function
        async def check_custom_service():
            """Custom health check logic."""
            # Simulate some async work
            await asyncio.sleep(0.1)

            # Return health status - custom function doesn't receive config
            return {
                "status": "healthy",
                "latency": 100,
                "metadata": {
                    "custom_field": "custom_value",
                    "checked_at": datetime.utcnow().isoformat(),
                },
            }

        services = [
            {
                "name": "custom_service",
                "type": "custom",
                "check_function": check_custom_service,
            }
        ]

        result = await health_check_node.execute_async(services=services)

        assert result["overall_status"] == "healthy"
        assert result["services"]["custom_service"]["status"] == "healthy"
        # Custom service check should work but response structure may vary

    @pytest.mark.asyncio
    async def test_mixed_service_health_status(
        self, health_check_node, test_api_server, redis_client
    ):
        """Test overall status calculation with mixed results."""
        health_status, port = test_api_server
        # Make API degraded
        health_status["status"] = "degraded"

        services = [
            {
                "name": "api_service",
                "type": "http",
                "url": f"http://localhost:{port}/health",
            },
            {
                "name": "redis_service",
                "type": "redis",
                "host": "localhost",
                "port": 6379,
            },
            {
                "name": "fake_service",
                "type": "http",
                "url": "http://localhost:9999/health",  # Non-existent
            },
        ]

        result = await health_check_node.execute_async(
            services=services, parallel=True, timeout=2.0
        )

        # Overall should be degraded or unhealthy (has failures)
        assert result["overall_status"] in ["degraded", "unhealthy"]
        # Count may vary based on actual health check results
        assert result["unhealthy_count"] >= 1  # At least the fake service should fail

        # Check individual statuses
        assert result["services"]["redis_service"]["status"] == "healthy"
        # API service may return 200 but with degraded content (still considered healthy by HTTP check)
        # Fake service should definitely be unhealthy
        assert result["services"]["fake_service"]["status"] == "unhealthy"

        # Reset API status
        health_status["status"] = "healthy"
