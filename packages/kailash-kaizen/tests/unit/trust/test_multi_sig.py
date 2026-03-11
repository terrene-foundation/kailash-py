"""
CARE-011: Tests for Multi-Signature Genesis Records.

Tests the M-of-N multi-signature support for critical agent establishment.
Uses real cryptographic operations via InMemoryKeyManager (no mocking).
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

import pytest
from kaizen.trust.crypto import serialize_for_signing, sign, verify_signature
from kaizen.trust.key_manager import InMemoryKeyManager
from kaizen.trust.multi_sig import (
    DuplicateSignatureError,
    InsufficientSignaturesError,
    MultiSigError,
    MultiSigManager,
    MultiSigPolicy,
    OperationNotFoundError,
    PendingMultiSig,
    SigningOperationExpiredError,
    UnauthorizedSignerError,
    create_genesis_payload,
    verify_multi_sig,
)

# =============================================================================
# Helper Functions
# =============================================================================


def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def create_signer_keys(
    key_manager: InMemoryKeyManager, signer_ids: list
) -> Dict[str, str]:
    """Create keys for signers and return public key mapping."""
    signer_public_keys = {}
    for signer_id in signer_ids:
        _, public_key = await key_manager.generate_keypair(signer_id)
        signer_public_keys[signer_id] = public_key
    return signer_public_keys


def create_sample_genesis_payload() -> str:
    """Create a sample genesis payload for testing."""
    return serialize_for_signing(
        {
            "id": "genesis-001",
            "agent_id": "agent-001",
            "authority_id": "org-acme",
            "authority_type": "organization",
            "created_at": "2024-01-01T00:00:00Z",
        }
    )


# =============================================================================
# MultiSigPolicy Tests
# =============================================================================


class TestMultiSigPolicy:
    """Tests for MultiSigPolicy dataclass."""

    def test_policy_creation(self):
        """Test valid M-of-N policy creation."""
        signer_keys = {
            "alice": "key_alice",
            "bob": "key_bob",
            "carol": "key_carol",
        }
        policy = MultiSigPolicy(
            required_signatures=2,
            total_signers=3,
            signer_public_keys=signer_keys,
        )
        assert policy.required_signatures == 2
        assert policy.total_signers == 3
        assert len(policy.signer_public_keys) == 3

    def test_policy_m_greater_than_n_raises(self):
        """Test that M > N raises ValueError."""
        signer_keys = {"alice": "key_alice", "bob": "key_bob"}
        with pytest.raises(ValueError, match="cannot exceed"):
            MultiSigPolicy(
                required_signatures=3,
                total_signers=2,
                signer_public_keys=signer_keys,
            )

    def test_policy_m_zero_raises(self):
        """Test that M = 0 raises ValueError."""
        signer_keys = {"alice": "key_alice", "bob": "key_bob"}
        with pytest.raises(ValueError, match="at least 1"):
            MultiSigPolicy(
                required_signatures=0,
                total_signers=2,
                signer_public_keys=signer_keys,
            )

    def test_policy_signer_count_matches_n(self):
        """Test that signer count must equal N."""
        signer_keys = {"alice": "key_alice"}  # Only 1 key, but N=3
        with pytest.raises(ValueError, match="must equal total_signers"):
            MultiSigPolicy(
                required_signatures=2,
                total_signers=3,
                signer_public_keys=signer_keys,
            )

    def test_policy_defaults(self):
        """Test default values for policy."""
        signer_keys = {"alice": "key_alice", "bob": "key_bob"}
        policy = MultiSigPolicy(
            required_signatures=1,
            total_signers=2,
            signer_public_keys=signer_keys,
        )
        assert policy.expiry_hours == 24

    def test_policy_to_dict(self):
        """Test policy serialization."""
        signer_keys = {"alice": "key_alice", "bob": "key_bob"}
        policy = MultiSigPolicy(
            required_signatures=1,
            total_signers=2,
            signer_public_keys=signer_keys,
            expiry_hours=48,
        )
        d = policy.to_dict()
        assert d["required_signatures"] == 1
        assert d["total_signers"] == 2
        assert d["expiry_hours"] == 48
        assert d["signer_public_keys"] == signer_keys

    def test_policy_from_dict(self):
        """Test policy deserialization."""
        data = {
            "required_signatures": 2,
            "total_signers": 3,
            "signer_public_keys": {"a": "ka", "b": "kb", "c": "kc"},
            "expiry_hours": 12,
        }
        policy = MultiSigPolicy.from_dict(data)
        assert policy.required_signatures == 2
        assert policy.total_signers == 3
        assert policy.expiry_hours == 12


# =============================================================================
# PendingMultiSig Tests
# =============================================================================


class TestPendingMultiSig:
    """Tests for PendingMultiSig dataclass."""

    def create_test_policy(self) -> MultiSigPolicy:
        """Create a test policy."""
        return MultiSigPolicy(
            required_signatures=2,
            total_signers=3,
            signer_public_keys={"alice": "k1", "bob": "k2", "carol": "k3"},
            expiry_hours=24,
        )

    def test_pending_creation(self):
        """Test PendingMultiSig creation with all fields."""
        policy = self.create_test_policy()
        pending = PendingMultiSig(
            operation_id="msig-test123",
            payload="test_payload",
            policy=policy,
        )
        assert pending.operation_id == "msig-test123"
        assert pending.payload == "test_payload"
        assert pending.policy == policy
        assert pending.signatures == {}
        assert pending.created_at is not None
        assert pending.expires_at is not None

    def test_pending_is_complete_false(self):
        """Test is_complete returns False when insufficient signatures."""
        policy = self.create_test_policy()
        pending = PendingMultiSig(
            operation_id="msig-test",
            payload="payload",
            policy=policy,
            signatures={"alice": "sig1"},  # Only 1 of 2 required
        )
        assert pending.is_complete() is False

    def test_pending_is_complete_true(self):
        """Test is_complete returns True when enough signatures."""
        policy = self.create_test_policy()
        pending = PendingMultiSig(
            operation_id="msig-test",
            payload="payload",
            policy=policy,
            signatures={"alice": "sig1", "bob": "sig2"},  # 2 of 2 required
        )
        assert pending.is_complete() is True

    def test_pending_is_expired(self):
        """Test is_expired after expiry time."""
        policy = MultiSigPolicy(
            required_signatures=1,
            total_signers=2,
            signer_public_keys={"alice": "k1", "bob": "k2"},
            expiry_hours=0,  # Immediate expiry
        )
        # Create with past expiry
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        pending = PendingMultiSig(
            operation_id="msig-test",
            payload="payload",
            policy=policy,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=0),
        )
        assert pending.is_expired() is True

    def test_pending_is_not_expired(self):
        """Test is_expired returns False before expiry."""
        policy = self.create_test_policy()
        pending = PendingMultiSig(
            operation_id="msig-test",
            payload="payload",
            policy=policy,
        )
        assert pending.is_expired() is False

    def test_pending_remaining_signatures(self):
        """Test remaining_signatures calculation."""
        policy = self.create_test_policy()
        pending = PendingMultiSig(
            operation_id="msig-test",
            payload="payload",
            policy=policy,
            signatures={"alice": "sig1"},
        )
        assert pending.remaining_signatures() == 1  # 2 required, 1 signed

    def test_pending_pending_signers(self):
        """Test pending_signers returns correct set."""
        policy = self.create_test_policy()
        pending = PendingMultiSig(
            operation_id="msig-test",
            payload="payload",
            policy=policy,
            signatures={"alice": "sig1"},
        )
        remaining = pending.pending_signers()
        assert remaining == {"bob", "carol"}

    def test_pending_auto_expiry(self):
        """Test auto-calculated expiry from policy."""
        policy = MultiSigPolicy(
            required_signatures=1,
            total_signers=2,
            signer_public_keys={"alice": "k1", "bob": "k2"},
            expiry_hours=48,
        )
        pending = PendingMultiSig(
            operation_id="msig-test",
            payload="payload",
            policy=policy,
        )
        expected_expiry = pending.created_at + timedelta(hours=48)
        # Allow small time delta for test execution
        assert abs((pending.expires_at - expected_expiry).total_seconds()) < 1

    def test_pending_serialization(self):
        """Test to_dict and from_dict round-trip."""
        policy = self.create_test_policy()
        original = PendingMultiSig(
            operation_id="msig-test",
            payload="test_payload",
            policy=policy,
            signatures={"alice": "sig1"},
        )
        d = original.to_dict()
        restored = PendingMultiSig.from_dict(d)
        assert restored.operation_id == original.operation_id
        assert restored.payload == original.payload
        assert restored.signatures == original.signatures


# =============================================================================
# MultiSigManager Tests
# =============================================================================


class TestMultiSigManager:
    """Tests for MultiSigManager."""

    @pytest.fixture
    def key_manager(self):
        """Create a fresh key manager for each test."""
        return InMemoryKeyManager()

    @pytest.fixture
    def signer_keys_3(self, key_manager):
        """Create 3 signers with keys."""
        return run_async(create_signer_keys(key_manager, ["alice", "bob", "carol"]))

    @pytest.fixture
    def policy_2_of_3(self, signer_keys_3) -> MultiSigPolicy:
        """Create a 2-of-3 policy."""
        return MultiSigPolicy(
            required_signatures=2,
            total_signers=3,
            signer_public_keys=signer_keys_3,
            expiry_hours=24,
        )

    def test_initiate_genesis_signing(self, key_manager, policy_2_of_3):
        """Test initiating a signing operation."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()

        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        assert pending.operation_id.startswith("msig-")
        assert pending.payload == payload
        assert pending.policy == policy_2_of_3
        assert pending.signatures == {}
        assert pending in manager.list_pending()

    def test_add_signature_valid(self, key_manager, policy_2_of_3):
        """Test adding a valid signature."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()
        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        # Sign with alice
        signature = run_async(key_manager.sign(payload, "alice"))
        updated = manager.add_signature(pending.operation_id, "alice", signature)

        assert "alice" in updated.signatures
        assert updated.signatures["alice"] == signature

    def test_add_signature_unauthorized_signer(self, key_manager, policy_2_of_3):
        """Test that unauthorized signer raises error."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()
        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        with pytest.raises(UnauthorizedSignerError, match="not authorized"):
            manager.add_signature(pending.operation_id, "eve", "fake_sig")

    def test_add_signature_duplicate_signer(self, key_manager, policy_2_of_3):
        """Test that duplicate signature raises error."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()
        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        signature = run_async(key_manager.sign(payload, "alice"))
        manager.add_signature(pending.operation_id, "alice", signature)

        with pytest.raises(DuplicateSignatureError, match="Duplicate"):
            manager.add_signature(pending.operation_id, "alice", signature)

    def test_add_signature_expired(self, key_manager, signer_keys_3):
        """Test that expired operation raises error."""
        # Create policy with 0 expiry hours
        policy = MultiSigPolicy(
            required_signatures=2,
            total_signers=3,
            signer_public_keys=signer_keys_3,
            expiry_hours=0,
        )
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()

        # Create a pending with past expiry
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        pending = PendingMultiSig(
            operation_id="msig-expired",
            payload=payload,
            policy=policy,
            created_at=past_time,
            expires_at=past_time,
        )
        manager._pending[pending.operation_id] = pending

        with pytest.raises(SigningOperationExpiredError, match="expired"):
            manager.add_signature(pending.operation_id, "alice", "sig")

    def test_add_signature_unknown_operation(self, key_manager):
        """Test that unknown operation raises error."""
        manager = MultiSigManager(key_manager=key_manager)

        with pytest.raises(OperationNotFoundError, match="not found"):
            manager.add_signature("msig-nonexistent", "alice", "sig")

    def test_add_signature_invalid_signature(self, key_manager, policy_2_of_3):
        """Test that invalid signature raises ValueError."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()
        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        # Try to add an invalid signature
        with pytest.raises(ValueError, match="Invalid signature"):
            manager.add_signature(pending.operation_id, "alice", "not_a_valid_sig")

    def test_complete_quorum_met(self, key_manager, policy_2_of_3):
        """Test completing when quorum is met."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()
        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        # Collect 2 signatures (quorum)
        sig1 = run_async(key_manager.sign(payload, "alice"))
        sig2 = run_async(key_manager.sign(payload, "bob"))
        manager.add_signature(pending.operation_id, "alice", sig1)
        manager.add_signature(pending.operation_id, "bob", sig2)

        combined = manager.complete_genesis_signing(pending.operation_id)
        parsed = json.loads(combined)

        assert parsed["type"] == "multisig"
        assert parsed["threshold"] == "2/3"
        assert "alice" in parsed["signatures"]
        assert "bob" in parsed["signatures"]

    def test_complete_quorum_not_met(self, key_manager, policy_2_of_3):
        """Test that completing without quorum raises error."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()
        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        # Only 1 signature (need 2)
        sig = run_async(key_manager.sign(payload, "alice"))
        manager.add_signature(pending.operation_id, "alice", sig)

        with pytest.raises(InsufficientSignaturesError, match="1/2"):
            manager.complete_genesis_signing(pending.operation_id)

    def test_complete_removes_from_pending(self, key_manager, policy_2_of_3):
        """Test that completion removes operation from pending."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()
        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        sig1 = run_async(key_manager.sign(payload, "alice"))
        sig2 = run_async(key_manager.sign(payload, "bob"))
        manager.add_signature(pending.operation_id, "alice", sig1)
        manager.add_signature(pending.operation_id, "bob", sig2)

        manager.complete_genesis_signing(pending.operation_id)

        assert manager.get_pending(pending.operation_id) is None

    def test_get_pending(self, key_manager, policy_2_of_3):
        """Test get_pending returns the operation."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()
        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        retrieved = manager.get_pending(pending.operation_id)
        assert retrieved is not None
        assert retrieved.operation_id == pending.operation_id

    def test_get_pending_nonexistent(self, key_manager):
        """Test get_pending returns None for unknown operation."""
        manager = MultiSigManager(key_manager=key_manager)
        assert manager.get_pending("msig-nonexistent") is None

    def test_list_pending(self, key_manager, policy_2_of_3):
        """Test listing all pending operations."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()

        pending1 = manager.initiate_genesis_signing(payload, policy_2_of_3)
        pending2 = manager.initiate_genesis_signing(payload, policy_2_of_3)

        pending_list = manager.list_pending()
        assert len(pending_list) == 2
        op_ids = {p.operation_id for p in pending_list}
        assert pending1.operation_id in op_ids
        assert pending2.operation_id in op_ids

    def test_cancel_operation(self, key_manager, policy_2_of_3):
        """Test cancelling a pending operation."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()
        pending = manager.initiate_genesis_signing(payload, policy_2_of_3)

        result = manager.cancel(pending.operation_id)
        assert result is True
        assert manager.get_pending(pending.operation_id) is None

    def test_cancel_nonexistent(self, key_manager):
        """Test cancelling nonexistent operation returns False."""
        manager = MultiSigManager(key_manager=key_manager)
        result = manager.cancel("msig-nonexistent")
        assert result is False

    def test_cleanup_expired(self, key_manager, signer_keys_3):
        """Test cleanup_expired removes expired operations."""
        manager = MultiSigManager(key_manager=key_manager)
        payload = create_sample_genesis_payload()

        # Create expired operation
        policy = MultiSigPolicy(
            required_signatures=2,
            total_signers=3,
            signer_public_keys=signer_keys_3,
            expiry_hours=0,
        )
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        expired = PendingMultiSig(
            operation_id="msig-expired",
            payload=payload,
            policy=policy,
            created_at=past_time,
            expires_at=past_time,
        )
        manager._pending[expired.operation_id] = expired

        # Create valid operation
        valid_policy = MultiSigPolicy(
            required_signatures=2,
            total_signers=3,
            signer_public_keys=signer_keys_3,
            expiry_hours=24,
        )
        valid = manager.initiate_genesis_signing(payload, valid_policy)

        # Cleanup
        removed = manager.cleanup_expired()
        assert removed == 1
        assert manager.get_pending("msig-expired") is None
        assert manager.get_pending(valid.operation_id) is not None


# =============================================================================
# Verification Tests
# =============================================================================


class TestVerifyMultiSig:
    """Tests for verify_multi_sig function."""

    @pytest.fixture
    def key_manager(self):
        """Create a fresh key manager."""
        return InMemoryKeyManager()

    @pytest.fixture
    def setup_3_of_5(self, key_manager) -> Tuple[MultiSigPolicy, str]:
        """Set up a 3-of-5 signing scenario."""
        signers = ["alice", "bob", "carol", "dave", "eve"]
        signer_keys = run_async(create_signer_keys(key_manager, signers))
        policy = MultiSigPolicy(
            required_signatures=3,
            total_signers=5,
            signer_public_keys=signer_keys,
        )
        payload = create_sample_genesis_payload()
        return policy, payload

    def test_verify_multi_sig_valid(self, key_manager, setup_3_of_5):
        """Test verification of valid combined signature."""
        policy, payload = setup_3_of_5
        manager = MultiSigManager(key_manager=key_manager)

        # Collect 3 signatures
        pending = manager.initiate_genesis_signing(payload, policy)
        for signer in ["alice", "bob", "carol"]:
            sig = run_async(key_manager.sign(payload, signer))
            manager.add_signature(pending.operation_id, signer, sig)

        combined = manager.complete_genesis_signing(pending.operation_id)

        # Verify
        is_valid = verify_multi_sig(payload, combined, policy, key_manager)
        assert is_valid is True

    def test_verify_multi_sig_invalid_tampered(self, key_manager, setup_3_of_5):
        """Test verification fails for tampered signature."""
        policy, payload = setup_3_of_5
        manager = MultiSigManager(key_manager=key_manager)

        pending = manager.initiate_genesis_signing(payload, policy)
        for signer in ["alice", "bob", "carol"]:
            sig = run_async(key_manager.sign(payload, signer))
            manager.add_signature(pending.operation_id, signer, sig)

        combined = manager.complete_genesis_signing(pending.operation_id)

        # Tamper with the combined signature
        parsed = json.loads(combined)
        parsed["signatures"]["alice"] = "tampered_signature"
        tampered = json.dumps(parsed)

        is_valid = verify_multi_sig(payload, tampered, policy, key_manager)
        assert is_valid is False

    def test_verify_multi_sig_insufficient_valid(self, key_manager, setup_3_of_5):
        """Test verification fails when less than M signatures are valid."""
        policy, payload = setup_3_of_5

        # Create combined signature with only 2 valid signatures
        sig1 = run_async(key_manager.sign(payload, "alice"))
        sig2 = run_async(key_manager.sign(payload, "bob"))

        combined = json.dumps(
            {
                "type": "multisig",
                "threshold": "3/5",
                "signatures": {
                    "alice": sig1,
                    "bob": sig2,
                    "carol": "invalid_sig",  # Invalid
                },
            }
        )

        is_valid = verify_multi_sig(payload, combined, policy, key_manager)
        assert is_valid is False  # Only 2 valid, need 3

    def test_verify_multi_sig_without_key_manager_skip_verification(self, setup_3_of_5):
        """Test verification returns True without key manager when skip_verification=True."""
        policy, payload = setup_3_of_5

        combined = json.dumps(
            {
                "type": "multisig",
                "threshold": "3/5",
                "signatures": {"a": "s1", "b": "s2", "c": "s3"},
            }
        )

        # CARE-050: Explicit skip_verification=True required for testing bypass
        is_valid = verify_multi_sig(
            payload, combined, policy, key_manager=None, skip_verification=True
        )
        assert is_valid is True

    def test_verify_multi_sig_fail_closed_without_key_manager(self, setup_3_of_5):
        """CARE-050: Test verification returns False without key manager (fail-closed)."""
        policy, payload = setup_3_of_5

        combined = json.dumps(
            {
                "type": "multisig",
                "threshold": "3/5",
                "signatures": {"a": "s1", "b": "s2", "c": "s3"},
            }
        )

        # Without key manager and skip_verification=False (default),
        # verification MUST return False (fail-closed behavior)
        is_valid = verify_multi_sig(payload, combined, policy, key_manager=None)
        assert is_valid is False

    def test_verify_multi_sig_fail_closed_default_skip_verification(self, setup_3_of_5):
        """CARE-050: Test that skip_verification defaults to False."""
        policy, payload = setup_3_of_5

        combined = json.dumps(
            {
                "type": "multisig",
                "threshold": "3/5",
                "signatures": {"a": "s1", "b": "s2", "c": "s3"},
            }
        )

        # Explicitly pass skip_verification=False to confirm default behavior
        is_valid = verify_multi_sig(
            payload, combined, policy, key_manager=None, skip_verification=False
        )
        assert is_valid is False

    def test_verify_multi_sig_with_key_manager_ignores_skip_verification(
        self, key_manager, setup_3_of_5
    ):
        """Test that skip_verification has no effect when key_manager is provided."""
        policy, payload = setup_3_of_5
        manager = MultiSigManager(key_manager=key_manager)

        # Collect 3 valid signatures
        pending = manager.initiate_genesis_signing(payload, policy)
        for signer in ["alice", "bob", "carol"]:
            sig = run_async(key_manager.sign(payload, signer))
            manager.add_signature(pending.operation_id, signer, sig)

        combined = manager.complete_genesis_signing(pending.operation_id)

        # With key_manager present, skip_verification should have no effect
        # Verification should still work normally
        is_valid = verify_multi_sig(
            payload, combined, policy, key_manager, skip_verification=True
        )
        assert is_valid is True

    def test_verify_multi_sig_invalid_json(self, key_manager, setup_3_of_5):
        """Test verification fails for invalid JSON."""
        policy, payload = setup_3_of_5

        is_valid = verify_multi_sig(payload, "not json", policy, key_manager)
        assert is_valid is False

    def test_verify_multi_sig_wrong_type(self, key_manager, setup_3_of_5):
        """Test verification fails for wrong signature type."""
        policy, payload = setup_3_of_5

        combined = json.dumps({"type": "single", "signature": "xxx"})
        is_valid = verify_multi_sig(payload, combined, policy, key_manager)
        assert is_valid is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestMultiSigIntegration:
    """Integration tests for complete multi-signature workflows."""

    def test_full_3_of_5_workflow(self):
        """Test complete 3-of-5 signing ceremony."""
        key_manager = InMemoryKeyManager()

        # Create 5 board members
        signers = ["ceo", "cfo", "cto", "coo", "ciso"]
        signer_keys = run_async(create_signer_keys(key_manager, signers))

        # Define policy: 3-of-5 approval required
        policy = MultiSigPolicy(
            required_signatures=3,
            total_signers=5,
            signer_public_keys=signer_keys,
            expiry_hours=72,  # 3 days to collect signatures
        )

        # Create genesis payload for high-value agent
        genesis_data = {
            "id": "genesis-financial-agent",
            "agent_id": "financial-analysis-agent",
            "authority_id": "acme-corp",
            "authority_type": "organization",
            "capabilities": ["read_financial_data", "generate_reports"],
            "budget_limit": 1000000,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = create_genesis_payload(genesis_data)

        # Initiate signing ceremony
        manager = MultiSigManager(key_manager=key_manager)
        pending = manager.initiate_genesis_signing(payload, policy)

        # CEO signs first
        ceo_sig = run_async(key_manager.sign(payload, "ceo"))
        manager.add_signature(pending.operation_id, "ceo", ceo_sig)
        assert pending.remaining_signatures() == 2

        # CFO signs
        cfo_sig = run_async(key_manager.sign(payload, "cfo"))
        manager.add_signature(pending.operation_id, "cfo", cfo_sig)
        assert pending.remaining_signatures() == 1

        # CTO signs - quorum reached
        cto_sig = run_async(key_manager.sign(payload, "cto"))
        manager.add_signature(pending.operation_id, "cto", cto_sig)
        assert pending.is_complete() is True

        # Complete the ceremony
        combined_sig = manager.complete_genesis_signing(pending.operation_id)

        # Verify the combined signature
        is_valid = verify_multi_sig(payload, combined_sig, policy, key_manager)
        assert is_valid is True

        # Verify signature format
        parsed = json.loads(combined_sig)
        assert parsed["type"] == "multisig"
        assert parsed["threshold"] == "3/5"
        assert len(parsed["signatures"]) == 3

    def test_2_of_3_with_real_keys(self):
        """Test 2-of-3 signing with real cryptographic keys."""
        key_manager = InMemoryKeyManager()

        # Create 3 signers with real keys
        signer_keys = run_async(
            create_signer_keys(key_manager, ["admin1", "admin2", "admin3"])
        )

        policy = MultiSigPolicy(
            required_signatures=2,
            total_signers=3,
            signer_public_keys=signer_keys,
        )

        payload = serialize_for_signing(
            {"action": "establish_agent", "agent_id": "test-agent"}
        )

        manager = MultiSigManager(key_manager=key_manager)
        pending = manager.initiate_genesis_signing(payload, policy)

        # Sign with admin1 and admin3 (skipping admin2)
        sig1 = run_async(key_manager.sign(payload, "admin1"))
        sig3 = run_async(key_manager.sign(payload, "admin3"))

        manager.add_signature(pending.operation_id, "admin1", sig1)
        manager.add_signature(pending.operation_id, "admin3", sig3)

        combined = manager.complete_genesis_signing(pending.operation_id)

        # Verify
        is_valid = verify_multi_sig(payload, combined, policy, key_manager)
        assert is_valid is True

    def test_combined_sig_format(self):
        """Test the format of combined signature JSON."""
        key_manager = InMemoryKeyManager()

        signer_keys = run_async(create_signer_keys(key_manager, ["s1", "s2", "s3"]))

        policy = MultiSigPolicy(
            required_signatures=2,
            total_signers=3,
            signer_public_keys=signer_keys,
        )

        payload = "test_payload"
        manager = MultiSigManager(key_manager=key_manager)
        pending = manager.initiate_genesis_signing(payload, policy)

        sig1 = run_async(key_manager.sign(payload, "s1"))
        sig2 = run_async(key_manager.sign(payload, "s2"))
        manager.add_signature(pending.operation_id, "s1", sig1)
        manager.add_signature(pending.operation_id, "s2", sig2)

        combined = manager.complete_genesis_signing(pending.operation_id)
        parsed = json.loads(combined)

        # Verify structure
        assert "type" in parsed
        assert parsed["type"] == "multisig"
        assert "threshold" in parsed
        assert parsed["threshold"] == "2/3"
        assert "signatures" in parsed
        assert isinstance(parsed["signatures"], dict)
        assert "s1" in parsed["signatures"]
        assert "s2" in parsed["signatures"]

    def test_manager_without_key_manager(self):
        """Test manager works without key manager (no verification)."""
        # No key manager - signatures collected but not verified
        manager = MultiSigManager(key_manager=None)

        signer_keys = {"alice": "key_a", "bob": "key_b"}
        policy = MultiSigPolicy(
            required_signatures=2,
            total_signers=2,
            signer_public_keys=signer_keys,
        )

        payload = "test"
        pending = manager.initiate_genesis_signing(payload, policy)

        # Can add any signature without verification
        manager.add_signature(pending.operation_id, "alice", "any_sig_1")
        manager.add_signature(pending.operation_id, "bob", "any_sig_2")

        combined = manager.complete_genesis_signing(pending.operation_id)
        assert combined is not None


# =============================================================================
# Exception Tests
# =============================================================================


class TestMultiSigExceptions:
    """Tests for exception classes."""

    def test_multi_sig_error_base(self):
        """Test base MultiSigError."""
        error = MultiSigError("test error", {"key": "value"})
        assert error.message == "test error"
        assert error.details == {"key": "value"}
        assert "test error" in str(error)

    def test_insufficient_signatures_error(self):
        """Test InsufficientSignaturesError."""
        error = InsufficientSignaturesError(1, 3, "msig-123")
        assert error.current == 1
        assert error.required == 3
        assert error.operation_id == "msig-123"
        assert "1/3" in str(error)

    def test_signing_operation_expired_error(self):
        """Test SigningOperationExpiredError."""
        expired = datetime.now(timezone.utc)
        error = SigningOperationExpiredError("msig-123", expired)
        assert error.operation_id == "msig-123"
        assert error.expired_at == expired

    def test_unauthorized_signer_error(self):
        """Test UnauthorizedSignerError."""
        error = UnauthorizedSignerError("eve", "msig-123")
        assert error.signer_id == "eve"
        assert error.operation_id == "msig-123"

    def test_duplicate_signature_error(self):
        """Test DuplicateSignatureError."""
        error = DuplicateSignatureError("alice", "msig-123")
        assert error.signer_id == "alice"
        assert "Duplicate" in str(error)

    def test_operation_not_found_error(self):
        """Test OperationNotFoundError."""
        error = OperationNotFoundError("msig-nonexistent")
        assert error.operation_id == "msig-nonexistent"
        assert "not found" in str(error)


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_genesis_payload(self):
        """Test create_genesis_payload produces deterministic output."""
        data = {"b": 2, "a": 1, "c": 3}
        payload1 = create_genesis_payload(data)
        payload2 = create_genesis_payload(data)

        # Should be deterministic
        assert payload1 == payload2
        # Should be valid JSON
        parsed = json.loads(payload1)
        assert parsed == data
