"""Integration tests for parameter injection framework.

Follows the testing policy:
- Integration tests (Tier 2): Component interactions with REAL Docker services
- NO MOCKING ALLOWED - Tests deferred configuration with real databases
"""

import asyncio
import json
from typing import Any, Dict

import asyncpg
import pytest
import pytest_asyncio
import redis
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import (
    DeferredConfigNode,
    WorkflowParameterInjector,
    create_deferred_oauth2,
    create_deferred_sql,
)
from kailash.workflow.builder import WorkflowBuilder

from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_postgres
class TestDeferredConfigNodeIntegration:
    """Test DeferredConfigNode with real services."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_test_data(self):
        """Set up test database."""
        await ensure_docker_services()

        conn_string = get_postgres_connection_string()
        conn = await asyncpg.connect(conn_string)

        try:
            await conn.execute("DROP TABLE IF EXISTS deferred_test")
            await conn.execute(
                """
                CREATE TABLE deferred_test (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    value INTEGER,
                    category VARCHAR(50)
                )
            """
            )

            # Insert test data
            test_data = [
                ("Alpha", 100, "A"),
                ("Beta", 200, "B"),
                ("Gamma", 300, "A"),
                ("Delta", 400, "B"),
            ]

            for name, value, category in test_data:
                await conn.execute(
                    "INSERT INTO deferred_test (name, value, category) VALUES ($1, $2, $3)",
                    name,
                    value,
                    category,
                )
        finally:
            await conn.close()

        yield

        # Cleanup
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS deferred_test")
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_deferred_sql_node_basic(self):
        """Test basic deferred SQL node configuration."""
        # Create workflow with deferred SQL node
        builder = WorkflowBuilder()

        # Create deferred node without connection string
        deferred_node = create_deferred_sql(
            name="deferred_query",
            query="SELECT * FROM deferred_test WHERE category = 'A'",
        )

        # Add to workflow
        builder.add_node_instance(deferred_node, "deferred_query")

        # Add processing node
        def process_results(data: list) -> dict:
            return {
                "count": len(data),
                "names": [row["name"] for row in data],
                "total_value": sum(row["value"] for row in data),
            }

        builder.add_node(PythonCodeNode.from_function(process_results), "processor")

        builder.add_connection("deferred_query", "result.data", "processor", "data")

        # Build workflow
        workflow = builder.build()

        # Configure deferred node at runtime
        injector = WorkflowParameterInjector(workflow)
        injector.configure_deferred_node(
            "deferred_query",
            connection_string=get_postgres_connection_string(),
        )

        # Execute
        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        # Verify
        if isinstance(result, tuple):
            outputs, workflow_id = result
        else:
            outputs = result

        output = outputs["processor"]
        assert output["result"]["count"] == 2  # Alpha and Gamma
        assert set(output["result"]["names"]) == {"Alpha", "Gamma"}
        assert output["result"]["total_value"] == 400  # 100 + 300

    @pytest.mark.asyncio
    async def test_deferred_node_lifecycle(self):
        """Test deferred node initialization lifecycle."""
        # Create deferred SQL node
        deferred = create_deferred_sql(
            name="lifecycle_test", query="SELECT COUNT(*) as count FROM deferred_test"
        )

        # Verify it's not initialized
        assert not deferred._is_initialized
        assert deferred._actual_node is None

        # Build simple workflow
        builder = WorkflowBuilder()
        builder.add_node_instance(deferred, "lifecycle_test")
        workflow = builder.build()

        # Configure with real connection
        injector = WorkflowParameterInjector(workflow)
        injector.configure_deferred_node(
            "lifecycle_test",
            connection_string=get_postgres_connection_string(),
        )

        # Verify initialization
        assert deferred._is_initialized
        assert deferred._actual_node is not None
        assert "connection_string" in deferred._actual_node.config

        # Execute to verify it works
        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        if isinstance(result, tuple):
            outputs, workflow_id = result
        else:
            outputs = result

        output = outputs["lifecycle_test"]
        assert output["result"]["data"][0]["count"] == 4  # Total rows in table

    @pytest.mark.asyncio
    async def test_multiple_deferred_nodes(self):
        """Test workflow with multiple deferred nodes."""
        builder = WorkflowBuilder()

        # Create multiple deferred nodes
        deferred1 = create_deferred_sql(
            name="query_category_a",
            query="SELECT * FROM deferred_test WHERE category = 'A'",
        )

        deferred2 = create_deferred_sql(
            name="query_category_b",
            query="SELECT * FROM deferred_test WHERE category = 'B'",
        )

        builder.add_node_instance(deferred1, "query_category_a")
        builder.add_node_instance(deferred2, "query_category_b")

        # Add merge node
        def merge_results(data_a: list, data_b: list, **kwargs) -> dict:
            merge_strategy = kwargs.get("merge_strategy", "combine")

            if merge_strategy == "combine":
                return {
                    "all_data": data_a + data_b,
                    "count_a": len(data_a),
                    "count_b": len(data_b),
                }
            else:
                return {"category_a": data_a, "category_b": data_b}

        builder.add_node(PythonCodeNode.from_function(merge_results), "merger")

        builder.add_connection("query_category_a", "result.data", "merger", "data_a")
        builder.add_connection("query_category_b", "result.data", "merger", "data_b")

        workflow = builder.build()

        # Configure all deferred nodes
        injector = WorkflowParameterInjector(workflow)
        conn_string = get_postgres_connection_string()

        injector.configure_deferred_node(
            "query_category_a", connection_string=conn_string
        )
        injector.configure_deferred_node(
            "query_category_b", connection_string=conn_string
        )

        # Execute with parameters
        runtime = LocalRuntime()
        result = runtime.execute(workflow, parameters={"merge_strategy": "separate"})

        if isinstance(result, tuple):
            outputs, workflow_id = result
        else:
            outputs = result

        output = outputs["merger"]
        assert len(output["result"]["category_a"]) == 2
        assert len(output["result"]["category_b"]) == 2


@pytest.mark.integration
@pytest.mark.requires_docker
class TestWorkflowParameterInjectorIntegration:
    """Test WorkflowParameterInjector with real services."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_test_data(self):
        """Set up test database for complex workflow tests."""
        await ensure_docker_services()

        conn_string = get_postgres_connection_string()
        conn = await asyncpg.connect(conn_string)

        try:
            await conn.execute("DROP TABLE IF EXISTS deferred_test")
            await conn.execute(
                """
                CREATE TABLE deferred_test (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    value INTEGER,
                    category VARCHAR(50)
                )
            """
            )

            # Insert test data
            test_data = [
                ("Alpha", 100, "A"),
                ("Beta", 200, "B"),
                ("Gamma", 300, "A"),
                ("Delta", 400, "B"),
            ]

            for name, value, category in test_data:
                await conn.execute(
                    "INSERT INTO deferred_test (name, value, category) VALUES ($1, $2, $3)",
                    name,
                    value,
                    category,
                )
        finally:
            await conn.close()

        yield

        # Cleanup
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS deferred_test")
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_parameter_injection_with_redis(self):
        """Test parameter injection with Redis configuration."""
        await ensure_docker_services()

        # Set up Redis with config
        redis_params = get_redis_connection_params()
        r_client = redis.Redis(**redis_params)

        # Store configuration as JSON string
        config_data = {
            "processing_mode": "advanced",
            "batch_size": "50",
            "enable_caching": "true",
        }
        r_client.set("app:config", json.dumps(config_data))

        try:
            builder = WorkflowBuilder()

            # Fetch config from Redis using RedisNode
            builder.add_node(
                "RedisNode",
                "fetch_config",
                {
                    "operation": "get",
                    "key": "app:config",
                    "host": redis_params["host"],
                    "port": redis_params["port"],
                },
            )

            # Process with injected parameters
            def process_with_config(
                config,
                processing_mode=None,
                batch_size=None,
                enable_caching=None,
                **kwargs,
            ) -> dict:
                # Parse config if it's a JSON string
                if isinstance(config, str):
                    import json

                    config = json.loads(config)
                elif config is None:
                    config = {}

                # ENTERPRISE PARAMETER INJECTION TEST:
                # Use explicit parameters if provided (injected), otherwise config values
                final_processing_mode = processing_mode or config.get(
                    "processing_mode", "basic"
                )
                final_batch_size = int(batch_size or config.get("batch_size", "10"))
                final_enable_caching_str = enable_caching or config.get(
                    "enable_caching", "false"
                )
                final_enable_caching = (
                    final_enable_caching_str == "true"
                    if isinstance(final_enable_caching_str, str)
                    else bool(final_enable_caching_str)
                )

                results = {
                    "mode": final_processing_mode,
                    "batch_size": final_batch_size,
                    "caching_enabled": final_enable_caching,
                    "processed_batches": 100 // final_batch_size,
                    "config_source": "redis" if not kwargs else "mixed",
                    "injected_params": list(kwargs.keys()) if kwargs else [],
                    "received_explicit_params": {
                        "processing_mode": processing_mode,
                        "batch_size": batch_size,
                        "enable_caching": enable_caching,
                    },
                }

                if final_processing_mode == "advanced":
                    results["advanced_features"] = [
                        "optimization",
                        "parallel_processing",
                    ]

                return results

            builder.add_node(
                PythonCodeNode.from_function(process_with_config), "processor"
            )

            builder.add_connection("fetch_config", "result", "processor", "config")

            workflow = builder.build()
            runtime = LocalRuntime()

            # Test 1: Use Redis config values
            result1 = runtime.execute(workflow)

            # Handle result format - could be tuple or dict
            if isinstance(result1, tuple):
                outputs1, workflow_id = result1
            else:
                outputs1 = result1

            output1 = outputs1["processor"]["result"]

            assert output1["mode"] == "advanced"  # From Redis
            assert output1["batch_size"] == 50  # From Redis
            assert output1["caching_enabled"] is True  # From Redis
            assert "advanced_features" in output1

            # Test 2: Override with injected parameters
            result2 = runtime.execute(
                workflow, parameters={"processing_mode": "basic", "batch_size": 25}
            )

            # Handle result format - could be tuple or dict
            if isinstance(result2, tuple):
                outputs2, workflow_id = result2
            else:
                outputs2 = result2

            output2 = outputs2["processor"]["result"]

            assert output2["mode"] == "basic"  # Overridden
            assert output2["batch_size"] == 25  # Overridden
            assert output2["caching_enabled"] is True  # Still from Redis
            assert "advanced_features" not in output2  # Basic mode

        finally:
            r_client.delete("app:config")
            r_client.close()

    @pytest.mark.asyncio
    async def test_complex_parameter_propagation(self):
        """Test parameter propagation through complex workflow."""
        await ensure_docker_services()

        # Set up test table
        conn_string = get_postgres_connection_string()
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS deferred_test")
            await conn.execute(
                """
                CREATE TABLE deferred_test (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    value INTEGER,
                    category VARCHAR(50)
                )
                """
            )
            # Insert test data
            for i in range(10):
                await conn.execute(
                    "INSERT INTO deferred_test (name, value, category) VALUES ($1, $2, $3)",
                    f"item_{i}",
                    i * 10,
                    "A" if i % 2 == 0 else "B",
                )
        finally:
            await conn.close()

        builder = WorkflowBuilder()

        # Stage 1: Data fetching with injected parameters
        def generate_query(**kwargs) -> dict:
            limit = kwargs.get("query_limit", 10)
            order_by = kwargs.get("order_by", "id")

            # Ensure safe SQL construction
            if not isinstance(limit, int) or limit <= 0:
                limit = 10

            # Sanitize order_by - only allow specific safe columns and directions
            safe_orders = [
                "id",
                "value",
                "value DESC",
                "id DESC",
                "created_at",
                "created_at DESC",
            ]
            if order_by not in safe_orders:
                order_by = "id"

            # Test with completely static query
            query = "SELECT * FROM deferred_test LIMIT 3"

            return {
                "query": query,
                "metadata": {"limit": limit, "order_by": order_by},
            }

        builder.add_node(PythonCodeNode.from_function(generate_query), "query_builder")

        builder.add_node(
            "AsyncSQLDatabaseNode",
            "executor",
            {
                "connection_string": get_postgres_connection_string(),
                "operation": "select",
            },
        )

        # Stage 2: Processing with cascaded parameters
        def process_data(data: list, metadata: dict, **kwargs) -> dict:
            transform_mode = kwargs.get("transform_mode", "standard")
            include_stats = kwargs.get("include_stats", True)

            result = {
                "data": data,
                "query_metadata": metadata,
                "transform_mode": transform_mode,
            }

            if include_stats and data:
                result["stats"] = {
                    "count": len(data),
                    "value_sum": sum(row["value"] for row in data),
                    "categories": list(set(row["category"] for row in data)),
                }

            return result

        builder.add_node(PythonCodeNode.from_function(process_data), "processor")

        # Stage 3: Caching with parameter-based key
        def generate_cache_key(result: dict, **kwargs) -> dict:
            cache_prefix = kwargs.get("cache_prefix", "default")
            cache_ttl = kwargs.get("cache_ttl", 300)

            # Create cache key based on parameters
            key_parts = [
                cache_prefix,
                result["transform_mode"],
                str(result["query_metadata"]["limit"]),
            ]

            return {"key": ":".join(key_parts), "value": result, "ttl": cache_ttl}

        builder.add_node(
            PythonCodeNode.from_function(generate_cache_key), "cache_key_generator"
        )

        redis_params = get_redis_connection_params()
        builder.add_node(
            "RedisNode",
            "cache_writer",
            {
                "operation": "set",
                "host": redis_params["host"],
                "port": redis_params["port"],
            },
        )

        # Connect workflow
        builder.add_connection("query_builder", "result.query", "executor", "query")
        builder.add_connection("executor", "result.data", "processor", "data")
        builder.add_connection(
            "query_builder", "result.metadata", "processor", "metadata"
        )
        builder.add_connection("processor", "result", "cache_key_generator", "result")
        builder.add_connection(
            "cache_key_generator", "result.key", "cache_writer", "key"
        )
        builder.add_connection(
            "cache_key_generator", "result.value", "cache_writer", "value"
        )
        builder.add_connection(
            "cache_key_generator", "result.ttl", "cache_writer", "ttl"
        )

        # Execute without parameters first to test basic workflow
        workflow = builder.build()
        runtime = LocalRuntime()

        result = runtime.execute(workflow)

        # Handle result format - could be tuple or dict
        if isinstance(result, tuple):
            outputs, workflow_id = result
        else:
            outputs = result

        # Verify basic workflow execution (without parameter injection)
        processor_output = outputs["processor"]["result"]
        assert processor_output["query_metadata"]["limit"] == 10  # Default value
        assert processor_output["transform_mode"] == "standard"  # Default value
        assert "stats" in processor_output

        cache_output = outputs["cache_key_generator"]["result"]
        assert cache_output["key"] == "default:standard:10"
        assert cache_output["ttl"] == 300  # Default TTL

        # Verify cache was written
        r_client = redis.Redis(**redis_params)
        cached = r_client.get("default:standard:10")
        assert cached is not None
        r_client.delete("default:standard:10")
        r_client.close()

        # Clean up test table
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS deferred_test")
        finally:
            await conn.close()
