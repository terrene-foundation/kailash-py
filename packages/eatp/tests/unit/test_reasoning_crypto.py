# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP Reasoning Trace crypto functions (TODO-010).

Covers:
- hash_reasoning_trace: deterministic SHA-256 hash of reasoning trace
- sign_reasoning_trace: Ed25519 signing of reasoning trace payload
- verify_reasoning_signature: verification of reasoning trace signature
- Integration with existing crypto functions (sign, verify_signature)
- Tamper detection: any field change must invalidate signature
- Hash sensitivity: any field change must produce different hash

Written BEFORE implementation (TDD). Tests define the contract.
"""

import hashlib
import json

import pytest
from datetime import datetime, timezone

from eatp.crypto import (
    generate_keypair,
    hash_reasoning_trace,
    serialize_for_signing,
    sign,
    sign_reasoning_trace,
    verify_reasoning_signature,
    verify_signature,
)
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXED_TIMESTAMP = datetime(2026, 3, 11, 14, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def minimal_trace():
    """A ReasoningTrace with only required fields."""
    return ReasoningTrace(
        decision="Approve data access for agent-beta",
        rationale="Agent has valid capability attestation and passes constraint checks",
        confidentiality=ConfidentialityLevel.RESTRICTED,
        timestamp=FIXED_TIMESTAMP,
    )


@pytest.fixture
def full_trace():
    """A ReasoningTrace with all fields populated."""
    return ReasoningTrace(
        decision="Delegate financial analysis to agent-gamma",
        rationale="Agent-gamma has specialized financial analysis capabilities and lower cost",
        confidentiality=ConfidentialityLevel.CONFIDENTIAL,
        timestamp=FIXED_TIMESTAMP,
        alternatives_considered=[
            "Use agent-delta (rejected: higher latency)",
            "Process in-house (rejected: lacks capability)",
        ],
        evidence=[
            {
                "type": "capability_check",
                "result": "passed",
                "capability": "financial_analysis",
            },
            {"type": "cost_estimate", "value": 0.05, "currency": "USD"},
        ],
        methodology="cost_benefit",
        confidence=0.87,
    )


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair for signing tests."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


# ===========================================================================
# Test Class 1: hash_reasoning_trace
# ===========================================================================


class TestHashReasoningTrace:
    """Tests for hash_reasoning_trace() function."""

    def test_returns_hex_string(self, minimal_trace):
        """hash_reasoning_trace must return a hex-encoded string."""
        result = hash_reasoning_trace(minimal_trace)
        assert isinstance(result, str)
        # SHA-256 hex digest is 64 characters
        assert len(result) == 64
        # Must be valid hex
        int(result, 16)

    def test_deterministic_same_trace(self, full_trace):
        """Calling hash_reasoning_trace twice on the same trace must produce the same hash."""
        hash1 = hash_reasoning_trace(full_trace)
        hash2 = hash_reasoning_trace(full_trace)
        assert hash1 == hash2

    def test_deterministic_equivalent_traces(self):
        """Two independently constructed but equivalent traces must hash the same."""
        trace1 = ReasoningTrace(
            decision="Test decision",
            rationale="Test rationale",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.5,
        )
        trace2 = ReasoningTrace(
            decision="Test decision",
            rationale="Test rationale",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.5,
        )
        assert hash_reasoning_trace(trace1) == hash_reasoning_trace(trace2)

    def test_uses_serialize_for_signing_then_sha256(self, full_trace):
        """hash_reasoning_trace must use serialize_for_signing(trace.to_signing_payload()) then SHA-256."""
        expected_serialized = serialize_for_signing(full_trace.to_signing_payload())
        expected_hash = hashlib.sha256(expected_serialized.encode("utf-8")).hexdigest()
        actual = hash_reasoning_trace(full_trace)
        assert actual == expected_hash

    def test_different_decision_different_hash(self):
        """Changing the decision field must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="Decision A",
            rationale="Same rationale",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        trace2 = ReasoningTrace(
            decision="Decision B",
            rationale="Same rationale",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        assert hash_reasoning_trace(trace1) != hash_reasoning_trace(trace2)

    def test_different_rationale_different_hash(self):
        """Changing the rationale field must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="Same decision",
            rationale="Rationale A",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        trace2 = ReasoningTrace(
            decision="Same decision",
            rationale="Rationale B",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        assert hash_reasoning_trace(trace1) != hash_reasoning_trace(trace2)

    def test_different_confidentiality_different_hash(self):
        """Changing the confidentiality level must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        trace2 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.SECRET,
            timestamp=FIXED_TIMESTAMP,
        )
        assert hash_reasoning_trace(trace1) != hash_reasoning_trace(trace2)

    def test_different_timestamp_different_hash(self):
        """Changing the timestamp must produce a different hash."""
        ts1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        trace1 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=ts1,
        )
        trace2 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=ts2,
        )
        assert hash_reasoning_trace(trace1) != hash_reasoning_trace(trace2)

    def test_different_confidence_different_hash(self):
        """Changing the confidence must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.5,
        )
        trace2 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.9,
        )
        assert hash_reasoning_trace(trace1) != hash_reasoning_trace(trace2)

    def test_different_methodology_different_hash(self):
        """Changing the methodology must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            methodology="risk_assessment",
        )
        trace2 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            methodology="cost_benefit",
        )
        assert hash_reasoning_trace(trace1) != hash_reasoning_trace(trace2)

    def test_different_alternatives_different_hash(self):
        """Changing alternatives_considered must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=["Alt A"],
        )
        trace2 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=["Alt B"],
        )
        assert hash_reasoning_trace(trace1) != hash_reasoning_trace(trace2)

    def test_different_evidence_different_hash(self):
        """Changing evidence must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            evidence=[{"type": "check", "result": "pass"}],
        )
        trace2 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            evidence=[{"type": "check", "result": "fail"}],
        )
        assert hash_reasoning_trace(trace1) != hash_reasoning_trace(trace2)

    def test_minimal_vs_full_trace_different_hash(self, minimal_trace, full_trace):
        """Minimal and full traces must produce different hashes."""
        assert hash_reasoning_trace(minimal_trace) != hash_reasoning_trace(full_trace)


# ===========================================================================
# Test Class 2: sign_reasoning_trace
# ===========================================================================


class TestSignReasoningTrace:
    """Tests for sign_reasoning_trace() function."""

    def test_returns_base64_string(self, minimal_trace, keypair):
        """sign_reasoning_trace must return a base64-encoded string."""
        private_key, _ = keypair
        signature = sign_reasoning_trace(minimal_trace, private_key)
        assert isinstance(signature, str)
        # Must be valid base64 (no exception on decode)
        import base64

        decoded = base64.b64decode(signature)
        # Ed25519 signature is 64 bytes
        assert len(decoded) == 64

    def test_deterministic_same_trace_same_key(self, full_trace, keypair):
        """Signing the same trace with the same key must produce the same signature."""
        private_key, _ = keypair
        sig1 = sign_reasoning_trace(full_trace, private_key)
        sig2 = sign_reasoning_trace(full_trace, private_key)
        assert sig1 == sig2

    def test_different_keys_different_signatures(self, minimal_trace):
        """Signing the same trace with different keys must produce different signatures."""
        priv1, _ = generate_keypair()
        priv2, _ = generate_keypair()
        sig1 = sign_reasoning_trace(minimal_trace, priv1)
        sig2 = sign_reasoning_trace(minimal_trace, priv2)
        assert sig1 != sig2

    def test_different_traces_different_signatures(
        self, minimal_trace, full_trace, keypair
    ):
        """Signing different traces with the same key must produce different signatures."""
        private_key, _ = keypair
        sig1 = sign_reasoning_trace(minimal_trace, private_key)
        sig2 = sign_reasoning_trace(full_trace, private_key)
        assert sig1 != sig2

    def test_consistent_with_sign_function(self, full_trace, keypair):
        """sign_reasoning_trace must produce the same result as sign(trace.to_signing_payload(), key)."""
        private_key, _ = keypair
        reasoning_sig = sign_reasoning_trace(full_trace, private_key)
        direct_sig = sign(full_trace.to_signing_payload(), private_key)
        assert reasoning_sig == direct_sig

    def test_invalid_private_key_raises(self, minimal_trace):
        """sign_reasoning_trace with invalid private key must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid private key"):
            sign_reasoning_trace(minimal_trace, "not-a-valid-key")


# ===========================================================================
# Test Class 3: verify_reasoning_signature
# ===========================================================================


class TestVerifyReasoningSignature:
    """Tests for verify_reasoning_signature() function."""

    def test_valid_signature_returns_true(self, full_trace, keypair):
        """verify_reasoning_signature must return True for a valid signature."""
        private_key, public_key = keypair
        signature = sign_reasoning_trace(full_trace, private_key)
        assert verify_reasoning_signature(full_trace, signature, public_key) is True

    def test_minimal_trace_round_trip(self, minimal_trace, keypair):
        """Sign and verify round-trip must work for minimal trace."""
        private_key, public_key = keypair
        signature = sign_reasoning_trace(minimal_trace, private_key)
        assert verify_reasoning_signature(minimal_trace, signature, public_key) is True

    def test_tampered_decision_fails(self, keypair):
        """Changing the decision after signing must cause verification to fail."""
        private_key, public_key = keypair
        original = ReasoningTrace(
            decision="Original decision",
            rationale="Some rationale",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=FIXED_TIMESTAMP,
        )
        signature = sign_reasoning_trace(original, private_key)

        tampered = ReasoningTrace(
            decision="Tampered decision",
            rationale="Some rationale",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=FIXED_TIMESTAMP,
        )
        assert verify_reasoning_signature(tampered, signature, public_key) is False

    def test_tampered_rationale_fails(self, keypair):
        """Changing the rationale after signing must cause verification to fail."""
        private_key, public_key = keypair
        original = ReasoningTrace(
            decision="Decision",
            rationale="Original rationale",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=FIXED_TIMESTAMP,
        )
        signature = sign_reasoning_trace(original, private_key)

        tampered = ReasoningTrace(
            decision="Decision",
            rationale="Tampered rationale",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=FIXED_TIMESTAMP,
        )
        assert verify_reasoning_signature(tampered, signature, public_key) is False

    def test_tampered_confidentiality_fails(self, keypair):
        """Changing the confidentiality level after signing must cause verification to fail."""
        private_key, public_key = keypair
        original = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        signature = sign_reasoning_trace(original, private_key)

        tampered = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.TOP_SECRET,
            timestamp=FIXED_TIMESTAMP,
        )
        assert verify_reasoning_signature(tampered, signature, public_key) is False

    def test_tampered_timestamp_fails(self, keypair):
        """Changing the timestamp after signing must cause verification to fail."""
        private_key, public_key = keypair
        original = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        signature = sign_reasoning_trace(original, private_key)

        tampered = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        )
        assert verify_reasoning_signature(tampered, signature, public_key) is False

    def test_tampered_confidence_fails(self, keypair):
        """Changing the confidence after signing must cause verification to fail."""
        private_key, public_key = keypair
        original = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.9,
        )
        signature = sign_reasoning_trace(original, private_key)

        tampered = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.1,
        )
        assert verify_reasoning_signature(tampered, signature, public_key) is False

    def test_tampered_methodology_fails(self, keypair):
        """Changing the methodology after signing must cause verification to fail."""
        private_key, public_key = keypair
        original = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            methodology="risk_assessment",
        )
        signature = sign_reasoning_trace(original, private_key)

        tampered = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            methodology="cost_benefit",
        )
        assert verify_reasoning_signature(tampered, signature, public_key) is False

    def test_tampered_alternatives_fails(self, keypair):
        """Changing alternatives_considered after signing must cause verification to fail."""
        private_key, public_key = keypair
        original = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=["Alt A"],
        )
        signature = sign_reasoning_trace(original, private_key)

        tampered = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=["Alt A", "Injected alt"],
        )
        assert verify_reasoning_signature(tampered, signature, public_key) is False

    def test_tampered_evidence_fails(self, keypair):
        """Changing evidence after signing must cause verification to fail."""
        private_key, public_key = keypair
        original = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            evidence=[{"type": "check", "result": "pass"}],
        )
        signature = sign_reasoning_trace(original, private_key)

        tampered = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            evidence=[{"type": "check", "result": "fail"}],
        )
        assert verify_reasoning_signature(tampered, signature, public_key) is False

    def test_wrong_public_key_fails(self, full_trace):
        """Verifying with a different key pair's public key must fail."""
        priv1, pub1 = generate_keypair()
        _, pub2 = generate_keypair()
        signature = sign_reasoning_trace(full_trace, priv1)
        assert verify_reasoning_signature(full_trace, signature, pub2) is False

    def test_consistent_with_verify_signature_function(self, full_trace, keypair):
        """verify_reasoning_signature must behave the same as verify_signature(payload, sig, key)."""
        private_key, public_key = keypair
        signature = sign_reasoning_trace(full_trace, private_key)

        reasoning_result = verify_reasoning_signature(full_trace, signature, public_key)
        direct_result = verify_signature(
            full_trace.to_signing_payload(), signature, public_key
        )
        assert reasoning_result == direct_result
        assert reasoning_result is True


# ===========================================================================
# Test Class 4: Integration - Full Sign/Verify/Hash Workflow
# ===========================================================================


class TestReasoningCryptoIntegration:
    """Integration tests for reasoning trace crypto functions working together."""

    def test_full_workflow_sign_verify_hash(self, full_trace, keypair):
        """Complete workflow: hash, sign, verify must all work together."""
        private_key, public_key = keypair

        # Hash the trace
        trace_hash = hash_reasoning_trace(full_trace)
        assert isinstance(trace_hash, str)
        assert len(trace_hash) == 64

        # Sign the trace
        signature = sign_reasoning_trace(full_trace, private_key)
        assert isinstance(signature, str)

        # Verify the signature
        assert verify_reasoning_signature(full_trace, signature, public_key) is True

    def test_hash_and_signature_are_independent(self, full_trace, keypair):
        """Hash and signature must be different representations (hash is SHA-256 hex, signature is base64 Ed25519)."""
        private_key, _ = keypair
        trace_hash = hash_reasoning_trace(full_trace)
        signature = sign_reasoning_trace(full_trace, private_key)
        # They must not be the same (different algorithms, different formats)
        assert trace_hash != signature

    def test_multiple_agents_can_sign_same_trace(self, full_trace):
        """Multiple agents with different keys can independently sign the same trace."""
        priv1, pub1 = generate_keypair()
        priv2, pub2 = generate_keypair()

        sig1 = sign_reasoning_trace(full_trace, priv1)
        sig2 = sign_reasoning_trace(full_trace, priv2)

        # Different signatures
        assert sig1 != sig2

        # Each verifies with its own public key
        assert verify_reasoning_signature(full_trace, sig1, pub1) is True
        assert verify_reasoning_signature(full_trace, sig2, pub2) is True

        # Cross-verification must fail
        assert verify_reasoning_signature(full_trace, sig1, pub2) is False
        assert verify_reasoning_signature(full_trace, sig2, pub1) is False

    def test_hash_is_stable_across_serialization_round_trip(self, full_trace):
        """Hash must be the same before and after to_dict/from_dict round-trip."""
        hash_before = hash_reasoning_trace(full_trace)
        d = full_trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        hash_after = hash_reasoning_trace(restored)
        assert hash_before == hash_after

    def test_signature_verifies_after_serialization_round_trip(
        self, full_trace, keypair
    ):
        """Signature created before serialization must verify after deserialization."""
        private_key, public_key = keypair
        signature = sign_reasoning_trace(full_trace, private_key)

        # Serialize and deserialize
        d = full_trace.to_dict()
        restored = ReasoningTrace.from_dict(d)

        # Signature must still verify
        assert verify_reasoning_signature(restored, signature, public_key) is True
