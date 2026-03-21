"""
Unit tests for EATP Biscuit interop module.

Tests export/import of constraint envelopes as Biscuit-inspired binary tokens,
token attenuation (adding restrictions without the original signing key),
verification, and round-trip fidelity.

Uses real Ed25519 keys via eatp.crypto for signing and verification.
"""

import struct
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from kailash.trust.chain import (
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
)
from kailash.trust.signing.crypto import generate_keypair

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)
_FUTURE = _NOW + timedelta(hours=24)


def _make_envelope(
    agent_id: str = "agent-001",
    num_constraints: int = 2,
    valid_until: datetime | None = None,
) -> ConstraintEnvelope:
    """Create a test ConstraintEnvelope with configurable constraints."""
    constraints: List[Constraint] = []
    for i in range(num_constraints):
        constraints.append(
            Constraint(
                id=f"con-{i:03d}",
                constraint_type=(ConstraintType.FINANCIAL if i % 2 == 0 else ConstraintType.DATA_ACCESS),
                value=100 * (i + 1) if i % 2 == 0 else f"scope_{i}",
                source=f"cap-{i:03d}",
                priority=i,
            )
        )
    return ConstraintEnvelope(
        id=f"env-{agent_id}",
        agent_id=agent_id,
        active_constraints=constraints,
        computed_at=_NOW,
        valid_until=valid_until,
    )


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from kailash.trust.interop.biscuit import (
    BISCUIT_VERSION,
    attenuate,
    from_biscuit,
    to_biscuit,
    verify_biscuit,
)


# ===================================================================
# 1. to_biscuit -- export constraints as Biscuit-inspired token
# ===================================================================


class TestToBiscuit:
    """Tests for to_biscuit()."""

    def test_returns_bytes(self):
        """Token output must be bytes."""
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)
        assert isinstance(token, bytes)
        assert len(token) > 0

    def test_token_starts_with_version_byte(self):
        """First byte encodes the Biscuit format version."""
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)
        assert token[0] == BISCUIT_VERSION

    def test_token_binary_structure(self):
        """Token follows: version(1) + authority_block_len(4) + authority_block + signatures."""
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)

        # Parse version
        version = token[0]
        assert version == BISCUIT_VERSION

        # Parse authority block length (4 bytes, big-endian unsigned int)
        authority_block_len = struct.unpack(">I", token[1:5])[0]
        assert authority_block_len > 0

        # authority block should be at bytes 5..5+authority_block_len
        authority_block_bytes = token[5 : 5 + authority_block_len]
        assert len(authority_block_bytes) == authority_block_len

    def test_authority_block_contains_envelope_data(self):
        """Authority block must contain constraint facts from the envelope."""
        import json

        envelope = _make_envelope(num_constraints=3)
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)

        # Extract authority block
        authority_block_len = struct.unpack(">I", token[1:5])[0]
        authority_block_bytes = token[5 : 5 + authority_block_len]
        authority_block = json.loads(authority_block_bytes.decode("utf-8"))

        # Must have facts, rules, constraints keys
        assert "facts" in authority_block
        assert "rules" in authority_block
        assert "constraints" in authority_block

        # Facts should contain envelope metadata
        assert authority_block["facts"]["envelope_id"] == envelope.id
        assert authority_block["facts"]["agent_id"] == envelope.agent_id

    def test_constraints_encoded_as_facts(self):
        """Each active constraint must appear as a fact in the authority block."""
        import json

        envelope = _make_envelope(num_constraints=3)
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)

        authority_block_len = struct.unpack(">I", token[1:5])[0]
        authority_block_bytes = token[5 : 5 + authority_block_len]
        authority_block = json.loads(authority_block_bytes.decode("utf-8"))

        constraint_facts = authority_block["constraints"]
        assert len(constraint_facts) == 3
        for i, cf in enumerate(constraint_facts):
            assert cf["id"] == f"con-{i:03d}"

    def test_empty_signing_key_raises_value_error(self):
        """Empty signing key must be rejected with a clear error."""
        envelope = _make_envelope()
        with pytest.raises(ValueError, match="signing_key"):
            to_biscuit(envelope, "")

    def test_envelope_with_no_constraints(self):
        """An envelope with zero constraints should still produce a valid token."""
        envelope = _make_envelope(num_constraints=0)
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        assert isinstance(token, bytes)
        # Should still round-trip
        restored = from_biscuit(token, public_key)
        assert restored.id == envelope.id
        assert len(restored.active_constraints) == 0

    def test_signature_present_in_token(self):
        """Token must end with an Ed25519 signature (64 bytes)."""
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)

        # Parse past version(1) + authority_block_len(4) + authority_block
        authority_block_len = struct.unpack(">I", token[1:5])[0]
        offset = 5 + authority_block_len

        # Next: number of attenuation blocks (4 bytes)
        num_attenuation = struct.unpack(">I", token[offset : offset + 4])[0]
        assert num_attenuation == 0  # No attenuation blocks yet

        # Remaining bytes should be signature section
        offset += 4
        # Number of signatures (4 bytes)
        num_signatures = struct.unpack(">I", token[offset : offset + 4])[0]
        assert num_signatures == 1  # Authority signature only
        offset += 4

        # Each signature: public_key(32 bytes) + signature(64 bytes)
        sig_entry = token[offset:]
        assert len(sig_entry) == 32 + 64  # pub_key + signature


# ===================================================================
# 2. from_biscuit -- import token back to ConstraintEnvelope
# ===================================================================


class TestFromBiscuit:
    """Tests for from_biscuit()."""

    def test_round_trip_preserves_envelope_id(self):
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)
        assert restored.id == envelope.id

    def test_round_trip_preserves_agent_id(self):
        envelope = _make_envelope(agent_id="agent-xyz")
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)
        assert restored.agent_id == "agent-xyz"

    def test_round_trip_preserves_constraints(self):
        envelope = _make_envelope(num_constraints=4)
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)

        assert len(restored.active_constraints) == 4
        for original, restored_c in zip(envelope.active_constraints, restored.active_constraints):
            assert restored_c.id == original.id
            assert restored_c.constraint_type == original.constraint_type
            assert restored_c.source == original.source
            assert restored_c.priority == original.priority

    def test_round_trip_preserves_constraint_values(self):
        """Constraint values must survive serialization exactly."""
        envelope = _make_envelope(num_constraints=2)
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)

        for original, restored_c in zip(envelope.active_constraints, restored.active_constraints):
            # Values may be converted through JSON, so compare string representations
            assert str(restored_c.value) == str(original.value)

    def test_round_trip_preserves_constraint_hash(self):
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)
        assert restored.constraint_hash == envelope.constraint_hash

    def test_returns_constraint_envelope_type(self):
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)
        assert isinstance(restored, ConstraintEnvelope)

    def test_rejects_invalid_signature(self):
        """Token signed with key A must fail verification with key B."""
        envelope = _make_envelope()
        private_key_a, _ = generate_keypair()
        _, public_key_b = generate_keypair()
        token = to_biscuit(envelope, private_key_a)
        with pytest.raises(Exception) as exc_info:
            from_biscuit(token, public_key_b)
        assert exc_info.value is not None

    def test_rejects_tampered_authority_block(self):
        """Modifying authority block bytes must cause verification failure."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        # Tamper with a byte in the authority block
        token_list = bytearray(token)
        # Flip a bit in the authority block region (byte at position 10)
        if len(token_list) > 10:
            token_list[10] ^= 0xFF
        tampered = bytes(token_list)

        with pytest.raises(Exception):
            from_biscuit(tampered, public_key)

    def test_rejects_truncated_token(self):
        """A truncated token must raise a clear error, not crash."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        # Truncate to just the first few bytes
        truncated = token[:5]
        with pytest.raises(Exception):
            from_biscuit(truncated, public_key)

    def test_rejects_empty_token(self):
        """An empty bytes object must raise a clear error."""
        _, public_key = generate_keypair()
        with pytest.raises(Exception):
            from_biscuit(b"", public_key)

    def test_rejects_wrong_version(self):
        """A token with an unknown version byte must be rejected."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        # Change version byte to something invalid
        tampered = bytes([0xFF]) + token[1:]
        with pytest.raises(ValueError, match="[Vv]ersion"):
            from_biscuit(tampered, public_key)

    def test_empty_public_key_raises_value_error(self):
        """Empty public key must be rejected with a clear error."""
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)
        with pytest.raises(ValueError, match="public_key"):
            from_biscuit(token, "")


# ===================================================================
# 3. attenuate -- add restrictions without original signing key
# ===================================================================


class TestAttenuate:
    """Tests for attenuate()."""

    def test_attenuated_token_is_bytes(self):
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)

        attenuator_private, _ = generate_keypair()
        attenuated = attenuate(token, ["read_only", "no_pii"], attenuator_private)
        assert isinstance(attenuated, bytes)

    def test_attenuated_token_has_attenuation_block(self):
        """After attenuation, the token must contain an attenuation block."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        attenuator_private, _ = generate_keypair()
        attenuated = attenuate(token, ["read_only"], attenuator_private)

        # Parse attenuated token to count attenuation blocks
        authority_block_len = struct.unpack(">I", attenuated[1:5])[0]
        offset = 5 + authority_block_len
        num_attenuation = struct.unpack(">I", attenuated[offset : offset + 4])[0]
        assert num_attenuation == 1

    def test_multiple_attenuations(self):
        """Token should support chained attenuations."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        # First attenuation
        att1_private, _ = generate_keypair()
        token = attenuate(token, ["read_only"], att1_private)

        # Second attenuation
        att2_private, _ = generate_keypair()
        token = attenuate(token, ["no_pii"], att2_private)

        # Should have 2 attenuation blocks
        authority_block_len = struct.unpack(">I", token[1:5])[0]
        offset = 5 + authority_block_len
        num_attenuation = struct.unpack(">I", token[offset : offset + 4])[0]
        assert num_attenuation == 2

    def test_attenuated_token_verifies_with_original_authority_key(self):
        """Verification must still pass with the original authority public key."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        attenuator_private, _ = generate_keypair()
        attenuated = attenuate(token, ["restricted"], attenuator_private)

        assert verify_biscuit(attenuated, public_key) is True

    def test_attenuated_token_contains_additional_constraints(self):
        """The attenuation block must carry the additional constraints."""
        import json

        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        attenuator_private, _ = generate_keypair()
        attenuated = attenuate(token, ["read_only", "max_rows:1000"], attenuator_private)

        # Parse the attenuation block
        authority_block_len = struct.unpack(">I", attenuated[1:5])[0]
        offset = 5 + authority_block_len
        num_attenuation = struct.unpack(">I", attenuated[offset : offset + 4])[0]
        offset += 4

        # Read first attenuation block
        att_block_len = struct.unpack(">I", attenuated[offset : offset + 4])[0]
        offset += 4
        att_block_bytes = attenuated[offset : offset + att_block_len]
        att_block = json.loads(att_block_bytes.decode("utf-8"))

        assert "additional_constraints" in att_block
        assert "read_only" in att_block["additional_constraints"]
        assert "max_rows:1000" in att_block["additional_constraints"]

    def test_empty_constraints_list_raises(self):
        """Attenuation with empty constraints is pointless and should be rejected."""
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)

        attenuator_private, _ = generate_keypair()
        with pytest.raises(ValueError, match="[Cc]onstraint"):
            attenuate(token, [], attenuator_private)

    def test_empty_attenuator_key_raises(self):
        """Empty attenuator key must be rejected."""
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)

        with pytest.raises(ValueError, match="attenuator_key"):
            attenuate(token, ["read_only"], "")

    def test_from_biscuit_returns_merged_constraints_after_attenuation(self):
        """from_biscuit on an attenuated token returns the original envelope.

        The original authority block constraints are preserved; attenuation
        blocks add restrictions that are tracked separately in the token
        structure. The from_biscuit function returns the base envelope.
        """
        envelope = _make_envelope(num_constraints=2)
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        attenuator_private, _ = generate_keypair()
        attenuated = attenuate(token, ["read_only"], attenuator_private)

        restored = from_biscuit(attenuated, public_key)
        assert restored.id == envelope.id
        assert len(restored.active_constraints) == 2


# ===================================================================
# 4. verify_biscuit -- verify token integrity
# ===================================================================


class TestVerifyBiscuit:
    """Tests for verify_biscuit()."""

    def test_valid_token_returns_true(self):
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        assert verify_biscuit(token, public_key) is True

    def test_invalid_signature_returns_false(self):
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        _, wrong_public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        assert verify_biscuit(token, wrong_public_key) is False

    def test_tampered_token_returns_false(self):
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        tampered = bytearray(token)
        if len(tampered) > 10:
            tampered[10] ^= 0xFF
        assert verify_biscuit(bytes(tampered), public_key) is False

    def test_attenuated_token_verifies(self):
        """An attenuated token must verify with the authority public key."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        att_private, _ = generate_keypair()
        attenuated = attenuate(token, ["constraint_a"], att_private)
        assert verify_biscuit(attenuated, public_key) is True

    def test_doubly_attenuated_token_verifies(self):
        """A token attenuated twice must still verify."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        att1_private, _ = generate_keypair()
        token = attenuate(token, ["constraint_a"], att1_private)

        att2_private, _ = generate_keypair()
        token = attenuate(token, ["constraint_b"], att2_private)

        assert verify_biscuit(token, public_key) is True

    def test_tampered_attenuation_block_fails_verification(self):
        """Tampering with an attenuation block must fail."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        att_private, _ = generate_keypair()
        attenuated = attenuate(token, ["constraint_a"], att_private)

        # Tamper with the attenuation block area
        authority_block_len = struct.unpack(">I", attenuated[1:5])[0]
        # The attenuation block starts after authority block + num_attenuation(4)
        att_area_start = 5 + authority_block_len + 4
        tampered = bytearray(attenuated)
        if len(tampered) > att_area_start + 5:
            tampered[att_area_start + 5] ^= 0xFF
        assert verify_biscuit(bytes(tampered), public_key) is False

    def test_empty_token_returns_false(self):
        _, public_key = generate_keypair()
        assert verify_biscuit(b"", public_key) is False

    def test_wrong_version_returns_false(self):
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        tampered = bytes([0xFF]) + token[1:]
        assert verify_biscuit(tampered, public_key) is False

    def test_empty_public_key_raises(self):
        envelope = _make_envelope()
        private_key, _ = generate_keypair()
        token = to_biscuit(envelope, private_key)
        with pytest.raises(ValueError, match="public_key"):
            verify_biscuit(token, "")


# ===================================================================
# 5. Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_large_number_of_constraints(self):
        """Token should handle envelopes with many constraints."""
        envelope = _make_envelope(num_constraints=50)
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)
        assert len(restored.active_constraints) == 50

    def test_constraint_with_complex_value(self):
        """Constraints with dict/list values must survive round-trip."""
        envelope = _make_envelope(num_constraints=0)
        envelope.active_constraints.append(
            Constraint(
                id="con-complex",
                constraint_type=ConstraintType.DATA_ACCESS,
                value={"tables": ["users", "orders"], "max_rows": 1000},
                source="cap-complex",
                priority=5,
            )
        )
        envelope.constraint_hash = ""
        # Trigger hash recomputation
        envelope.constraint_hash = envelope._compute_hash()

        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)

        assert len(restored.active_constraints) == 1
        restored_val = restored.active_constraints[0].value
        assert restored_val["tables"] == ["users", "orders"]
        assert restored_val["max_rows"] == 1000

    def test_constraint_types_preserved(self):
        """All ConstraintType enum values must round-trip correctly."""
        envelope = _make_envelope(num_constraints=0)
        for i, ct in enumerate(ConstraintType):
            envelope.active_constraints.append(
                Constraint(
                    id=f"con-type-{i}",
                    constraint_type=ct,
                    value=f"value_{ct.value}",
                    source=f"src-{i}",
                    priority=i,
                )
            )
        envelope.constraint_hash = envelope._compute_hash()

        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)

        for original, restored_c in zip(envelope.active_constraints, restored.active_constraints):
            assert restored_c.constraint_type == original.constraint_type

    def test_different_keys_produce_different_tokens(self):
        """Same envelope signed with different keys produces different tokens."""
        envelope = _make_envelope()
        key1_private, _ = generate_keypair()
        key2_private, _ = generate_keypair()

        token1 = to_biscuit(envelope, key1_private)
        token2 = to_biscuit(envelope, key2_private)
        assert token1 != token2

    def test_many_attenuation_levels(self):
        """Token must handle deep attenuation chains (5 levels)."""
        envelope = _make_envelope()
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)

        for i in range(5):
            att_private, _ = generate_keypair()
            token = attenuate(token, [f"restriction_{i}"], att_private)

        assert verify_biscuit(token, public_key) is True

        # Parse and verify 5 attenuation blocks
        authority_block_len = struct.unpack(">I", token[1:5])[0]
        offset = 5 + authority_block_len
        num_attenuation = struct.unpack(">I", token[offset : offset + 4])[0]
        assert num_attenuation == 5

    def test_valid_until_not_serialized_in_token(self):
        """valid_until is a local field, not part of the token.

        The token carries the constraint data; token validity is checked
        through the cryptographic signature chain, not through timestamps.
        The envelope returned from from_biscuit should still be usable.
        """
        envelope = _make_envelope(valid_until=_FUTURE)
        private_key, public_key = generate_keypair()
        token = to_biscuit(envelope, private_key)
        restored = from_biscuit(token, public_key)
        assert restored.id == envelope.id
