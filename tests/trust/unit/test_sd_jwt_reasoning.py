"""
Unit tests for SD-JWT reasoning trace selective disclosure.

Tests the confidentiality-driven SD-JWT disclosure for EATP reasoning traces:
- PUBLIC: reasoning fields included in always-visible payload
- RESTRICTED: reasoning_trace is selectively disclosable (hidden by default)
- CONFIDENTIAL: reasoning_trace AND alternatives_considered hidden
- SECRET/TOP_SECRET: only reasoning_trace_hash is included (trace itself stripped)

Covers:
- create_reasoning_sd_jwt: create SD-JWTs with confidentiality-driven disclosure
- Round-trip fidelity: create -> disclose -> verify
- Backward compatibility: chains without reasoning traces still work
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.signing.crypto import generate_keypair, hash_reasoning_trace
from kailash.trust.reasoning.traces import ConfidentialityLevel, ReasoningTrace

# ---------------------------------------------------------------------------
# Helpers: reusable fixtures
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)
_FUTURE = _NOW + timedelta(hours=24)


def _make_reasoning_trace(
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.PUBLIC,
    decision: str = "approve delegation",
    rationale: str = "agent has required capabilities and clean audit history",
    alternatives: list[str] | None = None,
    confidence: float = 0.95,
) -> ReasoningTrace:
    return ReasoningTrace(
        decision=decision,
        rationale=rationale,
        confidentiality=confidentiality,
        timestamp=_NOW,
        alternatives_considered=alternatives or ["deny", "defer to human"],
        evidence=[{"type": "audit_check", "result": "clean"}],
        methodology="capability_matching",
        confidence=confidence,
    )


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


def _make_delegation(
    deleg_id: str = "del-001",
    reasoning_trace: ReasoningTrace | None = None,
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
        reasoning_trace=reasoning_trace,
    )


def _make_chain_with_reasoning(
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.PUBLIC,
) -> TrustLineageChain:
    genesis = _make_genesis()
    trace = _make_reasoning_trace(confidentiality=confidentiality)
    delegation = _make_delegation(reasoning_trace=trace)

    return TrustLineageChain(
        genesis=genesis,
        capabilities=[],
        delegations=[delegation],
    )


def _make_chain_without_reasoning() -> TrustLineageChain:
    genesis = _make_genesis()
    delegation = _make_delegation(reasoning_trace=None)
    return TrustLineageChain(
        genesis=genesis,
        capabilities=[],
        delegations=[delegation],
    )


# ---------------------------------------------------------------------------
# Skip if PyNaCl is not installed (required for Ed25519)
# ---------------------------------------------------------------------------

nacl = pytest.importorskip("nacl", reason="PyNaCl required for SD-JWT tests")

# Import module under test after confirming nacl is available
from kailash.trust.interop.sd_jwt import (
    create_reasoning_sd_jwt,
    create_sd_jwt,
    verify_sd_jwt,
)

# Generate a real Ed25519 key pair for all tests
_PRIVATE_KEY, _PUBLIC_KEY = generate_keypair()


# ===================================================================
# 1. create_reasoning_sd_jwt -- PUBLIC confidentiality
# ===================================================================


class TestReasoningSdJwtPublic:
    """PUBLIC reasoning traces should be fully disclosed in the JWT payload."""

    def test_public_reasoning_all_fields_disclosed(self):
        """PUBLIC: all reasoning fields appear in verified result by default."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.PUBLIC)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        assert "genesis" in result
        assert "delegations" in result
        # For PUBLIC, reasoning data within delegations should be fully visible
        deleg = result["delegations"][0]
        assert "reasoning_trace" in deleg
        assert deleg["reasoning_trace"]["decision"] == "approve delegation"
        assert deleg["reasoning_trace"]["rationale"] is not None
        assert deleg["reasoning_trace"]["alternatives_considered"] is not None

    def test_public_reasoning_contains_full_trace(self):
        """PUBLIC: the full reasoning trace dict should be present."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.PUBLIC)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)
        trace = result["delegations"][0]["reasoning_trace"]
        assert trace["confidence"] == 0.95
        assert trace["methodology"] == "capability_matching"
        assert len(trace["evidence"]) == 1


# ===================================================================
# 2. create_reasoning_sd_jwt -- RESTRICTED confidentiality
# ===================================================================


class TestReasoningSdJwtRestricted:
    """RESTRICTED: reasoning_trace is a selectively disclosable claim."""

    def test_restricted_reasoning_hidden_by_default(self):
        """RESTRICTED: reasoning_trace hidden when not in disclosed_claims."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.RESTRICTED)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        # Delegations should be visible but reasoning_trace should be stripped
        assert "delegations" in result
        deleg = result["delegations"][0]
        assert "reasoning_trace" not in deleg

    def test_restricted_reasoning_disclosed_when_requested(self):
        """RESTRICTED: reasoning_trace visible when explicitly disclosed."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.RESTRICTED)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
            disclose_reasoning=True,
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace" in deleg
        assert deleg["reasoning_trace"]["decision"] == "approve delegation"

    def test_restricted_reasoning_hash_present(self):
        """RESTRICTED: reasoning_trace_hash should be present for verification."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.RESTRICTED)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace_hash" in deleg
        # The hash should be a 64-char hex string
        assert len(deleg["reasoning_trace_hash"]) == 64


# ===================================================================
# 3. create_reasoning_sd_jwt -- CONFIDENTIAL confidentiality
# ===================================================================


class TestReasoningSdJwtConfidential:
    """CONFIDENTIAL: reasoning_trace AND alternatives_considered hidden."""

    def test_confidential_reasoning_hidden_by_default(self):
        """CONFIDENTIAL: reasoning_trace hidden when not disclosed."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.CONFIDENTIAL)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace" not in deleg

    def test_confidential_disclosed_strips_alternatives(self):
        """CONFIDENTIAL: even when disclosed, alternatives_considered is removed."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.CONFIDENTIAL)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
            disclose_reasoning=True,
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace" in deleg
        # alternatives_considered should be stripped at CONFIDENTIAL level
        assert "alternatives_considered" not in deleg["reasoning_trace"]

    def test_confidential_keeps_decision_and_rationale(self):
        """CONFIDENTIAL: decision and rationale present when disclosed."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.CONFIDENTIAL)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
            disclose_reasoning=True,
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        trace = result["delegations"][0]["reasoning_trace"]
        assert trace["decision"] == "approve delegation"
        assert trace["rationale"] is not None

    def test_confidential_hash_present(self):
        """CONFIDENTIAL: reasoning_trace_hash always present."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.CONFIDENTIAL)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace_hash" in deleg
        assert len(deleg["reasoning_trace_hash"]) == 64


# ===================================================================
# 4. create_reasoning_sd_jwt -- SECRET / TOP_SECRET confidentiality
# ===================================================================


class TestReasoningSdJwtSecretTopSecret:
    """SECRET/TOP_SECRET: only reasoning_trace_hash included, trace stripped."""

    def test_secret_only_hash_included(self):
        """SECRET: reasoning_trace completely removed, only hash present."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.SECRET)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace" not in deleg
        assert "reasoning_trace_hash" in deleg
        assert len(deleg["reasoning_trace_hash"]) == 64

    def test_secret_disclose_reasoning_has_no_effect(self):
        """SECRET: even with disclose_reasoning=True, trace is not included."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.SECRET)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
            disclose_reasoning=True,
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace" not in deleg
        assert "reasoning_trace_hash" in deleg

    def test_top_secret_only_hash_included(self):
        """TOP_SECRET: reasoning_trace completely removed, only hash present."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.TOP_SECRET)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace" not in deleg
        assert "reasoning_trace_hash" in deleg

    def test_top_secret_disclose_reasoning_has_no_effect(self):
        """TOP_SECRET: disclose_reasoning=True has no effect."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.TOP_SECRET)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
            disclose_reasoning=True,
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace" not in deleg
        assert "reasoning_trace_hash" in deleg

    def test_secret_hash_matches_original_trace(self):
        """SECRET: the hash should match hash_reasoning_trace() output."""
        trace = _make_reasoning_trace(confidentiality=ConfidentialityLevel.SECRET)
        expected_hash = hash_reasoning_trace(trace)

        chain = _make_chain_with_reasoning(ConfidentialityLevel.SECRET)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert deleg["reasoning_trace_hash"] == expected_hash


# ===================================================================
# 5. Backward compatibility -- chains without reasoning traces
# ===================================================================


class TestReasoningSdJwtBackwardCompatibility:
    """SD-JWT without reasoning traces should still work correctly."""

    def test_chain_without_reasoning_works(self):
        """Chain with no reasoning trace produces valid SD-JWT."""
        chain = _make_chain_without_reasoning()
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        assert "genesis" in result
        assert "delegations" in result
        deleg = result["delegations"][0]
        assert "reasoning_trace" not in deleg
        assert "reasoning_trace_hash" not in deleg

    def test_chain_without_reasoning_ignores_disclose_flag(self):
        """disclose_reasoning=True has no effect when no trace exists."""
        chain = _make_chain_without_reasoning()
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
            disclose_reasoning=True,
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        deleg = result["delegations"][0]
        assert "reasoning_trace" not in deleg
        assert "reasoning_trace_hash" not in deleg


# ===================================================================
# 6. Round-trip fidelity: create -> disclose -> verify
# ===================================================================


class TestReasoningSdJwtRoundTrip:
    """Full round-trip tests: create SD-JWT, verify, check claim fidelity."""

    def test_public_round_trip_preserves_all_fields(self):
        """PUBLIC: round-trip preserves complete reasoning trace."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.PUBLIC)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        trace = result["delegations"][0]["reasoning_trace"]
        assert trace["decision"] == "approve delegation"
        assert trace["rationale"] == "agent has required capabilities and clean audit history"
        assert trace["alternatives_considered"] == ["deny", "defer to human"]
        assert trace["confidence"] == 0.95
        assert trace["methodology"] == "capability_matching"
        assert len(trace["evidence"]) == 1
        assert trace["evidence"][0]["type"] == "audit_check"

    def test_restricted_round_trip_with_disclosure(self):
        """RESTRICTED: round-trip with explicit disclosure preserves all fields."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.RESTRICTED)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
            disclose_reasoning=True,
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        trace = result["delegations"][0]["reasoning_trace"]
        assert trace["decision"] == "approve delegation"
        assert trace["alternatives_considered"] == ["deny", "defer to human"]
        assert trace["confidence"] == 0.95

    def test_confidential_round_trip_with_disclosure(self):
        """CONFIDENTIAL: round-trip with disclosure preserves core fields but strips alternatives."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.CONFIDENTIAL)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
            disclose_reasoning=True,
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        trace = result["delegations"][0]["reasoning_trace"]
        assert trace["decision"] == "approve delegation"
        assert trace["rationale"] == "agent has required capabilities and clean audit history"
        # alternatives_considered MUST be stripped at CONFIDENTIAL level
        assert "alternatives_considered" not in trace

    def test_signature_verification_rejects_wrong_key(self):
        """Round-trip must fail verification with wrong public key."""
        chain = _make_chain_with_reasoning(ConfidentialityLevel.PUBLIC)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        _, wrong_key = generate_keypair()
        with pytest.raises(Exception):
            verify_sd_jwt(token, wrong_key)


# ===================================================================
# 7. Input validation
# ===================================================================


class TestReasoningSdJwtValidation:
    """Input validation for create_reasoning_sd_jwt."""

    def test_empty_signing_key_rejected(self):
        chain = _make_chain_with_reasoning(ConfidentialityLevel.PUBLIC)
        with pytest.raises(ValueError, match="signing_key"):
            create_reasoning_sd_jwt(
                chain=chain,
                signing_key="",
                disclosed_claims=["genesis"],
            )

    def test_invalid_disclosed_claim_rejected(self):
        chain = _make_chain_with_reasoning(ConfidentialityLevel.PUBLIC)
        with pytest.raises(ValueError, match="not found in claims"):
            create_reasoning_sd_jwt(
                chain=chain,
                signing_key=_PRIVATE_KEY,
                disclosed_claims=["nonexistent_field"],
            )

    def test_returns_string(self):
        chain = _make_chain_with_reasoning(ConfidentialityLevel.PUBLIC)
        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis"],
        )
        assert isinstance(token, str)
        assert "~" in token


# ===================================================================
# 8. Multiple delegations with mixed confidentiality
# ===================================================================


class TestReasoningSdJwtMixedDelegations:
    """Chains with multiple delegations having different confidentiality levels."""

    def test_mixed_confidentiality_delegations(self):
        """Each delegation's reasoning is handled per its own confidentiality."""
        genesis = _make_genesis()
        public_trace = _make_reasoning_trace(confidentiality=ConfidentialityLevel.PUBLIC)
        secret_trace = _make_reasoning_trace(
            confidentiality=ConfidentialityLevel.SECRET,
            decision="escalate to senior agent",
        )

        deleg1 = DelegationRecord(
            id="del-pub",
            delegator_id="agent-001",
            delegatee_id="agent-002",
            task_id="task-1",
            capabilities_delegated=["analyze"],
            constraint_subset=[],
            delegated_at=_NOW,
            signature="sig-1",
            expires_at=None,
            parent_delegation_id=None,
            delegation_chain=["agent-001", "agent-002"],
            delegation_depth=1,
            reasoning_trace=public_trace,
        )
        deleg2 = DelegationRecord(
            id="del-secret",
            delegator_id="agent-002",
            delegatee_id="agent-003",
            task_id="task-2",
            capabilities_delegated=["execute"],
            constraint_subset=[],
            delegated_at=_NOW,
            signature="sig-2",
            expires_at=None,
            parent_delegation_id="del-pub",
            delegation_chain=["agent-001", "agent-002", "agent-003"],
            delegation_depth=2,
            reasoning_trace=secret_trace,
        )

        chain = TrustLineageChain(
            genesis=genesis,
            capabilities=[],
            delegations=[deleg1, deleg2],
        )

        token = create_reasoning_sd_jwt(
            chain=chain,
            signing_key=_PRIVATE_KEY,
            disclosed_claims=["genesis", "delegations"],
        )
        result = verify_sd_jwt(token, _PUBLIC_KEY)

        delegations = result["delegations"]
        assert len(delegations) == 2

        # First delegation (PUBLIC): full reasoning trace visible
        pub_deleg = delegations[0]
        assert "reasoning_trace" in pub_deleg
        assert pub_deleg["reasoning_trace"]["decision"] == "approve delegation"

        # Second delegation (SECRET): only hash, no trace
        secret_deleg = delegations[1]
        assert "reasoning_trace" not in secret_deleg
        assert "reasoning_trace_hash" in secret_deleg
