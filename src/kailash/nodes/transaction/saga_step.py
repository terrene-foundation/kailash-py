"""Saga Step Node for executing individual steps in a distributed transaction.

Each saga step represents a local transaction that can be compensated if needed.
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Callable, Dict, Optional

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


@register_node()
class SagaStepNode(AsyncNode):
    """Executes individual steps within a Saga transaction.

    Each SagaStepNode represents a single, compensatable unit of work within
    a distributed transaction. It encapsulates both the forward action and
    its compensating action.

    Features:
    - Idempotent execution
    - Built-in compensation logic
    - State tracking
    - Retry support
    - Monitoring integration

    Examples:
        >>> # Execute a saga step
        >>> step = SagaStepNode(step_name="process_payment")
        >>> result = await step.execute(
        ...     operation="execute",
        ...     execution_id="exec_123",
        ...     saga_context={"order_id": "order_456"},
        ...     data={"amount": 100.0, "currency": "USD"}
        ... )

        >>> # Compensate if needed
        >>> result = await step.execute(
        ...     operation="compensate",
        ...     execution_id="exec_123"
        ... )
    """

    def __init__(self, **kwargs):
        # Set node-specific attributes before calling parent
        self.step_name = kwargs.pop("step_name", "saga_step")
        self.idempotent = kwargs.pop("idempotent", True)
        self.retry_on_failure = kwargs.pop("retry_on_failure", True)
        self.max_retries = kwargs.pop("max_retries", 3)
        self.retry_delay = kwargs.pop("retry_delay", 1.0)
        self.timeout = kwargs.pop("timeout", 300.0)  # 5 minutes default
        self.enable_monitoring = kwargs.pop("enable_monitoring", True)

        # Compensation settings
        self.compensation_timeout = kwargs.pop(
            "compensation_timeout", 600.0
        )  # 10 minutes
        self.compensation_retries = kwargs.pop("compensation_retries", 5)

        # State tracking
        self.execution_id: Optional[str] = None
        self.execution_state: Dict[str, Any] = {}
        self.compensation_state: Dict[str, Any] = {}

        # Custom action handlers (can be overridden by subclasses)
        self.forward_action: Optional[Callable] = None
        self.compensation_action: Optional[Callable] = None

        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters for the Saga Step node."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="execute",
                description="Operation to perform",
            ),
            "execution_id": NodeParameter(
                name="execution_id",
                type=str,
                required=False,
                description="Unique execution identifier",
            ),
            "saga_context": NodeParameter(
                name="saga_context",
                type=dict,
                default={},
                description="Saga context data",
            ),
            "action_type": NodeParameter(
                name="action_type",
                type=str,
                default="process",
                description="Type of action to perform",
            ),
            "data": NodeParameter(
                name="data",
                type=dict,
                default={},
                description="Data to process",
            ),
            "required_inputs": NodeParameter(
                name="required_inputs",
                type=list,
                default=[],
                description="Required inputs for validation",
            ),
        }

    def execute(self, **runtime_inputs) -> Dict[str, Any]:
        """Execute the saga step based on the requested operation."""
        # For sync compatibility with LocalRuntime, we don't make this async
        # The AsyncNode base class handles running async_run in a sync context
        operation = runtime_inputs.get("operation", "execute")

        operations = {
            "execute": self._execute_forward,
            "compensate": self._execute_compensation,
            "get_status": self._get_status,
            "validate": self._validate_preconditions,
        }

        if operation not in operations:
            raise NodeExecutionError(f"Unknown operation: {operation}")

        try:
            return operations[operation](runtime_inputs)
        except Exception as e:
            logger.error(f"Saga step error in {self.step_name}: {e}")
            return {
                "status": "error",
                "step_name": self.step_name,
                "error": str(e),
                "operation": operation,
            }

    def _execute_forward(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the forward action of the saga step."""
        self.execution_id = inputs.get("execution_id", str(uuid.uuid4()))
        saga_context = inputs.get("saga_context", {})

        # Check idempotency
        if self.idempotent and self._check_already_executed():
            logger.info(
                f"Step {self.step_name} already executed for {self.execution_id}"
            )
            return self._get_cached_result()

        # Validate preconditions
        validation_result = self._validate_preconditions(inputs)
        if validation_result.get("status") != "valid":
            return validation_result

        # Execute with retries
        attempt = 0
        last_error = None

        while attempt < self.max_retries:
            try:
                # Log execution start
                self._log_execution_start()

                # Execute the actual business logic
                if self.forward_action:
                    result = self.forward_action(inputs, saga_context)
                else:
                    result = self._default_forward_action(inputs, saga_context)

                # Store result for idempotency
                self.execution_state = {
                    "execution_id": self.execution_id,
                    "result": result,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "attempts": attempt + 1,
                }

                self._log_execution_complete(result)

                return {
                    "status": "success",
                    "step_name": self.step_name,
                    "execution_id": self.execution_id,
                    "data": result,
                    "attempts": attempt + 1,
                }

            except Exception as e:
                last_error = e
                attempt += 1
                logger.warning(
                    f"Step {self.step_name} failed on attempt {attempt}: {e}"
                )

                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)  # Exponential backoff

        # All retries exhausted
        self._log_execution_failed(str(last_error))

        return {
            "status": "failed",
            "step_name": self.step_name,
            "execution_id": self.execution_id,
            "error": str(last_error),
            "attempts": attempt,
        }

    def _execute_compensation(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the compensation action of the saga step."""
        self.execution_id = inputs.get("execution_id", self.execution_id)
        saga_context = inputs.get("saga_context", {})

        # Check if compensation is needed
        if not self.execution_state:
            logger.info(
                f"No forward execution found for {self.step_name}, skipping compensation"
            )
            return {
                "status": "skipped",
                "step_name": self.step_name,
                "message": "No forward execution to compensate",
            }

        # Check if already compensated
        if self._check_already_compensated():
            logger.info(f"Step {self.step_name} already compensated")
            return {
                "status": "already_compensated",
                "step_name": self.step_name,
                "execution_id": self.execution_id,
            }

        # Execute compensation with retries
        attempt = 0
        last_error = None

        while attempt < self.compensation_retries:
            try:
                # Log compensation start
                self._log_compensation_start()

                # Execute the compensation logic
                if self.compensation_action:
                    result = self.compensation_action(
                        inputs, saga_context, self.execution_state
                    )
                else:
                    result = self._default_compensation_action(
                        inputs, saga_context, self.execution_state
                    )

                # Store compensation result
                self.compensation_state = {
                    "execution_id": self.execution_id,
                    "result": result,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "attempts": attempt + 1,
                }

                self._log_compensation_complete(result)

                return {
                    "status": "compensated",
                    "step_name": self.step_name,
                    "execution_id": self.execution_id,
                    "compensation_result": result,
                    "attempts": attempt + 1,
                }

            except Exception as e:
                last_error = e
                attempt += 1
                logger.warning(
                    f"Compensation for {self.step_name} failed on attempt {attempt}: {e}"
                )

                if attempt < self.compensation_retries:
                    time.sleep(self.retry_delay * attempt)

        # Compensation failed
        self._log_compensation_failed(str(last_error))

        return {
            "status": "compensation_failed",
            "step_name": self.step_name,
            "execution_id": self.execution_id,
            "error": str(last_error),
            "attempts": attempt,
        }

    def _validate_preconditions(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate preconditions before executing the step."""
        # Override in subclasses for specific validation
        required_inputs = inputs.get("required_inputs", [])
        saga_context = inputs.get("saga_context", {})

        missing_inputs = []
        for required in required_inputs:
            if required not in saga_context:
                missing_inputs.append(required)

        if missing_inputs:
            return {
                "status": "invalid",
                "step_name": self.step_name,
                "missing_inputs": missing_inputs,
                "message": f"Missing required inputs: {missing_inputs}",
            }

        return {
            "status": "valid",
            "step_name": self.step_name,
            "message": "All preconditions satisfied",
        }

    def _get_status(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get the current status of the saga step."""
        return {
            "status": "success",
            "step_name": self.step_name,
            "execution_state": self.execution_state,
            "compensation_state": self.compensation_state,
            "idempotent": self.idempotent,
            "retry_settings": {
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay,
                "compensation_retries": self.compensation_retries,
            },
        }

    def _default_forward_action(
        self, inputs: Dict[str, Any], saga_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Default forward action implementation."""
        # Override in subclasses or provide custom forward_action
        action_type = inputs.get("action_type", "process")
        data = inputs.get("data", {})

        # Simulate some processing
        result = {
            "action": action_type,
            "processed_data": data,
            "timestamp": datetime.now(UTC).isoformat(),
            "step": self.step_name,
        }

        return result

    def _default_compensation_action(
        self,
        inputs: Dict[str, Any],
        saga_context: Dict[str, Any],
        execution_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Default compensation action implementation."""
        # Override in subclasses or provide custom compensation_action
        result = {
            "action": "compensate",
            "compensated_execution": execution_state.get("execution_id"),
            "timestamp": datetime.now(UTC).isoformat(),
            "step": self.step_name,
        }

        return result

    def _check_already_executed(self) -> bool:
        """Check if this step has already been executed."""
        return bool(self.execution_state)

    def _check_already_compensated(self) -> bool:
        """Check if this step has already been compensated."""
        return bool(self.compensation_state)

    def _get_cached_result(self) -> Dict[str, Any]:
        """Get the cached result from a previous execution."""
        return {
            "status": "success",
            "step_name": self.step_name,
            "execution_id": self.execution_id,
            "data": self.execution_state.get("result", {}),
            "cached": True,
            "cached_at": self.execution_state.get("timestamp"),
        }

    def _log_execution_start(self):
        """Log the start of step execution."""
        if self.enable_monitoring:
            logger.info(
                f"Starting execution of saga step: {self.step_name}",
                extra={
                    "step_name": self.step_name,
                    "execution_id": self.execution_id,
                    "event": "saga_step_started",
                },
            )

    def _log_execution_complete(self, result: Any):
        """Log successful completion of step execution."""
        if self.enable_monitoring:
            logger.info(
                f"Completed execution of saga step: {self.step_name}",
                extra={
                    "step_name": self.step_name,
                    "execution_id": self.execution_id,
                    "event": "saga_step_completed",
                },
            )

    def _log_execution_failed(self, error: str):
        """Log failure of step execution."""
        if self.enable_monitoring:
            logger.error(
                f"Failed execution of saga step: {self.step_name}",
                extra={
                    "step_name": self.step_name,
                    "execution_id": self.execution_id,
                    "error": error,
                    "event": "saga_step_failed",
                },
            )

    def _log_compensation_start(self):
        """Log the start of compensation."""
        if self.enable_monitoring:
            logger.info(
                f"Starting compensation for saga step: {self.step_name}",
                extra={
                    "step_name": self.step_name,
                    "execution_id": self.execution_id,
                    "event": "saga_compensation_started",
                },
            )

    def _log_compensation_complete(self, result: Any):
        """Log successful completion of compensation."""
        if self.enable_monitoring:
            logger.info(
                f"Completed compensation for saga step: {self.step_name}",
                extra={
                    "step_name": self.step_name,
                    "execution_id": self.execution_id,
                    "event": "saga_compensation_completed",
                },
            )

    def _log_compensation_failed(self, error: str):
        """Log failure of compensation."""
        if self.enable_monitoring:
            logger.error(
                f"Failed compensation for saga step: {self.step_name}",
                extra={
                    "step_name": self.step_name,
                    "execution_id": self.execution_id,
                    "error": error,
                    "event": "saga_compensation_failed",
                },
            )
