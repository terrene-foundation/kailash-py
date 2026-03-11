"""
Unit tests for SecureChannel.

Tests cover the intent of secure channels:
- Sending signed messages
- Receiving and verifying messages
- Request/response correlation
- Channel statistics tracking
- Auto-audit integration

Note: These are unit tests (Tier 1), mocking is allowed.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.trust.messaging.channel import ChannelStatistics, SecureChannel
from kaizen.trust.messaging.envelope import MessageMetadata, SecureMessageEnvelope
from kaizen.trust.messaging.replay_protection import InMemoryReplayProtection
from kaizen.trust.messaging.verifier import MessageVerificationResult

# Module-level patch for sign function in unit tests
SIGN_MOCK_PATCH = "kaizen.trust.messaging.signer.sign"


class TestChannelStatistics:
    """Tests for ChannelStatistics dataclass."""

    def test_default_values(self):
        """Statistics have zero defaults."""
        stats = ChannelStatistics()

        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.messages_verified == 0
        assert stats.messages_rejected == 0
        assert stats.replay_attacks_prevented == 0
        assert stats.since is not None

    def test_to_dict_serialization(self):
        """Statistics can be serialized to dictionary."""
        stats = ChannelStatistics(
            messages_sent=10,
            messages_received=8,
            messages_verified=7,
            messages_rejected=1,
            replay_attacks_prevented=2,
        )

        data = stats.to_dict()

        assert data["messages_sent"] == 10
        assert data["messages_received"] == 8
        assert data["messages_verified"] == 7
        assert data["messages_rejected"] == 1
        assert data["replay_attacks_prevented"] == 2
        assert "uptime_seconds" in data


class TestSecureChannel:
    """Tests for SecureChannel class."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock TrustOperations."""
        trust_ops = MagicMock()
        trust_ops.get_chain = AsyncMock()
        trust_ops.verify = AsyncMock()
        trust_ops.audit = AsyncMock()

        # Setup chain mock
        chain = MagicMock()
        chain.compute_hash.return_value = "chain-hash"
        chain.genesis.agent_id = "agent-001"
        chain.genesis.public_key = "00" * 32
        chain.capability_attestations = []
        trust_ops.get_chain.return_value = chain
        trust_ops.verify.return_value = MagicMock(valid=True, reason=None)

        return trust_ops

    @pytest.fixture
    def mock_registry(self):
        """Create mock AgentRegistry."""
        registry = MagicMock()
        registry.get = AsyncMock(return_value=MagicMock(public_key="00" * 32))
        return registry

    @pytest.fixture
    def replay_protection(self):
        """Create replay protection."""
        return InMemoryReplayProtection()

    @pytest.fixture
    def channel(self, mock_trust_ops, mock_registry, replay_protection):
        """Create SecureChannel."""
        return SecureChannel(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
            agent_registry=mock_registry,
            replay_protection=replay_protection,
            auto_audit=False,  # Disable for unit tests
        )

    @pytest.mark.asyncio
    @patch(SIGN_MOCK_PATCH)
    async def test_send_creates_signed_envelope(self, mock_sign, channel):
        """send() creates a signed envelope."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        envelope = await channel.send(
            recipient_agent_id="agent-002",
            payload={"action": "test"},
        )

        assert isinstance(envelope, SecureMessageEnvelope)
        assert envelope.sender_agent_id == "agent-001"
        assert envelope.recipient_agent_id == "agent-002"
        assert envelope.signature != ""

    @pytest.mark.asyncio
    @patch(SIGN_MOCK_PATCH)
    async def test_send_increments_statistics(self, mock_sign, channel):
        """send() increments messages_sent counter."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="
        stats_before = channel.get_statistics().messages_sent

        await channel.send(
            recipient_agent_id="agent-002",
            payload={},
        )

        stats_after = channel.get_statistics().messages_sent
        assert stats_after == stats_before + 1

    @pytest.mark.asyncio
    @patch(SIGN_MOCK_PATCH)
    async def test_send_preserves_metadata(self, mock_sign, channel):
        """send() preserves provided metadata."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="
        metadata = MessageMetadata(priority="urgent", ttl_seconds=30)

        envelope = await channel.send(
            recipient_agent_id="agent-002",
            payload={},
            metadata=metadata,
        )

        assert envelope.metadata.priority == "urgent"
        assert envelope.metadata.ttl_seconds == 30

    @pytest.mark.asyncio
    async def test_receive_increments_statistics(
        self, channel, mock_trust_ops, mock_registry
    ):
        """receive() increments messages_received counter."""
        # Create a valid envelope
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-002",
            recipient_agent_id="agent-001",
            payload={},
            trust_chain_hash="chain-hash",
            signature="b" * 128,
        )

        # Setup chain for sender
        sender_chain = MagicMock()
        sender_chain.compute_hash.return_value = "chain-hash"
        sender_chain.genesis.agent_id = "agent-002"
        sender_chain.genesis.public_key = "00" * 32
        mock_trust_ops.get_chain.return_value = sender_chain

        stats_before = channel.get_statistics().messages_received

        await channel.receive(envelope)

        stats_after = channel.get_statistics().messages_received
        assert stats_after == stats_before + 1

    @pytest.mark.asyncio
    @patch(SIGN_MOCK_PATCH)
    async def test_send_reply_sets_correlation_id(self, mock_sign, channel):
        """send_reply() sets correlation_id to original message_id."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        original = SecureMessageEnvelope(
            message_id="original-id",
            sender_agent_id="agent-002",
            recipient_agent_id="agent-001",
            payload={},
            trust_chain_hash="hash",
        )

        reply = await channel.send_reply(
            original_message=original,
            payload={"status": "ok"},
        )

        assert reply.metadata.correlation_id == original.message_id

    @pytest.mark.asyncio
    @patch(SIGN_MOCK_PATCH)
    async def test_send_reply_addresses_to_sender(self, mock_sign, channel):
        """send_reply() addresses reply to original sender."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        original = SecureMessageEnvelope(
            sender_agent_id="agent-002",
            recipient_agent_id="agent-001",
            payload={},
            trust_chain_hash="hash",
        )

        reply = await channel.send_reply(
            original_message=original,
            payload={},
        )

        assert reply.recipient_agent_id == "agent-002"

    @pytest.mark.asyncio
    async def test_get_statistics_returns_current_stats(self, channel):
        """get_statistics() returns current channel statistics."""
        stats = channel.get_statistics()

        assert isinstance(stats, ChannelStatistics)
        assert stats.messages_sent == 0

    @pytest.mark.asyncio
    @patch(SIGN_MOCK_PATCH)
    async def test_reset_statistics_clears_counters(self, mock_sign, channel):
        """reset_statistics() resets all counters."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        # Send some messages to increment counters
        await channel.send("agent-002", {})
        await channel.send("agent-002", {})

        assert channel.get_statistics().messages_sent == 2

        channel.reset_statistics()

        assert channel.get_statistics().messages_sent == 0

    def test_agent_id_property(self, channel):
        """agent_id property returns channel's agent ID."""
        assert channel.agent_id == "agent-001"


class TestSecureChannelAutoAudit:
    """Tests for auto-audit functionality."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock TrustOperations with audit."""
        trust_ops = MagicMock()
        trust_ops.get_chain = AsyncMock()
        trust_ops.verify = AsyncMock()
        trust_ops.audit = AsyncMock()

        chain = MagicMock()
        chain.compute_hash.return_value = "chain-hash"
        trust_ops.get_chain.return_value = chain

        return trust_ops

    @pytest.mark.asyncio
    @patch(SIGN_MOCK_PATCH)
    async def test_auto_audit_on_send(self, mock_sign, mock_trust_ops):
        """Auto-audit records send operations."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        registry = MagicMock()
        registry.get = AsyncMock(return_value=None)

        channel = SecureChannel(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
            agent_registry=registry,
            replay_protection=InMemoryReplayProtection(),
            auto_audit=True,
        )

        await channel.send("agent-002", {"action": "test"})

        mock_trust_ops.audit.assert_called_once()
        call_args = mock_trust_ops.audit.call_args
        assert call_args.kwargs["action"] == "message_send"


class TestSendAndWaitReply:
    """Tests for send_and_wait_reply functionality."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock TrustOperations."""
        trust_ops = MagicMock()
        trust_ops.get_chain = AsyncMock()
        trust_ops.verify = AsyncMock()
        trust_ops.audit = AsyncMock()

        chain = MagicMock()
        chain.compute_hash.return_value = "chain-hash"
        chain.genesis.agent_id = "agent-001"
        chain.genesis.public_key = "00" * 32
        trust_ops.get_chain.return_value = chain
        trust_ops.verify.return_value = MagicMock(valid=True, reason=None)

        return trust_ops

    @pytest.fixture
    def mock_registry(self):
        """Create mock AgentRegistry."""
        registry = MagicMock()
        registry.get = AsyncMock(return_value=MagicMock(public_key="00" * 32))
        return registry

    @pytest.mark.asyncio
    @patch(SIGN_MOCK_PATCH)
    async def test_send_and_wait_reply_timeout(
        self, mock_sign, mock_trust_ops, mock_registry
    ):
        """send_and_wait_reply raises TimeoutError on timeout."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        channel = SecureChannel(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
            agent_registry=mock_registry,
            replay_protection=InMemoryReplayProtection(),
            auto_audit=False,
        )

        with pytest.raises(asyncio.TimeoutError):
            await channel.send_and_wait_reply(
                recipient_agent_id="agent-002",
                payload={},
                timeout_seconds=0.1,  # Very short timeout
            )

    @pytest.mark.asyncio
    @patch(SIGN_MOCK_PATCH)
    async def test_reply_matched_by_correlation_id(
        self, mock_sign, mock_trust_ops, mock_registry
    ):
        """Reply with matching correlation_id is matched to request."""
        mock_sign.return_value = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQ=="

        channel = SecureChannel(
            agent_id="agent-001",
            private_key=b"x" * 32,
            trust_operations=mock_trust_ops,
            agent_registry=mock_registry,
            replay_protection=InMemoryReplayProtection(),
            auto_audit=False,
        )

        # Send request and capture the message_id
        request_envelope = await channel.send("agent-002", {"question": "status?"})

        # Simulate receiving a reply (would normally come from network)
        reply = SecureMessageEnvelope(
            sender_agent_id="agent-002",
            recipient_agent_id="agent-001",
            payload={"answer": "ok"},
            trust_chain_hash="chain-hash",
            signature="b" * 128,
            metadata=MessageMetadata(correlation_id=request_envelope.message_id),
        )

        # Setup chain for reply sender
        sender_chain = MagicMock()
        sender_chain.compute_hash.return_value = "chain-hash"
        sender_chain.genesis.agent_id = "agent-002"
        sender_chain.genesis.public_key = "00" * 32
        mock_trust_ops.get_chain.return_value = sender_chain

        # Receive should match the reply
        result = await channel.receive(reply)

        # The reply should be received successfully
        assert result is not None
