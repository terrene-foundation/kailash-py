"""
Integration tests for AsyncPythonCodeNode with ResourceRegistry.

Tests the integration between AsyncPythonCodeNode and ResourceRegistry
to ensure resources can be accessed within async code execution.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from kailash.nodes.code.async_python import AsyncPythonCodeNode
from kailash.resources.factory import ResourceFactory
from kailash.resources.registry import ResourceRegistry


class MockDatabaseFactory(ResourceFactory):
    """Mock database factory for testing."""

    def __init__(self):
        self.query_results = {}

    async def create(self):
        mock_db = MagicMock()

        async def mock_fetch(query):
            return self.query_results.get(query, [])

        mock_db.fetch = mock_fetch
        return mock_db

    def get_config(self):
        return {"type": "mock_database"}


class MockHttpClientFactory(ResourceFactory):
    """Mock HTTP client factory for testing."""

    def __init__(self):
        self.responses = {}

    async def create(self):
        mock_client = MagicMock()

        async def mock_get(url):
            response_mock = MagicMock()
            response_mock.json.return_value = self.responses.get(url, {})
            response_mock.status_code = 200
            return response_mock

        mock_client.get = mock_get
        return mock_client

    def get_config(self):
        return {"type": "mock_http_client"}


@pytest.mark.asyncio
class TestAsyncPythonCodeNodeResourceIntegration:
    """Test AsyncPythonCodeNode with ResourceRegistry."""

    async def test_basic_resource_access(self):
        """Test basic resource access in async code."""
        # Set up registry with mock database
        registry = ResourceRegistry()
        db_factory = MockDatabaseFactory()
        db_factory.query_results["SELECT 1"] = [{"result": 1}]

        registry.register_factory("test_db", db_factory)

        # Create node with code that uses resource
        node = AsyncPythonCodeNode(
            code="""
# Get database from registry
db = await get_resource("test_db")

# Use the database
data = await db.fetch("SELECT 1")

result = {"data": data, "count": len(data)}
"""
        )

        # Execute with resource registry
        output = await node.async_run(resource_registry=registry)

        assert output["data"] == [{"result": 1}]
        assert output["count"] == 1

    async def test_multiple_resource_access(self):
        """Test accessing multiple resources."""
        # Set up registry with database and HTTP client
        registry = ResourceRegistry()

        # Database
        db_factory = MockDatabaseFactory()
        db_factory.query_results["SELECT * FROM users"] = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        registry.register_factory("db", db_factory)

        # HTTP client
        http_factory = MockHttpClientFactory()
        http_factory.responses["/api/status"] = {"status": "ok", "version": "1.0"}
        registry.register_factory("http", http_factory)

        # Create node that uses both resources
        node = AsyncPythonCodeNode(
            code="""
import asyncio

# Get both resources
db = await get_resource("db")
http = await get_resource("http")

# Use them concurrently
users_task = db.fetch("SELECT * FROM users")
status_task = http.get("/api/status")

users, status_response = await asyncio.gather(users_task, status_task)
status = status_response.json()

result = {
    "users": users,
    "api_status": status,
    "user_count": len(users)
}
"""
        )

        # Execute
        output = await node.async_run(resource_registry=registry)

        assert len(output["users"]) == 2
        assert output["users"][0]["name"] == "Alice"
        assert output["api_status"]["status"] == "ok"
        assert output["user_count"] == 2

    async def test_resource_error_handling(self):
        """Test error handling when resource access fails."""
        registry = ResourceRegistry()

        # Don't register any resources

        node = AsyncPythonCodeNode(
            code="""
try:
    db = await get_resource("nonexistent_db")
    result = {"error": False}
except Exception as e:
    result = {"error": True, "message": str(e)}
"""
        )

        output = await node.async_run(resource_registry=registry)

        assert output["error"] is True
        assert "no factory registered" in output["message"].lower()

    async def test_no_registry_provided(self):
        """Test behavior when no registry is provided."""
        node = AsyncPythonCodeNode(
            code="""
# Try to use get_resource without registry
try:
    db = await get_resource("test_db")
    result = {"error": False}
except Exception as e:
    result = {"error": True, "message": str(e)}
"""
        )

        # Execute without registry
        output = await node.async_run()

        assert output["error"] is True
        assert "get_resource" in output["message"]

    async def test_resource_with_concurrent_tasks(self):
        """Test resource usage with concurrent tasks."""
        registry = ResourceRegistry()

        # Set up database with multiple query results
        db_factory = MockDatabaseFactory()
        db_factory.query_results.update(
            {
                "SELECT * FROM users WHERE id = 1": [{"id": 1, "name": "Alice"}],
                "SELECT * FROM users WHERE id = 2": [{"id": 2, "name": "Bob"}],
                "SELECT * FROM users WHERE id = 3": [{"id": 3, "name": "Charlie"}],
            }
        )
        registry.register_factory("db", db_factory)

        node = AsyncPythonCodeNode(
            code="""
import asyncio

# Get database resource
db = await get_resource("db")

# Create multiple concurrent queries
user_ids = [1, 2, 3]
tasks = []

for user_id in user_ids:
    query = f"SELECT * FROM users WHERE id = {user_id}"
    task = db.fetch(query)
    tasks.append(task)

# Execute all queries concurrently
results = await asyncio.gather(*tasks)

# Flatten results
users = []
for result in results:
    users.extend(result)

result = {"users": users, "query_count": len(tasks)}
""",
            max_concurrent_tasks=5,
        )

        output = await node.async_run(resource_registry=registry)

        assert len(output["users"]) == 3
        assert output["query_count"] == 3

        # Check all users are present
        names = [user["name"] for user in output["users"]]
        assert "Alice" in names
        assert "Bob" in names
        assert "Charlie" in names

    async def test_resource_cleanup_simulation(self):
        """Test that resources can be used for operations that require cleanup."""
        registry = ResourceRegistry()

        # Mock database that tracks connection usage
        connection_count = {"active": 0, "total": 0}

        class TrackingDatabaseFactory(ResourceFactory):
            async def create(self):
                mock_db = MagicMock()

                async def acquire():
                    connection_count["active"] += 1
                    connection_count["total"] += 1
                    conn_mock = MagicMock()
                    conn_mock.fetchval = AsyncMock(return_value=42)
                    return conn_mock

                async def release(conn):
                    connection_count["active"] -= 1

                mock_db.acquire = acquire
                mock_db.release = release
                return mock_db

            def get_config(self):
                return {"type": "tracking_db"}

        registry.register_factory("tracking_db", TrackingDatabaseFactory())

        node = AsyncPythonCodeNode(
            code="""
# Get database resource
db = await get_resource("tracking_db")

# Simulate connection usage with proper cleanup
conn = await db.acquire()
try:
    value = await conn.fetchval("SELECT 42")
finally:
    await db.release(conn)

result = {"value": value, "cleanup_done": True}
"""
        )

        output = await node.async_run(resource_registry=registry)

        assert output["value"] == 42
        assert output["cleanup_done"] is True
        assert connection_count["active"] == 0  # Connection was released
        assert connection_count["total"] == 1  # One connection was used

    async def test_resource_health_check_integration(self):
        """Test that resource health affects availability."""
        registry = ResourceRegistry()

        # Create a resource that can be made unhealthy
        healthy_state = {"is_healthy": True}

        class HealthAwareDatabaseFactory(ResourceFactory):
            async def create(self):
                mock_db = MagicMock()
                mock_db.query = AsyncMock(return_value="data")
                mock_db._healthy = healthy_state
                return mock_db

            def get_config(self):
                return {"type": "health_aware_db"}

        async def health_check(db):
            return db._healthy["is_healthy"]

        registry.register_factory(
            "health_db", HealthAwareDatabaseFactory(), health_check=health_check
        )

        node = AsyncPythonCodeNode(
            code="""
# Get database resource
db = await get_resource("health_db")

# Use the database
data = await db.query("SELECT something")

result = {"data": data, "success": True}
"""
        )

        # First execution should work
        output = await node.async_run(resource_registry=registry)
        assert output["success"] is True

        # Make resource unhealthy
        healthy_state["is_healthy"] = False

        # Next access should recreate the resource
        # (In real scenario, this would create a fresh healthy resource)
        output2 = await node.async_run(resource_registry=registry)
        assert output2["success"] is True  # Should still work with recreated resource
