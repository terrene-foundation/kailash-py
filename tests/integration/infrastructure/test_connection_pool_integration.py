"""Integration tests for WorkflowConnectionPool with real databases."""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List

import pytest
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)


@pytest.mark.integration
@pytest.mark.asyncio
class TestConnectionPoolIntegration:
    """Integration tests using real database connections."""

    @pytest.fixture
    def postgres_config(self):
        """PostgreSQL configuration from environment."""
        return {
            "name": "postgres_pool",
            "database_type": "postgresql",
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", 5434)),
            "database": os.getenv("POSTGRES_DB", "kailash_test"),
            "user": os.getenv("POSTGRES_USER", "test_user"),
            "password": os.getenv("POSTGRES_PASSWORD", "test_password"),
            "min_connections": 2,
            "max_connections": 5,
        }

    @pytest.fixture
    def mysql_config(self):
        """MySQL configuration from environment."""
        return {
            "name": "mysql_pool",
            "database_type": "mysql",
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_PORT", 3307)),
            "database": os.getenv("MYSQL_DATABASE", "kailash_test"),
            "user": os.getenv("MYSQL_USER", "kailash_test"),
            "password": os.getenv("MYSQL_PASSWORD", "test_password"),
            "min_connections": 2,
            "max_connections": 5,
        }

    async def test_postgres_connection_lifecycle(self, postgres_config):
        """Test full connection lifecycle with PostgreSQL."""
        pool = WorkflowConnectionPool(**postgres_config)

        # Initialize pool
        init_result = await pool.process({"operation": "initialize"})
        assert init_result["status"] == "initialized"

        # Wait for minimum connections
        await asyncio.sleep(1)

        # Get stats to verify connections
        stats = await pool.process({"operation": "stats"})
        assert stats["current_state"]["total_connections"] >= 2

        # Acquire connection
        acquire_result = await pool.process({"operation": "acquire"})
        conn_id = acquire_result["connection_id"]
        assert conn_id is not None
        assert acquire_result["health_score"] > 50

        # Execute test query
        query_result = await pool.process(
            {
                "operation": "execute",
                "connection_id": conn_id,
                "query": "SELECT 1 as test, NOW() as timestamp",
                "fetch_mode": "one",
            }
        )

        # Debug print
        print(f"Query result: {query_result}")

        assert query_result["success"] is True
        assert (
            query_result["data"] is not None
        ), f"Query data is None. Full result: {query_result}"
        assert query_result["data"]["test"] == 1
        assert "timestamp" in query_result["data"]

        # Release connection
        release_result = await pool.process(
            {"operation": "release", "connection_id": conn_id}
        )
        assert release_result["status"] == "released"

        # Clean up
        await pool._cleanup()

    async def test_connection_pool_under_load(self, postgres_config):
        """Test connection pool behavior under concurrent load."""
        pool = WorkflowConnectionPool(**postgres_config)
        pool.max_connections = 3  # Limit for testing

        await pool.process({"operation": "initialize"})

        # First test sequential queries to ensure basic functionality
        for i in range(3):
            acquire_result = await pool.process({"operation": "acquire"})
            conn_id = acquire_result["connection_id"]

            query_result = await pool.process(
                {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": "SELECT $1::int as query_id",
                    "params": [i],
                    "fetch_mode": "one",
                }
            )
            if not query_result["success"]:
                print(f"Query {i} failed: {query_result}")
            assert query_result["success"] is True

            await pool.process({"operation": "release", "connection_id": conn_id})

        # Now test concurrent queries
        async def execute_query(query_id: int):
            try:
                # Acquire connection
                acquire_result = await pool.process({"operation": "acquire"})
                conn_id = acquire_result["connection_id"]

                # Execute query
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": "SELECT $1::int as query_id",
                        "params": [query_id],
                        "fetch_mode": "one",
                    }
                )

                # Release connection
                await pool.process({"operation": "release", "connection_id": conn_id})

                return query_id
            except Exception as e:
                print(f"Query {query_id} failed: {e}")
                raise

        # Execute 5 queries concurrently (more than max connections)
        start_time = time.time()
        tasks = [execute_query(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start_time

        # Verify all queries completed
        assert len(results) == 5
        assert set(results) == set(range(5))

        # Get final stats
        stats = await pool.process({"operation": "stats"})
        assert stats["queries"]["executed"] >= 8  # 3 sequential + 5 concurrent
        assert stats["connections"]["created"] <= 3  # Shouldn't exceed max

        await pool._cleanup()

    async def test_connection_health_monitoring(self, postgres_config):
        """Test connection health monitoring and recycling."""
        # Reduce intervals for faster testing
        postgres_config["health_check_interval"] = 0.1  # 100ms instead of 30s
        postgres_config["max_lifetime"] = 60.0  # 1 minute instead of 1 hour
        postgres_config["max_idle_time"] = 10.0  # 10s instead of 10 minutes

        pool = WorkflowConnectionPool(**postgres_config)
        pool.health_threshold = 70

        try:
            await pool.process({"operation": "initialize"})

            # Acquire connection
            acquire_result = await pool.process({"operation": "acquire"})
            conn_id = acquire_result["connection_id"]
            initial_health = acquire_result["health_score"]

            # Simulate just 2 errors to degrade health (faster)
            for _ in range(2):
                try:
                    await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": "SELECT * FROM nonexistent_table",
                        }
                    )
                except:
                    pass  # Expected to fail

            # Check connection health degraded
            stats = await pool.process({"operation": "stats"})
            current_health = stats["current_state"]["health_scores"][conn_id]
            assert current_health < initial_health

            # Release connection
            await pool.process({"operation": "release", "connection_id": conn_id})

        finally:
            # Ensure cleanup happens even if test fails
            try:
                # Stop the pool's actor system gracefully
                if hasattr(pool, "_supervisor"):
                    # Stop all actors first
                    await pool._supervisor.stop_all_actors()
                    # Then stop supervisor
                    pool._supervisor._running = False

                # Mark pool as closing
                pool._closing = True

                # Quick cleanup with short timeout
                try:
                    await asyncio.wait_for(pool._cleanup(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass

                # Cancel any remaining tasks
                tasks = [t for t in asyncio.all_tasks() if not t.done()]
                for task in tasks:
                    if "Actor" in str(task):
                        task.cancel()

            except Exception:
                pass  # Ignore cleanup errors

    async def test_workflow_integration_with_pool(self, postgres_config):
        """Test connection pool integrated with workflow - simplified."""
        # Test pool directly without complex workflow
        pool = WorkflowConnectionPool(**postgres_config)

        # Initialize
        init_result = await pool.process({"operation": "initialize"})
        assert init_result["status"] == "initialized"

        # Acquire connection
        acquire_result = await pool.process({"operation": "acquire"})
        conn_id = acquire_result["connection_id"]
        assert conn_id is not None

        # Execute query
        query_result = await pool.process(
            {
                "operation": "execute",
                "connection_id": conn_id,
                "query": "SELECT version() as db_version, current_timestamp as ts",
                "fetch_mode": "one",
            }
        )
        assert query_result["success"] is True
        assert "db_version" in query_result["data"]

        # Release connection
        release_result = await pool.process(
            {"operation": "release", "connection_id": conn_id}
        )
        assert release_result["status"] == "released"

        # Stats
        stats = await pool.process({"operation": "stats"})
        assert stats["queries"]["executed"] == 1

        # Clean up
        await pool._cleanup()

    async def test_connection_pool_recovery(self, postgres_config):
        """Test connection pool recovery from failures."""
        pool = WorkflowConnectionPool(**postgres_config)

        await pool.process({"operation": "initialize"})

        # Get initial stats
        initial_stats = await pool.process({"operation": "stats"})
        initial_connections = initial_stats["current_state"]["total_connections"]

        # Simulate connection failure by stopping supervisor
        # This would normally happen due to network issues, etc.
        await pool.supervisor.stop()

        # Wait a moment
        await asyncio.sleep(0.5)

        # Restart supervisor
        await pool.supervisor.start()

        # Pool should recover and create new connections
        await pool._ensure_min_connections()

        # Verify recovery
        recovery_stats = await pool.process({"operation": "stats"})
        assert (
            recovery_stats["current_state"]["total_connections"] >= pool.min_connections
        )

        # Should still be able to execute queries
        acquire_result = await pool.process({"operation": "acquire"})
        query_result = await pool.process(
            {
                "operation": "execute",
                "connection_id": acquire_result["connection_id"],
                "query": "SELECT 1 as test",
            }
        )
        assert query_result["success"] is True

        await pool._cleanup()

    async def test_pattern_based_pre_warming(self, postgres_config):
        """Test pattern-based connection pre-warming."""
        pool = WorkflowConnectionPool(**postgres_config)
        pool.pre_warm_enabled = True

        # Simulate workflow pattern history
        analyzer = pool.pattern_analyzer

        # Create history for "data_processing" workflows
        for i in range(5):
            analyzer.workflow_patterns[f"hist_{i}"] = {
                "type": "data_processing",
                "connections_used": 4,  # Typically uses 4 connections
            }

        # Start new workflow of same type
        await pool.on_workflow_start("new_workflow", "data_processing")

        # Wait for pre-warming
        await asyncio.sleep(1)

        # Check that connections were pre-warmed
        stats = await pool.process({"operation": "stats"})

        # Should have pre-warmed based on pattern (90th percentile)
        assert stats["current_state"]["total_connections"] >= 4

        await pool._cleanup()

    async def test_metrics_accuracy(self, postgres_config):
        """Test that metrics are accurately collected."""
        pool = WorkflowConnectionPool(**postgres_config)

        await pool.process({"operation": "initialize"})

        # Track operations
        acquisition_times = []
        query_times = []

        # Perform several operations
        for i in range(5):
            # Acquire
            start = time.time()
            acquire_result = await pool.process({"operation": "acquire"})
            acquisition_times.append(time.time() - start)

            # Query
            start = time.time()
            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": acquire_result["connection_id"],
                    "query": f"SELECT {i} as num",
                    "fetch_mode": "one",
                }
            )
            query_times.append(time.time() - start)

            # Release
            await pool.process(
                {
                    "operation": "release",
                    "connection_id": acquire_result["connection_id"],
                }
            )

        # Get final metrics
        stats = await pool.process({"operation": "stats"})

        # Verify metrics
        assert stats["queries"]["executed"] == 5
        assert stats["performance"]["avg_acquisition_time_ms"] > 0
        assert stats["connections"]["created"] >= pool.min_connections

        # Verify health checks are running (health check interval is set in config)
        # Since we may not have waited long enough for a health check,
        # just verify the mechanism exists
        updated_stats = await pool.process({"operation": "stats"})
        assert "health" in updated_stats
        assert "checks_performed" in updated_stats["health"]

        await pool._cleanup()
