"""Integration tests for PythonCodeNode with real services.

Follows the testing policy:
- Integration tests (Tier 2): Component interactions with REAL Docker services
- NO MOCKING ALLOWED - Uses real PostgreSQL, Redis via docker_config.py
"""

import asyncio
import json
from typing import Any, Dict

import asyncpg
import pytest
import pytest_asyncio
import redis
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime

# RedisNode not available in current SDK
from kailash.workflow.builder import WorkflowBuilder

from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_postgres
class TestPythonCodeDatabaseIntegration:
    """Test PythonCodeNode integration with real PostgreSQL."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure nodes are registered
        from kailash.nodes.base import NodeRegistry

        if "AsyncSQLDatabaseNode" not in NodeRegistry._nodes:
            NodeRegistry.register(AsyncSQLDatabaseNode, "AsyncSQLDatabaseNode")
        if "PythonCodeNode" not in NodeRegistry._nodes:
            NodeRegistry.register(PythonCodeNode, "PythonCodeNode")

    @pytest_asyncio.fixture(autouse=True)
    async def setup_database(self):
        """Set up test database with real PostgreSQL."""
        # Ensure Docker services are running
        await ensure_docker_services()

        # Get real connection string
        conn_string = get_postgres_connection_string()

        # Create test table
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS test_users")
            await conn.execute(
                """
                CREATE TABLE test_users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    email VARCHAR(100),
                    score INTEGER DEFAULT 0
                )
            """
            )

            # Insert test data
            await conn.execute(
                """
                INSERT INTO test_users (name, email, score) VALUES
                ('Alice', 'alice@test.com', 100),
                ('Bob', 'bob@test.com', 85),
                ('Charlie', 'charlie@test.com', 92)
            """
            )
        finally:
            await conn.close()

        yield

        # Cleanup
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS test_users")
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_pythoncode_with_sql_workflow(self):
        """Test PythonCodeNode processing SQL query results."""
        # Build workflow with real database
        builder = WorkflowBuilder()

        # Add SQL node with real connection
        builder.add_node(
            "AsyncSQLDatabaseNode",
            "fetch_users",
            {
                "connection_string": get_postgres_connection_string(),
                "query": "SELECT * FROM test_users WHERE score > $1",
            },
        )

        # Add PythonCode node to process results
        def process_users(data: list, **kwargs) -> dict:
            """Process user data and calculate statistics."""
            # Access workflow parameters if any
            threshold = kwargs.get("score_threshold", 90)

            high_scorers = [u for u in data if u["score"] >= threshold]
            avg_score = sum(u["score"] for u in data) / len(data) if data else 0

            return {
                "total_users": len(data),
                "high_scorers": high_scorers,
                "average_score": avg_score,
                "threshold_used": threshold,
            }

        builder.add_node(
            "PythonCodeNode", "process_results", {"function": process_users}
        )

        # Connect nodes - SQL node outputs result.data
        builder.add_connection("fetch_users", "result.data", "process_results", "data")

        # Execute with real runtime
        workflow = builder.build()
        runtime = LocalRuntime()

        # Add workflow parameter and SQL params
        result, run_id = runtime.execute(
            workflow,
            parameters={"fetch_users": {"params": [80]}, "score_threshold": 95},
        )

        # Verify results
        process_output = result["process_results"]
        # PythonCodeNode wraps output in 'result' field
        actual_output = process_output["result"]

        assert actual_output["total_users"] == 3  # All users with score > 80
        assert len(actual_output["high_scorers"]) == 1  # Only Alice has score >= 95
        assert actual_output["average_score"] == (100 + 85 + 92) / 3
        assert actual_output["threshold_used"] == 95

    @pytest.mark.asyncio
    async def test_pythoncode_error_handling_with_db(self):
        """Test error handling in database operations."""
        builder = WorkflowBuilder()

        # Add SQL node that might fail
        builder.add_node(
            "AsyncSQLDatabaseNode",
            "risky_query",
            {
                "connection_string": get_postgres_connection_string(),
                "query": "SELECT * FROM test_users WHERE name = $1",
            },
        )

        # Add PythonCode node with error handling
        def safe_process(data: list = None, **kwargs) -> dict:
            """Safely process data with fallbacks."""
            if not data:
                return {
                    "status": "no_data",
                    "message": "No users found",
                    "fallback_used": True,
                }

            return {"status": "success", "user_count": len(data), "users": data}

        builder.add_node("PythonCodeNode", "safe_processor", {"function": safe_process})

        builder.add_connection("risky_query", "result.data", "safe_processor", "data")

        workflow = builder.build()
        runtime = LocalRuntime()
        result, run_id = runtime.execute(
            workflow, parameters={"risky_query": {"params": ["test_user"]}}
        )

        # Verify fallback handling
        output = result["safe_processor"]["result"]
        assert output["status"] == "no_data"
        assert output["fallback_used"] is True


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_redis
class TestPythonCodeRedisIntegration:
    """Test PythonCodeNode integration with real Redis."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure nodes are registered
        from kailash.nodes.base import NodeRegistry

        if "PythonCodeNode" not in NodeRegistry._nodes:
            NodeRegistry.register(PythonCodeNode, "PythonCodeNode")

    @pytest_asyncio.fixture(autouse=True)
    async def setup_redis(self):
        """Set up Redis with test data."""
        # Ensure Docker services are running
        await ensure_docker_services()

        # Get real Redis connection
        redis_params = get_redis_connection_params()
        client = redis.Redis(**redis_params)

        # Clear test keys
        for key in client.scan_iter("test:*"):
            client.delete(key)

        # Set test data
        client.hset(
            "test:user:1", mapping={"name": "Alice", "score": "100", "level": "expert"}
        )
        client.hset(
            "test:user:2",
            mapping={"name": "Bob", "score": "85", "level": "intermediate"},
        )

        client.set("test:config:threshold", "90")

        yield

        # Cleanup
        for key in client.scan_iter("test:*"):
            client.delete(key)
        client.close()

    @pytest.mark.asyncio
    async def test_pythoncode_with_redis_caching(self):
        """Test PythonCodeNode with Redis caching pattern."""
        builder = WorkflowBuilder()

        # Use PythonCodeNode to fetch from Redis
        redis_params = get_redis_connection_params()

        def read_from_redis(**kwargs):
            """Read data from Redis."""
            import redis

            client = redis.Redis(
                host=kwargs.get("host", "localhost"),
                port=kwargs.get("port", 6379),
                decode_responses=True,
            )
            key = kwargs.get("key", "test:user:1")
            return client.hgetall(key)

        builder.add_node(
            "PythonCodeNode",
            "cache_reader",
            {
                "function": read_from_redis,
                "config": {
                    "host": redis_params["host"],
                    "port": redis_params["port"],
                    "key": "test:user:1",
                },
            },
        )

        # Add PythonCode node to process cached data
        def process_cached_user(data: dict, **kwargs) -> dict:
            """Process user data from cache."""
            # Convert score to int
            score = int(data.get("score", 0))

            # Get threshold from workflow params or default
            threshold = kwargs.get("score_threshold", 90)

            return {
                "user_name": data.get("name"),
                "is_high_scorer": score >= threshold,
                "score": score,
                "level": data.get("level"),
                "cache_hit": True,
            }

        builder.add_node(
            "PythonCodeNode", "process_cache", {"function": process_cached_user}
        )

        # Use PythonCodeNode to write to Redis
        def write_to_redis(value, **kwargs):
            """Write data to Redis."""
            import json

            import redis

            client = redis.Redis(
                host=kwargs.get("host", "localhost"),
                port=kwargs.get("port", 6379),
                decode_responses=True,
            )
            key = kwargs.get("key", "test:processed:1")
            # Convert dict to JSON string for Redis
            if isinstance(value, dict):
                value = json.dumps(value)
            client.set(key, value)
            return {"success": True, "key": key}

        builder.add_node(
            "PythonCodeNode",
            "cache_writer",
            {
                "function": write_to_redis,
                "config": {
                    "host": redis_params["host"],
                    "port": redis_params["port"],
                    "key": "test:processed:1",
                },
            },
        )

        # Connect nodes
        builder.add_connection("cache_reader", "result", "process_cache", "data")
        builder.add_connection("process_cache", "result", "cache_writer", "value")

        # Execute
        workflow = builder.build()
        runtime = LocalRuntime()
        result, run_id = runtime.execute(workflow, parameters={"score_threshold": 95})

        # Verify processing
        process_output = result["process_cache"]["result"]
        assert process_output["user_name"] == "Alice"
        assert process_output["is_high_scorer"] is True
        assert process_output["score"] == 100
        assert process_output["cache_hit"] is True

        # Verify result was cached
        client = redis.Redis(**redis_params)
        cached_result = client.get("test:processed:1")
        assert cached_result is not None
        client.close()


@pytest.mark.integration
@pytest.mark.requires_docker
class TestPythonCodeComplexIntegration:
    """Test complex integration scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    @pytest.mark.requires_redis
    async def test_multi_service_workflow(self):
        """Test workflow using both PostgreSQL and Redis."""
        # Ensure services are running
        await ensure_docker_services()

        # Set up test database
        conn_string = get_postgres_connection_string()
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS test_users")
            await conn.execute(
                """
                CREATE TABLE test_users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    email VARCHAR(100),
                    score INTEGER DEFAULT 0
                )
                """
            )
            await conn.execute(
                """
                INSERT INTO test_users (name, email, score) VALUES
                ('Alice', 'alice@test.com', 100),
                ('Bob', 'bob@test.com', 85),
                ('Charlie', 'charlie@test.com', 92)
                """
            )
        finally:
            await conn.close()

        builder = WorkflowBuilder()

        # Fetch from database
        builder.add_node(
            "AsyncSQLDatabaseNode",
            "fetch_data",
            {
                "connection_string": get_postgres_connection_string(),
                "query": "SELECT id, name, score FROM test_users",
            },
        )

        # Process with PythonCode
        def aggregate_users(data: list, **kwargs) -> dict:
            """Aggregate user statistics."""
            cache_key_prefix = kwargs.get("cache_prefix", "stats")

            total_score = sum(u["score"] for u in data)
            user_count = len(data)
            avg_score = total_score / user_count if user_count > 0 else 0

            stats = {
                "total_users": user_count,
                "total_score": total_score,
                "average_score": avg_score,
                "top_scorer": max(data, key=lambda x: x["score"]) if data else None,
            }

            # Return both cache_key and stats in result
            return {"cache_key": f"test:{cache_key_prefix}:summary", "stats": stats}

        builder.add_node("PythonCodeNode", "aggregate", {"function": aggregate_users})

        # Since PythonCodeNode doesn't allow Redis imports, prepare data for caching
        def prepare_cache_data(key: str, value: dict, **kwargs) -> dict:
            """Prepare data for Redis caching."""
            import json

            # Convert dict to JSON string that will be cached
            json_value = json.dumps(value)

            return {
                "cache_key": key,
                "cache_value": json_value,
                "ttl": 300,
                "success": True,
            }

        builder.add_node(
            "PythonCodeNode", "cache_stats", {"function": prepare_cache_data}
        )

        # Connect nodes with proper field mapping
        builder.add_connection("fetch_data", "result.data", "aggregate", "data")
        builder.add_connection("aggregate", "result.cache_key", "cache_stats", "key")
        builder.add_connection("aggregate", "result.stats", "cache_stats", "value")

        # Execute
        workflow = builder.build()
        runtime = LocalRuntime()
        result, run_id = runtime.execute(
            workflow, parameters={"cache_prefix": "integration_test"}
        )

        # Verify aggregation
        agg_output = result["aggregate"]["result"]
        assert agg_output["stats"]["total_users"] == 3
        assert agg_output["stats"]["average_score"] == (100 + 85 + 92) / 3
        assert agg_output["stats"]["top_scorer"]["name"] == "Alice"

        # Verify cache preparation (we can't actually cache with PythonCodeNode)
        cache_output = result["cache_stats"]["result"]
        assert cache_output["success"] is True
        assert cache_output["cache_key"] == "test:integration_test:summary"

        # Manually cache to verify the data format
        redis_params = get_redis_connection_params()
        client = redis.Redis(**redis_params)
        client.setex(
            cache_output["cache_key"], cache_output["ttl"], cache_output["cache_value"]
        )

        # Verify it was cached correctly
        cached = client.get("test:integration_test:summary")
        assert cached is not None

        # Parse and verify cached data
        import json

        cached_data = json.loads(cached)
        assert cached_data["total_users"] == 3
        client.close()

        # Cleanup database
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS test_users")
        finally:
            await conn.close()

    @pytest.mark.asyncio
    @pytest.mark.requires_postgres
    async def test_parameter_injection_patterns(self):
        """Test various parameter injection patterns in real scenarios."""
        await ensure_docker_services()

        # Set up test database
        conn_string = get_postgres_connection_string()
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS test_users")
            await conn.execute(
                """
                CREATE TABLE test_users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    email VARCHAR(100),
                    score INTEGER DEFAULT 0
                )
                """
            )
            await conn.execute(
                """
                INSERT INTO test_users (name, email, score) VALUES
                ('Alice', 'alice@test.com', 100),
                ('Bob', 'bob@test.com', 85),
                ('Charlie', 'charlie@test.com', 92)
                """
            )
        finally:
            await conn.close()

        builder = WorkflowBuilder()

        # SQL node with parameterized query
        builder.add_node(
            "AsyncSQLDatabaseNode",
            "fetch_by_score",
            {
                "connection_string": get_postgres_connection_string(),
                "query": "SELECT * FROM test_users WHERE score >= $1",
            },
        )

        # Python node that uses both data and workflow parameters
        def analyze_users(data: list, min_score: int = 80, **kwargs) -> dict:
            """Analyze users with flexible parameters."""
            # Get additional parameters from kwargs
            include_emails = kwargs.get("include_emails", False)
            score_multiplier = kwargs.get("score_multiplier", 1.0)

            results = {
                "users": [],
                "analysis": {
                    "min_score_used": min_score,
                    "multiplier": score_multiplier,
                    "include_emails": include_emails,
                },
            }

            for user in data:
                user_data = {
                    "name": user["name"],
                    "adjusted_score": user["score"] * score_multiplier,
                }

                if include_emails:
                    user_data["email"] = user["email"]

                results["users"].append(user_data)

            return results

        builder.add_node("PythonCodeNode", "analyze", {"function": analyze_users})

        # Connect with parameter mapping
        builder.add_connection("fetch_by_score", "result.data", "analyze", "data")

        # Execute with various parameters
        workflow = builder.build()
        runtime = LocalRuntime()

        # Test 1: With workflow parameters
        result1, run_id1 = runtime.execute(
            workflow,
            parameters={
                "fetch_by_score": {"params": [90]},
                "include_emails": True,
                "score_multiplier": 1.1,
            },
        )

        output1 = result1["analyze"]["result"]
        assert output1["analysis"]["include_emails"] is True
        assert output1["analysis"]["multiplier"] == 1.1
        assert "email" in output1["users"][0]

        # Test 2: Create a new workflow to avoid connection reuse issues
        builder2 = WorkflowBuilder()

        # SQL node with parameterized query
        builder2.add_node(
            "AsyncSQLDatabaseNode",
            "fetch_by_score2",
            {
                "connection_string": get_postgres_connection_string(),
                "query": "SELECT * FROM test_users WHERE score >= $1",
            },
        )

        # Reuse the analyze function
        builder2.add_node("PythonCodeNode", "analyze2", {"function": analyze_users})
        builder2.add_connection("fetch_by_score2", "result.data", "analyze2", "data")

        workflow2 = builder2.build()
        runtime2 = LocalRuntime()

        # Test 2: Without workflow parameters (use defaults)
        result2, run_id2 = runtime2.execute(
            workflow2, parameters={"fetch_by_score2": {"params": [85]}}
        )

        output2 = result2["analyze2"]["result"]
        assert output2["analysis"]["include_emails"] is False
        assert output2["analysis"]["multiplier"] == 1.0
        assert "email" not in output2["users"][0]

        # Cleanup database
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS test_users")
        finally:
            await conn.close()
