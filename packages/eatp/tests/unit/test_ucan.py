"""
Unit tests for EATP UCAN interop module.

Tests export/import of DelegationRecords as UCAN v0.10.0 tokens.
Covers:
- UCAN header structure (alg, typ, ucv)
- UCAN payload claims (iss, aud, att, exp, nnc, prf, fct)
- Capability attenuation mapping from EATP constraints
- Ed25519 signing and verification
- Round-trip fidelity (to_ucan -> from_ucan)
- Error handling for invalid inputs, tampered tokens, expired tokens
"""

import base64
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

import pytest

from eatp.chain import (
    CapabilityAttestation,
    CapabilityType,
    DelegationRecord,
)
from eatp.crypto import (
    generate_keypair,
    hash_reasoning_trace,
    sign,
    sign_reasoning_trace,
)
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)
_FUTURE = _NOW + timedelta(hours=24)
_PAST = _NOW - timedelta(hours=24)


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 key pair for tests."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


@pytest.fixture
def delegation(keypair):
    """Create a signed DelegationRecord for testing."""
    private_key, _ = keypair
    now = datetime.now(timezone.utc)
    payload = {
        "id": "del-001",
        "delegator_id": "agent-alpha",
        "delegatee_id": "agent-beta",
        "task_id": "task-001",
        "capabilities_delegated": ["analyze_data", "read_files"],
        "constraint_subset": ["read_only", "no_pii"],
        "delegated_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "parent_delegation_id": None,
    }
    signature = sign(payload, private_key)
    return DelegationRecord(
        id="del-001",
        delegator_id="agent-alpha",
        delegatee_id="agent-beta",
        task_id="task-001",
        capabilities_delegated=["analyze_data", "read_files"],
        constraint_subset=["read_only", "no_pii"],
        delegated_at=now,
        expires_at=now + timedelta(hours=24),
        signature=signature,
        parent_delegation_id=None,
        delegation_chain=["agent-alpha", "agent-beta"],
        delegation_depth=1,
    )


@pytest.fixture
def delegation_no_expiry(keypair):
    """Create a DelegationRecord without expiration."""
    private_key, _ = keypair
    now = datetime.now(timezone.utc)
    payload = {
        "id": "del-noexp",
        "delegator_id": "agent-alpha",
        "delegatee_id": "agent-beta",
        "task_id": "task-noexp",
        "capabilities_delegated": ["read_files"],
        "constraint_subset": [],
        "delegated_at": now.isoformat(),
        "expires_at": None,
        "parent_delegation_id": None,
    }
    signature = sign(payload, private_key)
    return DelegationRecord(
        id="del-noexp",
        delegator_id="agent-alpha",
        delegatee_id="agent-beta",
        task_id="task-noexp",
        capabilities_delegated=["read_files"],
        constraint_subset=[],
        delegated_at=now,
        expires_at=None,
        signature=signature,
        parent_delegation_id=None,
    )


@pytest.fixture
def expired_delegation(keypair):
    """Create an expired DelegationRecord."""
    private_key, _ = keypair
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=24)
    payload = {
        "id": "del-expired",
        "delegator_id": "agent-alpha",
        "delegatee_id": "agent-beta",
        "task_id": "task-expired",
        "capabilities_delegated": ["read_files"],
        "constraint_subset": [],
        "delegated_at": (past - timedelta(hours=24)).isoformat(),
        "expires_at": past.isoformat(),
        "parent_delegation_id": None,
    }
    signature = sign(payload, private_key)
    return DelegationRecord(
        id="del-expired",
        delegator_id="agent-alpha",
        delegatee_id="agent-beta",
        task_id="task-expired",
        capabilities_delegated=["read_files"],
        constraint_subset=[],
        delegated_at=past - timedelta(hours=24),
        expires_at=past,
        signature=signature,
        parent_delegation_id=None,
    )


# ---------------------------------------------------------------------------
# Import module under test
# ---------------------------------------------------------------------------

from eatp.interop.ucan import (
    UCAN_VERSION,
    from_ucan,
    to_ucan,
)


# ===========================================================================
# 1. UCAN Token Structure
# ===========================================================================


class TestUCANTokenStructure:
    """Verify UCAN v0.10.0 structural requirements."""

    def test_returns_string_token(self, delegation, keypair):
        """to_ucan returns a non-empty string."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_has_three_parts(self, delegation, keypair):
        """UCAN tokens are base64url(header).base64url(payload).base64url(signature)."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        parts = token.split(".")
        assert len(parts) == 3, f"Expected 3 UCAN segments, got {len(parts)}"

    def test_parts_are_base64url_encoded(self, delegation, keypair):
        """Each segment must be valid base64url (no padding required)."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        parts = token.split(".")
        for i, part in enumerate(parts):
            # base64url uses - and _ instead of + and /
            # Add padding for decoding
            padded = part + "=" * (4 - len(part) % 4)
            decoded = base64.urlsafe_b64decode(padded)
            assert len(decoded) > 0, f"Segment {i} decoded to empty bytes"


# ===========================================================================
# 2. UCAN Header
# ===========================================================================


class TestUCANHeader:
    """Verify UCAN header fields per v0.10.0 spec."""

    def _decode_header(self, token: str) -> dict:
        header_b64 = token.split(".")[0]
        padded = header_b64 + "=" * (4 - len(header_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))

    def test_header_alg_is_eddsa(self, delegation, keypair):
        """Header alg MUST be 'EdDSA' for Ed25519."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        header = self._decode_header(token)
        assert header["alg"] == "EdDSA"

    def test_header_typ_is_jwt(self, delegation, keypair):
        """Header typ MUST be 'JWT' (UCAN tokens are JWTs)."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        header = self._decode_header(token)
        assert header["typ"] == "JWT"

    def test_header_ucv_is_0_10_0(self, delegation, keypair):
        """Header ucv MUST be '0.10.0' for UCAN version."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        header = self._decode_header(token)
        assert header["ucv"] == "0.10.0"

    def test_header_has_no_extra_fields(self, delegation, keypair):
        """Header should only contain alg, typ, ucv."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        header = self._decode_header(token)
        assert set(header.keys()) == {"alg", "typ", "ucv"}


# ===========================================================================
# 3. UCAN Payload Claims
# ===========================================================================


class TestUCANPayload:
    """Verify UCAN payload claims per v0.10.0 spec."""

    def _decode_payload(self, token: str) -> dict:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))

    def test_iss_is_delegator_did(self, delegation, keypair):
        """iss MUST be the DID of the delegator."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)
        assert payload["iss"] == "did:eatp:agent-alpha"

    def test_iss_uses_custom_delegator_did_when_provided(self, delegation, keypair):
        """iss MUST use the provided delegator_did when given."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key, delegator_did="did:key:z6MkSomeKey")
        payload = self._decode_payload(token)
        assert payload["iss"] == "did:key:z6MkSomeKey"

    def test_aud_is_delegatee_did(self, delegation, keypair):
        """aud MUST be the DID of the delegatee."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)
        assert payload["aud"] == "did:eatp:agent-beta"

    def test_aud_uses_custom_delegatee_did_when_provided(self, delegation, keypair):
        """aud MUST use the provided delegatee_did when given."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key, delegatee_did="did:key:z6MkOtherKey")
        payload = self._decode_payload(token)
        assert payload["aud"] == "did:key:z6MkOtherKey"

    def test_att_contains_capabilities(self, delegation, keypair):
        """att MUST contain UCAN attenuations for delegated capabilities."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)

        assert "att" in payload
        att = payload["att"]
        assert isinstance(att, list)
        assert len(att) == 2  # analyze_data and read_files

    def test_att_each_entry_has_with_and_can(self, delegation, keypair):
        """Each attenuation MUST have 'with' (resource) and 'can' (ability) fields."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)

        for attenuation in payload["att"]:
            assert "with" in attenuation, "Attenuation missing 'with' field"
            assert "can" in attenuation, "Attenuation missing 'can' field"

    def test_att_capabilities_mapped_correctly(self, delegation, keypair):
        """Capabilities should map to UCAN attenuation 'can' values."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)

        can_values = sorted([a["can"] for a in payload["att"]])
        assert can_values == ["eatp/analyze_data", "eatp/read_files"]

    def test_att_resource_is_task_id(self, delegation, keypair):
        """Attenuation 'with' should reference the EATP task."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)

        for attenuation in payload["att"]:
            assert attenuation["with"] == "eatp:task:task-001"

    def test_exp_present_when_delegation_has_expiry(self, delegation, keypair):
        """exp claim MUST be present when delegation has expires_at."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)

        assert "exp" in payload
        assert isinstance(payload["exp"], int)

    def test_exp_absent_when_no_expiry(self, delegation_no_expiry, keypair):
        """exp claim MUST be absent when delegation has no expiry."""
        private_key, _ = keypair
        token = to_ucan(delegation_no_expiry, private_key)
        payload = self._decode_payload(token)

        assert "exp" not in payload

    def test_nnc_is_unique_nonce(self, delegation, keypair):
        """nnc (nonce) MUST be present and unique per token."""
        private_key, _ = keypair
        token1 = to_ucan(delegation, private_key)
        token2 = to_ucan(delegation, private_key)
        payload1 = self._decode_payload(token1)
        payload2 = self._decode_payload(token2)

        assert "nnc" in payload1
        assert "nnc" in payload2
        assert isinstance(payload1["nnc"], str)
        assert len(payload1["nnc"]) > 0
        assert payload1["nnc"] != payload2["nnc"], "Each UCAN must have a unique nonce"

    def test_prf_is_empty_list_for_root_ucan(self, delegation, keypair):
        """prf (proof) MUST be an empty list for root UCANs (no parent proof)."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)

        assert "prf" in payload
        assert payload["prf"] == []

    def test_fct_contains_eatp_metadata(self, delegation, keypair):
        """fct (facts) MUST contain EATP-specific metadata."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)

        assert "fct" in payload
        fct = payload["fct"]
        assert isinstance(fct, dict)
        assert fct["eatp_delegation_id"] == "del-001"
        assert fct["eatp_delegator_id"] == "agent-alpha"
        assert fct["eatp_delegatee_id"] == "agent-beta"
        assert fct["eatp_task_id"] == "task-001"

    def test_fct_contains_constraint_subset(self, delegation, keypair):
        """fct MUST include the EATP constraint subset for attenuation tracking."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)

        fct = payload["fct"]
        assert "eatp_constraints" in fct
        assert sorted(fct["eatp_constraints"]) == ["no_pii", "read_only"]

    def test_fct_contains_delegation_chain(self, delegation, keypair):
        """fct MUST include delegation chain info when present."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        payload = self._decode_payload(token)

        fct = payload["fct"]
        assert fct["eatp_delegation_chain"] == ["agent-alpha", "agent-beta"]
        assert fct["eatp_delegation_depth"] == 1


# ===========================================================================
# 4. Ed25519 Signature
# ===========================================================================


class TestUCANSignature:
    """Verify Ed25519 signature on UCAN tokens."""

    def test_signature_is_64_bytes(self, delegation, keypair):
        """Ed25519 signature MUST be 64 bytes."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)

        sig_b64 = token.split(".")[2]
        padded = sig_b64 + "=" * (4 - len(sig_b64) % 4)
        sig_bytes = base64.urlsafe_b64decode(padded)
        assert len(sig_bytes) == 64, f"Expected 64-byte Ed25519 signature, got {len(sig_bytes)}"

    def test_signature_verifies_with_correct_key(self, delegation, keypair):
        """from_ucan with matching public key should succeed."""
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)
        result = from_ucan(token, public_key)
        assert isinstance(result, DelegationRecord)

    def test_signature_fails_with_wrong_key(self, delegation, keypair):
        """from_ucan with wrong public key MUST raise an error."""
        private_key, _ = keypair
        _, wrong_public_key = generate_keypair()
        token = to_ucan(delegation, private_key)

        with pytest.raises(ValueError, match="[Ss]ignature"):
            from_ucan(token, wrong_public_key)


# ===========================================================================
# 5. Round-Trip Fidelity
# ===========================================================================


class TestRoundTrip:
    """Tests that to_ucan -> from_ucan preserves delegation data."""

    def test_preserves_delegation_id(self, delegation, keypair):
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)
        restored = from_ucan(token, public_key)
        assert restored.id == delegation.id

    def test_preserves_delegator_id(self, delegation, keypair):
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)
        restored = from_ucan(token, public_key)
        assert restored.delegator_id == delegation.delegator_id

    def test_preserves_delegatee_id(self, delegation, keypair):
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)
        restored = from_ucan(token, public_key)
        assert restored.delegatee_id == delegation.delegatee_id

    def test_preserves_task_id(self, delegation, keypair):
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)
        restored = from_ucan(token, public_key)
        assert restored.task_id == delegation.task_id

    def test_preserves_capabilities_delegated(self, delegation, keypair):
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)
        restored = from_ucan(token, public_key)
        assert sorted(restored.capabilities_delegated) == sorted(delegation.capabilities_delegated)

    def test_preserves_constraint_subset(self, delegation, keypair):
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)
        restored = from_ucan(token, public_key)
        assert sorted(restored.constraint_subset) == sorted(delegation.constraint_subset)

    def test_preserves_delegation_chain(self, delegation, keypair):
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)
        restored = from_ucan(token, public_key)
        assert restored.delegation_chain == delegation.delegation_chain

    def test_preserves_delegation_depth(self, delegation, keypair):
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)
        restored = from_ucan(token, public_key)
        assert restored.delegation_depth == delegation.delegation_depth

    def test_preserves_parent_delegation_id(self, keypair):
        """Round-trip with a non-None parent_delegation_id."""
        private_key, public_key = keypair
        now = datetime.now(timezone.utc)
        deleg = DelegationRecord(
            id="del-child",
            delegator_id="agent-beta",
            delegatee_id="agent-gamma",
            task_id="task-child",
            capabilities_delegated=["read_files"],
            constraint_subset=["audit_required"],
            delegated_at=now,
            expires_at=now + timedelta(hours=1),
            signature=sign({"id": "del-child"}, private_key),
            parent_delegation_id="del-parent",
            delegation_chain=["agent-alpha", "agent-beta", "agent-gamma"],
            delegation_depth=2,
        )

        token = to_ucan(deleg, private_key)
        restored = from_ucan(token, public_key)
        assert restored.parent_delegation_id == "del-parent"

    def test_round_trip_no_expiry(self, delegation_no_expiry, keypair):
        """Round-trip for delegation with no expiration."""
        private_key, public_key = keypair
        token = to_ucan(delegation_no_expiry, private_key)
        restored = from_ucan(token, public_key)
        assert restored.id == delegation_no_expiry.id
        assert restored.expires_at is None

    def test_round_trip_empty_constraints(self, keypair):
        """Round-trip for delegation with empty constraint subset."""
        private_key, public_key = keypair
        now = datetime.now(timezone.utc)
        deleg = DelegationRecord(
            id="del-empty-con",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-empty",
            capabilities_delegated=["read_files"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-empty-con"}, private_key),
        )
        token = to_ucan(deleg, private_key)
        restored = from_ucan(token, public_key)
        assert restored.constraint_subset == []


# ===========================================================================
# 6. Error Handling
# ===========================================================================


class TestErrorHandling:
    """Tests for error conditions and invalid inputs."""

    def test_to_ucan_empty_signing_key_raises(self, delegation):
        """to_ucan MUST raise ValueError on empty signing key."""
        with pytest.raises(ValueError, match="signing_key"):
            to_ucan(delegation, "")

    def test_to_ucan_invalid_signing_key_raises(self, delegation):
        """to_ucan MUST raise ValueError on invalid (non-base64) signing key."""
        with pytest.raises(ValueError, match="signing_key"):
            to_ucan(delegation, "not-a-valid-key!!!")

    def test_from_ucan_empty_public_key_raises(self, delegation, keypair):
        """from_ucan MUST raise ValueError on empty public key."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        with pytest.raises(ValueError, match="public_key"):
            from_ucan(token, "")

    def test_from_ucan_invalid_public_key_raises(self, delegation, keypair):
        """from_ucan MUST raise ValueError on invalid public key."""
        private_key, _ = keypair
        token = to_ucan(delegation, private_key)
        with pytest.raises(ValueError, match="public_key"):
            from_ucan(token, "not-a-valid-key!!!")

    def test_from_ucan_malformed_token_raises(self, keypair):
        """from_ucan MUST raise ValueError on malformed token."""
        _, public_key = keypair
        with pytest.raises(ValueError, match="[Tt]oken"):
            from_ucan("not.a.valid-token", public_key)

    def test_from_ucan_token_with_wrong_segment_count_raises(self, keypair):
        """from_ucan MUST raise ValueError when token does not have exactly 3 segments."""
        _, public_key = keypair
        with pytest.raises(ValueError, match="[Tt]oken"):
            from_ucan("only-two.parts", public_key)

    def test_from_ucan_tampered_payload_raises(self, delegation, keypair):
        """Modifying the token payload MUST cause signature verification failure."""
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)

        parts = token.split(".")
        payload_chars = list(parts[1])
        if payload_chars:
            payload_chars[0] = "A" if payload_chars[0] != "A" else "B"
        parts[1] = "".join(payload_chars)
        tampered = ".".join(parts)

        with pytest.raises(ValueError, match="[Ss]ignature"):
            from_ucan(tampered, public_key)

    def test_from_ucan_tampered_header_raises(self, delegation, keypair):
        """Modifying the header MUST cause signature verification failure."""
        private_key, public_key = keypair
        token = to_ucan(delegation, private_key)

        parts = token.split(".")
        header_chars = list(parts[0])
        if header_chars:
            header_chars[0] = "X" if header_chars[0] != "X" else "Y"
        parts[0] = "".join(header_chars)
        tampered = ".".join(parts)

        with pytest.raises(ValueError, match="[Ss]ignature|[Hh]eader|[Ii]nvalid"):
            from_ucan(tampered, public_key)

    def test_from_ucan_expired_token_raises(self, expired_delegation, keypair):
        """from_ucan MUST raise ValueError for expired tokens."""
        private_key, public_key = keypair
        token = to_ucan(expired_delegation, private_key)
        with pytest.raises(ValueError, match="[Ee]xpir"):
            from_ucan(token, public_key)

    def test_from_ucan_wrong_ucv_raises(self, keypair):
        """from_ucan MUST raise ValueError when ucv is not 0.10.0."""
        private_key, public_key = keypair

        # Build a token with wrong ucv manually
        header = {"alg": "EdDSA", "typ": "JWT", "ucv": "0.9.0"}
        payload = {
            "iss": "did:eatp:agent-alpha",
            "aud": "did:eatp:agent-beta",
            "att": [],
            "nnc": secrets.token_hex(16),
            "prf": [],
            "fct": {
                "eatp_delegation_id": "del-test",
                "eatp_delegator_id": "agent-alpha",
                "eatp_delegatee_id": "agent-beta",
                "eatp_task_id": "task-test",
                "eatp_constraints": [],
                "eatp_delegation_chain": [],
                "eatp_delegation_depth": 0,
                "eatp_delegated_at": datetime.now(timezone.utc).isoformat(),
                "eatp_parent_delegation_id": None,
                "eatp_original_signature": "sig",
            },
        }

        # Manually encode with wrong version (we need to import helper to sign)
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
            .rstrip(b"=")
            .decode()
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
            .rstrip(b"=")
            .decode()
        )
        signing_input = f"{header_b64}.{payload_b64}"

        from nacl.signing import SigningKey

        sk_bytes = base64.b64decode(private_key)
        sk = SigningKey(sk_bytes)
        sig = sk.sign(signing_input.encode()).signature
        sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

        token = f"{header_b64}.{payload_b64}.{sig_b64}"

        with pytest.raises(ValueError, match="ucv|version"):
            from_ucan(token, public_key)


# ===========================================================================
# 7. Module-Level Constants
# ===========================================================================


class TestModuleConstants:
    """Verify module-level constants are set correctly."""

    def test_ucan_version_is_0_10_0(self):
        assert UCAN_VERSION == "0.10.0"


# ===========================================================================
# 8. Edge Cases
# ===========================================================================


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_single_capability_delegation(self, keypair):
        """Delegation with a single capability should produce one attenuation."""
        private_key, public_key = keypair
        now = datetime.now(timezone.utc)
        deleg = DelegationRecord(
            id="del-single",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-single",
            capabilities_delegated=["only_one"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-single"}, private_key),
        )
        token = to_ucan(deleg, private_key)
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        assert len(payload["att"]) == 1
        assert payload["att"][0]["can"] == "eatp/only_one"

    def test_many_capabilities_delegation(self, keypair):
        """Delegation with many capabilities should produce matching attenuations."""
        private_key, public_key = keypair
        now = datetime.now(timezone.utc)
        caps = [f"cap_{i}" for i in range(10)]
        deleg = DelegationRecord(
            id="del-many",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-many",
            capabilities_delegated=caps,
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-many"}, private_key),
        )
        token = to_ucan(deleg, private_key)
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        assert len(payload["att"]) == 10

    def test_custom_dids_roundtrip(self, delegation, keypair):
        """Round-trip with custom DIDs should work (DIDs are in iss/aud)."""
        private_key, public_key = keypair
        token = to_ucan(
            delegation,
            private_key,
            delegator_did="did:key:z6MkCustom1",
            delegatee_did="did:key:z6MkCustom2",
        )
        restored = from_ucan(token, public_key)
        # The restored delegation should preserve the original IDs from fct
        assert restored.delegator_id == delegation.delegator_id
        assert restored.delegatee_id == delegation.delegatee_id

    def test_delegation_with_parent(self, keypair):
        """UCAN for delegation with parent_delegation_id should include it in fct."""
        private_key, public_key = keypair
        now = datetime.now(timezone.utc)
        deleg = DelegationRecord(
            id="del-child-2",
            delegator_id="agent-beta",
            delegatee_id="agent-gamma",
            task_id="task-chain",
            capabilities_delegated=["read_files"],
            constraint_subset=["no_pii"],
            delegated_at=now,
            signature=sign({"id": "del-child-2"}, private_key),
            parent_delegation_id="del-parent-1",
        )
        token = to_ucan(deleg, private_key)
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        assert payload["fct"]["eatp_parent_delegation_id"] == "del-parent-1"

    def test_att_constraint_tightening_in_fct(self, keypair):
        """Constraints (attenuation/tightening) should be tracked in fct."""
        private_key, public_key = keypair
        now = datetime.now(timezone.utc)
        deleg = DelegationRecord(
            id="del-tight",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-tight",
            capabilities_delegated=["analyze_data"],
            constraint_subset=["read_only", "no_pii", "max_100_rows"],
            delegated_at=now,
            signature=sign({"id": "del-tight"}, private_key),
        )
        token = to_ucan(deleg, private_key)
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        assert sorted(payload["fct"]["eatp_constraints"]) == [
            "max_100_rows",
            "no_pii",
            "read_only",
        ]


# ===========================================================================
# 9. Reasoning Trace Confidentiality Filtering
# ===========================================================================


class TestUCANReasoningConfidentiality:
    """Verify confidentiality-filtered reasoning traces in UCAN facts.

    The _build_facts() function includes the full reasoning trace in UCAN fct
    only when its confidentiality level is PUBLIC or RESTRICTED. For higher
    levels (CONFIDENTIAL, SECRET, TOP_SECRET) the trace content is stripped,
    but the hash and signature are always included when present.
    """

    def _decode_payload(self, token: str) -> dict:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))

    def _make_delegation_with_reasoning(
        self,
        keypair,
        confidentiality: ConfidentialityLevel,
    ) -> DelegationRecord:
        """Build a DelegationRecord with a reasoning trace at the given level."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)

        trace = ReasoningTrace(
            decision="Grant read access to dataset",
            rationale="Agent has valid credentials and task requires data analysis",
            confidentiality=confidentiality,
            timestamp=now,
            alternatives_considered=["deny access", "grant partial access"],
            evidence=[{"type": "credential_check", "result": "valid"}],
            methodology="capability_matching",
            confidence=0.95,
        )

        trace_hash = hash_reasoning_trace(trace)
        trace_signature = sign_reasoning_trace(trace, private_key)

        payload = {
            "id": f"del-reason-{confidentiality.value}",
            "delegator_id": "agent-alpha",
            "delegatee_id": "agent-beta",
            "task_id": "task-reason",
            "capabilities_delegated": ["read_files"],
            "constraint_subset": [],
            "delegated_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=24)).isoformat(),
            "parent_delegation_id": None,
        }
        signature = sign(payload, private_key)

        return DelegationRecord(
            id=f"del-reason-{confidentiality.value}",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-reason",
            capabilities_delegated=["read_files"],
            constraint_subset=[],
            delegated_at=now,
            expires_at=now + timedelta(hours=24),
            signature=signature,
            parent_delegation_id=None,
            reasoning_trace=trace,
            reasoning_trace_hash=trace_hash,
            reasoning_signature=trace_signature,
        )

    def test_ucan_export_includes_public_reasoning_trace(self, keypair):
        """PUBLIC reasoning traces MUST appear in UCAN facts."""
        private_key, _ = keypair
        deleg = self._make_delegation_with_reasoning(keypair, ConfidentialityLevel.PUBLIC)
        token = to_ucan(deleg, private_key)
        fct = self._decode_payload(token)["fct"]

        assert "eatp_reasoning_trace" in fct, "PUBLIC reasoning trace must be included in UCAN facts"
        assert fct["eatp_reasoning_trace"]["decision"] == "Grant read access to dataset"
        assert fct["eatp_reasoning_trace"]["confidentiality"] == "public"
        # Hash and signature must also be present
        assert "eatp_reasoning_trace_hash" in fct
        assert "eatp_reasoning_signature" in fct

    def test_ucan_export_includes_restricted_reasoning_trace(self, keypair):
        """RESTRICTED reasoning traces MUST appear in UCAN facts (boundary case)."""
        private_key, _ = keypair
        deleg = self._make_delegation_with_reasoning(keypair, ConfidentialityLevel.RESTRICTED)
        token = to_ucan(deleg, private_key)
        fct = self._decode_payload(token)["fct"]

        assert "eatp_reasoning_trace" in fct, "RESTRICTED reasoning trace must be included in UCAN facts"
        assert fct["eatp_reasoning_trace"]["confidentiality"] == "restricted"
        assert fct["eatp_reasoning_trace"]["rationale"] == (
            "Agent has valid credentials and task requires data analysis"
        )
        # Hash and signature must also be present
        assert "eatp_reasoning_trace_hash" in fct
        assert "eatp_reasoning_signature" in fct

    def test_ucan_export_strips_confidential_reasoning_trace(self, keypair):
        """CONFIDENTIAL reasoning traces MUST NOT appear in UCAN facts.

        The hash and signature MUST still be present so that a recipient
        who later obtains the trace out-of-band can verify its integrity.
        """
        private_key, _ = keypair
        deleg = self._make_delegation_with_reasoning(keypair, ConfidentialityLevel.CONFIDENTIAL)
        token = to_ucan(deleg, private_key)
        fct = self._decode_payload(token)["fct"]

        assert "eatp_reasoning_trace" not in fct, "CONFIDENTIAL reasoning trace must be stripped from UCAN facts"
        # Hash and signature MUST survive even when trace is stripped
        assert "eatp_reasoning_trace_hash" in fct, "reasoning trace hash must be present even when trace is stripped"
        assert "eatp_reasoning_signature" in fct, "reasoning signature must be present even when trace is stripped"
        assert len(fct["eatp_reasoning_trace_hash"]) == 64  # SHA-256 hex

    def test_ucan_export_strips_secret_reasoning_trace(self, keypair):
        """SECRET reasoning traces MUST NOT appear in UCAN facts."""
        private_key, _ = keypair
        deleg = self._make_delegation_with_reasoning(keypair, ConfidentialityLevel.SECRET)
        token = to_ucan(deleg, private_key)
        fct = self._decode_payload(token)["fct"]

        assert "eatp_reasoning_trace" not in fct, "SECRET reasoning trace must be stripped from UCAN facts"
        # Hash and signature MUST survive
        assert "eatp_reasoning_trace_hash" in fct
        assert "eatp_reasoning_signature" in fct

    def test_ucan_roundtrip_preserves_public_reasoning(self, keypair):
        """Export with PUBLIC reasoning, import back -- trace must survive."""
        private_key, public_key = keypair
        deleg = self._make_delegation_with_reasoning(keypair, ConfidentialityLevel.PUBLIC)
        token = to_ucan(deleg, private_key)
        restored = from_ucan(token, public_key)

        assert restored.reasoning_trace is not None, "PUBLIC reasoning trace must survive UCAN round-trip"
        assert restored.reasoning_trace.decision == deleg.reasoning_trace.decision
        assert restored.reasoning_trace.rationale == deleg.reasoning_trace.rationale
        assert restored.reasoning_trace.confidentiality == ConfidentialityLevel.PUBLIC
        assert restored.reasoning_trace.confidence == 0.95
        assert restored.reasoning_trace.methodology == "capability_matching"
        assert restored.reasoning_trace.alternatives_considered == [
            "deny access",
            "grant partial access",
        ]
        # Hash and signature must also round-trip
        assert restored.reasoning_trace_hash == deleg.reasoning_trace_hash
        assert restored.reasoning_signature == deleg.reasoning_signature

    def test_ucan_roundtrip_confidential_trace_is_none(self, keypair):
        """Export with CONFIDENTIAL reasoning, import back.

        The reasoning_trace must be None (stripped during export), but the
        reasoning_trace_hash must survive for out-of-band verification.
        """
        private_key, public_key = keypair
        deleg = self._make_delegation_with_reasoning(keypair, ConfidentialityLevel.CONFIDENTIAL)
        token = to_ucan(deleg, private_key)
        restored = from_ucan(token, public_key)

        assert restored.reasoning_trace is None, (
            "CONFIDENTIAL reasoning trace must be None after UCAN round-trip because it was stripped during export"
        )
        assert restored.reasoning_trace_hash is not None, (
            "reasoning_trace_hash must survive round-trip even when trace is stripped"
        )
        assert restored.reasoning_trace_hash == deleg.reasoning_trace_hash
        assert restored.reasoning_signature is not None, (
            "reasoning_signature must survive round-trip even when trace is stripped"
        )
        assert restored.reasoning_signature == deleg.reasoning_signature
