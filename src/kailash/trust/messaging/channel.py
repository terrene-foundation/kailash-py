# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Secure Channel - High-level agent-to-agent communication.

This module provides the SecureChannel abstraction for secure
message exchange between agents, combining signing, verification,
and replay protection.

Key Features:
- Simple send/receive API
- Request/response correlation
- Auto-audit integration
- Channel statistics
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from kailash.trust.chain import ActionResult, VerificationLevel
from kailash.trust.messaging.envelope import MessageMetadata, SecureMessageEnvelope
from kailash.trust.messaging.exceptions import ChannelError
from kailash.trust.messaging.replay_protection import ReplayProtection
from kailash.trust.messaging.signer import MessageSigner
from kailash.trust.messaging.verifier import MessageVerificationResult, MessageVerifier
from kailash.trust.operations import TrustOperations
from kailash.trust.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class ChannelStatistics:
    """
    Statistics for a SecureChannel.

    Tracks message counts and timing for diagnostics.

    Attributes:
        messages_sent: Total messages sent through channel.
        messages_received: Total messages received through channel.
        messages_verified: Messages that passed verification.
        messages_rejected: Messages that failed verification.
        replay_attacks_prevented: Replay attacks detected.
        since: When statistics tracking started.
    """

    messages_sent: int = 0
    messages_received: int = 0
    messages_verified: int = 0
    messages_rejected: int = 0
    replay_attacks_prevented: int = 0
    since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize statistics to dictionary."""
        return {
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "messages_verified": self.messages_verified,
            "messages_rejected": self.messages_rejected,
            "replay_attacks_prevented": self.replay_attacks_prevented,
            "since": self.since.isoformat(),
            "uptime_seconds": (datetime.now(timezone.utc) - self.since).total_seconds(),
        }


class SecureChannel:
    """
    High-level secure communication channel between agents.

    SecureChannel provides a simple API for secure agent-to-agent
    communication, handling signing, verification, replay protection,
    and optional audit logging.

    Features:
    - Send messages with automatic signing
    - Receive and verify messages
    - Request/response correlation
    - Auto-audit of all messages
    - Channel statistics

    Example:
        >>> channel = SecureChannel(
        ...     agent_id="agent-001",
        ...     private_key=agent_private_key,
        ...     trust_operations=trust_ops,
        ...     agent_registry=registry,
        ...     replay_protection=replay_protection
        ... )
        >>> # Send message
        >>> envelope = await channel.send(
        ...     recipient_agent_id="agent-002",
        ...     payload={"action": "execute_task"}
        ... )
        >>> # Receive and verify
        >>> result = await channel.receive(incoming_envelope)
        >>> if result.is_valid():
        ...     process_message(incoming_envelope)
    """

    def __init__(
        self,
        agent_id: str,
        private_key: Union[bytes, str],
        trust_operations: TrustOperations,
        agent_registry: AgentRegistry,
        replay_protection: ReplayProtection,
        verification_level: VerificationLevel = VerificationLevel.STANDARD,
        auto_audit: bool = True,
    ):
        """
        Initialize a SecureChannel.

        Args:
            agent_id: This agent's identifier.

            private_key: Ed25519 private key for signing outgoing
                messages. Can be raw bytes (32 bytes) or base64-encoded string.

            trust_operations: TrustOperations for trust verification
                and audit logging.

            agent_registry: AgentRegistry for agent discovery and
                public key retrieval.

            replay_protection: ReplayProtection for preventing
                replay attacks.

            verification_level: Level of trust verification.
                Default is STANDARD.

            auto_audit: Whether to automatically log all message
                operations to the audit trail. Default is True.
        """
        self._agent_id = agent_id
        self._trust_ops = trust_operations
        self._auto_audit = auto_audit

        # Create signer and verifier
        self._signer = MessageSigner(
            agent_id=agent_id,
            private_key=private_key,
            trust_operations=trust_operations,
        )
        self._verifier = MessageVerifier(
            trust_operations=trust_operations,
            agent_registry=agent_registry,
            replay_protection=replay_protection,
            verification_level=verification_level,
        )

        # Statistics
        self._stats = ChannelStatistics()

        # Pending replies (correlation_id -> Future)
        self._pending_replies: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    @property
    def agent_id(self) -> str:
        """This agent's identifier."""
        return self._agent_id

    async def send(
        self,
        recipient_agent_id: str,
        payload: Dict[str, Any],
        metadata: Optional[MessageMetadata] = None,
    ) -> SecureMessageEnvelope:
        """
        Send a signed message to another agent.

        Args:
            recipient_agent_id: Target agent's identifier.
            payload: Message content.
            metadata: Optional message metadata.

        Returns:
            The signed message envelope.

        Raises:
            ChannelError: If sending fails.
        """
        try:
            envelope = await self._signer.sign_message(
                recipient_agent_id=recipient_agent_id,
                payload=payload,
                metadata=metadata,
            )

            self._stats.messages_sent += 1

            # Auto-audit send
            if self._auto_audit:
                await self._audit_message("send", envelope)

            logger.debug(f"Sent message {envelope.message_id} to {recipient_agent_id}")

            return envelope

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise ChannelError("send", str(e), cause=e)

    async def receive(
        self,
        envelope: SecureMessageEnvelope,
    ) -> MessageVerificationResult:
        """
        Receive and verify an incoming message.

        Args:
            envelope: The received message envelope.

        Returns:
            Verification result with detailed status.

        Raises:
            ChannelError: If verification encounters a critical error.
        """
        try:
            result = await self._verifier.verify_message(envelope)

            self._stats.messages_received += 1

            if result.is_valid():
                self._stats.messages_verified += 1

                # Check if this is a reply to a pending request
                await self._handle_reply(envelope)
            else:
                self._stats.messages_rejected += 1
                if not result.not_replayed:
                    self._stats.replay_attacks_prevented += 1

            # Auto-audit receive
            if self._auto_audit:
                await self._audit_message("receive", envelope, result)

            logger.debug(
                f"Received message {envelope.message_id} from {envelope.sender_agent_id}: valid={result.is_valid()}"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to receive message: {e}")
            raise ChannelError("receive", str(e), cause=e)

    async def send_reply(
        self,
        original_message: SecureMessageEnvelope,
        payload: Dict[str, Any],
        metadata: Optional[MessageMetadata] = None,
    ) -> SecureMessageEnvelope:
        """
        Send a reply to a received message.

        Args:
            original_message: The message being replied to.
            payload: Reply content.
            metadata: Optional reply metadata.

        Returns:
            The signed reply envelope.
        """
        try:
            envelope = await self._signer.sign_reply(
                original_message=original_message,
                payload=payload,
                metadata=metadata,
            )

            self._stats.messages_sent += 1

            if self._auto_audit:
                await self._audit_message("send_reply", envelope)

            logger.debug(
                f"Sent reply {envelope.message_id} to "
                f"{original_message.sender_agent_id} "
                f"(correlation: {original_message.message_id})"
            )

            return envelope

        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
            raise ChannelError("send_reply", str(e), cause=e)

    async def send_and_wait_reply(
        self,
        recipient_agent_id: str,
        payload: Dict[str, Any],
        timeout_seconds: int = 30,
        metadata: Optional[MessageMetadata] = None,
    ) -> SecureMessageEnvelope:
        """
        Send a message and wait for a reply.

        This method sends a message and blocks until a reply with
        matching correlation_id is received, or timeout occurs.

        Args:
            recipient_agent_id: Target agent's identifier.
            payload: Message content.
            timeout_seconds: Maximum time to wait for reply.
            metadata: Optional message metadata.

        Returns:
            The verified reply envelope.

        Raises:
            asyncio.TimeoutError: If no reply within timeout.
            ChannelError: If sending or receiving fails.
        """
        # Send request
        request = await self.send(
            recipient_agent_id=recipient_agent_id,
            payload=payload,
            metadata=metadata,
        )

        # Create future for reply
        reply_future: asyncio.Future = asyncio.get_running_loop().create_future()

        async with self._lock:
            self._pending_replies[request.message_id] = reply_future

        try:
            # Wait for reply with timeout
            reply = await asyncio.wait_for(
                reply_future,
                timeout=timeout_seconds,
            )
            return reply

        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for reply to {request.message_id} after {timeout_seconds}s")
            raise

        finally:
            # Clean up pending reply
            async with self._lock:
                self._pending_replies.pop(request.message_id, None)

    async def _handle_reply(self, envelope: SecureMessageEnvelope) -> None:
        """Check if this envelope is a reply to a pending request."""
        if not envelope.metadata or not envelope.metadata.correlation_id:
            return

        correlation_id = envelope.metadata.correlation_id

        async with self._lock:
            future = self._pending_replies.get(correlation_id)
            if future and not future.done():
                future.set_result(envelope)
                logger.debug(f"Matched reply {envelope.message_id} to request {correlation_id}")

    async def _audit_message(
        self,
        message_type: str,
        envelope: SecureMessageEnvelope,
        result: Optional[MessageVerificationResult] = None,
    ) -> None:
        """Record message operation in audit trail."""
        try:
            action_result = ActionResult.SUCCESS
            if result and not result.is_valid():
                action_result = ActionResult.FAILURE

            metadata = {
                "message_type": message_type,
                "message_id": envelope.message_id,
                "sender": envelope.sender_agent_id,
                "recipient": envelope.recipient_agent_id,
                "timestamp": envelope.timestamp.isoformat(),
            }

            if result:
                metadata["verification_result"] = {
                    "valid": result.valid,
                    "signature_valid": result.signature_valid,
                    "trust_valid": result.trust_valid,
                    "not_expired": result.not_expired,
                    "not_replayed": result.not_replayed,
                }

            await self._trust_ops.audit(
                agent_id=self._agent_id,
                action=f"message_{message_type}",
                result=action_result,
                metadata=metadata,
            )

        except Exception as e:
            # Don't fail message operations due to audit failures
            logger.warning(f"Failed to audit message: {e}")

    def get_statistics(self) -> ChannelStatistics:
        """
        Get channel statistics.

        Returns:
            ChannelStatistics with message counts.
        """
        return self._stats

    def reset_statistics(self) -> None:
        """Reset channel statistics."""
        self._stats = ChannelStatistics()
