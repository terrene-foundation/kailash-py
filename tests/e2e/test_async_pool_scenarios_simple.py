"""Async Pool Scenarios Simple E2E Tests

These tests validate async connection pool scenarios with simple,
reliable patterns that should work consistently.

Key functionality tested:
- Basic async connection pooling
- Simple pool management scenarios
- Resource lifecycle validation
- Connection reuse patterns
"""

import asyncio
import time
from typing import Any, Dict

import pytest
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import AsyncWorkflowBuilder

from tests.utils.docker_config import DATABASE_CONFIG, REDIS_CONFIG

pytestmark = [pytest.mark.e2e, pytest.mark.requires_docker, pytest.mark.asyncio]


class TestAsyncPoolScenariosSimple:
    """Simple async pool scenario tests."""

    async def test_basic_database_pool_usage(self):
        """Test basic database connection pool usage."""
        builder = AsyncWorkflowBuilder("db_pool_basic")

        # Database pool initialization and testing
        db_pool_test_code = f"""
import asyncio
import asyncpg
import time

# Database configuration
db_config = {{
    "host": "{DATABASE_CONFIG['host']}",
    "port": {DATABASE_CONFIG['port']},
    "database": "{DATABASE_CONFIG['database']}",
    "user": "{DATABASE_CONFIG['user']}",
    "password": "{DATABASE_CONFIG['password']}"
}}

start_time = time.time()
connection_attempts = []
query_results = []

try:
    # Create connection pool
    pool = await asyncpg.create_pool(
        min_size=2,
        max_size=5,
        **db_config
    )

    # Test multiple concurrent connections
    async def test_connection(connection_id):
        async with pool.acquire() as conn:
            query_start = time.time()
            result = await conn.fetchval("SELECT $1 as connection_test", "test_" + str(connection_id))
            query_time = time.time() - query_start
            return {{"connection_id": connection_id, "result": result, "query_time": query_time}}

    # Run concurrent connection tests
    tasks = [test_connection(i) for i in range(8)]  # More tasks than max pool size
    connection_results = await asyncio.gather(*tasks)

    await pool.close()

    total_time = time.time() - start_time

    result = {{
        "pool_test_success": True,
        "concurrent_connections": len(connection_results),
        "total_execution_time": total_time,
        "average_query_time": sum(r["query_time"] for r in connection_results) / len(connection_results),
        "all_queries_successful": all("test_" in r["result"] for r in connection_results),
        "connection_results": connection_results,
        "pool_efficiency": len(connection_results) / total_time if total_time > 0 else 0
    }}

except Exception as e:
    result = {{
        "pool_test_success": False,
        "error": str(e),
        "error_type": type(e).__name__
    }}
"""

        # Pool performance analysis
        analysis_code = """
# Analyze pool performance
pool_data = pool_test_result
success = pool_data.get("pool_test_success", False)

if success:
    query_times = [r["query_time"] for r in pool_data.get("connection_results", [])]

    result = {
        "performance_analysis": {
            "min_query_time": min(query_times) if query_times else 0,
            "max_query_time": max(query_times) if query_times else 0,
            "query_time_variance": max(query_times) - min(query_times) if query_times else 0,
            "consistency_score": 1 - (max(query_times) - min(query_times)) / max(query_times) if query_times and max(query_times) > 0 else 0
        },
        "pool_health": {
            "connections_completed": len(query_times),
            "success_rate": 1.0 if pool_data.get("all_queries_successful") else 0.0,
            "efficiency_score": pool_data.get("pool_efficiency", 0),
            "performance_acceptable": pool_data.get("average_query_time", 1) < 0.5
        },
        "recommendations": {
            "pool_size_adequate": len(query_times) == 8,
            "performance_tuning_needed": pool_data.get("average_query_time", 1) > 0.2,
            "connection_handling_optimal": pool_data.get("all_queries_successful", False)
        }
    }
else:
    result = {
        "performance_analysis": {"error": "Pool test failed"},
        "pool_health": {"healthy": False},
        "recommendations": {"investigate_connection_issues": True}
    }
"""

        builder.add_node(
            "AsyncPythonCodeNode", "db_pool_test", {"code": db_pool_test_code}
        )
        builder.add_node(
            "PythonCodeNode", "performance_analysis", {"code": analysis_code}
        )

        builder.add_connection(
            "db_pool_test", "result", "performance_analysis", "pool_test_result"
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify pool testing workflow
        assert len(result["errors"]) == 0

        # Verify database pool test
        pool_result = result["results"]["db_pool_test"]
        assert pool_result["pool_test_success"] is True
        assert pool_result["concurrent_connections"] == 8
        assert pool_result["all_queries_successful"] is True
        assert pool_result["pool_efficiency"] > 1  # At least 1 connection/second

        # Verify performance analysis
        analysis_result = result["results"]["performance_analysis"]
        # PythonCodeNode wraps result in a "result" key
        if "result" in analysis_result:
            analysis_result = analysis_result["result"]
        assert "pool_health" in analysis_result
        pool_health = analysis_result["pool_health"]
        assert pool_health["connections_completed"] == 8
        assert pool_health["success_rate"] == 1.0
        assert pool_health["performance_acceptable"] is True

    async def test_redis_pool_simple_operations(self):
        """Test Redis connection pool with simple operations."""
        builder = AsyncWorkflowBuilder("redis_pool_simple")

        # Redis pool operations using proper async pattern
        redis_pool_code = f"""
import redis.asyncio as redis
import asyncio
import time

# Redis configuration
redis_config = {{
    "host": "{REDIS_CONFIG['host']}",
    "port": {REDIS_CONFIG['port']}
}}

start_time = time.time()
operations_completed = []

try:
    # Create async Redis connection pool
    redis_client = redis.from_url(
        f"redis://{{redis_config['host']}}:{{redis_config['port']}}",
        decode_responses=True,
        max_connections=10
    )

    # Test concurrent Redis operations
    async def perform_operation(op_type, key, value=None):
        op_start = time.time()

        if op_type == "set":
            result = await redis_client.set(key, value)
        elif op_type == "get":
            result = await redis_client.get(key)
        elif op_type == "incr":
            result = await redis_client.incr(key)
        else:
            result = None

        op_time = time.time() - op_start
        return {{
            "operation_type": op_type,
            "key": key,
            "result": str(result),
            "execution_time": op_time
        }}

    # Run operations concurrently
    tasks = [
        perform_operation("set", "test_key_1", "test_value_1"),
        perform_operation("set", "test_key_2", "test_value_2"),
        perform_operation("get", "test_key_1"),
        perform_operation("get", "test_key_2"),
        perform_operation("incr", "counter_test"),
        perform_operation("incr", "counter_test"),
        perform_operation("get", "counter_test")
    ]

    operations_completed = await asyncio.gather(*tasks)

    # Cleanup test keys
    await redis_client.delete("test_key_1", "test_key_2", "counter_test")
    await redis_client.aclose()

    total_time = time.time() - start_time

    result = {{
        "redis_pool_success": True,
        "operations_completed": len(operations_completed),
        "total_execution_time": total_time,
        "average_operation_time": sum(op["execution_time"] for op in operations_completed) / len(operations_completed),
        "operation_details": operations_completed,
        "operations_per_second": len(operations_completed) / total_time if total_time > 0 else 0
    }}

except Exception as e:
    result = {{
        "redis_pool_success": False,
        "error": str(e),
        "error_type": type(e).__name__
    }}
"""

        # Redis operation validation
        validation_code = """
# Validate Redis operations
redis_data = redis_operations
success = redis_data.get("redis_pool_success", False)

if success:
    operations = redis_data.get("operation_details", [])

    # Validate operation results
    set_operations = [op for op in operations if op["operation_type"] == "set"]
    get_operations = [op for op in operations if op["operation_type"] == "get"]
    incr_operations = [op for op in operations if op["operation_type"] == "incr"]

    result = {
        "operation_validation": {
            "set_operations_count": len(set_operations),
            "get_operations_count": len(get_operations),
            "incr_operations_count": len(incr_operations),
            "all_operations_fast": all(op["execution_time"] < 0.1 for op in operations),
            "get_operations_successful": all(op["result"] != "None" for op in get_operations),
            "incr_sequence_correct": len(incr_operations) == 2
        },
        "performance_metrics": {
            "total_operations": len(operations),
            "operations_per_second": redis_data.get("operations_per_second", 0),
            "average_latency": redis_data.get("average_operation_time", 0),
            "performance_grade": "excellent" if redis_data.get("operations_per_second", 0) > 50 else "good"
        },
        "redis_health": {
            "connection_stable": True,
            "response_times_consistent": max(op["execution_time"] for op in operations) < 0.1,
            "operations_reliable": len(operations) == 7
        }
    }
else:
    result = {
        "operation_validation": {"error": "Redis operations failed"},
        "performance_metrics": {"performance_grade": "failed"},
        "redis_health": {"connection_stable": False}
    }
"""

        # Use AsyncPythonCodeNode for async Redis operations
        from kailash.nodes.code import AsyncPythonCodeNode

        builder.add_node(
            "AsyncPythonCodeNode", "redis_operations", {"code": redis_pool_code}
        )
        builder.add_node(
            "PythonCodeNode", "redis_validation", {"code": validation_code}
        )

        builder.add_connection(
            "redis_operations", "result", "redis_validation", "redis_operations"
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify Redis pool workflow
        assert len(result["errors"]) == 0

        # Verify Redis operations
        redis_result = result["results"]["redis_operations"]
        assert redis_result["redis_pool_success"] is True
        assert redis_result["operations_completed"] == 7
        assert redis_result["operations_per_second"] > 10  # Should be fast

        # Verify validation
        validation_result = result["results"]["redis_validation"]
        # PythonCodeNode wraps result in a "result" key
        if "result" in validation_result:
            validation_result = validation_result["result"]
        assert "operation_validation" in validation_result
        operation_validation = validation_result["operation_validation"]
        assert operation_validation["set_operations_count"] == 2
        assert (
            operation_validation["get_operations_count"] == 3
        )  # 2 for test keys + 1 for counter
        assert operation_validation["incr_operations_count"] == 2
        assert operation_validation["all_operations_fast"] is True

        performance = validation_result["performance_metrics"]
        assert performance["performance_grade"] in ["excellent", "good"]

    async def test_mixed_pool_coordination(self):
        """Test coordination between multiple pool types."""
        builder = AsyncWorkflowBuilder("mixed_pool_coordination")

        # Coordinated pool operations - full async approach
        coordination_code = f'''
import asyncio
import asyncpg
import redis.asyncio as redis
import json
import time

start_time = time.time()
coordination_log = []

try:
    # Initialize both pools
    db_pool = await asyncpg.create_pool(
        host="{DATABASE_CONFIG['host']}",
        port={DATABASE_CONFIG['port']},
        database="{DATABASE_CONFIG['database']}",
        user="{DATABASE_CONFIG['user']}",
        password="{DATABASE_CONFIG['password']}",
        min_size=1,
        max_size=3
    )

    redis_client = redis.from_url(
        f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}",
        decode_responses=True
    )

    # Coordinated operations scenario
    coordination_log.append({{"step": "pools_initialized", "timestamp": time.time()}})

    # Step 1: Store data in database
    async with db_pool.acquire() as db_conn:
        await db_conn.execute("""
            CREATE TEMP TABLE IF NOT EXISTS coordination_test (
                id SERIAL PRIMARY KEY,
                data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        test_data = {{"message": "coordination_test", "value": 42}}
        result_id = await db_conn.fetchval(
            "INSERT INTO coordination_test (data) VALUES ($1) RETURNING id",
            json.dumps(test_data)
        )
        coordination_log.append({{"step": "data_stored_db", "id": result_id, "timestamp": time.time()}})

    # Step 2: Cache reference in Redis
    cache_key = f"coordination_test:{{result_id}}"
    await redis_client.set(
        cache_key,
        json.dumps({{"db_id": result_id, "cached_at": time.time()}})
    )
    coordination_log.append({{"step": "reference_cached", "cache_key": cache_key, "timestamp": time.time()}})

    # Step 3: Retrieve via cache then database
    cached_data = await redis_client.get(cache_key)
    cache_info = json.loads(cached_data)
    coordination_log.append({{"step": "cache_retrieved", "cache_info": cache_info, "timestamp": time.time()}})

    async with db_pool.acquire() as db_conn:
        db_data = await db_conn.fetchrow(
            "SELECT id, data, created_at::text as created_at FROM coordination_test WHERE id = $1",
            cache_info["db_id"]
        )
        coordination_log.append({{"step": "db_data_retrieved", "db_data": dict(db_data), "timestamp": time.time()}})

    # Step 4: Cleanup
    await redis_client.delete(cache_key)
    coordination_log.append({{"step": "cache_cleaned", "timestamp": time.time()}})

    await db_pool.close()
    await redis_client.aclose()

    total_time = time.time() - start_time

    result = {{
        "coordination_success": True,
        "total_steps": len(coordination_log),
        "execution_time": total_time,
        "coordination_log": coordination_log,
        "data_consistency": cache_info["db_id"] == result_id,
        "performance_acceptable": total_time < 2.0
    }}

except Exception as e:
    result = {{
        "coordination_success": False,
        "error": str(e),
        "coordination_log": coordination_log,
        "partial_completion": len(coordination_log)
    }}
'''

        # Coordination analysis
        analysis_code = """
# Analyze coordination effectiveness
coord_data = coordination_result
success = coord_data.get("coordination_success", False)

if success:
    log_entries = coord_data.get("coordination_log", [])

    # Calculate step timings
    step_timings = []
    for i in range(1, len(log_entries)):
        step_duration = log_entries[i]["timestamp"] - log_entries[i-1]["timestamp"]
        step_timings.append({
            "step": log_entries[i]["step"],
            "duration": step_duration
        })

    result = {
        "coordination_analysis": {
            "total_coordination_steps": len(log_entries),
            "data_consistency_verified": coord_data.get("data_consistency", False),
            "step_timings": step_timings,
            "bottleneck_step": max(step_timings, key=lambda x: x["duration"])["step"] if step_timings else None,
            "fastest_step": min(step_timings, key=lambda x: x["duration"])["step"] if step_timings else None
        },
        "pool_coordination_health": {
            "both_pools_functional": success,
            "cross_pool_data_flow": coord_data.get("data_consistency", False),
            "coordination_efficiency": coord_data.get("total_steps", 0) / coord_data.get("execution_time", 1),
            "performance_meets_target": coord_data.get("performance_acceptable", False)
        },
        "operational_insights": {
            "coordination_pattern": "cache_aside_with_db_primary",
            "data_flow_verified": True,
            "resource_cleanup_successful": "cache_cleaned" in [entry["step"] for entry in log_entries]
        }
    }
else:
    result = {
        "coordination_analysis": {"error": "Coordination failed"},
        "pool_coordination_health": {"both_pools_functional": False},
        "operational_insights": {"coordination_pattern": "failed"}
    }
"""

        builder.add_node(
            "AsyncPythonCodeNode", "pool_coordination", {"code": coordination_code}
        )
        builder.add_node(
            "PythonCodeNode", "coordination_analysis", {"code": analysis_code}
        )

        builder.add_connection(
            "pool_coordination",
            "result",
            "coordination_analysis",
            "coordination_result",
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify coordination workflow
        assert len(result["errors"]) == 0

        # Verify coordination
        coord_result = result["results"]["pool_coordination"]
        assert coord_result["coordination_success"] is True
        assert coord_result["total_steps"] >= 5  # At least 5 coordination steps
        assert coord_result["data_consistency"] is True
        assert coord_result["performance_acceptable"] is True

        # Verify analysis
        analysis_result = result["results"]["coordination_analysis"]
        # PythonCodeNode wraps result in a "result" key
        if "result" in analysis_result:
            analysis_result = analysis_result["result"]
        coord_analysis = analysis_result["coordination_analysis"]
        assert coord_analysis["data_consistency_verified"] is True
        assert len(coord_analysis["step_timings"]) > 0

        pool_health = analysis_result["pool_coordination_health"]
        assert pool_health["both_pools_functional"] is True
        assert pool_health["cross_pool_data_flow"] is True

        insights = analysis_result["operational_insights"]
        assert insights["coordination_pattern"] == "cache_aside_with_db_primary"
        assert insights["data_flow_verified"] is True
        assert insights["resource_cleanup_successful"] is True
