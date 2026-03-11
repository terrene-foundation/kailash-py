"""
Unit tests for MessageVerifier.

Tests cover the intent of message verification:
- Verifying cryptographic signatures
- Validating sender trust chains
- Detecting expired messages
- Detecting replay attacks
- Verifying sender capabilities and constraints

Note: These are unit tests (Tier 1), mocking is allowed.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from kaizen.trust.chain import VerificationLevel
from kaizen.trust.messaging.envelope import MessageMetadata, SecureMessageEnvelope
from kaizen.trust.messaging.replay_protection import InMemoryReplayProtection
from kaizen.trust.messaging.verifier import MessageVerificationResult, MessageVerifier


class TestMessageVerificationResult:
    """Tests for MessageVerificationResult dataclass."""

    def test_is_valid_when_all_checks_pass(self):
        """is_valid returns True when all checks pass."""
        result = MessageVerificationResult(
            valid=True,
            signature_valid=True,
            trust_valid=True,
            not_expired=True,
            not_replayed=True,
            sender_verified=True,
        )

        assert result.is_valid() is True

    def test_is_valid_false_when_signature_invalid(self):
        """is_valid returns False when signature is invalid."""
        result = MessageVerificationResult(
            valid=False,
            signature_valid=False,
            trust_valid=True,
            not_expired=True,
            not_replayed=True,
            sender_verified=True,
            errors=["Invalid signature"],
        )

        assert result.is_valid() is False

    def test_is_valid_false_when_trust_invalid(self):
        """is_valid returns False when trust is invalid."""
        result = MessageVerificationResult(
            valid=False,
            signature_valid=True,
            trust_valid=False,
            not_expired=True,
            not_replayed=True,
            sender_verified=True,
        )

        assert result.is_valid() is False

    def test_is_valid_false_when_expired(self):
        """is_valid returns False when message is expired."""
        result = MessageVerificationResult(
            valid=False,
            signature_valid=True,
            trust_valid=True,
            not_expired=False,
            not_replayed=True,
            sender_verified=True,
        )

        assert result.is_valid() is False

    def test_is_valid_false_when_replayed(self):
        """is_valid returns False when message is replayed."""
        result = MessageVerificationResult(
            valid=False,
            signature_valid=True,
            trust_valid=True,
            not_expired=True,
            not_replayed=False,
            sender_verified=True,
        )

        assert result.is_valid() is False

    def test_get_failure_reason_lists_failed_checks(self):
        """get_failure_reason describes all failed checks."""
        result = MessageVerificationResult(
            valid=False,
            signature_valid=False,
            trust_valid=False,
            not_expired=True,
            not_replayed=True,
            sender_verified=True,
            errors=["Signature mismatch", "Trust chain revoked"],
        )

        reason = result.get_failure_reason()

        assert "invalid signature" in reason
        assert "invalid trust chain" in reason
        assert "Signature mismatch" in reason

    def test_get_failure_reason_passed_when_valid(self):
        """get_failure_reason indicates pass when valid."""
        result = MessageVerificationResult(
            valid=True,
            signature_valid=True,
            trust_valid=True,
            not_expired=True,
            not_replayed=True,
            sender_verified=True,
        )

        reason = result.get_failure_reason()

        assert "passed" in reason.lower()


class TestMessageVerifier:
    """Tests for MessageVerifier class."""

    @pytest.fixture
    def mock_trust_ops(self):
        """Create mock TrustOperations."""
        trust_ops = MagicMock()
        trust_ops.get_chain = AsyncMock()
        trust_ops.verify = AsyncMock()
        return trust_ops

    @pytest.fixture
    def mock_registry(self):
        """Create mock AgentRegistry."""
        registry = MagicMock()
        registry.get = AsyncMock()
        return registry

    @pytest.fixture
    def replay_protection(self):
        """Create replay protection."""
        return InMemoryReplayProtection()

    @pytest.fixture
    def verifier(self, mock_trust_ops, mock_registry, replay_protection):
        """Create MessageVerifier."""
        return MessageVerifier(
            trust_operations=mock_trust_ops,
            agent_registry=mock_registry,
            replay_protection=replay_protection,
        )

    @pytest.fixture
    def valid_envelope(self):
        """Create a valid envelope for testing."""
        return SecureMessageEnvelope(
            message_id="test-msg-id",
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={"action": "test"},
            timestamp=datetime.now(timezone.utc),
            nonce="a" * 64,
            signature="b" * 128,  # Hex-encoded 64-byte signature
            trust_chain_hash="chain-hash",
            metadata=MessageMetadata(ttl_seconds=300),
        )

    def setup_valid_mocks(self, mock_trust_ops, mock_registry):
        """Setup mocks for valid verification."""
        # Mock chain with matching hash and public key
        chain = MagicMock()
        chain.compute_hash.return_value = "chain-hash"
        chain.genesis.agent_id = "agent-001"
        chain.genesis.public_key = "00" * 32  # 32-byte public key in hex
        mock_trust_ops.get_chain.return_value = chain

        # Mock verification result
        mock_trust_ops.verify.return_value = MagicMock(valid=True, reason=None)

        # Mock registry with public key
        mock_registry.get.return_value = MagicMock(public_key="00" * 32)

    @pytest.mark.asyncio
    async def test_verify_expired_message_fails(
        self, verifier, mock_trust_ops, mock_registry
    ):
        """Expired message fails verification."""
        self.setup_valid_mocks(mock_trust_ops, mock_registry)

        # Create expired envelope
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            trust_chain_hash="chain-hash",
            signature="b" * 128,
            metadata=MessageMetadata(ttl_seconds=60),
        )

        result = await verifier.verify_message(envelope)

        assert result.not_expired is False
        assert "expired" in result.get_failure_reason().lower()

    @pytest.mark.asyncio
    async def test_verify_future_timestamp_fails(
        self, verifier, mock_trust_ops, mock_registry
    ):
        """Message with future timestamp fails."""
        self.setup_valid_mocks(mock_trust_ops, mock_registry)

        # Create envelope with future timestamp (beyond clock skew tolerance)
        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            timestamp=datetime.now(timezone.utc) + timedelta(minutes=5),
            trust_chain_hash="chain-hash",
            signature="b" * 128,
        )

        result = await verifier.verify_message(envelope)

        assert result.not_expired is False
        assert "future" in result.get_failure_reason().lower()

    @pytest.mark.asyncio
    async def test_verify_replay_detected(
        self, verifier, mock_trust_ops, mock_registry, replay_protection
    ):
        """Replayed message is detected."""
        self.setup_valid_mocks(mock_trust_ops, mock_registry)

        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="chain-hash",
            signature="b" * 128,
        )

        # First verification records the nonce
        await replay_protection.check_nonce(
            envelope.message_id, envelope.nonce, envelope.timestamp
        )

        # Second verification should detect replay
        result = await verifier.verify_message(envelope)

        assert result.not_replayed is False
        assert "replay" in result.get_failure_reason().lower()

    @pytest.mark.asyncio
    async def test_verify_missing_trust_chain_fails(
        self, verifier, mock_trust_ops, mock_registry
    ):
        """Missing trust chain fails verification."""
        mock_trust_ops.get_chain.return_value = None
        mock_registry.get.return_value = None

        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="chain-hash",
            signature="b" * 128,
        )

        result = await verifier.verify_message(envelope)

        # Should fail due to missing public key/trust chain
        assert result.is_valid() is False

    @pytest.mark.asyncio
    async def test_verify_invalid_trust_chain_fails(
        self, verifier, mock_trust_ops, mock_registry
    ):
        """Invalid trust chain fails verification."""
        chain = MagicMock()
        chain.compute_hash.return_value = "chain-hash"
        chain.genesis.agent_id = "agent-001"
        chain.genesis.public_key = "00" * 32
        mock_trust_ops.get_chain.return_value = chain
        mock_trust_ops.verify.return_value = MagicMock(
            valid=False, reason="Trust revoked"
        )
        mock_registry.get.return_value = MagicMock(public_key="00" * 32)

        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="chain-hash",
            signature="b" * 128,
        )

        result = await verifier.verify_message(envelope)

        assert result.trust_valid is False

    @pytest.mark.asyncio
    async def test_verify_sender_mismatch_fails(
        self, verifier, mock_trust_ops, mock_registry
    ):
        """Sender not matching trust chain fails."""
        chain = MagicMock()
        chain.compute_hash.return_value = "chain-hash"
        chain.genesis.agent_id = "different-agent"  # Mismatch
        chain.genesis.public_key = "00" * 32
        mock_trust_ops.get_chain.return_value = chain
        mock_trust_ops.verify.return_value = MagicMock(valid=True, reason=None)
        mock_registry.get.return_value = MagicMock(public_key="00" * 32)

        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="chain-hash",
            signature="b" * 128,
        )

        result = await verifier.verify_message(envelope)

        assert result.sender_verified is False


class TestVerifySenderCapability:
    """Tests for verify_sender_capability method."""

    @pytest.fixture
    def mock_trust_ops(self):
        trust_ops = MagicMock()
        trust_ops.get_chain = AsyncMock()
        return trust_ops

    @pytest.fixture
    def verifier(self, mock_trust_ops):
        registry = MagicMock()
        registry.get = AsyncMock(return_value=None)
        replay_protection = InMemoryReplayProtection()
        return MessageVerifier(
            trust_operations=mock_trust_ops,
            agent_registry=registry,
            replay_protection=replay_protection,
        )

    @pytest.mark.asyncio
    async def test_sender_has_capability(self, verifier, mock_trust_ops):
        """Returns True when sender has capability."""
        # Mock chain with capability
        attestation = MagicMock()
        attestation.capability = "execute_task"
        attestation.expires_at = None

        chain = MagicMock()
        chain.capability_attestations = [attestation]
        mock_trust_ops.get_chain.return_value = chain

        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash",
        )

        result = await verifier.verify_sender_capability(envelope, "execute_task")

        assert result is True

    @pytest.mark.asyncio
    async def test_sender_missing_capability(self, verifier, mock_trust_ops):
        """Returns False when sender lacks capability."""
        # Mock chain without required capability
        attestation = MagicMock()
        attestation.capability = "read_data"
        attestation.expires_at = None

        chain = MagicMock()
        chain.capability_attestations = [attestation]
        mock_trust_ops.get_chain.return_value = chain

        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash",
        )

        result = await verifier.verify_sender_capability(envelope, "admin_access")

        assert result is False

    @pytest.mark.asyncio
    async def test_expired_capability_not_valid(self, verifier, mock_trust_ops):
        """Returns False when capability has expired."""
        # Mock chain with expired capability
        attestation = MagicMock()
        attestation.capability = "execute_task"
        attestation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        chain = MagicMock()
        chain.capability_attestations = [attestation]
        mock_trust_ops.get_chain.return_value = chain

        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash",
        )

        result = await verifier.verify_sender_capability(envelope, "execute_task")

        assert result is False


class TestVerifySenderConstraints:
    """Tests for verify_sender_constraints method."""

    @pytest.fixture
    def mock_trust_ops(self):
        trust_ops = MagicMock()
        trust_ops.verify = AsyncMock()
        return trust_ops

    @pytest.fixture
    def verifier(self, mock_trust_ops):
        registry = MagicMock()
        registry.get = AsyncMock(return_value=None)
        replay_protection = InMemoryReplayProtection()
        return MessageVerifier(
            trust_operations=mock_trust_ops,
            agent_registry=registry,
            replay_protection=replay_protection,
        )

    @pytest.mark.asyncio
    async def test_action_allowed_by_constraints(self, verifier, mock_trust_ops):
        """Returns True when action is allowed."""
        mock_trust_ops.verify.return_value = MagicMock(valid=True)

        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash",
        )

        result = await verifier.verify_sender_constraints(
            envelope, action="read", resource="/data"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_action_blocked_by_constraints(self, verifier, mock_trust_ops):
        """Returns False when action is blocked."""
        mock_trust_ops.verify.return_value = MagicMock(valid=False)

        envelope = SecureMessageEnvelope(
            sender_agent_id="agent-001",
            recipient_agent_id="agent-002",
            payload={},
            trust_chain_hash="hash",
        )

        result = await verifier.verify_sender_constraints(
            envelope, action="write", resource="/data"
        )

        assert result is False
