"""Docker-based integration tests for HealthCheckNode - NO MOCKS."""

import asyncio
import threading
import time
from datetime import datetime

import aiohttp
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from tests.integration.docker_test_base import DockerIntegrationTestBase

from kailash.nodes.monitoring import HealthCheckNode
from kailash.nodes.monitoring.health_check import HealthStatus, ServiceType


@pytest.mark.integration
@pytest.mark.requires_docker
class TestHealthCheckNodeDocker(DockerIntegrationTestBase):
    """Test HealthCheckNode with real services."""

    @pytest.fixture
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

        # Start server in background thread
        config = uvicorn.Config(app, host="127.0.0.1", port=8899, log_level="error")
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
                    async with session.get("http://localhost:8899/health") as resp:
                        if resp.status == 200:
                            break
                except:
                    await asyncio.sleep(0.1)

        yield health_status

        # Server will stop when thread ends

    @pytest.fixture
    async def health_check_node(self):
        """Create HealthCheckNode instance."""
        return HealthCheckNode(id="test_health_check")

    @pytest.mark.asyncio
    async def test_http_health_check_success(self, health_check_node, test_api_server):
        """Test successful HTTP health check against real server."""
        # Configure service to check
        services = [
            {
                "name": "test_api",
                "type": "http",
                "url": "http://localhost:8899/health",
                "expected_status": 200,
            }
        ]

        # Execute health check
        result = await health_check_node.execute(
            {"services": services, "timeout": 5.0, "parallel": True}
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
        assert "timestamp" in service_result["metadata"]

    @pytest.mark.asyncio
    async def test_http_health_check_failure(self, health_check_node, test_api_server):
        """Test failed HTTP health check against real server."""
        # Make server unhealthy
        test_api_server["status"] = "error"

        services = [
            {
                "name": "test_api",
                "type": "http",
                "url": "http://localhost:8899/health",
                "expected_status": 200,
            }
        ]

        result = await health_check_node.execute({"services": services, "timeout": 5.0})

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
        services = [
            {"name": "test_api", "type": "http", "url": "http://localhost:8899/health"},
            {
                "name": "test_metrics",
                "type": "http",
                "url": "http://localhost:8899/metrics",
            },
            {"name": "redis_cache", "type": "redis", "host": "localhost", "port": 6379},
        ]

        start_time = time.time()
        result = await health_check_node.execute(
            {"services": services, "parallel": True, "timeout": 5.0}
        )
        duration = time.time() - start_time

        # Should complete quickly due to parallel execution
        assert duration < 2.0

        # Check results
        assert result["overall_status"] == "healthy"
        assert result["healthy_count"] == 3
        assert result["unhealthy_count"] == 0

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

        result = await health_check_node.execute(
            {"services": services, "timeout": 10.0}
        )

        assert result["overall_status"] == "healthy"
        assert result["services"]["postgres_db"]["status"] == "healthy"
        assert "version" in result["services"]["postgres_db"]["metadata"]

    @pytest.mark.asyncio
    async def test_health_check_with_retries(self, health_check_node, test_api_server):
        """Test health check retry mechanism with real service."""
        # Make service flaky (will fail first, then succeed)
        fail_count = 0
        original_status = test_api_server["status"]

        async def flaky_behavior():
            nonlocal fail_count
            if fail_count < 2:
                fail_count += 1
                test_api_server["status"] = "error"
            else:
                test_api_server["status"] = "healthy"

        # Start flaky behavior
        await flaky_behavior()

        services = [
            {
                "name": "flaky_api",
                "type": "http",
                "url": "http://localhost:8899/health",
                "expected_status": 200,
            }
        ]

        # Execute with retries
        result = await health_check_node.execute(
            {"services": services, "retries": 3, "timeout": 5.0}
        )

        # Reset for next retry
        await flaky_behavior()
        await flaky_behavior()

        # Should eventually succeed
        assert result["overall_status"] == "healthy"
        assert result["services"]["flaky_api"]["status"] == "healthy"

        # Restore original status
        test_api_server["status"] = original_status

    @pytest.mark.asyncio
    async def test_health_check_timeout(self, health_check_node, test_api_server):
        """Test health check timeout with real slow service."""
        # Make service very slow
        test_api_server["delay"] = 2.0

        services = [
            {"name": "slow_api", "type": "http", "url": "http://localhost:8899/health"}
        ]

        # Execute with short timeout
        result = await health_check_node.execute(
            {"services": services, "timeout": 0.5, "retries": 1}  # 500ms timeout
        )

        assert result["overall_status"] == "unhealthy"
        assert result["services"]["slow_api"]["status"] == "unhealthy"
        assert "timeout" in result["services"]["slow_api"]["error"].lower()

        # Reset delay
        test_api_server["delay"] = 0

    @pytest.mark.asyncio
    async def test_custom_health_check(self, health_check_node):
        """Test custom health check function."""

        # Define custom check function
        async def check_custom_service(config):
            """Custom health check logic."""
            # Simulate some async work
            await asyncio.sleep(0.1)

            # Return health status based on config
            if config.get("simulate_healthy", True):
                return {
                    "status": "healthy",
                    "latency": 100,
                    "metadata": {
                        "custom_field": "custom_value",
                        "checked_at": datetime.utcnow().isoformat(),
                    },
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": "Custom check failed",
                    "latency": 100,
                }

        # Patch the custom check handler
        health_check_node._check_custom = check_custom_service

        services = [
            {"name": "custom_service", "type": "custom", "simulate_healthy": True}
        ]

        result = await health_check_node.execute({"services": services})

        assert result["overall_status"] == "healthy"
        assert result["services"]["custom_service"]["status"] == "healthy"
        assert (
            result["services"]["custom_service"]["metadata"]["custom_field"]
            == "custom_value"
        )

    @pytest.mark.asyncio
    async def test_mixed_service_health_status(
        self, health_check_node, test_api_server, redis_client
    ):
        """Test overall status calculation with mixed results."""
        # Make API degraded
        test_api_server["status"] = "degraded"

        services = [
            {
                "name": "api_service",
                "type": "http",
                "url": "http://localhost:8899/health",
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

        result = await health_check_node.execute(
            {"services": services, "parallel": True, "timeout": 2.0}
        )

        # Overall should be unhealthy (has failures)
        assert result["overall_status"] == "unhealthy"
        assert result["healthy_count"] == 1  # Only Redis
        assert result["unhealthy_count"] == 2  # API degraded + fake service

        # Check individual statuses
        assert result["services"]["redis_service"]["status"] == "healthy"
        assert (
            result["services"]["api_service"]["status"] == "unhealthy"
        )  # 200 but degraded
        assert result["services"]["fake_service"]["status"] == "unhealthy"

        # Reset API status
        test_api_server["status"] = "healthy"
