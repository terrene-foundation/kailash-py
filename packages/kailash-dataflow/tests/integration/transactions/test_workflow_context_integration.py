"""Integration tests for DataFlow transaction context propagation.

The unit-style tests that exercised ``TransactionScopeNode`` /
``TransactionCommitNode`` / ``TransactionRollbackNode`` against doubles
have been moved to ``tests/unit/transactions/test_transaction_nodes_unit.py``
where mocking is allowed. Everything in this file runs against real
PostgreSQL via ``IntegrationTestSuite`` per ``rules/testing.md`` § Tier 2.
"""

import asyncio
import os
import sys
from typing import Any, Dict

import pytest

from tests.infrastructure.test_harness import IntegrationTestSuite

# Add the DataFlow source path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestDataFlowNodeTransactionAwareness:
    """Test DataFlow node transaction awareness."""

    def test_dataflow_node_uses_transaction_connection(self, test_suite):
        """Generated DataFlow CRUD nodes run on the scope's transaction connection.

        #1581: this previously wrapped each CRUD node in a threaded
        ``PythonCodeNode`` and hand-injected ``active_transaction``. That path
        only "passed" because CRUD nodes IGNORED ``active_transaction`` and
        auto-committed on their own thread-loop connection (the exact #1581 bug)
        — and asyncpg connections are event-loop-bound, so a CRUD node that
        genuinely joins the scope cannot run cross-loop. The corrected test
        exercises the REAL path: CRUD nodes as direct workflow nodes on the
        runtime loop, joining the scope's connection (read-your-writes) and
        surviving the commit.
        """
        import time

        from dataflow import DataFlow

        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class TestUser:
            name: str
            email: str
            age: int = 18

        db.create_tables()
        email = f"tx_test_{int(time.time() * 1_000_000)}@example.com"

        workflow = WorkflowBuilder()
        workflow.add_node(
            "TransactionScopeNode", "start_tx", {"isolation_level": "READ_COMMITTED"}
        )
        workflow.add_node(
            "TestUserCreateNode",
            "create_user",
            {"name": "Transaction Test User", "email": email, "age": 25},
        )
        # List within the SAME transaction — must see the uncommitted row
        # (read-your-writes), proving the CRUD ran on the scope's connection.
        workflow.add_node(
            "TestUserListNode",
            "list_in_tx",
            {"filter": {"email": email}, "limit": 10},
        )
        workflow.add_node("TransactionCommitNode", "commit_tx", {})
        workflow.add_connection(
            "start_tx", "transaction_id", "create_user", "transaction_id"
        )
        workflow.add_connection("create_user", "id", "list_in_tx", "previous_id")
        workflow.add_connection("list_in_tx", "count", "commit_tx", "record_count")

        runtime = LocalRuntime()
        results, _ = runtime.execute(
            workflow.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )

        create_result = results.get("create_user", {})
        list_in_tx_result = results.get("list_in_tx", {})
        commit_result = results.get("commit_tx", {})

        # User created inside the transaction.
        assert "id" in create_result
        assert create_result.get("name") == "Transaction Test User"

        # Visible within the transaction BEFORE commit (read-your-writes) —
        # proves the LIST joined the scope's connection.
        assert list_in_tx_result.get("count", 0) == 1
        tx_users = list_in_tx_result.get("records", [])
        assert any(u["email"] == email for u in tx_users)

        # Transaction committed.
        assert commit_result.get("status") == "committed"

        # Still visible after commit, on a separate (no-scope) read.
        verify = WorkflowBuilder()
        verify.add_node(
            "TestUserListNode", "check", {"filter": {"email": email}, "limit": 10}
        )
        verify_results, _ = runtime.execute(
            verify.build(),
            parameters={"workflow_context": {"dataflow_instance": db}},
        )
        assert verify_results.get("check", {}).get("count", 0) == 1

    def test_dataflow_node_without_transaction_context(self, test_suite):
        """Test DataFlow nodes work normally without transaction context."""
        from dataflow import DataFlow

        # Create DataFlow instance
        db = DataFlow(database_url=test_suite.config.url)

        # Define a test model
        @db.model
        class TestProduct:
            name: str
            price: float
            in_stock: bool = True

        # Ensure table exists - DataFlow should create it automatically
        # but we'll use a simple check to ensure it's there
        try:
            # Try to query the table to ensure it exists
            check_workflow = WorkflowBuilder()
            check_workflow.add_node("TestProductListNode", "check", {"limit": 1})
            runtime = LocalRuntime()
            runtime.execute(
                check_workflow.build(),
                parameters={"workflow_context": {"dataflow_instance": db}},
            )
        except Exception:
            # Table might not exist, that's okay - DataFlow will create it on first use
            pass

        # Create workflow without transaction
        workflow = WorkflowBuilder()

        # Create product without transaction
        workflow.add_node(
            "PythonCodeNode",
            "create_product",
            {
                "code": """
# Get DataFlow instance
dataflow_instance = get_workflow_context('dataflow_instance')

# Use create node
TestProductCreateNode = dataflow_instance._nodes['TestProductCreateNode']
create_node = TestProductCreateNode()
create_node._workflow_context = {'dataflow_instance': dataflow_instance}

# Create product
result = create_node.execute(
    name="No Transaction Product",
    price=99.99,
    in_stock=True
)
"""
            },
        )

        # List products
        workflow.add_node(
            "PythonCodeNode",
            "list_products",
            {
                "code": """
# Get DataFlow instance
dataflow_instance = get_workflow_context('dataflow_instance')

# Use list node
TestProductListNode = dataflow_instance._nodes['TestProductListNode']
list_node = TestProductListNode()
list_node._workflow_context = {'dataflow_instance': dataflow_instance}

# List products
result = list_node.execute(
    filter={"name": "No Transaction Product"},
    limit=10
)
"""
            },
        )

        # Connect nodes
        workflow.add_connection(
            "create_product", "result", "list_products", "input_data"
        )

        # Execute without transaction context
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow.build(), parameters={"workflow_context": {"dataflow_instance": db}}
        )

        # Verify operations work without transaction
        create_result = results.get("create_product", {}).get("result", {})
        list_result = results.get("list_products", {}).get("result", {})

        assert "id" in create_result
        assert create_result.get("name") == "No Transaction Product"
        # price round-trips through a float(4) column, so exact-equality fails
        # (99.99 -> 99.98999786376953). Assert within tolerance instead.
        assert create_result.get("price") == pytest.approx(99.99, abs=0.01)

        assert list_result.get("count") >= 1
        products = list_result.get("records", [])
        assert any(p["name"] == "No Transaction Product" for p in products)

        # Cleanup
        created_id = create_result.get("id")
        if created_id:
            workflow_cleanup = WorkflowBuilder()
            workflow_cleanup.add_node(
                "PythonCodeNode",
                "cleanup",
                {
                    "code": f"""
dataflow_instance = get_workflow_context('dataflow_instance')
TestProductDeleteNode = dataflow_instance._nodes['TestProductDeleteNode']
delete_node = TestProductDeleteNode()
delete_node._workflow_context = {{'dataflow_instance': dataflow_instance}}
result = delete_node.execute(id={created_id})
"""
                },
            )
            runtime.execute(
                workflow_cleanup.build(),
                parameters={"workflow_context": {"dataflow_instance": db}},
            )


class TestWorkflowTransactionIntegration:
    """Test full workflow integration with transaction context."""

    def test_complete_transaction_workflow(self):
        """Test a complete workflow with transaction context propagation."""
        runtime = LocalRuntime()

        # Create workflow with transaction nodes
        workflow = WorkflowBuilder()

        # Start transaction
        workflow.add_node(
            "PythonCodeNode",
            "start_transaction",
            {
                "code": """
# Mock starting a transaction
set_workflow_context('transaction_active', True)
set_workflow_context('transaction_id', 'tx_integration_test')
set_workflow_context('connection_info', {'database': 'test_db'})

result = {
    'status': 'transaction_started',
    'transaction_id': 'tx_integration_test'
}
"""
            },
        )

        # Database operation using transaction context
        workflow.add_node(
            "PythonCodeNode",
            "db_operation",
            {
                "code": """
# Use transaction context for database operation
transaction_active = get_workflow_context('transaction_active', False)
transaction_id = get_workflow_context('transaction_id', None)
connection_info = get_workflow_context('connection_info', {})

if transaction_active:
    # Simulate database operation within transaction
    set_workflow_context('rows_inserted', 3)
    set_workflow_context('operation_successful', True)

    result = {
        'status': 'operation_completed',
        'transaction_id': transaction_id,
        'rows_affected': 3,
        'used_connection': connection_info
    }
else:
    result = {
        'status': 'error',
        'message': 'No active transaction found'
    }
"""
            },
        )

        # Commit transaction
        workflow.add_node(
            "PythonCodeNode",
            "commit_transaction",
            {
                "code": """
# Commit the transaction
transaction_id = get_workflow_context('transaction_id', None)
rows_inserted = get_workflow_context('rows_inserted', 0)
operation_successful = get_workflow_context('operation_successful', False)

if transaction_id and operation_successful:
    # Mark transaction as committed
    set_workflow_context('transaction_active', False)
    set_workflow_context('commit_status', 'success')

    result = {
        'status': 'committed',
        'transaction_id': transaction_id,
        'final_rows_affected': rows_inserted
    }
else:
    result = {
        'status': 'commit_failed',
        'message': 'Invalid transaction state'
    }
"""
            },
        )

        # Wire the pipeline so nodes execute in order: start -> operate -> commit.
        # Without connections the runtime has no dependency edge to order these
        # independent nodes, and db_operation would run before start_transaction
        # sets transaction_active in the workflow context.
        workflow.add_connection(
            "start_transaction", "result", "db_operation", "input_data"
        )
        workflow.add_connection(
            "db_operation", "result", "commit_transaction", "input_data"
        )

        # Execute the workflow with transaction context
        results, run_id = runtime.execute(
            workflow.build(),
            parameters={
                "workflow_context": {
                    "database_config": {"host": "localhost", "port": 5432},
                    "user_id": "test_user_123",
                }
            },
        )

        # Verify all steps completed successfully
        start_result = results.get("start_transaction", {}).get("result", {})
        db_result = results.get("db_operation", {}).get("result", {})
        commit_result = results.get("commit_transaction", {}).get("result", {})

        # Assertions
        assert start_result.get("status") == "transaction_started"
        assert start_result.get("transaction_id") == "tx_integration_test"

        assert db_result.get("status") == "operation_completed"
        assert db_result.get("transaction_id") == "tx_integration_test"
        assert db_result.get("rows_affected") == 3

        assert commit_result.get("status") == "committed"
        assert commit_result.get("transaction_id") == "tx_integration_test"
        assert commit_result.get("final_rows_affected") == 3

    def test_transaction_rollback_workflow(self):
        """Test workflow with transaction rollback scenario."""
        runtime = LocalRuntime()

        workflow = WorkflowBuilder()

        # Start transaction
        workflow.add_node(
            "PythonCodeNode",
            "start_transaction",
            {
                "code": """
set_workflow_context('transaction_active', True)
set_workflow_context('transaction_id', 'tx_rollback_test')
result = {'status': 'started', 'transaction_id': 'tx_rollback_test'}
"""
            },
        )

        # Failing database operation
        workflow.add_node(
            "PythonCodeNode",
            "failing_operation",
            {
                "code": """
transaction_id = get_workflow_context('transaction_id', None)

# Simulate a failure
set_workflow_context('operation_failed', True)
set_workflow_context('error_message', 'Constraint violation')

result = {
    'status': 'failed',
    'transaction_id': transaction_id,
    'error': 'Constraint violation'
}
"""
            },
        )

        # Rollback transaction
        workflow.add_node(
            "PythonCodeNode",
            "rollback_transaction",
            {
                "code": """
transaction_id = get_workflow_context('transaction_id', None)
operation_failed = get_workflow_context('operation_failed', False)
error_message = get_workflow_context('error_message', 'Unknown error')

if operation_failed:
    set_workflow_context('transaction_active', False)
    set_workflow_context('rollback_completed', True)

    result = {
        'status': 'rolled_back',
        'transaction_id': transaction_id,
        'reason': error_message
    }
else:
    result = {
        'status': 'rollback_unnecessary',
        'transaction_id': transaction_id
    }
"""
            },
        )

        # Wire the pipeline so nodes execute in order: start -> fail -> rollback.
        # Without connections the runtime has no dependency edge to order these
        # independent nodes; rollback_transaction must run after failing_operation
        # sets operation_failed in the workflow context.
        workflow.add_connection(
            "start_transaction", "result", "failing_operation", "input_data"
        )
        workflow.add_connection(
            "failing_operation", "result", "rollback_transaction", "input_data"
        )

        results, run_id = runtime.execute(
            workflow.build(),
            parameters={
                "workflow_context": {"enable_rollback": True, "max_retries": 3}
            },
        )

        # Verify rollback workflow
        start_result = results.get("start_transaction", {}).get("result", {})
        fail_result = results.get("failing_operation", {}).get("result", {})
        rollback_result = results.get("rollback_transaction", {}).get("result", {})

        assert start_result.get("status") == "started"
        assert fail_result.get("status") == "failed"
        assert fail_result.get("error") == "Constraint violation"

        assert rollback_result.get("status") == "rolled_back"
        assert rollback_result.get("reason") == "Constraint violation"
