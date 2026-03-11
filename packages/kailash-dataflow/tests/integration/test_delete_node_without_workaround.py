"""
Integration Tests for DataFlow DeleteNode Without Workaround

Tests that verify DeleteNode works correctly AFTER the Core SDK fix,
eliminating the need for the temporary workaround at line 1402-1414 in nodes.py.

Current Workaround Location:
  src/dataflow/core/nodes.py:1402-1414

The workaround filters out node_id injected by Core SDK to prevent namespace
collision with user's id parameter. After Core SDK fix (_node_id instead of id),
this workaround becomes unnecessary.

Expected Fix:
- Core SDK injects _node_id instead of id
- User's id parameter preserved without filtering
- DeleteNode works directly without workaround

Test Status: RED (Expected to FAIL before Core SDK fix and workaround removal)
After Fix: GREEN (Expected to PASS after Core SDK fix and workaround removal)
"""

import pytest

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestDeleteNodeWithoutWorkaround:
    """Test DeleteNode works correctly without the temporary workaround."""

    @pytest.mark.integration
    @pytest.mark.timeout(5)
    @pytest.mark.asyncio
    async def test_delete_node_with_empty_params_raises_error(self, test_suite):
        """
        DeleteNode with no params should raise ValueError.

        CRITICAL: After Core SDK fix, this should raise ValueError because
        no id parameter is provided. The workaround currently filters node_id,
        which makes id appear missing even when it shouldn't be.

        Expected Behavior:
        - BEFORE FIX (with workaround): Raises ValueError (workaround filters node_id)
        - AFTER FIX (no workaround): Raises ValueError (no id provided)
        - This test ensures validation works correctly in both cases
        """
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class TestRecord:
            name: str

        await db.initialize()

        # Create a test record first
        workflow = WorkflowBuilder()
        workflow.add_node("TestRecordCreateNode", "create", {"name": "test"})
        runtime = LocalRuntime()
        results, _ = await runtime.async_execute(workflow.build())
        created_id = results["create"]["id"]

        # Try to delete without providing id parameter
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node("TestRecordDeleteNode", "delete", {})

        # This should raise ValueError - missing required id parameter
        with pytest.raises(ValueError, match="requires 'id' or 'record_id' parameter"):
            await runtime.async_execute(delete_workflow.build())

    @pytest.mark.integration
    @pytest.mark.timeout(5)
    @pytest.mark.asyncio
    async def test_delete_node_with_int_id_works(self, test_suite):
        """
        DeleteNode with integer id should work correctly.

        This test verifies that numeric IDs work correctly after removing
        the workaround. The Core SDK fix ensures id parameter is not
        overwritten by node_id.
        """
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Product:
            name: str
            price: int

        await db.initialize()

        # Create a product
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductCreateNode", "create", {"name": "Widget", "price": 100}
        )
        runtime = LocalRuntime()
        results, _ = await runtime.async_execute(workflow.build())
        product_id = results["create"]["id"]

        # Verify it was created
        assert isinstance(product_id, int), f"Expected int ID, got {type(product_id)}"

        # Delete with integer id - should work without workaround
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node("ProductDeleteNode", "delete", {"id": product_id})
        delete_results, _ = await runtime.async_execute(delete_workflow.build())

        # Verify deletion succeeded
        assert delete_results["delete"]["deleted"] is True
        assert delete_results["delete"]["id"] == product_id

        # Verify record is gone
        read_workflow = WorkflowBuilder()
        read_workflow.add_node(
            "ProductReadNode", "read", {"id": product_id, "raise_on_not_found": False}
        )
        read_results, _ = await runtime.async_execute(read_workflow.build())
        assert read_results["read"]["found"] is False

    @pytest.mark.integration
    @pytest.mark.timeout(5)
    @pytest.mark.asyncio
    async def test_delete_node_with_string_id_works(self, test_suite):
        """
        DeleteNode with string id should work correctly.

        This is the CRITICAL test - string IDs are what caused the original bug.
        The workaround filtered non-numeric strings thinking they were node_ids.
        After the Core SDK fix, string IDs should work directly.

        Expected Behavior:
        - BEFORE FIX: String IDs might be filtered by workaround
        - AFTER FIX: String IDs work directly, preserved correctly
        """
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Session:
            id: str  # Explicit string ID
            user_id: str
            token: str

        await db.initialize()

        # Create a session with string ID
        session_id = "sess-uuid-abc123"
        user_id = "user-456"

        workflow = WorkflowBuilder()
        workflow.add_node(
            "SessionCreateNode",
            "create",
            {"id": session_id, "user_id": user_id, "token": "abc123token"},
        )
        runtime = LocalRuntime()
        results, _ = await runtime.async_execute(workflow.build())

        # Verify string ID was preserved
        assert results["create"]["id"] == session_id
        assert isinstance(results["create"]["id"], str)

        # Delete with string id - CRITICAL TEST
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node("SessionDeleteNode", "delete", {"id": session_id})
        delete_results, _ = await runtime.async_execute(delete_workflow.build())

        # Verify deletion succeeded with string ID
        assert delete_results["delete"]["deleted"] is True
        assert delete_results["delete"]["id"] == session_id
        assert isinstance(delete_results["delete"]["id"], str)

        # Verify record is gone
        read_workflow = WorkflowBuilder()
        read_workflow.add_node(
            "SessionReadNode", "read", {"id": session_id, "raise_on_not_found": False}
        )
        read_results, _ = await runtime.async_execute(read_workflow.build())
        assert read_results["read"]["found"] is False

    @pytest.mark.integration
    @pytest.mark.timeout(5)
    @pytest.mark.asyncio
    async def test_delete_node_preserves_id_type(self, test_suite):
        """
        DeleteNode should preserve the ID type from model definition.

        This test ensures type-aware ID handling works correctly after
        the Core SDK fix and workaround removal.
        """
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Document:
            id: str  # String ID type
            title: str
            content: str

        await db.initialize()

        # Create document with string ID
        doc_id = "doc-uuid-xyz789"
        workflow = WorkflowBuilder()
        workflow.add_node(
            "DocumentCreateNode",
            "create",
            {"id": doc_id, "title": "Test Document", "content": "Test content"},
        )
        runtime = LocalRuntime()
        results, _ = await runtime.async_execute(workflow.build())

        # Type should be preserved
        assert results["create"]["id"] == doc_id
        assert isinstance(results["create"]["id"], str)

        # Delete should also preserve type
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node("DocumentDeleteNode", "delete", {"id": doc_id})
        delete_results, _ = await runtime.async_execute(delete_workflow.build())

        # Verify type preserved in delete result
        assert delete_results["delete"]["id"] == doc_id
        assert isinstance(delete_results["delete"]["id"], str)
        assert delete_results["delete"]["deleted"] is True


class TestDeleteNodeParameterHandling:
    """Test parameter handling in DeleteNode after Core SDK fix."""

    @pytest.mark.integration
    @pytest.mark.timeout(5)
    @pytest.mark.asyncio
    async def test_delete_with_record_id_parameter(self, test_suite):
        """
        DeleteNode should accept both 'id' and 'record_id' parameters.

        Tests that the alternative parameter name works correctly.
        """
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Item:
            name: str
            quantity: int

        await db.initialize()

        # Create item
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ItemCreateNode", "create", {"name": "Test Item", "quantity": 10}
        )
        runtime = LocalRuntime()
        results, _ = await runtime.async_execute(workflow.build())
        item_id = results["create"]["id"]

        # Delete using record_id parameter instead of id
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node("ItemDeleteNode", "delete", {"record_id": item_id})
        delete_results, _ = await runtime.async_execute(delete_workflow.build())

        # Should work correctly
        assert delete_results["delete"]["deleted"] is True
        assert delete_results["delete"]["id"] == item_id

    @pytest.mark.integration
    @pytest.mark.timeout(5)
    @pytest.mark.asyncio
    async def test_node_id_does_not_interfere_with_user_id(self, test_suite):
        """
        CRITICAL: Node identifier should not interfere with user's id parameter.

        This is the core test that validates the Core SDK fix. The node_id
        (which is a string like "delete_node") should NOT overwrite the user's
        id parameter (which could be int, string UUID, etc.).

        Expected Behavior:
        - BEFORE FIX: node_id="delete_node" overwrites user id
        - AFTER FIX: _node_id="delete_node" is separate, user id preserved
        """
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Order:
            order_number: str
            amount: int

        await db.initialize()

        # Create order
        workflow = WorkflowBuilder()
        workflow.add_node(
            "OrderCreateNode", "create", {"order_number": "ORD-001", "amount": 500}
        )
        runtime = LocalRuntime()
        results, _ = await runtime.async_execute(workflow.build())
        order_id = results["create"]["id"]

        # Delete with specific node_id - this node identifier should NOT
        # interfere with the user's id parameter for the record to delete
        delete_workflow = WorkflowBuilder()
        # Node identifier is "my_delete_node" (string)
        # User's id parameter is order_id (integer)
        # These should be in separate namespaces after the fix
        delete_workflow.add_node("OrderDeleteNode", "my_delete_node", {"id": order_id})
        delete_results, _ = await runtime.async_execute(delete_workflow.build())

        # CRITICAL ASSERTION: User's id should be used for deletion, not node_id
        assert delete_results["my_delete_node"]["deleted"] is True
        assert delete_results["my_delete_node"]["id"] == order_id
        assert delete_results["my_delete_node"]["id"] != "my_delete_node", (
            "User's id parameter was overwritten by node_id! "
            "This means Core SDK fix is not applied."
        )


class TestDeleteNodeWorkflowIntegration:
    """Test DeleteNode in complete workflow scenarios."""

    @pytest.mark.integration
    @pytest.mark.timeout(5)
    @pytest.mark.asyncio
    async def test_create_read_delete_workflow(self, test_suite):
        """
        Test complete CREATE -> READ -> DELETE workflow.

        Ensures the entire workflow works correctly with proper ID handling.
        """
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Task:
            title: str
            completed: bool

        await db.initialize()

        runtime = LocalRuntime()

        # CREATE
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "TaskCreateNode", "create", {"title": "Complete tests", "completed": False}
        )
        create_results, _ = await runtime.async_execute(create_workflow.build())
        task_id = create_results["create"]["id"]

        # READ - verify it exists
        read_workflow = WorkflowBuilder()
        read_workflow.add_node("TaskReadNode", "read", {"id": task_id})
        read_results, _ = await runtime.async_execute(read_workflow.build())
        assert read_results["read"]["found"] is True
        assert read_results["read"]["title"] == "Complete tests"

        # DELETE
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node("TaskDeleteNode", "delete", {"id": task_id})
        delete_results, _ = await runtime.async_execute(delete_workflow.build())
        assert delete_results["delete"]["deleted"] is True

        # READ AGAIN - should not be found
        read_again_workflow = WorkflowBuilder()
        read_again_workflow.add_node(
            "TaskReadNode",
            "read_after_delete",
            {"id": task_id, "raise_on_not_found": False},
        )
        read_again_results, _ = await runtime.async_execute(read_again_workflow.build())
        assert read_again_results["read_after_delete"]["found"] is False

    @pytest.mark.integration
    @pytest.mark.timeout(5)
    @pytest.mark.asyncio
    async def test_delete_with_workflow_connections(self, test_suite):
        """
        Test DeleteNode with workflow connections passing id between nodes.

        This tests that ID parameters flow correctly through workflow connections
        without being overwritten by node identifiers.
        """
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Comment:
            text: str
            author: str

        await db.initialize()

        # Create workflow with connections
        workflow = WorkflowBuilder()

        # Create comment
        workflow.add_node(
            "CommentCreateNode",
            "create_comment",
            {"text": "Test comment", "author": "Alice"},
        )

        # Delete comment using id from create node
        workflow.add_node("CommentDeleteNode", "delete_comment", {})
        workflow.add_connection("create_comment", "delete_comment", "id", "id")

        runtime = LocalRuntime()
        results, _ = await runtime.async_execute(workflow.build())

        # Verify comment was created and deleted
        assert "create_comment" in results
        assert "delete_comment" in results
        assert results["delete_comment"]["deleted"] is True

        # The id should be the record id, not any node identifier
        comment_id = results["create_comment"]["id"]
        assert results["delete_comment"]["id"] == comment_id
        assert isinstance(comment_id, int)  # Auto-generated int ID


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
