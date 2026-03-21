# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP DualSignature system (Phase 5 G6).

Covers:
- DualSignature dataclass: construction, properties, serialization
- hmac_sign: HMAC-SHA256 computation for bytes, str, dict payloads
- hmac_verify: constant-time HMAC verification
- dual_sign: Ed25519 + optional HMAC-SHA256 combined signing
- dual_verify: Ed25519 mandatory + HMAC optional verification
- Security: HMAC uses compare_digest (constant-time), not ==
- Tamper detection: any payload change must invalidate both signatures
- Serialization round-trip: DualSignature.to_dict() / from_dict()

Written BEFORE implementation (TDD). Tests define the contract.
"""

import base64
import hashlib
import os
import secrets

import pytest

from kailash.trust.signing.crypto import (
    DualSignature,
    dual_sign,
    dual_verify,
    generate_keypair,
    hmac_sign,
    hmac_verify,
    serialize_for_signing,
    sign,
    verify_signature,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair for signing tests."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


@pytest.fixture
def hmac_key():
    """Generate a random 32-byte HMAC key."""
    return secrets.token_bytes(32)


@pytest.fixture
def sample_dict_payload():
    """A representative dict payload for signing."""
    return {
        "agent_id": "agent-001",
        "action": "analyze_data",
        "timestamp": "2026-03-14T10:00:00Z",
        "capability": "financial_analysis",
    }


@pytest.fixture
def sample_str_payload():
    """A representative string payload for signing."""
    return "trust-chain-verification-payload-2026"


@pytest.fixture
def sample_bytes_payload():
    """A representative bytes payload for signing."""
    return b"\x00\x01\x02\x03trust-chain-binary-payload"


# ===========================================================================
# Test Class 1: DualSignature Dataclass
# ===========================================================================


class TestDualSignatureDataclass:
    """Tests for DualSignature dataclass construction and properties."""

    def test_construction_ed25519_only(self):
        """DualSignature can be constructed with only ed25519_signature."""
        ds = DualSignature(ed25519_signature="abc123==")
        assert ds.ed25519_signature == "abc123=="
        assert ds.hmac_signature is None
        assert ds.hmac_algorithm == "sha256"

    def test_construction_with_hmac(self):
        """DualSignature can be constructed with both ed25519 and hmac signatures."""
        ds = DualSignature(
            ed25519_signature="ed25519sig==",
            hmac_signature="hmacsig==",
            hmac_algorithm="sha256",
        )
        assert ds.ed25519_signature == "ed25519sig=="
        assert ds.hmac_signature == "hmacsig=="
        assert ds.hmac_algorithm == "sha256"

    def test_has_hmac_false_when_none(self):
        """has_hmac must return False when hmac_signature is None."""
        ds = DualSignature(ed25519_signature="abc123==")
        assert ds.has_hmac is False

    def test_has_hmac_true_when_present(self):
        """has_hmac must return True when hmac_signature is set."""
        ds = DualSignature(
            ed25519_signature="abc123==",
            hmac_signature="hmac==",
        )
        assert ds.has_hmac is True

    def test_default_hmac_algorithm(self):
        """Default hmac_algorithm must be 'sha256'."""
        ds = DualSignature(ed25519_signature="abc123==")
        assert ds.hmac_algorithm == "sha256"

    def test_to_dict_without_hmac(self):
        """to_dict without HMAC must include ed25519_signature and hmac_algorithm only."""
        ds = DualSignature(ed25519_signature="ed_sig==")
        d = ds.to_dict()
        assert d == {
            "ed25519_signature": "ed_sig==",
            "hmac_algorithm": "sha256",
        }
        assert "hmac_signature" not in d

    def test_to_dict_with_hmac(self):
        """to_dict with HMAC must include all three fields."""
        ds = DualSignature(
            ed25519_signature="ed_sig==",
            hmac_signature="hmac_sig==",
            hmac_algorithm="sha256",
        )
        d = ds.to_dict()
        assert d == {
            "ed25519_signature": "ed_sig==",
            "hmac_signature": "hmac_sig==",
            "hmac_algorithm": "sha256",
        }

    def test_from_dict_without_hmac(self):
        """from_dict must reconstruct DualSignature without hmac_signature."""
        data = {
            "ed25519_signature": "ed_sig==",
            "hmac_algorithm": "sha256",
        }
        ds = DualSignature.from_dict(data)
        assert ds.ed25519_signature == "ed_sig=="
        assert ds.hmac_signature is None
        assert ds.hmac_algorithm == "sha256"

    def test_from_dict_with_hmac(self):
        """from_dict must reconstruct DualSignature with hmac_signature."""
        data = {
            "ed25519_signature": "ed_sig==",
            "hmac_signature": "hmac_sig==",
            "hmac_algorithm": "sha256",
        }
        ds = DualSignature.from_dict(data)
        assert ds.ed25519_signature == "ed_sig=="
        assert ds.hmac_signature == "hmac_sig=="
        assert ds.hmac_algorithm == "sha256"

    def test_from_dict_defaults_hmac_algorithm(self):
        """from_dict must default hmac_algorithm to 'sha256' when not present."""
        data = {"ed25519_signature": "ed_sig=="}
        ds = DualSignature.from_dict(data)
        assert ds.hmac_algorithm == "sha256"

    def test_to_dict_from_dict_round_trip_without_hmac(self):
        """to_dict followed by from_dict must round-trip correctly (no HMAC)."""
        original = DualSignature(ed25519_signature="round_trip_ed==")
        restored = DualSignature.from_dict(original.to_dict())
        assert restored.ed25519_signature == original.ed25519_signature
        assert restored.hmac_signature == original.hmac_signature
        assert restored.hmac_algorithm == original.hmac_algorithm

    def test_to_dict_from_dict_round_trip_with_hmac(self):
        """to_dict followed by from_dict must round-trip correctly (with HMAC)."""
        original = DualSignature(
            ed25519_signature="round_trip_ed==",
            hmac_signature="round_trip_hmac==",
            hmac_algorithm="sha256",
        )
        restored = DualSignature.from_dict(original.to_dict())
        assert restored.ed25519_signature == original.ed25519_signature
        assert restored.hmac_signature == original.hmac_signature
        assert restored.hmac_algorithm == original.hmac_algorithm

    def test_from_dict_missing_ed25519_raises(self):
        """from_dict must raise KeyError when ed25519_signature is missing."""
        with pytest.raises(KeyError):
            DualSignature.from_dict({"hmac_signature": "hmac=="})


# ===========================================================================
# Test Class 2: hmac_sign
# ===========================================================================


class TestHmacSign:
    """Tests for hmac_sign() function."""

    def test_returns_base64_string(self, hmac_key):
        """hmac_sign must return a base64-encoded string."""
        result = hmac_sign(b"test payload", hmac_key)
        assert isinstance(result, str)
        # Must be valid base64
        decoded = base64.b64decode(result)
        # HMAC-SHA256 produces 32 bytes
        assert len(decoded) == 32

    def test_deterministic_same_payload_same_key(self, hmac_key):
        """Calling hmac_sign twice with same payload and key must produce same result."""
        sig1 = hmac_sign(b"deterministic test", hmac_key)
        sig2 = hmac_sign(b"deterministic test", hmac_key)
        assert sig1 == sig2

    def test_different_keys_different_hmac(self):
        """Different HMAC keys must produce different signatures."""
        key1 = secrets.token_bytes(32)
        key2 = secrets.token_bytes(32)
        sig1 = hmac_sign(b"same payload", key1)
        sig2 = hmac_sign(b"same payload", key2)
        assert sig1 != sig2

    def test_different_payloads_different_hmac(self, hmac_key):
        """Different payloads must produce different HMACs."""
        sig1 = hmac_sign(b"payload A", hmac_key)
        sig2 = hmac_sign(b"payload B", hmac_key)
        assert sig1 != sig2

    def test_bytes_payload(self, hmac_key):
        """hmac_sign must handle bytes payload."""
        result = hmac_sign(b"\x00\x01\x02\x03", hmac_key)
        assert isinstance(result, str)
        assert len(base64.b64decode(result)) == 32

    def test_string_payload(self, hmac_key):
        """hmac_sign must handle string payload (encode to UTF-8)."""
        result = hmac_sign("string payload", hmac_key)
        assert isinstance(result, str)
        assert len(base64.b64decode(result)) == 32

    def test_dict_payload(self, hmac_key, sample_dict_payload):
        """hmac_sign must handle dict payload via serialize_for_signing."""
        result = hmac_sign(sample_dict_payload, hmac_key)
        assert isinstance(result, str)
        assert len(base64.b64decode(result)) == 32

    def test_dict_payload_uses_serialize_for_signing(
        self, hmac_key, sample_dict_payload
    ):
        """hmac_sign on dict must use serialize_for_signing for canonical representation."""
        import hmac as hmac_mod

        # Manually compute expected HMAC
        serialized = serialize_for_signing(sample_dict_payload).encode("utf-8")
        expected_mac = hmac_mod.new(hmac_key, serialized, hashlib.sha256)
        expected = base64.b64encode(expected_mac.digest()).decode("utf-8")

        actual = hmac_sign(sample_dict_payload, hmac_key)
        assert actual == expected

    def test_string_payload_consistency(self, hmac_key):
        """hmac_sign on string must be equivalent to HMAC of string.encode('utf-8')."""
        import hmac as hmac_mod

        payload_str = "test string"
        expected_mac = hmac_mod.new(
            hmac_key, payload_str.encode("utf-8"), hashlib.sha256
        )
        expected = base64.b64encode(expected_mac.digest()).decode("utf-8")

        actual = hmac_sign(payload_str, hmac_key)
        assert actual == expected


# ===========================================================================
# Test Class 3: hmac_verify
# ===========================================================================


class TestHmacVerify:
    """Tests for hmac_verify() function."""

    def test_valid_hmac_returns_true(self, hmac_key):
        """hmac_verify must return True for a valid HMAC signature."""
        payload = b"test payload"
        sig = hmac_sign(payload, hmac_key)
        assert hmac_verify(payload, sig, hmac_key) is True

    def test_invalid_hmac_returns_false(self, hmac_key):
        """hmac_verify must return False for an invalid HMAC signature."""
        payload = b"test payload"
        fake_sig = base64.b64encode(b"\x00" * 32).decode("utf-8")
        assert hmac_verify(payload, fake_sig, hmac_key) is False

    def test_tampered_payload_returns_false(self, hmac_key):
        """hmac_verify must return False when payload has been tampered with."""
        sig = hmac_sign(b"original payload", hmac_key)
        assert hmac_verify(b"tampered payload", sig, hmac_key) is False

    def test_wrong_key_returns_false(self):
        """hmac_verify must return False when using a different key."""
        key1 = secrets.token_bytes(32)
        key2 = secrets.token_bytes(32)
        sig = hmac_sign(b"payload", key1)
        assert hmac_verify(b"payload", sig, key2) is False

    def test_string_payload_round_trip(self, hmac_key):
        """hmac_verify must work with string payloads."""
        payload = "string payload"
        sig = hmac_sign(payload, hmac_key)
        assert hmac_verify(payload, sig, hmac_key) is True

    def test_dict_payload_round_trip(self, hmac_key, sample_dict_payload):
        """hmac_verify must work with dict payloads."""
        sig = hmac_sign(sample_dict_payload, hmac_key)
        assert hmac_verify(sample_dict_payload, sig, hmac_key) is True

    def test_bytes_payload_round_trip(self, hmac_key, sample_bytes_payload):
        """hmac_verify must work with bytes payloads."""
        sig = hmac_sign(sample_bytes_payload, hmac_key)
        assert hmac_verify(sample_bytes_payload, sig, hmac_key) is True

    def test_tampered_dict_returns_false(self, hmac_key, sample_dict_payload):
        """hmac_verify must return False when dict payload has been tampered with."""
        sig = hmac_sign(sample_dict_payload, hmac_key)
        tampered = dict(sample_dict_payload)
        tampered["agent_id"] = "agent-evil"
        assert hmac_verify(tampered, sig, hmac_key) is False


# ===========================================================================
# Test Class 4: dual_sign
# ===========================================================================


class TestDualSign:
    """Tests for dual_sign() function."""

    def test_ed25519_only_when_no_hmac_key(self, keypair, sample_dict_payload):
        """dual_sign without hmac_key must produce DualSignature with only Ed25519."""
        private_key, _ = keypair
        ds = dual_sign(sample_dict_payload, private_key)
        assert isinstance(ds, DualSignature)
        assert isinstance(ds.ed25519_signature, str)
        assert ds.hmac_signature is None
        assert ds.has_hmac is False

    def test_both_signatures_when_hmac_key_provided(
        self, keypair, hmac_key, sample_dict_payload
    ):
        """dual_sign with hmac_key must produce DualSignature with both signatures."""
        private_key, _ = keypair
        ds = dual_sign(sample_dict_payload, private_key, hmac_key=hmac_key)
        assert isinstance(ds, DualSignature)
        assert isinstance(ds.ed25519_signature, str)
        assert isinstance(ds.hmac_signature, str)
        assert ds.has_hmac is True

    def test_ed25519_matches_standalone_sign(self, keypair, sample_dict_payload):
        """The Ed25519 component of dual_sign must match standalone sign()."""
        private_key, _ = keypair
        ds = dual_sign(sample_dict_payload, private_key)
        standalone_sig = sign(sample_dict_payload, private_key)
        assert ds.ed25519_signature == standalone_sig

    def test_hmac_matches_standalone_hmac_sign(
        self, keypair, hmac_key, sample_dict_payload
    ):
        """The HMAC component of dual_sign must match standalone hmac_sign()."""
        private_key, _ = keypair
        ds = dual_sign(sample_dict_payload, private_key, hmac_key=hmac_key)
        standalone_hmac = hmac_sign(sample_dict_payload, hmac_key)
        assert ds.hmac_signature == standalone_hmac

    def test_deterministic_same_inputs(self, keypair, hmac_key, sample_dict_payload):
        """dual_sign with same inputs must produce same output."""
        private_key, _ = keypair
        ds1 = dual_sign(sample_dict_payload, private_key, hmac_key=hmac_key)
        ds2 = dual_sign(sample_dict_payload, private_key, hmac_key=hmac_key)
        assert ds1.ed25519_signature == ds2.ed25519_signature
        assert ds1.hmac_signature == ds2.hmac_signature

    def test_string_payload(self, keypair, hmac_key, sample_str_payload):
        """dual_sign must work with string payloads."""
        private_key, _ = keypair
        ds = dual_sign(sample_str_payload, private_key, hmac_key=hmac_key)
        assert isinstance(ds.ed25519_signature, str)
        assert isinstance(ds.hmac_signature, str)

    def test_bytes_payload(self, keypair, hmac_key, sample_bytes_payload):
        """dual_sign must work with bytes payloads."""
        private_key, _ = keypair
        ds = dual_sign(sample_bytes_payload, private_key, hmac_key=hmac_key)
        assert isinstance(ds.ed25519_signature, str)
        assert isinstance(ds.hmac_signature, str)

    def test_different_payloads_different_signatures(self, keypair, hmac_key):
        """Different payloads must produce different DualSignatures."""
        private_key, _ = keypair
        ds1 = dual_sign({"a": 1}, private_key, hmac_key=hmac_key)
        ds2 = dual_sign({"a": 2}, private_key, hmac_key=hmac_key)
        assert ds1.ed25519_signature != ds2.ed25519_signature
        assert ds1.hmac_signature != ds2.hmac_signature


# ===========================================================================
# Test Class 5: dual_verify
# ===========================================================================


class TestDualVerify:
    """Tests for dual_verify() function."""

    def test_valid_ed25519_only(self, keypair, sample_dict_payload):
        """dual_verify must return True for valid Ed25519-only DualSignature."""
        private_key, public_key = keypair
        ds = dual_sign(sample_dict_payload, private_key)
        assert dual_verify(sample_dict_payload, ds, public_key) is True

    def test_valid_both_signatures(self, keypair, hmac_key, sample_dict_payload):
        """dual_verify must return True when both Ed25519 and HMAC are valid."""
        private_key, public_key = keypair
        ds = dual_sign(sample_dict_payload, private_key, hmac_key=hmac_key)
        assert (
            dual_verify(sample_dict_payload, ds, public_key, hmac_key=hmac_key) is True
        )

    def test_invalid_ed25519_fails(self, keypair, sample_dict_payload):
        """dual_verify must return False when Ed25519 signature is invalid."""
        _, public_key = keypair
        # Create a DualSignature with a bogus Ed25519 signature
        bogus_ed = base64.b64encode(b"\x00" * 64).decode("utf-8")
        ds = DualSignature(ed25519_signature=bogus_ed)
        assert dual_verify(sample_dict_payload, ds, public_key) is False

    def test_invalid_hmac_fails(self, keypair, hmac_key, sample_dict_payload):
        """dual_verify must return False when HMAC signature is invalid but Ed25519 is valid."""
        private_key, public_key = keypair
        ed_sig = sign(sample_dict_payload, private_key)
        bogus_hmac = base64.b64encode(b"\x00" * 32).decode("utf-8")
        ds = DualSignature(ed25519_signature=ed_sig, hmac_signature=bogus_hmac)
        assert (
            dual_verify(sample_dict_payload, ds, public_key, hmac_key=hmac_key) is False
        )

    def test_ed25519_always_checked(self, keypair, hmac_key, sample_dict_payload):
        """Ed25519 is always mandatory. Invalid Ed25519 must fail even with valid HMAC."""
        private_key, public_key = keypair
        valid_hmac = hmac_sign(sample_dict_payload, hmac_key)
        bogus_ed = base64.b64encode(b"\x00" * 64).decode("utf-8")
        ds = DualSignature(ed25519_signature=bogus_ed, hmac_signature=valid_hmac)
        assert (
            dual_verify(sample_dict_payload, ds, public_key, hmac_key=hmac_key) is False
        )

    def test_hmac_skipped_when_no_key_provided(
        self, keypair, hmac_key, sample_dict_payload
    ):
        """When hmac_key is not provided to dual_verify, HMAC check must be skipped."""
        private_key, public_key = keypair
        ds = dual_sign(sample_dict_payload, private_key, hmac_key=hmac_key)
        # Verify without providing hmac_key -- should succeed (HMAC check skipped)
        assert dual_verify(sample_dict_payload, ds, public_key) is True

    def test_hmac_skipped_when_no_hmac_in_signature(
        self, keypair, hmac_key, sample_dict_payload
    ):
        """When DualSignature has no HMAC, providing hmac_key should not cause failure."""
        private_key, public_key = keypair
        ds = dual_sign(sample_dict_payload, private_key)  # No HMAC key
        assert ds.has_hmac is False
        # Verify with hmac_key -- should succeed since there's no HMAC to check
        assert (
            dual_verify(sample_dict_payload, ds, public_key, hmac_key=hmac_key) is True
        )

    def test_tampered_payload_fails_ed25519(self, keypair, sample_dict_payload):
        """Tampered payload must fail Ed25519 verification."""
        private_key, public_key = keypair
        ds = dual_sign(sample_dict_payload, private_key)
        tampered = dict(sample_dict_payload)
        tampered["agent_id"] = "evil-agent"
        assert dual_verify(tampered, ds, public_key) is False

    def test_tampered_payload_fails_both(self, keypair, hmac_key, sample_dict_payload):
        """Tampered payload must fail both Ed25519 and HMAC verification."""
        private_key, public_key = keypair
        ds = dual_sign(sample_dict_payload, private_key, hmac_key=hmac_key)
        tampered = dict(sample_dict_payload)
        tampered["agent_id"] = "evil-agent"
        assert dual_verify(tampered, ds, public_key, hmac_key=hmac_key) is False

    def test_wrong_public_key_fails(self, keypair, sample_dict_payload):
        """Verifying with wrong public key must fail."""
        private_key, _ = keypair
        _, wrong_public_key = generate_keypair()
        ds = dual_sign(sample_dict_payload, private_key)
        assert dual_verify(sample_dict_payload, ds, wrong_public_key) is False

    def test_wrong_hmac_key_fails(self, keypair, hmac_key, sample_dict_payload):
        """Verifying with wrong HMAC key must fail."""
        private_key, public_key = keypair
        ds = dual_sign(sample_dict_payload, private_key, hmac_key=hmac_key)
        wrong_hmac_key = secrets.token_bytes(32)
        assert (
            dual_verify(sample_dict_payload, ds, public_key, hmac_key=wrong_hmac_key)
            is False
        )

    def test_string_payload_round_trip(self, keypair, hmac_key, sample_str_payload):
        """dual_sign + dual_verify must work end-to-end with string payload."""
        private_key, public_key = keypair
        ds = dual_sign(sample_str_payload, private_key, hmac_key=hmac_key)
        assert (
            dual_verify(sample_str_payload, ds, public_key, hmac_key=hmac_key) is True
        )

    def test_bytes_payload_round_trip(self, keypair, hmac_key, sample_bytes_payload):
        """dual_sign + dual_verify must work end-to-end with bytes payload."""
        private_key, public_key = keypair
        ds = dual_sign(sample_bytes_payload, private_key, hmac_key=hmac_key)
        assert (
            dual_verify(sample_bytes_payload, ds, public_key, hmac_key=hmac_key) is True
        )


# ===========================================================================
# Test Class 6: Serialization Round-Trip with Real Signatures
# ===========================================================================


class TestDualSignatureSerializationWithRealSigs:
    """Tests for DualSignature serialization round-trip using real cryptographic signatures."""

    def test_to_dict_from_dict_preserves_verification_ed25519_only(
        self, keypair, sample_dict_payload
    ):
        """Serialized and deserialized DualSignature must still verify (Ed25519 only)."""
        private_key, public_key = keypair
        ds = dual_sign(sample_dict_payload, private_key)
        d = ds.to_dict()
        restored = DualSignature.from_dict(d)
        assert dual_verify(sample_dict_payload, restored, public_key) is True

    def test_to_dict_from_dict_preserves_verification_both(
        self, keypair, hmac_key, sample_dict_payload
    ):
        """Serialized and deserialized DualSignature must still verify (both signatures)."""
        private_key, public_key = keypair
        ds = dual_sign(sample_dict_payload, private_key, hmac_key=hmac_key)
        d = ds.to_dict()
        restored = DualSignature.from_dict(d)
        assert (
            dual_verify(sample_dict_payload, restored, public_key, hmac_key=hmac_key)
            is True
        )


# ===========================================================================
# Test Class 7: Security Properties
# ===========================================================================


class TestDualSignatureSecurity:
    """Security-focused tests for the DualSignature system."""

    def test_hmac_uses_constant_time_comparison(self, hmac_key):
        """hmac_verify must use hmac.compare_digest, not == operator.

        We verify this indirectly by confirming the function correctly
        identifies valid and invalid signatures (a timing-vulnerable ==
        would still produce correct results, but this test documents
        the requirement and the implementation can be audited).
        """
        payload = b"security test payload"
        sig = hmac_sign(payload, hmac_key)
        # Valid
        assert hmac_verify(payload, sig, hmac_key) is True
        # One-bit-different signature
        sig_bytes = base64.b64decode(sig)
        # Flip one bit in the first byte
        tampered_bytes = bytes([sig_bytes[0] ^ 0x01]) + sig_bytes[1:]
        tampered_sig = base64.b64encode(tampered_bytes).decode("utf-8")
        assert hmac_verify(payload, tampered_sig, hmac_key) is False

    def test_hmac_alone_not_sufficient_for_external_verification(
        self, keypair, hmac_key
    ):
        """Ed25519 is always required. HMAC alone is not sufficient.

        This tests that dual_verify always checks Ed25519, regardless
        of HMAC status.
        """
        private_key, public_key = keypair
        payload = {"critical": "data"}
        valid_hmac = hmac_sign(payload, hmac_key)
        # Create DualSignature with bogus Ed25519 but valid HMAC
        bogus_ed = base64.b64encode(b"\x00" * 64).decode("utf-8")
        ds = DualSignature(ed25519_signature=bogus_ed, hmac_signature=valid_hmac)
        # Must fail -- Ed25519 is mandatory
        assert dual_verify(payload, ds, public_key, hmac_key=hmac_key) is False

    def test_multiple_agents_dual_sign_same_payload(
        self, hmac_key, sample_dict_payload
    ):
        """Multiple agents with different Ed25519 keys can dual-sign the same payload."""
        priv1, pub1 = generate_keypair()
        priv2, pub2 = generate_keypair()

        ds1 = dual_sign(sample_dict_payload, priv1, hmac_key=hmac_key)
        ds2 = dual_sign(sample_dict_payload, priv2, hmac_key=hmac_key)

        # Ed25519 signatures differ
        assert ds1.ed25519_signature != ds2.ed25519_signature
        # HMAC signatures are the same (same key, same payload)
        assert ds1.hmac_signature == ds2.hmac_signature

        # Each verifies with its own public key
        assert dual_verify(sample_dict_payload, ds1, pub1, hmac_key=hmac_key) is True
        assert dual_verify(sample_dict_payload, ds2, pub2, hmac_key=hmac_key) is True

        # Cross-verification must fail (Ed25519 mismatch)
        assert dual_verify(sample_dict_payload, ds1, pub2, hmac_key=hmac_key) is False
        assert dual_verify(sample_dict_payload, ds2, pub1, hmac_key=hmac_key) is False


# ===========================================================================
# Test Class 8: Public API Exports
# ===========================================================================


class TestDualSignatureExports:
    """Tests that DualSignature system is properly exported from kailash.trust package."""

    def test_dual_signature_importable_from_eatp(self):
        """DualSignature must be importable from top-level eatp package."""
        from kailash.trust import DualSignature as DS

        assert DS is DualSignature

    def test_dual_sign_importable_from_eatp(self):
        """dual_sign must be importable from top-level eatp package."""
        from kailash.trust import dual_sign as ds

        assert ds is dual_sign

    def test_dual_verify_importable_from_eatp(self):
        """dual_verify must be importable from top-level eatp package."""
        from kailash.trust import dual_verify as dv

        assert dv is dual_verify

    def test_hmac_sign_importable_from_eatp(self):
        """hmac_sign must be importable from top-level eatp package."""
        from kailash.trust import hmac_sign as hs

        assert hs is hmac_sign

    def test_hmac_verify_importable_from_eatp(self):
        """hmac_verify must be importable from top-level eatp package."""
        from kailash.trust import hmac_verify as hv

        assert hv is hmac_verify

    def test_all_new_exports_in_eatp_all(self):
        """All DualSignature exports must be in eatp.__all__."""
        import kailash.trust

        for name in [
            "DualSignature",
            "dual_sign",
            "dual_verify",
            "hmac_sign",
            "hmac_verify",
        ]:
            assert (
                name in kailash.trust.__all__
            ), f"{name} missing from kailash.trust.__all__"

    def test_existing_crypto_exports_intact(self):
        """Adding DualSignature exports must not break existing crypto exports."""
        import kailash.trust

        for name in ["generate_keypair", "sign", "verify_signature"]:
            assert hasattr(
                kailash.trust, name
            ), f"{name} missing from kailash.trust after changes"
            assert (
                name in kailash.trust.__all__
            ), f"{name} missing from kailash.trust.__all__"
