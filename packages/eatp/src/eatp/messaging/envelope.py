# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Secure Message Envelope - Signed messages between agents.

This module provides the SecureMessageEnvelope for tamper-proof
agent-to-agent communication with cryptographic signatures.

Key Components:
- SecureMessageEnvelope: Complete signed message with all metadata
- MessageMetadata: Optional metadata (priority, TTL, correlation)
"""

import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


@dataclass
class MessageMetadata:
    """
    Optional metadata for messages.

    Provides additional context and control for message handling
    such as priority, time-to-live, and request/response correlation.

    Attributes:
        priority: Message priority level. Affects processing order
            in queues. Values: "low", "normal", "high", "urgent".
            Default is "normal".

        ttl_seconds: Time-to-live in seconds. Message is considered
            expired after (timestamp + ttl_seconds). Default is 300
            seconds (5 minutes).

        correlation_id: ID for request/response correlation. When
            replying to a message, set this to the original message_id
            to enable the sender to match responses.

        reply_to: Agent ID to reply to if different from sender.
            Useful for proxy or routing scenarios.

        content_type: MIME type of the payload content. Default is
            "application/json".

        encryption: Encryption algorithm used (future). Currently
            None as encryption is not yet implemented.

    Example:
        >>> metadata = MessageMetadata(
        ...     priority="high",
        ...     ttl_seconds=60,
        ...     correlation_id="req-123"
        ... )
        >>> if metadata.is_expired(datetime.now(timezone.utc) + timedelta(seconds=61)):
        ...     print("Message expired!")
    """

    priority: str = "normal"
    ttl_seconds: int = 300
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    content_type: str = "application/json"
    encryption: Optional[str] = None
    # Track when metadata was created for TTL calculations
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def is_expired(self, current_time: datetime) -> bool:
        """
        Check if the message has expired based on TTL.

        Args:
            current_time: Current time to compare against.

        Returns:
            True if message has expired, False otherwise.
        """
        if self.created_at is None:
            return False
        expiry_time = self.created_at + timedelta(seconds=self.ttl_seconds)
        return current_time > expiry_time

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata to dictionary."""
        return {
            "priority": self.priority,
            "ttl_seconds": self.ttl_seconds,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "content_type": self.content_type,
            "encryption": self.encryption,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageMetadata":
        """Deserialize metadata from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            priority=data.get("priority", "normal"),
            ttl_seconds=data.get("ttl_seconds", 300),
            correlation_id=data.get("correlation_id"),
            reply_to=data.get("reply_to"),
            content_type=data.get("content_type", "application/json"),
            encryption=data.get("encryption"),
            created_at=created_at,
        )


@dataclass
class SecureMessageEnvelope:
    """
    Signed message envelope for secure agent-to-agent communication.

    A SecureMessageEnvelope contains all information needed for
    secure message transmission including the payload, cryptographic
    signature, sender/recipient information, and replay protection.

    Attributes:
        message_id: Unique identifier for this message (UUID format).
            Generated automatically if not provided.

        sender_agent_id: Agent ID of the message sender. Must match
            the trust chain used for signing.

        recipient_agent_id: Agent ID of the intended recipient.

        payload: The actual message content. Must be JSON-serializable.

        timestamp: When the message was created (UTC). Used with TTL
            to determine message expiration.

        nonce: Random nonce for replay protection. Generated using
            cryptographically secure random bytes (32 bytes hex).

        signature: Ed25519 signature of the message. Set by the
            MessageSigner after signing.

        signature_algorithm: Algorithm used for signing. Currently
            always "Ed25519".

        trust_chain_hash: Hash of the sender's trust chain at signing
            time. Allows verification that the chain hasn't changed.

        metadata: Optional MessageMetadata with priority, TTL, etc.

    Security:
        - The signing payload is deterministic (same input = same bytes)
        - All fields except signature are included in signing payload
        - Nonces must be cryptographically random
        - Timestamps are UTC to avoid timezone issues

    Example:
        >>> envelope = SecureMessageEnvelope(
        ...     sender_agent_id="agent-001",
        ...     recipient_agent_id="agent-002",
        ...     payload={"action": "execute_task"},
        ...     trust_chain_hash="abc123..."
        ... )
        >>> signing_payload = envelope.get_signing_payload()
        >>> # Sign with Ed25519 private key
    """

    sender_agent_id: str
    recipient_agent_id: str
    payload: Dict[str, Any]
    trust_chain_hash: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    nonce: str = field(default_factory=lambda: secrets.token_hex(32))
    signature: str = ""
    signature_algorithm: str = "Ed25519"
    metadata: Optional[MessageMetadata] = None

    def get_signing_payload(self) -> bytes:
        """
        Generate the canonical signing payload.

        The signing payload is a deterministic byte sequence that
        includes all message fields except the signature itself.
        This ensures:
        - Same message always produces same signing payload
        - Any tampering changes the signing payload
        - Signature can be verified without the original signing

        Format:
            message_id + sender_id + recipient_id + payload_json +
            timestamp_iso + nonce + trust_chain_hash

        Returns:
            UTF-8 encoded bytes of the canonical payload.
        """
        # Serialize payload with sorted keys for determinism
        payload_json = json.dumps(
            self.payload,
            sort_keys=True,
            separators=(",", ":"),  # No whitespace
        )

        # Serialize metadata if present
        metadata_json = ""
        if self.metadata:
            metadata_dict = self.metadata.to_dict()
            metadata_json = json.dumps(
                metadata_dict,
                sort_keys=True,
                separators=(",", ":"),
            )

        # Create canonical string
        canonical = (
            self.message_id
            + self.sender_agent_id
            + self.recipient_agent_id
            + payload_json
            + self.timestamp.isoformat()
            + self.nonce
            + self.trust_chain_hash
            + metadata_json
        )

        return canonical.encode("utf-8")

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize envelope to dictionary.

        Returns:
            Dictionary representation of the envelope.
        """
        return {
            "message_id": self.message_id,
            "sender_agent_id": self.sender_agent_id,
            "recipient_agent_id": self.recipient_agent_id,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "nonce": self.nonce,
            "signature": self.signature,
            "signature_algorithm": self.signature_algorithm,
            "trust_chain_hash": self.trust_chain_hash,
            "metadata": self.metadata.to_dict() if self.metadata else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecureMessageEnvelope":
        """
        Deserialize envelope from dictionary.

        Args:
            data: Dictionary representation of the envelope.

        Returns:
            SecureMessageEnvelope instance.
        """
        timestamp = data["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        metadata = None
        if data.get("metadata"):
            metadata = MessageMetadata.from_dict(data["metadata"])

        return cls(
            message_id=data["message_id"],
            sender_agent_id=data["sender_agent_id"],
            recipient_agent_id=data["recipient_agent_id"],
            payload=data["payload"],
            timestamp=timestamp,
            nonce=data["nonce"],
            signature=data.get("signature", ""),
            signature_algorithm=data.get("signature_algorithm", "Ed25519"),
            trust_chain_hash=data["trust_chain_hash"],
            metadata=metadata,
        )

    def to_json(self) -> str:
        """
        Serialize envelope to JSON string.

        Returns:
            JSON string representation.
        """
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, json_str: str) -> "SecureMessageEnvelope":
        """
        Deserialize envelope from JSON string.

        Args:
            json_str: JSON string representation.

        Returns:
            SecureMessageEnvelope instance.
        """
        return cls.from_dict(json.loads(json_str))

    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        """
        Check if the message has expired.

        Uses metadata TTL if present, otherwise checks if message
        is older than 5 minutes (default TTL).

        Args:
            current_time: Time to compare against. Defaults to now.

        Returns:
            True if message has expired, False otherwise.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        ttl_seconds = 300  # Default 5 minutes
        if self.metadata:
            ttl_seconds = self.metadata.ttl_seconds

        expiry_time = self.timestamp + timedelta(seconds=ttl_seconds)
        return current_time > expiry_time

    def create_reply_metadata(self) -> MessageMetadata:
        """
        Create metadata for a reply to this message.

        Returns:
            MessageMetadata with correlation_id set to this message's ID.
        """
        return MessageMetadata(
            correlation_id=self.message_id,
            priority=self.metadata.priority if self.metadata else "normal",
        )
