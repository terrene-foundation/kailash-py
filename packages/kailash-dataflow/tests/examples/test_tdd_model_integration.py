"""
Example tests demonstrating @db.model integration with TDD infrastructure.

This module shows how DataFlow's auto-generated nodes work seamlessly with
the TDD testing infrastructure, providing fast, isolated tests with shared
database connections and transaction rollback.

Key Features Demonstrated:
- @db.model decorator generating TDD-aware nodes
- All 11 node types working with TDD transaction isolation
- Shared test connections with <100ms performance
- Automatic test cleanup through savepoints
"""

import asyncio
import os
from datetime import datetime
from typing import Optional

import pytest

# Set TDD mode for this test
os.environ["DATAFLOW_TDD_MODE"] = "true"

from dataflow import DataFlow
from dataflow.testing.tdd_support import (
    setup_tdd_infrastructure,
    tdd_test_context,
    teardown_tdd_infrastructure,
)

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestTDDModelIntegration:
    """Test @db.model integration with TDD infrastructure."""

    @pytest.fixture(scope="class", autouse=True)
    async def setup_tdd(self):
        """Setup TDD infrastructure for the test class."""
        await setup_tdd_infrastructure()
        yield
        await teardown_tdd_infrastructure()

    @pytest.mark.asyncio
    async def test_model_registration_with_tdd_context(self):
        """Test that @db.model decorator works with TDD test context."""
        async with tdd_test_context(test_id="model_registration") as ctx:
            # Create DataFlow instance with TDD context
            db = DataFlow(
                tdd_mode=True,
                test_context=ctx,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            # Register a model using the decorator
            @db.model
            class User:
                name: str
                email: str
                active: bool = True

            # Verify model was registered
            assert "User" in db._models
            assert "UserCreateNode" in db._nodes
            assert "UserReadNode" in db._nodes
            assert "UserUpdateNode" in db._nodes
            assert "UserDeleteNode" in db._nodes
            assert "UserListNode" in db._nodes

            # Verify TDD context was propagated to nodes
            create_node_class = db._nodes["UserCreateNode"]
            test_node = create_node_class()
            assert hasattr(test_node, "_tdd_mode")
            assert test_node._tdd_mode
            assert hasattr(test_node, "_test_context")
            assert test_node._test_context == ctx

    @pytest.mark.asyncio
    async def test_crud_nodes_with_tdd_isolation(self):
        """Test all CRUD nodes work with TDD transaction isolation."""
        async with tdd_test_context(test_id="crud_operations") as ctx:
            db = DataFlow(
                tdd_mode=True,
                test_context=ctx,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            @db.model
            class Product:
                name: str
                price: float
                in_stock: bool = True

            workflow = WorkflowBuilder()
            runtime = LocalRuntime()

            # Test CREATE node
            workflow.add_node(
                "ProductCreateNode",
                "create_product",
                {"name": "Test Product", "price": 99.99, "in_stock": True},
            )

            # Test READ node
            workflow.add_node("ProductReadNode", "read_product", {"id": 1})

            # Test UPDATE node
            workflow.add_node(
                "ProductUpdateNode", "update_product", {"id": 1, "price": 89.99}
            )

            # Test DELETE node
            workflow.add_node("ProductDeleteNode", "delete_product", {"id": 1})

            # Connect nodes
            workflow.add_connection("create_product", "id", "read_product", "id")
            workflow.add_connection("create_product", "id", "update_product", "id")
            workflow.add_connection("create_product", "id", "delete_product", "id")

            # Execute workflow - should use shared TDD connection
            start_time = datetime.now()
            results, run_id = runtime.execute(workflow.build())
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            # Verify performance goal: <100ms
            assert (
                execution_time < 100
            ), f"Execution took {execution_time}ms, should be <100ms"

            # Verify results
            assert results["create_product"]["name"] == "Test Product"
            assert results["read_product"]["found"]
            assert results["update_product"]["updated"]
            assert results["delete_product"]["deleted"]

    @pytest.mark.asyncio
    async def test_list_node_with_tdd_isolation(self):
        """Test LIST node works with TDD transaction isolation."""
        async with tdd_test_context(test_id="list_operations") as ctx:
            db = DataFlow(
                tdd_mode=True,
                test_context=ctx,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            @db.model
            class Customer:
                name: str
                email: str
                status: str = "active"

            workflow = WorkflowBuilder()
            runtime = LocalRuntime()

            # Test LIST node with filters
            workflow.add_node(
                "CustomerListNode",
                "list_customers",
                {
                    "filter": {"status": "active"},
                    "limit": 10,
                    "order_by": [{"name": 1}],
                },
            )

            start_time = datetime.now()
            results, run_id = runtime.execute(workflow.build())
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            # Verify performance goal: <100ms
            assert (
                execution_time < 100
            ), f"List execution took {execution_time}ms, should be <100ms"

            # Verify results structure
            assert "records" in results["list_customers"]
            assert "count" in results["list_customers"]
            assert "limit" in results["list_customers"]

    @pytest.mark.asyncio
    async def test_bulk_nodes_with_tdd_isolation(self):
        """Test all bulk operation nodes work with TDD transaction isolation."""
        async with tdd_test_context(test_id="bulk_operations") as ctx:
            db = DataFlow(
                tdd_mode=True,
                test_context=ctx,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            @db.model
            class Order:
                customer_id: int
                total: float
                status: str = "pending"

            workflow = WorkflowBuilder()
            runtime = LocalRuntime()

            # Test BULK CREATE node
            workflow.add_node(
                "OrderBulkCreateNode",
                "bulk_create_orders",
                {
                    "data": [
                        {"customer_id": 1, "total": 100.0, "status": "pending"},
                        {"customer_id": 2, "total": 200.0, "status": "pending"},
                        {"customer_id": 3, "total": 150.0, "status": "processing"},
                    ],
                    "batch_size": 1000,
                },
            )

            # Test BULK UPDATE node
            workflow.add_node(
                "OrderBulkUpdateNode",
                "bulk_update_orders",
                {
                    "filter": {"status": "pending"},
                    "update": {"status": "processing"},
                    "batch_size": 1000,
                },
            )

            # Test BULK DELETE node
            workflow.add_node(
                "OrderBulkDeleteNode",
                "bulk_delete_orders",
                {"filter": {"status": "cancelled"}, "batch_size": 1000},
            )

            # Test BULK UPSERT node
            workflow.add_node(
                "OrderBulkUpsertNode",
                "bulk_upsert_orders",
                {
                    "data": [{"customer_id": 4, "total": 300.0, "status": "confirmed"}],
                    "conflict_resolution": "upsert",
                    "batch_size": 1000,
                },
            )

            start_time = datetime.now()
            results, run_id = runtime.execute(workflow.build())
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            # Verify performance goal: <100ms for bulk operations
            assert (
                execution_time < 100
            ), f"Bulk execution took {execution_time}ms, should be <100ms"

            # Verify results
            assert results["bulk_create_orders"]["success"]
            assert results["bulk_create_orders"]["processed"] >= 0
            assert results["bulk_update_orders"]["success"]
            assert results["bulk_delete_orders"]["success"]
            assert results["bulk_upsert_orders"]["success"]

    @pytest.mark.asyncio
    async def test_transaction_isolation_between_tests(self):
        """Test that changes in one test don't affect another test."""
        # First test - create data
        async with tdd_test_context(test_id="isolation_test_1") as ctx1:
            db1 = DataFlow(
                tdd_mode=True,
                test_context=ctx1,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            @db1.model
            class IsolationTest:
                name: str
                value: int

            workflow1 = WorkflowBuilder()
            workflow1.add_node(
                "IsolationTestCreateNode",
                "create_test_data",
                {"name": "test_data_1", "value": 100},
            )

            runtime = LocalRuntime()
            results1, _ = runtime.execute(workflow1.build())

            # Data should be created in first test
            assert results1["create_test_data"]["name"] == "test_data_1"

        # Second test - should not see data from first test due to rollback
        async with tdd_test_context(test_id="isolation_test_2") as ctx2:
            db2 = DataFlow(
                tdd_mode=True,
                test_context=ctx2,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            @db2.model
            class IsolationTest:
                name: str
                value: int

            workflow2 = WorkflowBuilder()
            workflow2.add_node(
                "IsolationTestListNode",
                "list_test_data",
                {"filter": {"name": "test_data_1"}, "limit": 10},
            )

            results2, _ = runtime.execute(workflow2.build())

            # Should not find data from previous test (transaction was rolled back)
            assert results2["list_test_data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_workflow_context_integration(self):
        """Test that nodes detect and use TDD context from workflow execution."""
        async with tdd_test_context(test_id="workflow_context") as ctx:
            db = DataFlow(
                tdd_mode=True,
                test_context=ctx,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            @db.model
            class WorkflowTest:
                name: str
                category: str
                priority: int = 1

            workflow = WorkflowBuilder()
            runtime = LocalRuntime()

            # Create multiple connected operations
            workflow.add_node(
                "WorkflowTestCreateNode",
                "create_item",
                {"name": "Workflow Item", "category": "test", "priority": 5},
            )

            workflow.add_node("WorkflowTestReadNode", "read_item", {})

            workflow.add_node(
                "WorkflowTestUpdateNode",
                "update_item",
                {"category": "updated", "priority": 10},
            )

            workflow.add_node(
                "WorkflowTestListNode",
                "list_items",
                {"filter": {"category": "updated"}, "limit": 5},
            )

            # Connect the workflow
            workflow.add_connection("create_item", "id", "read_item", "id")
            workflow.add_connection("create_item", "id", "update_item", "id")

            start_time = datetime.now()
            results, run_id = runtime.execute(workflow.build())
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            # Verify performance and correctness
            assert (
                execution_time < 100
            ), f"Workflow execution took {execution_time}ms, should be <100ms"
            assert results["create_item"]["name"] == "Workflow Item"
            assert results["read_item"]["found"]
            assert results["update_item"]["updated"]
            assert results["list_items"]["count"] >= 0

    @pytest.mark.asyncio
    async def test_connection_inheritance_performance(self):
        """Test that generated nodes inherit shared test connection for performance."""
        async with tdd_test_context(test_id="connection_performance") as ctx:
            db = DataFlow(
                tdd_mode=True,
                test_context=ctx,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            @db.model
            class PerformanceTest:
                name: str
                timestamp: Optional[str] = None

            workflow = WorkflowBuilder()
            runtime = LocalRuntime()

            # Execute multiple sequential operations
            operations = []
            for i in range(10):  # 10 operations to test connection reuse
                create_id = f"create_{i}"
                read_id = f"read_{i}"

                workflow.add_node(
                    "PerformanceTestCreateNode",
                    create_id,
                    {"name": f"Test Item {i}", "timestamp": datetime.now().isoformat()},
                )

                workflow.add_node("PerformanceTestReadNode", read_id, {})

                workflow.add_connection(create_id, "id", read_id, "id")
                operations.extend([create_id, read_id])

            start_time = datetime.now()
            results, run_id = runtime.execute(workflow.build())
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            # With connection reuse, 20 operations should still be <100ms
            assert (
                execution_time < 100
            ), f"20 operations took {execution_time}ms, should be <100ms with connection reuse"

            # Verify all operations completed successfully
            for op_id in operations:
                assert op_id in results
                if op_id.startswith("create_"):
                    assert "name" in results[op_id]
                elif op_id.startswith("read_"):
                    assert results[op_id]["found"]


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
