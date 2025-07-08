"""Saga Coordinator Node for orchestrating distributed transactions.

The Saga pattern provides a way to manage distributed transactions by breaking them
into a series of local transactions, each with a compensating action for rollback.
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

from .saga_state_storage import SagaStateStorage, StorageFactory

logger = logging.getLogger(__name__)


class SagaState(Enum):
    """Saga execution states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPENSATING = "compensating"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"


class SagaStep:
    """Represents a single step in a saga."""

    def __init__(
        self,
        step_id: str,
        name: str,
        node_id: str,
        parameters: Dict[str, Any],
        compensation_node_id: Optional[str] = None,
        compensation_parameters: Optional[Dict[str, Any]] = None,
    ):
        self.step_id = step_id
        self.name = name
        self.node_id = node_id
        self.parameters = parameters
        self.compensation_node_id = compensation_node_id
        self.compensation_parameters = compensation_parameters or {}
        self.state: str = "pending"
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None


@register_node()
class SagaCoordinatorNode(AsyncNode):
    """Orchestrates distributed transactions using the Saga pattern.

    The Saga Coordinator manages the execution of a series of steps, each representing
    a local transaction. If any step fails, the coordinator executes compensating
    actions for all previously completed steps in reverse order.

    Features:
    - Step-by-step transaction execution
    - Automatic compensation on failure
    - State persistence and recovery
    - Monitoring and observability
    - Configurable retry policies

    Examples:
        >>> # Create a saga
        >>> saga = SagaCoordinatorNode()
        >>> result = await saga.execute(
        ...     operation="create_saga",
        ...     saga_name="order_processing",
        ...     timeout=600.0
        ... )

        >>> # Add steps
        >>> result = await saga.execute(
        ...     operation="add_step",
        ...     name="validate_order",
        ...     node_id="ValidationNode",
        ...     compensation_node_id="CancelOrderNode"
        ... )

        >>> # Execute saga
        >>> result = await saga.execute(operation="execute_saga")
    """

    def __init__(self, **kwargs):
        # Set node-specific attributes before calling parent
        self.saga_id = kwargs.pop("saga_id", None) or str(uuid.uuid4())
        self.saga_name = kwargs.pop("saga_name", "distributed_transaction")
        self.timeout = kwargs.pop("timeout", 3600.0)  # 1 hour default
        self.retry_policy = kwargs.pop(
            "retry_policy", {"max_attempts": 3, "delay": 1.0}
        )
        self.enable_monitoring = kwargs.pop("enable_monitoring", True)
        self.state_storage_type = kwargs.pop(
            "state_storage", "memory"
        )  # or "redis", "database"

        # Initialize internal state
        self.steps: List[SagaStep] = []
        self.state = SagaState.PENDING
        self.current_step_index = -1
        self.saga_context: Dict[str, Any] = {}
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.saga_history: List[Dict[str, Any]] = []

        # State persistence
        storage_config = kwargs.pop("storage_config", {})
        self._state_storage: SagaStateStorage = StorageFactory.create_storage(
            self.state_storage_type, **storage_config
        )

        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters for the Saga Coordinator node."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="execute_saga",
                description="Operation to perform",
            ),
            "saga_name": NodeParameter(
                name="saga_name",
                type=str,
                required=False,
                description="Name of the saga",
            ),
            "saga_id": NodeParameter(
                name="saga_id",
                type=str,
                required=False,
                description="Unique saga identifier",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=float,
                default=3600.0,
                description="Saga timeout in seconds",
            ),
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                description="Step name (for add_step)",
            ),
            "node_id": NodeParameter(
                name="node_id",
                type=str,
                required=False,
                description="Node ID to execute (for add_step)",
            ),
            "parameters": NodeParameter(
                name="parameters",
                type=dict,
                default={},
                description="Parameters for the step",
            ),
            "compensation_node_id": NodeParameter(
                name="compensation_node_id",
                type=str,
                required=False,
                description="Node ID for compensation",
            ),
            "compensation_parameters": NodeParameter(
                name="compensation_parameters",
                type=dict,
                default={},
                description="Parameters for compensation",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                default={},
                description="Saga context data",
            ),
        }

    async def async_run(self, **runtime_inputs) -> Dict[str, Any]:
        """Execute the Saga coordinator based on the requested operation."""
        operation = runtime_inputs.get("operation", "execute_saga")

        operations = {
            "create_saga": self._create_saga,
            "add_step": self._add_step,
            "execute_saga": self._execute_saga,
            "get_status": self._get_status,
            "compensate": self._compensate,
            "resume": self._resume_saga,
            "cancel": self._cancel_saga,
            "get_history": self._get_history,
            "load_saga": self._load_saga,
            "list_sagas": self._list_sagas,
        }

        if operation not in operations:
            raise NodeExecutionError(f"Unknown operation: {operation}")

        try:
            return await operations[operation](runtime_inputs)
        except Exception as e:
            logger.error(f"Saga coordinator error: {e}")
            return {
                "status": "error",
                "saga_id": self.saga_id,
                "error": str(e),
                "operation": operation,
            }

    async def _create_saga(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new saga instance."""
        self.saga_id = inputs.get("saga_id", str(uuid.uuid4()))
        self.saga_name = inputs.get("saga_name", self.saga_name)
        self.timeout = inputs.get("timeout", self.timeout)

        # Initialize saga
        self.state = SagaState.PENDING
        self.steps = []
        self.saga_context = inputs.get("context", {})

        # Persist initial state
        await self._persist_state()

        return {
            "status": "success",
            "saga_id": self.saga_id,
            "saga_name": self.saga_name,
            "state": self.state.value,
            "message": "Saga created successfully",
        }

    async def _add_step(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Add a step to the saga."""
        if self.state != SagaState.PENDING:
            raise NodeExecutionError(
                f"Cannot add steps to saga in state: {self.state.value}"
            )

        step = SagaStep(
            step_id=inputs.get("step_id", str(uuid.uuid4())),
            name=inputs.get("name", f"step_{len(self.steps) + 1}"),
            node_id=inputs.get("node_id"),
            parameters=inputs.get("parameters", {}),
            compensation_node_id=inputs.get("compensation_node_id"),
            compensation_parameters=inputs.get("compensation_parameters", {}),
        )

        if not step.node_id:
            raise NodeExecutionError("node_id is required for saga step")

        self.steps.append(step)
        await self._persist_state()

        return {
            "status": "success",
            "saga_id": self.saga_id,
            "step_id": step.step_id,
            "step_index": len(self.steps) - 1,
            "total_steps": len(self.steps),
        }

    async def _execute_saga(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute all steps in the saga."""
        if self.state not in [SagaState.PENDING, SagaState.RUNNING]:
            raise NodeExecutionError(
                f"Cannot execute saga in state: {self.state.value}"
            )

        if not self.steps:
            raise NodeExecutionError("No steps defined in saga")

        self.state = SagaState.RUNNING
        self.start_time = time.time()
        await self._persist_state()

        # Execute steps sequentially
        for i, step in enumerate(self.steps):
            self.current_step_index = i

            try:
                # Execute step
                result = await self._execute_step(step, inputs)

                if result.get("status") != "success":
                    # Step failed, start compensation
                    self.state = SagaState.COMPENSATING
                    await self._persist_state()
                    compensation_result = await self._compensate(inputs)

                    return {
                        "status": "failed",
                        "saga_id": self.saga_id,
                        "failed_step": step.name,
                        "error": result.get("error", "Step execution failed"),
                        "compensation": compensation_result,
                    }

                # Update saga context with step results
                if "output_key" in step.parameters:
                    self.saga_context[step.parameters["output_key"]] = result.get(
                        "data"
                    )

            except Exception as e:
                logger.error(f"Error executing step {step.name}: {e}")
                self.state = SagaState.COMPENSATING
                await self._persist_state()

                compensation_result = await self._compensate(inputs)

                return {
                    "status": "failed",
                    "saga_id": self.saga_id,
                    "failed_step": step.name,
                    "error": str(e),
                    "compensation": compensation_result,
                }

        # All steps completed successfully
        self.state = SagaState.COMPLETED
        self.end_time = time.time()
        await self._persist_state()

        return {
            "status": "success",
            "saga_id": self.saga_id,
            "saga_name": self.saga_name,
            "state": self.state.value,
            "steps_completed": len(self.steps),
            "duration": self.end_time - self.start_time,
            "context": self.saga_context,
        }

    async def _execute_step(
        self, step: SagaStep, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single saga step."""
        step.state = "running"
        step.start_time = time.time()

        # Log step execution
        self._log_event(
            "step_started",
            {
                "step_id": step.step_id,
                "step_name": step.name,
                "node_id": step.node_id,
            },
        )

        try:
            # Simulate step execution (in real implementation, would call actual node)
            # For now, return success
            result = {
                "status": "success",
                "data": {"step_result": f"Result of {step.name}"},
            }

            step.state = "completed"
            step.result = result
            step.end_time = time.time()

            self._log_event(
                "step_completed",
                {
                    "step_id": step.step_id,
                    "duration": step.end_time - step.start_time,
                },
            )

            return result

        except Exception as e:
            step.state = "failed"
            step.error = str(e)
            step.end_time = time.time()

            self._log_event(
                "step_failed",
                {
                    "step_id": step.step_id,
                    "error": str(e),
                },
            )

            raise

    async def _compensate(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute compensation for all completed steps in reverse order."""
        if self.state not in [SagaState.COMPENSATING, SagaState.FAILED]:
            self.state = SagaState.COMPENSATING
            await self._persist_state()

        compensated_steps = []
        compensation_errors = []

        # Compensate in reverse order
        for i in range(self.current_step_index, -1, -1):
            step = self.steps[i]

            if step.state != "completed":
                continue

            if not step.compensation_node_id:
                logger.warning(f"No compensation defined for step {step.name}")
                continue

            try:
                # Execute compensation
                self._log_event(
                    "compensation_started",
                    {
                        "step_id": step.step_id,
                        "step_name": step.name,
                    },
                )

                # Simulate compensation (in real implementation, would call actual node)
                step.state = "compensated"
                compensated_steps.append(step.name)

                self._log_event(
                    "compensation_completed",
                    {
                        "step_id": step.step_id,
                    },
                )

            except Exception as e:
                logger.error(f"Compensation failed for step {step.name}: {e}")
                compensation_errors.append(
                    {
                        "step": step.name,
                        "error": str(e),
                    }
                )

        # Update saga state
        self.state = (
            SagaState.COMPENSATED if not compensation_errors else SagaState.FAILED
        )
        self.end_time = time.time()
        await self._persist_state()

        return {
            "status": (
                "compensated" if not compensation_errors else "partial_compensation"
            ),
            "saga_id": self.saga_id,
            "compensated_steps": compensated_steps,
            "compensation_errors": compensation_errors,
            "duration": self.end_time - self.start_time if self.start_time else 0,
        }

    async def _resume_saga(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Resume a saga from where it left off."""
        if self.state not in [SagaState.RUNNING, SagaState.FAILED]:
            raise NodeExecutionError(f"Cannot resume saga in state: {self.state.value}")

        # Find the next pending step
        next_step_index = -1
        for i, step in enumerate(self.steps):
            if step.state == "pending":
                next_step_index = i
                break

        if next_step_index == -1:
            return {
                "status": "no_pending_steps",
                "saga_id": self.saga_id,
                "message": "No pending steps to resume",
            }

        # Resume from the next pending step
        self.current_step_index = next_step_index - 1
        return await self._execute_saga(inputs)

    async def _cancel_saga(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel the saga and trigger compensation."""
        if self.state == SagaState.COMPLETED:
            raise NodeExecutionError("Cannot cancel completed saga")

        self.state = SagaState.COMPENSATING
        await self._persist_state()

        return await self._compensate(inputs)

    async def _get_status(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get the current status of the saga."""
        steps_status = []
        for step in self.steps:
            steps_status.append(
                {
                    "step_id": step.step_id,
                    "name": step.name,
                    "state": step.state,
                    "error": step.error,
                    "duration": (
                        (step.end_time - step.start_time)
                        if step.start_time and step.end_time
                        else None
                    ),
                }
            )

        return {
            "status": "success",
            "saga_id": self.saga_id,
            "saga_name": self.saga_name,
            "state": self.state.value,
            "current_step_index": self.current_step_index,
            "total_steps": len(self.steps),
            "steps": steps_status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": (
                (self.end_time - self.start_time)
                if self.start_time and self.end_time
                else None
            ),
            "context": self.saga_context,
        }

    async def _get_history(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get the execution history of the saga."""
        return {
            "status": "success",
            "saga_id": self.saga_id,
            "history": self.saga_history,
            "total_events": len(self.saga_history),
        }

    async def _persist_state(self):
        """Persist saga state for recovery."""
        state_data = {
            "saga_id": self.saga_id,
            "saga_name": self.saga_name,
            "state": self.state.value,
            "current_step_index": self.current_step_index,
            "steps": [
                {
                    "step_id": step.step_id,
                    "name": step.name,
                    "node_id": step.node_id,
                    "parameters": step.parameters,
                    "compensation_node_id": step.compensation_node_id,
                    "compensation_parameters": step.compensation_parameters,
                    "state": step.state,
                    "result": step.result,
                    "error": step.error,
                    "start_time": step.start_time,
                    "end_time": step.end_time,
                }
                for step in self.steps
            ],
            "context": self.saga_context,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "timestamp": datetime.now(UTC).isoformat(),
            "saga_history": self.saga_history,
        }

        success = await self._state_storage.save_state(self.saga_id, state_data)
        if not success:
            logger.error(f"Failed to persist state for saga {self.saga_id}")

    def _log_event(self, event_type: str, data: Dict[str, Any]):
        """Log an event to saga history."""
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "saga_id": self.saga_id,
            "data": data,
        }

        self.saga_history.append(event)

        if self.enable_monitoring:
            logger.info(f"Saga event: {event_type}", extra=event)

    async def _load_saga(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Load saga state from persistence."""
        saga_id = inputs.get("saga_id", self.saga_id)

        state_data = await self._state_storage.load_state(saga_id)
        if not state_data:
            return {
                "status": "not_found",
                "saga_id": saga_id,
                "message": f"Saga {saga_id} not found",
            }

        # Restore saga state
        self.saga_id = state_data["saga_id"]
        self.saga_name = state_data["saga_name"]
        self.state = SagaState(state_data["state"])
        self.current_step_index = state_data["current_step_index"]
        self.saga_context = state_data["context"]
        self.start_time = state_data.get("start_time")
        self.end_time = state_data.get("end_time")
        self.saga_history = state_data.get("saga_history", [])

        # Restore steps
        self.steps = []
        for step_data in state_data["steps"]:
            step = SagaStep(
                step_id=step_data["step_id"],
                name=step_data["name"],
                node_id=step_data["node_id"],
                parameters=step_data["parameters"],
                compensation_node_id=step_data.get("compensation_node_id"),
                compensation_parameters=step_data.get("compensation_parameters", {}),
            )
            step.state = step_data["state"]
            step.result = step_data.get("result")
            step.error = step_data.get("error")
            step.start_time = step_data.get("start_time")
            step.end_time = step_data.get("end_time")
            self.steps.append(step)

        return {
            "status": "success",
            "saga_id": self.saga_id,
            "saga_name": self.saga_name,
            "state": self.state.value,
            "message": "Saga loaded successfully",
        }

    async def _list_sagas(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """List sagas based on filter criteria."""
        filter_criteria = inputs.get("filter", {})

        saga_ids = await self._state_storage.list_sagas(filter_criteria)

        return {
            "status": "success",
            "saga_ids": saga_ids,
            "count": len(saga_ids),
            "filter": filter_criteria,
        }
