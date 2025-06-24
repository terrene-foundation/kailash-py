"""
Health Check System - Monitor and maintain resource health.

This module provides health checking functionality for resources in the registry,
enabling automatic recovery and circuit breaker patterns.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Protocol, Union


class HealthCheckProtocol(Protocol):
    """Protocol for health check callables."""

    async def __call__(self, resource: Any) -> Union[bool, "HealthStatus"]:
        """
        Check if a resource is healthy.

        Args:
            resource: The resource to check

        Returns:
            bool or HealthStatus indicating health
        """
        ...


# Type alias for health checks
HealthCheck = HealthCheckProtocol


class HealthState(Enum):
    """Health states for resources."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthStatus:
    """
    Detailed health status for a resource.

    This provides more information than a simple boolean,
    allowing for degraded states and detailed diagnostics.
    """

    state: HealthState
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def is_healthy(self) -> bool:
        """Check if status indicates health."""
        return self.state in (HealthState.HEALTHY, HealthState.DEGRADED)

    @classmethod
    def healthy(cls, message: str = "Resource is healthy") -> "HealthStatus":
        """Create a healthy status."""
        return cls(HealthState.HEALTHY, message)

    @classmethod
    def unhealthy(cls, message: str, details: Dict[str, Any] = None) -> "HealthStatus":
        """Create an unhealthy status."""
        return cls(HealthState.UNHEALTHY, message, details)

    @classmethod
    def degraded(cls, message: str, details: Dict[str, Any] = None) -> "HealthStatus":
        """Create a degraded status."""
        return cls(HealthState.DEGRADED, message, details)


# Common health checks


async def database_health_check(pool) -> HealthStatus:
    """
    Health check for database connection pools.

    Args:
        pool: Database connection pool

    Returns:
        HealthStatus indicating database health
    """
    try:
        # Try to acquire a connection
        if hasattr(pool, "acquire"):
            # asyncpg style
            async with pool.acquire() as conn:
                # Try a simple query
                if hasattr(conn, "fetchval"):
                    await conn.fetchval("SELECT 1")
                elif hasattr(conn, "execute"):
                    await conn.execute("SELECT 1")
        elif hasattr(pool, "ping"):
            # Some pools have a ping method
            await pool.ping()
        elif hasattr(pool, "execute"):
            # aiosqlite style
            await pool.execute("SELECT 1")

        return HealthStatus.healthy("Database connection is healthy")

    except asyncio.TimeoutError:
        return HealthStatus.unhealthy(
            "Database connection timed out", {"error": "timeout"}
        )
    except Exception as e:
        return HealthStatus.unhealthy(
            f"Database health check failed: {str(e)}",
            {"error": str(e), "type": type(e).__name__},
        )


async def http_client_health_check(
    client, health_endpoint: str = "/health"
) -> HealthStatus:
    """
    Health check for HTTP clients.

    Args:
        client: HTTP client (aiohttp or httpx)
        health_endpoint: Endpoint to check

    Returns:
        HealthStatus indicating HTTP client health
    """
    try:
        # Handle different client types
        if hasattr(client, "get"):
            # aiohttp or httpx style
            if hasattr(client, "_base_url"):
                # httpx
                response = await client.get(health_endpoint)
                status_code = response.status_code
            else:
                # aiohttp
                async with client.get(health_endpoint) as response:
                    status_code = response.status

            if 200 <= status_code < 300:
                return HealthStatus.healthy(
                    f"HTTP client is healthy (status: {status_code})"
                )
            else:
                return HealthStatus.unhealthy(
                    f"HTTP health check returned {status_code}",
                    {"status_code": status_code},
                )
        else:
            # Unknown client type, assume healthy
            return HealthStatus.healthy(
                "HTTP client type not recognized, assuming healthy"
            )

    except asyncio.TimeoutError:
        return HealthStatus.unhealthy(
            "HTTP health check timed out", {"error": "timeout"}
        )
    except Exception as e:
        return HealthStatus.unhealthy(
            f"HTTP health check failed: {str(e)}",
            {"error": str(e), "type": type(e).__name__},
        )


async def cache_health_check(cache) -> HealthStatus:
    """
    Health check for cache clients.

    Args:
        cache: Cache client (Redis, Memcached, etc.)

    Returns:
        HealthStatus indicating cache health
    """
    try:
        test_key = "_health_check_test"
        test_value = "healthy"

        # Try to set and get a value
        if hasattr(cache, "set") and hasattr(cache, "get"):
            await cache.set(test_key, test_value)
            result = await cache.get(test_key)

            if result == test_value or (
                isinstance(result, bytes) and result.decode() == test_value
            ):
                # Clean up
                if hasattr(cache, "delete"):
                    await cache.delete(test_key)
                return HealthStatus.healthy("Cache is healthy")
            else:
                return HealthStatus.unhealthy(
                    "Cache health check failed: value mismatch",
                    {"expected": test_value, "got": result},
                )
        elif hasattr(cache, "ping"):
            # Redis style ping
            await cache.ping()
            return HealthStatus.healthy("Cache is healthy (ping successful)")
        else:
            # Unknown cache type
            return HealthStatus.healthy("Cache type not recognized, assuming healthy")

    except asyncio.TimeoutError:
        return HealthStatus.unhealthy(
            "Cache health check timed out", {"error": "timeout"}
        )
    except Exception as e:
        return HealthStatus.unhealthy(
            f"Cache health check failed: {str(e)}",
            {"error": str(e), "type": type(e).__name__},
        )


async def message_queue_health_check(mq) -> HealthStatus:
    """
    Health check for message queue clients.

    Args:
        mq: Message queue client

    Returns:
        HealthStatus indicating message queue health
    """
    try:
        # RabbitMQ (aio-pika)
        if hasattr(mq, "channel"):
            channel = await mq.channel()
            await channel.close()
            return HealthStatus.healthy(
                "Message queue is healthy (channel test successful)"
            )

        # Kafka
        elif hasattr(mq, "producer") and hasattr(mq, "consumer"):
            # Custom Kafka client from factory
            # Just check if they exist
            return HealthStatus.healthy("Kafka clients are healthy")

        # Generic check
        elif hasattr(mq, "is_closed"):
            if not mq.is_closed:
                return HealthStatus.healthy("Message queue connection is open")
            else:
                return HealthStatus.unhealthy("Message queue connection is closed")

        else:
            # Unknown MQ type
            return HealthStatus.healthy(
                "Message queue type not recognized, assuming healthy"
            )

    except asyncio.TimeoutError:
        return HealthStatus.unhealthy(
            "Message queue health check timed out", {"error": "timeout"}
        )
    except Exception as e:
        return HealthStatus.unhealthy(
            f"Message queue health check failed: {str(e)}",
            {"error": str(e), "type": type(e).__name__},
        )


def create_composite_health_check(*checks: HealthCheck) -> HealthCheck:
    """
    Create a composite health check from multiple checks.

    All checks must pass for the resource to be considered healthy.

    Args:
        *checks: Health check functions

    Returns:
        Composite health check function

    Example:
        ```python
        health_check = create_composite_health_check(
            lambda r: database_health_check(r.db),
            lambda r: cache_health_check(r.cache)
        )
        ```
    """

    async def composite_check(resource: Any) -> HealthStatus:
        results = []

        for check in checks:
            try:
                result = await check(resource)
                if isinstance(result, bool):
                    if not result:
                        return HealthStatus.unhealthy("Composite check failed")
                elif isinstance(result, HealthStatus):
                    if not result.is_healthy:
                        return result
                    results.append(result)
            except Exception as e:
                return HealthStatus.unhealthy(
                    f"Health check error: {str(e)}", {"error": str(e)}
                )

        # All checks passed
        return HealthStatus.healthy("All health checks passed")

    return composite_check
