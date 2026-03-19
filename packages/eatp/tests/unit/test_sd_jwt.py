"""
Unit tests for EATP SD-JWT selective disclosure module.

Tests the IETF SD-JWT spec implementation for EATP records:
- create_sd_jwt: create SD-JWTs with selectively disclosable claims
- verify_sd_jwt: verify signature and reconstruct disclosed claims
- export_chain_as_sd_jwt: convenience for TrustLineageChain
- export_capability_as_sd_jwt: convenience for CapabilityAttestation

Uses Ed25519 key pairs from eatp.crypto for all signing/verification.
"""

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from eatp.chain import (
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from eatp.crypto import generate_keypair

# ---------------------------------------------------------------------------
# Helpers: reusable fixtures
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)
_FUTURE = _NOW + timedelta(hours=24)
_PAST = _NOW - timedelta(hours=24)


def _make_genesis(
    agent_id: str = "agent-001",
    expires_at: datetime | None = None,
) -> GenesisRecord:
    return GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id="org-root",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=_NOW,
        signature="sig-genesis",
        signature_algorithm="Ed25519",
        expires_at=expires_at,
        metadata={"department": "engineering"},
    )


def _make_capability(
    cap_id: str = "cap-001",
    capability: str = "analyze_data",
    expires_at: datetime | None = None,
) -> CapabilityAttestation:
    return CapabilityAttestation(
        id=cap_id,
        capability=capability,
        capability_type=CapabilityType.ACTION,
        constraints=["read_only", "no_pii"],
        attester_id="org-root",
        attested_at=_NOW,
        signature="sig-cap",
        expires_at=expires_at,
        scope={"tables": ["transactions"]},
    )


def _make_delegation(
    deleg_id: str = "del-001",
    expires_at: datetime | None = None,
) -> DelegationRecord:
    return DelegationRecord(
        id=deleg_id,
        delegator_id="agent-001",
        delegatee_id="agent-002",
        task_id="task-abc",
        capabilities_delegated=["analyze_data"],
        constraint_subset=["read_only"],
        delegated_at=_NOW,
        signature="sig-deleg",
        expires_at=expires_at,
        parent_delegation_id=None,
        delegation_chain=["agent-001", "agent-002"],
        delegation_depth=1,
    )


def _make_chain(
    expires_at: datetime | None = None,
    with_capabilities: bool = True,
    with_delegations: bool = True,
) -> TrustLineageChain:
    genesis = _make_genesis(expires_at=expires_at)
    caps = [_make_capability(expires_at=expires_at)] if with_capabilities else []
    delegs = [_make_delegation(expires_at=expires_at)] if with_delegations else []

    return TrustLineageChain(
        genesis=genesis,
        capabilities=caps,
        delegations=delegs,
    )


# ---------------------------------------------------------------------------
# Skip if PyNaCl is not installed (required for Ed25519)
# ---------------------------------------------------------------------------

nacl = pytest.importorskip("nacl", reason="PyNaCl required for SD-JWT tests")

# Import module under test after confirming nacl is available
from eatp.interop.sd_jwt import (
    create_sd_jwt,
    export_capability_as_sd_jwt,
    export_chain_as_sd_jwt,
    verify_sd_jwt,
)

# Generate a real Ed25519 key pair for all tests
_PRIVATE_KEY, _PUBLIC_KEY = generate_keypair()


# ===================================================================
# 1. create_sd_jwt — basic structure
# ===================================================================


class TestCreateSdJwtStructure:
    """Tests for the output structure of create_sd_jwt."""

    def test_returns_string(self):
        token = create_sd_jwt(
            claims={"name": "agent-001", "role": "analyst"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
        )
        assert isinstance(token, str)
        assert len(token) > 0

    def test_combined_format_has_jwt_and_disclosures(self):
        """SD-JWT combined format: JWT~disclosure1~disclosure2~"""
        token = create_sd_jwt(
            claims={"name": "agent-001", "role": "analyst"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
        )
        # The format is JWT~disc1~disc2~...~
        # JWT itself has 3 dot-separated parts
        parts = token.split("~")
        jwt_part = parts[0]
        assert len(jwt_part.split(".")) == 3, "JWT segment must have header.payload.signature"
        # At least one disclosure for "name"
        assert len(parts) >= 2, "Must have at least JWT~disclosure~"
        # Trailing empty string from final ~
        assert parts[-1] == "", "SD-JWT combined format must end with ~"

    def test_jwt_header_has_sd_jwt_type(self):
        """Header should have typ=sd+jwt and alg=EdDSA."""
        token = create_sd_jwt(
            claims={"x": 1},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["x"],
        )
        jwt_part = token.split("~")[0]
        header_b64 = jwt_part.split(".")[0]
        # Add padding for base64url decode
        padded = header_b64 + "=" * (-len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
        assert header["alg"] == "EdDSA"
        assert header["typ"] == "sd+jwt"

    def test_payload_contains_sd_array(self):
        """Payload must have _sd array with hashed hidden claims."""
        token = create_sd_jwt(
            claims={"visible": "yes", "hidden": "secret"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["visible"],
        )
        jwt_part = token.split("~")[0]
        payload_b64 = jwt_part.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        assert "_sd" in payload, "Payload must contain _sd array"
        assert isinstance(payload["_sd"], list)
        assert len(payload["_sd"]) > 0, "_sd must contain at least one hash for 'hidden'"

    def test_payload_contains_sd_alg(self):
        """Payload must declare _sd_alg as sha-256."""
        token = create_sd_jwt(
            claims={"a": 1, "b": 2},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["a"],
        )
        jwt_part = token.split("~")[0]
        payload_b64 = jwt_part.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        assert payload["_sd_alg"] == "sha-256"

    def test_disclosed_claims_appear_as_disclosures(self):
        """Each disclosed claim produces a base64url-encoded disclosure."""
        token = create_sd_jwt(
            claims={"name": "agent-001", "role": "analyst", "level": 3},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name", "role"],
        )
        parts = token.split("~")
        # parts[0] is JWT, parts[-1] is empty (trailing ~)
        disclosures = [p for p in parts[1:] if p]
        assert len(disclosures) == 2, "Two disclosed claims should produce two disclosures"

        # Each disclosure is base64url([salt, claim_name, claim_value])
        for disc in disclosures:
            padded = disc + "=" * (-len(disc) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(padded))
            assert isinstance(decoded, list)
            assert len(decoded) == 3, "Disclosure must be [salt, name, value]"
            assert isinstance(decoded[0], str), "First element is salt"
            assert isinstance(decoded[1], str), "Second element is claim name"

    def test_hidden_claims_not_in_payload_directly(self):
        """Claims NOT in disclosed_claims should not appear in the JWT payload."""
        token = create_sd_jwt(
            claims={"public": "yes", "secret": "hidden_value"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["public"],
        )
        jwt_part = token.split("~")[0]
        payload_b64 = jwt_part.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        assert "secret" not in payload, "Hidden claim must not appear in JWT payload"
        assert "hidden_value" not in json.dumps(payload), "Hidden claim value must not be in payload"


# ===================================================================
# 2. create_sd_jwt — always_visible claims
# ===================================================================


class TestCreateSdJwtAlwaysVisible:
    """Tests for always_visible claims that are never hashed."""

    def test_always_visible_claims_in_payload(self):
        """always_visible claims must appear directly in the JWT payload."""
        token = create_sd_jwt(
            claims={"iss": "org-root", "sub": "agent-001", "role": "admin"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["role"],
            always_visible=["iss", "sub"],
        )
        jwt_part = token.split("~")[0]
        payload_b64 = jwt_part.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        assert payload["iss"] == "org-root"
        assert payload["sub"] == "agent-001"

    def test_always_visible_not_in_sd_array(self):
        """always_visible claims must NOT appear in the _sd hash array."""
        token = create_sd_jwt(
            claims={"iss": "org-root", "secret": "hidden"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=[],
            always_visible=["iss"],
        )
        jwt_part = token.split("~")[0]
        payload_b64 = jwt_part.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        # _sd should contain hash of "secret" only
        assert len(payload["_sd"]) == 1, "Only 'secret' should be hashed"

    def test_always_visible_not_in_disclosures(self):
        """always_visible claims should not produce disclosures."""
        token = create_sd_jwt(
            claims={"iss": "org-root", "name": "test"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
            always_visible=["iss"],
        )
        parts = token.split("~")
        disclosures = [p for p in parts[1:] if p]
        # Only "name" should have a disclosure
        assert len(disclosures) == 1

        padded = disclosures[0] + "=" * (-len(disclosures[0]) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
        assert decoded[1] == "name", "Only 'name' should be disclosed"


# ===================================================================
# 3. create_sd_jwt — disclosure hash verification
# ===================================================================


class TestSdJwtDisclosureHashing:
    """Verify that disclosure hashes in _sd match actual disclosures."""

    def test_disclosure_hash_matches_sd_entry(self):
        """Each disclosure's SHA-256 hash must appear in the _sd array."""
        token = create_sd_jwt(
            claims={"name": "agent-001", "role": "analyst"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name", "role"],
        )
        jwt_part = token.split("~")[0]
        payload_b64 = jwt_part.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        sd_hashes = set(payload["_sd"])

        parts = token.split("~")
        disclosures = [p for p in parts[1:] if p]

        for disc in disclosures:
            # Hash the raw base64url disclosure string
            disc_hash = (
                base64.urlsafe_b64encode(hashlib.sha256(disc.encode("ascii")).digest()).decode("ascii").rstrip("=")
            )
            assert disc_hash in sd_hashes, f"Disclosure hash {disc_hash} not found in _sd array {sd_hashes}"

    def test_hidden_claims_also_in_sd_array(self):
        """Claims that are NOT disclosed still have hashes in _sd."""
        token = create_sd_jwt(
            claims={"a": 1, "b": 2, "c": 3},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["a"],
        )
        jwt_part = token.split("~")[0]
        payload_b64 = jwt_part.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        # All 3 claims should have hashes in _sd
        assert len(payload["_sd"]) == 3, "All claims get hashed into _sd"


# ===================================================================
# 4. verify_sd_jwt — successful verification
# ===================================================================


class TestVerifySdJwt:
    """Tests for verify_sd_jwt with valid tokens."""

    def test_returns_dict(self):
        token = create_sd_jwt(
            claims={"name": "agent-001"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert isinstance(result, dict)

    def test_disclosed_claims_are_revealed(self):
        token = create_sd_jwt(
            claims={"name": "agent-001", "role": "analyst"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["name"] == "agent-001"

    def test_hidden_claims_not_revealed(self):
        """Claims without disclosures should not appear in result."""
        token = create_sd_jwt(
            claims={"name": "agent-001", "secret": "classified"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert "secret" not in result

    def test_always_visible_claims_in_result(self):
        token = create_sd_jwt(
            claims={"iss": "org-root", "name": "agent-001", "secret": "x"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
            always_visible=["iss"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["iss"] == "org-root"
        assert result["name"] == "agent-001"
        assert "secret" not in result

    def test_multiple_disclosed_claims(self):
        claims = {"a": 1, "b": "two", "c": [3], "d": {"nested": True}}
        token = create_sd_jwt(
            claims=claims,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["a", "b", "c", "d"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["a"] == 1
        assert result["b"] == "two"
        assert result["c"] == [3]
        assert result["d"] == {"nested": True}

    def test_all_claims_disclosed(self):
        """When all claims are disclosed, all should be in result."""
        claims = {"x": 1, "y": 2}
        token = create_sd_jwt(
            claims=claims,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["x", "y"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["x"] == 1
        assert result["y"] == 2

    def test_no_claims_disclosed(self):
        """When no claims are disclosed, only always_visible should be in result."""
        token = create_sd_jwt(
            claims={"secret1": "a", "secret2": "b"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=[],
            always_visible=[],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        # Only internal SD-JWT metadata should remain, not the claims
        assert "secret1" not in result
        assert "secret2" not in result


# ===================================================================
# 5. verify_sd_jwt — error cases
# ===================================================================


class TestVerifySdJwtErrors:
    """Tests for verify_sd_jwt error handling."""

    def test_rejects_invalid_signature(self):
        """Verification with wrong public key must fail."""
        token = create_sd_jwt(
            claims={"name": "agent-001"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
        )
        _, wrong_public_key = generate_keypair()
        with pytest.raises(Exception):
            verify_sd_jwt(token, wrong_public_key)

    def test_rejects_tampered_jwt(self):
        """Modifying the JWT portion must cause signature failure."""
        token = create_sd_jwt(
            claims={"name": "agent-001"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
        )
        parts = token.split("~")
        jwt_segments = parts[0].split(".")
        # Tamper with the payload
        payload_chars = list(jwt_segments[1])
        if payload_chars:
            payload_chars[0] = "A" if payload_chars[0] != "A" else "B"
        jwt_segments[1] = "".join(payload_chars)
        parts[0] = ".".join(jwt_segments)
        tampered = "~".join(parts)

        with pytest.raises(Exception):
            verify_sd_jwt(tampered, _PUBLIC_KEY)

    def test_rejects_tampered_disclosure(self):
        """Tampered disclosure should fail hash verification."""
        token = create_sd_jwt(
            claims={"name": "agent-001"},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["name"],
        )
        parts = token.split("~")
        # Tamper with the disclosure (parts[1])
        if parts[1]:
            tampered_disc = "AAAA" + parts[1][4:]
            parts[1] = tampered_disc
        tampered = "~".join(parts)

        with pytest.raises(ValueError, match="[Dd]isclosure.*hash"):
            verify_sd_jwt(tampered, _PUBLIC_KEY)

    def test_rejects_empty_token(self):
        with pytest.raises((ValueError, Exception)):
            verify_sd_jwt("", _PUBLIC_KEY)

    def test_rejects_malformed_token(self):
        with pytest.raises((ValueError, Exception)):
            verify_sd_jwt("not-a-valid-sd-jwt", _PUBLIC_KEY)


# ===================================================================
# 6. create_sd_jwt — input validation
# ===================================================================


class TestCreateSdJwtValidation:
    """Tests for input validation in create_sd_jwt."""

    def test_empty_signing_key_rejected(self):
        with pytest.raises(ValueError, match="signing_key"):
            create_sd_jwt(
                claims={"a": 1},
                signing_key="",
                disclosed_claims=["a"],
            )

    def test_empty_claims_rejected(self):
        with pytest.raises(ValueError, match="claims"):
            create_sd_jwt(
                claims={},
                signing_key=_PRIVATE_KEY,
                disclosed_claims=[],
            )

    def test_disclosed_claim_not_in_claims_rejected(self):
        """Disclosing a claim that doesn't exist in claims dict should error."""
        with pytest.raises(ValueError, match="not found in claims"):
            create_sd_jwt(
                claims={"a": 1},
                signing_key=_PRIVATE_KEY,
                disclosed_claims=["nonexistent"],
            )

    def test_always_visible_claim_not_in_claims_rejected(self):
        """always_visible claim that doesn't exist in claims dict should error."""
        with pytest.raises(ValueError, match="not found in claims"):
            create_sd_jwt(
                claims={"a": 1},
                signing_key=_PRIVATE_KEY,
                disclosed_claims=[],
                always_visible=["nonexistent"],
            )


# ===================================================================
# 7. export_chain_as_sd_jwt
# ===================================================================


class TestExportChainAsSdJwt:
    """Tests for export_chain_as_sd_jwt convenience function."""

    def test_returns_sd_jwt_string(self):
        chain = _make_chain()
        token = export_chain_as_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis"],
        )
        assert isinstance(token, str)
        assert "~" in token, "Must be SD-JWT combined format"

    def test_genesis_disclosed(self):
        chain = _make_chain()
        token = export_chain_as_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert "genesis" in result
        assert result["genesis"]["agent_id"] == "agent-001"

    def test_capabilities_disclosed(self):
        chain = _make_chain(with_capabilities=True)
        token = export_chain_as_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["capabilities"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert "capabilities" in result
        assert len(result["capabilities"]) == 1
        assert result["capabilities"][0]["capability"] == "analyze_data"

    def test_delegations_hidden(self):
        chain = _make_chain(with_delegations=True)
        token = export_chain_as_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert "delegations" not in result

    def test_selective_disclosure_of_chain_fields(self):
        chain = _make_chain(with_capabilities=True, with_delegations=True)
        token = export_chain_as_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "capabilities"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert "genesis" in result
        assert "capabilities" in result
        assert "delegations" not in result
        assert "chain_hash" not in result


# ===================================================================
# 8. export_capability_as_sd_jwt
# ===================================================================


class TestExportCapabilityAsSdJwt:
    """Tests for export_capability_as_sd_jwt convenience function."""

    def test_returns_sd_jwt_string(self):
        cap = _make_capability()
        token = export_capability_as_sd_jwt(
            attestation=cap,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["capability"],
        )
        assert isinstance(token, str)
        assert "~" in token

    def test_capability_name_disclosed(self):
        cap = _make_capability()
        token = export_capability_as_sd_jwt(
            attestation=cap,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["capability", "capability_type"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["capability"] == "analyze_data"
        assert result["capability_type"] == "action"

    def test_constraints_hidden(self):
        cap = _make_capability()
        token = export_capability_as_sd_jwt(
            attestation=cap,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["capability"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert "constraints" not in result

    def test_scope_disclosed(self):
        cap = _make_capability()
        token = export_capability_as_sd_jwt(
            attestation=cap,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["scope"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["scope"] == {"tables": ["transactions"]}

    def test_attester_id_disclosed(self):
        cap = _make_capability()
        token = export_capability_as_sd_jwt(
            attestation=cap,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["attester_id"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["attester_id"] == "org-root"


# ===================================================================
# 9. Edge cases and round-trip fidelity
# ===================================================================


class TestSdJwtEdgeCases:
    """Edge case and boundary condition tests."""

    def test_claims_with_nested_dicts(self):
        claims = {"config": {"level": 3, "tags": ["ml", "data"]}}
        token = create_sd_jwt(
            claims=claims,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["config"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["config"] == {"level": 3, "tags": ["ml", "data"]}

    def test_claims_with_list_values(self):
        claims = {"roles": ["admin", "reader"]}
        token = create_sd_jwt(
            claims=claims,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["roles"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["roles"] == ["admin", "reader"]

    def test_claims_with_null_value(self):
        claims = {"nullable": None, "present": "yes"}
        token = create_sd_jwt(
            claims=claims,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["nullable", "present"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["nullable"] is None
        assert result["present"] == "yes"

    def test_claims_with_numeric_values(self):
        claims = {"count": 42, "ratio": 3.14, "flag": True}
        token = create_sd_jwt(
            claims=claims,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["count", "ratio", "flag"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        assert result["count"] == 42
        assert result["ratio"] == 3.14
        assert result["flag"] is True

    def test_each_token_has_unique_salts(self):
        """Two SD-JWTs for the same claims should have different disclosures (different salts)."""
        claims = {"name": "agent-001"}
        token1 = create_sd_jwt(claims=claims, signing_key=_PRIVATE_KEY, disclosed_claims=["name"])
        token2 = create_sd_jwt(claims=claims, signing_key=_PRIVATE_KEY, disclosed_claims=["name"])

        disc1 = [p for p in token1.split("~")[1:] if p]
        disc2 = [p for p in token2.split("~")[1:] if p]
        assert disc1 != disc2, "Salts should differ between tokens"

    def test_large_number_of_claims(self):
        """SD-JWT should handle many claims."""
        claims = {f"claim_{i}": f"value_{i}" for i in range(50)}
        disclosed = [f"claim_{i}" for i in range(10)]
        token = create_sd_jwt(
            claims=claims,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=disclosed,
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        for i in range(10):
            assert result[f"claim_{i}"] == f"value_{i}"
        for i in range(10, 50):
            assert f"claim_{i}" not in result

    def test_empty_public_key_rejected(self):
        token = create_sd_jwt(
            claims={"a": 1},
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["a"],
        )
        with pytest.raises(ValueError, match="public_key"):
            verify_sd_jwt(token, "")
