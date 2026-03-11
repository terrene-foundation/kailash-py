"""
Kaizen Trust Messaging Module - Secure Agent-to-Agent Communication.

This module provides secure messaging primitives for agent-to-agent
communication with cryptographic signatures, trust verification,
and replay attack protection.

Key Components:
- SecureMessageEnvelope: Signed messages between agents
- MessageSigner: Sign outgoing messages with Ed25519
- MessageVerifier: Verify incoming messages and trust
- ReplayProtection: Prevent message replay attacks
- SecureChannel: High-level communication abstraction

Example:
    from kaizen.trust.messaging import (
        SecureChannel,
        MessageMetadata,
        InMemoryReplayProtection,
    )

    # Create secure channel for an agent
    channel = SecureChannel(
        agent_id="agent-001",
        private_key=agent_private_key,
        trust_operations=trust_ops,
        agent_registry=registry,
        replay_protection=InMemoryReplayProtection(),
    )

    # Send message to another agent
    envelope = await channel.send(
        recipient_agent_id="agent-002",
        payload={"action": "execute_task", "task_id": "task-123"},
        metadata=MessageMetadata(priority="high")
    )

    # Receive and verify message
    result = await channel.receive(envelope)
    if result.is_valid():
        # Process message
        pass
"""

from kaizen.trust.messaging.channel import ChannelStatistics, SecureChannel
from kaizen.trust.messaging.envelope import MessageMetadata, SecureMessageEnvelope
from kaizen.trust.messaging.exceptions import (
    ChannelError,
    MessageExpiredError,
    MessagingError,
    PublicKeyNotFoundError,
    ReplayDetectedError,
    SigningError,
    VerificationError,
)
from kaizen.trust.messaging.replay_protection import (
    InMemoryReplayProtection,
    ReplayProtection,
)
from kaizen.trust.messaging.signer import MessageSigner
from kaizen.trust.messaging.verifier import MessageVerificationResult, MessageVerifier

__all__ = [
    # Envelope
    "SecureMessageEnvelope",
    "MessageMetadata",
    # Signer
    "MessageSigner",
    # Verifier
    "MessageVerifier",
    "MessageVerificationResult",
    # Replay Protection
    "ReplayProtection",
    "InMemoryReplayProtection",
    # Channel
    "SecureChannel",
    "ChannelStatistics",
    # Exceptions
    "MessagingError",
    "SigningError",
    "VerificationError",
    "ReplayDetectedError",
    "MessageExpiredError",
    "PublicKeyNotFoundError",
    "ChannelError",
]
