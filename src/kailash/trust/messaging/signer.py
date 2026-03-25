# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Message Signer - Sign outgoing messages with Ed25519.

This module provides the MessageSigner for creating cryptographically
signed messages that can be verified by recipients.

Key Features:
- Ed25519 signature generation
- Trust chain hash integration
- Reply message support with correlation
"""

import base64
import logging
from typing import Any, Dict, Optional, Union

from kailash.trust.signing.crypto import sign
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.messaging.envelope import MessageMetadata, SecureMessageEnvelope
from kailash.trust.messaging.exceptions import SigningError
from kailash.trust.operations import TrustOperations

logger = logging.getLogger(__name__)


class MessageSigner:
    """
    Signs outgoing messages with Ed25519.

    The MessageSigner creates SecureMessageEnvelopes with cryptographic
    signatures that can be verified by recipients. It integrates with
    the trust system to include the sender's trust chain hash.

    Attributes:
        agent_id: The signing agent's identifier.

    Example:
        >>> signer = MessageSigner(
        ...     agent_id="agent-001",
        ...     private_key=agent_private_key,
        ...     trust_operations=trust_ops
        ... )
        >>> envelope = await signer.sign_message(
        ...     recipient_agent_id="agent-002",
        ...     payload={"action": "execute_task"}
        ... )
        >>> assert envelope.signature != ""
    """

    def __init__(
        self,
        agent_id: str,
        private_key: Union[bytes, str],
        trust_operations: TrustOperations,
    ):
        """
        Initialize the MessageSigner.

        Args:
            agent_id: The signing agent's identifier. Must match
                the agent's trust chain.

            private_key: Ed25519 private key for signing. Can be:
                - Raw bytes (32 bytes) - will be base64 encoded
                - Base64-encoded string - used directly
                This key must correspond to the public key in the
                agent's trust chain.

            trust_operations: TrustOperations instance for retrieving
                the agent's trust chain and hash.
        """
        self._agent_id = agent_id
        # Convert bytes to base64 string if needed (sign() expects base64 string)
        if isinstance(private_key, bytes):
            self._private_key = base64.b64encode(private_key).decode("utf-8")
        else:
            self._private_key = private_key
        del private_key  # Clear raw key material from local scope
        self._trust_ops = trust_operations

    @property
    def agent_id(self) -> str:
        """The signing agent's identifier."""
        return self._agent_id

    async def sign_message(
        self,
        recipient_agent_id: str,
        payload: Dict[str, Any],
        metadata: Optional[MessageMetadata] = None,
    ) -> SecureMessageEnvelope:
        """
        Create and sign a message to another agent.

        This method:
        1. Retrieves the current trust chain hash
        2. Creates a SecureMessageEnvelope with all fields
        3. Computes the signing payload
        4. Signs with Ed25519 private key
        5. Returns the signed envelope

        Args:
            recipient_agent_id: Agent ID of the recipient.

            payload: Message content. Must be JSON-serializable.

            metadata: Optional message metadata (priority, TTL, etc.).
                If not provided, default metadata is used.

        Returns:
            Signed SecureMessageEnvelope ready for transmission.

        Raises:
            SigningError: If signing fails (e.g., missing trust chain).

        Example:
            >>> envelope = await signer.sign_message(
            ...     recipient_agent_id="agent-002",
            ...     payload={"action": "query", "params": {"table": "users"}},
            ...     metadata=MessageMetadata(priority="high", ttl_seconds=60)
            ... )
        """
        try:
            # Get current trust chain hash
            trust_chain_hash = await self._get_current_trust_chain_hash()

            # Create envelope (message_id, nonce, timestamp auto-generated)
            envelope = SecureMessageEnvelope(
                sender_agent_id=self._agent_id,
                recipient_agent_id=recipient_agent_id,
                payload=payload,
                trust_chain_hash=trust_chain_hash,
                metadata=metadata,
            )

            # Get signing payload
            signing_payload = envelope.get_signing_payload()

            # Sign with Ed25519 - returns base64-encoded string
            signature = sign(signing_payload, self._private_key)  # type: ignore[reportArgumentType]

            # Set signature in envelope (already base64-encoded by sign())
            envelope.signature = signature

            logger.debug(
                f"Signed message {envelope.message_id} from {self._agent_id} to {recipient_agent_id}"
            )

            return envelope

        except TrustChainNotFoundError:
            raise SigningError(
                self._agent_id,
                "Trust chain not found - agent may not be established",
            )
        except Exception as e:
            logger.error(f"Failed to sign message: {e}")
            raise SigningError(self._agent_id, str(e), cause=e)

    async def sign_reply(
        self,
        original_message: SecureMessageEnvelope,
        payload: Dict[str, Any],
        metadata: Optional[MessageMetadata] = None,
    ) -> SecureMessageEnvelope:
        """
        Create and sign a reply to a received message.

        This method creates a reply with the correlation_id set to
        the original message's message_id, enabling request/response
        correlation.

        Args:
            original_message: The message being replied to.

            payload: Reply content. Must be JSON-serializable.

            metadata: Optional message metadata. If not provided,
                creates reply metadata with correlation_id set.

        Returns:
            Signed SecureMessageEnvelope as reply.

        Example:
            >>> # Receive a request
            >>> request = received_envelope
            >>> # Send reply
            >>> reply = await signer.sign_reply(
            ...     original_message=request,
            ...     payload={"status": "completed", "result": "success"}
            ... )
            >>> assert reply.metadata.correlation_id == request.message_id
        """
        # Create reply metadata if not provided
        if metadata is None:
            metadata = original_message.create_reply_metadata()
        elif metadata.correlation_id is None:
            # Set correlation_id if not already set
            metadata.correlation_id = original_message.message_id

        # Get recipient (reply to sender or reply_to if specified)
        recipient = original_message.sender_agent_id
        if original_message.metadata and original_message.metadata.reply_to:
            recipient = original_message.metadata.reply_to

        return await self.sign_message(
            recipient_agent_id=recipient,
            payload=payload,
            metadata=metadata,
        )

    async def _get_current_trust_chain_hash(self) -> str:
        """
        Retrieve the agent's current trust chain hash.

        Returns:
            Hash of the agent's trust chain.

        Raises:
            TrustChainNotFoundError: If agent has no trust chain.
        """
        chain = await self._trust_ops.get_chain(self._agent_id)

        if not chain:
            raise TrustChainNotFoundError(agent_id=self._agent_id)

        return chain.hash()
