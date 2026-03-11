"""DataFlow Transaction Manager Node - SDK Compliant Implementation."""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.transaction.distributed_transaction_manager import (
    DistributedTransactionManagerNode as SDKTransactionManager,
)
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node()
class DataFlowTransactionManagerNode(AsyncNode):
    """Node for managing distributed transactions in DataFlow operations.

    This node extends AsyncNode and leverages the SDK's DistributedTransactionManagerNode
    to provide enterprise-grade transaction management following SDK patterns.

    Configuration Parameters (set during initialization):
        transaction_type: Type of transaction (saga, two_phase_commit, compensating)
        timeout_seconds: Transaction timeout in seconds
        max_retries: Maximum retry attempts
        isolation_level: Transaction isolation level
        enable_deadlock_detection: Enable deadlock detection
        enable_metrics: Enable transaction metrics

    Runtime Parameters (provided during execution):
        operations: List of operations to execute in transaction
        compensation_actions: Compensation actions for each operation
        context: Transaction context
        commit_strategy: Commit strategy (all_or_nothing, best_effort)
    """

    def __init__(self, **kwargs):
        """Initialize the DataFlowTransactionManagerNode with configuration parameters."""
        # Extract configuration parameters before calling super()
        self.transaction_type = kwargs.pop("transaction_type", "saga")
        self.timeout_seconds = kwargs.pop("timeout_seconds", 30)
        self.max_retries = kwargs.pop("max_retries", 3)
        self.isolation_level = kwargs.pop("isolation_level", "READ_COMMITTED")
        self.enable_deadlock_detection = kwargs.pop("enable_deadlock_detection", True)
        self.enable_metrics = kwargs.pop("enable_metrics", True)

        # Call parent constructor
        super().__init__(**kwargs)

        # Initialize the SDK TransactionManager
        self.transaction_manager = SDKTransactionManager(
            node_id=f"{getattr(self, 'node_id', 'unknown')}_sdk_tm",
            transaction_type=self.transaction_type,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
        )

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the runtime parameters this node accepts."""
        return {
            "operations": NodeParameter(
                name="operations",
                type=list,
                required=True,
                description="List of operations to execute in transaction",
            ),
            "compensation_actions": NodeParameter(
                name="compensation_actions",
                type=dict,
                required=False,
                default={},
                description="Compensation actions for each operation",
                auto_map_from=["compensations", "rollback_actions"],
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Transaction context and metadata",
            ),
            "commit_strategy": NodeParameter(
                name="commit_strategy",
                type=str,
                required=False,
                default="all_or_nothing",
                description="Commit strategy: all_or_nothing, best_effort",
            ),
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute distributed transaction asynchronously."""
        transaction_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        try:
            # Validate and map parameters using SDK validation
            validated_inputs = self.validate_inputs(**kwargs)

            # Extract validated parameters
            operations = validated_inputs.get("operations", [])
            compensation_actions = validated_inputs.get("compensation_actions", {})
            context = validated_inputs.get("context", {})
            commit_strategy = validated_inputs.get("commit_strategy", "all_or_nothing")

            if not operations:
                raise NodeValidationError("No operations provided for transaction")

            # Initialize transaction
            transaction = {
                "id": transaction_id,
                "status": "active",
                "operations": operations,
                "compensation_actions": compensation_actions,
                "context": context,
                "start_time": start_time,
                "completed_operations": [],
                "failed_operations": [],
            }

            # Execute transaction based on type
            if self.transaction_type == "saga":
                result = await self._execute_saga_transaction(transaction)
            elif self.transaction_type == "two_phase_commit":
                result = await self._execute_two_phase_commit(transaction)
            else:
                result = await self._execute_compensating_transaction(transaction)

            # Calculate metrics
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            # Build result following SDK patterns
            result_data = {
                "success": result["success"],
                "transaction_id": transaction_id,
                "transaction_type": self.transaction_type,
                "status": result["status"],
                "operations_completed": len(result.get("completed_operations", [])),
                "operations_failed": len(result.get("failed_operations", [])),
                "operations_total": len(operations),
                "metadata": {
                    "duration_seconds": duration,
                    "isolation_level": self.isolation_level,
                    "commit_strategy": commit_strategy,
                    "deadlock_detected": result.get("deadlock_detected", False),
                    "retries_attempted": result.get("retries", 0),
                },
            }

            # Add operation details
            if result.get("completed_operations"):
                result_data["completed_operations"] = result["completed_operations"]

            if result.get("failed_operations"):
                result_data["failed_operations"] = result["failed_operations"]
                result_data["error_details"] = result.get("error_details", [])

            # Add metrics if enabled
            if self.enable_metrics:
                result_data["metrics"] = {
                    "operation_latencies": result.get("operation_latencies", {}),
                    "total_latency_ms": duration * 1000,
                    "throughput_ops_per_sec": (
                        len(operations) / duration if duration > 0 else 0
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
                "transaction_id": transaction_id,
                "status": "failed",
            }

    async def _execute_saga_transaction(
        self, transaction: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a saga transaction pattern."""
        completed = []
        failed = []
        operation_latencies = {}

        try:
            # Forward phase - execute operations in sequence
            for operation in transaction["operations"]:
                op_start = datetime.utcnow()

                try:
                    # Execute operation
                    result = await self._execute_operation(operation)

                    completed.append(
                        {
                            "operation_id": operation.get("id", str(uuid.uuid4())),
                            "operation_type": operation.get("type"),
                            "result": result,
                        }
                    )

                    op_duration = (datetime.utcnow() - op_start).total_seconds()
                    operation_latencies[operation.get("id", "unknown")] = (
                        op_duration * 1000
                    )

                except Exception as e:
                    # Operation failed - start compensation
                    failed.append(
                        {
                            "operation_id": operation.get("id", str(uuid.uuid4())),
                            "operation_type": operation.get("type"),
                            "error": str(e),
                        }
                    )

                    # Compensate completed operations in reverse order
                    await self._compensate_operations(
                        completed, transaction["compensation_actions"]
                    )

                    return {
                        "success": False,
                        "status": "rolled_back",
                        "completed_operations": [],
                        "failed_operations": failed,
                        "error_details": [str(e)],
                        "operation_latencies": operation_latencies,
                    }

            # All operations completed successfully
            return {
                "success": True,
                "status": "committed",
                "completed_operations": completed,
                "failed_operations": [],
                "operation_latencies": operation_latencies,
            }

        except Exception as e:
            # Unexpected error - attempt compensation
            await self._compensate_operations(
                completed, transaction["compensation_actions"]
            )

            return {
                "success": False,
                "status": "failed",
                "completed_operations": [],
                "failed_operations": failed,
                "error_details": [str(e)],
                "operation_latencies": operation_latencies,
            }

    async def _execute_two_phase_commit(
        self, transaction: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a two-phase commit transaction pattern."""
        prepared = []
        failed = []
        operation_latencies = {}

        try:
            # Phase 1: Prepare all operations
            for operation in transaction["operations"]:
                op_start = datetime.utcnow()

                try:
                    # Prepare operation (acquire locks, validate, etc.)
                    prepare_result = await self._prepare_operation(operation)

                    prepared.append(
                        {
                            "operation_id": operation.get("id", str(uuid.uuid4())),
                            "operation_type": operation.get("type"),
                            "prepare_result": prepare_result,
                        }
                    )

                    op_duration = (datetime.utcnow() - op_start).total_seconds()
                    operation_latencies[operation.get("id", "unknown")] = (
                        op_duration * 1000
                    )

                except Exception as e:
                    # Prepare failed - abort all
                    failed.append(
                        {
                            "operation_id": operation.get("id", str(uuid.uuid4())),
                            "operation_type": operation.get("type"),
                            "error": str(e),
                        }
                    )

                    # Abort prepared operations
                    await self._abort_operations(prepared)

                    return {
                        "success": False,
                        "status": "aborted",
                        "completed_operations": [],
                        "failed_operations": failed,
                        "error_details": [str(e)],
                        "operation_latencies": operation_latencies,
                    }

            # Phase 2: Commit all operations
            committed = []
            for prep_op in prepared:
                try:
                    commit_result = await self._commit_operation(prep_op)
                    committed.append(
                        {
                            "operation_id": prep_op["operation_id"],
                            "operation_type": prep_op["operation_type"],
                            "result": commit_result,
                        }
                    )
                except Exception as e:
                    # Commit failed - this is a serious error
                    # Some operations may be committed, some not
                    return {
                        "success": False,
                        "status": "partial_commit",
                        "completed_operations": committed,
                        "failed_operations": [
                            {"operation_id": prep_op["operation_id"], "error": str(e)}
                        ],
                        "error_details": [
                            f"Partial commit - manual intervention required: {str(e)}"
                        ],
                        "operation_latencies": operation_latencies,
                    }

            # All operations committed successfully
            return {
                "success": True,
                "status": "committed",
                "completed_operations": committed,
                "failed_operations": [],
                "operation_latencies": operation_latencies,
            }

        except Exception as e:
            # Unexpected error - abort all
            await self._abort_operations(prepared)

            return {
                "success": False,
                "status": "failed",
                "completed_operations": [],
                "failed_operations": failed,
                "error_details": [str(e)],
                "operation_latencies": operation_latencies,
            }

    async def _execute_compensating_transaction(
        self, transaction: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a compensating transaction pattern."""
        # Similar to saga but with explicit compensation tracking
        return await self._execute_saga_transaction(transaction)

    async def _execute_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single operation."""
        # Use SDK transaction manager to execute
        return await self.transaction_manager.execute_operation(operation)

    async def _prepare_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare an operation for two-phase commit."""
        # Use SDK transaction manager to prepare
        return await self.transaction_manager.prepare_operation(operation)

    async def _commit_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Commit a prepared operation."""
        # Use SDK transaction manager to commit
        return await self.transaction_manager.commit_operation(operation)

    async def _abort_operations(self, operations: List[Dict[str, Any]]) -> None:
        """Abort prepared operations."""
        for operation in operations:
            try:
                await self.transaction_manager.abort_operation(operation)
            except Exception:
                # Log but continue aborting others
                pass

    async def _compensate_operations(
        self,
        completed_operations: List[Dict[str, Any]],
        compensation_actions: Dict[str, Any],
    ) -> None:
        """Execute compensation actions for completed operations."""
        # Execute compensations in reverse order
        for operation in reversed(completed_operations):
            op_id = operation["operation_id"]
            if op_id in compensation_actions:
                try:
                    compensation = compensation_actions[op_id]
                    await self.transaction_manager.execute_compensation(compensation)
                except Exception:
                    # Log but continue compensating others
                    pass
