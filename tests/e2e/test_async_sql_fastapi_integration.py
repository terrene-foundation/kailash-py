"""E2E tests for AsyncSQLDatabaseNode with FastAPI (real-world async framework).

This test file implements Tier 3 (E2E) tests for the event loop isolation fix.
Tests are written FIRST following TDD methodology (RED phase).

CRITICAL: NO MOCKING - Uses REAL FastAPI application and PostgreSQL database.

EXPECTED BEHAVIOR: Tests should FAIL with RuntimeError on sequential requests.

Test Coverage:
- FastAPI sequential requests (THE PRIMARY BUG SCENARIO)
- FastAPI concurrent requests (should work)
- Long-running server stability

Reference:
- ADR: # contrib (removed)/project/adrs/0071-async-sql-event-loop-isolation.md
- Task Breakdown: TODO-ASYNC-SQL-EVENT-LOOP-TDD-BREAKDOWN.md
- Bug Report: Each FastAPI request creates new event loop, causing RuntimeError
"""

import asyncio
import time
from typing import Dict

import pytest
import pytest_asyncio

# FastAPI imports - required for E2E tests
try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from httpx import AsyncClient
except ImportError:
    pytest.skip(
        "FastAPI/httpx not installed. Install with: pip install fastapi httpx uvicorn",
        allow_module_level=True,
    )

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

# Real PostgreSQL configuration
POSTGRES_CONFIG = {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "kailash_test",
    "user": "test_user",
    "password": "test_password",
}


@pytest.fixture
def fastapi_app():
    """Create real FastAPI application with AsyncSQLDatabaseNode endpoints.

    This simulates a real-world FastAPI application using AsyncSQLDatabaseNode
    for database operations.

    NO MOCKING - Real FastAPI app, real database operations.
    """
    app = FastAPI(title="AsyncSQL Event Loop Test API")

    # Initialize database table
    @app.on_event("startup")
    async def startup():
        """Create test table on startup."""
        config = POSTGRES_CONFIG.copy()
        setup_node = AsyncSQLDatabaseNode(
            id="setup",
            config=config,
            query="""
            CREATE TABLE IF NOT EXISTS api_requests (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
        try:
            await setup_node.async_run()
        except Exception as e:
            print(f"Warning: Table creation failed: {e}")

    @app.post("/users")
    async def create_user(name: str):
        """Create user endpoint - uses AsyncSQLDatabaseNode.

        THIS IS THE BUG SCENARIO:
        - First request succeeds
        - Second request fails with RuntimeError (pool from wrong event loop)

        Each FastAPI request runs in a new event loop (per FastAPI design).
        """
        config = POSTGRES_CONFIG.copy()

        # Create node and execute query
        node = AsyncSQLDatabaseNode(
            id="create_user",
            config=config,
            query="INSERT INTO api_requests (name) VALUES (:name) RETURNING id",
            parameters={"name": name},
        )

        try:
            result = await node.async_run()
            return {
                "status": "created",
                "name": name,
                "result": result,
            }
        except RuntimeError as e:
            # This is the bug we're fixing!
            raise HTTPException(
                status_code=500,
                detail=f"Event loop error: {str(e)}",
            )

    @app.get("/users")
    async def list_users():
        """List users endpoint - uses AsyncSQLDatabaseNode."""
        config = POSTGRES_CONFIG.copy()

        node = AsyncSQLDatabaseNode(
            id="list_users",
            config=config,
            query="SELECT id, name FROM api_requests ORDER BY id DESC LIMIT 10",
        )

        try:
            result = await node.async_run()
            return {
                "status": "success",
                "count": len(result) if result else 0,
                "users": result or [],
            }
        except RuntimeError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Event loop error: {str(e)}",
            )

    @app.get("/health")
    async def health_check():
        """Health check endpoint - tests database connectivity."""
        config = POSTGRES_CONFIG.copy()

        node = AsyncSQLDatabaseNode(
            id="health",
            config=config,
            query="SELECT 1 as alive",
        )

        try:
            result = await node.async_run()
            return {
                "status": "healthy",
                "database": "connected",
            }
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Database error: {str(e)}",
            )

    @app.get("/metrics")
    async def get_metrics():
        """Get pool metrics endpoint."""
        try:
            metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
            return {
                "status": "success",
                "metrics": metrics,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    return app


@pytest_asyncio.fixture
async def client(fastapi_app):
    """Create async HTTP client for testing FastAPI app.

    NO MOCKING - Real HTTP client making real requests.
    """
    async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def cleanup_pools():
    """Clean up shared pools after each test."""
    yield
    try:
        await AsyncSQLDatabaseNode.clear_shared_pools()
    except Exception:
        pass


@pytest.mark.e2e
class TestFastAPISequentialRequests:
    """Test FastAPI sequential requests (THE PRIMARY BUG SCENARIO).

    FastAPI creates new event loop for each request (via ASGI server).
    This causes RuntimeError when pools are shared across event loops.

    EXPECTED: Tests FAIL with RuntimeError until fix implemented.
    """

    @pytest.mark.asyncio
    async def test_fastapi_sequential_requests(self, client):
        """Test 100 consecutive HTTP requests to FastAPI endpoint.

        This is THE BUG from the bug report:
        - First request succeeds (creates pool in event loop A)
        - Second request fails (tries to use pool from loop A in new loop B)
        - RuntimeError: "Event loop is closed" or similar

        FR-001: Sequential requests must all succeed

        EXPECTED: FAIL with RuntimeError after first request
        """
        # Make 100 sequential POST requests
        for i in range(100):
            response = await client.post(
                "/users",
                params={"name": f"user_{i}"},
            )

            # All requests should succeed
            assert response.status_code == 200, (
                f"Request {i} failed with status {response.status_code}. "
                f"Response: {response.json()}"
            )

            data = response.json()
            assert data["status"] == "created", f"Request {i} failed: {data}"
            assert (
                data["name"] == f"user_{i}"
            ), f"Request {i} returned wrong name: {data}"

        # All 100 requests should have succeeded
        # Verify by querying the database
        response = await client.get("/users")
        assert response.status_code == 200

        data = response.json()
        assert (
            data["count"] >= 10
        ), f"Should have at least 10 users, got {data['count']}"

    @pytest.mark.asyncio
    async def test_fastapi_mixed_operations(self, client):
        """Test mixed POST and GET requests in sequence.

        FR-001: Different operations should work sequentially

        EXPECTED: FAIL with RuntimeError on subsequent requests
        """
        # Create user
        response = await client.post("/users", params={"name": "alice"})
        assert response.status_code == 200

        # List users
        response = await client.get("/users")
        assert response.status_code == 200

        # Create another user
        response = await client.post("/users", params={"name": "bob"})
        assert response.status_code == 200

        # List again
        response = await client.get("/users")
        assert response.status_code == 200

        # Health check
        response = await client.get("/health")
        assert response.status_code == 200


@pytest.mark.e2e
class TestFastAPIConcurrentRequests:
    """Test FastAPI concurrent requests (should work - same loop).

    Concurrent requests within FastAPI might share same event loop,
    so this might already work.

    EXPECTED: Mixed results (may pass if concurrent in same loop).
    """

    @pytest.mark.asyncio
    async def test_fastapi_concurrent_requests(self, client):
        """Test 50 simultaneous concurrent requests.

        FR-002: Concurrent requests should work

        EXPECTED: May PASS (concurrent requests might share loop)
        """
        # Make 50 concurrent POST requests
        tasks = []
        for i in range(50):
            task = client.post("/users", params={"name": f"concurrent_{i}"})
            tasks.append(task)

        # Wait for all requests to complete
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes and failures
        successes = 0
        failures = 0

        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                failures += 1
                print(f"Request {i} failed with exception: {response}")
            elif response.status_code == 200:
                successes += 1
            else:
                failures += 1
                print(f"Request {i} failed with status {response.status_code}")

        # Most requests should succeed
        assert (
            successes > 40
        ), f"Too many failures: {successes} successes, {failures} failures"

    @pytest.mark.asyncio
    async def test_dataflow_api_endpoints(self, client):
        """Test DataFlow-style CRUD operations via REST API.

        FR-002: DataFlow CRUD via API should work

        EXPECTED: May FAIL on sequential operations
        """
        # CREATE
        response = await client.post("/users", params={"name": "dataflow_user"})
        assert response.status_code == 200

        # READ
        response = await client.get("/users")
        assert response.status_code == 200
        assert response.json()["count"] > 0

        # Another CREATE
        response = await client.post("/users", params={"name": "another_user"})
        assert response.status_code == 200

        # Another READ
        response = await client.get("/users")
        assert response.status_code == 200


@pytest.mark.e2e
class TestDatabaseConnectionStability:
    """Test database connection stability over time.

    EXPECTED: Pool count growth or RuntimeError errors.
    """

    @pytest.mark.asyncio
    async def test_database_connection_stability(self, client):
        """Test connection count remains stable over 60 seconds.

        Simulates long-running server with periodic requests.

        FR-003: No connection/pool leaks over time

        EXPECTED: FAIL - pool count grows or RuntimeError
        """
        # Get initial metrics
        response = await client.get("/metrics")
        assert response.status_code == 200
        initial_metrics = response.json()["metrics"]
        initial_pool_count = initial_metrics.get("total_pools", 0)

        # Run for 60 seconds with request every 10 seconds
        start_time = time.time()
        request_count = 0

        while time.time() - start_time < 60:
            # Make request
            response = await client.post(
                "/users",
                params={"name": f"stability_test_{request_count}"},
            )

            # Should succeed
            assert response.status_code == 200, (
                f"Request {request_count} failed after "
                f"{time.time() - start_time:.1f} seconds"
            )

            request_count += 1

            # Wait 10 seconds
            await asyncio.sleep(10)

        # Get final metrics
        response = await client.get("/metrics")
        assert response.status_code == 200
        final_metrics = response.json()["metrics"]
        final_pool_count = final_metrics.get("total_pools", 0)

        # Pool count should not grow significantly
        pool_growth = final_pool_count - initial_pool_count
        assert pool_growth < 5, (
            f"Pool count grew by {pool_growth} over 60 seconds. "
            f"Initial: {initial_pool_count}, Final: {final_pool_count}. "
            f"This indicates memory leak."
        )

        # Should have made at least 6 requests
        assert request_count >= 6, (
            f"Should have made at least 6 requests in 60 seconds, "
            f"but only made {request_count}"
        )

    @pytest.mark.asyncio
    async def test_health_check_stability(self, client):
        """Test health check endpoint works consistently.

        FR-003: Health checks should always work

        EXPECTED: May FAIL with RuntimeError
        """
        # Make 20 sequential health checks
        for i in range(20):
            response = await client.get("/health")

            assert (
                response.status_code == 200
            ), f"Health check {i} failed with status {response.status_code}"

            data = response.json()
            assert data["status"] == "healthy", f"Health check {i} not healthy: {data}"

            # Small delay between checks
            await asyncio.sleep(0.1)
