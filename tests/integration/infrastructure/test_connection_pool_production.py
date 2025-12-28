"""Production-grade integration tests for WorkflowConnectionPool.

These tests simulate real-world scenarios with high concurrency, failures,
and complex query patterns that would be encountered in production.
"""

import asyncio
import os
import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.sdk_exceptions import NodeExecutionError


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.slow
class TestConnectionPoolProduction:
    """Production-grade integration tests with demanding scenarios."""

    @pytest.fixture
    def postgres_config(self):
        """PostgreSQL configuration for production testing."""
        return {
            "name": "production_pool",
            "database_type": "postgresql",
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", 5434)),
            "database": os.getenv("POSTGRES_DB", "kailash_test"),
            "user": os.getenv("POSTGRES_USER", "test_user"),
            "password": os.getenv("POSTGRES_PASSWORD", "test_password"),
            "min_connections": 5,
            "max_connections": 20,
            "health_threshold": 60,
            "pre_warm": True,
        }

    async def test_high_concurrency_mixed_workload(self, postgres_config):
        """Test pool under high concurrency with mixed query patterns."""
        pool = WorkflowConnectionPool(**postgres_config)
        await pool.process({"operation": "initialize"})

        # Create test table
        setup_conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": setup_conn["connection_id"],
                "query": """
                CREATE TABLE IF NOT EXISTS load_test (
                    id SERIAL PRIMARY KEY,
                    user_id UUID,
                    action VARCHAR(50),
                    data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
                "fetch_mode": "one",
            }
        )

        # Create indexes for realistic performance
        await pool.process(
            {
                "operation": "execute",
                "connection_id": setup_conn["connection_id"],
                "query": "CREATE INDEX IF NOT EXISTS idx_user_id ON load_test(user_id)",
                "fetch_mode": "one",
            }
        )

        await pool.process(
            {"operation": "release", "connection_id": setup_conn["connection_id"]}
        )

        # Simulate mixed workload
        async def simulate_user_session(session_id: int):
            """Simulate a realistic user session with multiple operations."""
            user_id = str(uuid.uuid4())
            results = []

            try:
                # Acquire connection for session
                conn_result = await pool.process({"operation": "acquire"})
                conn_id = conn_result["connection_id"]

                # Insert user actions (simulating writes)
                for i in range(random.randint(3, 10)):
                    action = random.choice(["view", "click", "purchase", "search"])
                    await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": """
                            INSERT INTO load_test (user_id, action, data)
                            VALUES ($1::uuid, $2, $3::jsonb)
                            RETURNING id
                        """,
                            "params": [
                                user_id,
                                action,
                                f'{{"session": {session_id}, "step": {i}}}',
                            ],
                            "fetch_mode": "one",
                        }
                    )

                    # Simulate think time
                    await asyncio.sleep(random.uniform(0.01, 0.05))

                # Read operations (simulating analytics queries)
                analytics_result = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": """
                        SELECT action, COUNT(*) as count
                        FROM load_test
                        WHERE user_id = $1::uuid
                        GROUP BY action
                    """,
                        "params": [user_id],
                        "fetch_mode": "all",
                    }
                )
                results.append(analytics_result)

                # Complex aggregation query
                if random.random() > 0.7:  # 30% of sessions do heavy analytics
                    heavy_result = await pool.process(
                        {
                            "operation": "execute",
                            "connection_id": conn_id,
                            "query": """
                            WITH user_stats AS (
                                SELECT
                                    user_id,
                                    COUNT(*) as action_count,
                                    COUNT(DISTINCT action) as unique_actions,
                                    MAX(created_at) as last_action
                                FROM load_test
                                WHERE created_at > NOW() - INTERVAL '1 hour'
                                GROUP BY user_id
                            )
                            SELECT
                                COUNT(*) as active_users,
                                AVG(action_count) as avg_actions_per_user,
                                MAX(action_count) as max_actions
                            FROM user_stats
                        """,
                            "fetch_mode": "one",
                        }
                    )
                    results.append(heavy_result)

                # Release connection
                await pool.process({"operation": "release", "connection_id": conn_id})

                return {"session_id": session_id, "success": True, "results": results}

            except Exception as e:
                return {"session_id": session_id, "success": False, "error": str(e)}

        # Run high concurrency test
        start_time = time.time()
        concurrent_sessions = 100  # Simulate 100 concurrent user sessions

        tasks = [simulate_user_session(i) for i in range(concurrent_sessions)]
        results = await asyncio.gather(*tasks)

        elapsed_time = time.time() - start_time

        # Analyze results
        successful_sessions = sum(1 for r in results if r["success"])
        failed_sessions = sum(1 for r in results if not r["success"])

        # Get final stats
        stats = await pool.process({"operation": "stats"})

        # Assertions
        assert (
            successful_sessions >= concurrent_sessions * 0.95
        )  # At least 95% success rate
        assert stats["connections"]["created"] <= postgres_config["max_connections"]
        assert (
            stats["queries"]["executed"] > concurrent_sessions * 3
        )  # Multiple queries per session
        assert stats["queries"]["error_rate"] < 0.05  # Less than 5% error rate

        # Performance assertions
        avg_time_per_session = elapsed_time / concurrent_sessions
        assert (
            avg_time_per_session < 1.0
        )  # Each session should complete in under 1 second on average

        # Cleanup
        cleanup_conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": cleanup_conn["connection_id"],
                "query": "DROP TABLE IF EXISTS load_test",
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": cleanup_conn["connection_id"]}
        )

        await pool._cleanup()

        print(
            f"""
High Concurrency Test Results:
- Total Sessions: {concurrent_sessions}
- Successful: {successful_sessions}
- Failed: {failed_sessions}
- Total Time: {elapsed_time:.2f}s
- Avg Time/Session: {avg_time_per_session:.3f}s
- Queries Executed: {stats['queries']['executed']}
- Error Rate: {stats['queries']['error_rate']:.2%}
- Connections Created: {stats['connections']['created']}
- Pool Efficiency: {stats['queries']['executed'] / stats['connections']['created']:.1f} queries/connection
        """
        )

    async def test_connection_failure_recovery(self, postgres_config):
        """Test pool behavior under connection failures and recovery."""
        pool = WorkflowConnectionPool(**postgres_config)
        await pool.process({"operation": "initialize"})

        # Track metrics
        query_results = []
        failure_points = []

        async def execute_with_tracking(operation: str, **kwargs):
            """Execute operation and track results."""
            start = time.time()
            try:
                result = await pool.process({"operation": operation, **kwargs})
                query_results.append(
                    {
                        "time": time.time() - start,
                        "success": True,
                        "operation": operation,
                    }
                )
                return result
            except Exception as e:
                query_results.append(
                    {
                        "time": time.time() - start,
                        "success": False,
                        "operation": operation,
                        "error": str(e),
                    }
                )
                failure_points.append(len(query_results) - 1)
                raise

        # Normal operations
        for i in range(10):
            conn = await execute_with_tracking("acquire")
            await execute_with_tracking(
                "execute",
                connection_id=conn["connection_id"],
                query="SELECT $1::int as num, NOW() as time",
                params=[i],
                fetch_mode="one",
            )
            await execute_with_tracking("release", connection_id=conn["connection_id"])

        # Simulate connection failures by stopping supervisor
        await pool.supervisor.stop()

        # Try operations during failure
        failed_attempts = 0
        for i in range(5):
            try:
                conn = await pool.process({"operation": "acquire"})
                await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn["connection_id"],
                        "query": "SELECT 1",
                        "fetch_mode": "one",
                    }
                )
            except:
                failed_attempts += 1

        # Restart supervisor (simulating recovery)
        await pool.supervisor.start()
        await pool._ensure_min_connections()

        # Resume normal operations
        recovery_start = len(query_results)
        for i in range(10):
            conn = await execute_with_tracking("acquire")
            await execute_with_tracking(
                "execute",
                connection_id=conn["connection_id"],
                query="SELECT $1::int as num",
                params=[i],
                fetch_mode="one",
            )
            await execute_with_tracking("release", connection_id=conn["connection_id"])

        # Analyze recovery
        pre_failure_success_rate = sum(
            1
            for r in query_results[
                : failure_points[0] if failure_points else len(query_results)
            ]
            if r["success"]
        ) / max(1, failure_points[0] if failure_points else len(query_results))

        post_recovery_success_rate = sum(
            1 for r in query_results[recovery_start:] if r["success"]
        ) / max(1, len(query_results) - recovery_start)

        # Assertions
        assert (
            pre_failure_success_rate == 1.0
        )  # All operations should succeed before failure
        assert failed_attempts >= 3  # Most operations should fail during outage
        assert post_recovery_success_rate >= 0.95  # Should recover to high success rate

        await pool._cleanup()

        print(
            f"""
Failure Recovery Test Results:
- Pre-failure success rate: {pre_failure_success_rate:.1%}
- Failed attempts during outage: {failed_attempts}/5
- Post-recovery success rate: {post_recovery_success_rate:.1%}
- Total operations: {len(query_results)}
        """
        )

    async def test_long_running_queries_timeout(self, postgres_config):
        """Test pool handling of long-running queries and timeouts."""
        pool = WorkflowConnectionPool(**postgres_config)
        pool.max_connections = 5  # Limit connections to test queueing
        await pool.process({"operation": "initialize"})

        results = []

        async def long_query(query_id: int, duration: float):
            """Execute a query that takes specified duration."""
            try:
                conn = await pool.process({"operation": "acquire"})

                # Use pg_sleep to simulate long query
                start = time.time()
                result = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn["connection_id"],
                        "query": f"SELECT pg_sleep({duration}), $1::int as query_id",
                        "params": [query_id],
                        "fetch_mode": "one",
                    }
                )
                elapsed = time.time() - start

                await pool.process(
                    {"operation": "release", "connection_id": conn["connection_id"]}
                )

                return {
                    "query_id": query_id,
                    "success": True,
                    "duration": elapsed,
                    "expected": duration,
                }
            except Exception as e:
                return {"query_id": query_id, "success": False, "error": str(e)}

        # Mix of query durations
        query_durations = [
            0.1,
            0.1,
            0.1,  # Fast queries
            0.5,
            0.5,  # Medium queries
            1.0,
            1.0,  # Slow queries
            2.0,  # Very slow query
        ]

        # Execute concurrently
        start_time = time.time()
        tasks = [long_query(i, duration) for i, duration in enumerate(query_durations)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # Analyze results
        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        # With 5 connections and mixed durations, total time should be optimized
        assert len(successful) >= len(query_durations) * 0.8  # At least 80% success
        assert total_time < sum(query_durations) * 0.7  # Parallel execution benefit

        # Get stats
        stats = await pool.process({"operation": "stats"})

        # Check connection utilization
        queries_per_connection = (
            stats["queries"]["executed"] / stats["connections"]["created"]
        )
        assert queries_per_connection > 1.5  # Connections should be reused

        await pool._cleanup()

        print(
            f"""
Long Query Test Results:
- Total queries: {len(results)}
- Successful: {len(successful)}
- Failed: {len(failed)}
- Total time: {total_time:.2f}s
- Expected serial time: {sum(query_durations):.2f}s
- Speedup: {sum(query_durations) / total_time:.2f}x
- Queries per connection: {queries_per_connection:.1f}
        """
        )

    async def test_memory_pressure_and_resource_limits(self, postgres_config):
        """Test pool behavior under memory pressure with large result sets."""
        pool = WorkflowConnectionPool(**postgres_config)
        await pool.process({"operation": "initialize"})

        # Create table with large data
        setup_conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": setup_conn["connection_id"],
                "query": """
                CREATE TABLE IF NOT EXISTS large_data (
                    id SERIAL PRIMARY KEY,
                    data TEXT,
                    metadata JSONB
                )
            """,
                "fetch_mode": "one",
            }
        )

        # Insert large dataset
        large_text = "x" * 10000  # 10KB per row
        for batch in range(10):
            await pool.process(
                {
                    "operation": "execute",
                    "connection_id": setup_conn["connection_id"],
                    "query": """
                    INSERT INTO large_data (data, metadata)
                    SELECT
                        $1 || generate_series::text,
                        jsonb_build_object(
                            'batch', $2::int,
                            'index', generate_series,
                            'timestamp', NOW()
                        )
                    FROM generate_series(1, 100)
                """,
                    "params": [large_text, batch],
                    "fetch_mode": "one",
                }
            )

        await pool.process(
            {"operation": "release", "connection_id": setup_conn["connection_id"]}
        )

        # Test concurrent large queries
        async def fetch_large_dataset(query_id: int):
            """Fetch large dataset to test memory handling."""
            try:
                conn = await pool.process({"operation": "acquire"})

                # Fetch large result set
                result = await pool.process(
                    {
                        "operation": "execute",
                        "connection_id": conn["connection_id"],
                        "query": """
                        SELECT id, LEFT(data, 100) as data_preview, metadata
                        FROM large_data
                        WHERE (metadata->>'batch')::int = $1::int
                    """,
                        "params": [query_id % 10],
                        "fetch_mode": "all",
                    }
                )

                await pool.process(
                    {"operation": "release", "connection_id": conn["connection_id"]}
                )

                return {
                    "query_id": query_id,
                    "success": True,
                    "row_count": len(result["data"]) if result["data"] else 0,
                }
            except Exception as e:
                return {"query_id": query_id, "success": False, "error": str(e)}

        # Run concurrent large queries
        concurrent_queries = 20
        tasks = [fetch_large_dataset(i) for i in range(concurrent_queries)]
        results = await asyncio.gather(*tasks)

        # Verify results
        successful = [r for r in results if r.get("success")]
        assert len(successful) >= concurrent_queries * 0.9  # 90% success rate

        # Check that connections handled the load
        stats = await pool.process({"operation": "stats"})
        assert stats["connections"]["created"] <= postgres_config["max_connections"]

        # Cleanup
        cleanup_conn = await pool.process({"operation": "acquire"})
        await pool.process(
            {
                "operation": "execute",
                "connection_id": cleanup_conn["connection_id"],
                "query": "DROP TABLE IF EXISTS large_data",
                "fetch_mode": "one",
            }
        )
        await pool.process(
            {"operation": "release", "connection_id": cleanup_conn["connection_id"]}
        )

        await pool._cleanup()

        print(
            f"""
Memory Pressure Test Results:
- Concurrent queries: {concurrent_queries}
- Successful: {len(successful)}
- Connections used: {stats['connections']['created']}
- Average rows per query: {sum(r.get('row_count', 0) for r in successful) / len(successful):.0f}
        """
        )


if __name__ == "__main__":
    # Run tests directly
    import sys

    test = TestConnectionPoolProduction()
    config = test.postgres_config()

    async def run_all():
        print("Running production integration tests...\n")

        try:
            print("1. High Concurrency Mixed Workload Test")
            await test.test_high_concurrency_mixed_workload(config)

            print("\n2. Connection Failure Recovery Test")
            await test.test_connection_failure_recovery(config)

            print("\n3. Long Running Queries Test")
            await test.test_long_running_queries_timeout(config)

            print("\n4. Memory Pressure Test")
            await test.test_memory_pressure_and_resource_limits(config)

            print("\n✅ All production tests completed successfully!")
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            sys.exit(1)

    asyncio.run(run_all())
