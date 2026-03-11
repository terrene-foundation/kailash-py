"""
Unit tests for SecureMessageEnvelope and MessageMetadata.

Tests cover the intent of message envelopes:
- Creating tamper-proof message containers
- Deterministic signing payload generation
- Serialization/deserialization roundtrips
- Message expiration logic

Note: These are unit tests (Tier 1), no external dependencies.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from kaizen.trust.messaging.envelope import MessageMetadata, SecureMessageEnvelope


class TestMessageMetadata:
    """Tests for MessageMetadata dataclass."""

    def test_default_values(self):
        """Metadata has sensible defaults."""
        metadata = MessageMetadata()

        assert metadata.priority == "normal"
        assert metadata.ttl_seconds == 300
        assert metadata.correlation_id is None
        assert metadata.reply_to is None
        assert metadata.content_type == "application/json"
        assert metadata.encryption is None
        assert metadata.created_at is not None

    def test_custom_values(self):
        """Metadata accepts custom values."""
        metadata = MessageMetadata(
            priority="high",
            ttl_seconds=60,
            correlation_id="req-123",
            reply_to="agent-003",
            content_type="text/plain",
        )

        assert metadata.priority == "high"
        assert metadata.ttl_seconds == 60
        assert metadata.correlation_id == "req-123"
        assert metadata.reply_to == "agent-003"

    def test_is_expired_false_when_fresh(self):
        """Fresh message is not expired."""
        metadata = MessageMetadata(ttl_seconds=300)

        assert metadata.is_expired(datetime.now(timezone.utc)) is False

    def test_is_expired_true_when_old(self):
        """Old message is expired."""
        metadata = MessageMetadata(ttl_seconds=60)

        future_time = datetime.now(timezone.utc) + timedelta(seconds=61)
        assert metadata.is_expired(future_time) is True

    def test_to_dict_serialization(self):
        """Metadata can be serialized to dictionary."""
        metadata = MessageMetadata(
            priority="urgent",
            ttl_seconds=30,
            correlation_id="corr-456",
        )

        data = metadata.to_dict()

        assert data["priority"] == "urgent"
        assert data["ttl_seconds"] == 30
        assert data["correlation_id"] == "corr-456"

    def test_from_dict_deserialization(self):
        """Metadata can be deserialized from dictionary."""
        data = {
            "priority": "low",
            "ttl_seconds": 600,
            "correlation_id": "test-id",
            "created_at": "2024-01-01T12:00:00",
        }

        metadata = MessageMetadata.from_dict(data)

        assert metadata.priority == "low"
        assert metadata.ttl_seconds == 600
        assert metadata.correlation_id == "test-id"


class TestSecureMessageEnvelope:
    """Tests for SecureMessageEnvelope dataclass."""

    def test_envelope_creation_with_required_fields(self):
        """Envelope can be created with required fields only."""
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={"action": "test"},
            trust_chain_hash="hash123",
        )

        assert envelope.sender_agent_id == "agent-001"
        assert envelope.recipient_agent_id == "agent-002"
        assert envelope.payload == {"action": "test"}
        assert envelope.trust_chain_hash == "hash123"

    def test_envelope_auto_generates_id_and_nonce(self):
        """Envelope auto-generates message_id and nonce."""
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash123",
        )

        # UUID format (36 chars with hyphens)
        assert len(envelope.message_id) == 36
        # Nonce is 64 hex chars (32 bytes)
        assert len(envelope.nonce) == 64

    def test_envelope_auto_generates_timestamp(self):
        """Envelope auto-generates timestamp."""
        before = datetime.now(timezone.utc)
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash123",
        )
        after = datetime.now(timezone.utc)

        assert before <= envelope.timestamp <= after

    def test_envelope_with_metadata(self):
        """Envelope can include metadata."""
        metadata = MessageMetadata(priority="high")
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash123",
            metadata=metadata,
        )

        assert envelope.metadata.priority == "high"

    def test_get_signing_payload_returns_bytes(self):
        """Signing payload is returned as bytes."""
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={"key": "value"},
            trust_chain_hash="hash123",
        )

        payload = envelope.get_signing_payload()

        assert isinstance(payload, bytes)
        assert len(payload) > 0

    def test_get_signing_payload_is_deterministic(self):
        """Same envelope produces same signing payload."""
        # Create envelope with fixed values
        envelope = SecureMessageEnvelope(
            message_id="fixed-id",
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={"key": "value"},
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            nonce="a" * 64,
            trust_chain_hash="hash123",
        )

        payload1 = envelope.get_signing_payload()
        payload2 = envelope.get_signing_payload()

        assert payload1 == payload2

    def test_signing_payload_changes_with_payload_change(self):
        """Signing payload changes when message payload changes."""
        envelope1 = SecureMessageEnvelope(
            message_id="fixed-id",
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={"action": "read"},
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            nonce="a" * 64,
            trust_chain_hash="hash123",
        )
        envelope2 = SecureMessageEnvelope(
            message_id="fixed-id",
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={"action": "write"},  # Changed
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            nonce="a" * 64,
            trust_chain_hash="hash123",
        )

        assert envelope1.get_signing_payload() != envelope2.get_signing_payload()

    def test_signing_payload_includes_all_fields(self):
        """Signing payload includes all required fields."""
        envelope = SecureMessageEnvelope(
            message_id="test-id",
            sender_agent_id="sender",
            recipient_agent_id="recipient",
            payload={"data": 123},
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            nonce="nonce123",
            trust_chain_hash="chain-hash",
        )

        payload = envelope.get_signing_payload().decode("utf-8")

        assert "test-id" in payload
        assert "sender" in payload
        assert "recipient" in payload
        assert "123" in payload
        assert "nonce123" in payload
        assert "chain-hash" in payload

    def test_to_dict_serialization(self):
        """Envelope can be serialized to dictionary."""
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={"action": "test"},
            trust_chain_hash="hash123",
            signature="sig123",
        )

        data = envelope.to_dict()

        assert data["sender_agent_id"] == "agent-001"
        assert data["recipient_agent_id"] == "agent-002"
        assert data["payload"] == {"action": "test"}
        assert data["signature"] == "sig123"
        assert "timestamp" in data
        assert "nonce" in data
        assert "message_id" in data

    def test_from_dict_deserialization(self):
        """Envelope can be deserialized from dictionary."""
        data = {
            "message_id": "msg-123",
            "sender_agent_id": "agent-001",
            "recipient_agent_id": "agent-002",
            "payload": {"key": "value"},
            "timestamp": "2024-01-01T12:00:00",
            "nonce": "abc123",
            "signature": "sig456",
            "signature_algorithm": "Ed25519",
            "trust_chain_hash": "hash789",
        }

        envelope = SecureMessageEnvelope.from_dict(data)

        assert envelope.message_id == "msg-123"
        assert envelope.sender_agent_id == "agent-001"
        assert envelope.payload == {"key": "value"}
        assert envelope.signature == "sig456"

    def test_roundtrip_serialization(self):
        """Envelope survives to_dict -> from_dict roundtrip."""
        original = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={"complex": {"nested": [1, 2, 3]}},
            trust_chain_hash="hash123",
            metadata=MessageMetadata(priority="high"),
        )

        data = original.to_dict()
        restored = SecureMessageEnvelope.from_dict(data)

        assert restored.message_id == original.message_id
        assert restored.sender_agent_id == original.sender_agent_id
        assert restored.payload == original.payload
        assert restored.nonce == original.nonce
        assert restored.metadata.priority == original.metadata.priority

    def test_to_json_returns_string(self):
        """to_json returns JSON string."""
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash123",
        )

        json_str = envelope.to_json()

        assert isinstance(json_str, str)
        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed["sender_agent_id"] == "agent-001"

    def test_from_json_parses_string(self):
        """from_json parses JSON string."""
        json_str = json.dumps(
            {
                "message_id": "msg-1",
                "sender_agent_id": "sender",
                "recipient_agent_id": "recipient",
                "payload": {},
                "timestamp": "2024-01-01T00:00:00",
                "nonce": "nonce",
                "trust_chain_hash": "hash",
            }
        )

        envelope = SecureMessageEnvelope.from_json(json_str)

        assert envelope.message_id == "msg-1"
        assert envelope.sender_agent_id == "sender"

    def test_is_expired_with_default_ttl(self):
        """Envelope expiration uses default TTL when no metadata."""
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash123",
        )

        # Fresh message
        assert envelope.is_expired() is False

        # 6 minutes later (default TTL is 5 minutes)
        future = datetime.now(timezone.utc) + timedelta(minutes=6)
        assert envelope.is_expired(future) is True

    def test_is_expired_with_custom_ttl(self):
        """Envelope expiration respects metadata TTL."""
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash123",
            metadata=MessageMetadata(ttl_seconds=10),
        )

        # 5 seconds - not expired
        assert (
            envelope.is_expired(datetime.now(timezone.utc) + timedelta(seconds=5))
            is False
        )

        # 15 seconds - expired
        assert (
            envelope.is_expired(datetime.now(timezone.utc) + timedelta(seconds=15))
            is True
        )

    def test_create_reply_metadata(self):
        """create_reply_metadata sets correlation_id."""
        original = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash123",
            metadata=MessageMetadata(priority="urgent"),
        )

        reply_metadata = original.create_reply_metadata()

        assert reply_metadata.correlation_id == original.message_id
        assert reply_metadata.priority == "urgent"
