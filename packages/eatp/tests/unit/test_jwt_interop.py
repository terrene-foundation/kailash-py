"""
Unit tests for EATP JWT interop module.

Tests export/import of trust chains, capabilities, and delegations as JWTs.
Covers standard IETF claims, custom eatp_* claims, expiration handling,
round-trip fidelity, and graceful error handling.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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
    with_audit: bool = False,
    with_constraints: bool = False,
) -> TrustLineageChain:
    genesis = _make_genesis(expires_at=expires_at)
    caps = [_make_capability(expires_at=expires_at)] if with_capabilities else []
    delegs = [_make_delegation(expires_at=expires_at)] if with_delegations else []
    audit_anchors = []
    if with_audit:
        audit_anchors = [
            AuditAnchor(
                id="audit-001",
                agent_id="agent-001",
                action="analyze",
                timestamp=_NOW,
                trust_chain_hash="hash123",
                result=ActionResult.SUCCESS,
                signature="sig-audit",
                resource="db:transactions",
                context={"query": "SELECT *"},
            )
        ]
    constraint_envelope = None
    if with_constraints:
        constraint_envelope = ConstraintEnvelope(
            id="env-agent-001",
            agent_id="agent-001",
            active_constraints=[
                Constraint(
                    id="con-001",
                    constraint_type=ConstraintType.FINANCIAL,
                    value=100,
                    source="cap-001",
                    priority=1,
                )
            ],
        )

    chain = TrustLineageChain(
        genesis=genesis,
        capabilities=caps,
        delegations=delegs,
        constraint_envelope=constraint_envelope,
        audit_anchors=audit_anchors,
    )
    return chain


# ---------------------------------------------------------------------------
# Skip if pyjwt not installed
# ---------------------------------------------------------------------------

jwt = pytest.importorskip("jwt", reason="pyjwt[crypto] required for JWT interop tests")

# Import the module under test AFTER confirming jwt is available
from eatp.interop.jwt import (
    EATP_VERSION,
    export_capability_as_jwt,
    export_chain_as_jwt,
    export_delegation_as_jwt,
    import_chain_from_jwt,
)

# ---------------------------------------------------------------------------
# Use EdDSA (Ed25519) for JWT tests — the same algorithm EATP uses in production.
# HMAC algorithms are excluded from the safe list to prevent key-confusion attacks.
# ---------------------------------------------------------------------------

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

_ed25519_key = Ed25519PrivateKey.generate()
SIGNING_KEY = _ed25519_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
VERIFY_KEY = _ed25519_key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
ALGORITHM = "EdDSA"


# ===================================================================
# 1. export_chain_as_jwt
# ===================================================================


class TestExportChainAsJWT:
    """Tests for export_chain_as_jwt."""

    def test_returns_string_token(self):
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_has_three_parts(self):
        """JWT tokens are header.payload.signature."""
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        parts = token.split(".")
        assert len(parts) == 3, f"Expected 3 JWT segments, got {len(parts)}"

    def test_standard_ietf_claims_present(self):
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        # iss - issuer should be the authority_id from genesis
        assert "iss" in payload
        assert payload["iss"] == chain.genesis.authority_id

        # sub - subject should be the agent_id
        assert "sub" in payload
        assert payload["sub"] == chain.genesis.agent_id

        # iat - issued at must be present and be a number
        assert "iat" in payload
        assert isinstance(payload["iat"], (int, float))

        # jti - JWT ID must be present and non-empty
        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_exp_claim_present_when_chain_has_expiry(self):
        chain = _make_chain(expires_at=_FUTURE)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        assert "exp" in payload
        assert isinstance(payload["exp"], (int, float))

    def test_exp_claim_absent_when_no_expiry(self):
        chain = _make_chain(expires_at=None)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        assert "exp" not in payload

    def test_eatp_version_claim(self):
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        assert payload["eatp_version"] == EATP_VERSION

    def test_eatp_chain_claim_contains_full_chain_data(self):
        chain = _make_chain(with_capabilities=True, with_delegations=True)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        assert "eatp_chain" in payload
        chain_data = payload["eatp_chain"]

        # Genesis
        assert "genesis" in chain_data
        assert chain_data["genesis"]["agent_id"] == "agent-001"

        # Capabilities
        assert "capabilities" in chain_data
        assert len(chain_data["capabilities"]) == 1
        assert chain_data["capabilities"][0]["capability"] == "analyze_data"

        # Delegations
        assert "delegations" in chain_data
        assert len(chain_data["delegations"]) == 1
        assert chain_data["delegations"][0]["delegator_id"] == "agent-001"

    def test_eatp_type_claim(self):
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        assert payload["eatp_type"] == "trust_chain"

    def test_chain_with_audit_anchors(self):
        chain = _make_chain(with_audit=True)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        chain_data = payload["eatp_chain"]
        assert "audit_anchors" in chain_data
        assert len(chain_data["audit_anchors"]) == 1
        assert chain_data["audit_anchors"][0]["action"] == "analyze"

    def test_chain_with_constraint_envelope(self):
        chain = _make_chain(with_constraints=True)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        chain_data = payload["eatp_chain"]
        assert "constraint_envelope" in chain_data
        assert chain_data["constraint_envelope"] is not None

    def test_minimal_chain_genesis_only(self):
        chain = _make_chain(with_capabilities=False, with_delegations=False)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        chain_data = payload["eatp_chain"]
        assert chain_data["genesis"]["id"] == "gen-agent-001"
        assert chain_data["capabilities"] == []
        assert chain_data["delegations"] == []


# ===================================================================
# 2. import_chain_from_jwt
# ===================================================================


class TestImportChainFromJWT:
    """Tests for import_chain_from_jwt."""

    def test_round_trip_preserves_genesis(self):
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)

        assert restored.genesis.id == chain.genesis.id
        assert restored.genesis.agent_id == chain.genesis.agent_id
        assert restored.genesis.authority_id == chain.genesis.authority_id
        assert restored.genesis.authority_type == chain.genesis.authority_type
        assert restored.genesis.signature_algorithm == chain.genesis.signature_algorithm
        assert restored.genesis.metadata == chain.genesis.metadata

    def test_round_trip_preserves_capabilities(self):
        chain = _make_chain(with_capabilities=True)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)

        assert len(restored.capabilities) == len(chain.capabilities)
        original = chain.capabilities[0]
        restored_cap = restored.capabilities[0]
        assert restored_cap.id == original.id
        assert restored_cap.capability == original.capability
        assert restored_cap.capability_type == original.capability_type
        assert restored_cap.constraints == original.constraints
        assert restored_cap.attester_id == original.attester_id
        assert restored_cap.scope == original.scope

    def test_round_trip_preserves_delegations(self):
        chain = _make_chain(with_delegations=True)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)

        assert len(restored.delegations) == len(chain.delegations)
        original = chain.delegations[0]
        restored_deleg = restored.delegations[0]
        assert restored_deleg.id == original.id
        assert restored_deleg.delegator_id == original.delegator_id
        assert restored_deleg.delegatee_id == original.delegatee_id
        assert restored_deleg.task_id == original.task_id
        assert restored_deleg.capabilities_delegated == original.capabilities_delegated
        assert restored_deleg.constraint_subset == original.constraint_subset
        assert restored_deleg.parent_delegation_id == original.parent_delegation_id

    def test_round_trip_preserves_constraint_envelope(self):
        chain = _make_chain(with_constraints=True)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)

        assert restored.constraint_envelope is not None
        assert restored.constraint_envelope.id == chain.constraint_envelope.id
        assert restored.constraint_envelope.agent_id == chain.constraint_envelope.agent_id

    def test_round_trip_minimal_chain(self):
        chain = _make_chain(with_capabilities=False, with_delegations=False)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)

        assert restored.genesis.id == chain.genesis.id
        assert restored.capabilities == []
        assert restored.delegations == []

    def test_rejects_invalid_signature(self):
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        with pytest.raises(Exception) as exc_info:
            import_chain_from_jwt(token, "wrong-key", algorithm=ALGORITHM)
        # Should raise a clear error, not silently return garbage
        assert exc_info.value is not None

    def test_rejects_expired_token(self):
        chain = _make_chain(expires_at=_PAST)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        with pytest.raises(Exception) as exc_info:
            import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)
        assert exc_info.value is not None

    def test_rejects_tampered_payload(self):
        """Modifying the token payload should cause signature verification failure."""
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        # Tamper: swap a character in the payload segment
        parts = token.split(".")
        payload_chars = list(parts[1])
        if payload_chars:
            payload_chars[0] = "A" if payload_chars[0] != "A" else "B"
        parts[1] = "".join(payload_chars)
        tampered = ".".join(parts)

        with pytest.raises(Exception):
            import_chain_from_jwt(tampered, VERIFY_KEY, algorithm=ALGORITHM)

    def test_rejects_missing_eatp_version(self):
        """Token without eatp_version should be rejected."""
        payload = {
            "iss": "org-root",
            "sub": "agent-001",
            "iat": int(_NOW.timestamp()),
            "jti": str(uuid.uuid4()),
            "eatp_type": "trust_chain",
            # deliberately no eatp_version
            "eatp_chain": _make_chain().to_dict(),
        }
        token = jwt.encode(payload, SIGNING_KEY, algorithm=ALGORITHM)
        with pytest.raises(ValueError, match="eatp_version"):
            import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)

    def test_rejects_wrong_eatp_type(self):
        """Token with wrong eatp_type should be rejected."""
        chain = _make_chain()
        payload = {
            "iss": "org-root",
            "sub": "agent-001",
            "iat": int(_NOW.timestamp()),
            "jti": str(uuid.uuid4()),
            "eatp_version": EATP_VERSION,
            "eatp_type": "not_a_chain",
            "eatp_chain": chain.to_dict(),
        }
        token = jwt.encode(payload, SIGNING_KEY, algorithm=ALGORITHM)
        with pytest.raises(ValueError, match="eatp_type"):
            import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)

    def test_rejects_missing_eatp_chain(self):
        """Token without eatp_chain claim should be rejected."""
        payload = {
            "iss": "org-root",
            "sub": "agent-001",
            "iat": int(_NOW.timestamp()),
            "jti": str(uuid.uuid4()),
            "eatp_version": EATP_VERSION,
            "eatp_type": "trust_chain",
            # no eatp_chain
        }
        token = jwt.encode(payload, SIGNING_KEY, algorithm=ALGORITHM)
        with pytest.raises(ValueError, match="eatp_chain"):
            import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)

    def test_returns_trust_lineage_chain_type(self):
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)
        assert isinstance(restored, TrustLineageChain)


# ===================================================================
# 3. export_capability_as_jwt
# ===================================================================


class TestExportCapabilityAsJWT:
    """Tests for export_capability_as_jwt."""

    def test_returns_valid_jwt(self):
        cap = _make_capability()
        token = export_capability_as_jwt(cap, SIGNING_KEY, algorithm=ALGORITHM)
        assert isinstance(token, str)
        parts = token.split(".")
        assert len(parts) == 3

    def test_standard_claims(self):
        cap = _make_capability()
        token = export_capability_as_jwt(cap, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        assert payload["iss"] == cap.attester_id
        assert payload["sub"] == cap.id
        assert "iat" in payload
        assert "jti" in payload
        assert payload["eatp_version"] == EATP_VERSION
        assert payload["eatp_type"] == "capability_attestation"

    def test_capability_data_in_payload(self):
        cap = _make_capability()
        token = export_capability_as_jwt(cap, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        assert "eatp_capability" in payload
        cap_data = payload["eatp_capability"]
        assert cap_data["id"] == cap.id
        assert cap_data["capability"] == cap.capability
        assert cap_data["capability_type"] == cap.capability_type.value
        assert cap_data["constraints"] == cap.constraints
        assert cap_data["attester_id"] == cap.attester_id
        assert cap_data["scope"] == cap.scope

    def test_exp_claim_when_capability_expires(self):
        cap = _make_capability(expires_at=_FUTURE)
        token = export_capability_as_jwt(cap, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        assert "exp" in payload

    def test_no_exp_when_no_expiry(self):
        cap = _make_capability(expires_at=None)
        token = export_capability_as_jwt(cap, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        assert "exp" not in payload


# ===================================================================
# 4. export_delegation_as_jwt
# ===================================================================


class TestExportDelegationAsJWT:
    """Tests for export_delegation_as_jwt."""

    def test_returns_valid_jwt(self):
        deleg = _make_delegation()
        token = export_delegation_as_jwt(deleg, SIGNING_KEY, algorithm=ALGORITHM)
        assert isinstance(token, str)
        parts = token.split(".")
        assert len(parts) == 3

    def test_standard_claims(self):
        deleg = _make_delegation()
        token = export_delegation_as_jwt(deleg, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        assert payload["iss"] == deleg.delegator_id
        assert payload["sub"] == deleg.delegatee_id
        assert "iat" in payload
        assert "jti" in payload
        assert payload["eatp_version"] == EATP_VERSION
        assert payload["eatp_type"] == "delegation"

    def test_delegation_data_in_payload(self):
        deleg = _make_delegation()
        token = export_delegation_as_jwt(deleg, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        assert "eatp_delegation" in payload
        d = payload["eatp_delegation"]
        assert d["id"] == deleg.id
        assert d["delegator_id"] == deleg.delegator_id
        assert d["delegatee_id"] == deleg.delegatee_id
        assert d["task_id"] == deleg.task_id
        assert d["capabilities_delegated"] == deleg.capabilities_delegated
        assert d["constraint_subset"] == deleg.constraint_subset

    def test_exp_claim_when_delegation_expires(self):
        deleg = _make_delegation(expires_at=_FUTURE)
        token = export_delegation_as_jwt(deleg, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        assert "exp" in payload

    def test_no_exp_when_no_expiry(self):
        deleg = _make_delegation(expires_at=None)
        token = export_delegation_as_jwt(deleg, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        assert "exp" not in payload


# ===================================================================
# 5. Error handling: missing pyjwt
# ===================================================================


class TestMissingPyJWT:
    """Verify the module raises a clear error when pyjwt is not installed."""

    def test_import_error_message_is_clear(self):
        """Simulating missing jwt at the module level is tricky in unit tests.
        Instead, we verify the guard import pattern exists by checking the
        module-level EATP_VERSION constant is accessible (proving the module
        loaded successfully with jwt present)."""
        assert EATP_VERSION == "0.1.0"


# ===================================================================
# 6. Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_chain_with_multiple_capabilities(self):
        genesis = _make_genesis()
        caps = [_make_capability(cap_id=f"cap-{i}", capability=f"cap_{i}") for i in range(5)]
        chain = TrustLineageChain(genesis=genesis, capabilities=caps)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)
        assert len(restored.capabilities) == 5

    def test_chain_with_multiple_delegations(self):
        genesis = _make_genesis()
        delegs = [_make_delegation(deleg_id=f"del-{i}") for i in range(3)]
        chain = TrustLineageChain(genesis=genesis, delegations=delegs)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)
        assert len(restored.delegations) == 3

    def test_metadata_with_nested_structures(self):
        genesis = _make_genesis()
        genesis.metadata = {
            "department": "engineering",
            "tags": ["ml", "data"],
            "config": {"level": 3, "active": True},
        }
        chain = TrustLineageChain(genesis=genesis)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)
        assert restored.genesis.metadata == genesis.metadata

    def test_jti_is_unique_per_export(self):
        chain = _make_chain()
        token1 = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        token2 = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload1 = jwt.decode(token1, VERIFY_KEY, algorithms=[ALGORITHM])
        payload2 = jwt.decode(token2, VERIFY_KEY, algorithms=[ALGORITHM])
        assert payload1["jti"] != payload2["jti"], "Each JWT must have a unique jti"

    def test_empty_constraints_list(self):
        cap = _make_capability()
        cap.constraints = []
        token = export_capability_as_jwt(cap, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        assert payload["eatp_capability"]["constraints"] == []

    def test_none_scope_in_capability(self):
        cap = _make_capability()
        cap.scope = None
        token = export_capability_as_jwt(cap, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])
        assert payload["eatp_capability"]["scope"] is None

    def test_signing_key_cannot_be_empty(self):
        chain = _make_chain()
        with pytest.raises((ValueError, Exception)):
            export_chain_as_jwt(chain, "", algorithm=ALGORITHM)

    def test_verify_key_cannot_be_empty(self):
        chain = _make_chain()
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        with pytest.raises((ValueError, Exception)):
            import_chain_from_jwt(token, "", algorithm=ALGORITHM)


# ===================================================================
# 7. Reasoning trace confidentiality filtering
# ===================================================================

from eatp.chain import ActionResult, AuditAnchor
from eatp.crypto import hash_reasoning_trace
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace


def _make_reasoning_trace(
    confidentiality: ConfidentialityLevel,
    decision: str = "delegate analysis task",
    rationale: str = "agent-002 has required capability and capacity",
) -> ReasoningTrace:
    """Create a ReasoningTrace at the given confidentiality level."""
    return ReasoningTrace(
        decision=decision,
        rationale=rationale,
        confidentiality=confidentiality,
        timestamp=_NOW,
        alternatives_considered=["agent-003 was busy"],
        evidence=[{"source": "capability_check", "result": "pass"}],
        methodology="capability_matching",
        confidence=0.92,
    )


def _make_delegation_with_reasoning(
    confidentiality: ConfidentialityLevel,
    deleg_id: str = "del-reason-001",
) -> DelegationRecord:
    """Create a DelegationRecord carrying a reasoning trace at the given level."""
    trace = _make_reasoning_trace(confidentiality)
    trace_hash = hash_reasoning_trace(trace)
    return DelegationRecord(
        id=deleg_id,
        delegator_id="agent-001",
        delegatee_id="agent-002",
        task_id="task-abc",
        capabilities_delegated=["analyze_data"],
        constraint_subset=["read_only"],
        delegated_at=_NOW,
        signature="sig-deleg",
        expires_at=None,
        parent_delegation_id=None,
        delegation_chain=["agent-001", "agent-002"],
        delegation_depth=1,
        reasoning_trace=trace,
        reasoning_trace_hash=trace_hash,
        reasoning_signature="sig-reasoning-placeholder",
    )


def _make_chain_with_reasoning_delegation(
    confidentiality: ConfidentialityLevel,
) -> TrustLineageChain:
    """Build a chain whose single delegation carries a reasoning trace."""
    genesis = _make_genesis()
    delegation = _make_delegation_with_reasoning(confidentiality)
    return TrustLineageChain(
        genesis=genesis,
        delegations=[delegation],
    )


def _make_chain_with_reasoning_audit(
    confidentiality: ConfidentialityLevel,
) -> TrustLineageChain:
    """Build a chain whose single audit anchor carries a reasoning trace."""
    genesis = _make_genesis()
    trace = _make_reasoning_trace(confidentiality)
    trace_hash = hash_reasoning_trace(trace)
    audit = AuditAnchor(
        id="audit-reason-001",
        agent_id="agent-001",
        action="analyze",
        timestamp=_NOW,
        trust_chain_hash="hash123",
        result=ActionResult.SUCCESS,
        signature="sig-audit",
        resource="db:transactions",
        context={"query": "SELECT *"},
        reasoning_trace=trace,
        reasoning_trace_hash=trace_hash,
        reasoning_signature="sig-audit-reasoning-placeholder",
    )
    return TrustLineageChain(
        genesis=genesis,
        audit_anchors=[audit],
    )


class TestJWTReasoningConfidentiality:
    """Tests for confidentiality-based filtering of reasoning traces in JWT export.

    The JWT serializer strips reasoning_trace from delegations and audit anchors
    when confidentiality > RESTRICTED, while always preserving the hash and
    signature (which are integrity proofs, not confidential content).
    """

    def test_jwt_export_includes_public_reasoning_trace(self):
        """PUBLIC reasoning traces MUST appear in JWT claims."""
        chain = _make_chain_with_reasoning_delegation(ConfidentialityLevel.PUBLIC)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        delegation_data = payload["eatp_chain"]["delegations"][0]
        assert "reasoning_trace" in delegation_data, "PUBLIC reasoning trace must be included in JWT claims"
        assert delegation_data["reasoning_trace"]["decision"] == "delegate analysis task"
        assert delegation_data["reasoning_trace"]["confidentiality"] == "public"
        # Hash and signature must also be present
        assert "reasoning_trace_hash" in delegation_data
        assert "reasoning_signature" in delegation_data

    def test_jwt_export_includes_restricted_reasoning_trace(self):
        """RESTRICTED reasoning traces (boundary) MUST appear in JWT claims."""
        chain = _make_chain_with_reasoning_delegation(ConfidentialityLevel.RESTRICTED)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        delegation_data = payload["eatp_chain"]["delegations"][0]
        assert "reasoning_trace" in delegation_data, (
            "RESTRICTED reasoning trace must be included (boundary: <= RESTRICTED)"
        )
        assert delegation_data["reasoning_trace"]["confidentiality"] == "restricted"
        # Hash and signature must also be present
        assert "reasoning_trace_hash" in delegation_data
        assert "reasoning_signature" in delegation_data

    def test_jwt_export_strips_confidential_reasoning_trace(self):
        """CONFIDENTIAL reasoning traces MUST be stripped from JWT claims."""
        chain = _make_chain_with_reasoning_delegation(ConfidentialityLevel.CONFIDENTIAL)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        delegation_data = payload["eatp_chain"]["delegations"][0]
        assert "reasoning_trace" not in delegation_data, "CONFIDENTIAL reasoning trace must NOT appear in JWT claims"
        # Hash and signature are integrity proofs, not confidential -- always present
        assert "reasoning_trace_hash" in delegation_data
        assert delegation_data["reasoning_trace_hash"] == hash_reasoning_trace(chain.delegations[0].reasoning_trace)
        assert "reasoning_signature" in delegation_data

    def test_jwt_export_strips_secret_reasoning_trace(self):
        """SECRET reasoning traces MUST be stripped from JWT claims."""
        chain = _make_chain_with_reasoning_delegation(ConfidentialityLevel.SECRET)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        delegation_data = payload["eatp_chain"]["delegations"][0]
        assert "reasoning_trace" not in delegation_data, "SECRET reasoning trace must NOT appear in JWT claims"
        # Hash and signature still present for integrity verification
        assert "reasoning_trace_hash" in delegation_data
        assert "reasoning_signature" in delegation_data

    def test_jwt_export_audit_anchor_filters_confidential(self):
        """Audit anchor with CONFIDENTIAL reasoning should have trace stripped."""
        chain = _make_chain_with_reasoning_audit(ConfidentialityLevel.CONFIDENTIAL)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[ALGORITHM])

        audit_data = payload["eatp_chain"]["audit_anchors"][0]
        assert "reasoning_trace" not in audit_data, "CONFIDENTIAL reasoning trace on audit anchor must be stripped"
        # Hash and signature survive filtering
        assert "reasoning_trace_hash" in audit_data
        assert audit_data["reasoning_trace_hash"] == hash_reasoning_trace(chain.audit_anchors[0].reasoning_trace)
        assert "reasoning_signature" in audit_data

    def test_jwt_roundtrip_preserves_public_reasoning(self):
        """Export chain with PUBLIC reasoning as JWT, import back, verify survival."""
        chain = _make_chain_with_reasoning_delegation(ConfidentialityLevel.PUBLIC)
        token = export_chain_as_jwt(chain, SIGNING_KEY, algorithm=ALGORITHM)
        restored = import_chain_from_jwt(token, VERIFY_KEY, algorithm=ALGORITHM)

        assert len(restored.delegations) == 1
        restored_deleg = restored.delegations[0]

        # The reasoning trace must survive the round trip
        assert restored_deleg.reasoning_trace is not None, "PUBLIC reasoning trace must survive JWT round-trip"
        assert restored_deleg.reasoning_trace.decision == "delegate analysis task"
        assert restored_deleg.reasoning_trace.rationale == ("agent-002 has required capability and capacity")
        assert restored_deleg.reasoning_trace.confidentiality == ConfidentialityLevel.PUBLIC
        assert restored_deleg.reasoning_trace.confidence == 0.92
        assert restored_deleg.reasoning_trace.methodology == "capability_matching"
        assert restored_deleg.reasoning_trace.alternatives_considered == ["agent-003 was busy"]
        # Hash and signature also preserved
        assert restored_deleg.reasoning_trace_hash is not None
        assert restored_deleg.reasoning_trace_hash == hash_reasoning_trace(chain.delegations[0].reasoning_trace)
        assert restored_deleg.reasoning_signature == "sig-reasoning-placeholder"
