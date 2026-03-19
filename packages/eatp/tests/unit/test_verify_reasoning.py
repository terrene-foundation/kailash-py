# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for verify() reasoning trace integration (TODO-012).

Covers:
- QUICK verification: no reasoning checks (unchanged behavior)
- STANDARD verification: reasoning presence check when REASONING_REQUIRED active
- FULL verification: reasoning hash + signature cryptographic verification
- VerificationResult reasoning fields (reasoning_verified, reasoning_present)
- Backward compatibility: no reasoning traces works identically to before

Written BEFORE implementation (TDD). Tests define the contract.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import uuid4

import pytest

from eatp.authority import AuthorityPermission, OrganizationalAuthority
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
    VerificationLevel,
    VerificationResult,
)
from eatp.crypto import (
    generate_keypair,
    hash_reasoning_trace,
    serialize_for_signing,
    sign,
    sign_reasoning_trace,
)
from eatp.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace
from eatp.store.memory import InMemoryTrustStore

logger = logging.getLogger(__name__)

FIXED_TIMESTAMP = datetime(2026, 3, 11, 14, 30, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Real In-Memory Authority Registry (NOT a mock)
# ---------------------------------------------------------------------------


class SimpleAuthorityRegistry:
    """Real in-memory authority registry for tests."""

    def __init__(self) -> None:
        self._authorities: Dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        pass

    def register(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority

    async def get_authority(
        self,
        authority_id: str,
        include_inactive: bool = False,
    ) -> OrganizationalAuthority:
        authority = self._authorities.get(authority_id)
        if authority is None:
            from eatp.exceptions import AuthorityNotFoundError

            raise AuthorityNotFoundError(authority_id)
        if not authority.is_active and not include_inactive:
            from eatp.exceptions import AuthorityInactiveError

            raise AuthorityInactiveError(authority_id)
        return authority

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


@pytest.fixture
def authority(keypair):
    """Create a real OrganizationalAuthority."""
    _, public_key = keypair
    return OrganizationalAuthority(
        id="org-test",
        name="Test Corp",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="test-key-001",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.DELEGATE_TRUST,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
    )


@pytest.fixture
def registry(authority):
    """Real authority registry with test authority."""
    reg = SimpleAuthorityRegistry()
    reg.register(authority)
    return reg


@pytest.fixture
def key_manager(keypair):
    """TrustKeyManager with the test private key."""
    private_key, _ = keypair
    km = TrustKeyManager()
    km.register_key("test-key-001", private_key)
    return km


@pytest.fixture
async def memory_store():
    """Initialized InMemoryTrustStore."""
    store = InMemoryTrustStore()
    await store.initialize()
    return store


@pytest.fixture
async def ops(registry, key_manager, memory_store):
    """Initialized TrustOperations instance."""
    operations = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=memory_store,
    )
    await operations.initialize()
    return operations


@pytest.fixture
def reasoning_trace():
    """A fully populated ReasoningTrace."""
    return ReasoningTrace(
        decision="Approve data access",
        rationale="Agent has valid capability and passes constraints",
        confidentiality=ConfidentialityLevel.RESTRICTED,
        timestamp=FIXED_TIMESTAMP,
        confidence=0.95,
    )


@pytest.fixture
def signed_reasoning_trace(reasoning_trace, keypair):
    """A ReasoningTrace with hash and signature computed."""
    private_key, _ = keypair
    trace_hash = hash_reasoning_trace(reasoning_trace)
    trace_sig = sign_reasoning_trace(reasoning_trace, private_key)
    return reasoning_trace, trace_hash, trace_sig


async def _establish_agent_with_capability(
    ops: TrustOperations,
    agent_id: str,
    capabilities: list,
    constraints: Optional[list] = None,
):
    """Helper: establish an agent with given capabilities and optional constraints."""
    cap_requests = [
        CapabilityRequest(
            capability=cap,
            capability_type=CapabilityType.ACTION,
        )
        for cap in capabilities
    ]
    await ops.establish(
        agent_id=agent_id,
        authority_id="org-test",
        capabilities=cap_requests,
    )
    # If constraints provided, add them to the agent's constraint envelope
    if constraints:
        chain = await ops.trust_store.get_chain(agent_id)
        for constraint in constraints:
            chain.constraint_envelope.active_constraints.append(constraint)
        await ops.trust_store.store_chain(chain)


# ===========================================================================
# Test Class 1: VerificationResult Reasoning Fields
# ===========================================================================


class TestVerificationResultReasoningFields:
    """VerificationResult must include reasoning_verified and reasoning_present fields."""

    def test_reasoning_verified_field_defaults_to_none(self):
        """reasoning_verified should default to None (not checked)."""
        result = VerificationResult(valid=True)
        assert result.reasoning_verified is None

    def test_reasoning_present_field_defaults_to_none(self):
        """reasoning_present should default to None (not checked)."""
        result = VerificationResult(valid=True)
        assert result.reasoning_present is None

    def test_reasoning_verified_can_be_set_true(self):
        """reasoning_verified can be explicitly set to True."""
        result = VerificationResult(valid=True, reasoning_verified=True)
        assert result.reasoning_verified is True

    def test_reasoning_verified_can_be_set_false(self):
        """reasoning_verified can be explicitly set to False."""
        result = VerificationResult(valid=True, reasoning_verified=False)
        assert result.reasoning_verified is False

    def test_reasoning_present_can_be_set_true(self):
        """reasoning_present can be explicitly set to True."""
        result = VerificationResult(valid=True, reasoning_present=True)
        assert result.reasoning_present is True

    def test_reasoning_present_can_be_set_false(self):
        """reasoning_present can be explicitly set to False."""
        result = VerificationResult(valid=True, reasoning_present=False)
        assert result.reasoning_present is False

    def test_both_fields_can_be_set_together(self):
        """Both reasoning fields can be set simultaneously."""
        result = VerificationResult(
            valid=True,
            reasoning_verified=True,
            reasoning_present=True,
        )
        assert result.reasoning_verified is True
        assert result.reasoning_present is True


# ===========================================================================
# Test Class 2: QUICK Verification - No Reasoning Checks
# ===========================================================================


class TestVerifyQuickNoReasoningChecks:
    """QUICK verification must NOT perform any reasoning checks."""

    @pytest.mark.asyncio
    async def test_quick_verify_no_reasoning_fields(self, ops):
        """QUICK verify should not populate reasoning fields."""
        await _establish_agent_with_capability(ops, "agent-q1", ["read_data"])
        result = await ops.verify(
            agent_id="agent-q1",
            action="read_data",
            level=VerificationLevel.QUICK,
        )
        assert result.valid is True
        assert result.reasoning_verified is None
        assert result.reasoning_present is None

    @pytest.mark.asyncio
    async def test_quick_verify_unchanged_with_reasoning_required_constraint(self, ops):
        """QUICK verify is unaffected even if REASONING_REQUIRED constraint exists."""
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-q2", ["analyze"], constraints=[reasoning_constraint])
        result = await ops.verify(
            agent_id="agent-q2",
            action="analyze",
            level=VerificationLevel.QUICK,
        )
        assert result.valid is True
        assert result.reasoning_verified is None
        assert result.reasoning_present is None


# ===========================================================================
# Test Class 3: STANDARD Verification - Reasoning Presence Check
# ===========================================================================


class TestVerifyStandardReasoningPresence:
    """STANDARD verification checks reasoning presence when REASONING_REQUIRED."""

    @pytest.mark.asyncio
    async def test_standard_no_reasoning_constraint_skips_check(self, ops):
        """Without REASONING_REQUIRED constraint, reasoning is not checked."""
        await _establish_agent_with_capability(ops, "agent-s1", ["read_data"])
        result = await ops.verify(
            agent_id="agent-s1",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        # When no REASONING_REQUIRED constraint, reasoning fields remain None
        assert result.reasoning_verified is None
        assert result.reasoning_present is None

    @pytest.mark.asyncio
    async def test_standard_reasoning_required_no_delegations_no_anchors(self, ops):
        """REASONING_REQUIRED with no delegations/anchors: reasoning_present is None."""
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-s2", ["read_data"], constraints=[reasoning_constraint])
        result = await ops.verify(
            agent_id="agent-s2",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        # No delegations/anchors to check, so reasoning_present reflects that
        assert result.reasoning_present is None

    @pytest.mark.asyncio
    async def test_standard_reasoning_required_delegation_with_trace(self, ops, reasoning_trace, keypair):
        """REASONING_REQUIRED + delegation with reasoning_trace: reasoning_present=True."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-s3", ["read_data"], constraints=[reasoning_constraint])
        # Add a delegation with reasoning trace to the chain
        chain = await ops.trust_store.get_chain("agent-s3")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-s3",
            task_id="task-001",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload", private_key),
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            reasoning_signature=sign_reasoning_trace(reasoning_trace, private_key),
        )
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-s3",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        assert result.reasoning_present is True

    @pytest.mark.asyncio
    async def test_standard_reasoning_required_delegation_missing_trace(self, ops, keypair):
        """REASONING_REQUIRED + delegation without reasoning_trace: reasoning_present=False."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-s4", ["read_data"], constraints=[reasoning_constraint])
        # Add a delegation WITHOUT reasoning trace
        chain = await ops.trust_store.get_chain("agent-s4")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-s4",
            task_id="task-002",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload", private_key),
            # No reasoning_trace, reasoning_trace_hash, or reasoning_signature
        )
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-s4",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        # Still valid (reasoning is not a hard failure), but presence is flagged
        assert result.valid is True
        assert result.reasoning_present is False

    @pytest.mark.asyncio
    async def test_standard_reasoning_required_audit_with_trace(self, ops, reasoning_trace, keypair):
        """REASONING_REQUIRED + audit anchor with reasoning_trace: reasoning_present=True."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_actions",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-s5", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-s5")
        anchor = AuditAnchor(
            id=f"aud-{uuid4()}",
            agent_id="agent-s5",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-placeholder",
            result=ActionResult.SUCCESS,
            signature=sign("test-payload", private_key),
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            reasoning_signature=sign_reasoning_trace(reasoning_trace, private_key),
        )
        chain.audit_anchors.append(anchor)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-s5",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        assert result.reasoning_present is True

    @pytest.mark.asyncio
    async def test_standard_reasoning_required_audit_missing_trace(self, ops, keypair):
        """REASONING_REQUIRED + audit anchor without trace: reasoning_present=False."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_actions",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-s6", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-s6")
        anchor = AuditAnchor(
            id=f"aud-{uuid4()}",
            agent_id="agent-s6",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-placeholder",
            result=ActionResult.SUCCESS,
            signature=sign("test-payload", private_key),
            # No reasoning trace
        )
        chain.audit_anchors.append(anchor)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-s6",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        assert result.reasoning_present is False


# ===========================================================================
# Test Class 4: FULL Verification - Reasoning Hash + Signature
# ===========================================================================


class TestVerifyFullReasoningCrypto:
    """FULL verification checks reasoning hash and signature cryptographically."""

    @pytest.mark.asyncio
    async def test_full_no_reasoning_constraint_skips_check(self, ops):
        """Without REASONING_REQUIRED, reasoning fields remain None even at FULL."""
        await _establish_agent_with_capability(ops, "agent-f1", ["read_data"])
        result = await ops.verify(
            agent_id="agent-f1",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        assert result.reasoning_verified is None
        assert result.reasoning_present is None

    @pytest.mark.asyncio
    async def test_full_delegation_valid_reasoning(self, ops, reasoning_trace, keypair):
        """FULL verify with valid reasoning hash + signature: reasoning_verified=True."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        # Establish delegator agent so _verify_signatures can resolve delegation chain
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-f2", ["read_data"], constraints=[reasoning_constraint])

        chain = await ops.trust_store.get_chain("agent-f2")
        del_id = f"del-{uuid4()}"
        delegation = DelegationRecord(
            id=del_id,
            delegator_id="agent-root",
            delegatee_id="agent-f2",
            task_id="task-003",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            reasoning_signature=sign(
                serialize_for_signing(
                    {
                        "parent_record_id": del_id,
                        "reasoning": reasoning_trace.to_signing_payload(),
                    }
                ),
                private_key,
            ),
        )
        # Sign the delegation with the authority key (same key used for all agents)
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)

        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-f2",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        assert result.reasoning_present is True
        assert result.reasoning_verified is True

    @pytest.mark.asyncio
    async def test_full_delegation_tampered_hash(self, ops, reasoning_trace, keypair):
        """FULL verify with wrong reasoning hash: reasoning_verified=False, valid=False."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-f3", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-f3")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-f3",
            task_id="task-004",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash="tampered_hash_value_abc123",  # Wrong hash
            reasoning_signature=sign_reasoning_trace(reasoning_trace, private_key),
        )
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-f3",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False
        assert result.reasoning_verified is False
        assert "reasoning" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_full_delegation_missing_signature_with_trace(self, ops, reasoning_trace, keypair):
        """FULL verify: trace present but signature missing: reasoning_verified=False."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-f4", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-f4")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-f4",
            task_id="task-005",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            reasoning_signature=None,  # Missing signature
        )
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-f4",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False
        assert result.reasoning_verified is False
        assert "reasoning" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_full_audit_valid_reasoning(self, ops, reasoning_trace, keypair):
        """FULL verify with valid audit anchor reasoning: reasoning_verified=True."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_actions",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-f5", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-f5")
        anchor_id = f"aud-{uuid4()}"
        anchor = AuditAnchor(
            id=anchor_id,
            agent_id="agent-f5",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-placeholder",
            result=ActionResult.SUCCESS,
            signature=sign("test-payload", private_key),
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            reasoning_signature=sign(
                serialize_for_signing(
                    {
                        "parent_record_id": anchor_id,
                        "reasoning": reasoning_trace.to_signing_payload(),
                    }
                ),
                private_key,
            ),
        )
        chain.audit_anchors.append(anchor)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-f5",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        assert result.reasoning_present is True
        assert result.reasoning_verified is True

    @pytest.mark.asyncio
    async def test_full_audit_tampered_hash(self, ops, reasoning_trace, keypair):
        """FULL verify with tampered audit reasoning hash: reasoning_verified=False."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_actions",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-f6", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-f6")
        anchor = AuditAnchor(
            id=f"aud-{uuid4()}",
            agent_id="agent-f6",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-placeholder",
            result=ActionResult.SUCCESS,
            signature=sign("test-payload", private_key),
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash="tampered_hash_value_xyz789",  # Wrong hash
            reasoning_signature=sign_reasoning_trace(reasoning_trace, private_key),
        )
        chain.audit_anchors.append(anchor)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-f6",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False
        assert result.reasoning_verified is False


# ===========================================================================
# Test Class 5: Backward Compatibility
# ===========================================================================


class TestVerifyBackwardCompatibility:
    """Verify without reasoning traces works identically to before."""

    @pytest.mark.asyncio
    async def test_existing_verify_standard_unchanged(self, ops):
        """Standard verify with no reasoning constraint returns same as before."""
        await _establish_agent_with_capability(ops, "agent-bc1", ["read_data"])
        result = await ops.verify(
            agent_id="agent-bc1",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        assert result.capability_used is not None
        # Reasoning fields should be None (not checked)
        assert result.reasoning_verified is None
        assert result.reasoning_present is None

    @pytest.mark.asyncio
    async def test_existing_verify_full_unchanged(self, ops):
        """Full verify with no reasoning constraint returns same as before."""
        await _establish_agent_with_capability(ops, "agent-bc2", ["read_data"])
        result = await ops.verify(
            agent_id="agent-bc2",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        # Reasoning fields should be None (not checked)
        assert result.reasoning_verified is None
        assert result.reasoning_present is None

    @pytest.mark.asyncio
    async def test_verify_nonexistent_agent_unchanged(self, ops):
        """Verify for nonexistent agent still returns valid=False."""
        result = await ops.verify(
            agent_id="agent-nonexistent",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is False
        assert "No trust chain found" in result.reason

    @pytest.mark.asyncio
    async def test_verify_no_capability_unchanged(self, ops):
        """Verify with wrong action still returns valid=False."""
        await _establish_agent_with_capability(ops, "agent-bc3", ["read_data"])
        result = await ops.verify(
            agent_id="agent-bc3",
            action="delete_all",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is False
        assert "No capability found" in result.reason


# ===========================================================================
# Test Class 6: Mixed Records - Some With, Some Without Reasoning
# ===========================================================================


class TestVerifyMixedReasoningRecords:
    """Verify handles chains with mixed reasoning trace presence."""

    @pytest.mark.asyncio
    async def test_standard_mixed_delegations_partial_reasoning(self, ops, reasoning_trace, keypair):
        """With some delegations having traces and some not: reasoning_present=False."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-m1", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-m1")

        # Delegation WITH reasoning trace
        del_with = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-m1",
            task_id="task-a",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload-a", private_key),
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            reasoning_signature=sign_reasoning_trace(reasoning_trace, private_key),
        )
        # Delegation WITHOUT reasoning trace
        del_without = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-m1",
            task_id="task-b",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload-b", private_key),
        )
        chain.delegations.extend([del_with, del_without])
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-m1",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        # At least one record is missing reasoning, so reasoning_present=False
        assert result.reasoning_present is False


# ===========================================================================
# Test Class 7: Bug Fix — FULL Level Must Cryptographically Verify Reasoning
#                Signatures (Not Just Check Presence)
# ===========================================================================


class TestVerifyFullReasoningSignatureCryptoVerification:
    """FULL verification must cryptographically verify reasoning_signature,
    not just check that it is non-None.

    An attacker attaching a random string as reasoning_signature MUST cause
    verification to fail with reasoning_verified=False.
    """

    @pytest.mark.asyncio
    async def test_full_delegation_invalid_reasoning_signature_fails(self, ops, reasoning_trace, keypair):
        """FULL verify: valid hash but INVALID (random) reasoning_signature must fail."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-sig1", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-sig1")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-sig1",
            task_id="task-sig-001",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            # ATTACK: random base64 string instead of real signature
            reasoning_signature="dGhpcyBpcyBhIGZha2Ugc2lnbmF0dXJl_INVALID_SIG",
        )
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-sig1",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False, (
            "FULL verification must FAIL when reasoning_signature is not a valid "
            "Ed25519 signature — presence-only check is insufficient"
        )
        assert result.reasoning_verified is False
        assert "reasoning" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_full_audit_invalid_reasoning_signature_fails(self, ops, reasoning_trace, keypair):
        """FULL verify: audit anchor with valid hash but INVALID reasoning sig must fail."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_actions",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-sig2", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-sig2")
        anchor = AuditAnchor(
            id=f"aud-{uuid4()}",
            agent_id="agent-sig2",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-placeholder",
            result=ActionResult.SUCCESS,
            signature=sign("test-payload", private_key),
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            # ATTACK: random string instead of real signature
            reasoning_signature="AAAA_not_a_real_signature_AAAA",
        )
        chain.audit_anchors.append(anchor)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-sig2",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False, (
            "FULL verification must FAIL when audit anchor reasoning_signature is not a valid Ed25519 signature"
        )
        assert result.reasoning_verified is False
        assert "reasoning" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_full_delegation_wrong_key_reasoning_signature_fails(self, ops, reasoning_trace, keypair):
        """FULL verify: reasoning signed with DIFFERENT key must fail verification."""
        private_key, _ = keypair
        # Generate a completely different keypair for the attacker
        attacker_private_key, _ = generate_keypair()

        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-sig3", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-sig3")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-sig3",
            task_id="task-sig-003",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            # Signed with attacker's key, not the authority's key
            reasoning_signature=sign_reasoning_trace(reasoning_trace, attacker_private_key),
        )
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-sig3",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False, (
            "FULL verification must FAIL when reasoning_signature was signed "
            "with a different key than the authority's public key"
        )
        assert result.reasoning_verified is False
        assert "reasoning" in result.reason.lower()


# ===========================================================================
# Test Class 8: Bug Fix — STANDARD Level Must Record Violations For Missing
#                Reasoning When REASONING_REQUIRED Is Active
# ===========================================================================


class TestVerifyStandardMissingReasoningViolations:
    """When REASONING_REQUIRED is active and reasoning is missing, the
    VerificationResult must include a non-blocking violation in the
    violations list. The result should still be valid=True (non-blocking),
    but the violation must be recorded for audit/compliance purposes.
    """

    @pytest.mark.asyncio
    async def test_standard_missing_reasoning_records_violation(self, ops, keypair):
        """Missing reasoning on delegation with REASONING_REQUIRED must add violation."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-v1", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-v1")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-v1",
            task_id="task-v-001",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload", private_key),
            # No reasoning_trace, no reasoning_trace_hash, no reasoning_signature
        )
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-v1",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        # Still valid (non-blocking finding)
        assert result.valid is True
        assert result.reasoning_present is False
        # But violations list must contain the missing reasoning entry
        assert len(result.violations) > 0, (
            "STANDARD verification must record a violation when REASONING_REQUIRED is active but reasoning is missing"
        )
        violation = result.violations[0]
        assert violation["constraint_type"] == "reasoning_required"
        assert violation["severity"] == "warning"
        assert "reasoning" in violation["reason"].lower()

    @pytest.mark.asyncio
    async def test_standard_missing_reasoning_on_audit_records_violation(self, ops, keypair):
        """Missing reasoning on audit anchor with REASONING_REQUIRED must add violation."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_actions",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-v2", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-v2")
        anchor = AuditAnchor(
            id=f"aud-{uuid4()}",
            agent_id="agent-v2",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-placeholder",
            result=ActionResult.SUCCESS,
            signature=sign("test-payload", private_key),
            # No reasoning trace
        )
        chain.audit_anchors.append(anchor)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-v2",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        assert result.reasoning_present is False
        assert len(result.violations) > 0, (
            "STANDARD verification must record a violation when "
            "REASONING_REQUIRED is active but reasoning is missing on audit records"
        )
        violation = result.violations[0]
        assert violation["constraint_type"] == "reasoning_required"
        assert violation["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_standard_reasoning_present_no_violations(self, ops, reasoning_trace, keypair):
        """When reasoning IS present, no reasoning violations should be added."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-v3", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-v3")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-v3",
            task_id="task-v-003",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload", private_key),
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            reasoning_signature=sign_reasoning_trace(reasoning_trace, private_key),
        )
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-v3",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        assert result.reasoning_present is True
        # No violations should be present for reasoning
        reasoning_violations = [v for v in result.violations if v.get("constraint_type") == "reasoning_required"]
        assert len(reasoning_violations) == 0

    @pytest.mark.asyncio
    async def test_standard_no_reasoning_constraint_no_violations(self, ops):
        """Without REASONING_REQUIRED constraint, no reasoning violations."""
        await _establish_agent_with_capability(ops, "agent-v4", ["read_data"])
        result = await ops.verify(
            agent_id="agent-v4",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        reasoning_violations = [v for v in result.violations if v.get("constraint_type") == "reasoning_required"]
        assert len(reasoning_violations) == 0


# ===========================================================================
# Test Class 9: Decision 3 — FULL Level Hard Failure for REASONING_REQUIRED
#                + Missing Trace (v2.2 Spec)
# ===========================================================================


class TestVerifyFullReasoningRequiredHardFailure:
    """At FULL verification level, if REASONING_REQUIRED constraint is active
    and no reasoning trace is present, verification MUST fail (hard failure).

    This differs from STANDARD level where the same scenario produces a
    valid=True result with a warning violation.

    Verification gradient (REASONING_REQUIRED + no trace):
    - QUICK:    Ignored
    - STANDARD: Valid with warning
    - FULL:     **Invalid (hard failure)**
    """

    @pytest.mark.asyncio
    async def test_full_reasoning_required_missing_trace_hard_failure(self, ops, keypair):
        """FULL + REASONING_REQUIRED + no trace = failure."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-hf1", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-hf1")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-hf1",
            task_id="task-hf-001",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload", private_key),
            # No reasoning_trace, no reasoning_trace_hash, no reasoning_signature
        )
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-hf1",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False, (
            "FULL verification MUST fail when REASONING_REQUIRED is active and no reasoning trace is present"
        )
        assert result.reasoning_present is False
        assert result.reasoning_verified is False
        assert "REASONING_REQUIRED" in result.reason

    @pytest.mark.asyncio
    async def test_full_reasoning_required_with_valid_trace_succeeds(self, ops, reasoning_trace, keypair):
        """FULL + REASONING_REQUIRED + valid trace = success."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-hf2", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-hf2")
        del_id = f"del-{uuid4()}"
        delegation = DelegationRecord(
            id=del_id,
            delegator_id="agent-root",
            delegatee_id="agent-hf2",
            task_id="task-hf-002",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            reasoning_signature=sign(
                serialize_for_signing(
                    {
                        "parent_record_id": del_id,
                        "reasoning": reasoning_trace.to_signing_payload(),
                    }
                ),
                private_key,
            ),
        )
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-hf2",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        assert result.reasoning_present is True
        assert result.reasoning_verified is True

    @pytest.mark.asyncio
    async def test_standard_reasoning_required_missing_trace_still_valid(self, ops, keypair):
        """STANDARD + REASONING_REQUIRED + no trace = valid with warning (unchanged)."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-hf3", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-hf3")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-hf3",
            task_id="task-hf-003",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload", private_key),
            # No reasoning trace
        )
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-hf3",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True, (
            "STANDARD verification must remain valid (advisory) when REASONING_REQUIRED + no trace"
        )
        assert result.reasoning_present is False
        # Warning violation must be recorded
        assert len(result.violations) > 0
        violation = result.violations[0]
        assert violation["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_full_reasoning_required_missing_trace_on_audit_anchor(self, ops, keypair):
        """FULL + REASONING_REQUIRED + no trace on audit anchor = failure."""
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_actions",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-hf4", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-hf4")
        anchor = AuditAnchor(
            id=f"aud-{uuid4()}",
            agent_id="agent-hf4",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-placeholder",
            result=ActionResult.SUCCESS,
            signature=sign("test-payload", private_key),
            # No reasoning trace
        )
        chain.audit_anchors.append(anchor)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-hf4",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False, (
            "FULL verification MUST fail when REASONING_REQUIRED is active "
            "and no reasoning trace is present on audit anchors"
        )
        assert result.reasoning_present is False
        assert result.reasoning_verified is False
        assert "REASONING_REQUIRED" in result.reason

    @pytest.mark.asyncio
    async def test_full_reasoning_required_mixed_records_hard_failure(self, ops, reasoning_trace, keypair):
        """FULL + REASONING_REQUIRED + mixed records (some with, some without) = failure.

        When some delegations have reasoning traces and some do not, the chain
        as a whole has reasoning_present=False, triggering the hard failure.
        """
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-hf5", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-hf5")

        # Delegation WITH reasoning trace
        del_id_with = f"del-{uuid4()}"
        del_with = DelegationRecord(
            id=del_id_with,
            delegator_id="agent-root",
            delegatee_id="agent-hf5",
            task_id="task-hf-005a",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            reasoning_signature=sign(
                serialize_for_signing(
                    {
                        "parent_record_id": del_id_with,
                        "reasoning": reasoning_trace.to_signing_payload(),
                    }
                ),
                private_key,
            ),
        )
        del_payload = serialize_for_signing(del_with.to_signing_payload())
        del_with.signature = sign(del_payload, private_key)

        # Delegation WITHOUT reasoning trace
        del_without = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-hf5",
            task_id="task-hf-005b",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload", private_key),
        )

        chain.delegations.extend([del_with, del_without])
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-hf5",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False, (
            "FULL verification MUST fail when REASONING_REQUIRED is active "
            "and ANY record is missing reasoning (mixed records)"
        )
        assert result.reasoning_present is False

    @pytest.mark.asyncio
    async def test_full_trace_present_but_hash_none_fails(self, ops, reasoning_trace, keypair):
        """FULL verify: reasoning_trace present but reasoning_trace_hash=None must fail.

        This simulates a record where someone forgot to compute the hash or
        a record from a pre-v2.2 SDK that had reasoning but no hash binding.
        """
        private_key, _ = keypair
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-hf6", ["read_data"], constraints=[reasoning_constraint])
        chain = await ops.trust_store.get_chain("agent-hf6")
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-hf6",
            task_id="task-hf-006",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=None,  # Hash not computed (inconsistent state)
            reasoning_signature=sign_reasoning_trace(reasoning_trace, private_key),
        )
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-hf6",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False, (
            "FULL verification must fail when reasoning_trace is present "
            "but reasoning_trace_hash was never computed (None)"
        )
        assert result.reasoning_verified is False
