"""
Integration tests for ErrorEnhancer integration in nodes.py.

Verifies that enhanced error messages are produced during real workflow execution.
"""

import pytest
from dataflow import DataFlow
from dataflow.platform.errors import DataFlowError

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
class TestNodesEnhancedErrors:
    """Test that nodes.py uses ErrorEnhancer for runtime errors."""

    def test_read_node_missing_id_enhanced_error(self, memory_dataflow):
        """Test DF-702: ReadNode missing id produces enhanced error."""
        db = memory_dataflow

        @db.model
        class User:
            id: str
            name: str

        # Try to read without id - runtime should catch enhanced error
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserReadNode",
            "read",
            {
                # Missing 'id' parameter!
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution failed with enhanced error
        assert "read" in results
        result = results["read"]
        assert isinstance(result, dict), "Expected error dict"
        assert result.get("failed") is True, "Node should have failed"
        assert "error" in result, "Should have error message"

        # Verify enhanced error message contains key information
        error_msg = result["error"]
        assert "UserReadNode" in error_msg or "read" in error_msg
        assert "id" in error_msg.lower() or "record_id" in error_msg.lower()

        # Verify workflow executed
        assert run_id is not None

    def test_unsafe_filter_operator_enhanced_error(self, memory_dataflow):
        """Test DF-701: Unsafe filter operator produces enhanced error."""
        db = memory_dataflow

        @db.model
        class User:
            id: str
            status: str

        # Try to use unsafe $where operator - runtime should catch enhanced error
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserListNode",
            "list",
            {"filter": {"status": {"$where": "this.age > 18"}}},  # Unsafe!
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution failed with enhanced error
        assert "list" in results
        result = results["list"]
        assert isinstance(result, dict), "Expected error dict"
        assert result.get("failed") is True, "Node should have failed"
        assert "error" in result, "Should have error message"

        # Verify enhanced error mentions unsafe operator
        error_msg = result["error"]
        assert "$where" in error_msg or "unsafe" in error_msg.lower()

        # Verify workflow executed
        assert run_id is not None

    def test_update_node_missing_filter_id_enhanced_error(self, memory_dataflow):
        """Test DF-704: UpdateNode missing filter id produces enhanced error."""
        db = memory_dataflow

        @db.model
        class User:
            id: str
            name: str

        # Try to update without id in filter - runtime should catch enhanced error
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpdateNode",
            "update",
            {"filter": {}, "fields": {"name": "Updated"}},  # Missing 'id'!
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution failed with enhanced error
        assert "update" in results
        result = results["update"]
        assert isinstance(result, dict), "Expected error dict"
        assert result.get("failed") is True, "Node should have failed"
        assert "error" in result, "Should have error message"

        # Verify enhanced error mentions filter and id
        error_msg = result["error"]
        assert "filter" in error_msg.lower() or "id" in error_msg.lower()

        # Verify workflow executed
        assert run_id is not None

    def test_delete_node_missing_id_enhanced_error(self, memory_dataflow):
        """Test DF-705: DeleteNode missing id produces enhanced error."""
        db = memory_dataflow

        @db.model
        class User:
            id: str
            name: str

        # Try to delete without id - runtime should catch enhanced error
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserDeleteNode",
            "delete",
            {
                # Missing 'id' parameter!
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution failed with enhanced error
        assert "delete" in results
        result = results["delete"]
        assert isinstance(result, dict), "Expected error dict"
        assert result.get("failed") is True, "Node should have failed"
        assert "error" in result, "Should have error message"

        # Verify enhanced error mentions id requirement
        error_msg = result["error"]
        assert "id" in error_msg.lower() or "record_id" in error_msg.lower()

        # Verify workflow executed
        assert run_id is not None

    def test_upsert_node_empty_conflict_on_enhanced_error(self, memory_dataflow):
        """Test DF-706: UpsertNode empty conflict_on produces enhanced error."""
        db = memory_dataflow

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Try to upsert with empty conflict_on - runtime should catch enhanced error
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                "where": {"email": "test@example.com"},
                "conflict_on": [],  # Empty!
                "create": {"id": "user-1", "email": "test@example.com", "name": "Test"},
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution failed with enhanced error
        assert "upsert" in results
        result = results["upsert"]
        assert isinstance(result, dict), "Expected error dict"
        assert result.get("failed") is True, "Node should have failed"
        assert "error" in result, "Should have error message"

        # Verify enhanced error mentions conflict_on
        error_msg = result["error"]
        assert "conflict_on" in error_msg.lower()

        # Verify workflow executed
        assert run_id is not None

    def test_upsert_node_missing_where_enhanced_error(self, memory_dataflow):
        """Test DF-707: UpsertNode missing where produces enhanced error.

        Note: This test expects WorkflowValidationError because workflow validation
        catches missing required parameters before node execution.
        """
        db = memory_dataflow

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Try to upsert without where - workflow validation should catch this
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                # Missing 'where'!
                "create": {"id": "user-1", "email": "test@example.com", "name": "Test"}
            },
        )

        runtime = LocalRuntime()

        # Workflow validation raises error before execution
        from kailash.sdk_exceptions import WorkflowValidationError

        with pytest.raises(WorkflowValidationError) as exc_info:
            runtime.execute(workflow.build())

        # Verify error mentions 'where' parameter
        error_str = str(exc_info.value)
        assert "where" in error_str.lower()

    def test_upsert_node_missing_operations_enhanced_error(self, memory_dataflow):
        """Test DF-708: UpsertNode missing update/create produces enhanced error."""
        db = memory_dataflow

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Try to upsert without update or create - runtime should catch enhanced error
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                "where": {"email": "test@example.com"},
                # Missing both 'update' and 'create'!
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution failed with enhanced error
        assert "upsert" in results
        result = results["upsert"]
        assert isinstance(result, dict), "Expected error dict"
        assert result.get("failed") is True, "Node should have failed"
        assert "error" in result, "Should have error message"

        # Verify enhanced error mentions update/create
        error_msg = result["error"]
        assert "update" in error_msg.lower() or "create" in error_msg.lower()

        # Verify workflow executed
        assert run_id is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
