"""Simple E2E test for WorkflowConnectionPool."""

import asyncio
import os

import pytest

from kailash import Workflow
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.runtime import LocalRuntime


@pytest.mark.e2e
@pytest.mark.asyncio
class TestConnectionPoolSimple:
    """Simple E2E test for connection pool."""

    @pytest.fixture
    def db_config(self):
        """Database configuration."""
        return {
            "name": "test_pool",
            "database_type": "postgresql",
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", 5433)),
            "database": os.getenv("POSTGRES_DB", "kailash_test"),
            "user": os.getenv("POSTGRES_USER", "admin"),
            "password": os.getenv("POSTGRES_PASSWORD", "admin"),
            "min_connections": 2,
            "max_connections": 5,
        }

    async def test_basic_pool_operations(self, db_config):
        """Test basic connection pool operations in a workflow."""
        # Create workflow
        workflow = Workflow("test_pool", "Test Pool")

        # Add pool node
        pool = WorkflowConnectionPool(**db_config)

        # Test direct operations first
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
                "query": "SELECT 1 as test, NOW() as timestamp",
                "fetch_mode": "one",
            }
        )
        assert query_result["success"] is True
        assert query_result["data"]["test"] == 1

        # Release connection
        release_result = await pool.process(
            {"operation": "release", "connection_id": conn_id}
        )
        assert release_result["status"] == "released"

        # Get stats
        stats = await pool.process({"operation": "stats"})
        assert stats["queries"]["executed"] == 1
        assert stats["connections"]["created"] >= 2

        # Clean up
        await pool._cleanup()

        print("✅ All basic pool operations passed!")

    async def test_workflow_with_pool(self, db_config):
        """Test connection pool in a workflow context."""
        # Create workflow
        workflow = Workflow("analytics", "Analytics Workflow")

        # Add nodes
        workflow.add_node("pool", WorkflowConnectionPool(), **db_config)

        workflow.add_node(
            "init",
            "PythonCodeNode",
            code="""
# Initialize the pool
result = {"operation": "initialize"}
""",
        )

        workflow.add_node(
            "query",
            "PythonCodeNode",
            code="""
# Prepare query operation
pool_status = inputs.get("pool", {})
result = {
    "operation": "acquire"
}
""",
        )

        # Connect nodes
        workflow.connect("init", "pool")
        workflow.connect("pool", "query")

        # Execute workflow
        runtime = LocalRuntime(enable_async=True)

        # Provide runtime parameters to satisfy validation
        params = {"pool": {"operation": "initialize"}, "query": {"pool": {}}}

        outputs, error = await runtime.execute_async(workflow, parameters=params)

        if error:
            print(f"Error: {error}")
            print(f"Outputs: {outputs}")

        # Basic check
        assert error is None
        assert "pool" in outputs

        # Clean up pool
        pool_node = workflow.get_node("pool")
        await pool_node._cleanup()

        print("✅ Workflow execution passed!")


if __name__ == "__main__":
    # Run tests directly
    test = TestConnectionPoolSimple()
    config = test.db_config()

    asyncio.run(test.test_basic_pool_operations(config))
    asyncio.run(test.test_workflow_with_pool(config))
