"""Unit tests for SagaCoordinatorNode."""

import time
from unittest.mock import MagicMock, patch

import pytest
from kailash.nodes.transaction import SagaCoordinatorNode, SagaStepNode
from kailash.nodes.transaction.saga_state_storage import InMemoryStateStorage
from kailash.sdk_exceptions import NodeExecutionError


class TestSagaCoordinatorNode:
    """Test suite for SagaCoordinatorNode."""

    @pytest.fixture
    def saga_coordinator(self):
        """Create a SagaCoordinatorNode instance for testing."""
        return SagaCoordinatorNode(
            saga_name="test_saga",
            timeout=300.0,
            enable_monitoring=False,
        )

    def test_create_saga(self, saga_coordinator):
        """Test creating a new saga."""
        result = saga_coordinator.execute(
            operation="create_saga",
            saga_name="order_processing",
            timeout=600.0,
            context={"user_id": "user123", "order_id": "order456"},
        )

        assert result["status"] == "success"
        assert result["saga_name"] == "order_processing"
        assert result["state"] == "pending"
        assert "saga_id" in result

    def test_add_step(self, saga_coordinator):
        """Test adding steps to a saga."""
        # First create saga
        saga_coordinator.execute(operation="create_saga")

        # Add step
        result = saga_coordinator.execute(
            operation="add_step",
            name="validate_order",
            node_id="validation_node",
            parameters={"validation_rules": ["check_inventory", "verify_payment"]},
            compensation_node_id="cancel_order_node",
            compensation_parameters={"reason": "validation_failed"},
        )

        assert result["status"] == "success"
        assert result["step_index"] == 0
        assert result["total_steps"] == 1
        assert "step_id" in result

    def test_add_step_invalid_state(self, saga_coordinator):
        """Test adding step to saga in invalid state."""
        # Create and start saga
        saga_coordinator.execute(operation="create_saga")
        saga_coordinator.state = saga_coordinator.state.__class__.RUNNING

        # Try to add step
        result = saga_coordinator.execute(
            operation="add_step",
            name="invalid_step",
            node_id="some_node",
        )

        assert result["status"] == "error"
        assert "Cannot add steps" in result["error"]

    def test_execute_saga_no_steps(self, saga_coordinator):
        """Test executing saga with no steps."""
        # Create saga
        saga_coordinator.execute(operation="create_saga")

        # Try to execute
        result = saga_coordinator.execute(operation="execute_saga")

        assert result["status"] == "error"
        assert "No steps defined" in result["error"]

    def test_execute_saga_success(self, saga_coordinator):
        """Test successful saga execution."""
        # Create saga
        saga_coordinator.execute(operation="create_saga")

        # Add steps
        steps = [
            {
                "name": "step1",
                "node_id": "node1",
                "parameters": {"output_key": "result1"},
            },
            {
                "name": "step2",
                "node_id": "node2",
                "parameters": {"output_key": "result2"},
            },
            {
                "name": "step3",
                "node_id": "node3",
                "parameters": {"output_key": "result3"},
            },
        ]

        for step in steps:
            saga_coordinator.execute(
                operation="add_step",
                **step,
                compensation_node_id=f"comp_{step['node_id']}",
            )

        # Execute saga
        result = saga_coordinator.execute(operation="execute_saga")

        assert result["status"] == "success"
        assert result["state"] == "completed"
        assert result["steps_completed"] == 3
        assert "duration" in result
        assert "context" in result

    def test_execute_saga_with_failure(self, saga_coordinator):
        """Test saga execution with step failure."""
        import asyncio

        # Create saga
        saga_coordinator.execute(operation="create_saga")

        # Add steps
        for i in range(3):
            saga_coordinator.execute(
                operation="add_step",
                name=f"step{i+1}",
                node_id=f"node{i+1}",
                compensation_node_id=f"comp_node{i+1}",
            )

        # Mock step execution to fail on second step
        async def mock_execute_step(step, inputs):
            if step.name == "step2":
                raise Exception("Step 2 failed")
            return {"status": "success", "data": f"result_{step.name}"}

        saga_coordinator._execute_step = mock_execute_step

        # Execute saga
        result = saga_coordinator.execute(operation="execute_saga")

        assert result["status"] == "failed"
        assert result["failed_step"] == "step2"
        assert "Step 2 failed" in result["error"]
        assert "compensation" in result

    def test_compensate(self, saga_coordinator):
        """Test compensation execution."""
        # Create saga with completed steps
        saga_coordinator.execute(operation="create_saga")

        # Add and "complete" steps
        for i in range(3):
            step = MagicMock()
            step.step_id = f"step_{i}"
            step.name = f"step{i+1}"
            step.state = "completed"
            step.compensation_node_id = f"comp_node{i+1}"
            saga_coordinator.steps.append(step)

        saga_coordinator.current_step_index = 2
        saga_coordinator.state = saga_coordinator.state.__class__.COMPENSATING

        # Execute compensation
        result = saga_coordinator.execute(operation="compensate")

        assert result["status"] == "compensated"
        assert len(result["compensated_steps"]) == 3
        assert result["compensation_errors"] == []

    def test_get_status(self, saga_coordinator):
        """Test getting saga status."""
        # Create saga
        saga_coordinator.execute(operation="create_saga", saga_name="test_saga")

        # Add a step
        saga_coordinator.execute(
            operation="add_step",
            name="test_step",
            node_id="test_node",
        )

        # Get status
        result = saga_coordinator.execute(operation="get_status")

        assert result["status"] == "success"
        assert result["saga_name"] == "test_saga"
        assert result["state"] == "pending"
        assert result["total_steps"] == 1
        assert len(result["steps"]) == 1

    def test_cancel_saga(self, saga_coordinator):
        """Test canceling a saga."""
        # Create and start saga
        saga_coordinator.execute(operation="create_saga")
        saga_coordinator.state = saga_coordinator.state.__class__.RUNNING

        # Mock compensate method
        saga_coordinator._compensate = MagicMock(return_value={"status": "compensated"})

        # Cancel saga
        result = saga_coordinator.execute(operation="cancel")

        assert saga_coordinator._compensate.called
        assert saga_coordinator.state == saga_coordinator.state.__class__.COMPENSATING

    def test_cancel_completed_saga(self, saga_coordinator):
        """Test canceling a completed saga (should fail)."""
        # Create completed saga
        saga_coordinator.execute(operation="create_saga")
        saga_coordinator.state = saga_coordinator.state.__class__.COMPLETED

        # Try to cancel
        result = saga_coordinator.execute(operation="cancel")

        assert result["status"] == "error"
        assert "Cannot cancel completed saga" in result["error"]

    def test_resume_saga(self, saga_coordinator):
        """Test resuming a saga."""
        # Create saga with pending steps
        saga_coordinator.execute(operation="create_saga")

        # Add steps with mixed states
        step1 = MagicMock()
        step1.state = "completed"
        step1.name = "step1"
        saga_coordinator.steps.append(step1)

        step2 = MagicMock()
        step2.state = "pending"
        step2.name = "step2"
        saga_coordinator.steps.append(step2)

        saga_coordinator.state = saga_coordinator.state.__class__.RUNNING

        # Mock execute_saga
        saga_coordinator._execute_saga = MagicMock(return_value={"status": "success"})

        # Resume
        result = saga_coordinator.execute(operation="resume")

        assert saga_coordinator._execute_saga.called

    def test_get_history(self, saga_coordinator):
        """Test getting saga execution history."""
        # Create saga and add some events
        saga_coordinator.execute(operation="create_saga")

        # Add some history
        saga_coordinator._log_event("test_event", {"data": "test"})
        saga_coordinator._log_event("another_event", {"data": "more_test"})

        # Get history
        result = saga_coordinator.execute(operation="get_history")

        assert result["status"] == "success"
        assert result["total_events"] == 2
        assert len(result["history"]) == 2

    def test_state_persistence(self, saga_coordinator):
        """Test state persistence mechanism."""
        # Create saga
        result = saga_coordinator.execute(
            operation="create_saga",
            saga_id="test_saga_123",
            context={"test_data": "value"},
        )

        # Add a step
        saga_coordinator.execute(
            operation="add_step",
            name="test_step",
            node_id="test_node",
        )

        # Check state was persisted (InMemoryStateStorage used by default)
        storage = saga_coordinator._state_storage
        assert isinstance(storage._storage, dict)
        assert "test_saga_123" in storage._storage
        state = storage._storage["test_saga_123"]
        assert state["saga_id"] == "test_saga_123"
        assert state["state"] == "pending"
        assert len(state["steps"]) == 1
        assert state["context"]["test_data"] == "value"

    def test_unknown_operation(self, saga_coordinator):
        """Test handling of unknown operation."""
        with pytest.raises(NodeExecutionError) as exc_info:
            saga_coordinator.execute(operation="unknown_operation")

        assert "Unknown operation" in str(exc_info.value)

    def test_saga_timeout_configuration(self):
        """Test saga timeout configuration."""
        saga = SagaCoordinatorNode(timeout=1800.0)
        assert saga.timeout == 1800.0

        saga = SagaCoordinatorNode()
        assert saga.timeout == 3600.0  # Default

    def test_retry_policy_configuration(self):
        """Test retry policy configuration."""
        retry_policy = {"max_attempts": 5, "delay": 2.0}
        saga = SagaCoordinatorNode(retry_policy=retry_policy)
        assert saga.retry_policy["max_attempts"] == 5
        assert saga.retry_policy["delay"] == 2.0
