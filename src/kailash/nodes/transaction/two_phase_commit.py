"""Two-Phase Commit (2PC) Transaction Coordinator Node.

This module implements the Two-Phase Commit protocol for distributed transactions,
ensuring atomicity across multiple resources. Unlike sagas which use compensation,
2PC uses a prepare/commit protocol to achieve ACID properties.

The Two-Phase Commit protocol consists of:
1. Phase 1 (Prepare): All participants prepare to commit and vote
2. Phase 2 (Commit/Abort): Coordinator decides based on votes

Examples:
    Basic 2PC transaction:

    >>> coordinator = TwoPhaseCommitCoordinatorNode(
    ...     transaction_name="order_processing",
    ...     participants=["database", "payment", "inventory"]
    ... )
    >>> result = coordinator.execute(
    ...     operation="begin_transaction",
    ...     context={"order_id": "order_123", "amount": 100.00}
    ... )

    Adding participants:

    >>> coordinator.execute(
    ...     operation="add_participant",
    ...     participant_id="audit_service",
    ...     endpoint="http://audit:8080/prepare"
    ... )

    Executing transaction:

    >>> result = coordinator.execute(operation="execute_transaction")
    # Returns success if all participants commit, failure if any abort
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeMetadata, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError

logger = logging.getLogger(__name__)


class TransactionState(Enum):
    """Two-phase commit transaction states."""

    INIT = "init"
    PREPARING = "preparing"
    PREPARED = "prepared"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ABORTING = "aborting"
    ABORTED = "aborted"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ParticipantVote(Enum):
    """Participant votes in prepare phase."""

    PREPARED = "prepared"
    ABORT = "abort"
    TIMEOUT = "timeout"


class TwoPhaseCommitParticipant:
    """Represents a participant in the 2PC protocol."""

    def __init__(
        self,
        participant_id: str,
        endpoint: str,
        timeout: int = 30,
        retry_count: int = 3,
    ):
        self.participant_id = participant_id
        self.endpoint = endpoint
        self.timeout = timeout
        self.retry_count = retry_count
        self.vote: Optional[ParticipantVote] = None
        self.last_contact: Optional[datetime] = None
        self.prepare_time: Optional[datetime] = None
        self.commit_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert participant to dictionary for serialization."""
        return {
            "participant_id": self.participant_id,
            "endpoint": self.endpoint,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "vote": self.vote.value if self.vote else None,
            "last_contact": (
                self.last_contact.isoformat() if self.last_contact else None
            ),
            "prepare_time": (
                self.prepare_time.isoformat() if self.prepare_time else None
            ),
            "commit_time": self.commit_time.isoformat() if self.commit_time else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TwoPhaseCommitParticipant":
        """Create participant from dictionary."""
        participant = cls(
            participant_id=data["participant_id"],
            endpoint=data["endpoint"],
            timeout=data.get("timeout", 30),
            retry_count=data.get("retry_count", 3),
        )

        if data.get("vote"):
            participant.vote = ParticipantVote(data["vote"])
        if data.get("last_contact"):
            participant.last_contact = datetime.fromisoformat(data["last_contact"])
        if data.get("prepare_time"):
            participant.prepare_time = datetime.fromisoformat(data["prepare_time"])
        if data.get("commit_time"):
            participant.commit_time = datetime.fromisoformat(data["commit_time"])

        return participant


@register_node("TwoPhaseCommitCoordinatorNode")
class TwoPhaseCommitCoordinatorNode(AsyncNode):
    """Node implementing Two-Phase Commit coordinator functionality.

    This node orchestrates distributed transactions using the 2PC protocol,
    ensuring atomicity across multiple participants. Unlike saga patterns,
    2PC provides stronger consistency guarantees but requires all participants
    to be available during the transaction.

    Key Features:
    - Atomic distributed transactions
    - Automatic timeout handling
    - Participant failure detection
    - Transaction state persistence
    - Recovery after coordinator failure
    - Configurable retry policies

    Operations:
    - begin_transaction: Start new 2PC transaction
    - add_participant: Add participant to transaction
    - execute_transaction: Execute prepare/commit phases
    - abort_transaction: Abort transaction
    - get_status: Get transaction status
    - recover_transaction: Recover from coordinator failure
    """

    def __init__(
        self,
        transaction_name: str = None,
        transaction_id: str = None,
        participants: List[str] = None,
        timeout: int = 300,
        prepare_timeout: int = 30,
        commit_timeout: int = 30,
        max_retries: int = 3,
        state_storage: str = "memory",
        storage_config: Dict[str, Any] = None,
        **kwargs,
    ):
        """Initialize Two-Phase Commit coordinator.

        Args:
            transaction_name: Human-readable transaction name
            transaction_id: Unique transaction identifier
            participants: List of participant identifiers
            timeout: Overall transaction timeout in seconds
            prepare_timeout: Timeout for prepare phase in seconds
            commit_timeout: Timeout for commit phase in seconds
            max_retries: Maximum retry attempts per participant
            state_storage: Storage backend ("memory", "redis", "database")
            storage_config: Configuration for state storage
            **kwargs: Additional node configuration
        """
        # Set node metadata
        metadata = NodeMetadata(
            name=kwargs.get("name", "two_phase_commit_coordinator"),
            description="Coordinates distributed transactions using Two-Phase Commit protocol",
            version="1.0.0",
            tags={"transaction", "2pc", "distributed", "coordinator"},
        )

        # Initialize AsyncNode
        super().__init__(metadata=metadata, **kwargs)

        # Transaction configuration
        self.transaction_name = transaction_name or f"2pc_{int(time.time())}"
        self.transaction_id = transaction_id or str(uuid.uuid4())
        self.timeout = timeout
        self.prepare_timeout = prepare_timeout
        self.commit_timeout = commit_timeout
        self.max_retries = max_retries

        # Transaction state
        self.state = TransactionState.INIT
        self.participants: Dict[str, TwoPhaseCommitParticipant] = {}
        self.context: Dict[str, Any] = {}
        self.started_at: Optional[datetime] = None
        self.prepared_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None

        # Initialize participants if provided
        if participants:
            for p_id in participants:
                self.participants[p_id] = TwoPhaseCommitParticipant(
                    participant_id=p_id,
                    endpoint=f"http://{p_id}/2pc",  # Default endpoint
                    timeout=prepare_timeout,
                )

        # State persistence
        self.state_storage = state_storage
        self.storage_config = storage_config or {}
        self._storage = None

        logger.info(f"Initialized 2PC coordinator: {self.transaction_id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters for validation."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                description="2PC operation to execute",
                default="begin_transaction",
            ),
            "participant_id": NodeParameter(
                name="participant_id",
                type=str,
                required=False,
                description="Participant ID for add_participant operation",
            ),
            "endpoint": NodeParameter(
                name="endpoint",
                type=str,
                required=False,
                description="Participant endpoint for add_participant operation",
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
            "state": NodeParameter(
                name="state",
                type=str,
                required=True,
                description="Current transaction state",
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
        """Execute 2PC operation asynchronously."""
        operation = kwargs.get("operation", "begin_transaction")

        try:
            if operation == "begin_transaction":
                return await self._begin_transaction(**kwargs)
            elif operation == "add_participant":
                return await self._add_participant(**kwargs)
            elif operation == "execute_transaction":
                return await self._execute_transaction()
            elif operation == "abort_transaction":
                return await self._abort_transaction()
            elif operation == "get_status":
                return await self._get_status()
            elif operation == "recover_transaction":
                return await self._recover_transaction(**kwargs)
            else:
                raise NodeExecutionError(f"Unknown 2PC operation: {operation}")

        except Exception as e:
            logger.error(f"2PC coordinator error: {e}")
            self.error_message = str(e)
            await self._persist_state()
            return {
                "status": "error",
                "transaction_id": self.transaction_id,
                "state": self.state.value,
                "error": str(e),
            }

    async def _begin_transaction(self, **kwargs) -> Dict[str, Any]:
        """Begin a new 2PC transaction."""
        if self.state != TransactionState.INIT:
            raise NodeExecutionError(
                f"Transaction already in state: {self.state.value}"
            )

        # Update context
        context = kwargs.get("context", {})
        self.context.update(context)

        # Set transaction start time
        self.started_at = datetime.now(UTC)

        logger.info(f"Beginning 2PC transaction: {self.transaction_id}")

        # Persist initial state
        await self._persist_state()

        return {
            "status": "success",
            "transaction_id": self.transaction_id,
            "state": self.state.value,
            "participants": list(self.participants.keys()),
            "started_at": self.started_at.isoformat(),
        }

    async def _add_participant(self, **kwargs) -> Dict[str, Any]:
        """Add a participant to the transaction."""
        participant_id = kwargs.get("participant_id")
        endpoint = kwargs.get("endpoint")

        if not participant_id:
            raise NodeExecutionError(
                "participant_id is required for add_participant operation"
            )

        if not endpoint:
            # Generate default endpoint
            endpoint = f"http://{participant_id}/2pc"

        if participant_id in self.participants:
            logger.warning(f"Participant {participant_id} already exists")
            return {
                "status": "exists",
                "transaction_id": self.transaction_id,
                "participant_id": participant_id,
            }

        # Create participant
        participant = TwoPhaseCommitParticipant(
            participant_id=participant_id,
            endpoint=endpoint,
            timeout=self.prepare_timeout,
            retry_count=self.max_retries,
        )

        self.participants[participant_id] = participant

        logger.info(
            f"Added participant {participant_id} to transaction {self.transaction_id}"
        )

        # Persist state
        await self._persist_state()

        return {
            "status": "success",
            "transaction_id": self.transaction_id,
            "participant_id": participant_id,
            "total_participants": len(self.participants),
        }

    async def _execute_transaction(self) -> Dict[str, Any]:
        """Execute the two-phase commit protocol."""
        if not self.participants:
            raise NodeExecutionError("No participants defined for transaction")

        try:
            # Phase 1: Prepare
            logger.info(f"Starting prepare phase for transaction {self.transaction_id}")
            self.state = TransactionState.PREPARING
            await self._persist_state()

            prepare_success = await self._execute_prepare_phase()

            if not prepare_success:
                # Some participants voted to abort
                logger.warning(
                    f"Prepare phase failed for transaction {self.transaction_id}"
                )
                await self._abort_all_participants()
                self.state = TransactionState.ABORTED
                await self._persist_state()

                return {
                    "status": "aborted",
                    "transaction_id": self.transaction_id,
                    "state": self.state.value,
                    "reason": "One or more participants voted to abort",
                }

            # All participants prepared successfully
            self.state = TransactionState.PREPARED
            self.prepared_at = datetime.now(UTC)
            await self._persist_state()

            # Phase 2: Commit
            logger.info(f"Starting commit phase for transaction {self.transaction_id}")
            self.state = TransactionState.COMMITTING
            await self._persist_state()

            commit_success = await self._execute_commit_phase()

            if commit_success:
                self.state = TransactionState.COMMITTED
                self.completed_at = datetime.now(UTC)

                logger.info(f"Transaction {self.transaction_id} committed successfully")

                await self._persist_state()

                return {
                    "status": "success",
                    "transaction_id": self.transaction_id,
                    "state": self.state.value,
                    "participants_committed": len(
                        [p for p in self.participants.values() if p.commit_time]
                    ),
                    "completed_at": self.completed_at.isoformat(),
                }
            else:
                # Commit phase failed - this is a serious problem in 2PC
                self.state = TransactionState.FAILED
                self.error_message = (
                    "Commit phase failed - system in inconsistent state"
                )

                logger.error(
                    f"CRITICAL: Commit phase failed for transaction {self.transaction_id}"
                )

                await self._persist_state()

                return {
                    "status": "failed",
                    "transaction_id": self.transaction_id,
                    "state": self.state.value,
                    "error": self.error_message,
                }

        except Exception as e:
            logger.error(f"Transaction execution failed: {e}")
            self.state = TransactionState.FAILED
            self.error_message = str(e)
            await self._persist_state()

            # Try to abort if we're still in prepare phase
            if self.state in [TransactionState.PREPARING, TransactionState.PREPARED]:
                await self._abort_all_participants()

            return {
                "status": "failed",
                "transaction_id": self.transaction_id,
                "state": self.state.value,
                "error": str(e),
            }

    async def _execute_prepare_phase(self) -> bool:
        """Execute prepare phase of 2PC protocol."""
        # Send prepare requests to all participants
        prepare_tasks = []

        for participant in self.participants.values():
            task = asyncio.create_task(self._send_prepare_request(participant))
            prepare_tasks.append(task)

        # Wait for all prepare responses with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*prepare_tasks, return_exceptions=True),
                timeout=self.prepare_timeout,
            )
        except asyncio.TimeoutError:
            logger.error(f"Prepare phase timeout for transaction {self.transaction_id}")
            return False

        # Check if all participants voted to prepare
        for participant in self.participants.values():
            if participant.vote != ParticipantVote.PREPARED:
                logger.warning(
                    f"Participant {participant.participant_id} voted {participant.vote}"
                )
                return False

        return True

    async def _execute_commit_phase(self) -> bool:
        """Execute commit phase of 2PC protocol."""
        # Send commit requests to all participants
        commit_tasks = []

        for participant in self.participants.values():
            task = asyncio.create_task(self._send_commit_request(participant))
            commit_tasks.append(task)

        # Wait for all commit responses
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*commit_tasks, return_exceptions=True),
                timeout=self.commit_timeout,
            )

            # Check for any failures
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    participant_id = list(self.participants.keys())[i]
                    logger.error(
                        f"Commit failed for participant {participant_id}: {result}"
                    )
                    return False

            return True

        except asyncio.TimeoutError:
            logger.error(f"Commit phase timeout for transaction {self.transaction_id}")
            return False

    async def _send_prepare_request(self, participant: TwoPhaseCommitParticipant):
        """Send prepare request to a participant."""
        try:
            # This is a mock implementation - in real usage, this would
            # make HTTP/gRPC calls to actual participants
            logger.info(f"Sending PREPARE to {participant.participant_id}")

            # Simulate network call and processing time
            await asyncio.sleep(0.1)

            # Mock successful prepare vote (in real implementation, this would
            # depend on the participant's actual response)
            participant.vote = ParticipantVote.PREPARED
            participant.prepare_time = datetime.now(UTC)
            participant.last_contact = datetime.now(UTC)

            logger.info(f"Participant {participant.participant_id} voted PREPARED")

        except Exception as e:
            logger.error(f"Failed to send prepare to {participant.participant_id}: {e}")
            participant.vote = ParticipantVote.ABORT
            participant.last_contact = datetime.now(UTC)

    async def _send_commit_request(self, participant: TwoPhaseCommitParticipant):
        """Send commit request to a participant."""
        try:
            # This is a mock implementation
            logger.info(f"Sending COMMIT to {participant.participant_id}")

            # Simulate commit processing
            await asyncio.sleep(0.1)

            participant.commit_time = datetime.now(UTC)
            participant.last_contact = datetime.now(UTC)

            logger.info(
                f"Participant {participant.participant_id} committed successfully"
            )

        except Exception as e:
            logger.error(f"Failed to send commit to {participant.participant_id}: {e}")
            raise

    async def _abort_all_participants(self):
        """Send abort requests to all participants."""
        logger.info(f"Aborting all participants for transaction {self.transaction_id}")

        abort_tasks = []
        for participant in self.participants.values():
            task = asyncio.create_task(self._send_abort_request(participant))
            abort_tasks.append(task)

        # Don't wait indefinitely for abort responses
        try:
            await asyncio.wait_for(
                asyncio.gather(*abort_tasks, return_exceptions=True), timeout=30
            )
        except asyncio.TimeoutError:
            logger.warning("Some abort requests timed out")

    async def _send_abort_request(self, participant: TwoPhaseCommitParticipant):
        """Send abort request to a participant."""
        try:
            logger.info(f"Sending ABORT to {participant.participant_id}")

            # Simulate abort processing
            await asyncio.sleep(0.05)

            participant.last_contact = datetime.now(UTC)

        except Exception as e:
            logger.warning(f"Failed to send abort to {participant.participant_id}: {e}")

    async def _abort_transaction(self) -> Dict[str, Any]:
        """Abort the transaction."""
        if self.state in [TransactionState.COMMITTED, TransactionState.ABORTED]:
            return {
                "status": "already_finished",
                "transaction_id": self.transaction_id,
                "state": self.state.value,
            }

        logger.info(f"Aborting transaction {self.transaction_id}")

        self.state = TransactionState.ABORTING
        await self._persist_state()

        # Send abort to all participants
        await self._abort_all_participants()

        self.state = TransactionState.ABORTED
        self.completed_at = datetime.now(UTC)
        await self._persist_state()

        return {
            "status": "success",
            "transaction_id": self.transaction_id,
            "state": self.state.value,
            "aborted_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    async def _get_status(self) -> Dict[str, Any]:
        """Get current transaction status."""
        participant_info = []
        for participant in self.participants.values():
            participant_info.append(
                {
                    "participant_id": participant.participant_id,
                    "vote": participant.vote.value if participant.vote else None,
                    "prepare_time": (
                        participant.prepare_time.isoformat()
                        if participant.prepare_time
                        else None
                    ),
                    "commit_time": (
                        participant.commit_time.isoformat()
                        if participant.commit_time
                        else None
                    ),
                    "last_contact": (
                        participant.last_contact.isoformat()
                        if participant.last_contact
                        else None
                    ),
                }
            )

        result = {
            "status": "success",
            "transaction_id": self.transaction_id,
            "transaction_name": self.transaction_name,
            "state": self.state.value,
            "participants": participant_info,
            "context": self.context,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "prepared_at": self.prepared_at.isoformat() if self.prepared_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }

        # Add state-specific timestamps
        if self.state == TransactionState.ABORTED and self.completed_at:
            result["aborted_at"] = self.completed_at.isoformat()

        if self.error_message:
            result["error"] = self.error_message

        return result

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
            f"Recovered transaction {transaction_id} in state {self.state.value}"
        )

        # Check if we need to continue processing
        if self.state == TransactionState.PREPARED:
            # We were about to commit - continue with commit
            logger.info(
                f"Continuing commit phase for recovered transaction {transaction_id}"
            )
            commit_result = await self._execute_commit_phase()
            if commit_result:
                self.state = TransactionState.COMMITTED
                self.completed_at = datetime.now(UTC)
                await self._persist_state()
                return await self._get_status()
            else:
                self.state = TransactionState.FAILED
                await self._persist_state()
                return await self._get_status()
        elif self.state == TransactionState.COMMITTING:
            # We were committing - check participant status and retry if needed
            logger.info(
                f"Retrying commit phase for recovered transaction {transaction_id}"
            )
            commit_result = await self._execute_commit_phase()
            if commit_result:
                self.state = TransactionState.COMMITTED
                self.completed_at = datetime.now(UTC)
                await self._persist_state()
                return await self._get_status()
            else:
                self.state = TransactionState.FAILED
                await self._persist_state()
                return await self._get_status()

        return await self._get_status()

    async def _persist_state(self):
        """Persist transaction state."""
        if not self._storage:
            # Initialize storage if needed
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
                redis_client, self.storage_config.get("key_prefix", "2pc:state:")
            )
        elif self.state_storage == "database":
            db_pool = self.storage_config.get("db_pool")
            if not db_pool:
                logger.warning("Database pool not provided, using memory storage")
                from .saga_state_storage import InMemoryStateStorage

                return InMemoryStateStorage()
            return TwoPhaseDatabaseStorage(
                db_pool,
                self.storage_config.get("table_name", "two_phase_commit_states"),
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
            "state": self.state.value,
            "context": self.context,
            "participants": {
                p_id: participant.to_dict()
                for p_id, participant in self.participants.items()
            },
            "timeout": self.timeout,
            "prepare_timeout": self.prepare_timeout,
            "commit_timeout": self.commit_timeout,
            "max_retries": self.max_retries,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "prepared_at": self.prepared_at.isoformat() if self.prepared_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
        }

    def _restore_from_state(self, state_data: Dict[str, Any]):
        """Restore transaction state from persistence data."""
        self.transaction_id = state_data["transaction_id"]
        self.transaction_name = state_data["transaction_name"]
        self.state = TransactionState(state_data["state"])
        self.context = state_data.get("context", {})
        self.timeout = state_data.get("timeout", self.timeout)
        self.prepare_timeout = state_data.get("prepare_timeout", self.prepare_timeout)
        self.commit_timeout = state_data.get("commit_timeout", self.commit_timeout)
        self.max_retries = state_data.get("max_retries", self.max_retries)
        self.error_message = state_data.get("error_message")

        # Restore timestamps
        if state_data.get("started_at"):
            self.started_at = datetime.fromisoformat(state_data["started_at"])
        if state_data.get("prepared_at"):
            self.prepared_at = datetime.fromisoformat(state_data["prepared_at"])
        if state_data.get("completed_at"):
            self.completed_at = datetime.fromisoformat(state_data["completed_at"])

        # Restore participants
        self.participants = {}
        for p_id, p_data in state_data.get("participants", {}).items():
            self.participants[p_id] = TwoPhaseCommitParticipant.from_dict(p_data)


class TwoPhaseDatabaseStorage:
    """Database storage for Two-Phase Commit states with correct column mapping."""

    def __init__(self, db_pool: Any, table_name: str = "two_phase_commit_states"):
        self.db_pool = db_pool
        self.table_name = table_name

    async def save_state(self, transaction_id: str, state_data: Dict[str, Any]) -> bool:
        """Save 2PC state to database with correct column mapping."""
        try:
            async with self.db_pool.acquire() as conn:
                query = f"""
                INSERT INTO {self.table_name}
                    (transaction_id, transaction_name, state, state_data, updated_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (transaction_id)
                DO UPDATE SET
                    transaction_name = EXCLUDED.transaction_name,
                    state = EXCLUDED.state,
                    state_data = EXCLUDED.state_data,
                    updated_at = EXCLUDED.updated_at
                """

                await conn.execute(
                    query,
                    transaction_id,
                    state_data.get("transaction_name", ""),
                    state_data.get("state", ""),
                    json.dumps(state_data),
                    datetime.now(UTC),
                )

                return True

        except Exception as e:
            logger.error(
                f"Failed to save 2PC state to database for transaction {transaction_id}: {e}"
            )
            return False

    async def load_state(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Load 2PC state from database."""
        try:
            async with self.db_pool.acquire() as conn:
                query = f"""
                SELECT state_data
                FROM {self.table_name}
                WHERE transaction_id = $1
                """

                row = await conn.fetchrow(query, transaction_id)

                if row:
                    return json.loads(row["state_data"])
                return None

        except Exception as e:
            logger.error(
                f"Failed to load 2PC state from database for transaction {transaction_id}: {e}"
            )
            return None

    async def delete_state(self, transaction_id: str) -> bool:
        """Delete 2PC state from database."""
        try:
            async with self.db_pool.acquire() as conn:
                query = f"DELETE FROM {self.table_name} WHERE transaction_id = $1"
                result = await conn.execute(query, transaction_id)

                # Check if any rows were deleted
                return result.split()[-1] != "0"

        except Exception as e:
            logger.error(
                f"Failed to delete 2PC state from database for transaction {transaction_id}: {e}"
            )
            return False

    async def list_sagas(
        self, filter_criteria: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """List transaction IDs from database (for compatibility)."""
        try:
            async with self.db_pool.acquire() as conn:
                if not filter_criteria:
                    query = f"SELECT transaction_id FROM {self.table_name}"
                    rows = await conn.fetch(query)
                else:
                    # Build WHERE clause
                    conditions = []
                    params = []
                    param_count = 0

                    for key, value in filter_criteria.items():
                        param_count += 1
                        if key in ["state", "transaction_name"]:
                            conditions.append(f"{key} = ${param_count}")
                            params.append(value)
                        else:
                            # For other fields, use JSONB query
                            conditions.append(f"state_data->'{key}' = ${param_count}")
                            params.append(json.dumps(value))

                    where_clause = " AND ".join(conditions)
                    query = f"SELECT transaction_id FROM {self.table_name} WHERE {where_clause}"
                    rows = await conn.fetch(query, *params)

                return [row["transaction_id"] for row in rows]

        except Exception as e:
            logger.error(f"Failed to list 2PC transactions from database: {e}")
            return []
