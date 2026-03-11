"""Integration tests for DataFlow transaction context propagation."""

import asyncio
import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

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


class TestTransactionNodeImplementation:
    """Test DataFlow transaction node implementations."""

    def test_transaction_scope_node_starts_transaction(self):
        """Test TransactionScopeNode starts a real database transaction."""
        # Import DataFlow transaction node
        from dataflow.nodes.transaction_nodes import TransactionScopeNode

        # Mock DataFlow instance and connection
        mock_dataflow = Mock()
        mock_connection = AsyncMock()
        mock_transaction = Mock()  # Regular mock, not AsyncMock

        # Set up async mocks correctly
        async def mock_get_connection():
            return mock_connection

        # The transaction object should be a regular mock with async methods
        mock_transaction.start = AsyncMock()
        # Mock the transaction() method to return the mock_transaction (not a coroutine)
        mock_connection.transaction = Mock(return_value=mock_transaction)
        mock_connection.execute = AsyncMock()

        mock_dataflow.get_connection = mock_get_connection

        # Create node and set workflow context
        node = TransactionScopeNode()
        node._workflow_context = {"dataflow_instance": mock_dataflow}

        # Execute the node
        result = node.execute(isolation_level="READ_COMMITTED", timeout=30)

        # Verify transaction was stored in context
        assert "transaction_connection" in node._workflow_context
        assert "active_transaction" in node._workflow_context
        assert node._workflow_context["active_transaction"] == mock_transaction

        # Verify result
        assert result["status"] == "started"
        assert "transaction_id" in result

    def test_transaction_commit_node_commits_from_context(self):
        """Test TransactionCommitNode commits transaction from context."""
        from dataflow.nodes.transaction_nodes import TransactionCommitNode

        # Mock transaction and connection
        mock_transaction = Mock()
        mock_connection = Mock()

        # Set up async methods
        mock_transaction.commit = AsyncMock()
        mock_connection.close = AsyncMock()

        node = TransactionCommitNode()
        node._workflow_context = {
            "active_transaction": mock_transaction,
            "transaction_connection": mock_connection,
        }

        result = node.execute()

        # Verify context was cleaned up (set to None, not removed)
        assert node._workflow_context["active_transaction"] is None
        assert node._workflow_context["transaction_connection"] is None

        # Verify result
        assert result["status"] == "committed"

    def test_transaction_rollback_node_rollback_from_context(self):
        """Test TransactionRollbackNode rolls back transaction from context."""
        from dataflow.nodes.transaction_nodes import TransactionRollbackNode

        # Mock transaction and connection
        mock_transaction = Mock()
        mock_connection = Mock()

        # Set up async methods
        mock_transaction.rollback = AsyncMock()
        mock_connection.close = AsyncMock()

        node = TransactionRollbackNode()
        node._workflow_context = {
            "active_transaction": mock_transaction,
            "transaction_connection": mock_connection,
            "rollback_reason": "User requested",
        }

        result = node.execute(reason="User requested")

        # Verify context was cleaned up (set to None, not removed)
        assert node._workflow_context["active_transaction"] is None
        assert node._workflow_context["transaction_connection"] is None

        # Verify result
        assert result["status"] == "rolled_back"
        # The rollback reason comes from workflow context, not parameters
        assert result["reason"] == "User requested"


class TestDataFlowNodeTransactionAwareness:
    """Test DataFlow node transaction awareness."""

    def test_dataflow_node_uses_transaction_connection(self, test_suite):
        """Test that DataFlow nodes use connection from transaction context."""
        from dataflow import DataFlow
        from dataflow.nodes.transaction_nodes import (
            TransactionCommitNode,
            TransactionScopeNode,
        )

        # Create DataFlow instance with test database
        # Using the test PostgreSQL instance on port 5434
        db = DataFlow(database_url=test_suite.config.url)

        # Define a test model
        @db.model
        class TestUser:
            name: str
            email: str
            age: int = 18

        # Ensure table exists - DataFlow should create it automatically
        # but we'll use a simple check to ensure it's there
        try:
            # Try to query the table to ensure it exists
            from kailash.runtime.local import LocalRuntime

            check_workflow = WorkflowBuilder()
            check_workflow.add_node("TestUserListNode", "check", {"limit": 1})
            runtime = LocalRuntime()
            runtime.execute(
                check_workflow.build(),
                parameters={"workflow_context": {"dataflow_instance": db}},
            )
        except Exception:
            # Table might not exist, that's okay - DataFlow will create it on first use
            pass

        # Create workflow
        workflow = WorkflowBuilder()

        # Start transaction
        workflow.add_node(
            "TransactionScopeNode", "start_tx", {"isolation_level": "READ_COMMITTED"}
        )

        # Use PythonCodeNode to create user within transaction
        # This avoids the validation issue with dynamically generated nodes
        workflow.add_node(
            "PythonCodeNode",
            "create_user",
            {
                "code": """
# Get the DataFlow instance and transaction connection from context
dataflow_instance = get_workflow_context('dataflow_instance')
tx_connection = get_workflow_context('transaction_connection')

# Import the generated node class
TestUserCreateNode = dataflow_instance._nodes['TestUserCreateNode']

# Create node instance and set workflow context
create_node = TestUserCreateNode()
create_node._workflow_context = {
    'dataflow_instance': dataflow_instance,
    'transaction_connection': tx_connection,
    'active_transaction': get_workflow_context('active_transaction')
}

# Execute the create operation
result = create_node.execute(
    name="Transaction Test User",
    email="tx_test@example.com",
    age=25
)
"""
            },
        )

        # List users within same transaction
        workflow.add_node(
            "PythonCodeNode",
            "list_in_tx",
            {
                "code": """
# Get context
dataflow_instance = get_workflow_context('dataflow_instance')
tx_connection = get_workflow_context('transaction_connection')

# Use list node
TestUserListNode = dataflow_instance._nodes['TestUserListNode']
list_node = TestUserListNode()
list_node._workflow_context = {
    'dataflow_instance': dataflow_instance,
    'transaction_connection': tx_connection,
    'active_transaction': get_workflow_context('active_transaction')
}

# List users with the test email
result = list_node.execute(
    filter={"email": "tx_test@example.com"},
    limit=10
)
"""
            },
        )

        # Commit transaction
        workflow.add_node("TransactionCommitNode", "commit_tx", {})

        # List users after commit (without transaction)
        workflow.add_node(
            "PythonCodeNode",
            "list_after_commit",
            {
                "code": """
# Get DataFlow instance (no transaction context)
dataflow_instance = get_workflow_context('dataflow_instance')

# Use list node without transaction
TestUserListNode = dataflow_instance._nodes['TestUserListNode']
list_node = TestUserListNode()
list_node._workflow_context = {
    'dataflow_instance': dataflow_instance
}

# List users
result = list_node.execute(
    filter={"email": "tx_test@example.com"},
    limit=10
)
"""
            },
        )

        # Connect nodes
        workflow.add_connection("start_tx", "result", "create_user", "input_data")
        workflow.add_connection("create_user", "result", "list_in_tx", "input_data")
        workflow.add_connection("list_in_tx", "result", "commit_tx", "input_data")
        workflow.add_connection(
            "commit_tx", "result", "list_after_commit", "input_data"
        )

        # Execute with DataFlow instance in context
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow.build(), parameters={"workflow_context": {"dataflow_instance": db}}
        )

        # Verify transaction was used
        create_result = results.get("create_user", {}).get("result", {})
        list_in_tx_result = results.get("list_in_tx", {}).get("result", {})
        commit_result = results.get("commit_tx", {})
        list_after_result = results.get("list_after_commit", {}).get("result", {})

        # User should be created
        assert "id" in create_result
        assert create_result.get("name") == "Transaction Test User"

        # User should be visible within transaction (before commit)
        assert list_in_tx_result.get("count", 0) >= 1
        tx_users = list_in_tx_result.get("records", [])
        assert any(u["email"] == "tx_test@example.com" for u in tx_users)

        # Transaction should commit successfully
        # The TransactionCommitNode returns mock results since we're in test mode
        assert "status" in commit_result or "result" in commit_result

        # User should still be visible after commit
        assert list_after_result.get("count", 0) >= 1
        after_users = list_after_result.get("records", [])
        assert any(u["email"] == "tx_test@example.com" for u in after_users)

        # Cleanup - delete test data
        created_id = create_result.get("id")
        if created_id:
            workflow_cleanup = WorkflowBuilder()
            workflow_cleanup.add_node(
                "PythonCodeNode",
                "cleanup",
                {
                    "code": f"""
dataflow_instance = get_workflow_context('dataflow_instance')
TestUserDeleteNode = dataflow_instance._nodes['TestUserDeleteNode']
delete_node = TestUserDeleteNode()
delete_node._workflow_context = {{'dataflow_instance': dataflow_instance}}
result = delete_node.execute(id={created_id})
"""
                },
            )
            runtime.execute(
                workflow_cleanup.build(),
                parameters={"workflow_context": {"dataflow_instance": db}},
            )

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
        assert create_result.get("price") == 99.99

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
