"""Transaction Context Node for workflow-level transaction coordination.

This module provides a context manager node that enables transparent transaction
management across workflow executions. It automatically manages transaction
lifecycles, participant registration, and pattern selection for entire workflows.

The TransactionContextNode:
1. Provides transparent transaction boundaries for workflows
2. Automatically registers workflow nodes as transaction participants
3. Manages distributed transaction coordination across workflow steps
4. Handles automatic compensation and recovery for failed workflows
5. Integrates with monitoring and metrics collection

Examples:
    Basic workflow transaction:

    >>> context = TransactionContextNode(
    ...     transaction_name="user_onboarding",
    ...     consistency="eventual",
    ...     availability="high"
    ... )
    >>> result = await context.execute(
    ...     operation="begin_workflow_transaction",
    ...     workflow_nodes=[
    ...         {"id": "create_user", "type": "UserCreateNode"},
    ...         {"id": "send_welcome", "type": "EmailNode"},
    ...         {"id": "setup_profile", "type": "ProfileSetupNode"}
    ...     ]
    ... )

    DataFlow integration:

    >>> # Automatically wrap DataFlow operations in transactions
    >>> context = TransactionContextNode(
    ...     auto_wrap_bulk_operations=True,
    ...     default_pattern="saga",
    ...     monitoring_enabled=True
    ... )
    >>> result = await context.execute(
    ...     operation="wrap_bulk_operation",
    ...     bulk_node="ProductBulkCreateNode",
    ...     compensation_node="ProductBulkDeleteNode"
    ... )

    Enterprise configuration:

    >>> context = TransactionContextNode(
    ...     transaction_name="order_processing",
    ...     pattern="auto",
    ...     requirements={
    ...         "consistency": "strong",
    ...         "availability": "medium",
    ...         "timeout": 600
    ...     },
    ...     monitoring_enabled=True,
    ...     audit_logging=True
    ... )
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from kailash.nodes.base import NodeMetadata, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError

from .distributed_transaction_manager import (
    AvailabilityLevel,
    ConsistencyLevel,
    DistributedTransactionManagerNode,
    ParticipantCapability,
    TransactionPattern,
    TransactionRequirements,
)

logger = logging.getLogger(__name__)


class WorkflowTransactionStatus(Enum):
    """Workflow transaction status."""

    PENDING = "pending"
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    COMPENSATED = "compensated"
    FAILED = "failed"


class ParticipantType(Enum):
    """Types of transaction participants."""

    WORKFLOW_NODE = "workflow_node"
    BULK_OPERATION = "bulk_operation"
    EXTERNAL_SERVICE = "external_service"
    DATABASE_OPERATION = "database_operation"


class WorkflowParticipant:
    """Represents a workflow participant in a transaction."""

    def __init__(
        self,
        participant_id: str,
        node_type: str,
        participant_type: ParticipantType = ParticipantType.WORKFLOW_NODE,
        supports_2pc: bool = False,
        supports_saga: bool = True,
        compensation_node: Optional[str] = None,
        compensation_parameters: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        retry_count: int = 3,
        priority: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.participant_id = participant_id
        self.node_type = node_type
        self.participant_type = participant_type
        self.supports_2pc = supports_2pc
        self.supports_saga = supports_saga
        self.compensation_node = compensation_node
        self.compensation_parameters = compensation_parameters or {}
        self.timeout = timeout
        self.retry_count = retry_count
        self.priority = priority
        self.metadata = metadata or {}

        # Auto-detect capabilities based on node type
        self._detect_capabilities()

    def _detect_capabilities(self):
        """Auto-detect transaction capabilities based on node type."""
        # Database operations typically support 2PC
        if any(
            db_keyword in self.node_type.lower()
            for db_keyword in ["sql", "database", "bulk", "create", "update", "delete"]
        ):
            self.supports_2pc = True

        # External services typically only support saga
        if any(
            ext_keyword in self.node_type.lower()
            for ext_keyword in ["http", "rest", "api", "email", "notification"]
        ):
            self.supports_2pc = False

        # Bulk operations need special handling
        if "bulk" in self.node_type.lower():
            self.participant_type = ParticipantType.BULK_OPERATION

    def to_participant_capability(self) -> ParticipantCapability:
        """Convert to ParticipantCapability for DTM."""
        return ParticipantCapability(
            participant_id=self.participant_id,
            endpoint=f"workflow://{self.participant_id}",
            supports_2pc=self.supports_2pc,
            supports_saga=self.supports_saga,
            compensation_action=self.compensation_node,
            timeout=self.timeout,
            retry_count=self.retry_count,
            priority=self.priority,
        )


@register_node("TransactionContextNode")
class TransactionContextNode(AsyncNode):
    """Workflow-level transaction coordination node.

    This node provides transparent transaction management for entire workflows,
    automatically managing transaction lifecycles, participant registration,
    and distributed coordination across workflow steps.

    Key Features:
    - Automatic workflow transaction boundaries
    - Transparent participant registration
    - Intelligent compensation logic
    - DataFlow integration support
    - Monitoring and metrics integration
    - Enterprise-grade configuration

    Operations:
    - begin_workflow_transaction: Start transaction for workflow
    - register_participant: Register workflow node as participant
    - wrap_bulk_operation: Wrap bulk operations in transactions
    - execute_workflow_step: Execute single workflow step with transaction
    - commit_workflow: Commit workflow transaction
    - rollback_workflow: Rollback workflow transaction
    - get_workflow_status: Get workflow transaction status
    """

    def __init__(
        self,
        transaction_name: str = None,
        context_id: str = None,
        pattern: Union[TransactionPattern, str] = TransactionPattern.AUTO,
        requirements: Optional[Dict[str, Any]] = None,
        auto_wrap_bulk_operations: bool = True,
        monitoring_enabled: bool = True,
        audit_logging: bool = False,
        state_storage: str = "memory",
        storage_config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Initialize Transaction Context Node.

        Args:
            transaction_name: Human-readable transaction name
            context_id: Unique context identifier
            pattern: Transaction pattern (saga, two_phase_commit, auto)
            requirements: Transaction requirements for pattern selection
            auto_wrap_bulk_operations: Automatically wrap bulk operations
            monitoring_enabled: Enable transaction monitoring
            audit_logging: Enable audit logging
            state_storage: Storage backend for transaction state
            storage_config: Configuration for state storage
            **kwargs: Additional node configuration
        """
        # Set node metadata
        metadata = NodeMetadata(
            name=kwargs.get("name", "transaction_context"),
            description="Workflow-level transaction coordination with automatic participant management",
            version="1.0.0",
            tags={"transaction", "workflow", "context", "coordination"},
        )

        # Initialize AsyncNode
        super().__init__(metadata=metadata, **kwargs)

        # Context configuration
        self.transaction_name = transaction_name or f"workflow_tx_{int(time.time())}"
        self.context_id = context_id or str(uuid.uuid4())
        self.pattern = (
            TransactionPattern(pattern) if isinstance(pattern, str) else pattern
        )
        self.auto_wrap_bulk_operations = auto_wrap_bulk_operations
        self.monitoring_enabled = monitoring_enabled
        self.audit_logging = audit_logging

        # Transaction requirements
        if requirements:
            self.requirements = TransactionRequirements(**requirements)
        else:
            self.requirements = TransactionRequirements()

        # State
        self.status = WorkflowTransactionStatus.PENDING
        self.participants: List[WorkflowParticipant] = []
        self.workflow_context: Dict[str, Any] = {}
        self.execution_order: List[str] = []
        self.created_at: Optional[datetime] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None

        # Distributed transaction manager
        self.dtm = DistributedTransactionManagerNode(
            transaction_name=self.transaction_name,
            transaction_id=self.context_id,
            default_pattern=self.pattern,
            state_storage=state_storage,
            storage_config=storage_config or {},
            monitoring_enabled=monitoring_enabled,
            audit_logging=audit_logging,
        )

        # Monitoring
        self._metrics_node = None
        if monitoring_enabled:
            self._init_monitoring()

        logger.info(f"Initialized TransactionContextNode: {self.context_id}")

    def _init_monitoring(self):
        """Initialize transaction monitoring."""
        try:
            from kailash.nodes.monitoring.transaction_metrics import (
                TransactionMetricsNode,
            )

            self._metrics_node = TransactionMetricsNode()
        except ImportError:
            logger.warning("TransactionMetricsNode not available, monitoring disabled")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters for validation."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Transaction context operation to execute",
            ),
            "workflow_nodes": NodeParameter(
                name="workflow_nodes",
                type=list,
                required=False,
                description="List of workflow nodes to register as participants",
            ),
            "participant": NodeParameter(
                name="participant",
                type=dict,
                required=False,
                description="Single participant to register",
            ),
            "bulk_node": NodeParameter(
                name="bulk_node",
                type=str,
                required=False,
                description="Bulk operation node to wrap in transaction",
            ),
            "compensation_node": NodeParameter(
                name="compensation_node",
                type=str,
                required=False,
                description="Compensation node for bulk operation",
            ),
            "step_id": NodeParameter(
                name="step_id",
                type=str,
                required=False,
                description="Workflow step identifier",
            ),
            "step_parameters": NodeParameter(
                name="step_parameters",
                type=dict,
                required=False,
                description="Parameters for workflow step execution",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                description="Workflow context data",
            ),
            "force_pattern": NodeParameter(
                name="force_pattern",
                type=str,
                required=False,
                description="Force specific transaction pattern",
            ),
        }

    def get_outputs(self) -> Dict[str, NodeParameter]:
        """Get node outputs."""
        return {
            "status": NodeParameter(
                name="status",
                type=str,
                required=True,
                description="Operation status",
            ),
            "context_id": NodeParameter(
                name="context_id",
                type=str,
                required=True,
                description="Transaction context identifier",
            ),
            "workflow_status": NodeParameter(
                name="workflow_status",
                type=str,
                required=True,
                description="Workflow transaction status",
            ),
            "participants": NodeParameter(
                name="participants",
                type=list,
                required=False,
                description="List of registered participants",
            ),
            "selected_pattern": NodeParameter(
                name="selected_pattern",
                type=str,
                required=False,
                description="Selected transaction pattern",
            ),
            "result": NodeParameter(
                name="result",
                type=dict,
                required=False,
                description="Operation result data",
            ),
            "error": NodeParameter(
                name="error",
                type=str,
                required=False,
                description="Error message if operation failed",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute transaction context operation."""
        operation = kwargs.get("operation")

        try:
            if operation == "begin_workflow_transaction":
                return await self._begin_workflow_transaction(**kwargs)
            elif operation == "register_participant":
                return await self._register_participant(**kwargs)
            elif operation == "wrap_bulk_operation":
                return await self._wrap_bulk_operation(**kwargs)
            elif operation == "execute_workflow_step":
                return await self._execute_workflow_step(**kwargs)
            elif operation == "commit_workflow":
                return await self._commit_workflow(**kwargs)
            elif operation == "rollback_workflow":
                return await self._rollback_workflow(**kwargs)
            elif operation == "get_workflow_status":
                return await self._get_workflow_status(**kwargs)
            else:
                raise NodeExecutionError(f"Unknown operation: {operation}")

        except Exception as e:
            logger.error(f"Transaction context operation failed: {e}")
            self.error_message = str(e)
            await self._record_error(str(e))
            return {
                "status": "error",
                "context_id": self.context_id,
                "workflow_status": self.status.value,
                "error": str(e),
            }

    async def _begin_workflow_transaction(self, **kwargs) -> Dict[str, Any]:
        """Begin a workflow transaction."""
        if self.status != WorkflowTransactionStatus.PENDING:
            raise NodeExecutionError(f"Transaction already {self.status.value}")

        # Update context
        context = kwargs.get("context", {})
        self.workflow_context.update(context)

        # Register workflow nodes as participants
        workflow_nodes = kwargs.get("workflow_nodes", [])
        for node_info in workflow_nodes:
            participant = WorkflowParticipant(
                participant_id=node_info["id"],
                node_type=node_info["type"],
                compensation_node=node_info.get("compensation_node"),
                compensation_parameters=node_info.get("compensation_parameters"),
                priority=node_info.get("priority", 1),
                metadata=node_info.get("metadata", {}),
            )
            self.participants.append(participant)

        # Create transaction with DTM
        dtm_result = await self.dtm.async_run(
            operation="create_transaction",
            transaction_name=self.transaction_name,
            requirements=self.requirements.__dict__,
            context=self.workflow_context,
        )

        if dtm_result.get("status") != "success":
            raise NodeExecutionError(
                f"Failed to create transaction: {dtm_result.get('error')}"
            )

        # Register participants with DTM
        for participant in self.participants:
            capability = participant.to_participant_capability()
            await self.dtm.async_run(
                operation="add_participant", participant=capability.to_dict()
            )

        # Update status
        self.status = WorkflowTransactionStatus.ACTIVE
        self.created_at = datetime.now(UTC)

        # Start monitoring
        if self._metrics_node:
            await self._metrics_node.async_run(
                operation="start_transaction",
                transaction_id=self.context_id,
                name=self.transaction_name,
                tags={"type": "workflow_transaction"},
            )

        logger.info(f"Started workflow transaction: {self.context_id}")

        return {
            "status": "success",
            "context_id": self.context_id,
            "workflow_status": self.status.value,
            "participants": len(self.participants),
            "created_at": self.created_at.isoformat(),
        }

    async def _register_participant(self, **kwargs) -> Dict[str, Any]:
        """Register a single participant."""
        participant_info = kwargs.get("participant")
        if not participant_info:
            raise NodeExecutionError("participant information required")

        participant = WorkflowParticipant(
            participant_id=participant_info["id"],
            node_type=participant_info["type"],
            compensation_node=participant_info.get("compensation_node"),
            compensation_parameters=participant_info.get("compensation_parameters"),
            priority=participant_info.get("priority", 1),
            metadata=participant_info.get("metadata", {}),
        )

        # Add to participants list
        self.participants.append(participant)

        # Register with DTM
        capability = participant.to_participant_capability()
        dtm_result = await self.dtm.async_run(
            operation="add_participant", participant=capability.to_dict()
        )

        if dtm_result.get("status") != "success":
            raise NodeExecutionError(
                f"Failed to register participant: {dtm_result.get('error')}"
            )

        return {
            "status": "success",
            "context_id": self.context_id,
            "workflow_status": self.status.value,
            "participant_id": participant.participant_id,
            "total_participants": len(self.participants),
        }

    async def _wrap_bulk_operation(self, **kwargs) -> Dict[str, Any]:
        """Wrap a bulk operation in a transaction."""
        bulk_node = kwargs.get("bulk_node")
        if not bulk_node:
            raise NodeExecutionError("bulk_node required for wrap_bulk_operation")

        compensation_node = kwargs.get("compensation_node")

        # Create participant for bulk operation
        participant = WorkflowParticipant(
            participant_id=f"bulk_{bulk_node}_{int(time.time())}",
            node_type=bulk_node,
            participant_type=ParticipantType.BULK_OPERATION,
            compensation_node=compensation_node,
            supports_2pc=True,  # Bulk operations support 2PC
            supports_saga=True,
            priority=1,
        )

        # Register participant
        self.participants.append(participant)

        # Register with DTM if transaction is active
        if self.status == WorkflowTransactionStatus.ACTIVE:
            capability = participant.to_participant_capability()
            await self.dtm.async_run(
                operation="add_participant", participant=capability.to_dict()
            )

        return {
            "status": "success",
            "context_id": self.context_id,
            "workflow_status": self.status.value,
            "participant_id": participant.participant_id,
            "wrapped_operation": bulk_node,
            "compensation_node": compensation_node,
        }

    async def _execute_workflow_step(self, **kwargs) -> Dict[str, Any]:
        """Execute a single workflow step within transaction."""
        step_id = kwargs.get("step_id")
        if not step_id:
            raise NodeExecutionError("step_id required for execute_workflow_step")

        step_parameters = kwargs.get("step_parameters", {})

        # Find participant
        participant = None
        for p in self.participants:
            if p.participant_id == step_id:
                participant = p
                break

        if not participant:
            raise NodeExecutionError(f"Participant {step_id} not found")

        # Record step execution order
        self.execution_order.append(step_id)

        # For now, this is a placeholder - in full implementation,
        # this would integrate with the workflow execution engine
        # to actually execute the step

        return {
            "status": "success",
            "context_id": self.context_id,
            "workflow_status": self.status.value,
            "step_id": step_id,
            "execution_order": self.execution_order,
        }

    async def _commit_workflow(self, **kwargs) -> Dict[str, Any]:
        """Commit the workflow transaction."""
        if self.status != WorkflowTransactionStatus.ACTIVE:
            raise NodeExecutionError(
                f"Cannot commit transaction in status: {self.status.value}"
            )

        # Force pattern if specified
        force_pattern = kwargs.get("force_pattern")
        if force_pattern:
            self.pattern = TransactionPattern(force_pattern)

        # Execute transaction with DTM
        dtm_result = await self.dtm.async_run(
            operation="execute_transaction",
            pattern=(
                self.pattern.value
                if self.pattern != TransactionPattern.AUTO
                else "auto"
            ),
        )

        # Update status based on result
        if dtm_result.get("status") == "success":
            transaction_status = dtm_result.get("transaction_status", "committed")
            if transaction_status == "committed":
                self.status = WorkflowTransactionStatus.COMMITTED
            elif transaction_status == "compensated":
                self.status = WorkflowTransactionStatus.COMPENSATED
            else:
                self.status = WorkflowTransactionStatus.COMMITTED
        else:
            self.status = WorkflowTransactionStatus.FAILED
            self.error_message = dtm_result.get("error", "Transaction execution failed")

        self.completed_at = datetime.now(UTC)

        # End monitoring
        if self._metrics_node:
            await self._metrics_node.async_run(
                operation="end_transaction",
                transaction_id=self.context_id,
                status=(
                    "success"
                    if self.status == WorkflowTransactionStatus.COMMITTED
                    else "error"
                ),
                error=self.error_message,
            )

        logger.info(
            f"Workflow transaction {self.context_id} completed with status: {self.status.value}"
        )

        return {
            "status": (
                "success"
                if self.status == WorkflowTransactionStatus.COMMITTED
                else "failed"
            ),
            "context_id": self.context_id,
            "workflow_status": self.status.value,
            "selected_pattern": dtm_result.get("selected_pattern"),
            "participants": len(self.participants),
            "execution_time": (
                (self.completed_at - self.created_at).total_seconds()
                if self.created_at
                else 0
            ),
            "result": dtm_result.get("result"),
            "error": self.error_message,
        }

    async def _rollback_workflow(self, **kwargs) -> Dict[str, Any]:
        """Rollback the workflow transaction."""
        if self.status not in [
            WorkflowTransactionStatus.ACTIVE,
            WorkflowTransactionStatus.FAILED,
        ]:
            return {
                "status": "already_finished",
                "context_id": self.context_id,
                "workflow_status": self.status.value,
            }

        # Abort transaction with DTM
        dtm_result = await self.dtm.async_run(operation="abort_transaction")

        self.status = WorkflowTransactionStatus.ROLLED_BACK
        self.completed_at = datetime.now(UTC)

        # End monitoring
        if self._metrics_node:
            await self._metrics_node.async_run(
                operation="end_transaction",
                transaction_id=self.context_id,
                status="aborted",
            )

        logger.info(f"Workflow transaction {self.context_id} rolled back")

        return {
            "status": "success",
            "context_id": self.context_id,
            "workflow_status": self.status.value,
            "rolled_back_at": self.completed_at.isoformat(),
        }

    async def _get_workflow_status(self, **kwargs) -> Dict[str, Any]:
        """Get current workflow transaction status."""
        # Get DTM status
        dtm_status = await self.dtm.async_run(operation="get_status")

        participant_info = [
            {
                "id": p.participant_id,
                "type": p.node_type,
                "participant_type": p.participant_type.value,
                "supports_2pc": p.supports_2pc,
                "supports_saga": p.supports_saga,
                "compensation_node": p.compensation_node,
                "priority": p.priority,
                "metadata": p.metadata,
            }
            for p in self.participants
        ]

        return {
            "status": "success",
            "context_id": self.context_id,
            "transaction_name": self.transaction_name,
            "workflow_status": self.status.value,
            "participants": participant_info,
            "execution_order": self.execution_order,
            "workflow_context": self.workflow_context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "dtm_status": dtm_status,
            "error": self.error_message,
        }

    async def _record_error(self, error: str):
        """Record error for monitoring."""
        if self._metrics_node:
            try:
                await self._metrics_node.async_run(
                    operation="end_transaction",
                    transaction_id=self.context_id,
                    status="error",
                    error=error,
                )
            except Exception as e:
                logger.warning(f"Failed to record error in metrics: {e}")
