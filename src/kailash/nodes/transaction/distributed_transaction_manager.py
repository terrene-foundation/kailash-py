"""Distributed Transaction Manager for orchestrating different transaction patterns.

This module provides a high-level manager that can automatically choose between
different distributed transaction patterns (Saga, Two-Phase Commit) based on
transaction requirements and participant capabilities.

The Distributed Transaction Manager:
1. Analyzes transaction requirements and participant capabilities
2. Selects the appropriate transaction pattern (Saga vs 2PC)
3. Orchestrates the chosen pattern with optimal configuration
4. Provides unified monitoring and recovery across all patterns
5. Manages transaction lifecycle and resource cleanup

Examples:
    Automatic pattern selection:

    >>> manager = DistributedTransactionManager()
    >>> result = manager.execute(
    ...     transaction_name="order_processing",
    ...     participants=[
    ...         {"id": "payment", "supports_2pc": True, "compensation": "refund"},
    ...         {"id": "inventory", "supports_2pc": True, "compensation": "release"},
    ...         {"id": "shipping", "supports_2pc": False, "compensation": "cancel"}
    ...     ],
    ...     requirements={"consistency": "strong", "availability": "high"}
    ... )
    # Automatically selects Saga due to shipping service not supporting 2PC

    Explicit pattern selection:

    >>> manager = DistributedTransactionManager()
    >>> result = manager.execute(
    ...     transaction_name="financial_transfer",
    ...     pattern="two_phase_commit",  # Force 2PC for strong consistency
    ...     participants=[...],
    ...     context={"amount": 10000.00, "currency": "USD"}
    ... )

    Enterprise configuration:

    >>> manager = DistributedTransactionManager(
    ...     default_timeout=300,
    ...     retry_policy={"max_attempts": 3, "backoff": "exponential"},
    ...     monitoring=True,
    ...     audit_logging=True,
    ...     state_storage="database"
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

logger = logging.getLogger(__name__)


class TransactionPattern(Enum):
    """Available distributed transaction patterns."""

    SAGA = "saga"
    TWO_PHASE_COMMIT = "two_phase_commit"
    AUTO = "auto"  # Automatic selection based on requirements


class ConsistencyLevel(Enum):
    """Transaction consistency requirements."""

    EVENTUAL = "eventual"  # Saga pattern suitable
    STRONG = "strong"  # 2PC preferred
    IMMEDIATE = "immediate"  # 2PC required


class AvailabilityLevel(Enum):
    """Transaction availability requirements."""

    HIGH = "high"  # Saga pattern preferred
    MEDIUM = "medium"  # Either pattern acceptable
    LOW = "low"  # 2PC acceptable


class TransactionStatus(Enum):
    """Overall transaction status."""

    PENDING = "pending"
    RUNNING = "running"
    COMMITTED = "committed"
    ABORTED = "aborted"
    COMPENSATED = "compensated"
    FAILED = "failed"
    RECOVERING = "recovering"


class ParticipantCapability:
    """Represents a participant's transaction capabilities."""

    def __init__(
        self,
        participant_id: str,
        endpoint: str,
        supports_2pc: bool = False,
        supports_saga: bool = True,
        compensation_action: Optional[str] = None,
        timeout: int = 30,
        retry_count: int = 3,
        priority: int = 1,
    ):
        self.participant_id = participant_id
        self.endpoint = endpoint
        self.supports_2pc = supports_2pc
        self.supports_saga = supports_saga
        self.compensation_action = compensation_action
        self.timeout = timeout
        self.retry_count = retry_count
        self.priority = priority

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "participant_id": self.participant_id,
            "endpoint": self.endpoint,
            "supports_2pc": self.supports_2pc,
            "supports_saga": self.supports_saga,
            "compensation_action": self.compensation_action,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParticipantCapability":
        """Create from dictionary."""
        return cls(
            participant_id=data["participant_id"],
            endpoint=data["endpoint"],
            supports_2pc=data.get("supports_2pc", False),
            supports_saga=data.get("supports_saga", True),
            compensation_action=data.get("compensation_action"),
            timeout=data.get("timeout", 30),
            retry_count=data.get("retry_count", 3),
            priority=data.get("priority", 1),
        )


class TransactionRequirements:
    """Represents transaction requirements for pattern selection."""

    def __init__(
        self,
        consistency: Union[ConsistencyLevel, str] = ConsistencyLevel.EVENTUAL,
        availability: Union[AvailabilityLevel, str] = AvailabilityLevel.HIGH,
        timeout: int = 300,
        isolation_level: str = "read_committed",
        durability: bool = True,
        allow_partial_failure: bool = True,
    ):
        self.consistency = (
            ConsistencyLevel(consistency)
            if isinstance(consistency, str)
            else consistency
        )
        self.availability = (
            AvailabilityLevel(availability)
            if isinstance(availability, str)
            else availability
        )
        self.timeout = timeout
        self.isolation_level = isolation_level
        self.durability = durability
        self.allow_partial_failure = allow_partial_failure


@register_node("DistributedTransactionManagerNode")
class DistributedTransactionManagerNode(AsyncNode):
    """High-level distributed transaction manager.

    This node provides a unified interface for distributed transactions,
    automatically selecting the optimal pattern (Saga vs 2PC) based on
    participant capabilities and transaction requirements.

    Key Features:
    - Automatic pattern selection based on requirements
    - Unified interface for all transaction patterns
    - Participant capability analysis
    - Transaction lifecycle management
    - Cross-pattern monitoring and recovery
    - Enterprise-grade configuration options

    Operations:
    - create_transaction: Create new distributed transaction
    - add_participant: Add participant with capabilities
    - execute_transaction: Execute with optimal pattern
    - get_status: Get unified transaction status
    - abort_transaction: Abort active transaction
    - recover_transaction: Recover failed transaction
    - list_transactions: List managed transactions
    """

    def __init__(
        self,
        transaction_name: str = None,
        transaction_id: str = None,
        default_pattern: Union[TransactionPattern, str] = TransactionPattern.AUTO,
        default_timeout: int = 300,
        state_storage: str = "memory",
        storage_config: Dict[str, Any] = None,
        monitoring_enabled: bool = True,
        audit_logging: bool = False,
        retry_policy: Dict[str, Any] = None,
        **kwargs,
    ):
        """Initialize Distributed Transaction Manager.

        Args:
            transaction_name: Human-readable transaction name
            transaction_id: Unique transaction identifier
            default_pattern: Default transaction pattern to use
            default_timeout: Default timeout for transactions
            state_storage: Storage backend for transaction state
            storage_config: Configuration for state storage
            monitoring_enabled: Enable transaction monitoring
            audit_logging: Enable audit logging
            retry_policy: Retry configuration
            **kwargs: Additional node configuration
        """
        # Set node metadata
        metadata = NodeMetadata(
            name=kwargs.get("name", "distributed_transaction_manager"),
            description="High-level manager for distributed transactions with pattern selection",
            version="1.0.0",
            tags={"transaction", "distributed", "manager", "saga", "2pc"},
        )

        # Initialize AsyncNode
        super().__init__(metadata=metadata, **kwargs)

        # Transaction configuration
        self.transaction_name = transaction_name or f"dtx_{int(time.time())}"
        self.transaction_id = transaction_id or str(uuid.uuid4())
        self.default_pattern = (
            TransactionPattern(default_pattern)
            if isinstance(default_pattern, str)
            else default_pattern
        )
        self.default_timeout = default_timeout
        self.monitoring_enabled = monitoring_enabled
        self.audit_logging = audit_logging

        # Retry policy
        self.retry_policy = retry_policy or {
            "max_attempts": 3,
            "backoff": "exponential",
            "base_delay": 1.0,
            "max_delay": 30.0,
        }

        # Transaction state
        self.status = TransactionStatus.PENDING
        self.selected_pattern: Optional[TransactionPattern] = None
        self.participants: List[ParticipantCapability] = []
        self.requirements: Optional[TransactionRequirements] = None
        self.context: Dict[str, Any] = {}
        self.created_at: Optional[datetime] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None

        # Pattern coordinators
        self._saga_coordinator = None
        self._2pc_coordinator = None
        self._active_coordinator = None

        # State persistence
        self.state_storage = state_storage
        self.storage_config = storage_config or {}
        self._storage = None

        logger.info(
            f"Initialized Distributed Transaction Manager: {self.transaction_id}"
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters for validation."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                description="Transaction operation to execute",
                default="create_transaction",
            ),
            "transaction_name": NodeParameter(
                name="transaction_name",
                type=str,
                required=False,
                description="Human-readable transaction name",
            ),
            "pattern": NodeParameter(
                name="pattern",
                type=str,
                required=False,
                description="Transaction pattern (saga, two_phase_commit, auto)",
            ),
            "participants": NodeParameter(
                name="participants",
                type=list,
                required=False,
                description="List of transaction participants with capabilities",
            ),
            "requirements": NodeParameter(
                name="requirements",
                type=dict,
                required=False,
                description="Transaction requirements for pattern selection",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                description="Transaction context data",
            ),
            "transaction_id": NodeParameter(
                name="transaction_id",
                type=str,
                required=False,
                description="Transaction ID for recovery operations",
            ),
        }

    def get_outputs(self) -> Dict[str, NodeParameter]:
        """Get node outputs."""
        return {
            "status": NodeParameter(
                name="status",
                type=str,
                required=True,
                description="Operation status (success, failed, aborted)",
            ),
            "transaction_id": NodeParameter(
                name="transaction_id",
                type=str,
                required=True,
                description="Transaction identifier",
            ),
            "transaction_status": NodeParameter(
                name="transaction_status",
                type=str,
                required=True,
                description="Current transaction status",
            ),
            "selected_pattern": NodeParameter(
                name="selected_pattern",
                type=str,
                required=False,
                description="Selected transaction pattern",
            ),
            "participants": NodeParameter(
                name="participants",
                type=list,
                required=False,
                description="List of transaction participants",
            ),
            "result": NodeParameter(
                name="result",
                type=dict,
                required=False,
                description="Transaction result data",
            ),
            "error": NodeParameter(
                name="error",
                type=str,
                required=False,
                description="Error message if transaction failed",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute transaction manager operation asynchronously."""
        operation = kwargs.get("operation", "create_transaction")

        try:
            if operation == "create_transaction":
                return await self._create_transaction(**kwargs)
            elif operation == "add_participant":
                return await self._add_participant(**kwargs)
            elif operation == "execute_transaction":
                return await self._execute_transaction(**kwargs)
            elif operation == "get_status":
                return await self._get_status()
            elif operation == "abort_transaction":
                return await self._abort_transaction()
            elif operation == "recover_transaction":
                return await self._recover_transaction(**kwargs)
            elif operation == "list_transactions":
                return await self._list_transactions(**kwargs)
            else:
                raise NodeExecutionError(
                    f"Unknown transaction manager operation: {operation}"
                )

        except Exception as e:
            logger.error(f"Distributed transaction manager error: {e}")
            self.error_message = str(e)
            await self._persist_state()
            return {
                "status": "error",
                "transaction_id": self.transaction_id,
                "transaction_status": self.status.value,
                "error": str(e),
            }

    async def _create_transaction(self, **kwargs) -> Dict[str, Any]:
        """Create a new distributed transaction."""
        if self.status != TransactionStatus.PENDING:
            raise NodeExecutionError(
                f"Transaction already in status: {self.status.value}"
            )

        # Set transaction name if provided
        transaction_name = kwargs.get("transaction_name")
        if transaction_name:
            self.transaction_name = transaction_name

        # Set requirements
        requirements_data = kwargs.get("requirements", {})
        self.requirements = TransactionRequirements(**requirements_data)

        # Update context
        context = kwargs.get("context", {})
        self.context.update(context)

        # Set creation time
        self.created_at = datetime.now(UTC)

        logger.info(f"Creating distributed transaction: {self.transaction_id}")

        # Persist initial state
        await self._persist_state()

        return {
            "status": "success",
            "transaction_id": self.transaction_id,
            "transaction_status": self.status.value,
            "transaction_name": self.transaction_name,
            "created_at": self.created_at.isoformat(),
        }

    async def _add_participant(self, **kwargs) -> Dict[str, Any]:
        """Add a participant to the transaction."""
        participant_data = kwargs.get("participant", kwargs)  # Support both formats

        if not participant_data.get("participant_id"):
            raise NodeExecutionError(
                "participant_id is required for add_participant operation"
            )

        # Create participant capability
        participant = ParticipantCapability.from_dict(participant_data)

        # Check if participant already exists
        existing_ids = [p.participant_id for p in self.participants]
        if participant.participant_id in existing_ids:
            logger.warning(f"Participant {participant.participant_id} already exists")
            return {
                "status": "exists",
                "transaction_id": self.transaction_id,
                "participant_id": participant.participant_id,
            }

        self.participants.append(participant)

        logger.info(
            f"Added participant {participant.participant_id} to transaction {self.transaction_id}"
        )

        # Persist state
        await self._persist_state()

        return {
            "status": "success",
            "transaction_id": self.transaction_id,
            "participant_id": participant.participant_id,
            "total_participants": len(self.participants),
        }

    async def _execute_transaction(self, **kwargs) -> Dict[str, Any]:
        """Execute the distributed transaction with optimal pattern."""
        if not self.participants:
            raise NodeExecutionError("No participants defined for transaction")

        try:
            # Select pattern if not already selected
            if not self.selected_pattern:
                pattern = kwargs.get("pattern", self.default_pattern)
                if isinstance(pattern, str):
                    pattern = TransactionPattern(pattern)

                if pattern == TransactionPattern.AUTO:
                    self.selected_pattern = self._select_optimal_pattern()
                else:
                    self.selected_pattern = pattern
                    self._validate_pattern_compatibility()

            # Update status
            self.status = TransactionStatus.RUNNING
            self.started_at = datetime.now(UTC)
            await self._persist_state()

            logger.info(
                f"Executing transaction {self.transaction_id} with pattern: {self.selected_pattern.value}"
            )

            # Create and execute appropriate coordinator
            if self.selected_pattern == TransactionPattern.SAGA:
                result = await self._execute_saga_pattern()
            elif self.selected_pattern == TransactionPattern.TWO_PHASE_COMMIT:
                result = await self._execute_2pc_pattern()
            else:
                raise NodeExecutionError(
                    f"Unsupported transaction pattern: {self.selected_pattern}"
                )

            # Update final status
            if result.get("status") == "success":
                if result.get("state") == "committed":
                    self.status = TransactionStatus.COMMITTED
                elif result.get("state") == "compensated":
                    self.status = TransactionStatus.COMPENSATED
                else:
                    self.status = TransactionStatus.COMMITTED
            else:
                if result.get("status") == "aborted":
                    self.status = TransactionStatus.ABORTED
                else:
                    self.status = TransactionStatus.FAILED
                    self.error_message = result.get(
                        "error", "Transaction execution failed"
                    )

            self.completed_at = datetime.now(UTC)
            await self._persist_state()

            return {
                "status": result.get("status", "failed"),
                "transaction_id": self.transaction_id,
                "transaction_status": self.status.value,
                "selected_pattern": self.selected_pattern.value,
                "participants": len(self.participants),
                "execution_time": (self.completed_at - self.started_at).total_seconds(),
                "result": result,
            }

        except Exception as e:
            logger.error(f"Transaction execution failed: {e}")
            self.status = TransactionStatus.FAILED
            self.error_message = str(e)
            self.completed_at = datetime.now(UTC)
            await self._persist_state()

            return {
                "status": "failed",
                "transaction_id": self.transaction_id,
                "transaction_status": self.status.value,
                "selected_pattern": (
                    self.selected_pattern.value if self.selected_pattern else None
                ),
                "error": str(e),
            }

    def _select_optimal_pattern(self) -> TransactionPattern:
        """Select optimal transaction pattern based on requirements and capabilities."""
        # Check if all participants support 2PC
        all_support_2pc = all(p.supports_2pc for p in self.participants)

        # Analyze requirements
        requires_strong_consistency = self.requirements.consistency in [
            ConsistencyLevel.STRONG,
            ConsistencyLevel.IMMEDIATE,
        ]
        requires_high_availability = (
            self.requirements.availability == AvailabilityLevel.HIGH
        )

        # Pattern selection logic
        if self.requirements.consistency == ConsistencyLevel.IMMEDIATE:
            # Immediate consistency requires 2PC
            if not all_support_2pc:
                raise NodeExecutionError(
                    "Immediate consistency requires all participants to support 2PC, "
                    f"but participants {[p.participant_id for p in self.participants if not p.supports_2pc]} do not"
                )
            return TransactionPattern.TWO_PHASE_COMMIT

        elif (
            requires_strong_consistency
            and all_support_2pc
            and not requires_high_availability
        ):
            # Strong consistency preferred with 2PC support and availability not critical
            return TransactionPattern.TWO_PHASE_COMMIT

        elif requires_high_availability or not all_support_2pc:
            # High availability required or not all participants support 2PC
            return TransactionPattern.SAGA

        else:
            # Default to Saga for flexibility
            return TransactionPattern.SAGA

    def _validate_pattern_compatibility(self):
        """Validate that selected pattern is compatible with participants."""
        if self.selected_pattern == TransactionPattern.TWO_PHASE_COMMIT:
            unsupported = [
                p.participant_id for p in self.participants if not p.supports_2pc
            ]
            if unsupported:
                raise NodeExecutionError(
                    f"2PC pattern selected but participants {unsupported} do not support 2PC"
                )

        elif self.selected_pattern == TransactionPattern.SAGA:
            unsupported = [
                p.participant_id for p in self.participants if not p.supports_saga
            ]
            if unsupported:
                raise NodeExecutionError(
                    f"Saga pattern selected but participants {unsupported} do not support Saga"
                )

    async def _execute_saga_pattern(self) -> Dict[str, Any]:
        """Execute transaction using Saga pattern."""
        from .saga_coordinator import SagaCoordinatorNode

        # Create saga coordinator
        self._saga_coordinator = SagaCoordinatorNode(
            saga_name=self.transaction_name,
            saga_id=self.transaction_id,
            timeout=(
                self.requirements.timeout if self.requirements else self.default_timeout
            ),
            state_storage=self.state_storage,
            storage_config=self.storage_config,
        )
        self._active_coordinator = self._saga_coordinator

        # Begin saga
        await self._saga_coordinator.async_run(
            operation="create_saga", context=self.context
        )

        # Add saga steps based on participants
        for participant in sorted(self.participants, key=lambda p: p.priority):
            await self._saga_coordinator.async_run(
                operation="add_step",
                name=f"step_{participant.participant_id}",
                node_id=f"ParticipantNode_{participant.participant_id}",
                parameters={
                    "endpoint": participant.endpoint,
                    "timeout": participant.timeout,
                    "retry_count": participant.retry_count,
                },
                compensation_node_id=f"CompensationNode_{participant.participant_id}",
                compensation_parameters={
                    "action": participant.compensation_action or "rollback",
                    "endpoint": participant.endpoint,
                },
            )

        # Execute saga
        return await self._saga_coordinator.async_run(operation="execute_saga")

    async def _execute_2pc_pattern(self) -> Dict[str, Any]:
        """Execute transaction using Two-Phase Commit pattern."""
        from .two_phase_commit import TwoPhaseCommitCoordinatorNode

        # Create 2PC coordinator
        self._2pc_coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name=self.transaction_name,
            transaction_id=self.transaction_id,
            timeout=(
                self.requirements.timeout if self.requirements else self.default_timeout
            ),
            state_storage=self.state_storage,
            storage_config=self.storage_config,
        )
        self._active_coordinator = self._2pc_coordinator

        # Begin transaction
        await self._2pc_coordinator.async_run(
            operation="begin_transaction", context=self.context
        )

        # Add participants
        for participant in self.participants:
            await self._2pc_coordinator.async_run(
                operation="add_participant",
                participant_id=participant.participant_id,
                endpoint=participant.endpoint,
            )

        # Execute 2PC
        return await self._2pc_coordinator.async_run(operation="execute_transaction")

    async def _get_status(self) -> Dict[str, Any]:
        """Get current transaction status."""
        participant_info = [p.to_dict() for p in self.participants]

        result = {
            "status": "success",
            "transaction_id": self.transaction_id,
            "transaction_name": self.transaction_name,
            "transaction_status": self.status.value,
            "selected_pattern": (
                self.selected_pattern.value if self.selected_pattern else None
            ),
            "participants": participant_info,
            "context": self.context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }

        # Add requirements info
        if self.requirements:
            result["requirements"] = {
                "consistency": self.requirements.consistency.value,
                "availability": self.requirements.availability.value,
                "timeout": self.requirements.timeout,
                "isolation_level": self.requirements.isolation_level,
                "durability": self.requirements.durability,
                "allow_partial_failure": self.requirements.allow_partial_failure,
            }

        # Add active coordinator status if available
        if self._active_coordinator:
            try:
                coordinator_status = await self._active_coordinator.async_run(
                    operation="get_status"
                )
                result["coordinator_status"] = coordinator_status
            except Exception as e:
                logger.warning(f"Failed to get coordinator status: {e}")

        if self.error_message:
            result["error"] = self.error_message

        return result

    async def _abort_transaction(self) -> Dict[str, Any]:
        """Abort the transaction."""
        if self.status in [
            TransactionStatus.COMMITTED,
            TransactionStatus.ABORTED,
            TransactionStatus.COMPENSATED,
        ]:
            return {
                "status": "already_finished",
                "transaction_id": self.transaction_id,
                "transaction_status": self.status.value,
            }

        logger.info(f"Aborting transaction {self.transaction_id}")

        # Abort active coordinator if exists
        if self._active_coordinator:
            try:
                await self._active_coordinator.async_run(operation="abort_transaction")
            except Exception as e:
                logger.warning(f"Failed to abort coordinator: {e}")

        self.status = TransactionStatus.ABORTED
        self.completed_at = datetime.now(UTC)
        await self._persist_state()

        return {
            "status": "success",
            "transaction_id": self.transaction_id,
            "transaction_status": self.status.value,
            "aborted_at": self.completed_at.isoformat(),
        }

    async def _recover_transaction(self, **kwargs) -> Dict[str, Any]:
        """Recover transaction from persistent state."""
        transaction_id = kwargs.get("transaction_id", self.transaction_id)

        # Initialize storage if not already done
        if not self._storage:
            self._storage = await self._get_storage()

        if not self._storage:
            raise NodeExecutionError("State storage not configured for recovery")

        # Load transaction state
        state_data = await self._storage.load_state(transaction_id)
        if not state_data:
            raise NodeExecutionError(f"Transaction {transaction_id} not found")

        # Restore state
        self._restore_from_state(state_data)

        logger.info(
            f"Recovered transaction {transaction_id} with pattern {self.selected_pattern}"
        )

        # Recover appropriate coordinator
        if self.selected_pattern == TransactionPattern.SAGA:
            from .saga_coordinator import SagaCoordinatorNode

            self._saga_coordinator = SagaCoordinatorNode(
                saga_name=self.transaction_name,
                saga_id=transaction_id,
                state_storage=self.state_storage,
                storage_config=self.storage_config,
            )
            self._active_coordinator = self._saga_coordinator
            # Load the saga state
            load_result = await self._saga_coordinator.async_run(
                operation="load_saga", saga_id=transaction_id
            )
            if load_result.get("status") != "success":
                logger.warning(f"Failed to load saga state: {load_result}")
            return await self._get_status()
        elif self.selected_pattern == TransactionPattern.TWO_PHASE_COMMIT:
            from .two_phase_commit import TwoPhaseCommitCoordinatorNode

            self._2pc_coordinator = TwoPhaseCommitCoordinatorNode(
                transaction_name=self.transaction_name,
                transaction_id=transaction_id,
                state_storage=self.state_storage,
                storage_config=self.storage_config,
            )
            self._active_coordinator = self._2pc_coordinator
            # For 2PC, we just return the status since the coordinator initializes with the right ID
            return await self._get_status()

        return await self._get_status()

    async def _list_transactions(self, **kwargs) -> Dict[str, Any]:
        """List managed transactions."""
        if not self._storage:
            self._storage = await self._get_storage()

        if not self._storage:
            return {"status": "success", "transactions": [], "count": 0}

        # Get filter criteria
        filter_criteria = kwargs.get("filter", {})

        try:
            transaction_ids = await self._storage.list_sagas(filter_criteria)
            return {
                "status": "success",
                "transactions": transaction_ids,
                "count": len(transaction_ids),
            }
        except Exception as e:
            logger.error(f"Failed to list transactions: {e}")
            return {"status": "error", "error": str(e), "transactions": [], "count": 0}

    async def _persist_state(self):
        """Persist transaction state."""
        if not self._storage:
            self._storage = await self._get_storage()

        if self._storage:
            state_data = self._get_state_data()
            await self._storage.save_state(self.transaction_id, state_data)

    async def _get_storage(self):
        """Get storage instance for state persistence."""
        if self.state_storage == "memory":
            from .saga_state_storage import InMemoryStateStorage

            return InMemoryStateStorage()
        elif self.state_storage == "redis":
            from .saga_state_storage import RedisStateStorage

            redis_client = self.storage_config.get("redis_client")
            if not redis_client:
                logger.warning("Redis client not provided, using memory storage")
                from .saga_state_storage import InMemoryStateStorage

                return InMemoryStateStorage()
            return RedisStateStorage(
                redis_client, self.storage_config.get("key_prefix", "dtx:state:")
            )
        elif self.state_storage == "database":
            from .saga_state_storage import DatabaseStateStorage

            db_pool = self.storage_config.get("db_pool")
            if not db_pool:
                logger.warning("Database pool not provided, using memory storage")
                from .saga_state_storage import InMemoryStateStorage

                return InMemoryStateStorage()
            return DatabaseStateStorage(
                db_pool,
                self.storage_config.get("table_name", "distributed_transaction_states"),
            )
        else:
            logger.warning(f"Unknown storage type: {self.state_storage}, using memory")
            from .saga_state_storage import InMemoryStateStorage

            return InMemoryStateStorage()

    def _get_state_data(self) -> Dict[str, Any]:
        """Get current state as dictionary for persistence."""
        return {
            "transaction_id": self.transaction_id,
            "transaction_name": self.transaction_name,
            "status": self.status.value,
            "selected_pattern": (
                self.selected_pattern.value if self.selected_pattern else None
            ),
            "participants": [p.to_dict() for p in self.participants],
            "requirements": (
                {
                    "consistency": self.requirements.consistency.value,
                    "availability": self.requirements.availability.value,
                    "timeout": self.requirements.timeout,
                    "isolation_level": self.requirements.isolation_level,
                    "durability": self.requirements.durability,
                    "allow_partial_failure": self.requirements.allow_partial_failure,
                }
                if self.requirements
                else None
            ),
            "context": self.context,
            "default_timeout": self.default_timeout,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
        }

    def _restore_from_state(self, state_data: Dict[str, Any]):
        """Restore transaction state from persistence data."""
        self.transaction_id = state_data["transaction_id"]
        self.transaction_name = state_data["transaction_name"]
        self.status = TransactionStatus(state_data["status"])

        if state_data.get("selected_pattern"):
            self.selected_pattern = TransactionPattern(state_data["selected_pattern"])

        # Restore participants
        self.participants = []
        for p_data in state_data.get("participants", []):
            self.participants.append(ParticipantCapability.from_dict(p_data))

        # Restore requirements
        if state_data.get("requirements"):
            req_data = state_data["requirements"]
            self.requirements = TransactionRequirements(
                consistency=req_data["consistency"],
                availability=req_data["availability"],
                timeout=req_data["timeout"],
                isolation_level=req_data["isolation_level"],
                durability=req_data["durability"],
                allow_partial_failure=req_data["allow_partial_failure"],
            )

        self.context = state_data.get("context", {})
        self.default_timeout = state_data.get("default_timeout", self.default_timeout)
        self.error_message = state_data.get("error_message")

        # Restore timestamps
        if state_data.get("created_at"):
            self.created_at = datetime.fromisoformat(state_data["created_at"])
        if state_data.get("started_at"):
            self.started_at = datetime.fromisoformat(state_data["started_at"])
        if state_data.get("completed_at"):
            self.completed_at = datetime.fromisoformat(state_data["completed_at"])
