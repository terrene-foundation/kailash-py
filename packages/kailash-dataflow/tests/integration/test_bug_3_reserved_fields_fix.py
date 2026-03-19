"""
Integration tests for Bug #3: Reserved Field Names fix.

Verifies that the Core SDK namespace separation (_node_id vs id) works correctly
and users can now freely use 'id' as a parameter name without conflicts.

Bug #3 Fix:
- src/kailash/workflow/graph.py: Inject _node_id instead of id
- src/kailash/nodes/base.py: Use _node_id internally, id property for compatibility
- packages/kailash-dataflow/src/dataflow/core/nodes.py: Removed workaround
"""

import pytest
from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestBug3ReservedFieldsFix:
    """Test that Bug #3 fix works correctly."""

    @pytest.fixture(autouse=True)
    async def setup_and_cleanup(self, test_suite):
        """Setup and cleanup database for each test."""

        async def clean_test_data():
            async with test_suite.get_connection() as connection:
                try:
                    await connection.execute("DROP TABLE IF EXISTS test_models CASCADE")
                    await connection.execute("DROP TABLE IF EXISTS users CASCADE")
                except Exception:
                    pass

        await clean_test_data()
        yield
        await clean_test_data()

    @pytest.mark.asyncio
    async def test_user_can_use_id_parameter(self, test_suite):
        """
        Test that users can now use 'id' as a parameter name without conflicts.

        Before Bug #3 fix: WorkflowBuilder injected id=node_id, causing conflicts
        After Bug #3 fix: WorkflowBuilder injects _node_id=node_id, no conflicts
        """
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class TestModel:
            id: int
            name: str

        await db.initialize()

        # Create record using 'id' parameter (should work without conflicts)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestModelCreateNode",
            "create",
            {"id": 42, "name": "test"},  # Using 'id' parameter freely
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        # Verify record was created with correct ID
        assert results["create"]["id"] == 42, "User's id parameter should be preserved"
        assert results["create"]["name"] == "test"

        # Verify in database
        async with test_suite.get_connection() as conn:
            record = await conn.fetchrow("SELECT * FROM test_models WHERE id = 42")
            assert record is not None, "Record should exist in database"
            assert record["id"] == 42
            assert record["name"] == "test"

    @pytest.mark.asyncio
    async def test_deletenode_works_without_workaround(self, test_suite):
        """
        Test that DeleteNode works correctly without the workaround.

        Before Bug #3 fix: Needed workaround to filter out injected node_id
        After Bug #3 fix: No workaround needed, 'id' parameter works directly
        """
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class User:
            id: int
            username: str

        await db.initialize()

        # First, create a record
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode", "create_user", {"id": 99, "username": "testuser"}
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        assert results["create_user"]["id"] == 99

        # Verify record exists
        async with test_suite.get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM users WHERE id = 99)"
            )
            assert exists, "Record should exist before deletion"

        # Now delete it using 'id' parameter (tests workaround removal)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserDeleteNode",
            "delete_user",
            {"id": 99},  # This should work without workaround
        )

        results, _ = runtime.execute(workflow.build())

        # Verify record was deleted
        async with test_suite.get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM users WHERE id = 99)"
            )
            assert not exists, "Record should be deleted"

    @pytest.mark.asyncio
    async def test_backward_compatibility_node_id_property(self, test_suite):
        """
        Test that node.id property still works for backward compatibility.

        Even though nodes use _node_id internally, the .id property should
        still return the node identifier.
        """
        from kailash.nodes.base import Node

        # Create a simple node
        class TestNode(Node):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)

            def get_parameters(self):
                from kailash.nodes.base import NodeParameter

                return {}

            def run(self, **inputs):
                return {"result": "success"}

        # Create node with _node_id (how WorkflowBuilder does it now)
        node = TestNode(_node_id="my_test_node")

        # Verify backward compatibility - node.id should work
        assert node.id == "my_test_node", (
            "node.id property should return node identifier"
        )
        assert node._node_id == "my_test_node", "_node_id should be set correctly"

    @pytest.mark.asyncio
    async def test_workflow_builder_injects_node_id_correctly(self, test_suite):
        """
        Test that WorkflowBuilder injects _node_id (not id) into nodes.

        This verifies the Core SDK fix in graph.py.
        """
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class TestModel:
            id: int
            name: str

        await db.initialize()

        # Build workflow - WorkflowBuilder should inject _node_id
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestModelCreateNode",
            "my_create_node",  # This will be the node_id
            {"id": 123, "name": "test"},  # User's 'id' parameter
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        # The user's 'id' parameter should be used for the database record
        assert results["my_create_node"]["id"] == 123, (
            "User's id parameter should be preserved"
        )

        # Verify in database
        async with test_suite.get_connection() as conn:
            record = await conn.fetchrow("SELECT * FROM test_models WHERE id = 123")
            assert record is not None
            assert record["id"] == 123  # User's id value, not node_id

    @pytest.mark.asyncio
    async def test_multiple_nodes_with_id_parameters(self, test_suite):
        """
        Test that multiple nodes can all use 'id' parameter without conflicts.

        This ensures the namespace separation works across multiple nodes
        in the same workflow.
        """
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class TestModel:
            id: int
            name: str

        await db.initialize()

        # Build workflow with multiple nodes, all using 'id' parameter
        workflow = WorkflowBuilder()

        workflow.add_node("TestModelCreateNode", "create_1", {"id": 1, "name": "first"})

        workflow.add_node(
            "TestModelCreateNode", "create_2", {"id": 2, "name": "second"}
        )

        workflow.add_node("TestModelCreateNode", "create_3", {"id": 3, "name": "third"})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        # Verify all records created with correct IDs
        assert results["create_1"]["id"] == 1
        assert results["create_2"]["id"] == 2
        assert results["create_3"]["id"] == 3

        # Verify in database
        async with test_suite.get_connection() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM test_models")
            assert count == 3, "All 3 records should be created"

            for expected_id in [1, 2, 3]:
                exists = await conn.fetchval(
                    f"SELECT EXISTS(SELECT 1 FROM test_models WHERE id = {expected_id})"
                )
                assert exists, f"Record with id={expected_id} should exist"
