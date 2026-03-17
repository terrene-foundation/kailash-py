"""Integration tests for SagaCoordinatorNode with real node execution.

These tests verify that the saga coordinator correctly wires step execution
and compensation to a real NodeExecutor, using MockNodeExecutor to control
outcomes without depending on external infrastructure.
"""

import pytest

from kailash.nodes.transaction.node_executor import MockNodeExecutor
from kailash.nodes.transaction.saga_coordinator import SagaCoordinatorNode, SagaState


class TestSagaRealExecution:
    """End-to-end saga execution through the NodeExecutor integration."""

    @pytest.fixture
    def executor(self):
        return MockNodeExecutor()

    @pytest.fixture
    def saga(self, executor):
        return SagaCoordinatorNode(
            saga_name="integration_test",
            timeout=30.0,
            enable_monitoring=False,
            executor=executor,
        )

    # ------------------------------------------------------------------
    # Happy path: three steps, all succeed
    # ------------------------------------------------------------------

    def test_three_step_saga_success(self, saga, executor):
        """All three steps execute via the executor and saga completes."""
        # Configure executor responses
        executor.set_response(
            "ValidateOrder",
            {"status": "success", "data": {"order_valid": True}},
        )
        executor.set_response(
            "ProcessPayment",
            {"status": "success", "data": {"payment_id": "pay_123"}},
        )
        executor.set_response(
            "ShipOrder",
            {"status": "success", "data": {"tracking": "TRACK_456"}},
        )

        # Create saga
        saga.execute(operation="create_saga", context={"order_id": "ord_789"})

        # Add 3 steps
        saga.execute(
            operation="add_step",
            name="validate",
            node_id="ValidateOrder",
            parameters={"output_key": "validation"},
            compensation_node_id="CancelValidation",
        )
        saga.execute(
            operation="add_step",
            name="payment",
            node_id="ProcessPayment",
            parameters={"output_key": "payment"},
            compensation_node_id="RefundPayment",
        )
        saga.execute(
            operation="add_step",
            name="shipping",
            node_id="ShipOrder",
            parameters={"output_key": "shipment"},
            compensation_node_id="CancelShipment",
        )

        # Execute
        result = saga.execute(operation="execute_saga")

        assert result["status"] == "success"
        assert result["state"] == "completed"
        assert result["steps_completed"] == 3

        # Verify executor was called with the correct node types
        call_types = [c["node_type"] for c in executor.calls]
        assert call_types == ["ValidateOrder", "ProcessPayment", "ShipOrder"]

        # Verify saga context was passed to each call
        for call in executor.calls:
            assert "order_id" in call["params"]
            assert call["params"]["order_id"] == "ord_789"

    # ------------------------------------------------------------------
    # Failure on step 3: compensation for steps 2 and 1
    # ------------------------------------------------------------------

    def test_step_failure_triggers_compensation(self, saga, executor):
        """When step 3 fails, steps 2 and 1 are compensated in reverse order."""
        executor.set_response(
            "ValidateOrder",
            {"status": "success", "data": {"order_valid": True}},
        )
        executor.set_response(
            "ProcessPayment",
            {"status": "success", "data": {"payment_id": "pay_123"}},
        )
        # Step 3 fails
        executor.set_failure("ShipOrder", RuntimeError("Warehouse unavailable"))

        # Compensation nodes succeed
        executor.set_response("RefundPayment", {"status": "success"})
        executor.set_response("CancelValidation", {"status": "success"})

        # Build saga
        saga.execute(operation="create_saga", context={"order_id": "ord_999"})
        saga.execute(
            operation="add_step",
            name="validate",
            node_id="ValidateOrder",
            parameters={},
            compensation_node_id="CancelValidation",
        )
        saga.execute(
            operation="add_step",
            name="payment",
            node_id="ProcessPayment",
            parameters={},
            compensation_node_id="RefundPayment",
        )
        saga.execute(
            operation="add_step",
            name="shipping",
            node_id="ShipOrder",
            parameters={},
            compensation_node_id="CancelShipment",
        )

        result = saga.execute(operation="execute_saga")

        assert result["status"] == "failed"
        assert result["failed_step"] == "shipping"
        assert "Warehouse unavailable" in result["error"]

        # Compensation should have been called for steps 2 and 1 (reverse)
        compensation = result["compensation"]
        assert "payment" in compensation["compensated_steps"]
        assert "validate" in compensation["compensated_steps"]

        # Verify compensation calls hit the executor
        comp_calls = [
            c["node_type"]
            for c in executor.calls
            if c["node_type"] in ("RefundPayment", "CancelValidation")
        ]
        # Reverse order: payment first, then validation
        assert comp_calls == ["RefundPayment", "CancelValidation"]

    # ------------------------------------------------------------------
    # Compensation receives original_result and saga context
    # ------------------------------------------------------------------

    def test_compensation_params_include_original_result(self, saga, executor):
        """Compensation calls receive the original step result and saga context."""
        step_result = {"status": "success", "data": {"reserved": True}}
        executor.set_response("ReserveInventory", step_result)
        executor.set_failure("ChargeCard", ValueError("Card expired"))
        executor.set_response("ReleaseInventory", {"status": "success"})

        saga.execute(operation="create_saga", context={"customer": "cust_1"})
        saga.execute(
            operation="add_step",
            name="reserve",
            node_id="ReserveInventory",
            parameters={},
            compensation_node_id="ReleaseInventory",
            compensation_parameters={"reason": "saga_rollback"},
        )
        saga.execute(
            operation="add_step",
            name="charge",
            node_id="ChargeCard",
            parameters={},
            compensation_node_id="RefundCard",
        )

        result = saga.execute(operation="execute_saga")
        assert result["status"] == "failed"

        # Find the compensation call for ReleaseInventory
        release_calls = [
            c for c in executor.calls if c["node_type"] == "ReleaseInventory"
        ]
        assert len(release_calls) == 1
        comp_params = release_calls[0]["params"]

        # Should include compensation_parameters, original_result, and saga context
        assert comp_params["reason"] == "saga_rollback"
        assert comp_params["original_result"] == step_result
        assert comp_params["customer"] == "cust_1"

    # ------------------------------------------------------------------
    # No compensation node defined: step is skipped in compensation
    # ------------------------------------------------------------------

    def test_step_without_compensation_is_skipped(self, saga, executor):
        """Steps without a compensation_node_id are skipped during compensation."""
        executor.set_response("StepA", {"status": "success"})
        executor.set_failure("StepB", RuntimeError("boom"))

        saga.execute(operation="create_saga")
        saga.execute(
            operation="add_step",
            name="step_a",
            node_id="StepA",
            parameters={},
            # No compensation_node_id
        )
        saga.execute(
            operation="add_step",
            name="step_b",
            node_id="StepB",
            parameters={},
            compensation_node_id="CompB",
        )

        result = saga.execute(operation="execute_saga")
        assert result["status"] == "failed"

        # step_a should NOT appear in compensated_steps (no comp node)
        compensation = result["compensation"]
        assert "step_a" not in compensation["compensated_steps"]

    # ------------------------------------------------------------------
    # Saga state transitions
    # ------------------------------------------------------------------

    def test_saga_state_after_success(self, saga, executor):
        """Saga state is COMPLETED after all steps succeed."""
        executor.set_response("Node", {"status": "success"})
        saga.execute(operation="create_saga")
        saga.execute(operation="add_step", name="s", node_id="Node", parameters={})
        saga.execute(operation="execute_saga")

        assert saga.state == SagaState.COMPLETED

    def test_saga_state_after_failure_with_compensation(self, saga, executor):
        """Saga state is COMPENSATED when failure + compensation both complete."""
        executor.set_response("NodeA", {"status": "success"})
        executor.set_failure("NodeB", RuntimeError("fail"))
        executor.set_response("CompA", {"status": "success"})

        saga.execute(operation="create_saga")
        saga.execute(
            operation="add_step",
            name="a",
            node_id="NodeA",
            parameters={},
            compensation_node_id="CompA",
        )
        saga.execute(
            operation="add_step",
            name="b",
            node_id="NodeB",
            parameters={},
            compensation_node_id="CompB",
        )
        saga.execute(operation="execute_saga")

        assert saga.state == SagaState.COMPENSATED

    # ------------------------------------------------------------------
    # Executor timeout is forwarded
    # ------------------------------------------------------------------

    def test_executor_receives_saga_timeout(self, executor):
        """The saga's timeout value is passed through to the executor."""
        saga = SagaCoordinatorNode(
            saga_name="timeout_test",
            timeout=42.0,
            enable_monitoring=False,
            executor=executor,
        )
        executor.set_response("FastNode", {"status": "success"})

        saga.execute(operation="create_saga", timeout=42.0)
        saga.execute(
            operation="add_step", name="fast", node_id="FastNode", parameters={}
        )
        saga.execute(operation="execute_saga", timeout=42.0)

        assert executor.calls[0]["timeout"] == 42.0

    # ------------------------------------------------------------------
    # Event logging still works with real execution
    # ------------------------------------------------------------------

    def test_event_history_logged_for_real_execution(self, saga, executor):
        """step_started / step_completed events are emitted for real execution."""
        executor.set_response("LogNode", {"status": "success"})

        saga.execute(operation="create_saga")
        saga.execute(
            operation="add_step", name="logged", node_id="LogNode", parameters={}
        )
        saga.execute(operation="execute_saga")

        history = saga.execute(operation="get_history")
        event_types = [e["event_type"] for e in history["history"]]
        assert "step_started" in event_types
        assert "step_completed" in event_types

    # ------------------------------------------------------------------
    # Compensation failure: partial compensation reported
    # ------------------------------------------------------------------

    def test_compensation_failure_reported(self, saga, executor):
        """When a compensation node fails, the error is captured and reported."""
        executor.set_response("NodeA", {"status": "success"})
        executor.set_response("NodeB", {"status": "success"})
        executor.set_failure("NodeC", RuntimeError("step C dies"))

        # CompB fails during compensation
        executor.set_failure("CompB", RuntimeError("comp B fails"))
        executor.set_response("CompA", {"status": "success"})

        saga.execute(operation="create_saga")
        saga.execute(
            operation="add_step",
            name="a",
            node_id="NodeA",
            parameters={},
            compensation_node_id="CompA",
        )
        saga.execute(
            operation="add_step",
            name="b",
            node_id="NodeB",
            parameters={},
            compensation_node_id="CompB",
        )
        saga.execute(
            operation="add_step",
            name="c",
            node_id="NodeC",
            parameters={},
            compensation_node_id="CompC",
        )

        result = saga.execute(operation="execute_saga")

        assert result["status"] == "failed"
        compensation = result["compensation"]
        assert compensation["status"] == "partial_compensation"
        assert len(compensation["compensation_errors"]) == 1
        assert compensation["compensation_errors"][0]["step"] == "b"
        assert "comp B fails" in compensation["compensation_errors"][0]["error"]

        # Step A was still compensated successfully
        assert "a" in compensation["compensated_steps"]

        # Final saga state should be FAILED (partial compensation)
        assert saga.state == SagaState.FAILED
