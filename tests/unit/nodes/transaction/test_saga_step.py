"""Unit tests for SagaStepNode."""

import time
from unittest.mock import MagicMock, patch

import pytest
from kailash.nodes.transaction import SagaStepNode
from kailash.sdk_exceptions import NodeExecutionError


class TestSagaStepNode:
    """Test suite for SagaStepNode."""

    @pytest.fixture
    def saga_step(self):
        """Create a SagaStepNode instance for testing."""
        return SagaStepNode(
            step_name="test_step",
            idempotent=True,
            retry_on_failure=True,
            max_retries=3,
            enable_monitoring=False,
        )

    def test_execute_forward_success(self, saga_step):
        """Test successful forward execution."""
        result = saga_step.execute(
            operation="execute",
            execution_id="exec123",
            saga_context={"order_id": "order456"},
            action_type="process_payment",
            data={"amount": 100.0, "currency": "USD"},
        )

        assert result["status"] == "success"
        assert result["step_name"] == "test_step"
        assert result["execution_id"] == "exec123"
        assert result["data"]["action"] == "process_payment"
        assert result["attempts"] == 1

    def test_execute_forward_with_custom_action(self, saga_step):
        """Test forward execution with custom action."""
        custom_result = {"custom": "result", "processed": True}

        def custom_forward(inputs, saga_ctx):
            return custom_result

        saga_step.forward_action = custom_forward

        result = saga_step.execute(
            operation="execute",
            execution_id="exec456",
            saga_context={"test": "data"},
        )

        assert result["status"] == "success"
        assert result["data"] == custom_result

    def test_idempotent_execution(self, saga_step):
        """Test idempotent execution returns cached result."""
        # First execution
        result1 = saga_step.execute(
            operation="execute",
            execution_id="exec789",
            saga_context={},
            data={"test": "data"},
        )
        assert result1["status"] == "success"
        assert "cached" not in result1

        # Second execution (should return cached)
        result2 = saga_step.execute(
            operation="execute",
            execution_id="exec789",
            saga_context={},
            data={"test": "data"},
        )
        assert result2["status"] == "success"
        assert result2["cached"] is True
        assert result2["data"] == result1["data"]

    def test_non_idempotent_execution(self, saga_step):
        """Test non-idempotent execution executes every time."""
        saga_step.idempotent = False

        # Execute twice
        result1 = saga_step.execute(
            operation="execute",
            execution_id="exec999",
            saga_context={},
        )
        result2 = saga_step.execute(
            operation="execute",
            execution_id="exec999",
            saga_context={},
        )

        # Both should execute (not cached)
        assert result1["status"] == "success"
        assert result2["status"] == "success"
        assert "cached" not in result1
        assert "cached" not in result2

    def test_execute_with_retries(self, saga_step):
        """Test execution with retries on failure."""
        attempt_count = 0

        # Use fast retry delay for unit tests
        saga_step.retry_delay = 0.001

        def flaky_action(inputs, saga_ctx):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception(f"Attempt {attempt_count} failed")
            return {"success": True}

        saga_step.forward_action = flaky_action

        result = saga_step.execute(
            operation="execute",
            execution_id="exec_retry",
            saga_context={},
        )

        assert result["status"] == "success"
        assert result["attempts"] == 3
        assert attempt_count == 3

    def test_execute_max_retries_exceeded(self, saga_step):
        """Test execution fails after max retries."""

        # Use fast retry delay for unit tests
        saga_step.retry_delay = 0.001

        def always_fail(inputs, saga_ctx):
            raise Exception("Always fails")

        saga_step.forward_action = always_fail
        saga_step.max_retries = 2

        result = saga_step.execute(
            operation="execute",
            execution_id="exec_fail",
            saga_context={},
        )

        assert result["status"] == "failed"
        assert result["attempts"] == 2
        assert "Always fails" in result["error"]

    def test_validate_preconditions_valid(self, saga_step):
        """Test precondition validation passes."""
        result = saga_step.execute(
            operation="validate",
            required_inputs=["user_id", "order_id"],
            saga_context={"user_id": "user123", "order_id": "order456"},
        )

        assert result["status"] == "valid"
        assert result["message"] == "All preconditions satisfied"

    def test_validate_preconditions_invalid(self, saga_step):
        """Test precondition validation fails."""
        result = saga_step.execute(
            operation="validate",
            required_inputs=["user_id", "order_id", "payment_token"],
            saga_context={"user_id": "user123"},
        )

        assert result["status"] == "invalid"
        assert result["missing_inputs"] == ["order_id", "payment_token"]

    def test_execute_compensation_success(self, saga_step):
        """Test successful compensation execution."""
        # First execute forward
        saga_step.execute(
            operation="execute",
            execution_id="exec_comp",
            saga_context={"order_id": "order789"},
            data={"amount": 50.0},
        )

        # Then compensate
        result = saga_step.execute(
            operation="compensate",
            execution_id="exec_comp",
            saga_context={"order_id": "order789"},
        )

        assert result["status"] == "compensated"
        assert result["step_name"] == "test_step"
        assert result["attempts"] == 1

    def test_execute_compensation_with_custom_action(self, saga_step):
        """Test compensation with custom action."""
        # Execute forward first
        saga_step.execute(operation="execute", execution_id="exec123")

        custom_comp_result = {"compensated": True, "refunded": 100.0}

        def custom_compensation(inputs, saga_ctx, exec_state):
            return custom_comp_result

        saga_step.compensation_action = custom_compensation

        result = saga_step.execute(
            operation="compensate",
            execution_id="exec123",
            saga_context={},
        )

        assert result["status"] == "compensated"
        assert result["compensation_result"] == custom_comp_result

    def test_compensate_without_forward_execution(self, saga_step):
        """Test compensation without prior forward execution."""
        result = saga_step.execute(
            operation="compensate",
            execution_id="no_exec",
            saga_context={},
        )

        assert result["status"] == "skipped"
        assert "No forward execution to compensate" in result["message"]

    def test_compensate_already_compensated(self, saga_step):
        """Test compensation of already compensated step."""
        # Execute forward
        saga_step.execute(operation="execute", execution_id="exec_twice")

        # Compensate once
        result1 = saga_step.execute(operation="compensate", execution_id="exec_twice")
        assert result1["status"] == "compensated"

        # Try to compensate again
        result2 = saga_step.execute(operation="compensate", execution_id="exec_twice")
        assert result2["status"] == "already_compensated"

    def test_compensation_with_retries(self, saga_step):
        """Test compensation with retries."""
        # Use fast retry delay for unit tests
        saga_step.retry_delay = 0.001

        # Execute forward first
        saga_step.execute(operation="execute", execution_id="exec_retry_comp")

        attempt_count = 0

        def flaky_compensation(inputs, saga_ctx, exec_state):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise Exception(f"Compensation attempt {attempt_count} failed")
            return {"compensated": True}

        saga_step.compensation_action = flaky_compensation

        result = saga_step.execute(
            operation="compensate",
            execution_id="exec_retry_comp",
        )

        assert result["status"] == "compensated"
        assert result["attempts"] == 2

    def test_compensation_max_retries_exceeded(self, saga_step):
        """Test compensation fails after max retries."""
        # Use fast retry delay for unit tests
        saga_step.retry_delay = 0.001

        # Execute forward first
        saga_step.execute(operation="execute", execution_id="exec_comp_fail")

        def always_fail_comp(inputs, saga_ctx, exec_state):
            raise Exception("Compensation always fails")

        saga_step.compensation_action = always_fail_comp
        saga_step.compensation_retries = 2

        result = saga_step.execute(
            operation="compensate",
            execution_id="exec_comp_fail",
        )

        assert result["status"] == "compensation_failed"
        assert result["attempts"] == 2
        assert "Compensation always fails" in result["error"]

    def test_get_status(self, saga_step):
        """Test getting step status."""
        # Execute forward
        saga_step.execute(
            operation="execute",
            execution_id="exec_status",
            data={"test": "data"},
        )

        # Get status
        result = saga_step.execute(operation="get_status")

        assert result["status"] == "success"
        assert result["step_name"] == "test_step"
        assert result["idempotent"] is True
        assert "execution_state" in result
        assert "retry_settings" in result

    def test_unknown_operation(self, saga_step):
        """Test handling of unknown operation."""
        with pytest.raises(NodeExecutionError) as exc_info:
            saga_step.execute(operation="unknown_op")

        assert "Unknown operation" in str(exc_info.value)

    def test_retry_delay_exponential_backoff(self, saga_step):
        """Test exponential backoff in retry delay."""
        attempt_times = []

        def track_attempts(inputs, saga_ctx):
            attempt_times.append(time.time())
            if len(attempt_times) < 3:
                raise Exception("Fail")
            return {"success": True}

        saga_step.forward_action = track_attempts
        saga_step.retry_delay = 0.1  # Small delay for testing

        with patch("time.sleep") as mock_sleep:
            result = saga_step.execute(operation="execute")

        # Check exponential backoff was applied
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 0.1  # First retry: delay * 1
        assert mock_sleep.call_args_list[1][0][0] == 0.2  # Second retry: delay * 2

    def test_step_configuration(self):
        """Test step configuration options."""
        step = SagaStepNode(
            step_name="custom_step",
            idempotent=False,
            retry_on_failure=False,
            max_retries=5,
            retry_delay=2.0,
            timeout=600.0,
            compensation_timeout=1200.0,
            compensation_retries=10,
        )

        assert step.step_name == "custom_step"
        assert step.idempotent is False
        assert step.retry_on_failure is False
        assert step.max_retries == 5
        assert step.retry_delay == 2.0
        assert step.timeout == 600.0
        assert step.compensation_timeout == 1200.0
        assert step.compensation_retries == 10
