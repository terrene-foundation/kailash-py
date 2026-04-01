# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for SignedEnvelope -- Ed25519 signing for ConstraintEnvelopeConfig.

Issue #207: ConstraintEnvelope Ed25519 signing.

Covers:
- sign_envelope() creates a valid SignedEnvelope
- verify() validates signature + checks expiry
- is_valid() non-throwing check
- Tampered envelopes fail verification
- Expired envelopes fail verification
- Serialization round-trip (to_dict / from_dict)
- Wrong key fails verification
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.envelopes import (
    SignedEnvelope,
    sign_envelope,
)
from kailash.trust.signing.crypto import generate_keypair


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair() -> tuple[str, str]:
    """Generate an Ed25519 keypair."""
    return generate_keypair()


@pytest.fixture
def envelope() -> ConstraintEnvelopeConfig:
    """A test ConstraintEnvelopeConfig."""
    return ConstraintEnvelopeConfig(
        id="test-env-001",
        description="Test envelope for signing",
        confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        financial=FinancialConstraintConfig(
            max_spend_usd=1000.0,
            api_cost_budget_usd=500.0,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write", "deploy"],
        ),
    )


@pytest.fixture
def signed(
    envelope: ConstraintEnvelopeConfig, keypair: tuple[str, str]
) -> SignedEnvelope:
    """A signed envelope using the test keypair."""
    private_key, _ = keypair
    return sign_envelope(envelope, private_key, signed_by="D1-R1")


# ---------------------------------------------------------------------------
# Signing Tests
# ---------------------------------------------------------------------------


class TestSignEnvelope:
    """sign_envelope() creates valid SignedEnvelope instances."""

    def test_creates_signed_envelope(
        self,
        signed: SignedEnvelope,
        envelope: ConstraintEnvelopeConfig,
    ) -> None:
        """sign_envelope returns a SignedEnvelope with correct fields."""
        assert isinstance(signed, SignedEnvelope)
        assert signed.envelope == envelope
        assert signed.signed_by == "D1-R1"
        assert signed.signature  # non-empty
        assert signed.signed_at is not None
        assert signed.expires_at is not None
        # Default expiry is 90 days
        delta = signed.expires_at - signed.signed_at
        assert 89 <= delta.days <= 91

    def test_custom_expiry(
        self,
        envelope: ConstraintEnvelopeConfig,
        keypair: tuple[str, str],
    ) -> None:
        """Custom expires_in_days is respected."""
        private_key, _ = keypair
        signed = sign_envelope(
            envelope, private_key, signed_by="D1-R1", expires_in_days=30
        )
        delta = signed.expires_at - signed.signed_at
        assert 29 <= delta.days <= 31

    def test_zero_expiry_raises(
        self,
        envelope: ConstraintEnvelopeConfig,
        keypair: tuple[str, str],
    ) -> None:
        """expires_in_days <= 0 raises ValueError."""
        private_key, _ = keypair
        with pytest.raises(ValueError, match="expires_in_days must be positive"):
            sign_envelope(envelope, private_key, signed_by="D1-R1", expires_in_days=0)

    def test_frozen_dataclass(self, signed: SignedEnvelope) -> None:
        """SignedEnvelope is frozen -- cannot be mutated."""
        with pytest.raises(AttributeError):
            signed.signature = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Verification Tests
# ---------------------------------------------------------------------------


class TestVerify:
    """SignedEnvelope.verify() validates signature + expiry."""

    def test_valid_signature(
        self, signed: SignedEnvelope, keypair: tuple[str, str]
    ) -> None:
        """A freshly signed envelope verifies with the matching public key."""
        _, public_key = keypair
        assert signed.verify(public_key) is True

    def test_wrong_key_fails(self, signed: SignedEnvelope) -> None:
        """Verification with a different key returns False."""
        _, other_public = generate_keypair()
        assert signed.verify(other_public) is False

    def test_tampered_envelope_fails(
        self,
        envelope: ConstraintEnvelopeConfig,
        keypair: tuple[str, str],
    ) -> None:
        """Modifying the envelope after signing invalidates the signature."""
        private_key, public_key = keypair
        signed = sign_envelope(envelope, private_key, signed_by="D1-R1")

        # Create a new SignedEnvelope with a different envelope but same signature
        tampered_envelope = ConstraintEnvelopeConfig(
            id="tampered-env",
            description="Tampered",
            financial=FinancialConstraintConfig(max_spend_usd=999999.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["everything"],
            ),
        )
        tampered = SignedEnvelope(
            envelope=tampered_envelope,
            signature=signed.signature,
            signed_at=signed.signed_at,
            signed_by=signed.signed_by,
            expires_at=signed.expires_at,
        )
        assert tampered.verify(public_key) is False

    def test_expired_envelope_fails(
        self,
        envelope: ConstraintEnvelopeConfig,
        keypair: tuple[str, str],
    ) -> None:
        """An expired SignedEnvelope returns False on verify."""
        private_key, public_key = keypair
        now = datetime.now(UTC)
        # Create a manually expired signed envelope
        from kailash.trust.signing.crypto import serialize_for_signing, sign

        payload = serialize_for_signing(envelope.model_dump(mode="json"))
        signature = sign(payload, private_key)

        expired = SignedEnvelope(
            envelope=envelope,
            signature=signature,
            signed_at=now - timedelta(days=100),
            signed_by="D1-R1",
            expires_at=now - timedelta(days=10),  # Expired 10 days ago
        )
        assert expired.verify(public_key) is False


# ---------------------------------------------------------------------------
# is_valid() Tests
# ---------------------------------------------------------------------------


class TestIsValid:
    """SignedEnvelope.is_valid() non-throwing check."""

    def test_valid_returns_true(
        self, signed: SignedEnvelope, keypair: tuple[str, str]
    ) -> None:
        """is_valid returns True for a valid signed envelope."""
        _, public_key = keypair
        assert signed.is_valid(public_key) is True

    def test_invalid_returns_false(self, signed: SignedEnvelope) -> None:
        """is_valid returns False for wrong key without raising."""
        _, other_public = generate_keypair()
        assert signed.is_valid(other_public) is False

    def test_garbage_key_returns_false(self, signed: SignedEnvelope) -> None:
        """is_valid returns False for malformed key without raising."""
        assert signed.is_valid("not-a-valid-key") is False


# ---------------------------------------------------------------------------
# Serialization Tests
# ---------------------------------------------------------------------------


class TestSerialization:
    """SignedEnvelope.to_dict() / from_dict() round-trip."""

    def test_round_trip(self, signed: SignedEnvelope, keypair: tuple[str, str]) -> None:
        """to_dict -> from_dict produces equivalent object."""
        data = signed.to_dict()
        restored = SignedEnvelope.from_dict(data)

        assert restored.signature == signed.signature
        assert restored.signed_by == signed.signed_by
        assert restored.envelope.id == signed.envelope.id

        # Verify the restored envelope is still valid
        _, public_key = keypair
        assert restored.verify(public_key) is True

    def test_to_dict_structure(self, signed: SignedEnvelope) -> None:
        """to_dict produces expected keys."""
        data = signed.to_dict()
        assert "envelope" in data
        assert "signature" in data
        assert "signed_at" in data
        assert "signed_by" in data
        assert "expires_at" in data
        assert isinstance(data["envelope"], dict)
        assert isinstance(data["signature"], str)
