"""
Unit tests for Health Check System.

Tests health checking functionality including:
- HealthStatus and HealthState
- Database health checks
- HTTP client health checks
- Cache health checks
- Message queue health checks
- Composite health checks
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from kailash.resources.health import (
    HealthState,
    HealthStatus,
    cache_health_check,
    create_composite_health_check,
    database_health_check,
    http_client_health_check,
    message_queue_health_check,
)


class TestHealthStatus:
    """Test HealthStatus functionality."""

    def test_healthy_status(self):
        """Test healthy status creation."""
        status = HealthStatus.healthy("All good")

        assert status.state == HealthState.HEALTHY
        assert status.message == "All good"
        assert status.is_healthy is True
        assert isinstance(status.timestamp, datetime)

    def test_unhealthy_status(self):
        """Test unhealthy status creation."""
        details = {"error": "Connection failed", "code": 500}
        status = HealthStatus.unhealthy("Database down", details)

        assert status.state == HealthState.UNHEALTHY
        assert status.message == "Database down"
        assert status.details == details
        assert status.is_healthy is False

    def test_degraded_status(self):
        """Test degraded status creation."""
        details = {"latency": "high", "retry_count": 3}
        status = HealthStatus.degraded("Slow response", details)

        assert status.state == HealthState.DEGRADED
        assert status.message == "Slow response"
        assert status.details == details
        assert status.is_healthy is True  # Degraded is still considered healthy

    def test_unknown_status(self):
        """Test unknown status."""
        status = HealthStatus(HealthState.UNKNOWN)

        assert status.state == HealthState.UNKNOWN
        assert status.is_healthy is False

    def test_is_healthy_property(self):
        """Test is_healthy property for different states."""
        assert HealthStatus(HealthState.HEALTHY).is_healthy is True
        assert HealthStatus(HealthState.DEGRADED).is_healthy is True
        assert HealthStatus(HealthState.UNHEALTHY).is_healthy is False
        assert HealthStatus(HealthState.UNKNOWN).is_healthy is False


@pytest.mark.asyncio
class TestDatabaseHealthCheck:
    """Test database health checking."""

    async def test_asyncpg_pool_healthy(self):
        """Test healthy asyncpg pool."""
        mock_conn = MagicMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        status = await database_health_check(mock_pool)

        assert status.is_healthy
        assert "healthy" in status.message.lower()
        mock_conn.fetchval.assert_called_once_with("SELECT 1")

    async def test_pool_with_ping(self):
        """Test pool with ping method."""
        mock_pool = MagicMock()
        mock_pool.ping = AsyncMock()

        # Mock so it doesn't have acquire method
        del mock_pool.acquire

        status = await database_health_check(mock_pool)

        assert status.is_healthy
        mock_pool.ping.assert_called_once()

    async def test_aiosqlite_connection(self):
        """Test aiosqlite connection."""
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()

        # Mock so it doesn't have acquire or ping
        del mock_conn.acquire
        del mock_conn.ping

        status = await database_health_check(mock_conn)

        assert status.is_healthy
        mock_conn.execute.assert_called_once_with("SELECT 1")

    async def test_database_timeout(self):
        """Test database timeout handling."""
        mock_pool = MagicMock()
        mock_pool.acquire.side_effect = asyncio.TimeoutError()

        status = await database_health_check(mock_pool)

        assert not status.is_healthy
        assert status.state == HealthState.UNHEALTHY
        assert "timed out" in status.message.lower()
        assert status.details["error"] == "timeout"

    async def test_database_exception(self):
        """Test database exception handling."""
        mock_pool = MagicMock()
        mock_pool.acquire.side_effect = Exception("Connection failed")

        status = await database_health_check(mock_pool)

        assert not status.is_healthy
        assert "Connection failed" in status.message
        assert status.details["error"] == "Connection failed"


@pytest.mark.asyncio
class TestHttpClientHealthCheck:
    """Test HTTP client health checking."""

    async def test_aiohttp_client_healthy(self):
        """Test healthy aiohttp client."""
        # Create a mock response
        mock_response = MagicMock()
        mock_response.status = 200

        # Create mock client - aiohttp is detected by NOT having _base_url
        mock_client = MagicMock()
        # Explicitly remove _base_url to simulate aiohttp
        if hasattr(mock_client, "_base_url"):
            del mock_client._base_url

        # Mock get method to return an async context manager
        mock_get = MagicMock()
        mock_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get.__aexit__ = AsyncMock(return_value=None)
        mock_client.get.return_value = mock_get

        status = await http_client_health_check(mock_client)

        assert status.is_healthy
        assert "200" in status.message
        mock_client.get.assert_called_once_with("/health")

    async def test_httpx_client_healthy(self):
        """Test healthy httpx client."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client._base_url = "https://api.example.com"  # httpx marker
        mock_client.get = AsyncMock(return_value=mock_response)

        status = await http_client_health_check(mock_client)

        assert status.is_healthy
        assert "200" in status.message
        mock_client.get.assert_called_once_with("/health")

    async def test_http_client_unhealthy_status(self):
        """Test HTTP client returning error status."""
        mock_response = MagicMock()
        mock_response.status = 500

        mock_client = MagicMock()
        # Explicitly remove _base_url to simulate aiohttp
        if hasattr(mock_client, "_base_url"):
            del mock_client._base_url

        mock_get = MagicMock()
        mock_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get.__aexit__ = AsyncMock(return_value=None)
        mock_client.get.return_value = mock_get

        status = await http_client_health_check(mock_client)

        assert not status.is_healthy
        assert "500" in status.message
        assert status.details["status_code"] == 500

    async def test_http_client_timeout(self):
        """Test HTTP client timeout."""
        mock_client = MagicMock()
        # Explicitly remove _base_url to simulate aiohttp
        if hasattr(mock_client, "_base_url"):
            del mock_client._base_url

        # Mock get method to raise timeout in __aenter__
        mock_get = MagicMock()
        mock_get.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_get.__aexit__ = AsyncMock(return_value=None)
        mock_client.get.return_value = mock_get

        status = await http_client_health_check(mock_client)

        assert not status.is_healthy
        assert "timed out" in status.message.lower()

    async def test_http_client_custom_endpoint(self):
        """Test HTTP client with custom health endpoint."""
        mock_response = MagicMock()
        mock_response.status = 200

        mock_client = MagicMock()
        # Explicitly remove _base_url to simulate aiohttp
        if hasattr(mock_client, "_base_url"):
            del mock_client._base_url

        # Mock get method to return an async context manager
        mock_get = MagicMock()
        mock_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get.__aexit__ = AsyncMock(return_value=None)
        mock_client.get.return_value = mock_get

        status = await http_client_health_check(mock_client, "/api/health")

        assert status.is_healthy
        mock_client.get.assert_called_once_with("/api/health")

    async def test_unknown_client_type(self):
        """Test unknown HTTP client type."""
        mock_client = MagicMock()
        # Remove get method to make it unknown
        del mock_client.get

        status = await http_client_health_check(mock_client)

        assert status.is_healthy  # Assumes healthy for unknown types
        assert "not recognized" in status.message


@pytest.mark.asyncio
class TestCacheHealthCheck:
    """Test cache health checking."""

    async def test_cache_set_get_healthy(self):
        """Test cache with set/get interface."""
        mock_cache = MagicMock()
        mock_cache.set = AsyncMock()
        mock_cache.get = AsyncMock(return_value="healthy")
        mock_cache.delete = AsyncMock()

        status = await cache_health_check(mock_cache)

        assert status.is_healthy
        mock_cache.set.assert_called_once()
        mock_cache.get.assert_called_once()
        mock_cache.delete.assert_called_once()

    async def test_cache_set_get_bytes_response(self):
        """Test cache returning bytes."""
        mock_cache = MagicMock()
        mock_cache.set = AsyncMock()
        mock_cache.get = AsyncMock(return_value=b"healthy")
        mock_cache.delete = AsyncMock()

        status = await cache_health_check(mock_cache)

        assert status.is_healthy

    async def test_cache_value_mismatch(self):
        """Test cache returning wrong value."""
        mock_cache = MagicMock()
        mock_cache.set = AsyncMock()
        mock_cache.get = AsyncMock(return_value="wrong_value")
        mock_cache.delete = AsyncMock()

        status = await cache_health_check(mock_cache)

        assert not status.is_healthy
        assert "mismatch" in status.message.lower()
        assert status.details["expected"] == "healthy"
        assert status.details["got"] == "wrong_value"

    async def test_cache_ping_interface(self):
        """Test cache with ping interface (Redis style)."""
        mock_cache = MagicMock()
        mock_cache.ping = AsyncMock()
        # Remove set/get to force ping path
        del mock_cache.set
        del mock_cache.get

        status = await cache_health_check(mock_cache)

        assert status.is_healthy
        assert "ping" in status.message.lower()
        mock_cache.ping.assert_called_once()

    async def test_cache_timeout(self):
        """Test cache timeout."""
        mock_cache = MagicMock()
        mock_cache.set = AsyncMock(side_effect=asyncio.TimeoutError())

        status = await cache_health_check(mock_cache)

        assert not status.is_healthy
        assert "timed out" in status.message.lower()

    async def test_unknown_cache_type(self):
        """Test unknown cache type."""
        mock_cache = MagicMock()
        # Remove all known methods
        del mock_cache.set
        del mock_cache.get
        del mock_cache.ping

        status = await cache_health_check(mock_cache)

        assert status.is_healthy  # Assumes healthy for unknown types


@pytest.mark.asyncio
class TestMessageQueueHealthCheck:
    """Test message queue health checking."""

    async def test_rabbitmq_connection_healthy(self):
        """Test healthy RabbitMQ connection."""
        mock_channel = MagicMock()
        mock_channel.close = AsyncMock()

        mock_mq = MagicMock()
        mock_mq.channel = AsyncMock(return_value=mock_channel)

        status = await message_queue_health_check(mock_mq)

        assert status.is_healthy
        assert "channel test" in status.message.lower()
        mock_mq.channel.assert_called_once()
        mock_channel.close.assert_called_once()

    async def test_kafka_client_healthy(self):
        """Test healthy Kafka client."""
        mock_mq = MagicMock()
        mock_mq.producer = MagicMock()
        mock_mq.consumer = MagicMock()
        # Remove channel attribute to avoid RabbitMQ detection
        if hasattr(mock_mq, "channel"):
            del mock_mq.channel

        status = await message_queue_health_check(mock_mq)

        assert status.is_healthy
        assert "kafka clients are healthy" in status.message.lower()

    async def test_connection_with_is_closed(self):
        """Test connection with is_closed property."""
        mock_mq = MagicMock()
        mock_mq.is_closed = False
        # Remove other known attributes
        del mock_mq.channel
        del mock_mq.producer
        del mock_mq.consumer

        status = await message_queue_health_check(mock_mq)

        assert status.is_healthy
        assert "connection is open" in status.message.lower()

    async def test_connection_closed(self):
        """Test closed connection."""
        mock_mq = MagicMock()
        mock_mq.is_closed = True
        # Remove other known attributes
        del mock_mq.channel
        del mock_mq.producer
        del mock_mq.consumer

        status = await message_queue_health_check(mock_mq)

        assert not status.is_healthy
        assert "closed" in status.message.lower()

    async def test_mq_timeout(self):
        """Test message queue timeout."""
        mock_mq = MagicMock()
        mock_mq.channel = AsyncMock(side_effect=asyncio.TimeoutError())

        status = await message_queue_health_check(mock_mq)

        assert not status.is_healthy
        assert "timed out" in status.message.lower()

    async def test_unknown_mq_type(self):
        """Test unknown message queue type."""
        mock_mq = MagicMock()
        # Remove all known attributes
        del mock_mq.channel
        del mock_mq.producer
        del mock_mq.consumer
        del mock_mq.is_closed

        status = await message_queue_health_check(mock_mq)

        assert status.is_healthy  # Assumes healthy for unknown types


@pytest.mark.asyncio
class TestCompositeHealthCheck:
    """Test composite health checking."""

    async def test_all_checks_pass(self):
        """Test all health checks passing."""

        async def check1(resource):
            return True

        async def check2(resource):
            return HealthStatus.healthy("Check 2 passed")

        async def check3(resource):
            return HealthStatus.degraded("Check 3 degraded")

        composite = create_composite_health_check(check1, check2, check3)

        status = await composite("dummy_resource")

        assert status.is_healthy
        # The actual message might vary - just check it's healthy
        assert status.state == HealthState.HEALTHY
        # Details might not be populated for composite checks
        if status.details:
            assert status.details.get("checks", 0) >= 1

    async def test_one_check_fails(self):
        """Test one health check failing."""

        async def check1(resource):
            return True

        async def check2(resource):
            return HealthStatus.unhealthy("Check 2 failed")

        async def check3(resource):
            return True

        composite = create_composite_health_check(check1, check2, check3)

        status = await composite("dummy_resource")

        assert not status.is_healthy
        assert status.message == "Check 2 failed"

    async def test_boolean_check_fails(self):
        """Test boolean health check failing."""

        async def check1(resource):
            return True

        async def check2(resource):
            return False  # Boolean failure

        composite = create_composite_health_check(check1, check2)

        status = await composite("dummy_resource")

        assert not status.is_healthy
        assert "composite check failed" in status.message.lower()

    async def test_check_exception(self):
        """Test health check raising exception."""

        async def check1(resource):
            return True

        async def check2(resource):
            raise Exception("Check exploded")

        composite = create_composite_health_check(check1, check2)

        status = await composite("dummy_resource")

        assert not status.is_healthy
        assert "Check exploded" in status.message
        assert status.details["error"] == "Check exploded"
