#!/usr/bin/env python3
"""
Unit Tests for Workflow Binding (TODO-154)

Tests the DataFlowWorkflowBinder class and workflow integration with DataFlow.
Uses SQLite in-memory databases following Tier 1 testing guidelines.

Test coverage:
1. Binder initialization
2. create_workflow() - returns WorkflowBuilder, generates IDs, stores context
3. _resolve_node_type() - maps model+operation to node type string
4. _resolve_node_type() validation - errors for unregistered models, invalid operations
5. add_model_node() - adds node to workflow correctly
6. add_model_node() with connections - connections are passed through
7. add_model_node() validation - rejects invalid model/operation
8. execute() - delegates to runtime correctly
9. get_available_nodes() - returns correct operations per model
10. get_available_nodes() filtered - filters by model name
11. Cross-model workflow - multiple models in same workflow
12. DataFlow.create_workflow() - engine method works
13. DataFlow.add_node() - engine method delegates correctly
14. DataFlow.execute_workflow() - engine method delegates correctly
15. DataFlow.get_available_nodes() - engine method works
16. Backward compatibility - existing WorkflowBuilder.add_node() still works
17. All 11 operations - verify all CRUD+bulk operations map correctly
18. Multiple workflows - can create multiple workflows from same DataFlow
19. Workflow ID generation - auto-generated IDs are unique
20. Error message quality - error messages mention available models/operations
"""

from unittest.mock import MagicMock, patch

import pytest
from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.unit
class TestDataFlowWorkflowBinder:
    """Test the DataFlowWorkflowBinder class."""

    # ---- Test 1: Binder initialization ----

    def test_binder_initialization(self, memory_dataflow):
        """Binder is initialized with DataFlow instance."""
        db = memory_dataflow

        # Verify binder was initialized during DataFlow creation
        assert hasattr(db, "_workflow_binder")
        assert db._workflow_binder is not None
        assert db._workflow_binder.dataflow_instance is db

    # ---- Test 2: create_workflow() ----

    def test_create_workflow_returns_workflow_builder(self, memory_dataflow):
        """create_workflow() returns a WorkflowBuilder instance."""
        db = memory_dataflow
        workflow = db.create_workflow()

        assert isinstance(workflow, WorkflowBuilder)

    def test_create_workflow_with_explicit_id(self, memory_dataflow):
        """create_workflow() uses provided workflow_id."""
        db = memory_dataflow
        workflow = db.create_workflow("my_custom_workflow")

        assert hasattr(workflow, "_dataflow_workflow_id")
        assert workflow._dataflow_workflow_id == "my_custom_workflow"

    def test_create_workflow_generates_unique_ids(self, memory_dataflow):
        """create_workflow() generates unique IDs when not provided."""
        db = memory_dataflow
        workflow1 = db.create_workflow()
        workflow2 = db.create_workflow()

        assert workflow1._dataflow_workflow_id != workflow2._dataflow_workflow_id
        assert workflow1._dataflow_workflow_id.startswith("dataflow_")
        assert workflow2._dataflow_workflow_id.startswith("dataflow_")

    def test_create_workflow_stores_dataflow_context(self, memory_dataflow):
        """create_workflow() attaches DataFlow context to workflow."""
        db = memory_dataflow
        workflow = db.create_workflow()

        assert hasattr(workflow, "_dataflow_context")
        assert workflow._dataflow_context is db

    def test_create_workflow_tracks_workflow(self, memory_dataflow):
        """create_workflow() stores workflow in binder's tracking dict."""
        db = memory_dataflow
        workflow = db.create_workflow("tracked_workflow")

        assert "tracked_workflow" in db._workflow_binder._workflows
        assert db._workflow_binder._workflows["tracked_workflow"] is workflow

    # ---- Test 3: _resolve_node_type() ----

    def test_resolve_node_type_basic(self, memory_dataflow):
        """_resolve_node_type() correctly maps model+operation to node type."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        binder = db._workflow_binder

        # Test basic operations
        assert binder._resolve_node_type("User", "Create") == "UserCreateNode"
        assert binder._resolve_node_type("User", "Read") == "UserReadNode"
        assert binder._resolve_node_type("User", "Update") == "UserUpdateNode"
        assert binder._resolve_node_type("User", "Delete") == "UserDeleteNode"
        assert binder._resolve_node_type("User", "List") == "UserListNode"
        assert binder._resolve_node_type("User", "Upsert") == "UserUpsertNode"
        assert binder._resolve_node_type("User", "Count") == "UserCountNode"

    def test_resolve_node_type_bulk_operations(self, memory_dataflow):
        """_resolve_node_type() correctly maps bulk operations."""
        db = memory_dataflow

        @db.model
        class Product:
            name: str

        binder = db._workflow_binder

        assert (
            binder._resolve_node_type("Product", "BulkCreate")
            == "ProductBulkCreateNode"
        )
        assert (
            binder._resolve_node_type("Product", "BulkUpdate")
            == "ProductBulkUpdateNode"
        )
        assert (
            binder._resolve_node_type("Product", "BulkDelete")
            == "ProductBulkDeleteNode"
        )
        assert (
            binder._resolve_node_type("Product", "BulkUpsert")
            == "ProductBulkUpsertNode"
        )

    # ---- Test 4: _resolve_node_type() validation ----

    def test_resolve_node_type_invalid_model(self, memory_dataflow):
        """_resolve_node_type() raises ValueError for unregistered model."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        binder = db._workflow_binder

        with pytest.raises(ValueError) as exc_info:
            binder._resolve_node_type("NonExistent", "Create")

        error_msg = str(exc_info.value)
        assert "NonExistent" in error_msg
        assert "not registered" in error_msg
        assert "User" in error_msg  # Should mention available models

    def test_resolve_node_type_invalid_operation(self, memory_dataflow):
        """_resolve_node_type() raises ValueError for invalid operation."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        binder = db._workflow_binder

        with pytest.raises(ValueError) as exc_info:
            binder._resolve_node_type("User", "InvalidOp")

        error_msg = str(exc_info.value)
        assert "InvalidOp" in error_msg
        assert "Invalid operation" in error_msg
        # Should mention available operations
        assert "Create" in error_msg or "Available operations" in error_msg

    # ---- Test 5: add_model_node() ----

    def test_add_model_node_basic(self, memory_dataflow):
        """add_model_node() adds node to workflow correctly."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow = db.create_workflow()
        result = db.add_node(
            workflow, "User", "Create", "create_user", {"id": "user-1", "name": "Alice"}
        )

        # Check return value
        assert result == "create_user"

        # Check node was added to workflow (workflow.nodes is a dict keyed by node_id)
        assert len(workflow.nodes) == 1
        assert "create_user" in workflow.nodes
        assert workflow.nodes["create_user"]["type"] == "UserCreateNode"

    def test_add_model_node_with_params(self, memory_dataflow):
        """add_model_node() correctly passes parameters."""
        db = memory_dataflow

        @db.model
        class Order:
            product: str
            quantity: int

        workflow = db.create_workflow()
        db.add_node(
            workflow,
            "Order",
            "Create",
            "create_order",
            {"id": "order-1", "product": "Widget", "quantity": 5},
        )

        node = workflow.nodes["create_order"]
        assert node["config"]["product"] == "Widget"
        assert node["config"]["quantity"] == 5

    # ---- Test 6: add_model_node() with connections ----

    def test_add_model_node_with_connections(self, memory_dataflow):
        """add_model_node() correctly passes connections."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow = db.create_workflow()

        # First node
        db.add_node(
            workflow, "User", "Create", "create_user", {"id": "user-1", "name": "Alice"}
        )

        # Second node with connection
        db.add_node(
            workflow,
            "User",
            "Read",
            "read_user",
            {"id": "${create_user.id}"},
            connections={"create_user": ["id"]},
        )

        # Check nodes were added
        assert len(workflow.nodes) == 2
        assert "create_user" in workflow.nodes
        assert "read_user" in workflow.nodes
        assert workflow.nodes["read_user"]["type"] == "UserReadNode"

    # ---- Test 7: add_model_node() validation ----

    def test_add_model_node_invalid_model(self, memory_dataflow):
        """add_model_node() raises ValueError for invalid model."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow = db.create_workflow()

        with pytest.raises(ValueError) as exc_info:
            db.add_node(workflow, "InvalidModel", "Create", "test", {})

        assert "InvalidModel" in str(exc_info.value)
        assert "not registered" in str(exc_info.value)

    def test_add_model_node_invalid_operation(self, memory_dataflow):
        """add_model_node() raises ValueError for invalid operation."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow = db.create_workflow()

        with pytest.raises(ValueError) as exc_info:
            db.add_node(workflow, "User", "InvalidOp", "test", {})

        assert "InvalidOp" in str(exc_info.value)
        assert "Invalid operation" in str(exc_info.value)

    # ---- Test 8: execute() ----

    def test_execute_delegates_to_runtime(self, memory_dataflow):
        """execute() delegates to runtime correctly."""
        db = memory_dataflow

        @db.model
        class Item:
            name: str

        workflow = db.create_workflow()
        db.add_node(
            workflow,
            "Item",
            "Create",
            "create_item",
            {"id": "item-1", "name": "Test Item"},
        )

        # Use mock runtime for unit test
        mock_runtime = MagicMock(spec=LocalRuntime)
        mock_runtime.execute.return_value = (
            {"create_item": {"id": "item-1"}},
            "run-123",
        )

        results, run_id = db.execute_workflow(workflow, {}, runtime=mock_runtime)

        # Verify runtime.execute was called
        mock_runtime.execute.assert_called_once()
        assert results == {"create_item": {"id": "item-1"}}
        assert run_id == "run-123"

    def test_execute_creates_default_runtime(self, memory_dataflow):
        """execute() creates LocalRuntime if not provided."""
        db = memory_dataflow

        @db.model
        class Item:
            name: str

        workflow = db.create_workflow()
        db.add_node(
            workflow, "Item", "Create", "create_item", {"id": "item-1", "name": "Test"}
        )

        # Patch LocalRuntime to verify it's instantiated
        with patch("dataflow.core.workflow_binding.LocalRuntime") as MockRuntime:
            mock_instance = MagicMock()
            mock_instance.execute.return_value = ({}, "run-id")
            MockRuntime.return_value = mock_instance

            db.execute_workflow(workflow)

            MockRuntime.assert_called_once()
            mock_instance.execute.assert_called_once()

    # ---- Test 9: get_available_nodes() ----

    def test_get_available_nodes_all_models(self, memory_dataflow):
        """get_available_nodes() returns correct operations for all models."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        @db.model
        class Product:
            title: str

        nodes = db.get_available_nodes()

        assert "User" in nodes
        assert "Product" in nodes
        assert "Create" in nodes["User"]
        assert "Read" in nodes["User"]
        assert "Update" in nodes["User"]
        assert "Delete" in nodes["User"]
        assert "List" in nodes["User"]
        assert "Upsert" in nodes["User"]
        assert "Count" in nodes["User"]
        assert "BulkCreate" in nodes["User"]
        assert "BulkUpdate" in nodes["User"]
        assert "BulkDelete" in nodes["User"]
        assert "BulkUpsert" in nodes["User"]

    # ---- Test 10: get_available_nodes() filtered ----

    def test_get_available_nodes_filtered(self, memory_dataflow):
        """get_available_nodes() filters by model name."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        @db.model
        class Product:
            title: str

        nodes = db.get_available_nodes("User")

        assert "User" in nodes
        assert "Product" not in nodes
        assert len(nodes) == 1

    def test_get_available_nodes_nonexistent_model(self, memory_dataflow):
        """get_available_nodes() returns empty dict for nonexistent model."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        nodes = db.get_available_nodes("NonExistent")

        assert nodes == {}

    # ---- Test 11: Cross-model workflow ----

    def test_cross_model_workflow(self, memory_dataflow):
        """Multiple models can be used in the same workflow."""
        db = memory_dataflow

        @db.model
        class User:
            name: str
            email: str

        @db.model
        class Order:
            user_id: str
            product: str

        workflow = db.create_workflow("checkout")

        # Add User operation
        db.add_node(
            workflow,
            "User",
            "Create",
            "create_user",
            {"id": "user-1", "name": "Alice", "email": "alice@test.com"},
        )

        # Add Order operation with connection
        db.add_node(
            workflow,
            "Order",
            "Create",
            "create_order",
            {"id": "order-1", "user_id": "${create_user.id}", "product": "Widget"},
            connections={"create_user": ["id"]},
        )

        # Verify workflow has both nodes (nodes is dict keyed by node_id)
        assert len(workflow.nodes) == 2
        assert "create_user" in workflow.nodes
        assert "create_order" in workflow.nodes
        assert workflow.nodes["create_user"]["type"] == "UserCreateNode"
        assert workflow.nodes["create_order"]["type"] == "OrderCreateNode"

    # ---- Test 12: DataFlow.create_workflow() ----

    def test_dataflow_create_workflow(self, memory_dataflow):
        """DataFlow.create_workflow() engine method works."""
        db = memory_dataflow
        workflow = db.create_workflow("test_workflow")

        assert isinstance(workflow, WorkflowBuilder)
        assert workflow._dataflow_workflow_id == "test_workflow"
        assert workflow._dataflow_context is db

    # ---- Test 13: DataFlow.add_node() ----

    def test_dataflow_add_node(self, memory_dataflow):
        """DataFlow.add_node() engine method delegates correctly."""
        db = memory_dataflow

        @db.model
        class Task:
            title: str

        workflow = db.create_workflow()
        result = db.add_node(
            workflow,
            "Task",
            "Create",
            "create_task",
            {"id": "task-1", "title": "Test Task"},
        )

        assert result == "create_task"
        assert len(workflow.nodes) == 1

    # ---- Test 14: DataFlow.execute_workflow() ----

    def test_dataflow_execute_workflow(self, memory_dataflow):
        """DataFlow.execute_workflow() engine method delegates correctly."""
        db = memory_dataflow

        @db.model
        class Task:
            title: str

        workflow = db.create_workflow()
        db.add_node(
            workflow, "Task", "Create", "create_task", {"id": "task-1", "title": "Test"}
        )

        mock_runtime = MagicMock(spec=LocalRuntime)
        mock_runtime.execute.return_value = ({"create_task": {}}, "run-id")

        results, run_id = db.execute_workflow(
            workflow, {"input": "value"}, runtime=mock_runtime
        )

        mock_runtime.execute.assert_called_once()
        # Check inputs were passed
        call_args = mock_runtime.execute.call_args
        assert call_args[0][1] == {"input": "value"}

    # ---- Test 15: DataFlow.get_available_nodes() ----

    def test_dataflow_get_available_nodes(self, memory_dataflow):
        """DataFlow.get_available_nodes() engine method works."""
        db = memory_dataflow

        @db.model
        class Widget:
            name: str

        nodes = db.get_available_nodes()

        assert "Widget" in nodes
        assert "Create" in nodes["Widget"]

    # ---- Test 16: Backward compatibility ----

    def test_backward_compatibility_workflow_builder(self, memory_dataflow):
        """Existing WorkflowBuilder.add_node() pattern still works."""
        db = memory_dataflow

        @db.model
        class User:
            name: str
            email: str

        # OLD PATTERN - should still work
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode",
            "create",
            {"id": "user-1", "name": "Alice", "email": "alice@test.com"},
        )

        # Verify node was added (nodes is dict keyed by node_id)
        assert len(workflow.nodes) == 1
        assert "create" in workflow.nodes
        assert workflow.nodes["create"]["type"] == "UserCreateNode"

    def test_backward_compatibility_direct_node_registry(self, memory_dataflow):
        """Nodes registered via @db.model are available in NodeRegistry."""
        from kailash.nodes.base import NodeRegistry

        db = memory_dataflow

        @db.model
        class Contact:
            name: str

        # Node should be in registry
        node_class = NodeRegistry.get("ContactCreateNode")
        assert node_class is not None

    # ---- Test 17: All 11 operations ----

    def test_all_eleven_operations(self, memory_dataflow):
        """All 11 CRUD+bulk operations map correctly."""
        db = memory_dataflow

        @db.model
        class Entity:
            value: str

        binder = db._workflow_binder

        # All expected operations
        expected_ops = [
            ("Create", "EntityCreateNode"),
            ("Read", "EntityReadNode"),
            ("Update", "EntityUpdateNode"),
            ("Delete", "EntityDeleteNode"),
            ("List", "EntityListNode"),
            ("Upsert", "EntityUpsertNode"),
            ("Count", "EntityCountNode"),
            ("BulkCreate", "EntityBulkCreateNode"),
            ("BulkUpdate", "EntityBulkUpdateNode"),
            ("BulkDelete", "EntityBulkDeleteNode"),
            ("BulkUpsert", "EntityBulkUpsertNode"),
        ]

        for op_name, expected_node_type in expected_ops:
            resolved = binder._resolve_node_type("Entity", op_name)
            assert (
                resolved == expected_node_type
            ), f"Operation {op_name} should resolve to {expected_node_type}"

    def test_all_operations_in_operation_map(self, memory_dataflow):
        """Verify OPERATION_MAP has exactly 11 operations."""
        from dataflow.core.workflow_binding import DataFlowWorkflowBinder

        assert len(DataFlowWorkflowBinder.OPERATION_MAP) == 11

        expected_keys = {
            "Create",
            "Read",
            "Update",
            "Delete",
            "List",
            "Upsert",
            "Count",
            "BulkCreate",
            "BulkUpdate",
            "BulkDelete",
            "BulkUpsert",
        }
        assert set(DataFlowWorkflowBinder.OPERATION_MAP.keys()) == expected_keys

    # ---- Test 18: Multiple workflows ----

    def test_multiple_workflows_from_same_dataflow(self, memory_dataflow):
        """Can create multiple workflows from same DataFlow instance."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow1 = db.create_workflow("workflow_1")
        workflow2 = db.create_workflow("workflow_2")
        workflow3 = db.create_workflow("workflow_3")

        # All workflows should be different objects
        assert workflow1 is not workflow2
        assert workflow2 is not workflow3
        assert workflow1 is not workflow3

        # All should have same DataFlow context
        assert workflow1._dataflow_context is db
        assert workflow2._dataflow_context is db
        assert workflow3._dataflow_context is db

        # All should be tracked
        assert len(db._workflow_binder._workflows) == 3

    # ---- Test 19: Workflow ID generation ----

    def test_workflow_id_uniqueness(self, memory_dataflow):
        """Auto-generated workflow IDs are unique."""
        db = memory_dataflow
        ids = set()

        for _ in range(100):
            workflow = db.create_workflow()
            ids.add(workflow._dataflow_workflow_id)

        # All 100 IDs should be unique
        assert len(ids) == 100

    def test_workflow_id_format(self, memory_dataflow):
        """Auto-generated IDs follow expected format."""
        db = memory_dataflow
        workflow = db.create_workflow()

        # Format: dataflow_{8_hex_chars}
        wf_id = workflow._dataflow_workflow_id
        assert wf_id.startswith("dataflow_")
        assert len(wf_id) == len("dataflow_") + 8  # 8 hex chars

    # ---- Test 20: Error message quality ----

    def test_error_message_lists_available_models(self, memory_dataflow):
        """Error message for unknown model lists available models."""
        db = memory_dataflow

        @db.model
        class Alpha:
            name: str

        @db.model
        class Beta:
            value: int

        workflow = db.create_workflow()

        with pytest.raises(ValueError) as exc_info:
            db.add_node(workflow, "Gamma", "Create", "test", {})

        error_msg = str(exc_info.value)
        assert "Gamma" in error_msg
        # Should mention at least one available model
        assert "Alpha" in error_msg or "Beta" in error_msg

    def test_error_message_lists_available_operations(self, memory_dataflow):
        """Error message for unknown operation lists available operations."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow = db.create_workflow()

        with pytest.raises(ValueError) as exc_info:
            db.add_node(workflow, "User", "FakeOp", "test", {})

        error_msg = str(exc_info.value)
        assert "FakeOp" in error_msg
        assert "Invalid operation" in error_msg
        # Should list available operations
        assert "Available operations" in error_msg or "Create" in error_msg


@pytest.mark.unit
class TestWorkflowBinderHelperMethods:
    """Test helper methods on DataFlowWorkflowBinder."""

    def test_get_workflow(self, memory_dataflow):
        """get_workflow() retrieves previously created workflow."""
        db = memory_dataflow
        workflow = db.create_workflow("test_wf")

        retrieved = db._workflow_binder.get_workflow("test_wf")
        assert retrieved is workflow

    def test_get_workflow_not_found(self, memory_dataflow):
        """get_workflow() returns None for unknown workflow."""
        db = memory_dataflow
        result = db._workflow_binder.get_workflow("nonexistent")
        assert result is None

    def test_list_workflows(self, memory_dataflow):
        """list_workflows() returns all workflow IDs."""
        db = memory_dataflow
        db.create_workflow("wf_a")
        db.create_workflow("wf_b")
        db.create_workflow("wf_c")

        workflow_ids = db._workflow_binder.list_workflows()
        assert len(workflow_ids) == 3
        assert "wf_a" in workflow_ids
        assert "wf_b" in workflow_ids
        assert "wf_c" in workflow_ids


@pytest.mark.unit
class TestWorkflowBinderImports:
    """Test that DataFlowWorkflowBinder is properly exported."""

    def test_import_from_core(self):
        """DataFlowWorkflowBinder can be imported from dataflow.core."""
        from dataflow.core import DataFlowWorkflowBinder

        assert DataFlowWorkflowBinder is not None

    def test_import_from_dataflow(self):
        """DataFlowWorkflowBinder can be imported from dataflow."""
        from dataflow import DataFlowWorkflowBinder

        assert DataFlowWorkflowBinder is not None

    def test_binder_has_operation_map(self):
        """DataFlowWorkflowBinder has OPERATION_MAP class attribute."""
        from dataflow import DataFlowWorkflowBinder

        assert hasattr(DataFlowWorkflowBinder, "OPERATION_MAP")
        assert isinstance(DataFlowWorkflowBinder.OPERATION_MAP, dict)
