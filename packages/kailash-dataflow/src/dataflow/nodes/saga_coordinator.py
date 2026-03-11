"""DataFlow Saga Coordinator Node - SDK Compliant Implementation."""

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.transaction.saga_coordinator import (
    SagaCoordinatorNode as SDKSagaCoordinator,
)
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class SagaState(Enum):
    """Saga execution states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPENSATING = "compensating"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"


@register_node()
class DataFlowSagaCoordinatorNode(AsyncNode):
    """Node for coordinating saga transactions in DataFlow operations.

    This node extends AsyncNode and leverages the SDK's SagaCoordinatorNode
    to provide enterprise-grade saga pattern implementation following SDK patterns.

    Configuration Parameters (set during initialization):
        compensation_strategy: Strategy for compensation (sequential, parallel, smart)
        timeout_seconds: Saga timeout in seconds
        max_retries: Maximum retry attempts per step
        enable_partial_rollback: Allow partial rollback on failure
        enable_step_retries: Enable automatic step retries
        enable_compensation_retries: Enable compensation retries

    Runtime Parameters (provided during execution):
        saga_definition: Definition of saga steps and compensations
        initial_context: Initial context for saga execution
        checkpoint_enabled: Enable checkpointing for recovery
        async_compensation: Execute compensations asynchronously
    """

    def __init__(self, **kwargs):
        """Initialize the DataFlowSagaCoordinatorNode with configuration parameters."""
        # Extract configuration parameters before calling super()
        self.compensation_strategy = kwargs.pop("compensation_strategy", "sequential")
        self.timeout_seconds = kwargs.pop("timeout_seconds", 300)
        self.max_retries = kwargs.pop("max_retries", 3)
        self.enable_partial_rollback = kwargs.pop("enable_partial_rollback", False)
        self.enable_step_retries = kwargs.pop("enable_step_retries", True)
        self.enable_compensation_retries = kwargs.pop(
            "enable_compensation_retries", True
        )

        # Call parent constructor
        super().__init__(**kwargs)

        # Initialize the SDK SagaCoordinator
        self.saga_coordinator = SDKSagaCoordinator(
            node_id=f"{self.node_id}_sdk_saga",
            compensation_strategy=self.compensation_strategy,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
        )

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the runtime parameters this node accepts."""
        return {
            "saga_definition": NodeParameter(
                name="saga_definition",
                type=dict,
                required=True,
                description="Definition of saga steps and compensations",
            ),
            "initial_context": NodeParameter(
                name="initial_context",
                type=dict,
                required=False,
                default={},
                description="Initial context for saga execution",
                auto_map_from=["context", "saga_context"],
            ),
            "checkpoint_enabled": NodeParameter(
                name="checkpoint_enabled",
                type=bool,
                required=False,
                default=True,
                description="Enable checkpointing for recovery",
            ),
            "async_compensation": NodeParameter(
                name="async_compensation",
                type=bool,
                required=False,
                default=False,
                description="Execute compensations asynchronously",
            ),
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute saga transaction asynchronously."""
        saga_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        try:
            # Validate and map parameters using SDK validation
            validated_inputs = self.validate_inputs(**kwargs)

            # Extract validated parameters
            saga_definition = validated_inputs.get("saga_definition", {})
            initial_context = validated_inputs.get("initial_context", {})
            checkpoint_enabled = validated_inputs.get("checkpoint_enabled", True)
            async_compensation = validated_inputs.get("async_compensation", False)

            # Validate saga definition
            validation_result = self._validate_saga_definition(saga_definition)
            if not validation_result["valid"]:
                raise NodeValidationError(
                    f"Invalid saga definition: {validation_result['errors']}"
                )

            # Initialize saga state
            saga_state = {
                "id": saga_id,
                "state": SagaState.RUNNING,
                "definition": saga_definition,
                "context": initial_context.copy(),
                "completed_steps": [],
                "failed_step": None,
                "compensated_steps": [],
                "checkpoints": [],
                "start_time": start_time,
            }

            # Execute saga
            result = await self._execute_saga(
                saga_state, checkpoint_enabled, async_compensation
            )

            # Calculate metrics
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            # Build result following SDK patterns
            result_data = {
                "success": result["success"],
                "saga_id": saga_id,
                "final_state": result["state"].value,
                "steps_completed": len(result.get("completed_steps", [])),
                "steps_compensated": len(result.get("compensated_steps", [])),
                "steps_total": len(saga_definition.get("steps", [])),
                "final_context": result.get("context", {}),
                "metadata": {
                    "duration_seconds": duration,
                    "compensation_strategy": self.compensation_strategy,
                    "checkpoints_created": len(result.get("checkpoints", [])),
                    "retries_used": result.get("total_retries", 0),
                },
            }

            # Add step details
            if result.get("completed_steps"):
                result_data["completed_steps"] = result["completed_steps"]

            if result.get("failed_step"):
                result_data["failed_step"] = result["failed_step"]
                result_data["failure_reason"] = result.get("failure_reason")

            if result.get("compensated_steps"):
                result_data["compensated_steps"] = result["compensated_steps"]

            # Add performance metrics
            result_data["performance_metrics"] = {
                "step_latencies": result.get("step_latencies", {}),
                "compensation_latencies": result.get("compensation_latencies", {}),
                "total_latency_ms": duration * 1000,
                "avg_step_latency_ms": self._calculate_avg_latency(
                    result.get("step_latencies", {})
                ),
            }

            return result_data

        except (ValueError, NodeValidationError):
            # Let validation errors propagate for proper test handling
            raise
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "saga_id": saga_id,
                "final_state": SagaState.FAILED.value,
            }

    def _validate_saga_definition(
        self, saga_definition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate saga definition structure."""
        errors = []

        if not saga_definition:
            errors.append("Saga definition is empty")
            return {"valid": False, "errors": errors}

        if "steps" not in saga_definition:
            errors.append("Saga definition must contain 'steps'")
        else:
            steps = saga_definition["steps"]
            if not isinstance(steps, list) or len(steps) == 0:
                errors.append("Steps must be a non-empty list")
            else:
                # Validate each step
                for i, step in enumerate(steps):
                    if not isinstance(step, dict):
                        errors.append(f"Step {i} must be a dictionary")
                        continue

                    if "name" not in step:
                        errors.append(f"Step {i} missing required field 'name'")

                    if "action" not in step:
                        errors.append(f"Step {i} missing required field 'action'")

                    if (
                        "compensation" not in step
                        and self.compensation_strategy != "none"
                    ):
                        errors.append(f"Step {i} missing compensation action")

        return {"valid": len(errors) == 0, "errors": errors}

    async def _execute_saga(
        self,
        saga_state: Dict[str, Any],
        checkpoint_enabled: bool,
        async_compensation: bool,
    ) -> Dict[str, Any]:
        """Execute the saga transaction."""
        step_latencies = {}
        compensation_latencies = {}
        total_retries = 0

        try:
            # Execute steps sequentially
            for step in saga_state["definition"]["steps"]:
                step_start = datetime.utcnow()
                step_id = step.get("id", step["name"])

                # Create checkpoint if enabled
                if checkpoint_enabled:
                    await self._create_checkpoint(saga_state)

                # Execute step with retries
                step_result = None
                for retry in range(self.max_retries):
                    try:
                        step_result = await self._execute_step(
                            step, saga_state["context"]
                        )
                        break
                    except Exception as e:
                        total_retries += 1
                        if retry == self.max_retries - 1:
                            # Final retry failed
                            saga_state["failed_step"] = {
                                "id": step_id,
                                "name": step["name"],
                                "error": str(e),
                                "retries": retry + 1,
                            }
                            saga_state["state"] = SagaState.COMPENSATING

                            # Start compensation
                            await self._compensate_saga(
                                saga_state, async_compensation, compensation_latencies
                            )

                            return {
                                "success": False,
                                "state": saga_state["state"],
                                "completed_steps": saga_state["completed_steps"],
                                "failed_step": saga_state["failed_step"],
                                "compensated_steps": saga_state["compensated_steps"],
                                "failure_reason": str(e),
                                "context": saga_state["context"],
                                "step_latencies": step_latencies,
                                "compensation_latencies": compensation_latencies,
                                "total_retries": total_retries,
                                "checkpoints": saga_state["checkpoints"],
                            }

                        # Retry with exponential backoff
                        await asyncio.sleep(2**retry)

                # Step completed successfully
                saga_state["completed_steps"].append(
                    {"id": step_id, "name": step["name"], "result": step_result}
                )

                # Update context with step result
                if isinstance(step_result, dict) and "context_updates" in step_result:
                    saga_state["context"].update(step_result["context_updates"])

                # Record latency
                step_duration = (datetime.utcnow() - step_start).total_seconds()
                step_latencies[step_id] = step_duration * 1000

            # All steps completed successfully
            saga_state["state"] = SagaState.COMPLETED

            return {
                "success": True,
                "state": saga_state["state"],
                "completed_steps": saga_state["completed_steps"],
                "compensated_steps": [],
                "context": saga_state["context"],
                "step_latencies": step_latencies,
                "compensation_latencies": compensation_latencies,
                "total_retries": total_retries,
                "checkpoints": saga_state["checkpoints"],
            }

        except Exception as e:
            # Unexpected error - compensate
            saga_state["state"] = SagaState.FAILED
            await self._compensate_saga(
                saga_state, async_compensation, compensation_latencies
            )

            return {
                "success": False,
                "state": saga_state["state"],
                "completed_steps": saga_state["completed_steps"],
                "compensated_steps": saga_state["compensated_steps"],
                "failure_reason": str(e),
                "context": saga_state["context"],
                "step_latencies": step_latencies,
                "compensation_latencies": compensation_latencies,
                "total_retries": total_retries,
                "checkpoints": saga_state["checkpoints"],
            }

    async def _execute_step(
        self, step: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single saga step."""
        # Use SDK saga coordinator to execute step
        return await self.saga_coordinator.execute_step(step, context)

    async def _compensate_saga(
        self,
        saga_state: Dict[str, Any],
        async_compensation: bool,
        compensation_latencies: Dict[str, float],
    ) -> None:
        """Execute compensation for completed steps."""
        if self.compensation_strategy == "none":
            return

        # Get steps to compensate
        steps_to_compensate = []
        for completed_step in reversed(saga_state["completed_steps"]):
            step_def = next(
                (
                    s
                    for s in saga_state["definition"]["steps"]
                    if s.get("id", s["name"]) == completed_step["id"]
                ),
                None,
            )
            if step_def and "compensation" in step_def:
                steps_to_compensate.append((completed_step, step_def["compensation"]))

        if async_compensation and self.compensation_strategy == "parallel":
            # Execute compensations in parallel
            compensation_tasks = []
            for completed_step, compensation in steps_to_compensate:
                task = self._compensate_step_async(
                    completed_step, compensation, saga_state, compensation_latencies
                )
                compensation_tasks.append(task)

            await asyncio.gather(*compensation_tasks, return_exceptions=True)
        else:
            # Execute compensations sequentially
            for completed_step, compensation in steps_to_compensate:
                await self._compensate_step(
                    completed_step, compensation, saga_state, compensation_latencies
                )

        saga_state["state"] = SagaState.COMPENSATED

    async def _compensate_step(
        self,
        step: Dict[str, Any],
        compensation: Dict[str, Any],
        saga_state: Dict[str, Any],
        latencies: Dict[str, float],
    ) -> None:
        """Compensate a single step."""
        comp_start = datetime.utcnow()
        step_id = step["id"]

        for retry in range(self.max_retries if self.enable_compensation_retries else 1):
            try:
                # Execute compensation
                await self.saga_coordinator.execute_compensation(
                    compensation, saga_state["context"]
                )

                # Record successful compensation
                saga_state["compensated_steps"].append(
                    {
                        "id": step_id,
                        "name": step["name"],
                        "compensated_at": datetime.utcnow().isoformat(),
                    }
                )

                # Record latency
                comp_duration = (datetime.utcnow() - comp_start).total_seconds()
                latencies[f"{step_id}_compensation"] = comp_duration * 1000

                break
            except Exception:
                if retry == self.max_retries - 1:
                    # Log but continue with other compensations
                    saga_state["compensated_steps"].append(
                        {
                            "id": step_id,
                            "name": step["name"],
                            "compensation_failed": True,
                        }
                    )

                # Retry with backoff
                await asyncio.sleep(2**retry)

    async def _compensate_step_async(
        self,
        step: Dict[str, Any],
        compensation: Dict[str, Any],
        saga_state: Dict[str, Any],
        latencies: Dict[str, float],
    ) -> None:
        """Async wrapper for step compensation."""
        await self._compensate_step(step, compensation, saga_state, latencies)

    async def _create_checkpoint(self, saga_state: Dict[str, Any]) -> None:
        """Create a checkpoint for saga recovery."""
        checkpoint = {
            "timestamp": datetime.utcnow().isoformat(),
            "completed_steps": len(saga_state["completed_steps"]),
            "context_snapshot": saga_state["context"].copy(),
        }
        saga_state["checkpoints"].append(checkpoint)

    def _calculate_avg_latency(self, latencies: Dict[str, float]) -> float:
        """Calculate average latency from latency dictionary."""
        if not latencies:
            return 0.0
        return sum(latencies.values()) / len(latencies)
