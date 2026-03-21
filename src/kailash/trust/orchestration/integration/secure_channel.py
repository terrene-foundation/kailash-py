# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Secure Orchestration Channel - Encrypted task delegation.

This module integrates SecureChannel with TrustAwareOrchestrationRuntime
for secure task delegation between agents in orchestrated workflows.

Key Features:
- Encrypted task delegation with trust context
- Standardized delegation message protocol
- Request/response correlation for task results
- Auto-audit of delegation operations

Example:
    channel = SecureOrchestrationChannel(
        agent_id="supervisor-001",
        private_key=private_key,
        trust_operations=trust_ops,
        agent_registry=registry,
        replay_protection=replay_protection,
    )

    result = await channel.delegate_task(
        worker_agent_id="worker-001",
        task={"action": "analyze_data", "params": {...}},
        context=trust_context,
        timeout_seconds=60,
    )
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from kailash.trust.chain import VerificationLevel
from kailash.trust.messaging.channel import ChannelStatistics, SecureChannel
from kailash.trust.messaging.envelope import MessageMetadata, SecureMessageEnvelope
from kailash.trust.messaging.replay_protection import ReplayProtection
from kailash.trust.operations import TrustOperations
from kailash.trust.orchestration.exceptions import (
    ContextPropagationError,
    OrchestrationTrustError,
)
from kailash.trust.orchestration.execution_context import TrustExecutionContext
from kailash.trust.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


class DelegationMessageType(str, Enum):
    """Types of delegation messages in the orchestration protocol."""

    # Task lifecycle
    TASK_DELEGATION = "task_delegation"  # Supervisor -> Worker: Execute task
    TASK_ACCEPTED = "task_accepted"  # Worker -> Supervisor: Acknowledging task
    TASK_RESULT = "task_result"  # Worker -> Supervisor: Task completed
    TASK_ERROR = "task_error"  # Worker -> Supervisor: Task failed
    TASK_PROGRESS = "task_progress"  # Worker -> Supervisor: Progress update

    # Delegation management
    DELEGATION_REVOKED = "delegation_revoked"  # Supervisor -> Worker: Revoke access
    CONTEXT_UPDATE = "context_update"  # Supervisor -> Worker: Updated constraints


@dataclass
class DelegationMessage:
    """
    Standardized message for workflow delegation.

    Encapsulates task delegation requests and responses with
    trust context and metadata.
    """

    message_type: DelegationMessageType
    task_id: str
    payload: Dict[str, Any]
    context_data: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "message_type": self.message_type.value,
            "task_id": self.task_id,
            "payload": self.payload,
            "context_data": self.context_data,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelegationMessage":
        """Deserialize from dictionary."""
        return cls(
            message_type=DelegationMessageType(data["message_type"]),
            task_id=data["task_id"],
            payload=data["payload"],
            context_data=data.get("context_data"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create_delegation(
        cls,
        task: Any,
        context: TrustExecutionContext,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "DelegationMessage":
        """Create a task delegation message."""
        return cls(
            message_type=DelegationMessageType.TASK_DELEGATION,
            task_id=str(uuid.uuid4()),
            payload={"task": task} if not isinstance(task, dict) else task,
            context_data=context.to_dict(),
            metadata=metadata or {},
        )

    @classmethod
    def create_result(
        cls,
        task_id: str,
        result: Any,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "DelegationMessage":
        """Create a task result message."""
        return cls(
            message_type=(DelegationMessageType.TASK_RESULT if success else DelegationMessageType.TASK_ERROR),
            task_id=task_id,
            payload={
                "result": result,
                "success": success,
                "error": error,
            },
            metadata=metadata or {},
        )

    @classmethod
    def create_progress(
        cls,
        task_id: str,
        progress_percent: float,
        status_message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "DelegationMessage":
        """Create a progress update message."""
        return cls(
            message_type=DelegationMessageType.TASK_PROGRESS,
            task_id=task_id,
            payload={
                "progress_percent": progress_percent,
                "status_message": status_message,
            },
            metadata=metadata or {},
        )


@dataclass
class DelegationResult:
    """Result of a task delegation."""

    task_id: str
    worker_agent_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    delegation_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "task_id": self.task_id,
            "worker_agent_id": self.worker_agent_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "delegation_time_ms": self.delegation_time_ms,
        }


class SecureOrchestrationChannel:
    """
    Secure channel for orchestration task delegation.

    Extends SecureChannel with workflow-specific functionality:
    - Task delegation with trust context
    - Result collection with correlation
    - Progress monitoring
    - Delegation revocation

    Example:
        >>> channel = SecureOrchestrationChannel(
        ...     agent_id="supervisor-001",
        ...     private_key=private_key,
        ...     trust_operations=trust_ops,
        ...     agent_registry=registry,
        ...     replay_protection=replay_protection
        ... )
        >>>
        >>> # Delegate task to worker
        >>> result = await channel.delegate_task(
        ...     worker_agent_id="worker-001",
        ...     task={"action": "analyze", "data": [1, 2, 3]},
        ...     context=execution_context,
        ...     timeout_seconds=60
        ... )
        >>>
        >>> if result.success:
        ...     print(f"Task completed: {result.result}")
    """

    def __init__(
        self,
        agent_id: str,
        private_key: bytes,
        trust_operations: TrustOperations,
        agent_registry: AgentRegistry,
        replay_protection: ReplayProtection,
        verification_level: VerificationLevel = VerificationLevel.STANDARD,
        auto_audit: bool = True,
        default_timeout_seconds: int = 60,
    ):
        """
        Initialize a SecureOrchestrationChannel.

        Args:
            agent_id: This agent's identifier.
            private_key: Ed25519 private key for signing.
            trust_operations: TrustOperations for verification.
            agent_registry: AgentRegistry for agent discovery.
            replay_protection: ReplayProtection for preventing replays.
            verification_level: Level of trust verification.
            auto_audit: Auto-log operations to audit trail.
            default_timeout_seconds: Default timeout for delegations.
        """
        self._agent_id = agent_id
        self._trust_ops = trust_operations
        self._agent_registry = agent_registry
        self._default_timeout = default_timeout_seconds

        # Create underlying secure channel
        self._channel = SecureChannel(
            agent_id=agent_id,
            private_key=private_key,
            trust_operations=trust_operations,
            agent_registry=agent_registry,
            replay_protection=replay_protection,
            verification_level=verification_level,
            auto_audit=auto_audit,
        )

        # Delegation tracking
        self._active_delegations: Dict[str, DelegationMessage] = {}
        self._message_handlers: Dict[DelegationMessageType, List[Callable]] = {}
        self._lock = asyncio.Lock()

        logger.info(f"SecureOrchestrationChannel initialized for {agent_id}")

    @property
    def agent_id(self) -> str:
        """This agent's identifier."""
        return self._agent_id

    @property
    def secure_channel(self) -> SecureChannel:
        """Underlying secure channel."""
        return self._channel

    async def delegate_task(
        self,
        worker_agent_id: str,
        task: Any,
        context: TrustExecutionContext,
        timeout_seconds: Optional[int] = None,
        capabilities: Optional[List[str]] = None,
    ) -> DelegationResult:
        """
        Delegate a task to a worker agent.

        Creates a child execution context for the worker, sends the task
        via encrypted channel, and waits for the result.

        Args:
            worker_agent_id: Target worker agent.
            task: Task definition (dict or any serializable).
            context: Current execution context.
            timeout_seconds: Timeout for task completion.
            capabilities: Capabilities to delegate (subset of context).

        Returns:
            DelegationResult with task outcome.

        Raises:
            ContextPropagationError: If context propagation fails.
            asyncio.TimeoutError: If task times out.
        """
        import time

        start_time = time.perf_counter()
        timeout = timeout_seconds or self._default_timeout

        # Create child context for worker
        try:
            child_context = context.propagate_to_child(
                child_agent_id=worker_agent_id,
                task_id=str(uuid.uuid4()),
                capabilities=capabilities,
            )
        except Exception as e:
            raise ContextPropagationError(
                self._agent_id,
                worker_agent_id,
                f"Failed to create child context: {e}",
            )

        # Create delegation message
        delegation_msg = DelegationMessage.create_delegation(
            task=task,
            context=child_context,
            metadata={
                "delegator_id": self._agent_id,
                "timeout_seconds": timeout,
            },
        )

        # Track active delegation
        async with self._lock:
            self._active_delegations[delegation_msg.task_id] = delegation_msg

        try:
            # Send delegation and wait for result
            reply = await self._channel.send_and_wait_reply(
                recipient_agent_id=worker_agent_id,
                payload=delegation_msg.to_dict(),
                timeout_seconds=timeout,
            )

            # Parse result
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            result_data = reply.payload

            if result_data.get("message_type") == DelegationMessageType.TASK_ERROR.value:
                return DelegationResult(
                    task_id=delegation_msg.task_id,
                    worker_agent_id=worker_agent_id,
                    success=False,
                    error=result_data.get("payload", {}).get("error", "Unknown error"),
                    delegation_time_ms=elapsed_ms,
                )

            return DelegationResult(
                task_id=delegation_msg.task_id,
                worker_agent_id=worker_agent_id,
                success=True,
                result=result_data.get("payload", {}).get("result"),
                execution_time_ms=result_data.get("metadata", {}).get("execution_time_ms", 0),
                delegation_time_ms=elapsed_ms,
            )

        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return DelegationResult(
                task_id=delegation_msg.task_id,
                worker_agent_id=worker_agent_id,
                success=False,
                error=f"Task timed out after {timeout}s",
                delegation_time_ms=elapsed_ms,
            )

        finally:
            # Clean up tracking
            async with self._lock:
                self._active_delegations.pop(delegation_msg.task_id, None)

    async def handle_delegation(
        self,
        envelope: SecureMessageEnvelope,
        executor: Callable[[Any, TrustExecutionContext], Any],
    ) -> SecureMessageEnvelope:
        """
        Handle an incoming delegation as a worker.

        Verifies the incoming message, extracts the task and context,
        executes the task, and sends the result.

        Args:
            envelope: Incoming delegation message.
            executor: Async function to execute the task.

        Returns:
            The result message envelope.

        Raises:
            OrchestrationTrustError: If verification fails.
        """
        import time

        start_time = time.perf_counter()

        # Verify incoming message
        result = await self._channel.receive(envelope)
        if not result.is_valid():
            raise OrchestrationTrustError(f"Invalid delegation message: {result.failure_reasons}")

        # Parse delegation message
        delegation_msg = DelegationMessage.from_dict(envelope.payload)

        if delegation_msg.message_type != DelegationMessageType.TASK_DELEGATION:
            raise OrchestrationTrustError(f"Expected TASK_DELEGATION, got {delegation_msg.message_type}")

        # Reconstruct execution context
        context = TrustExecutionContext.from_dict(delegation_msg.context_data)

        # Execute task
        try:
            task_result = await executor(
                delegation_msg.payload.get("task", delegation_msg.payload),
                context,
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Send success result
            result_msg = DelegationMessage.create_result(
                task_id=delegation_msg.task_id,
                result=task_result,
                success=True,
                metadata={"execution_time_ms": elapsed_ms},
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Task execution failed: {e}")

            # Send error result
            result_msg = DelegationMessage.create_result(
                task_id=delegation_msg.task_id,
                result=None,
                success=False,
                error=str(e),
                metadata={"execution_time_ms": elapsed_ms},
            )

        # Send reply
        return await self._channel.send_reply(
            original_message=envelope,
            payload=result_msg.to_dict(),
        )

    async def send_progress(
        self,
        original_message: SecureMessageEnvelope,
        task_id: str,
        progress_percent: float,
        status_message: str,
    ) -> SecureMessageEnvelope:
        """
        Send a progress update for an ongoing task.

        Args:
            original_message: The original delegation message.
            task_id: Task identifier.
            progress_percent: Completion percentage (0-100).
            status_message: Human-readable status.

        Returns:
            The progress message envelope.
        """
        progress_msg = DelegationMessage.create_progress(
            task_id=task_id,
            progress_percent=progress_percent,
            status_message=status_message,
        )

        return await self._channel.send_reply(
            original_message=original_message,
            payload=progress_msg.to_dict(),
        )

    async def revoke_delegation(
        self,
        worker_agent_id: str,
        task_id: str,
        reason: str = "Delegation revoked",
    ) -> SecureMessageEnvelope:
        """
        Revoke a delegation to a worker agent.

        Args:
            worker_agent_id: Worker to revoke.
            task_id: Task identifier to revoke.
            reason: Reason for revocation.

        Returns:
            The revocation message envelope.
        """
        revoke_msg = DelegationMessage(
            message_type=DelegationMessageType.DELEGATION_REVOKED,
            task_id=task_id,
            payload={"reason": reason},
        )

        envelope = await self._channel.send(
            recipient_agent_id=worker_agent_id,
            payload=revoke_msg.to_dict(),
        )

        # Remove from active delegations
        async with self._lock:
            self._active_delegations.pop(task_id, None)

        logger.info(f"Revoked delegation {task_id} from {worker_agent_id}: {reason}")

        return envelope

    def register_handler(
        self,
        message_type: DelegationMessageType,
        handler: Callable,
    ) -> None:
        """
        Register a handler for a delegation message type.

        Args:
            message_type: Type of message to handle.
            handler: Async callable to handle messages.
        """
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)

    async def process_message(
        self,
        envelope: SecureMessageEnvelope,
    ) -> Optional[SecureMessageEnvelope]:
        """
        Process an incoming message through registered handlers.

        Args:
            envelope: Incoming message envelope.

        Returns:
            Optional response envelope.
        """
        # Verify message
        result = await self._channel.receive(envelope)
        if not result.is_valid():
            logger.warning(f"Invalid message rejected: {result.failure_reasons}")
            return None

        # Parse delegation message
        try:
            delegation_msg = DelegationMessage.from_dict(envelope.payload)
        except Exception as e:
            logger.warning(f"Failed to parse delegation message: {e}")
            return None

        # Find handlers
        handlers = self._message_handlers.get(delegation_msg.message_type, [])
        if not handlers:
            logger.debug(f"No handlers for message type {delegation_msg.message_type}")
            return None

        # Execute handlers
        for handler in handlers:
            try:
                result = await handler(delegation_msg, envelope)
                if result:
                    return result
            except Exception as e:
                logger.error(f"Handler error: {e}")

        return None

    def get_active_delegations(self) -> List[DelegationMessage]:
        """Get list of active delegations."""
        return list(self._active_delegations.values())

    def get_statistics(self) -> ChannelStatistics:
        """Get channel statistics."""
        return self._channel.get_statistics()
