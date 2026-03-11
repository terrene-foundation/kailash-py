"""
Unit tests for MessageSigner.

Tests cover the intent of message signing:
- Creating cryptographically signed messages
- Generating unique message IDs and nonces
- Integrating with trust chain for hash inclusion
- Creating reply messages with correlation

Note: These are unit tests (Tier 1), mocking is allowed.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.trust.exceptions import TrustChainNotFoundError
from kaizen.trust.messaging.envelope import MessageMetadata, SecureMessageEnvelope
from kaizen.trust.messaging.exceptions import SigningError
from kaizen.trust.messaging.signer import MessageSigner


class TestMessageSignerInitialization:
    """Tests for MessageSigner initialization."""

    def test_signer_stores_agent_id(self):
        """Signer stores the agent ID."""
        trust_ops = MagicMock()

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=trust_ops,
        )

        assert signer.agent_id == "agent-001"


class TestSignMessage:
    """Tests for sign_message method."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock TrustOperations."""
        trust_ops = MagicMock()
        trust_ops.get_chain = AsyncMock()
        return trust_ops

    @pytest.fixture
    def mock_chain(self):
        """Create mock trust chain."""
        chain = MagicMock()
        chain.compute_hash.return_value = "chain-hash-123"
        return chain

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_message_creates_envelope(
        self, mock_sign, mock_trust_ops, mock_chain
    ):
        """sign_message creates a SecureMessageEnvelope."""
        mock_trust_ops.get_chain.return_value = mock_chain
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="  # base64-encoded signature

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        envelope = await signer.sign_message(
            recipient_agent_id="agent-002",
            payload={"action": "test"},
        )

        assert isinstance(envelope, SecureMessageEnvelope)
        assert envelope.sender_agent_id == "agent-001"
        assert envelope.recipient_agent_id == "agent-002"
        assert envelope.payload == {"action": "test"}

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_message_generates_unique_id(
        self, mock_sign, mock_trust_ops, mock_chain
    ):
        """Each signed message has a unique message_id."""
        mock_trust_ops.get_chain.return_value = mock_chain
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        envelope1 = await signer.sign_message(
            recipient_agent_id="agent-002",
            payload={},
        )
        envelope2 = await signer.sign_message(
            recipient_agent_id="agent-002",
            payload={},
        )

        assert envelope1.message_id != envelope2.message_id

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_message_generates_unique_nonce(
        self, mock_sign, mock_trust_ops, mock_chain
    ):
        """Each signed message has a unique nonce."""
        mock_trust_ops.get_chain.return_value = mock_chain
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        envelope1 = await signer.sign_message(
            recipient_agent_id="agent-002",
            payload={},
        )
        envelope2 = await signer.sign_message(
            recipient_agent_id="agent-002",
            payload={},
        )

        assert envelope1.nonce != envelope2.nonce

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_message_includes_trust_chain_hash(
        self, mock_sign, mock_trust_ops, mock_chain
    ):
        """Signed message includes current trust chain hash."""
        mock_trust_ops.get_chain.return_value = mock_chain
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        envelope = await signer.sign_message(
            recipient_agent_id="agent-002",
            payload={},
        )

        assert envelope.trust_chain_hash == "chain-hash-123"

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_message_sets_signature(
        self, mock_sign, mock_trust_ops, mock_chain
    ):
        """Signed message has non-empty signature."""
        mock_trust_ops.get_chain.return_value = mock_chain
        # sign() returns base64-encoded string - 64 bytes = 88 chars base64
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        envelope = await signer.sign_message(
            recipient_agent_id="agent-002",
            payload={},
        )

        assert envelope.signature != ""
        # Signature is base64-encoded (88 chars for 64 bytes)
        assert len(envelope.signature) == 88

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_message_preserves_metadata(
        self, mock_sign, mock_trust_ops, mock_chain
    ):
        """Signed message preserves provided metadata."""
        mock_trust_ops.get_chain.return_value = mock_chain
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        metadata = MessageMetadata(priority="urgent", ttl_seconds=30)
        envelope = await signer.sign_message(
            recipient_agent_id="agent-002",
            payload={},
            metadata=metadata,
        )

        assert envelope.metadata.priority == "urgent"
        assert envelope.metadata.ttl_seconds == 30

    @pytest.mark.asyncio
    async def test_sign_message_fails_without_trust_chain(self, mock_trust_ops):
        """Signing fails when agent has no trust chain."""
        mock_trust_ops.get_chain.return_value = None

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        with pytest.raises(SigningError) as exc_info:
            await signer.sign_message(
                recipient_agent_id="agent-002",
                payload={},
            )

        assert "agent-001" in str(exc_info.value)


class TestSignReply:
    """Tests for sign_reply method."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock TrustOperations."""
        trust_ops = MagicMock()
        trust_ops.get_chain = AsyncMock()
        chain = MagicMock()
        chain.compute_hash.return_value = "chain-hash-123"
        trust_ops.get_chain.return_value = chain
        return trust_ops

    @pytest.fixture
    def original_message(self):
        """Create original message to reply to."""
        return SecureMessageEnvelope(
            message_id="original-msg-id",
            sender_agent_id="agent-002",
            recipient_agent_id="agent-001",
            payload={"question": "status?"},
            trust_chain_hash="original-hash",
            signature="original-sig",
        )

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_reply_sets_correlation_id(
        self, mock_sign, mock_trust_ops, original_message
    ):
        """Reply has correlation_id set to original message_id."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        reply = await signer.sign_reply(
            original_message=original_message,
            payload={"answer": "ok"},
        )

        assert reply.metadata.correlation_id == original_message.message_id

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_reply_sends_to_original_sender(
        self, mock_sign, mock_trust_ops, original_message
    ):
        """Reply is addressed to original sender."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        reply = await signer.sign_reply(
            original_message=original_message,
            payload={"answer": "ok"},
        )

        assert reply.recipient_agent_id == original_message.sender_agent_id

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_reply_respects_reply_to(self, mock_sign, mock_trust_ops):
        """Reply is sent to reply_to if specified."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        original = SecureMessageEnvelope(
            sender_agent_id="agent-002",
            recipient_agent_id="agent-001",
            payload={},
            trust_chain_hash="hash",
            metadata=MessageMetadata(reply_to="agent-003"),
        )

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        reply = await signer.sign_reply(
            original_message=original,
            payload={"answer": "ok"},
        )

        assert reply.recipient_agent_id == "agent-003"

    @pytest.mark.asyncio
    @patch("kaizen.trust.messaging.signer.sign")
    async def test_sign_reply_preserves_custom_metadata(
        self, mock_sign, mock_trust_ops, original_message
    ):
        """Reply preserves custom metadata when provided."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        signer = MessageSigner(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
        )

        custom_metadata = MessageMetadata(priority="high", ttl_seconds=10)
        reply = await signer.sign_reply(
            original_message=original_message,
            payload={},
            metadata=custom_metadata,
        )

        assert reply.metadata.priority == "high"
        assert reply.metadata.ttl_seconds == 10
        # correlation_id should be set
        assert reply.metadata.correlation_id == original_message.message_id
