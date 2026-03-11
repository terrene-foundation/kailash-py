"""
Tier 3 E2E Test: Verify complete DataFlow workflow with health check fix.

This test replicates the exact production scenario that was failing:
- DataFlow model with PostgreSQL
- Generated CRUD nodes
- AsyncLocal Runtime execution
- Internal EnterpriseConnectionPool health checks

Bug: #TIMEOUT_PARAMETER_BUG
Fix: Removed timeout=5 from health_check() execute_query() call
Expected: DataFlow workflows execute successfully without TypeError
"""

import asyncio
import os
import tempfile

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.test")

pytestmark = [pytest.mark.tier3, pytest.mark.e2e]


@pytest.mark.asyncio
async def test_dataflow_postgresql_workflow_complete():
    """
    Test complete DataFlow workflow with PostgreSQL (the exact failing scenario).

    This replicates the production bug report:
    - Creates DataFlow with PostgreSQL
    - Defines @db.model
    - Generates nodes
    - Executes workflow with AsyncLocalRuntime
    - Verifies no TypeError about timeout parameter
    """
    from dataflow import DataFlow

    from kailash.runtime import AsyncLocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    pg_url = os.getenv("POSTGRES_TEST_URL")
    if not pg_url:
        pytest.skip("POSTGRES_TEST_URL not set in .env.test")

    # Create DataFlow with PostgreSQL
    db = DataFlow(pg_url, auto_migrate=True)

    @db.model
    class Conversation:
        id: str
        user_id: str
        title: str

    await db.initialize()

    try:
        # Build workflow with CRUD operations
        workflow = WorkflowBuilder()

        # CREATE operation
        workflow.add_node(
            "ConversationCreateNode",
            "create",
            {
                "id": "conv-test-123",
                "user_id": "user-456",
                "title": "Test Conversation",
            },
        )

        # READ operation
        workflow.add_node("ConversationReadNode", "read", {"id": "conv-test-123"})

        # LIST operation
        workflow.add_node(
            "ConversationListNode",
            "list",
            {"filter": {"user_id": "user-456"}, "limit": 10},
        )

        # Connect nodes
        workflow.add_connection("create", "id", "read", "id")
        workflow.add_connection("read", "conversation", "list", "trigger")

        # Execute workflow - this will trigger EnterpriseConnectionPool health checks
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        # Verify all operations succeeded without TypeError
        assert "create" in results
        assert results["create"]["id"] == "conv-test-123"
        assert results["create"]["user_id"] == "user-456"
        assert results["create"]["title"] == "Test Conversation"

        assert "read" in results
        assert results["read"]["id"] == "conv-test-123"

        assert "list" in results
        assert len(results["list"]) >= 1
        assert any(c["id"] == "conv-test-123" for c in results["list"])

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_dataflow_mysql_workflow_complete():
    """Test complete DataFlow workflow with MySQL."""
    from dataflow import DataFlow

    from kailash.runtime import AsyncLocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    mysql_url = os.getenv("MYSQL_TEST_URL")
    if not mysql_url:
        pytest.skip("MYSQL_TEST_URL not set in .env.test")

    db = DataFlow(mysql_url, auto_migrate=True)

    @db.model
    class User:
        id: str
        name: str
        email: str

    await db.initialize()

    try:
        workflow = WorkflowBuilder()

        workflow.add_node(
            "UserCreateNode",
            "create",
            {"id": "user-001", "name": "Alice", "email": "alice@example.com"},
        )

        workflow.add_node("UserListNode", "list", {"limit": 10})

        workflow.add_connection("create", "user", "list", "trigger")

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        assert "create" in results
        assert results["create"]["id"] == "user-001"

        assert "list" in results
        assert len(results["list"]) >= 1

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_dataflow_sqlite_workflow_complete():
    """Test complete DataFlow workflow with SQLite."""
    from dataflow import DataFlow

    from kailash.runtime import AsyncLocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    # Use temporary file for SQLite
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

        @db.model
        class Message:
            id: str
            conversation_id: str
            content: str

        await db.initialize()

        workflow = WorkflowBuilder()

        workflow.add_node(
            "MessageCreateNode",
            "create",
            {"id": "msg-001", "conversation_id": "conv-123", "content": "Hello World"},
        )

        workflow.add_node("MessageReadNode", "read", {"id": "msg-001"})

        workflow.add_connection("create", "message", "read", "trigger")

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        assert "create" in results
        assert results["create"]["id"] == "msg-001"
        assert results["create"]["content"] == "Hello World"

        assert "read" in results
        assert results["read"]["id"] == "msg-001"

        await db.close()

    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_dataflow_bulk_operations_with_health_check():
    """Test DataFlow bulk operations work correctly with health checks."""
    from dataflow import DataFlow

    from kailash.runtime import AsyncLocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    pg_url = os.getenv("POSTGRES_TEST_URL")
    if not pg_url:
        pytest.skip("POSTGRES_TEST_URL not set in .env.test")

    db = DataFlow(pg_url, auto_migrate=True)

    @db.model
    class Product:
        id: str
        name: str
        price: float

    await db.initialize()

    try:
        workflow = WorkflowBuilder()

        # Bulk create
        workflow.add_node(
            "ProductBulk_CreateNode",
            "bulk_create",
            {
                "data": [
                    {"id": f"prod-{i:03d}", "name": f"Product {i}", "price": i * 10.0}
                    for i in range(100)
                ]
            },
        )

        # List to verify
        workflow.add_node("ProductListNode", "list", {"limit": 150})

        # Count to verify
        workflow.add_node("ProductCountNode", "count", {"filter": {}})

        workflow.add_connection("bulk_create", "created", "list", "trigger")
        workflow.add_connection("list", "products", "count", "trigger")

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        assert "bulk_create" in results
        assert results["bulk_create"]["created_count"] == 100

        assert "list" in results
        assert len(results["list"]) >= 100

        assert "count" in results
        assert results["count"]["count"] >= 100

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_dataflow_concurrent_workflows():
    """Test multiple concurrent DataFlow workflows execute without errors."""
    from dataflow import DataFlow

    from kailash.runtime import AsyncLocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    pg_url = os.getenv("POSTGRES_TEST_URL")
    if not pg_url:
        pytest.skip("POSTGRES_TEST_URL not set in .env.test")

    db = DataFlow(pg_url, auto_migrate=True)

    @db.model
    class Session:
        id: str
        user_id: str
        active: bool

    await db.initialize()

    try:

        async def run_workflow(session_id: str, user_id: str):
            """Helper to run a single workflow."""
            workflow = WorkflowBuilder()

            workflow.add_node(
                "SessionCreateNode",
                "create",
                {"id": session_id, "user_id": user_id, "active": True},
            )

            workflow.add_node("SessionReadNode", "read", {"id": session_id})

            workflow.add_connection("create", "session", "read", "trigger")

            runtime = AsyncLocalRuntime()
            results, _ = await runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            return results

        # Run 10 workflows concurrently
        tasks = [run_workflow(f"session-{i:03d}", f"user-{i % 3}") for i in range(10)]

        results_list = await asyncio.gather(*tasks)

        # Verify all succeeded
        assert len(results_list) == 10
        for i, results in enumerate(results_list):
            assert "create" in results
            assert results["create"]["id"] == f"session-{i:03d}"
            assert "read" in results
            assert results["read"]["id"] == f"session-{i:03d}"

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_production_scenario_ai_hub_workflow():
    """
    Replicate exact production scenario from bug report: AI Hub Phase 3.

    From bug report:
    - Backend API returns: {"detail":"Failed to create conversation"}
    - HTTP 500 Internal Server Error
    - Workflow executes until database node execution
    - Health check fails with timeout parameter error
    """
    from dataflow import DataFlow

    from kailash.runtime import AsyncLocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    pg_url = os.getenv("POSTGRES_TEST_URL")
    if not pg_url:
        pytest.skip("POSTGRES_TEST_URL not set in .env.test")

    # Replicate AI Hub schema
    db = DataFlow(pg_url, auto_migrate=True)

    @db.model
    class Conversation:
        id: str
        user_id: str
        agent_id: str
        title: str
        status: str
        parent_conversation_id: str = None
        branch_point_message_id: str = None
        last_message_at: str = None
        metadata_json: str = None

    await db.initialize()

    try:
        # Replicate production workflow
        workflow = WorkflowBuilder()

        workflow.add_node(
            "ConversationCreateNode",
            "create_conversation",
            {
                "id": "conv_12b0e30cc818",
                "user_id": "dev_user_123",
                "agent_id": "agent_gpt4",
                "title": "New Conversation",
                "status": "active",
                "parent_conversation_id": None,
                "branch_point_message_id": None,
                "last_message_at": "2024-01-01T00:00:00Z",
                "metadata_json": "{}",
            },
        )

        # Execute workflow that was failing in production
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        # This should succeed now (was failing with TypeError before fix)
        assert "create_conversation" in results
        assert results["create_conversation"]["id"] == "conv_12b0e30cc818"
        assert results["create_conversation"]["user_id"] == "dev_user_123"
        assert results["create_conversation"]["status"] == "active"

        # Verify we can read it back
        workflow2 = WorkflowBuilder()
        workflow2.add_node("ConversationReadNode", "read", {"id": "conv_12b0e30cc818"})

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})
        assert results2["read"]["id"] == "conv_12b0e30cc818"

    finally:
        await db.close()
