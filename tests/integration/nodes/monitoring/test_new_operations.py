"""Unit tests for new operations added to monitoring nodes.

This test file covers the infrastructure gaps that were resolved:
1. DeadlockDetectorNode: initialize, acquire_resource, request_resource, release_resource
2. TransactionMetricsNode: complete_transaction, success_rate calculation
3. TransactionMonitorNode: complete_transaction with schema compliance
4. RaceConditionDetectorNode: complete_operation
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from kailash.nodes.monitoring.deadlock_detector import DeadlockDetectorNode
from kailash.nodes.monitoring.race_condition_detector import RaceConditionDetectorNode
from kailash.nodes.monitoring.transaction_metrics import TransactionMetricsNode
from kailash.nodes.monitoring.transaction_monitor import TransactionMonitorNode


class TestNewDeadlockDetectorOperations:
    """Test new operations added to DeadlockDetectorNode."""

    def setup_method(self):
        """Set up test fixtures."""
        self.node = DeadlockDetectorNode()

    def test_initialize_operation(self):
        """Test the new initialize operation."""
        result = self.node.execute(operation="initialize")

        assert result["status"] == "success"
        assert result["monitoring_status"] == "initialized"
        assert "deadlocks_detected" in result
        assert "deadlock_count" in result
        assert "active_locks" in result
        assert "active_waits" in result
        assert "wait_for_graph" in result
        assert "timestamp" in result

    def test_acquire_resource_operation(self):
        """Test the new acquire_resource operation (alias for register_lock)."""
        result = self.node.execute(
            operation="acquire_resource",
            transaction_id="txn_123",
            resource_id="table_users",
            lock_type="exclusive",
        )

        assert result["status"] == "success"
        # acquire_resource is an alias for register_lock, so check register_lock fields
        assert "deadlocks_detected" in result
        assert "active_locks" in result
        assert result["active_locks"] == 1  # Should have registered exactly one lock

    def test_request_resource_operation(self):
        """Test the new request_resource operation."""
        result = self.node.execute(
            operation="request_resource",
            transaction_id="txn_456",
            resource_id="table_orders",
            resource_type="database_table",
            lock_type="SHARED",
        )

        assert result["status"] == "success"
        assert "deadlocks_detected" in result
        assert (
            "active_waits" in result
        )  # Fixed: request_resource returns active_waits, not active_accesses
        assert result["monitoring_status"] == "requested_database_table_shared"

    def test_release_resource_operation(self):
        """Test the new release_resource operation (alias for release_lock)."""
        # First acquire a resource
        self.node.execute(
            operation="acquire_resource",
            transaction_id="txn_789",
            resource_id="table_products",
        )

        # Then release it
        result = self.node.execute(
            operation="release_resource",
            transaction_id="txn_789",
            resource_id="table_products",
        )

        assert result["status"] == "success"


class TestTransactionMetricsNewFeatures:
    """Test new features added to TransactionMetricsNode."""

    def setup_method(self):
        """Set up test fixtures."""
        self.node = TransactionMetricsNode()

    def test_complete_transaction_operation(self):
        """Test the new complete_transaction operation."""
        # Start a transaction first
        self.node.execute(
            operation="start_transaction",
            transaction_id="txn_complete_test",
            name="test_transaction",
        )

        # Complete it
        result = self.node.execute(
            operation="complete_transaction",
            transaction_id="txn_complete_test",
            success=True,
        )

        assert result["status"] == "success"
        assert "success_rate" in result
        assert result["success_rate"] == 1.0  # Should be 1.0 for successful transaction

    def test_success_rate_calculation(self):
        """Test success rate calculation in get_metrics."""
        # Add some successful and failed transactions
        for i in range(3):
            self.node.execute(
                operation="start_transaction",
                transaction_id=f"success_{i}",
                name="success_test",
            )
            self.node.execute(
                operation="end_transaction",
                transaction_id=f"success_{i}",
                status="success",
            )

        for i in range(1):
            self.node.execute(
                operation="start_transaction",
                transaction_id=f"failure_{i}",
                name="failure_test",
            )
            self.node.execute(
                operation="end_transaction",
                transaction_id=f"failure_{i}",
                status="error",
            )

        # Get metrics
        result = self.node.execute(operation="get_metrics")

        assert result["status"] == "success"
        assert "success_rate" in result
        assert result["success_rate"] == 0.75  # 3 success / 4 total = 0.75
        assert "total_transactions" in result
        assert result["total_transactions"] == 4


class TestTransactionMonitorNewFeatures:
    """Test new features added to TransactionMonitorNode."""

    def setup_method(self):
        """Set up test fixtures."""
        self.node = TransactionMonitorNode()

    def test_complete_transaction_operation(self):
        """Test the new complete_transaction operation with schema compliance."""
        result = self.node.execute(
            operation="complete_transaction",
            transaction_id="monitor_test_123",
            success=True,
        )

        assert result["status"] == "success"
        assert result["monitoring_status"] == "transaction_completed"
        assert result["transaction_id"] == "monitor_test_123"
        assert "trace_data" in result
        assert "span_data" in result
        assert "alerts" in result
        assert "metrics" in result
        assert "correlation_id" in result
        assert "timestamp" in result

    def test_complete_transaction_input_schema(self):
        """Test that transaction_id and success parameters are properly accepted."""
        # This should not raise a validation error
        result = self.node.execute(
            operation="complete_transaction",
            transaction_id="schema_test_456",
            success=False,
        )

        assert result["transaction_status"] == "completed"


class TestRaceConditionDetectorNewFeatures:
    """Test new features added to RaceConditionDetectorNode."""

    def setup_method(self):
        """Set up test fixtures."""
        self.node = RaceConditionDetectorNode()

    def test_complete_operation(self):
        """Test the new complete_operation."""
        # Register an operation first
        self.node.execute(
            operation="register_operation",
            operation_id="op_123",
            resource_id="shared_resource",
            thread_id="thread_1",
        )

        # Complete it
        result = self.node.execute(
            operation="complete_operation",
            operation_id="op_123",
            resource_id="shared_resource",
            success=True,
        )

        assert result["status"] == "success"
        assert result["operation_id"] == "op_123"
        assert result["operation_success"] is True
        assert "races_detected" in result
        assert "race_count" in result
        assert "active_accesses" in result
        assert "active_operations" in result
        assert result["monitoring_status"] == "operation_completed"


class TestAsyncNodeEnhancements:
    """Test enhancements to AsyncNode base class."""

    def test_async_node_event_loop_handling(self):
        """Test that AsyncNode properly handles event loop scenarios."""
        node = TransactionMetricsNode()  # Uses AsyncNode base class

        # This should work without "RuntimeError: no running event loop"
        result = node.execute(operation="get_metrics")

        assert result["status"] == "success"
        # Should have our new fields
        assert "success_rate" in result
        assert "total_transactions" in result

    @pytest.mark.asyncio
    async def test_async_execution_direct(self):
        """Test direct async execution."""
        node = TransactionMetricsNode()

        result = await node.execute_async(operation="get_metrics")

        assert result["status"] == "success"
        assert "success_rate" in result
        assert "total_transactions" in result


if __name__ == "__main__":
    pytest.main([__file__])
