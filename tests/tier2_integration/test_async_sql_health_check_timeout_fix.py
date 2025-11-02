"""
Tier 2 Integration Test: Verify health_check() timeout parameter fix.

This test verifies that EnterpriseConnectionPool.health_check() works correctly
without passing a timeout parameter to adapter.execute().

Bug: #TIMEOUT_PARAMETER_BUG
Fix: Removed timeout=5 from health_check() execute_query() call
Reason: Pool-level command_timeout already provides timeout protection
"""

import asyncio
import os

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.test")

pytestmark = [pytest.mark.tier2, pytest.mark.integration]


@pytest.mark.asyncio
async def test_postgresql_health_check_no_timeout_error():
    """Test that PostgreSQL health check doesn't raise TypeError about timeout."""
    from kailash.nodes.data.async_sql import (
        DatabaseConfig,
        DatabaseType,
        EnterpriseConnectionPool,
    )

    # Get PostgreSQL connection string
    pg_url = os.getenv("POSTGRES_TEST_URL")
    if not pg_url:
        pytest.skip("POSTGRES_TEST_URL not set in .env.test")

    # Create connection pool with real PostgreSQL
    config = DatabaseConfig(
        type=DatabaseType.POSTGRESQL,
        connection_string=pg_url,
        max_pool_size=5,
        pool_timeout=30,
        command_timeout=60,  # This provides timeout protection
    )

    pool = EnterpriseConnectionPool(
        config=config, pool_id="test_health_check", enable_health_checks=True
    )

    try:
        # Initialize pool
        await pool.initialize()

        # Run health check - should NOT raise TypeError about timeout parameter
        health_result = await pool.health_check()

        # Verify health check succeeded
        assert (
            health_result.is_healthy
        ), f"Health check failed: {health_result.error_message}"
        assert health_result.latency_ms > 0
        assert (
            health_result.latency_ms < 1000
        ), f"Health check too slow: {health_result.latency_ms}ms"

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_mysql_health_check_no_timeout_error():
    """Test that MySQL health check doesn't raise TypeError about timeout."""
    from kailash.nodes.data.async_sql import (
        DatabaseConfig,
        DatabaseType,
        EnterpriseConnectionPool,
    )

    # Get MySQL connection string
    mysql_url = os.getenv("MYSQL_TEST_URL")
    if not mysql_url:
        pytest.skip("MYSQL_TEST_URL not set in .env.test")

    config = DatabaseConfig(
        type=DatabaseType.MYSQL,
        connection_string=mysql_url,
        max_pool_size=5,
        pool_timeout=30,
        command_timeout=60,
    )

    pool = EnterpriseConnectionPool(
        config=config, pool_id="test_mysql_health_check", enable_health_checks=True
    )

    try:
        await pool.initialize()
        health_result = await pool.health_check()

        assert (
            health_result.is_healthy
        ), f"Health check failed: {health_result.error_message}"
        assert health_result.latency_ms > 0

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_sqlite_health_check_no_timeout_error():
    """Test that SQLite health check doesn't raise TypeError about timeout."""
    from kailash.nodes.data.async_sql import (
        DatabaseConfig,
        DatabaseType,
        EnterpriseConnectionPool,
    )

    # Use in-memory SQLite
    config = DatabaseConfig(
        type=DatabaseType.SQLITE,
        connection_string=":memory:",
        max_pool_size=5,
        pool_timeout=30,
        command_timeout=60,
    )

    pool = EnterpriseConnectionPool(
        config=config, pool_id="test_sqlite_health_check", enable_health_checks=True
    )

    try:
        await pool.initialize()
        health_result = await pool.health_check()

        assert health_result.is_healthy
        assert health_result.latency_ms > 0

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_pool_command_timeout_protects_slow_queries():
    """Verify that pool-level command_timeout still protects against slow queries."""
    from kailash.nodes.data.async_sql import (
        DatabaseConfig,
        DatabaseType,
        EnterpriseConnectionPool,
    )

    pg_url = os.getenv("POSTGRES_TEST_URL")
    if not pg_url:
        pytest.skip("POSTGRES_TEST_URL not set in .env.test")

    # Create pool with very short command_timeout
    config = DatabaseConfig(
        type=DatabaseType.POSTGRESQL,
        connection_string=pg_url,
        max_pool_size=5,
        pool_timeout=30,
        command_timeout=1,  # 1 second timeout
    )

    pool = EnterpriseConnectionPool(
        config=config,
        pool_id="test_timeout_protection",
        enable_health_checks=False,  # Disable auto health checks
    )

    try:
        await pool.initialize()

        # Try to run a query that takes longer than command_timeout
        with pytest.raises((asyncio.TimeoutError, Exception)) as exc_info:
            await pool.execute_query("SELECT pg_sleep(5)")  # 5 second sleep

        # Verify it timed out (could be TimeoutError or QueryError wrapping it)
        assert (
            "timeout" in str(exc_info.value).lower()
            or "cancel" in str(exc_info.value).lower()
        )

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_health_check_performance():
    """Verify health check completes quickly (< 100ms for in-memory DB)."""
    import time

    from kailash.nodes.data.async_sql import (
        DatabaseConfig,
        DatabaseType,
        EnterpriseConnectionPool,
    )

    config = DatabaseConfig(
        type=DatabaseType.SQLITE,
        connection_string=":memory:",
        max_pool_size=5,
        pool_timeout=30,
        command_timeout=60,
    )

    pool = EnterpriseConnectionPool(
        config=config, pool_id="test_performance", enable_health_checks=True
    )

    try:
        await pool.initialize()

        # Run multiple health checks and measure average time
        times = []
        for _ in range(10):
            start = time.time()
            health_result = await pool.health_check()
            duration = (time.time() - start) * 1000  # Convert to ms

            assert health_result.is_healthy
            times.append(duration)

        avg_time = sum(times) / len(times)
        assert avg_time < 100, f"Health check too slow: {avg_time:.2f}ms average"

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_multiple_concurrent_health_checks():
    """Verify multiple concurrent health checks work correctly."""
    from kailash.nodes.data.async_sql import (
        DatabaseConfig,
        DatabaseType,
        EnterpriseConnectionPool,
    )

    pg_url = os.getenv("POSTGRES_TEST_URL")
    if not pg_url:
        pytest.skip("POSTGRES_TEST_URL not set in .env.test")

    config = DatabaseConfig(
        type=DatabaseType.POSTGRESQL,
        connection_string=pg_url,
        max_pool_size=5,
        pool_timeout=30,
        command_timeout=60,
    )

    pool = EnterpriseConnectionPool(
        config=config, pool_id="test_concurrent", enable_health_checks=True
    )

    try:
        await pool.initialize()

        # Run 10 health checks concurrently
        tasks = [pool.health_check() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r.is_healthy for r in results)
        assert all(r.latency_ms > 0 for r in results)

    finally:
        await pool.close()
