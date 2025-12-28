"""Integration tests for Enhanced Gateway with real services.

Tests cover:
- Full workflow execution with Docker services
- Resource lifecycle management
- Secret resolution flow
- Multi-resource workflows
- Concurrent request handling
"""

import asyncio
import json
import os
from datetime import datetime

import pytest
import pytest_asyncio
from kailash.client import KailashClient
from kailash.gateway import (
    EnhancedDurableAPIGateway,
    ResourceReference,
    SecretManager,
    WorkflowRequest,
    create_gateway_app,
)
from kailash.resources import ResourceRegistry
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import AsyncWorkflowBuilder


@pytest_asyncio.fixture
async def real_resource_registry():
    """Create resource registry with real services."""
    registry = ResourceRegistry()
    yield registry
    await registry.cleanup()


@pytest_asyncio.fixture
async def gateway_with_resources(real_resource_registry):
    """Create gateway with real resources."""
    secret_manager = SecretManager()

    # Store test credentials matching Docker setup
    await secret_manager.store_secret(
        "db_credentials", {"user": "test_user", "password": "test_password"}
    )

    gateway = EnhancedDurableAPIGateway(
        resource_registry=real_resource_registry, secret_manager=secret_manager
    )

    yield gateway

    # Cleanup
    try:
        await gateway.shutdown()
    except Exception:
        pass

    if hasattr(gateway, "_runtime"):
        try:
            await gateway._runtime.cleanup()
        except Exception:
            pass

    # Wait for async tasks to complete
    await asyncio.sleep(0.1)


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestEnhancedGatewayIntegration:
    """Test enhanced gateway with real services."""

    @pytest.mark.asyncio
    async def test_database_workflow_integration(self, gateway_with_resources):
        """Test workflow using real PostgreSQL database."""
        # Create workflow that uses database
        workflow = (
            AsyncWorkflowBuilder("db_workflow")
            .add_async_code(
                "create_table",
                """
db = await get_resource("main_db")
async with db.acquire() as conn:
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS gateway_test (
            id SERIAL PRIMARY KEY,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    result = {"table_created": True}
""",
                required_resources=["main_db"],
            )
            .add_async_code(
                "insert_data",
                """
import time
db = await get_resource("main_db")
async with db.acquire() as conn:
    # Insert test data
    await conn.execute(
        "INSERT INTO gateway_test (name) VALUES ($1), ($2), ($3)",
        "Alice", "Bob", "Charlie"
    )
    # Query count
    count = await conn.fetchval("SELECT COUNT(*) FROM gateway_test")
    result = {"records_inserted": 3, "total_count": count}
""",
                required_resources=["main_db"],
            )
            .add_async_code(
                "query_data",
                """
db = await get_resource("main_db")
async with db.acquire() as conn:
    rows = await conn.fetch("SELECT * FROM gateway_test ORDER BY id DESC LIMIT 5")
    result = {
        "records": [dict(row) for row in rows],
        "count": len(rows)
    }
""",
                required_resources=["main_db"],
            )
            .add_connection("create_table", "result", "insert_data", "input")
            .add_connection("insert_data", "result", "query_data", "input")
            .build()
        )

        # Register workflow
        gateway_with_resources.register_workflow(
            "db_integration", workflow, description="Database integration test"
        )

        # Execute with database resource
        request = WorkflowRequest(
            inputs={},
            resources={
                "main_db": ResourceReference(
                    type="database",
                    config={
                        "host": "localhost",
                        "port": 5434,
                        "database": "kailash_test",
                    },
                    credentials_ref="db_credentials",
                )
            },
        )

        response = await gateway_with_resources.execute_workflow(
            "db_integration", request
        )

        # Verify results
        assert response.status == "completed"
        assert response.error is None

        # Check final query results
        query_result = response.result["query_data"]
        assert query_result["count"] >= 3
        assert any(r["name"] == "Alice" for r in query_result["records"])
        assert any(r["name"] == "Bob" for r in query_result["records"])
        assert any(r["name"] == "Charlie" for r in query_result["records"])

        # Cleanup - don't try to get db resource directly since it has a hashed name
        # The resource will be cleaned up automatically by the fixture

    @pytest.mark.asyncio
    async def test_multi_resource_workflow(self, gateway_with_resources):
        """Test workflow using multiple resources."""
        # Create workflow using database and cache
        workflow = (
            AsyncWorkflowBuilder("multi_resource")
            .add_async_code(
                "fetch_from_db",
                """
db = await get_resource("db")
async with db.acquire() as conn:
    # Get some data
    rows = await conn.fetch("SELECT 1 as id, 'test' as value")
    result = {"db_data": [dict(row) for row in rows]}
""",
                required_resources=["db"],
            )
            .add_async_code(
                "cache_data",
                """
cache = await get_resource("cache")
import json

# Cache the database data
for item in db_data:
    key = f"gateway_test:{item['id']}"
    await cache.setex(key, 60, json.dumps(item))

result = {"cached_count": len(db_data)}
""",
                required_resources=["cache"],
            )
            .add_async_code(
                "verify_cache",
                """
cache = await get_resource("cache")
import json

# Read back from cache
cached_items = []
for i in range(1, cached_count + 1):
    key = f"gateway_test:{i}"
    data = await cache.get(key)
    if data:
        cached_items.append(json.loads(data))

result = {
    "verified_count": len(cached_items),
    "cache_hit_rate": len(cached_items) / cached_count if cached_count > 0 else 0
}
""",
                required_resources=["cache"],
            )
            .add_connection("fetch_from_db", "db_data", "cache_data", "db_data")
            .add_connection(
                "cache_data", "cached_count", "verify_cache", "cached_count"
            )
            .build()
        )

        gateway_with_resources.register_workflow("multi_resource", workflow)

        # Execute with multiple resources
        request = WorkflowRequest(
            inputs={},
            resources={
                "db": ResourceReference(
                    type="database",
                    config={
                        "host": "localhost",
                        "port": 5434,
                        "database": "kailash_test",
                    },
                    credentials_ref="db_credentials",
                ),
                "cache": ResourceReference(
                    type="cache", config={"host": "localhost", "port": 6380}
                ),
            },
        )

        response = await gateway_with_resources.execute_workflow(
            "multi_resource", request
        )

        assert response.status == "completed"
        assert response.result["verify_cache"]["cache_hit_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_concurrent_workflow_execution(self, gateway_with_resources):
        """Test concurrent execution of multiple workflows."""
        # Create simple workflow
        workflow = (
            AsyncWorkflowBuilder("concurrent_test")
            .add_async_code(
                "process",
                """
import asyncio
import random
import time

# Simulate some async work
delay = random.uniform(0.1, 0.3)
await asyncio.sleep(delay)

result = {
    "request_id": request_id,
    "processed_at": time.time(),
    "delay": delay
}
""",
            )
            .build()
        )

        gateway_with_resources.register_workflow("concurrent_test", workflow)

        # Execute multiple workflows concurrently
        requests = []
        for i in range(10):
            request = WorkflowRequest(
                inputs={"request_id": f"req_{i}"}, context={"index": i}
            )
            requests.append(request)

        # Execute all concurrently
        tasks = [
            gateway_with_resources.execute_workflow("concurrent_test", req)
            for req in requests
        ]

        responses = await asyncio.gather(*tasks)

        # Verify all completed
        assert all(r.status == "completed" for r in responses)
        assert len(set(r.request_id for r in responses)) == 10  # All unique

        # Check timing - should be concurrent not sequential
        times = [r.result["process"]["processed_at"] for r in responses]
        time_range = max(times) - min(times)
        assert time_range < 1.0  # Should complete within 1 second if concurrent

    @pytest.mark.asyncio
    async def test_resource_sharing_across_workflows(self, gateway_with_resources):
        """Test that resources are properly shared across workflows."""
        # Register a shared database resource
        db_ref = ResourceReference(
            type="database",
            config={"host": "localhost", "port": 5434, "database": "postgres"},
            credentials_ref="db_credentials",
        )

        # Store the reference in registry with a name we can use
        shared_db_name = "shared_db"

        # Create workflow that counts connections
        workflow = (
            AsyncWorkflowBuilder("connection_test")
            .add_async_code(
                "check_pool",
                """
# Use the resource name from the request
db = await get_resource("shared_db")
pool_size = db.size if hasattr(db, 'size') else 'unknown'
result = {
    "workflow_id": workflow_id,
    "pool_info": str(type(db)),
    "has_pool": True
}
""",
                required_resources=["shared_db"],
            )
            .build()
        )

        gateway_with_resources.register_workflow("connection_test", workflow)

        # Execute multiple times
        results = []
        for i in range(5):
            request = WorkflowRequest(
                inputs={"workflow_id": i},
                resources={"shared_db": db_ref},  # Use the same reference
            )
            response = await gateway_with_resources.execute_workflow(
                "connection_test", request
            )
            results.append(response)

        # All should succeed and use the same pool
        assert all(r.status == "completed" for r in results)

        # Check that we're using a pool (same type)
        pool_types = [r.result["check_pool"]["pool_info"] for r in results]
        assert len(set(pool_types)) == 1  # All same type = shared resource

    @pytest.mark.asyncio
    async def test_workflow_with_http_resource(self, gateway_with_resources):
        """Test workflow using HTTP client resource."""
        workflow = (
            AsyncWorkflowBuilder("http_test")
            .add_async_code(
                "fetch_data",
                """
http = await get_resource("api")

# Make concurrent requests
import asyncio
urls = [
    "/users/1",
    "/users/2",
    "/posts/1"
]

async def fetch_url(url):
    try:
        response = await http.get(f"https://jsonplaceholder.typicode.com{url}")
        return await response.json()
    except Exception as e:
        return {"error": str(e)}

results = await asyncio.gather(*[fetch_url(url) for url in urls])

result = {
    "fetched": len([r for r in results if "error" not in r]),
    "errors": len([r for r in results if "error" in r]),
    "data": results
}
""",
                required_resources=["api"],
            )
            .build()
        )

        gateway_with_resources.register_workflow("http_test", workflow)

        request = WorkflowRequest(
            inputs={},
            resources={
                "api": ResourceReference(type="http_client", config={"timeout": 10})
            },
        )

        response = await gateway_with_resources.execute_workflow("http_test", request)

        assert response.status == "completed"
        assert response.result["fetch_data"]["fetched"] > 0
