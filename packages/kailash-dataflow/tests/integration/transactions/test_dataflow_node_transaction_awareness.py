"""Integration tests for DataFlow node transaction awareness with real database."""

import asyncio
import os
from typing import Any, Dict

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestDataFlowNodeRealTransactionAwareness:
    """Test DataFlow node transaction awareness with real database."""

    def test_dataflow_create_and_read_in_transaction(self, test_suite):
        """Test that DataFlow nodes share transaction connection."""
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

        from dataflow import DataFlow
        from dataflow.nodes.transaction_nodes import (
            TransactionCommitNode,
            TransactionScopeNode,
        )

        # Create DataFlow instance with test database
        db = DataFlow(database_url=test_suite.config.url)

        # Define a test model
        @db.model
        class TransactionTestUser:
            name: str
            email: str
            age: int = 25

        # Create tables
        db.create_tables()

        # Create workflow
        workflow = WorkflowBuilder()

        # Start transaction
        workflow.add_node(
            "TransactionScopeNode", "start_tx", {"isolation_level": "READ_COMMITTED"}
        )

        # Create user within transaction
        workflow.add_node(
            "TransactionTestUserCreateNode",
            "create_user",
            {"name": "Alice Transaction", "email": "alice_tx@example.com", "age": 30},
        )

        # Create another user in same transaction
        workflow.add_node(
            "TransactionTestUserCreateNode",
            "create_user2",
            {"name": "Bob Transaction", "email": "bob_tx@example.com", "age": 28},
        )

        # List users to verify both are visible in same transaction
        workflow.add_node(
            "TransactionTestUserListNode",
            "list_users",
            {
                "filter": {
                    "email": {"$in": ["alice_tx@example.com", "bob_tx@example.com"]}
                },
                "limit": 10,
            },
        )

        # Commit transaction
        workflow.add_node("TransactionCommitNode", "commit_tx", {})

        # Connect nodes - only connect for flow control, not data passing
        workflow.add_connection(
            "start_tx", "transaction_id", "create_user", "transaction_id"
        )
        workflow.add_connection("create_user", "id", "create_user2", "previous_id")
        workflow.add_connection("create_user2", "id", "list_users", "previous_id")
        workflow.add_connection("list_users", "count", "commit_tx", "record_count")

        # Execute with DataFlow instance in context
        runtime = LocalRuntime()
        runtime_params = {"dataflow_instance": db}
        results, run_id = runtime.execute(workflow.build(), runtime_params)

        # Verify all operations succeeded
        tx_result = results.get("start_tx", {}).get("result", {})
        user1_result = results.get("create_user", {})
        user2_result = results.get("create_user2", {})
        list_result = results.get("list_users", {})
        commit_result = results.get("commit_tx", {}).get("result", {})

        # Check transaction was started
        assert tx_result.get("status") == "started"
        assert "transaction_id" in tx_result

        # Check both users were created
        assert "id" in user1_result
        assert user1_result.get("name") == "Alice Transaction"
        assert "id" in user2_result
        assert user2_result.get("name") == "Bob Transaction"

        # Check list found both users (they're visible in same transaction)
        assert list_result.get("count") >= 2
        records = list_result.get("records", [])
        emails = [r["email"] for r in records]
        assert "alice_tx@example.com" in emails
        assert "bob_tx@example.com" in emails

        # Check transaction was committed
        assert commit_result.get("status") == "committed"

        # Cleanup - delete test data
        cleanup_workflow = WorkflowBuilder()
        cleanup_workflow.add_node(
            "TransactionTestUserDeleteNode", "cleanup1", {"id": user1_result["id"]}
        )
        cleanup_workflow.add_node(
            "TransactionTestUserDeleteNode", "cleanup2", {"id": user2_result["id"]}
        )
        cleanup_workflow.add_connection("cleanup1", "result", "cleanup2", "input_data")
        runtime.execute(
            cleanup_workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )

    def test_dataflow_rollback_transaction(self, test_suite):
        """Test that rollback prevents data from being committed."""
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

        from dataflow import DataFlow
        from dataflow.nodes.transaction_nodes import (
            TransactionRollbackNode,
            TransactionScopeNode,
        )

        # Create DataFlow instance
        db = DataFlow(database_url=test_suite.config.url)

        # Define a test model
        @db.model
        class RollbackTestProduct:
            name: str
            price: float
            sku: str

        # Create workflow with rollback
        workflow = WorkflowBuilder()

        # Start transaction
        workflow.add_node(
            "TransactionScopeNode",
            "start_tx",
            {"isolation_level": "READ_COMMITTED", "rollback_on_error": True},
        )

        # Create product within transaction
        workflow.add_node(
            "RollbackTestProductCreateNode",
            "create_product",
            {
                "name": "Rollback Test Product",
                "price": 199.99,
                "sku": "ROLLBACK-TEST-001",
            },
        )

        # Simulate an error condition that triggers rollback
        workflow.add_node(
            "PythonCodeNode",
            "trigger_error",
            {
                "code": """
# Simulate error condition
set_workflow_context('error_occurred', True)
set_workflow_context('rollback_reason', 'Simulated validation error')
result = {'status': 'error', 'message': 'Validation failed'}
"""
            },
        )

        # Rollback transaction
        workflow.add_node(
            "TransactionRollbackNode",
            "rollback_tx",
            {"reason": "Validation error in workflow"},
        )

        # Connect nodes
        workflow.add_connection("start_tx", "result", "create_product", "input_data")
        workflow.add_connection(
            "create_product", "result", "trigger_error", "input_data"
        )
        workflow.add_connection("trigger_error", "result", "rollback_tx", "input_data")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow.build(), parameters={"workflow_context": {"dataflow_instance": db}}
        )

        # Verify rollback occurred
        rollback_result = results.get("rollback_tx", {}).get("result", {})
        assert rollback_result.get("status") == "rolled_back"

        # Verify product was NOT persisted by trying to list it
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "RollbackTestProductListNode",
            "check_products",
            {"filter": {"sku": "ROLLBACK-TEST-001"}, "limit": 10},
        )

        verify_results, _ = runtime.execute(
            verify_workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )

        # Product should not exist due to rollback
        list_result = verify_results.get("check_products", {})
        assert list_result.get("count", 0) == 0
        assert len(list_result.get("records", [])) == 0

    def test_dataflow_without_transaction_normal_operation(self, test_suite):
        """Test that DataFlow nodes work normally without transaction context."""
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

        from dataflow import DataFlow

        # Create DataFlow instance
        db = DataFlow(database_url=test_suite.config.url)

        # Define a test model
        @db.model
        class StandardOrder:
            order_number: str
            customer_name: str
            total: float
            status: str = "pending"

        # Create workflow without transaction
        workflow = WorkflowBuilder()

        # Create order without transaction
        workflow.add_node(
            "StandardOrderCreateNode",
            "create_order",
            {
                "order_number": "ORD-2025-001",
                "customer_name": "John Doe",
                "total": 299.99,
                "status": "pending",
            },
        )

        # Update order status
        workflow.add_node(
            "PythonCodeNode",
            "update_order",
            {
                "code": """
# Get order ID from previous step
order_id = parameters.get('order_id')

# Use the update node
from kailash.nodes.base import NodeRegistry
StandardOrderUpdateNode = NodeRegistry.get_node_class('StandardOrderUpdateNode')

update_node = StandardOrderUpdateNode()
# Pass workflow context
update_node._workflow_context = get_workflow_context('_all', {})

# Update the order
result = update_node.execute(id=order_id, status='confirmed')
"""
            },
        )

        # List orders
        workflow.add_node(
            "StandardOrderListNode",
            "list_orders",
            {"filter": {"order_number": "ORD-2025-001"}, "limit": 10},
        )

        # Connect nodes
        workflow.add_connection("create_order", "id", "update_order", "order_id")
        workflow.add_connection("update_order", "result", "list_orders", "input_data")

        # Execute without transaction
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow.build(), parameters={"workflow_context": {"dataflow_instance": db}}
        )

        # Verify operations succeeded without transaction
        create_result = results.get("create_order", {})
        update_result = results.get("update_order", {}).get("result", {})
        list_result = results.get("list_orders", {})

        # Check order was created
        assert "id" in create_result
        assert create_result.get("order_number") == "ORD-2025-001"
        assert create_result.get("status") == "pending"

        # Check order was updated
        assert update_result.get("status") == "confirmed"
        assert update_result.get("updated") is True

        # Check list shows updated order
        assert list_result.get("count") >= 1
        orders = list_result.get("records", [])
        updated_order = next(
            (o for o in orders if o["order_number"] == "ORD-2025-001"), None
        )
        assert updated_order is not None
        assert updated_order["status"] == "confirmed"

        # Cleanup
        cleanup_workflow = WorkflowBuilder()
        cleanup_workflow.add_node(
            "StandardOrderDeleteNode", "cleanup", {"id": create_result["id"]}
        )
        runtime.execute(
            cleanup_workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )
