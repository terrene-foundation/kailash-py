"""
E2E Integration Tests: Secure Messaging.

Test Intent:
- Verify encrypted messages are properly signed and verified
- Test replay protection prevents message reuse
- Validate delegation message protocol works end-to-end
- Ensure message tampering is detected

These tests use real cryptographic operations - NO MOCKING.
"""

import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from kaizen.trust.crypto import generate_keypair, sign, verify_signature
from kaizen.trust.messaging.envelope import MessageMetadata, SecureMessageEnvelope
from kaizen.trust.messaging.replay_protection import (
    InMemoryReplayProtection,
    ReplayProtection,
)
from kaizen.trust.orchestration.execution_context import TrustExecutionContext
from kaizen.trust.orchestration.integration.secure_channel import (
    DelegationMessage,
    DelegationMessageType,
    DelegationResult,
    SecureOrchestrationChannel,
)


class TestCryptographicOperations:
    """
    Test cryptographic signing and verification with real Ed25519 keys.

    Validates that the crypto module correctly signs and verifies data.
    """

    def test_keypair_generation(self):
        """Keypair should generate valid Ed25519 keys."""
        private_key, public_key = generate_keypair()

        # Keys should be base64-encoded strings
        assert private_key is not None
        assert public_key is not None
        assert len(private_key) > 0
        assert len(public_key) > 0

    def test_sign_and_verify_succeeds(self, test_keypair):
        """Signing and verification should succeed with matching keys."""
        private_key, public_key = test_keypair

        data = {"message": "test", "value": 42}
        signature = sign(data, private_key)

        is_valid = verify_signature(data, signature, public_key)
        assert is_valid is True

    def test_verification_fails_with_wrong_key(self):
        """Signature verification should fail with wrong public key."""
        private_key1, public_key1 = generate_keypair()
        private_key2, public_key2 = generate_keypair()

        data = {"message": "test"}
        signature = sign(data, private_key1)

        # Verify with wrong key
        is_valid = verify_signature(data, signature, public_key2)
        assert is_valid is False

    def test_signature_detects_tampering(self, test_keypair):
        """Modified data should fail signature verification."""
        private_key, public_key = test_keypair

        original_data = {"amount": 100}
        signature = sign(original_data, private_key)

        # Tamper with data
        tampered_data = {"amount": 10000}

        is_valid = verify_signature(tampered_data, signature, public_key)
        assert is_valid is False


class TestReplayProtection:
    """
    Test replay attack prevention.

    Validates that the same message cannot be replayed
    within the protection window.
    """

    @pytest.mark.asyncio
    async def test_first_message_is_accepted(self):
        """First use of nonce should be accepted."""
        protection = InMemoryReplayProtection()

        nonce = secrets.token_hex(32)
        is_new = await protection.check_nonce(
            message_id="msg-001",
            nonce=nonce,
            timestamp=datetime.now(timezone.utc),
        )

        assert is_new is True

    @pytest.mark.asyncio
    async def test_replay_is_rejected(self):
        """Same nonce should be rejected on second use."""
        protection = InMemoryReplayProtection()
        nonce = secrets.token_hex(32)

        # First use - accepted
        is_new1 = await protection.check_nonce(
            message_id="msg-001",
            nonce=nonce,
            timestamp=datetime.now(timezone.utc),
        )
        assert is_new1 is True

        # Replay attempt - rejected
        is_new2 = await protection.check_nonce(
            message_id="msg-002",  # Different message ID
            nonce=nonce,  # Same nonce = replay
            timestamp=datetime.now(timezone.utc),
        )
        assert is_new2 is False

    @pytest.mark.asyncio
    async def test_different_nonces_both_accepted(self):
        """Different nonces should all be accepted."""
        protection = InMemoryReplayProtection()

        nonce1 = secrets.token_hex(32)
        nonce2 = secrets.token_hex(32)
        nonce3 = secrets.token_hex(32)

        result1 = await protection.check_nonce(
            "msg-1", nonce1, datetime.now(timezone.utc)
        )
        result2 = await protection.check_nonce(
            "msg-2", nonce2, datetime.now(timezone.utc)
        )
        result3 = await protection.check_nonce(
            "msg-3", nonce3, datetime.now(timezone.utc)
        )

        assert result1 is True
        assert result2 is True
        assert result3 is True

    @pytest.mark.asyncio
    async def test_nonce_count_tracks_correctly(self):
        """Nonce count should reflect tracked nonces."""
        protection = InMemoryReplayProtection()

        assert protection.get_nonce_count() == 0

        await protection.check_nonce("msg-1", "nonce-1", datetime.now(timezone.utc))
        assert protection.get_nonce_count() == 1

        await protection.check_nonce("msg-2", "nonce-2", datetime.now(timezone.utc))
        assert protection.get_nonce_count() == 2

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_nonces(self):
        """Cleanup should remove nonces older than TTL."""
        protection = InMemoryReplayProtection()

        # Add nonce with old timestamp
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        await protection.check_nonce("msg-old", "nonce-old", old_time)

        # Add recent nonce
        await protection.check_nonce("msg-new", "nonce-new", datetime.now(timezone.utc))

        assert protection.get_nonce_count() == 2

        # Cleanup with 1 hour TTL
        removed = await protection.cleanup_expired_nonces(ttl_seconds=3600)

        assert removed == 1
        assert protection.get_nonce_count() == 1

    @pytest.mark.asyncio
    async def test_clear_removes_all_nonces(self):
        """Clear should remove all tracked nonces."""
        protection = InMemoryReplayProtection()

        await protection.check_nonce("msg-1", "nonce-1", datetime.now(timezone.utc))
        await protection.check_nonce("msg-2", "nonce-2", datetime.now(timezone.utc))

        await protection.clear()

        assert protection.get_nonce_count() == 0


class TestSecureMessageEnvelope:
    """
    Test secure message envelope structure.

    Validates envelope creation, serialization, and integrity.
    """

    def test_envelope_auto_generates_fields(self):
        """Envelope should auto-generate message_id, nonce, timestamp."""
        envelope = SecureMessageEnvelope(
            sender_agent_id="sender-001",
            recipient_agent_id="recipient-001",
            payload={"action": "test"},
            trust_chain_hash="abc123",
        )

        assert envelope.message_id is not None
        assert envelope.nonce is not None
        assert envelope.timestamp is not None
        assert len(envelope.message_id) > 0
        assert len(envelope.nonce) > 0

    def test_envelope_preserves_payload(self):
        """Envelope should preserve payload content."""
        payload = {"action": "analyze", "data": [1, 2, 3]}

        envelope = SecureMessageEnvelope(
            sender_agent_id="sender-001",
            recipient_agent_id="recipient-001",
            payload=payload,
            trust_chain_hash="hash",
        )

        assert envelope.payload == payload

    def test_envelope_serialization_roundtrip(self):
        """Envelope should serialize and deserialize correctly."""
        original = SecureMessageEnvelope(
            sender_agent_id="sender-001",
            recipient_agent_id="recipient-001",
            payload={"data": "test"},
            trust_chain_hash="hash123",
            metadata=MessageMetadata(priority="high"),
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = SecureMessageEnvelope.from_dict(data)

        assert restored.message_id == original.message_id
        assert restored.sender_agent_id == original.sender_agent_id
        assert restored.recipient_agent_id == original.recipient_agent_id
        assert restored.payload == original.payload
        assert restored.nonce == original.nonce

    def test_envelope_signing_payload_is_deterministic(self):
        """Signing payload should be deterministic for same envelope."""
        envelope = SecureMessageEnvelope(
            sender_agent_id="sender-001",
            recipient_agent_id="recipient-001",
            payload={"action": "test"},
            trust_chain_hash="hash",
        )

        payload1 = envelope.get_signing_payload()
        payload2 = envelope.get_signing_payload()

        assert payload1 == payload2


class TestDelegationMessageProtocol:
    """
    Test delegation message protocol for orchestration.

    Validates the message types and format used in
    secure task delegation.
    """

    def test_create_task_delegation_message(self, supervisor_context):
        """Task delegation message should be properly structured."""
        msg = DelegationMessage.create_delegation(
            task={"action": "analyze", "data": [1, 2, 3]},
            context=supervisor_context,
            metadata={"priority": "high"},
        )

        assert msg.message_type == DelegationMessageType.TASK_DELEGATION
        assert msg.task_id is not None
        assert msg.payload["action"] == "analyze"
        assert msg.context_data is not None
        assert msg.metadata["priority"] == "high"

    def test_create_result_message(self):
        """Task result message should capture outcomes."""
        # Success result
        success_msg = DelegationMessage.create_result(
            task_id="task-001",
            result={"status": "completed", "output": "data"},
            success=True,
        )

        assert success_msg.message_type == DelegationMessageType.TASK_RESULT
        assert success_msg.payload["success"] is True
        assert success_msg.payload["result"]["status"] == "completed"

        # Error result
        error_msg = DelegationMessage.create_result(
            task_id="task-002",
            result=None,
            success=False,
            error="Processing failed",
        )

        assert error_msg.message_type == DelegationMessageType.TASK_ERROR
        assert error_msg.payload["success"] is False
        assert error_msg.payload["error"] == "Processing failed"

    def test_create_progress_message(self):
        """Progress message should report execution status."""
        msg = DelegationMessage.create_progress(
            task_id="task-001",
            progress_percent=75.0,
            status_message="Processing 75% complete",
        )

        assert msg.message_type == DelegationMessageType.TASK_PROGRESS
        assert msg.payload["progress_percent"] == 75.0
        assert msg.payload["status_message"] == "Processing 75% complete"

    def test_message_serialization_roundtrip(self, supervisor_context):
        """Messages should survive serialization roundtrip."""
        original = DelegationMessage.create_delegation(
            task={"action": "test"},
            context=supervisor_context,
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = DelegationMessage.from_dict(data)

        assert restored.message_type == original.message_type
        assert restored.task_id == original.task_id
        assert restored.payload == original.payload


class TestDelegationResult:
    """
    Test delegation result structure.

    Validates result tracking and metrics.
    """

    def test_successful_delegation_result(self):
        """Successful result should contain output."""
        result = DelegationResult(
            task_id="task-001",
            worker_agent_id="worker-001",
            success=True,
            result={"data": "output"},
            execution_time_ms=150.5,
            delegation_time_ms=200.0,
        )

        assert result.success is True
        assert result.result["data"] == "output"
        assert result.error is None
        assert result.execution_time_ms == 150.5

    def test_failed_delegation_result(self):
        """Failed result should contain error."""
        result = DelegationResult(
            task_id="task-001",
            worker_agent_id="worker-001",
            success=False,
            error="Task timed out",
            delegation_time_ms=60000.0,
        )

        assert result.success is False
        assert result.error == "Task timed out"
        assert result.result is None

    def test_result_serialization(self):
        """Result should serialize to dictionary."""
        result = DelegationResult(
            task_id="task-001",
            worker_agent_id="worker-001",
            success=True,
            result={"status": "done"},
            execution_time_ms=100.0,
            delegation_time_ms=150.0,
        )

        data = result.to_dict()

        assert data["task_id"] == "task-001"
        assert data["worker_agent_id"] == "worker-001"
        assert data["success"] is True
        assert data["execution_time_ms"] == 100.0
