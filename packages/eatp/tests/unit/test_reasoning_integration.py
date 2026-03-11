# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Integration and adversarial tests for the EATP Reasoning Trace extension (TODO-022).

Covers:
- Part 1: End-to-end flows — create chain, delegate with reasoning, audit
  with reasoning, verify at all levels, score with reasoning coverage.
- Part 2: Adversarial scenarios — tampered hashes, wrong keys, null fields,
  extremely long content, unicode/special chars, concurrent verification.
- Part 3: Backward compatibility — legacy chains (no reasoning), old-format
  deserialization, scoring unchanged without REASONING_REQUIRED.
- Part 4: Property-based tests (hypothesis) — roundtrip serialization,
  hash mutation sensitivity, confidentiality ordering totality.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
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
    verify_reasoning_signature,
    verify_signature,
)
from eatp.enforce.shadow import ShadowEnforcer
from eatp.enforce.strict import StrictEnforcer, Verdict
from eatp.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace
from eatp.scoring import compute_trust_score, generate_trust_report
from eatp.store.memory import InMemoryTrustStore

logger = logging.getLogger(__name__)

FIXED_TIMESTAMP = datetime(2026, 3, 11, 14, 30, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Real In-Memory Authority Registry (same pattern as test_verify_reasoning.py)
# ---------------------------------------------------------------------------


class SimpleAuthorityRegistry:
    """Real in-memory authority registry for integration tests."""

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
# Shared Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


@pytest.fixture
def keypair_alt():
    """Generate a second (different) Ed25519 keypair for adversarial tests."""
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
        decision="Approve data access for analysis",
        rationale="Agent has valid capability and passes all constraint checks",
        confidentiality=ConfidentialityLevel.RESTRICTED,
        timestamp=FIXED_TIMESTAMP,
        alternatives_considered=["Deny access", "Request additional review"],
        evidence=[{"type": "capability_check", "result": "pass"}],
        methodology="risk_assessment",
        confidence=0.95,
    )


def _make_reasoning_constraint() -> Constraint:
    """Create a REASONING_REQUIRED constraint."""
    return Constraint(
        id=f"con-{uuid4()}",
        constraint_type=ConstraintType.REASONING_REQUIRED,
        value="all_delegations_and_audits",
        source="test-policy",
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


def _make_delegation_with_reasoning(
    delegatee_id: str,
    reasoning_trace: ReasoningTrace,
    private_key: str,
    deleg_id: Optional[str] = None,
    delegator_id: str = "agent-root",
) -> DelegationRecord:
    """Create a delegation record with properly signed reasoning trace."""
    deleg_id = deleg_id or f"del-{uuid4()}"
    delegation = DelegationRecord(
        id=deleg_id,
        delegator_id=delegator_id,
        delegatee_id=delegatee_id,
        task_id=f"task-{uuid4()}",
        capabilities_delegated=["read_data"],
        constraint_subset=[],
        delegated_at=datetime.now(timezone.utc),
        signature="placeholder",
        reasoning_trace=reasoning_trace,
        reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
        reasoning_signature=sign_reasoning_trace(
            reasoning_trace, private_key, context_id=deleg_id
        ),
    )
    del_payload = serialize_for_signing(delegation.to_signing_payload())
    delegation.signature = sign(del_payload, private_key)
    return delegation


def _make_audit_anchor_with_reasoning(
    agent_id: str,
    reasoning_trace: ReasoningTrace,
    private_key: str,
    anchor_id: Optional[str] = None,
) -> AuditAnchor:
    """Create an audit anchor with properly signed reasoning trace."""
    anchor_id = anchor_id or f"aud-{uuid4()}"
    return AuditAnchor(
        id=anchor_id,
        agent_id=agent_id,
        action="read_data",
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash="hash-placeholder",
        result=ActionResult.SUCCESS,
        signature=sign("audit-payload", private_key),
        reasoning_trace=reasoning_trace,
        reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
        reasoning_signature=sign_reasoning_trace(
            reasoning_trace, private_key, context_id=anchor_id
        ),
    )


# ===========================================================================
# Part 1: End-to-End Flow Tests
# ===========================================================================


class TestReasoningEndToEndFlow:
    """Test full lifecycle: create chain -> delegate with reasoning -> audit
    with reasoning -> verify -> score."""

    @pytest.mark.asyncio
    async def test_delegate_with_reasoning_then_verify_full(
        self, ops, reasoning_trace, keypair
    ):
        """End-to-end: establish agent, delegate with reasoning, verify at FULL
        level. Reasoning should be present and verified."""
        private_key, _ = keypair
        reasoning_constraint = _make_reasoning_constraint()

        # Establish delegator and delegatee agents
        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(
            ops, "agent-e2e-1", ["read_data"], constraints=[reasoning_constraint]
        )

        # Add delegation with reasoning trace to the chain
        chain = await ops.trust_store.get_chain("agent-e2e-1")
        delegation = _make_delegation_with_reasoning(
            "agent-e2e-1", reasoning_trace, private_key
        )
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        # Verify at FULL level
        result = await ops.verify(
            agent_id="agent-e2e-1",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        assert result.reasoning_present is True
        assert result.reasoning_verified is True

    @pytest.mark.asyncio
    async def test_delegate_then_audit_with_reasoning_then_verify(
        self, ops, reasoning_trace, keypair
    ):
        """Full flow with both delegation reasoning and audit reasoning."""
        private_key, _ = keypair
        reasoning_constraint = _make_reasoning_constraint()

        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(
            ops, "agent-e2e-2", ["read_data"], constraints=[reasoning_constraint]
        )

        chain = await ops.trust_store.get_chain("agent-e2e-2")

        # Add delegation with reasoning
        delegation = _make_delegation_with_reasoning(
            "agent-e2e-2", reasoning_trace, private_key
        )
        chain.delegations.append(delegation)

        # Add audit anchor with reasoning
        audit_trace = ReasoningTrace(
            decision="Execute data analysis",
            rationale="Delegated task requires immediate processing",
            confidentiality=ConfidentialityLevel.CONFIDENTIAL,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.88,
        )
        anchor = _make_audit_anchor_with_reasoning(
            "agent-e2e-2", audit_trace, private_key
        )
        chain.audit_anchors.append(anchor)
        await ops.trust_store.store_chain(chain)

        # Verify at FULL level
        result = await ops.verify(
            agent_id="agent-e2e-2",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        assert result.reasoning_present is True
        assert result.reasoning_verified is True

    @pytest.mark.asyncio
    async def test_chain_with_mixed_reasoning_verification(
        self, ops, reasoning_trace, keypair
    ):
        """Some delegations with reasoning, some without. STANDARD verify should
        report reasoning_present=False when any record is missing a trace."""
        private_key, _ = keypair
        reasoning_constraint = _make_reasoning_constraint()

        await _establish_agent_with_capability(
            ops, "agent-e2e-3", ["read_data"], constraints=[reasoning_constraint]
        )

        chain = await ops.trust_store.get_chain("agent-e2e-3")

        # Delegation WITH reasoning
        del_with = _make_delegation_with_reasoning(
            "agent-e2e-3", reasoning_trace, private_key, deleg_id="del-with"
        )
        chain.delegations.append(del_with)

        # Delegation WITHOUT reasoning
        del_without = DelegationRecord(
            id="del-without",
            delegator_id="agent-root",
            delegatee_id="agent-e2e-3",
            task_id="task-no-reasoning",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload", private_key),
        )
        chain.delegations.append(del_without)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-e2e-3",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result.valid is True
        # Mixed: at least one record is missing reasoning
        assert result.reasoning_present is False

    @pytest.mark.asyncio
    async def test_scoring_reflects_reasoning_coverage(
        self, ops, reasoning_trace, keypair
    ):
        """Chain with REASONING_REQUIRED constraint: score includes
        reasoning_coverage factor proportional to coverage."""
        private_key, _ = keypair
        reasoning_constraint = _make_reasoning_constraint()

        await _establish_agent_with_capability(
            ops, "agent-e2e-4", ["read_data"], constraints=[reasoning_constraint]
        )

        chain = await ops.trust_store.get_chain("agent-e2e-4")

        # Add 2 delegations with reasoning, 1 without -> 67% coverage
        for i in range(2):
            del_with = _make_delegation_with_reasoning(
                "agent-e2e-4",
                reasoning_trace,
                private_key,
                deleg_id=f"del-scored-{i}",
            )
            chain.delegations.append(del_with)

        del_without = DelegationRecord(
            id="del-scored-no-trace",
            delegator_id="agent-root",
            delegatee_id="agent-e2e-4",
            task_id="task-no-reasoning",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test-payload", private_key),
        )
        chain.delegations.append(del_without)
        await ops.trust_store.store_chain(chain)

        score = await compute_trust_score("agent-e2e-4", ops.trust_store)
        assert "reasoning_coverage" in score.breakdown
        # 2/3 = ~67% coverage, weight = 5 -> contribution ~3.33
        assert 0 < score.breakdown["reasoning_coverage"] < 5.0

        # Compare with a fully covered agent
        await _establish_agent_with_capability(
            ops, "agent-e2e-4-full", ["read_data"], constraints=[reasoning_constraint]
        )
        chain_full = await ops.trust_store.get_chain("agent-e2e-4-full")
        del_full = _make_delegation_with_reasoning(
            "agent-e2e-4-full",
            reasoning_trace,
            private_key,
            deleg_id="del-scored-full",
        )
        chain_full.delegations.append(del_full)
        await ops.trust_store.store_chain(chain_full)

        score_full = await compute_trust_score("agent-e2e-4-full", ops.trust_store)
        assert (
            score_full.breakdown["reasoning_coverage"]
            > score.breakdown["reasoning_coverage"]
        )

    @pytest.mark.asyncio
    async def test_full_lifecycle_establish_delegate_audit_verify_score_report(
        self, ops, reasoning_trace, keypair
    ):
        """Complete lifecycle: establish -> delegate -> audit -> verify -> score -> report."""
        private_key, _ = keypair
        reasoning_constraint = _make_reasoning_constraint()

        # Step 1: Establish
        await _establish_agent_with_capability(ops, "agent-root", ["analyze"])
        await _establish_agent_with_capability(
            ops, "agent-lifecycle", ["analyze"], constraints=[reasoning_constraint]
        )

        # Step 2: Delegate with reasoning
        chain = await ops.trust_store.get_chain("agent-lifecycle")
        delegation = _make_delegation_with_reasoning(
            "agent-lifecycle", reasoning_trace, private_key
        )
        delegation.capabilities_delegated = ["analyze"]
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)
        chain.delegations.append(delegation)

        # Step 3: Audit with reasoning
        audit_trace = ReasoningTrace(
            decision="Run financial analysis",
            rationale="Quarterly report deadline approaching",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=FIXED_TIMESTAMP,
            methodology="cost_benefit",
            confidence=0.92,
        )
        anchor = _make_audit_anchor_with_reasoning(
            "agent-lifecycle", audit_trace, private_key
        )
        anchor.action = "analyze"
        chain.audit_anchors.append(anchor)
        await ops.trust_store.store_chain(chain)

        # Step 4: Verify
        result = await ops.verify(
            agent_id="agent-lifecycle",
            action="analyze",
            level=VerificationLevel.FULL,
        )
        assert result.valid is True
        assert result.reasoning_present is True
        assert result.reasoning_verified is True

        # Step 5: Score
        score = await compute_trust_score("agent-lifecycle", ops.trust_store)
        assert 0 <= score.score <= 100
        assert "reasoning_coverage" in score.breakdown
        assert score.breakdown["reasoning_coverage"] == 5.0  # 100% coverage

        # Step 6: Report
        report = await generate_trust_report("agent-lifecycle", ops.trust_store)
        # With full reasoning coverage, no reasoning risk indicators should appear
        reasoning_risks = [
            ri for ri in report.risk_indicators if "reasoning" in ri.lower()
        ]
        assert len(reasoning_risks) == 0


# ===========================================================================
# Part 2: Adversarial Tests
# ===========================================================================


class TestReasoningAdversarial:
    """Adversarial scenarios: tampered data, wrong keys, edge cases."""

    @pytest.mark.asyncio
    async def test_tampered_reasoning_hash_detected(
        self, ops, reasoning_trace, keypair
    ):
        """Modify reasoning_trace after signing: verify should catch hash mismatch."""
        private_key, _ = keypair
        reasoning_constraint = _make_reasoning_constraint()

        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(
            ops, "agent-adv-1", ["read_data"], constraints=[reasoning_constraint]
        )

        chain = await ops.trust_store.get_chain("agent-adv-1")

        # Create delegation with valid reasoning
        delegation = _make_delegation_with_reasoning(
            "agent-adv-1", reasoning_trace, private_key
        )

        # Tamper: change the stored hash to a wrong value
        delegation.reasoning_trace_hash = "tampered_hash_0000000000000000"

        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-adv-1",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result.valid is False
        assert result.reasoning_verified is False
        assert "reasoning" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_wrong_key_reasoning_signature_detected(
        self, ops, reasoning_trace, keypair, keypair_alt
    ):
        """Sign reasoning with one key, verify with authority's key:
        should detect signature mismatch."""
        private_key, _ = keypair
        alt_private_key, _ = keypair_alt
        reasoning_constraint = _make_reasoning_constraint()

        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(
            ops, "agent-adv-2", ["read_data"], constraints=[reasoning_constraint]
        )

        chain = await ops.trust_store.get_chain("agent-adv-2")

        # Create delegation: correct hash but wrong key for reasoning signature
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id="agent-root",
            delegatee_id="agent-adv-2",
            task_id="task-wrong-key",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="placeholder",
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=hash_reasoning_trace(reasoning_trace),
            # Sign reasoning with WRONG key
            reasoning_signature=sign_reasoning_trace(reasoning_trace, alt_private_key),
        )
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)

        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-adv-2",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        # The reasoning signature was signed with wrong key, so verification
        # should either fail (valid=False) or mark reasoning_verified=False
        assert result.reasoning_verified is False

    @pytest.mark.asyncio
    async def test_null_reasoning_fields_handled_gracefully(self, ops, keypair):
        """All optional reasoning fields set to None: should not crash."""
        private_key, _ = keypair

        minimal_trace = ReasoningTrace(
            decision="Approve",
            rationale="Valid",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=[],
            evidence=[],
            methodology=None,
            confidence=None,
        )

        # Verify hashing and signing work with minimal trace
        trace_hash = hash_reasoning_trace(minimal_trace)
        assert len(trace_hash) == 64  # SHA-256 hex

        trace_sig = sign_reasoning_trace(minimal_trace, private_key)
        assert len(trace_sig) > 0

        _, public_key = keypair
        assert verify_reasoning_signature(minimal_trace, trace_sig, public_key) is True

    @pytest.mark.asyncio
    async def test_extremely_long_reasoning_content(self, keypair):
        """Long (but within-limit) decision/rationale: should hash and sign correctly."""
        private_key, public_key = keypair

        long_decision = "D" * 9_999  # Just under 10K limit
        long_rationale = "R" * 49_999  # Just under 50K limit

        trace = ReasoningTrace(
            decision=long_decision,
            rationale=long_rationale,
            confidentiality=ConfidentialityLevel.SECRET,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=["alt_" + str(i) for i in range(100)],
            confidence=0.5,
        )

        trace_hash = hash_reasoning_trace(trace)
        assert len(trace_hash) == 64

        trace_sig = sign_reasoning_trace(trace, private_key)
        assert verify_reasoning_signature(trace, trace_sig, public_key) is True

        # Verify roundtrip serialization
        d = trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        assert restored.decision == long_decision
        assert restored.rationale == long_rationale
        assert len(restored.alternatives_considered) == 100

    @pytest.mark.asyncio
    async def test_oversized_reasoning_fields_rejected(self, keypair):
        """Fields exceeding size limits are rejected with ValueError."""
        with pytest.raises(ValueError, match="decision exceeds maximum"):
            ReasoningTrace(
                decision="D" * 10_001,
                rationale="valid",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
            )
        with pytest.raises(ValueError, match="rationale exceeds maximum"):
            ReasoningTrace(
                decision="valid",
                rationale="R" * 50_001,
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
            )
        with pytest.raises(ValueError, match="alternatives_considered exceeds"):
            ReasoningTrace(
                decision="valid",
                rationale="valid",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                alternatives_considered=["x"] * 101,
            )
        with pytest.raises(ValueError, match="evidence exceeds"):
            ReasoningTrace(
                decision="valid",
                rationale="valid",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                evidence=[{"k": "v"}] * 101,
            )

    @pytest.mark.asyncio
    async def test_oversized_individual_alternative_rejected(self):
        """Individual alternative exceeding 5,000 chars is rejected."""
        with pytest.raises(ValueError, match="alternative.*exceeds"):
            ReasoningTrace(
                decision="valid",
                rationale="valid",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                alternatives_considered=["A" * 5_001],
            )

    @pytest.mark.asyncio
    async def test_oversized_methodology_rejected(self):
        """Methodology exceeding 1,000 chars is rejected."""
        with pytest.raises(ValueError, match="methodology exceeds"):
            ReasoningTrace(
                decision="valid",
                rationale="valid",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                methodology="M" * 1_001,
            )

    @pytest.mark.asyncio
    async def test_unicode_and_special_chars_in_reasoning(self, keypair):
        """Unicode, emoji, newlines in decision/rationale: hash and sign should work."""
        private_key, public_key = keypair

        trace = ReasoningTrace(
            decision="Approve access for \u5206\u6790 (analysis)",
            rationale="Agent meets requirements.\nLine2.\tTabbed.\n\u2603 Snowman approved.",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=[
                "Deny: \u274c",
                "Review: \u2705",
            ],
            evidence=[{"note": "Unicode test: \u00e9\u00e8\u00ea\u00eb"}],
            methodology="capability_matching",
            confidence=0.77,
        )

        trace_hash = hash_reasoning_trace(trace)
        assert len(trace_hash) == 64

        trace_sig = sign_reasoning_trace(trace, private_key)
        assert verify_reasoning_signature(trace, trace_sig, public_key) is True

        # Roundtrip
        d = trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        assert restored.decision == trace.decision
        assert restored.rationale == trace.rationale

    @pytest.mark.asyncio
    async def test_future_confidentiality_level_rejected(self):
        """Unknown confidentiality level string should raise ValueError."""
        with pytest.raises(ValueError):
            ConfidentialityLevel("ultra_secret")

    @pytest.mark.asyncio
    async def test_concurrent_verification_safety(self, ops, reasoning_trace, keypair):
        """Multiple verify calls on same chain concurrently: all should succeed."""
        private_key, _ = keypair
        reasoning_constraint = _make_reasoning_constraint()

        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(
            ops, "agent-concurrent", ["read_data"], constraints=[reasoning_constraint]
        )

        chain = await ops.trust_store.get_chain("agent-concurrent")
        delegation = _make_delegation_with_reasoning(
            "agent-concurrent", reasoning_trace, private_key
        )
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        # Run 10 concurrent verify calls
        tasks = [
            ops.verify(
                agent_id="agent-concurrent",
                action="read_data",
                level=VerificationLevel.FULL,
            )
            for _ in range(10)
        ]
        results = await asyncio.gather(*tasks)

        for result in results:
            assert result.valid is True
            assert result.reasoning_present is True
            assert result.reasoning_verified is True

    @pytest.mark.asyncio
    async def test_confidence_out_of_range_rejected(self):
        """Confidence values outside [0.0, 1.0] should raise ValueError."""
        with pytest.raises(ValueError, match="confidence must be between"):
            ReasoningTrace(
                decision="Test",
                rationale="Test",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                confidence=1.5,
            )

        with pytest.raises(ValueError, match="confidence must be between"):
            ReasoningTrace(
                decision="Test",
                rationale="Test",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                confidence=-0.1,
            )

    @pytest.mark.asyncio
    async def test_enforcer_propagates_reasoning_metadata(
        self, ops, reasoning_trace, keypair
    ):
        """StrictEnforcer should propagate reasoning fields into enforcement record."""
        private_key, _ = keypair
        reasoning_constraint = _make_reasoning_constraint()

        await _establish_agent_with_capability(ops, "agent-root", ["read_data"])
        await _establish_agent_with_capability(
            ops, "agent-enforce", ["read_data"], constraints=[reasoning_constraint]
        )

        chain = await ops.trust_store.get_chain("agent-enforce")
        delegation = _make_delegation_with_reasoning(
            "agent-enforce", reasoning_trace, private_key
        )
        chain.delegations.append(delegation)
        await ops.trust_store.store_chain(chain)

        result = await ops.verify(
            agent_id="agent-enforce",
            action="read_data",
            level=VerificationLevel.FULL,
        )

        enforcer = StrictEnforcer()
        verdict = enforcer.enforce(
            agent_id="agent-enforce",
            action="read_data",
            result=result,
        )
        assert verdict == Verdict.AUTO_APPROVED

        records = enforcer.records
        assert len(records) == 1
        assert records[0].metadata.get("reasoning_present") is True
        assert records[0].metadata.get("reasoning_verified") is True

    @pytest.mark.asyncio
    async def test_shadow_enforcer_tracks_reasoning_metrics(
        self, ops, reasoning_trace, keypair
    ):
        """ShadowEnforcer should track reasoning presence/absence in metrics."""
        private_key, _ = keypair

        # Create result with reasoning present
        result_with = VerificationResult(
            valid=True,
            reasoning_present=True,
            reasoning_verified=True,
        )
        # Create result without reasoning
        result_without = VerificationResult(
            valid=True,
            reasoning_present=False,
            reasoning_verified=False,
        )

        shadow = ShadowEnforcer()
        shadow.check("agent-1", "read_data", result_with)
        shadow.check("agent-2", "read_data", result_without)
        shadow.check("agent-3", "read_data", result_with)

        assert shadow.metrics.reasoning_present_count == 2
        assert shadow.metrics.reasoning_absent_count == 1
        assert shadow.metrics.reasoning_verification_failed_count == 1

        report = shadow.report()
        assert "Reasoning present:" in report
        assert "Reasoning absent:" in report


# ===========================================================================
# Part 3: Backward Compatibility Tests
# ===========================================================================


class TestReasoningBackwardCompat:
    """Ensure legacy chains without reasoning work unchanged."""

    @pytest.mark.asyncio
    async def test_chain_without_reasoning_verifies_normally(self, ops):
        """Legacy chain (no reasoning) still verifies at all levels."""
        await _establish_agent_with_capability(ops, "agent-legacy-1", ["read_data"])

        # QUICK
        result_q = await ops.verify(
            agent_id="agent-legacy-1",
            action="read_data",
            level=VerificationLevel.QUICK,
        )
        assert result_q.valid is True
        assert result_q.reasoning_verified is None
        assert result_q.reasoning_present is None

        # STANDARD
        result_s = await ops.verify(
            agent_id="agent-legacy-1",
            action="read_data",
            level=VerificationLevel.STANDARD,
        )
        assert result_s.valid is True
        assert result_s.reasoning_verified is None
        assert result_s.reasoning_present is None

        # FULL
        result_f = await ops.verify(
            agent_id="agent-legacy-1",
            action="read_data",
            level=VerificationLevel.FULL,
        )
        assert result_f.valid is True
        assert result_f.reasoning_verified is None
        assert result_f.reasoning_present is None

    @pytest.mark.asyncio
    async def test_old_format_chain_deserializes(self):
        """Chain dict without reasoning fields deserializes correctly."""
        old_delegation_data = {
            "id": "del-old-001",
            "delegator_id": "parent",
            "delegatee_id": "child",
            "task_id": "task-old",
            "capabilities_delegated": ["analyze"],
            "constraint_subset": ["read_only"],
            "delegated_at": "2025-01-01T00:00:00+00:00",
            "signature": "old-sig",
            # No reasoning_trace, reasoning_trace_hash, or reasoning_signature
        }
        delegation = DelegationRecord.from_dict(old_delegation_data)
        assert delegation.reasoning_trace is None
        assert delegation.reasoning_trace_hash is None
        assert delegation.reasoning_signature is None
        assert delegation.delegator_id == "parent"

        old_anchor_data = {
            "id": "aud-old-001",
            "agent_id": "agent-old",
            "action": "read",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "trust_chain_hash": "abc123",
            "result": "success",
            "signature": "old-sig",
            # No reasoning fields
        }
        anchor = AuditAnchor.from_dict(old_anchor_data)
        assert anchor.reasoning_trace is None
        assert anchor.reasoning_trace_hash is None
        assert anchor.reasoning_signature is None

    @pytest.mark.asyncio
    async def test_scoring_unchanged_without_reasoning_required(self, ops, keypair):
        """Without REASONING_REQUIRED constraint, scoring is identical
        regardless of reasoning trace presence."""
        private_key, _ = keypair

        # Agent without REASONING_REQUIRED, with delegation (no reasoning)
        await _establish_agent_with_capability(ops, "agent-compat-1", ["read_data"])
        chain1 = await ops.trust_store.get_chain("agent-compat-1")
        del1 = DelegationRecord(
            id="del-compat-1",
            delegator_id="agent-root",
            delegatee_id="agent-compat-1",
            task_id="task-compat-1",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign("test", private_key),
        )
        chain1.delegations.append(del1)
        await ops.trust_store.store_chain(chain1)
        score1 = await compute_trust_score("agent-compat-1", ops.trust_store)

        # Agent without REASONING_REQUIRED, with delegation (has reasoning)
        reasoning_trace = ReasoningTrace(
            decision="Test",
            rationale="Test",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        await _establish_agent_with_capability(ops, "agent-compat-2", ["read_data"])
        chain2 = await ops.trust_store.get_chain("agent-compat-2")
        del2 = _make_delegation_with_reasoning(
            "agent-compat-2", reasoning_trace, private_key, deleg_id="del-compat-2"
        )
        chain2.delegations.append(del2)
        await ops.trust_store.store_chain(chain2)
        score2 = await compute_trust_score("agent-compat-2", ops.trust_store)

        # Both should NOT have reasoning_coverage in breakdown
        assert "reasoning_coverage" not in score1.breakdown
        assert "reasoning_coverage" not in score2.breakdown

        # Both should have identical factor keys
        assert score1.breakdown.keys() == score2.breakdown.keys()

    @pytest.mark.asyncio
    async def test_delegation_to_dict_from_dict_roundtrip_with_reasoning(self):
        """DelegationRecord with reasoning: to_dict -> from_dict preserves all fields."""
        trace = ReasoningTrace(
            decision="Delegate for analysis",
            rationale="Agent has required skill",
            confidentiality=ConfidentialityLevel.CONFIDENTIAL,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=["Direct execution"],
            evidence=[{"source": "capability_registry"}],
            methodology="capability_matching",
            confidence=0.85,
        )

        private_key, public_key = generate_keypair()
        delegation = DelegationRecord(
            id="del-rt-001",
            delegator_id="parent",
            delegatee_id="child",
            task_id="task-rt",
            capabilities_delegated=["analyze"],
            constraint_subset=["read_only"],
            delegated_at=FIXED_TIMESTAMP,
            signature="sig-placeholder",
            reasoning_trace=trace,
            reasoning_trace_hash=hash_reasoning_trace(trace),
            reasoning_signature=sign_reasoning_trace(trace, private_key),
        )

        d = delegation.to_dict()
        restored = DelegationRecord.from_dict(d)

        assert restored.reasoning_trace is not None
        assert restored.reasoning_trace.decision == trace.decision
        assert restored.reasoning_trace.rationale == trace.rationale
        assert (
            restored.reasoning_trace.confidentiality
            == ConfidentialityLevel.CONFIDENTIAL
        )
        assert restored.reasoning_trace.confidence == 0.85
        assert restored.reasoning_trace_hash == delegation.reasoning_trace_hash
        assert restored.reasoning_signature == delegation.reasoning_signature


# ===========================================================================
# Part 4: Property-Based Tests (hypothesis)
# ===========================================================================

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False

pytestmark_hypothesis = pytest.mark.skipif(
    not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed"
)


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestReasoningPropertyBased:
    """Property-based tests using hypothesis."""

    @given(
        decision=st.text(min_size=1, max_size=500),
        rationale=st.text(min_size=1, max_size=500),
        confidence=st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        ),
        methodology=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        level=st.sampled_from(list(ConfidentialityLevel)),
    )
    @settings(max_examples=50)
    def test_any_reasoning_trace_roundtrips(
        self, decision, rationale, confidence, methodology, level
    ):
        """Property: for any valid trace, to_dict() -> from_dict() roundtrips."""
        trace = ReasoningTrace(
            decision=decision,
            rationale=rationale,
            confidentiality=level,
            timestamp=FIXED_TIMESTAMP,
            methodology=methodology,
            confidence=confidence,
        )
        d = trace.to_dict()
        restored = ReasoningTrace.from_dict(d)

        assert restored.decision == decision
        assert restored.rationale == rationale
        assert restored.confidentiality == level
        assert restored.methodology == methodology
        assert restored.confidence == confidence
        assert restored.timestamp == FIXED_TIMESTAMP

    @given(
        decision=st.text(min_size=1, max_size=200),
        rationale=st.text(min_size=1, max_size=200),
        level=st.sampled_from(list(ConfidentialityLevel)),
    )
    @settings(max_examples=30)
    def test_hash_changes_on_any_mutation(self, decision, rationale, level):
        """Property: changing any field changes the hash."""
        trace = ReasoningTrace(
            decision=decision,
            rationale=rationale,
            confidentiality=level,
            timestamp=FIXED_TIMESTAMP,
        )
        original_hash = hash_reasoning_trace(trace)

        # Mutate decision
        mutated = ReasoningTrace(
            decision=decision + "_mutated",
            rationale=rationale,
            confidentiality=level,
            timestamp=FIXED_TIMESTAMP,
        )
        assert hash_reasoning_trace(mutated) != original_hash

        # Mutate rationale
        mutated2 = ReasoningTrace(
            decision=decision,
            rationale=rationale + "_mutated",
            confidentiality=level,
            timestamp=FIXED_TIMESTAMP,
        )
        assert hash_reasoning_trace(mutated2) != original_hash

    @given(
        level_a=st.sampled_from(list(ConfidentialityLevel)),
        level_b=st.sampled_from(list(ConfidentialityLevel)),
    )
    @settings(max_examples=50)
    def test_confidentiality_ordering_total(self, level_a, level_b):
        """Property: all pairs of ConfidentialityLevel are comparable (total order)."""
        # Exactly one of: a < b, a == b, a > b must hold
        lt = level_a < level_b
        eq = level_a == level_b
        gt = level_a > level_b

        # Exactly one must be true
        assert sum([lt, eq, gt]) == 1

        # Consistency with <= and >=
        assert (level_a <= level_b) == (lt or eq)
        assert (level_a >= level_b) == (gt or eq)
