"""
Integration tests for AsyncWorkflowBuilder with real infrastructure.

Tests the complete AsyncWorkflowBuilder functionality with real databases,
HTTP services, cache systems, and LLM integration using Docker infrastructure.
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict

import aiohttp
import asyncpg
import pytest
import pytest_asyncio

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from kailash.resources.factory import (
    CacheFactory,
    DatabasePoolFactory,
    HttpClientFactory,
)
from kailash.resources.registry import ResourceRegistry
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import (
    AsyncPatterns,
    AsyncWorkflowBuilder,
    ErrorHandler,
    RetryPolicy,
)

from tests.utils.docker_config import DATABASE_CONFIG, OLLAMA_CONFIG, REDIS_CONFIG


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_redis
@pytest.mark.slow
class TestAsyncWorkflowBuilderIntegration:
    """Integration tests for AsyncWorkflowBuilder with real infrastructure."""

    @pytest_asyncio.fixture
    async def postgres_connection(self):
        """Create a PostgreSQL connection for testing."""
        conn = await asyncpg.connect(
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
            database=DATABASE_CONFIG["database"],
        )

        # Setup test tables - drop first to ensure clean state
        await conn.execute("DROP TABLE IF EXISTS orders CASCADE")
        await conn.execute("DROP TABLE IF EXISTS users CASCADE")
        await conn.execute("DROP TABLE IF EXISTS user_analysis CASCADE")

        await conn.execute(
            """
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW(),
                data JSONB
            )
        """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                amount DECIMAL(10,2),
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Insert test data
        user_ids = []
        for i in range(10):
            user_id = await conn.fetchval(
                """
                INSERT INTO users (name, email, data)
                VALUES ($1, $2, $3)
                RETURNING id
            """,
                f"User {i}",
                f"user{i}@test.com",
                json.dumps({"score": i * 10}),
            )
            user_ids.append(user_id)

        # Insert orders
        for user_id in user_ids[:5]:
            await conn.execute(
                """
                INSERT INTO orders (user_id, amount, status)
                VALUES ($1, $2, $3)
            """,
                user_id,
                100.0 + user_id * 25,
                "completed",
            )

        yield conn

        # Cleanup
        await conn.execute("DROP TABLE IF EXISTS orders CASCADE")
        await conn.execute("DROP TABLE IF EXISTS users CASCADE")
        await conn.execute("DROP TABLE IF EXISTS user_analysis CASCADE")
        await conn.close()

    @pytest_asyncio.fixture
    async def redis_connection(self):
        """Create a Redis connection for testing."""
        if redis is None:
            pytest.skip("Redis not available")

        redis_client = redis.Redis(
            host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"], decode_responses=True
        )

        # Clear any existing test data
        await redis_client.flushdb()

        yield redis_client

        # Cleanup
        await redis_client.flushdb()
        await redis_client.aclose()

    @pytest_asyncio.fixture
    async def mock_api_server(self):
        """Start a mock API server for testing HTTP interactions."""
        import aiohttp.web_runner
        from aiohttp import web

        async def health(request):
            return web.json_response({"status": "healthy"})

        async def users_endpoint(request):
            await asyncio.sleep(0.1)  # Simulate processing time
            return web.json_response(
                {
                    "users": [
                        {"id": 1, "name": "Alice", "email": "alice@test.com"},
                        {"id": 2, "name": "Bob", "email": "bob@test.com"},
                        {"id": 3, "name": "Charlie", "email": "charlie@test.com"},
                    ],
                    "total": 3,
                }
            )

        async def slow_endpoint(request):
            await asyncio.sleep(0.2)  # Simulate slow service
            return web.json_response({"message": "slow response"})

        async def unreliable_endpoint(request):
            # Fail 50% of the time
            if time.time() % 2 < 1:
                raise web.HTTPInternalServerError(
                    text="Service temporarily unavailable"
                )
            return web.json_response({"message": "success"})

        async def rate_limited_endpoint(request):
            # Simulate rate limiting
            await asyncio.sleep(0.1)
            return web.json_response({"message": "processed", "timestamp": time.time()})

        app = web.Application()
        app.router.add_get("/health", health)
        app.router.add_get("/users", users_endpoint)
        app.router.add_get("/slow", slow_endpoint)
        app.router.add_get("/unreliable", unreliable_endpoint)
        app.router.add_post("/rate-limited", rate_limited_endpoint)

        runner = aiohttp.web_runner.AppRunner(app)
        await runner.setup()

        site = aiohttp.web_runner.TCPSite(runner, "localhost", 8999)
        await site.start()

        yield "http://localhost:8999"

        await runner.cleanup()

    @pytest_asyncio.fixture
    async def resource_registry(self, postgres_connection, redis_connection):
        """Create a resource registry with real connections."""
        registry = ResourceRegistry()

        # Database factory
        db_factory = DatabasePoolFactory(
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
            database=DATABASE_CONFIG["database"],
            min_size=2,
            max_size=5,
        )
        registry.register_factory("test_db", db_factory)

        # HTTP client factory
        http_factory = HttpClientFactory(timeout=30)
        registry.register_factory("http_client", http_factory)

        # Cache factory
        cache_factory = CacheFactory(
            backend="redis", host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"]
        )
        registry.register_factory("cache", cache_factory)

        return registry

    @pytest.mark.asyncio
    async def test_database_integration_workflow(
        self, resource_registry, postgres_connection
    ):
        """Test workflow with real database operations."""
        builder = AsyncWorkflowBuilder(
            "db_integration_test", resource_registry=resource_registry
        )

        # Add database resource
        builder.with_database(
            "test_db",
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            database=DATABASE_CONFIG["database"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
        )

        # Query users with high scores
        builder.add_async_code(
            "query_high_scores",
            """
            db = await get_resource("test_db")
            async with db.acquire() as conn:
                users = await conn.fetch('''
                    SELECT id, name, email, (data->>'score')::int as score
                    FROM users
                    WHERE (data->>'score')::int >= $1
                    ORDER BY (data->>'score')::int DESC
                ''', min_score)

                result = {
                    "high_score_users": [dict(user) for user in users],
                    "count": len(users),
                    "min_score_threshold": min_score
                }
            """,
        )

        # Calculate statistics
        builder.add_async_code(
            "calculate_stats",
            """
            users = high_score_users
            if not users:
                result = {"stats": {"count": 0, "avg_score": 0, "max_score": 0}}
            else:
                scores = [user["score"] for user in users]
                result = {
                    "stats": {
                        "count": len(users),
                        "avg_score": sum(scores) / len(scores),
                        "max_score": max(scores),
                        "min_score": min(scores),
                        "total_score": sum(scores)
                    },
                    "top_user": max(users, key=lambda u: u["score"])
                }
            """,
        )

        # Store results back to database
        builder.add_async_code(
            "store_analysis",
            """
            import json
            import time

            db = await get_resource("test_db")
            async with db.acquire() as conn:
                # Create analysis table if not exists
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_analysis (
                        id SERIAL PRIMARY KEY,
                        analysis_date TIMESTAMP DEFAULT NOW(),
                        stats JSONB,
                        top_user JSONB
                    )
                ''')

                # Extract stats and top_user from the analysis_result
                stats = analysis_result.get("stats", {})
                top_user = analysis_result.get("top_user")

                # Insert analysis results
                analysis_id = await conn.fetchval('''
                    INSERT INTO user_analysis (stats, top_user)
                    VALUES ($1, $2)
                    RETURNING id
                ''', json.dumps(stats), json.dumps(top_user) if top_user else None)

                result = {
                    "analysis_id": analysis_id,
                    "stored": True,
                    "analysis_date": time.time()
                }
            """,
        )

        # Connect the workflow
        builder.add_connection(
            "query_high_scores",
            "high_score_users",
            "calculate_stats",
            "high_score_users",
        )
        builder.add_connection(
            "calculate_stats", "result", "store_analysis", "analysis_result"
        )

        # Build and execute
        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=resource_registry)

        result = await runtime.execute_workflow_async(workflow, {"min_score": 50})

        # Verify results
        assert len(result["errors"]) == 0
        assert "query_high_scores" in result["results"]
        assert "calculate_stats" in result["results"]
        assert "store_analysis" in result["results"]

        # Check data quality
        query_result = result["results"]["query_high_scores"]
        assert "high_score_users" in query_result
        assert "count" in query_result

        stats_result = result["results"]["calculate_stats"]
        assert "stats" in stats_result

        store_result = result["results"]["store_analysis"]
        assert store_result["stored"] is True
        assert "analysis_id" in store_result

    @pytest.mark.asyncio
    async def test_http_integration_with_patterns(
        self, mock_api_server, resource_registry
    ):
        """Test HTTP integration with async patterns."""
        builder = AsyncWorkflowBuilder(
            "http_integration_test", resource_registry=resource_registry
        )

        # Add HTTP client
        builder.with_http_client(
            "api_client",
            base_url=mock_api_server,
            headers={"User-Agent": "Kailash-Test/1.0"},
        )

        # Test retry pattern with unreliable endpoint
        AsyncPatterns.retry_with_backoff(
            builder,
            "retry_request",
            """
import aiohttp
client = await get_resource("api_client")
async with client.get("/unreliable") as response:
    if response.status != 200:
        raise aiohttp.ClientError(f"HTTP {response.status}")
    data = await response.json()
    result = {"status": response.status, "data": data}
            """,
            max_retries=5,
            initial_backoff=0.1,
            backoff_factor=1.5,
        )

        # Test rate limiting pattern
        AsyncPatterns.rate_limited(
            builder,
            "rate_limited_requests",
            """
client = await get_resource("api_client")

# Make multiple requests
responses = []
for i in range(request_count):
    async with client.post("/rate-limited",
                         json={"request_id": i}) as response:
        data = await response.json()
        responses.append({"id": i, "response": data})

result = {
    "responses": responses,
    "total_requests": len(responses)
}
            """,
            requests_per_second=5,
            burst_size=3,
        )

        # Test timeout with fallback
        AsyncPatterns.timeout_with_fallback(
            builder,
            "primary_api",
            "fallback_api",
            """
# Primary: slow endpoint
client = await get_resource("api_client")
async with client.get("/slow") as response:
    result = await response.json()
            """,
            """
# Fallback: fast endpoint
client = await get_resource("api_client")
async with client.get("/users") as response:
    data = await response.json()
    result = {"fallback_used": True, "data": data}
            """,
            timeout_seconds=1.0,
        )

        # Connect patterns - pass request_count from input
        # Note: retry_request doesn't output request_count, so we'll connect differently

        # Build and execute
        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=resource_registry)

        result = await runtime.execute_workflow_async(workflow, {"request_count": 3})

        # Verify results
        assert len(result["errors"]) == 0

        # Check retry results
        retry_result = result["results"]["retry_request"]
        assert retry_result["success"] is True
        assert "total_attempts" in retry_result

        # Check rate limiting
        rate_result = result["results"]["rate_limited_requests"]
        assert "responses" in rate_result
        assert "_rate_limit_info" in rate_result

        # Check timeout/fallback
        fallback_result = result["results"]["fallback_api"]
        # Should use fallback due to timeout
        assert fallback_result.get("_source") == "fallback"
        assert fallback_result.get("_primary_timeout") is True

    @pytest.mark.asyncio
    async def test_cache_integration_patterns(
        self, redis_connection, resource_registry
    ):
        """Test cache integration with cache-aside pattern."""
        builder = AsyncWorkflowBuilder(
            "cache_integration_test", resource_registry=resource_registry
        )

        # Add cache resource
        builder.with_cache(
            "redis_cache",
            backend="redis",
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
        )

        # Setup data generator
        builder.add_async_code(
            "generate_data",
            """
import time
result = {
    "item_ids": [f"item_{i}" for i in range(1, 6)],
    "batch_timestamp": time.time()
}
            """,
        )

        # Process items with cache-aside pattern
        builder.add_parallel_map(
            "process_with_cache",
            """
async def process_item(item_id):
    import json
    import time
    import asyncio
    cache = await get_resource("redis_cache")

    # Try cache first
    cached_data = await cache.get(f"processed_{item_id}")
    if cached_data:
        return {
            "item_id": item_id,
            "data": json.loads(cached_data),
            "from_cache": True
        }

    # Simulate expensive processing
    await asyncio.sleep(0.1)
    processed_data = {
        "id": item_id,
        "processed_at": time.time(),
        "value": hash(item_id) % 1000
    }

    # Store in cache with TTL
    await cache.setex(f"processed_{item_id}", 300, json.dumps(processed_data))

    return {
        "item_id": item_id,
        "data": processed_data,
        "from_cache": False
    }
            """,
            max_workers=3,
            timeout_per_item=5,
        )

        # Aggregate results
        builder.add_async_code(
            "aggregate_results",
            """
cache_hits = sum(1 for r in results if r.get("from_cache"))
cache_misses = len(results) - cache_hits

result = {
    "total_processed": len(results),
    "cache_hits": cache_hits,
    "cache_misses": cache_misses,
    "cache_hit_rate": cache_hits / len(results) if results else 0,
    "processed_items": results
}
            """,
        )

        # Connect workflow
        builder.add_connection(
            "generate_data", "item_ids", "process_with_cache", "items"
        )
        builder.add_connection(
            "process_with_cache", "results", "aggregate_results", "results"
        )

        # Build and execute first time (cache misses)
        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=resource_registry)

        result1 = await runtime.execute_workflow_async(workflow, {})

        # Verify first execution
        assert len(result1["errors"]) == 0
        aggregate1 = result1["results"]["aggregate_results"]
        assert aggregate1["cache_misses"] == 5  # All cache misses first time
        assert aggregate1["cache_hits"] == 0

        # Execute again (should have cache hits)
        result2 = await runtime.execute_workflow_async(workflow, {})

        # Verify second execution
        assert len(result2["errors"]) == 0
        aggregate2 = result2["results"]["aggregate_results"]
        assert aggregate2["cache_hits"] > 0  # Should have cache hits
        assert aggregate2["cache_hit_rate"] > 0

    @pytest.mark.asyncio
    async def test_complex_real_world_pipeline(
        self, resource_registry, mock_api_server
    ):
        """Test a complex real-world data processing pipeline."""
        builder = AsyncWorkflowBuilder(
            "real_world_pipeline", resource_registry=resource_registry
        )

        # Add all resources
        builder.with_database(
            "analytics_db",
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            database=DATABASE_CONFIG["database"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
        )
        builder.with_http_client("external_api", base_url=mock_api_server)
        builder.with_cache(
            "processing_cache", host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"]
        )

        # Step 1: Fetch user data from API with circuit breaker
        AsyncPatterns.circuit_breaker(
            builder,
            "fetch_users",
            """
client = await get_resource("external_api")
async with client.get("/users") as response:
    if response.status != 200:
        raise Exception(f"API error: {response.status}")
    data = await response.json()
    result = {
        "users": data["users"],
        "fetched_at": time.time(),
        "count": len(data["users"])
    }
            """,
            failure_threshold=3,
            reset_timeout=30.0,
        )

        # Step 2: Enrich user data with database information
        builder.add_parallel_map(
            "enrich_users",
            """
async def process_item(user):
    db = await get_resource("analytics_db")
    async with db.acquire() as conn:
        # Get user orders
        orders = await conn.fetch('''
            SELECT id, amount, status, created_at
            FROM orders
            WHERE user_id = $1
        ''', user["id"])

        # Calculate user metrics
        total_orders = len(orders)
        total_spent = sum(float(order["amount"]) for order in orders)
        avg_order = total_spent / total_orders if total_orders > 0 else 0

        return {
            "user_id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "metrics": {
                "total_orders": total_orders,
                "total_spent": total_spent,
                "avg_order_value": avg_order,
                "customer_score": min(100, total_spent / 10)
            },
            "orders": [dict(order) for order in orders]
        }
            """,
            max_workers=3,
            continue_on_error=True,
        )

        # Step 3: Apply business rules and segment customers
        builder.add_async_code(
            "segment_customers",
            """
segments = {
    "vip": [],
    "regular": [],
    "new": []
}

for customer in enriched_customers:
    score = customer["metrics"]["customer_score"]
    total_orders = customer["metrics"]["total_orders"]

    if score >= 80 and total_orders >= 5:
        segments["vip"].append(customer)
    elif total_orders > 0:
        segments["regular"].append(customer)
    else:
        segments["new"].append(customer)

result = {
    "segments": segments,
    "summary": {
        "vip_count": len(segments["vip"]),
        "regular_count": len(segments["regular"]),
        "new_count": len(segments["new"]),
        "total_processed": len(enriched_customers)
    }
}
            """,
        )

        # Step 4: Store analytics results
        builder.add_async_code(
            "store_analytics",
            """
import json
import time

# Custom JSON encoder to handle special types
def safe_json_encode(obj):
    if isinstance(obj, dict):
        return {k: safe_json_encode(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json_encode(v) for v in obj]
    elif hasattr(obj, '__float__'):  # Handles Decimal and similar types
        return float(obj)
    elif hasattr(obj, '__str__') and not isinstance(obj, str):
        return str(obj)
    else:
        return obj

# Store analytics in database
db = await get_resource("analytics_db")
cache = await get_resource("processing_cache")

# Extract segments and summary from analysis_result
segments = analysis_result.get("segments", {})
summary = analysis_result.get("summary", {})

# Convert to JSON-safe format
segments_safe = safe_json_encode(segments)
summary_safe = safe_json_encode(summary)

async with db.acquire() as conn:
    # Create analytics table
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS customer_analytics (
            id SERIAL PRIMARY KEY,
            analysis_date TIMESTAMP DEFAULT NOW(),
            segments JSONB,
            summary JSONB
        )
    ''')

    # Store results
    analytics_id = await conn.fetchval('''
        INSERT INTO customer_analytics (segments, summary)
        VALUES ($1, $2)
        RETURNING id
    ''', json.dumps(segments_safe), json.dumps(summary_safe))

    # Also cache the results
    cache_key = f"customer_analytics_{analysis_date}"
    cache_data = {
        "analytics_id": analytics_id,
        "segments": segments_safe,
        "summary": summary_safe,
        "stored_at": time.time()
    }
    await cache.setex(cache_key, 3600, json.dumps(cache_data))

    result = cache_data
            """,
        )

        # Connect the pipeline
        builder.add_connection("fetch_users", "users", "enrich_users", "items")
        builder.add_connection(
            "enrich_users", "results", "segment_customers", "enriched_customers"
        )
        builder.add_connection(
            "segment_customers", "result", "store_analytics", "analysis_result"
        )

        # Build and execute
        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=resource_registry)

        start_time = time.time()
        result = await runtime.execute_workflow_async(
            workflow, {"analysis_date": "2024-01-01"}
        )
        end_time = time.time()

        # Verify comprehensive results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "fetch_users" in result["results"]
        assert "enrich_users" in result["results"]
        assert "segment_customers" in result["results"]
        assert "store_analytics" in result["results"]

        # Check data quality and business logic
        fetch_result = result["results"]["fetch_users"]
        assert fetch_result["count"] > 0
        assert "_circuit_breaker_info" in fetch_result

        enrich_result = result["results"]["enrich_users"]
        assert "results" in enrich_result
        assert "statistics" in enrich_result

        segment_result = result["results"]["segment_customers"]
        assert "segments" in segment_result
        assert "summary" in segment_result
        assert segment_result["summary"]["total_processed"] > 0

        # Verify performance
        execution_time = end_time - start_time
        assert execution_time < 30.0  # Should complete within 30 seconds

        # Verify database storage
        store_result = result["results"]["store_analytics"]
        assert "analytics_id" in store_result
        assert store_result.get("stored_at") is not None

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, resource_registry):
        """Test comprehensive error handling and recovery patterns."""
        builder = AsyncWorkflowBuilder(
            "error_handling_test", resource_registry=resource_registry
        )

        # Add resources
        builder.with_database(
            "test_db",
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            database=DATABASE_CONFIG["database"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
        )

        # Node that sometimes fails
        error_handler = ErrorHandler(
            handler_type="fallback",
            fallback_value={"error_handled": True, "fallback_data": "default"},
        )

        retry_policy = RetryPolicy(max_retries=3, base_delay=0.1)

        builder.add_async_code(
            "unreliable_operation",
            """
import random
import time
import asyncio

# Simulate random failures
if random.random() < failure_rate:
    if random.choice([True, False]):
        raise ConnectionError("Simulated connection error")
    else:
        raise asyncio.TimeoutError("Simulated timeout")

# Success case
result = {
    "success": True,
    "data": f"processed_at_{time.time()}",
    "attempt_info": "successful"
}
            """,
            retry_policy=retry_policy,
            error_handler=error_handler,
            description="Operation that may fail randomly",
        )

        # Recovery validation
        builder.add_async_code(
            "validate_recovery",
            """
if operation_result.get("error_handled"):
    result = {
        "recovery_successful": True,
        "used_fallback": True,
        "fallback_value": operation_result.get("fallback_data")
    }
else:
    result = {
        "recovery_successful": True,
        "used_fallback": False,
        "original_data": operation_result.get("data")
    }
            """,
        )

        # Database operation with transaction safety
        builder.add_async_code(
            "safe_database_operation",
            """
import time

db = await get_resource("test_db")

try:
    async with db.acquire() as conn:
        async with conn.transaction():
            # Test operation that might fail
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS test_recovery (
                    id SERIAL PRIMARY KEY,
                    data TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')

            # Insert test data
            test_id = await conn.fetchval('''
                INSERT INTO test_recovery (data)
                VALUES ($1)
                RETURNING id
            ''', f"test_data_{time.time()}")

            result = {
                "database_success": True,
                "test_id": test_id,
                "operation": "insert_completed"
            }

except Exception as e:
    result = {
        "database_success": False,
        "error": str(e),
        "operation": "transaction_rolled_back"
    }
            """,
        )

        # Connect workflow
        builder.add_connection(
            "unreliable_operation", "result", "validate_recovery", "operation_result"
        )
        builder.add_connection(
            "validate_recovery", "result", "safe_database_operation", "recovery_info"
        )

        # Test with high failure rate
        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=resource_registry)

        # Execute multiple times to test different failure scenarios
        results = []
        successful_count = 0

        for i in range(10):  # Try more times to account for randomness
            try:
                result = await runtime.execute_workflow_async(
                    workflow,
                    {
                        "failure_rate": 0.3
                    },  # 30% failure rate - lower to get more successes
                )
                results.append(result)

                # Check if this execution succeeded
                if "unreliable_operation" in result.get("results", {}):
                    unreliable_result = result["results"]["unreliable_operation"]
                    if unreliable_result.get("success") or unreliable_result.get(
                        "error_handled"
                    ):
                        successful_count += 1
                elif len(result.get("errors", [])) == 0:
                    successful_count += 1

            except Exception as e:
                # Count executions that hit the error handler
                if "error_handled" in str(e) or "fallback" in str(e):
                    successful_count += 1
                # Otherwise it's a real failure, continue

        # At least some executions should succeed given the lower failure rate
        assert (
            successful_count >= 4
        ), f"Only {successful_count} out of 10 executions succeeded"

        # Verify that at least one successful execution completed the workflow
        completed_executions = [
            r for r in results if "safe_database_operation" in r.get("results", {})
        ]
        assert (
            len(completed_executions) >= 1
        ), "No executions completed the full workflow"

        # Check database operation in successful executions
        for result in completed_executions:
            db_result = result["results"]["safe_database_operation"]
            assert "database_success" in db_result or "error" in db_result

    @pytest.mark.asyncio
    async def test_performance_and_concurrency(self, resource_registry):
        """Test performance characteristics and concurrency handling."""
        builder = AsyncWorkflowBuilder(
            "performance_test", resource_registry=resource_registry
        )

        # Add cache for performance testing
        builder.with_cache(
            "perf_cache", host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"]
        )

        # Generate large dataset
        builder.add_async_code(
            "generate_dataset",
            """
import time

dataset = []
for i in range(dataset_size):
    dataset.append({
        "id": i,
        "value": i * 2.5,
        "category": f"cat_{i % 10}",
        "metadata": {"batch": i // 100, "timestamp": time.time()}
    })

result = {
    "dataset": dataset,
    "size": len(dataset),
    "generated_at": time.time()
}
            """,
        )

        # Process with high concurrency
        builder.add_parallel_map(
            "high_concurrency_processing",
            """
async def process_item(item):
    import time

    # Simulate CPU and I/O work
    await asyncio.sleep(0.01)  # I/O simulation

    # CPU work simulation
    computed_value = sum(range(item["id"] % 100))

    # Cache operation
    cache = await get_resource("perf_cache")
    cache_key = f"computed_{item['id']}"
    await cache.setex(cache_key, 60, str(computed_value))

    return {
        "id": item["id"],
        "original_value": item["value"],
        "computed_value": computed_value,
        "category": item["category"],
        "processed_at": time.time()
    }
            """,
            max_workers=20,  # High concurrency
            batch_size=50,
            timeout_per_item=5,
            continue_on_error=True,
        )

        # Aggregate and analyze performance
        builder.add_async_code(
            "analyze_performance",
            """
# Extract results and statistics from processing_result
results = processing_result.get("results", [])
statistics = processing_result.get("statistics", {})

# Calculate performance metrics
total_items = statistics.get("total", len(results))
successful_items = statistics.get("successful", len([r for r in results if r.get("computed_value") is not None]))
failed_items = statistics.get("failed", total_items - successful_items)

# Calculate processing times if available
avg_duration = statistics.get("average_duration", 0)
total_duration = statistics.get("total_duration", 0)

throughput = total_items / total_duration if total_duration > 0 else 0

result = {
    "performance_metrics": {
        "total_items": total_items,
        "successful_items": successful_items,
        "failed_items": failed_items,
        "success_rate": successful_items / total_items if total_items > 0 else 0,
        "avg_processing_time": avg_duration,
        "total_processing_time": total_duration,
        "throughput_items_per_second": throughput,
        "concurrency_level": 20
    },
    "quality_metrics": {
        "data_integrity": all(r.get("id") is not None for r in results),
        "value_consistency": len(set(r.get("category") for r in results if r.get("category"))) <= 10
    }
}
            """,
        )

        # Connect workflow
        builder.add_connection(
            "generate_dataset", "dataset", "high_concurrency_processing", "items"
        )
        builder.add_connection(
            "high_concurrency_processing",
            "result",
            "analyze_performance",
            "processing_result",
        )

        # Execute performance test
        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=resource_registry)

        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {"dataset_size": 500})
        end_time = time.time()

        # Verify performance results - AsyncLocalRuntime returns different format
        assert "results" in result

        # Check dataset generation
        dataset_result = result["results"]["generate_dataset"]
        assert dataset_result["size"] == 500

        # Check processing results
        processing_result = result["results"]["high_concurrency_processing"]
        assert "results" in processing_result
        assert "statistics" in processing_result
        assert (
            processing_result["statistics"]["successful"] > 400
        )  # At least 80% success

        # Check performance analysis
        perf_result = result["results"]["analyze_performance"]
        metrics = perf_result["performance_metrics"]

        assert metrics["total_items"] == 500
        assert metrics["success_rate"] > 0.8  # At least 80% success rate

        # Verify reasonable performance
        total_execution_time = end_time - start_time
        assert total_execution_time < 60  # Should complete within 1 minute

        # If throughput metrics available, verify reasonable performance
        if "throughput_items_per_second" in metrics:
            assert (
                metrics["throughput_items_per_second"] > 10
            )  # At least 10 items/second


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
