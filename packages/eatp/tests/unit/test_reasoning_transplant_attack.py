# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for C-1 CRITICAL: Reasoning trace signature bound to parent record.

Verifies that reasoning signatures are bound to their parent record ID,
preventing transplant attacks where a valid reasoning signature from one
delegation/audit is reused on a different delegation/audit.

Tests cover:
1. crypto.py: sign_reasoning_trace() and verify_reasoning_signature() with context_id
2. operations/__init__.py: delegate() binds reasoning signature to delegation.id
3. operations/__init__.py: audit() binds reasoning signature to anchor.id
4. operations/__init__.py: _verify_reasoning_traces() verifies bound signatures
5. Transplant attack detection: signature from record A fails on record B

Written BEFORE implementation (TDD). Tests define the contract.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import uuid4

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
    verify_reasoning_signature,
    verify_signature,
)
from eatp.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace
from eatp.store.memory import InMemoryTrustStore


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
    if constraints:
        chain = await ops.trust_store.get_chain(agent_id)
        for constraint in constraints:
            chain.constraint_envelope.active_constraints.append(constraint)
        await ops.trust_store.store_chain(chain)


# ===========================================================================
# Test Class 1: sign_reasoning_trace with context_id
# ===========================================================================


class TestSignReasoningTraceWithContextId:
    """sign_reasoning_trace must support optional context_id parameter."""

    def test_sign_with_context_id_produces_different_signature(self, reasoning_trace, keypair):
        """Signing with context_id must produce a different signature than without."""
        private_key, _ = keypair
        sig_without = sign_reasoning_trace(reasoning_trace, private_key)
        sig_with = sign_reasoning_trace(reasoning_trace, private_key, context_id="del-123")
        assert sig_without != sig_with

    def test_sign_with_different_context_ids_produces_different_signatures(self, reasoning_trace, keypair):
        """Different context_ids must produce different signatures."""
        private_key, _ = keypair
        sig_a = sign_reasoning_trace(reasoning_trace, private_key, context_id="del-aaa")
        sig_b = sign_reasoning_trace(reasoning_trace, private_key, context_id="del-bbb")
        assert sig_a != sig_b

    def test_sign_with_none_context_id_matches_no_context(self, reasoning_trace, keypair):
        """context_id=None must produce the same signature as no context_id."""
        private_key, _ = keypair
        sig_default = sign_reasoning_trace(reasoning_trace, private_key)
        sig_none = sign_reasoning_trace(reasoning_trace, private_key, context_id=None)
        assert sig_default == sig_none

    def test_sign_with_context_id_is_deterministic(self, reasoning_trace, keypair):
        """Same trace + same key + same context_id must produce the same signature."""
        private_key, _ = keypair
        sig1 = sign_reasoning_trace(reasoning_trace, private_key, context_id="del-xyz")
        sig2 = sign_reasoning_trace(reasoning_trace, private_key, context_id="del-xyz")
        assert sig1 == sig2


# ===========================================================================
# Test Class 2: verify_reasoning_signature with context_id
# ===========================================================================


class TestVerifyReasoningSignatureWithContextId:
    """verify_reasoning_signature must support optional context_id parameter."""

    def test_verify_with_matching_context_id_succeeds(self, reasoning_trace, keypair):
        """Signature created with context_id must verify with the same context_id."""
        private_key, public_key = keypair
        sig = sign_reasoning_trace(reasoning_trace, private_key, context_id="del-456")
        assert verify_reasoning_signature(reasoning_trace, sig, public_key, context_id="del-456") is True

    def test_verify_with_wrong_context_id_fails(self, reasoning_trace, keypair):
        """Signature created with one context_id must fail with a different context_id."""
        private_key, public_key = keypair
        sig = sign_reasoning_trace(reasoning_trace, private_key, context_id="del-456")
        assert verify_reasoning_signature(reasoning_trace, sig, public_key, context_id="del-789") is False

    def test_verify_context_sig_without_context_fails(self, reasoning_trace, keypair):
        """Signature created WITH context_id must fail verification WITHOUT context_id."""
        private_key, public_key = keypair
        sig = sign_reasoning_trace(reasoning_trace, private_key, context_id="del-456")
        assert verify_reasoning_signature(reasoning_trace, sig, public_key) is False

    def test_verify_no_context_sig_with_context_fails(self, reasoning_trace, keypair):
        """Signature created WITHOUT context_id must fail verification WITH context_id."""
        private_key, public_key = keypair
        sig = sign_reasoning_trace(reasoning_trace, private_key)
        assert verify_reasoning_signature(reasoning_trace, sig, public_key, context_id="del-456") is False

    def test_verify_none_context_matches_no_context(self, reasoning_trace, keypair):
        """context_id=None on verify must match no-context signing."""
        private_key, public_key = keypair
        sig = sign_reasoning_trace(reasoning_trace, private_key)
        assert verify_reasoning_signature(reasoning_trace, sig, public_key, context_id=None) is True


# ===========================================================================
# Test Class 3: delegate() binds reasoning signature to delegation.id
# ===========================================================================


class TestDelegateBindsReasoningSignature:
    """delegate() must bind the reasoning signature to the delegation record ID."""

    @pytest.mark.asyncio
    async def test_delegate_reasoning_signature_bound_to_delegation_id(self, ops, reasoning_trace, keypair):
        """The reasoning signature on a delegation must be bound to delegation.id."""
        private_key, public_key = keypair

        await _establish_agent_with_capability(ops, "agent-delegator", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-delegatee", ["read_data"])

        delegation = await ops.delegate(
            delegator_id="agent-delegator",
            delegatee_id="agent-delegatee",
            task_id="task-bind-001",
            capabilities=["read_data"],
            reasoning_trace=reasoning_trace,
        )

        # The signature must verify when bound to the delegation's own ID
        bound_payload = serialize_for_signing(
            {
                "parent_record_id": delegation.id,
                "reasoning": reasoning_trace.to_signing_payload(),
            }
        )
        assert verify_signature(bound_payload, delegation.reasoning_signature, public_key) is True

        # The signature must NOT verify against the unbounded trace payload
        unbound_payload = serialize_for_signing(reasoning_trace.to_signing_payload())
        assert verify_signature(unbound_payload, delegation.reasoning_signature, public_key) is False


# ===========================================================================
# Test Class 4: audit() binds reasoning signature to anchor.id
# ===========================================================================


class TestAuditBindsReasoningSignature:
    """audit() must bind the reasoning signature to the audit anchor ID."""

    @pytest.mark.asyncio
    async def test_audit_reasoning_signature_bound_to_anchor_id(self, ops, reasoning_trace, keypair):
        """The reasoning signature on an audit anchor must be bound to anchor.id."""
        private_key, public_key = keypair

        await _establish_agent_with_capability(ops, "agent-audited", ["read_data"])

        anchor = await ops.audit(
            agent_id="agent-audited",
            action="read_data",
            resource="test-resource",
            result=ActionResult.SUCCESS,
            reasoning_trace=reasoning_trace,
        )

        # The signature must verify when bound to the anchor's own ID
        bound_payload = serialize_for_signing(
            {
                "parent_record_id": anchor.id,
                "reasoning": reasoning_trace.to_signing_payload(),
            }
        )
        assert verify_signature(bound_payload, anchor.reasoning_signature, public_key) is True

        # The signature must NOT verify against the unbounded trace payload
        unbound_payload = serialize_for_signing(reasoning_trace.to_signing_payload())
        assert verify_signature(unbound_payload, anchor.reasoning_signature, public_key) is False


# ===========================================================================
# Test Class 5: _verify_reasoning_traces detects transplant attacks
# ===========================================================================


class TestVerifyDetectsTransplantAttack:
    """FULL verification must detect reasoning signature transplant attacks."""

    @pytest.mark.asyncio
    async def test_transplanted_delegation_reasoning_signature_fails_verification(self, ops, reasoning_trace, keypair):
        """A reasoning signature from delegation A must fail on delegation B."""
        private_key, public_key = keypair

        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(ops, "agent-victim", ["read_data"], constraints=[reasoning_constraint])

        # Create a legitimate delegation to get a valid reasoning signature
        legit_delegation = await ops.delegate(
            delegator_id="agent-root",
            delegatee_id="agent-victim",
            task_id="task-legit-001",
            capabilities=["read_data"],
            reasoning_trace=reasoning_trace,
        )
        stolen_reasoning_signature = legit_delegation.reasoning_signature

        # Now create a second delegation and transplant the reasoning signature
        chain = await ops.trust_store.get_chain("agent-victim")
        transplant_delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-victim",
            task_id="task-transplant",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            # ATTACK: transplanted signature from a different delegation
            reasoning_signature=stolen_reasoning_signature,
        )
        del_payload = serialize_for_signing(transplant_delegation.to_signing_payload())
        transplant_delegation.signature = sign(del_payload, private_key)
        chain.delegations.append(transplant_delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-victim",
            action="read_data",
            level=VerificationLevel.FULL,
        )

        # The transplanted signature must be detected and rejected
        assert result.valid is False, (
            "FULL verification must FAIL when a reasoning signature is transplanted from one delegation to another"
        )
        assert result.reasoning_verified is False

    @pytest.mark.asyncio
    async def test_transplanted_audit_reasoning_signature_fails_verification(self, ops, reasoning_trace, keypair):
        """A reasoning signature from audit anchor A must fail on audit anchor B."""
        private_key, public_key = keypair

        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_actions",
            source="test",
        )
        await _establish_agent_with_capability(
            ops, "agent-audit-victim", ["read_data"], constraints=[reasoning_constraint]
        )

        # Create a legitimate audit anchor to get a valid reasoning signature
        legit_anchor = await ops.audit(
            agent_id="agent-audit-victim",
            action="read_data",
            resource="resource-1",
            result=ActionResult.SUCCESS,
            reasoning_trace=reasoning_trace,
        )
        stolen_reasoning_signature = legit_anchor.reasoning_signature

        # Create a second audit anchor and transplant the reasoning signature
        chain = await ops.trust_store.get_chain("agent-audit-victim")
        transplant_anchor = AuditAnchor(
            id=f"aud-{uuid4()}",
            agent_id="agent-audit-victim",
            action="read_data",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="hash-placeholder",
            result=ActionResult.SUCCESS,
            signature=sign("test-payload", private_key),
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            # ATTACK: transplanted signature from a different audit anchor
            reasoning_signature=stolen_reasoning_signature,
        )
        chain.audit_anchors.append(transplant_anchor)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-audit-victim",
            action="read_data",
            level=VerificationLevel.FULL,
        )

        assert result.valid is False, (
            "FULL verification must FAIL when a reasoning signature is transplanted from one audit anchor to another"
        )
        assert result.reasoning_verified is False

    @pytest.mark.asyncio
    async def test_legitimate_bound_delegation_reasoning_passes(self, ops, reasoning_trace, keypair):
        """A properly bound reasoning signature on a delegation must pass FULL verification."""
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_delegations",
            source="test",
        )
        await _establish_agent_with_capability(ops, "agent-root", ["analyze"])
        await _establish_agent_with_capability(ops, "agent-legit", ["analyze"], constraints=[reasoning_constraint])

        await ops.delegate(
            delegator_id="agent-root",
            delegatee_id="agent-legit",
            task_id="task-legit-002",
            capabilities=["analyze"],
            reasoning_trace=reasoning_trace,
        )

        result = await ops.verify(
            agent_id="agent-legit",
            action="analyze",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        assert result.reasoning_verified is True

    @pytest.mark.asyncio
    async def test_legitimate_bound_audit_reasoning_passes(self, ops, reasoning_trace, keypair):
        """A properly bound reasoning signature on an audit anchor must pass FULL verification."""
        reasoning_constraint = Constraint(
            id=f"con-{uuid4()}",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="all_actions",
            source="test",
        )
        await _establish_agent_with_capability(
            ops, "agent-audit-legit", ["analyze"], constraints=[reasoning_constraint]
        )

        await ops.audit(
            agent_id="agent-audit-legit",
            action="analyze",
            resource="test-resource",
            result=ActionResult.SUCCESS,
            reasoning_trace=reasoning_trace,
        )

        result = await ops.verify(
            agent_id="agent-audit-legit",
            action="analyze",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        assert result.reasoning_verified is True
