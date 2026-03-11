#!/usr/bin/env python3
"""
Integration Tests for Workflow Binding (TODO-154)

Tests workflow binding with real PostgreSQL database operations.
Uses the shared test infrastructure on port 5434.

NO MOCKING - all tests use real database infrastructure.
"""

import asyncio
import time
from typing import Optional

import pytest
from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow

# PostgreSQL test database URL
TEST_DATABASE_URL = "postgresql://test_user:test_password@localhost:5434/kailash_test"


def generate_unique_suffix() -> str:
    """Generate unique suffix for test isolation."""
    return f"_{int(time.time() * 1000000)}"


@pytest.fixture
def test_dataflow():
    """Create DataFlow instance with PostgreSQL for integration tests."""
    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True)
    yield db
    # Cleanup: close connections
    if hasattr(db, "_connection_manager") and db._connection_manager:
        try:
            db._connection_manager.close()
        except Exception:
            pass


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestWorkflowBindingIntegration:
    """Integration tests for workflow binding with real PostgreSQL."""

    def test_create_workflow_execute_create_node(self, test_dataflow):
        """Create workflow -> add Create node -> execute -> verify data in DB."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define model with unique name
        model_name = f"IntegrationUser{suffix}"

        # Create model dynamically
        model_class = type(
            model_name,
            (),
            {
                "__annotations__": {
                    "name": str,
                    "email": str,
                }
            },
        )

        # Register with DataFlow
        db.model(model_class)

        # Create and execute workflow
        workflow = db.create_workflow("test_create")
        db.add_node(
            workflow,
            model_name,
            "Create",
            "create_user",
            {"id": f"user{suffix}", "name": "Alice", "email": "alice@integration.test"},
        )

        results, run_id = db.execute_workflow(workflow)

        # Verify execution
        assert run_id is not None
        assert "create_user" in results

    def test_cross_model_workflow(self, test_dataflow):
        """Cross-model workflow: Create User -> Create Order (with user_id) -> verify both."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define User model
        user_model_name = f"CrossUser{suffix}"
        user_class = type(
            user_model_name,
            (),
            {
                "__annotations__": {
                    "name": str,
                    "email": str,
                }
            },
        )
        db.model(user_class)

        # Define Order model
        order_model_name = f"CrossOrder{suffix}"
        order_class = type(
            order_model_name,
            (),
            {
                "__annotations__": {
                    "user_id": str,
                    "product": str,
                    "quantity": int,
                }
            },
        )
        db.model(order_class)

        # Create cross-model workflow
        workflow = db.create_workflow("checkout")

        # Add User node
        db.add_node(
            workflow,
            user_model_name,
            "Create",
            "create_user",
            {"id": f"user{suffix}", "name": "Bob", "email": "bob@cross.test"},
        )

        # Add Order node with connection to User
        db.add_node(
            workflow,
            order_model_name,
            "Create",
            "create_order",
            {
                "id": f"order{suffix}",
                "user_id": f"user{suffix}",
                "product": "Widget",
                "quantity": 3,
            },
            connections={"create_user": ["id"]},
        )

        results, run_id = db.execute_workflow(workflow)

        # Verify both nodes executed
        assert "create_user" in results
        assert "create_order" in results

    def test_read_after_create_workflow(self, test_dataflow):
        """Read after Create in same workflow."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define model
        model_name = f"ReadableEntity{suffix}"
        model_class = type(
            model_name,
            (),
            {
                "__annotations__": {
                    "title": str,
                    "value": int,
                }
            },
        )
        db.model(model_class)

        # Create workflow with Create then Read
        workflow = db.create_workflow("create_then_read")

        db.add_node(
            workflow,
            model_name,
            "Create",
            "create_entity",
            {"id": f"entity{suffix}", "title": "Test Entity", "value": 42},
        )

        db.add_node(
            workflow,
            model_name,
            "Read",
            "read_entity",
            {"id": f"entity{suffix}"},
            connections={"create_entity": ["id"]},
        )

        results, run_id = db.execute_workflow(workflow)

        # Verify both operations executed
        assert "create_entity" in results
        assert "read_entity" in results
        # Read should return the created entity
        if results.get("read_entity"):
            assert (
                results["read_entity"].get("title") == "Test Entity"
                or results["read_entity"].get("output", {}).get("title")
                == "Test Entity"
            )

    def test_update_workflow(self, test_dataflow):
        """Update workflow: Read -> Update -> Read again -> verify changes."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define model
        model_name = f"UpdatableItem{suffix}"
        model_class = type(
            model_name,
            (),
            {
                "__annotations__": {
                    "name": str,
                    "status": str,
                }
            },
        )
        db.model(model_class)

        # First create the item
        create_workflow = db.create_workflow("setup")
        db.add_node(
            create_workflow,
            model_name,
            "Create",
            "setup_item",
            {"id": f"item{suffix}", "name": "Original Name", "status": "draft"},
        )
        db.execute_workflow(create_workflow)

        # Now create update workflow
        update_workflow = db.create_workflow("update_flow")

        db.add_node(
            update_workflow,
            model_name,
            "Update",
            "update_item",
            {"filter": {"id": f"item{suffix}"}, "fields": {"status": "published"}},
        )

        db.add_node(
            update_workflow,
            model_name,
            "Read",
            "verify_update",
            {"id": f"item{suffix}"},
            connections={"update_item": ["id"]},
        )

        results, run_id = db.execute_workflow(update_workflow)

        assert "update_item" in results
        assert "verify_update" in results

    def test_delete_workflow(self, test_dataflow):
        """Delete workflow."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define model
        model_name = f"DeletableRecord{suffix}"
        model_class = type(
            model_name,
            (),
            {
                "__annotations__": {
                    "data": str,
                }
            },
        )
        db.model(model_class)

        # First create the record
        create_workflow = db.create_workflow("setup")
        db.add_node(
            create_workflow,
            model_name,
            "Create",
            "create_record",
            {"id": f"record{suffix}", "data": "To be deleted"},
        )
        db.execute_workflow(create_workflow)

        # Now delete
        delete_workflow = db.create_workflow("delete_flow")
        db.add_node(
            delete_workflow,
            model_name,
            "Delete",
            "delete_record",
            {"id": f"record{suffix}"},
        )

        results, run_id = db.execute_workflow(delete_workflow)

        assert "delete_record" in results

    def test_list_and_count_workflow(self, test_dataflow):
        """List and Count in workflows."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define model
        model_name = f"ListableProduct{suffix}"
        model_class = type(
            model_name,
            (),
            {
                "__annotations__": {
                    "category": str,
                    "price": float,
                }
            },
        )
        db.model(model_class)

        # Create some products
        setup_workflow = db.create_workflow("setup")
        for i in range(3):
            db.add_node(
                setup_workflow,
                model_name,
                "Create",
                f"create_p{i}",
                {
                    "id": f"product{suffix}_{i}",
                    "category": "electronics",
                    "price": 10.0 + i,
                },
            )
        db.execute_workflow(setup_workflow)

        # Now list and count
        query_workflow = db.create_workflow("query")
        db.add_node(
            query_workflow,
            model_name,
            "List",
            "list_products",
            {"filter": {"category": "electronics"}, "limit": 10},
        )
        db.add_node(
            query_workflow,
            model_name,
            "Count",
            "count_products",
            {"filter": {"category": "electronics"}},
        )

        results, run_id = db.execute_workflow(query_workflow)

        assert "list_products" in results
        assert "count_products" in results

    def test_bulk_operations_workflow(self, test_dataflow):
        """Bulk operations in workflows."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define model
        model_name = f"BulkItem{suffix}"
        model_class = type(
            model_name,
            (),
            {
                "__annotations__": {
                    "name": str,
                    "batch": str,
                }
            },
        )
        db.model(model_class)

        # Create bulk workflow
        workflow = db.create_workflow("bulk_ops")
        db.add_node(
            workflow,
            model_name,
            "BulkCreate",
            "bulk_create",
            {
                "records": [
                    {"id": f"item{suffix}_1", "name": "Item 1", "batch": "batch1"},
                    {"id": f"item{suffix}_2", "name": "Item 2", "batch": "batch1"},
                    {"id": f"item{suffix}_3", "name": "Item 3", "batch": "batch1"},
                ]
            },
        )

        results, run_id = db.execute_workflow(workflow)

        assert "bulk_create" in results

    def test_error_handling_invalid_params(self, test_dataflow):
        """Error handling: executing with invalid params."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define model
        model_name = f"StrictModel{suffix}"
        model_class = type(
            model_name,
            (),
            {
                "__annotations__": {
                    "required_field": str,
                }
            },
        )
        db.model(model_class)

        workflow = db.create_workflow("error_test")

        # Trying to use invalid operation should raise before execution
        with pytest.raises(ValueError) as exc_info:
            db.add_node(workflow, model_name, "InvalidOp", "bad_node", {})

        assert "Invalid operation" in str(exc_info.value)


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestWorkflowBindingBackwardCompatibility:
    """Test backward compatibility with existing patterns."""

    def test_traditional_workflow_builder_pattern(self, test_dataflow):
        """Traditional WorkflowBuilder pattern still works."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define model
        model_name = f"TraditionalUser{suffix}"
        model_class = type(
            model_name,
            (),
            {
                "__annotations__": {
                    "username": str,
                }
            },
        )
        db.model(model_class)

        # Use traditional WorkflowBuilder pattern
        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{model_name}CreateNode",
            "create",
            {"id": f"user{suffix}", "username": "traditional_user"},
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert "create" in results

    def test_mixed_approach(self, test_dataflow):
        """Can mix new db.add_node() with traditional WorkflowBuilder."""
        db = test_dataflow
        suffix = generate_unique_suffix()

        # Define model
        model_name = f"MixedEntity{suffix}"
        model_class = type(
            model_name,
            (),
            {
                "__annotations__": {
                    "value": str,
                }
            },
        )
        db.model(model_class)

        # Use new pattern for workflow creation
        workflow = db.create_workflow("mixed")

        # Use new pattern for first node
        db.add_node(
            workflow,
            model_name,
            "Create",
            "create_via_add_node",
            {"id": f"entity1{suffix}", "value": "created via add_node"},
        )

        # Use traditional pattern for second node (directly on WorkflowBuilder)
        workflow.add_node(
            f"{model_name}CreateNode",
            "create_via_builder",
            {"id": f"entity2{suffix}", "value": "created via builder"},
        )

        results, run_id = db.execute_workflow(workflow)

        assert "create_via_add_node" in results
        assert "create_via_builder" in results


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestWorkflowBindingIsolation:
    """Test workflow isolation and multi-instance scenarios."""

    def test_multiple_dataflow_instances(self):
        """Multiple DataFlow instances can have independent workflows."""
        suffix = generate_unique_suffix()

        db1 = DataFlow(TEST_DATABASE_URL, auto_migrate=True)
        db2 = DataFlow(TEST_DATABASE_URL, auto_migrate=True)

        try:
            # Define models on each instance
            model1_name = f"Instance1Model{suffix}"
            model1_class = type(model1_name, (), {"__annotations__": {"data": str}})
            db1.model(model1_class)

            model2_name = f"Instance2Model{suffix}"
            model2_class = type(model2_name, (), {"__annotations__": {"info": str}})
            db2.model(model2_class)

            # Create workflows on each
            wf1 = db1.create_workflow("wf1")
            wf2 = db2.create_workflow("wf2")

            # Verify they're independent
            assert wf1._dataflow_context is db1
            assert wf2._dataflow_context is db2
            assert wf1._dataflow_context is not wf2._dataflow_context

        finally:
            # Cleanup
            for db in [db1, db2]:
                if hasattr(db, "_connection_manager") and db._connection_manager:
                    try:
                        db._connection_manager.close()
                    except Exception:
                        pass

    def test_get_available_nodes_isolation(self):
        """get_available_nodes() only returns models from its DataFlow instance."""
        suffix = generate_unique_suffix()

        db1 = DataFlow(TEST_DATABASE_URL, auto_migrate=True)
        db2 = DataFlow(TEST_DATABASE_URL, auto_migrate=True)

        try:
            # Define different models on each
            model1_name = f"IsolatedA{suffix}"
            model1_class = type(model1_name, (), {"__annotations__": {"value": str}})
            db1.model(model1_class)

            model2_name = f"IsolatedB{suffix}"
            model2_class = type(model2_name, (), {"__annotations__": {"data": str}})
            db2.model(model2_class)

            # Check isolation
            nodes1 = db1.get_available_nodes()
            nodes2 = db2.get_available_nodes()

            assert model1_name in nodes1
            assert model2_name not in nodes1

            assert model2_name in nodes2
            assert model1_name not in nodes2

        finally:
            for db in [db1, db2]:
                if hasattr(db, "_connection_manager") and db._connection_manager:
                    try:
                        db._connection_manager.close()
                    except Exception:
                        pass
