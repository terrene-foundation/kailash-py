"""Unit tests for HealthCheckNode."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest
from kailash.nodes.monitoring import HealthCheckNode
from kailash.nodes.monitoring.health_check import HealthStatus, ServiceType
from kailash.sdk_exceptions import NodeExecutionError


class TestHealthCheckNode:
    """Test suite for HealthCheckNode."""

    def test_node_initialization(self):
        """Test that HealthCheckNode initializes correctly."""
        node = HealthCheckNode(id="test_health")
        assert node.id == "test_health"
        assert node.metadata.name == "HealthCheckNode"  # Auto-generated from class name

    def test_get_parameters(self):
        """Test parameter definition."""
        node = HealthCheckNode()
        params = node.get_parameters()

        # Check required parameters
        assert "services" in params
        assert params["services"].required is True
        assert params["services"].type == list

        # Check optional parameters
        assert "timeout" in params
        assert params["timeout"].required is False
        assert params["timeout"].default == 30.0

        assert "parallel" in params
        assert params["parallel"].default is True

        assert "retries" in params
        assert params["retries"].default == 3

    def test_get_output_schema(self):
        """Test output schema definition."""
        node = HealthCheckNode()
        schema = node.get_output_schema()

        # Check output fields
        assert "overall_status" in schema
        assert schema["overall_status"].type == str

        assert "services" in schema
        assert schema["services"].type == dict

        assert "healthy_count" in schema
        assert "unhealthy_count" in schema
        assert "total_latency" in schema
        assert "timestamp" in schema

    def test_health_status_enum(self):
        """Test HealthStatus enumeration."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNKNOWN.value == "unknown"

    def test_service_type_enum(self):
        """Test ServiceType enumeration."""
        assert ServiceType.HTTP.value == "http"
        assert ServiceType.DATABASE.value == "database"
        assert ServiceType.REDIS.value == "redis"
        assert ServiceType.CUSTOM.value == "custom"

    @pytest.mark.asyncio
    async def test_http_health_check_success(self):
        """Test successful HTTP health check."""
        node = HealthCheckNode()

        # Create a complete mock for aiohttp
        with patch("kailash.nodes.monitoring.health_check.aiohttp") as mock_aiohttp:
            # Mock response
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.headers = {"X-Response-Time": "50ms"}

            # Create async context managers using MagicMock
            # For the request
            mock_request_cm = MagicMock()
            mock_request_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request_cm.__aexit__ = AsyncMock(return_value=None)

            # For the session
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_request_cm)

            mock_session_cm = MagicMock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)

            # Configure ClientSession
            mock_aiohttp.ClientSession = MagicMock(return_value=mock_session_cm)
            mock_aiohttp.ClientTimeout = MagicMock()

            # Execute with mocked HTTP service
            result = await node.execute_async(
                services=[
                    {
                        "name": "api",
                        "type": "http",
                        "url": "https://api.example.com/health",
                        "method": "GET",
                        "expected_status": [200, 204],
                    }
                ],
                parallel=False,
            )

            # Verify results
            assert result["overall_status"] == "healthy"
            assert result["healthy_count"] == 1
            assert result["unhealthy_count"] == 0
            assert "api" in result["services"]
            assert result["services"]["api"]["status"] == "healthy"
            assert result["services"]["api"]["status_code"] == 200

    @pytest.mark.asyncio
    async def test_http_health_check_failure(self):
        """Test failed HTTP health check."""
        node = HealthCheckNode()

        with patch("kailash.nodes.monitoring.health_check.aiohttp") as mock_aiohttp:
            # Mock response with error status
            mock_response = MagicMock()
            mock_response.status = 500

            # Create async context managers using MagicMock
            # For the request
            mock_request_cm = MagicMock()
            mock_request_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request_cm.__aexit__ = AsyncMock(return_value=None)

            # For the session
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_request_cm)

            mock_session_cm = MagicMock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)

            # Configure ClientSession
            mock_aiohttp.ClientSession = MagicMock(return_value=mock_session_cm)
            mock_aiohttp.ClientTimeout = MagicMock()

            result = await node.execute_async(
                services=[
                    {
                        "name": "api",
                        "type": "http",
                        "url": "https://api.example.com/health",
                        "expected_status": [200],
                    }
                ],
                retries=1,  # Reduce retries for faster test
            )

            # Verify failure is recorded
            assert result["overall_status"] == "unhealthy"
            assert result["healthy_count"] == 0
            assert result["unhealthy_count"] == 1
            assert result["services"]["api"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_database_health_check_mock(self):
        """Test database health check with mock."""
        node = HealthCheckNode()

        # Mock asyncpg connection
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 1
        mock_conn.close.return_value = None

        with patch("asyncpg.connect", return_value=mock_conn):
            result = await node.execute_async(
                services=[
                    {
                        "name": "postgres",
                        "type": "database",
                        "connection_string": "postgresql://test:test@localhost/test",
                        "test_query": "SELECT 1",
                    }
                ]
            )

            # Verify results
            assert result["overall_status"] == "healthy"
            assert result["services"]["postgres"]["status"] == "healthy"
            assert result["services"]["postgres"]["query_result"] == 1

    @pytest.mark.asyncio
    async def test_custom_health_check(self):
        """Test custom health check function."""
        node = HealthCheckNode()

        # Custom check function
        async def custom_check():
            return {"status": "healthy", "custom_data": "test"}

        result = await node.execute_async(
            services=[
                {
                    "name": "custom_service",
                    "type": "custom",
                    "check_function": custom_check,
                }
            ]
        )

        # Verify custom check results
        assert result["overall_status"] == "healthy"
        assert result["services"]["custom_service"]["status"] == "healthy"
        assert result["services"]["custom_service"]["custom_data"] == "test"

    @pytest.mark.asyncio
    async def test_parallel_health_checks(self):
        """Test parallel execution of health checks."""
        node = HealthCheckNode()

        # Mock multiple services
        services = []
        for i in range(3):

            async def check():
                await asyncio.sleep(0.01)  # Simulate some work
                return {"status": "healthy", "service_id": i}

            services.append(
                {"name": f"service_{i}", "type": "custom", "check_function": check}
            )

        result = await node.execute_async(services=services, parallel=True)

        # Verify all services were checked
        assert result["overall_status"] == "healthy"
        assert result["healthy_count"] == 3
        assert len(result["services"]) == 3

    @pytest.mark.asyncio
    async def test_fail_fast_mode(self):
        """Test fail-fast mode stops on first failure."""
        node = HealthCheckNode()

        check_count = 0

        async def failing_check():
            nonlocal check_count
            check_count += 1
            raise Exception("Service unavailable")

        async def healthy_check():
            nonlocal check_count
            check_count += 1
            return {"status": "healthy"}

        result = await node.execute_async(
            services=[
                {"name": "failing", "type": "custom", "check_function": failing_check},
                {"name": "healthy", "type": "custom", "check_function": healthy_check},
            ],
            parallel=False,
            fail_fast=True,
            retries=1,
        )

        # With fail_fast, should stop after first failure
        assert result["overall_status"] == "unhealthy"
        assert "failing" in result["services"]
        # The healthy service might not be checked due to fail_fast

    @pytest.mark.asyncio
    async def test_retry_configuration(self):
        """Test that retry configuration is passed through correctly."""
        node = HealthCheckNode()

        # Simple test to verify retry parameters are accepted
        with patch("kailash.nodes.monitoring.health_check.aiohttp") as mock_aiohttp:
            # Mock successful response
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.headers = {}

            # Create async context managers
            mock_request_cm = MagicMock()
            mock_request_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request_cm.__aexit__ = AsyncMock(return_value=None)

            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_request_cm)

            mock_session_cm = MagicMock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)

            # Configure ClientSession
            mock_aiohttp.ClientSession = MagicMock(return_value=mock_session_cm)
            mock_aiohttp.ClientTimeout = MagicMock()

            # Test with custom retry settings
            result = await node.execute_async(
                services=[
                    {
                        "name": "test_api",
                        "type": "http",
                        "url": "https://api.example.com/health",
                        "expected_status": [200],
                    }
                ],
                retries=5,  # Custom retry count
                retry_delay=0.5,  # Custom retry delay
            )

            # Verify success
            assert result["overall_status"] == "healthy"
            assert "test_api" in result["services"]
            assert result["services"]["test_api"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_degraded_status(self):
        """Test degraded status when some services are unhealthy."""
        node = HealthCheckNode()

        async def healthy():
            return {"status": "healthy"}

        async def unhealthy():
            raise Exception("Service down")

        result = await node.execute_async(
            services=[
                {"name": "service1", "type": "custom", "check_function": healthy},
                {"name": "service2", "type": "custom", "check_function": unhealthy},
            ],
            retries=1,
        )

        # Mixed results should give degraded status
        assert result["overall_status"] == "degraded"
        assert result["healthy_count"] == 1
        assert result["unhealthy_count"] == 1

    def test_node_import(self):
        """Test that HealthCheckNode can be imported from monitoring module."""
        from kailash.nodes.monitoring import HealthCheckNode as ImportedNode

        assert ImportedNode is not None
        assert ImportedNode.__name__ == "HealthCheckNode"

    def test_synchronous_execute(self):
        """Test synchronous execution wrapper."""
        node = HealthCheckNode()

        # Mock the async execution
        async def mock_check():
            return {"status": "healthy"}

        with patch.object(node, "execute_async") as mock_execute:
            mock_execute.return_value = {
                "overall_status": "healthy",
                "services": {"test": {"status": "healthy"}},
                "healthy_count": 1,
                "unhealthy_count": 0,
                "total_latency": 0.1,
                "timestamp": datetime.now().isoformat(),
            }

            # Execute synchronously
            result = node.execute(
                services=[
                    {"name": "test", "type": "custom", "check_function": mock_check}
                ]
            )

            assert result["overall_status"] == "healthy"
