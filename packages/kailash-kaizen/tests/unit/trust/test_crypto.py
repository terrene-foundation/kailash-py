"""
Unit tests for EATP cryptographic utilities.

Tests cover:
- Key generation
- Signing
- Verification
- Serialization
- Hashing
"""

from datetime import datetime

import pytest
from kaizen.trust.crypto import (
    NACL_AVAILABLE,
    generate_keypair,
    hash_chain,
    hash_trust_chain_state,
    serialize_for_signing,
    sign,
    verify_signature,
)
from kaizen.trust.exceptions import InvalidSignatureError

# Skip crypto tests if PyNaCl not available
pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not installed")


class TestKeyGeneration:
    """Tests for Ed25519 key generation."""

    def test_generate_keypair_returns_tuple(self):
        """generate_keypair returns (private_key, public_key) tuple."""
        result = generate_keypair()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_generate_keypair_keys_are_strings(self):
        """Generated keys are base64-encoded strings."""
        private_key, public_key = generate_keypair()
        assert isinstance(private_key, str)
        assert isinstance(public_key, str)

    def test_generate_keypair_keys_are_valid_base64(self):
        """Generated keys are valid base64."""
        import base64

        private_key, public_key = generate_keypair()

        # Should not raise
        base64.b64decode(private_key)
        base64.b64decode(public_key)

    def test_generate_keypair_creates_unique_keys(self):
        """Each call generates unique keys."""
        key1 = generate_keypair()
        key2 = generate_keypair()
        assert key1[0] != key2[0]  # Private keys different
        assert key1[1] != key2[1]  # Public keys different


class TestSigning:
    """Tests for Ed25519 signing."""

    @pytest.fixture
    def keypair(self):
        """Generate a keypair for tests."""
        return generate_keypair()

    def test_sign_string(self, keypair):
        """Can sign a string payload."""
        private_key, _ = keypair
        signature = sign("test payload", private_key)
        assert isinstance(signature, str)
        assert len(signature) > 0

    def test_sign_bytes(self, keypair):
        """Can sign a bytes payload."""
        private_key, _ = keypair
        signature = sign(b"test payload", private_key)
        assert isinstance(signature, str)

    def test_sign_dict(self, keypair):
        """Can sign a dict payload."""
        private_key, _ = keypair
        payload = {"action": "test", "timestamp": "2025-12-15"}
        signature = sign(payload, private_key)
        assert isinstance(signature, str)

    def test_sign_same_payload_same_signature(self, keypair):
        """Same payload produces same signature."""
        private_key, _ = keypair
        payload = {"a": 1, "b": 2}
        sig1 = sign(payload, private_key)
        sig2 = sign(payload, private_key)
        assert sig1 == sig2

    def test_sign_different_payload_different_signature(self, keypair):
        """Different payloads produce different signatures."""
        private_key, _ = keypair
        sig1 = sign("payload1", private_key)
        sig2 = sign("payload2", private_key)
        assert sig1 != sig2

    def test_sign_invalid_private_key_raises(self):
        """Invalid private key raises ValueError."""
        with pytest.raises(ValueError):
            sign("test", "invalid-key")


class TestVerification:
    """Tests for Ed25519 signature verification."""

    @pytest.fixture
    def keypair(self):
        """Generate a keypair for tests."""
        return generate_keypair()

    def test_verify_valid_signature(self, keypair):
        """Valid signature verifies successfully."""
        private_key, public_key = keypair
        payload = "test payload"
        signature = sign(payload, private_key)

        assert verify_signature(payload, signature, public_key) is True

    def test_verify_tampered_payload(self, keypair):
        """Tampered payload fails verification."""
        private_key, public_key = keypair
        signature = sign("original payload", private_key)

        assert verify_signature("tampered payload", signature, public_key) is False

    def test_verify_wrong_public_key(self, keypair):
        """Wrong public key fails verification."""
        private_key, _ = keypair
        _, other_public_key = generate_keypair()

        signature = sign("test payload", private_key)

        assert verify_signature("test payload", signature, other_public_key) is False

    def test_verify_dict_payload(self, keypair):
        """Dict payloads verify correctly."""
        private_key, public_key = keypair
        payload = {"action": "test", "value": 123}
        signature = sign(payload, private_key)

        assert verify_signature(payload, signature, public_key) is True

    def test_verify_dict_key_order_independent(self, keypair):
        """Dict verification is key-order independent."""
        private_key, public_key = keypair
        payload1 = {"b": 2, "a": 1}
        signature = sign(payload1, private_key)

        # Different key order, same content
        payload2 = {"a": 1, "b": 2}
        assert verify_signature(payload2, signature, public_key) is True


class TestSerialization:
    """Tests for deterministic serialization."""

    def test_serialize_dict_sorted_keys(self):
        """Dict keys are sorted in serialization."""
        result = serialize_for_signing({"b": 2, "a": 1, "c": 3})
        assert result == '{"a":1,"b":2,"c":3}'

    def test_serialize_nested_dict(self):
        """Nested dicts are sorted recursively."""
        result = serialize_for_signing({"outer": {"b": 2, "a": 1}})
        assert result == '{"outer":{"a":1,"b":2}}'

    def test_serialize_list(self):
        """Lists are preserved in order."""
        result = serialize_for_signing({"items": [3, 1, 2]})
        assert result == '{"items":[3,1,2]}'

    def test_serialize_datetime(self):
        """Datetime is converted to ISO format."""
        dt = datetime(2025, 12, 15, 10, 30, 0)
        result = serialize_for_signing({"timestamp": dt})
        assert result == '{"timestamp":"2025-12-15T10:30:00"}'

    def test_serialize_enum(self):
        """Enum is converted to value."""
        from kaizen.trust.chain import ActionResult

        result = serialize_for_signing({"result": ActionResult.SUCCESS})
        assert result == '{"result":"success"}'

    def test_serialize_deterministic(self):
        """Same input always produces same output."""
        payload = {"action": "test", "value": 123, "nested": {"x": 1}}
        result1 = serialize_for_signing(payload)
        result2 = serialize_for_signing(payload)
        assert result1 == result2


class TestHashing:
    """Tests for SHA-256 hashing."""

    def test_hash_chain_string(self):
        """Can hash a string."""
        result = hash_chain("test data")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex = 64 chars

    def test_hash_chain_dict(self):
        """Can hash a dict."""
        result = hash_chain({"key": "value"})
        assert len(result) == 64

    def test_hash_chain_bytes(self):
        """Can hash bytes."""
        result = hash_chain(b"test data")
        assert len(result) == 64

    def test_hash_chain_deterministic(self):
        """Same input produces same hash."""
        hash1 = hash_chain({"a": 1, "b": 2})
        hash2 = hash_chain({"b": 2, "a": 1})  # Different key order
        assert hash1 == hash2

    def test_hash_chain_different_inputs(self):
        """Different inputs produce different hashes."""
        hash1 = hash_chain("input1")
        hash2 = hash_chain("input2")
        assert hash1 != hash2

    def test_hash_trust_chain_state(self):
        """hash_trust_chain_state produces consistent results."""
        hash1 = hash_trust_chain_state(
            genesis_id="gen-001",
            capability_ids=["cap-001", "cap-002"],
            delegation_ids=["del-001"],
            constraint_hash="abc123",
        )
        hash2 = hash_trust_chain_state(
            genesis_id="gen-001",
            capability_ids=["cap-002", "cap-001"],  # Different order
            delegation_ids=["del-001"],
            constraint_hash="abc123",
        )
        # Should be same because IDs are sorted internally
        assert hash1 == hash2

    def test_hash_trust_chain_state_different_inputs(self):
        """Different chain states produce different hashes."""
        hash1 = hash_trust_chain_state(
            genesis_id="gen-001",
            capability_ids=["cap-001"],
            delegation_ids=[],
            constraint_hash="abc",
        )
        hash2 = hash_trust_chain_state(
            genesis_id="gen-002",
            capability_ids=["cap-001"],
            delegation_ids=[],
            constraint_hash="abc",
        )
        assert hash1 != hash2


class TestCryptoWithoutNaCl:
    """Tests for behavior when PyNaCl is not available."""

    def test_nacl_available_flag(self):
        """NACL_AVAILABLE is True when PyNaCl is installed."""
        # This test assumes PyNaCl is installed
        assert NACL_AVAILABLE is True
