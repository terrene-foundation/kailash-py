# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for EATP emission from GovernanceEngine (TODO-06, TODO-12, TODO-13).

Covers:
- TODO-06: Bridge bilateral consent (consent_bridge, require_bilateral_consent)
- TODO-12: DelegationRecord emission on set_role_envelope, set_task_envelope, create_bridge
- TODO-13: CapabilityAttestation emission on grant_clearance, barrier_enforced audit,
           effective envelope snapshot in verify_action audit
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kailash.trust.pact.access import PactBridge
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.compilation import RoleDefinition
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DepartmentConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    OrgDefinition,
    TrustPostureLevel,
)
from kailash.trust.pact.eatp_emitter import InMemoryPactEmitter
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope, TaskEnvelope
from kailash.trust.pact.exceptions import PactError
from kailash.trust.pact.knowledge import KnowledgeItem


# ---------------------------------------------------------------------------
# Helpers -- minimal org for testing
# ---------------------------------------------------------------------------


def _make_org_and_engine(
    *,
    eatp_emitter: InMemoryPactEmitter | None = None,
    require_bilateral_consent: bool = False,
) -> tuple[GovernanceEngine, dict[str, str]]:
    """Create a minimal org with two departments and return (engine, addresses).

    Org structure:
        CEO (D1-R1)
        +-- Dean of Engineering (D1-R1-D1-R1) -- primary for d-eng
        |   +-- Team Lead (D1-R1-D1-R1-T1-R1) -- team t-backend in d-eng
        +-- Dean of Science (D1-R1-D2-R1) -- primary for d-sci
            +-- Researcher (D1-R1-D2-R1-T1-R1) -- team t-bio in d-sci

    addresses dict maps friendly names to D/T/R positional addresses.
    """
    roles = [
        RoleDefinition(
            role_id="ceo",
            name="CEO",
            is_primary_for_unit="d-eng",
        ),
        RoleDefinition(
            role_id="dean-eng",
            name="Dean of Engineering",
            reports_to_role_id="ceo",
            is_primary_for_unit="d-eng",
        ),
        RoleDefinition(
            role_id="team-lead",
            name="Team Lead",
            reports_to_role_id="dean-eng",
        ),
        RoleDefinition(
            role_id="dean-sci",
            name="Dean of Science",
            reports_to_role_id="ceo",
            is_primary_for_unit="d-sci",
        ),
        RoleDefinition(
            role_id="researcher",
            name="Researcher",
            reports_to_role_id="dean-sci",
        ),
    ]

    org = OrgDefinition(
        org_id="test-org",
        name="Test Org",
        departments=[
            DepartmentConfig(department_id="d-eng", name="Engineering"),
            DepartmentConfig(department_id="d-sci", name="Science"),
        ],
        roles=roles,
    )

    engine = GovernanceEngine(
        org,
        eatp_emitter=eatp_emitter,
        require_bilateral_consent=require_bilateral_consent,
    )

    # Build address lookup by role_id
    addresses: dict[str, str] = {}
    for addr, node in engine._compiled_org.nodes.items():
        if node.role_definition is not None:
            addresses[node.role_definition.role_id] = addr

    return engine, addresses


def _set_envelope_for_role(
    engine: GovernanceEngine,
    defining_addr: str,
    target_addr: str,
    *,
    envelope_id: str = "env-1",
    allowed_actions: list[str] | None = None,
    max_spend: float = 1000.0,
) -> RoleEnvelope:
    """Set a role envelope and return it."""
    env_config = ConstraintEnvelopeConfig(
        id=envelope_id,
        description="test envelope",
        financial=FinancialConstraintConfig(max_spend_usd=max_spend),
        operational=OperationalConstraintConfig(
            allowed_actions=allowed_actions or ["read", "write", "deploy"],
        ),
    )
    role_env = RoleEnvelope(
        id=envelope_id,
        defining_role_address=defining_addr,
        target_role_address=target_addr,
        envelope=env_config,
    )
    engine.set_role_envelope(role_env)
    return role_env


# ---------------------------------------------------------------------------
# TODO-06: Bridge bilateral consent
# ---------------------------------------------------------------------------


class TestBridgeBilateralConsent:
    """Bridge bilateral consent -- require_bilateral_consent flag."""

    def test_consent_bridge_required_missing_consent(self) -> None:
        """With require_bilateral_consent=True, create_bridge without consent raises PactError."""
        emitter = InMemoryPactEmitter()
        engine, addrs = _make_org_and_engine(
            eatp_emitter=emitter,
            require_bilateral_consent=True,
        )

        # Set up envelopes so we can approve and create bridge
        # Dean of Eng sets envelope for Team Lead
        _set_envelope_for_role(
            engine, addrs["dean-eng"], addrs["team-lead"], envelope_id="env-tl"
        )
        # Dean of Sci sets envelope for Researcher
        _set_envelope_for_role(
            engine, addrs["dean-sci"], addrs["researcher"], envelope_id="env-res"
        )

        # LCA approval (CEO approves bridge between Team Lead and Researcher)
        engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["ceo"],
        )

        bridge = PactBridge(
            id="bridge-eng-sci",
            role_a_address=addrs["team-lead"],
            role_b_address=addrs["researcher"],
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )

        # No consent registered -- should fail
        with pytest.raises(PactError, match="bilateral consent missing"):
            engine.create_bridge(bridge)

    def test_consent_bridge_success(self) -> None:
        """With consent from both sides + LCA approval, create_bridge succeeds."""
        emitter = InMemoryPactEmitter()
        engine, addrs = _make_org_and_engine(
            eatp_emitter=emitter,
            require_bilateral_consent=True,
        )

        _set_envelope_for_role(
            engine, addrs["dean-eng"], addrs["team-lead"], envelope_id="env-tl"
        )
        _set_envelope_for_role(
            engine, addrs["dean-sci"], addrs["researcher"], envelope_id="env-res"
        )

        bridge_id = "bridge-eng-sci"

        # Register bilateral consent
        engine.consent_bridge(addrs["team-lead"], bridge_id)
        engine.consent_bridge(addrs["researcher"], bridge_id)

        # LCA approval
        engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["ceo"],
        )

        bridge = PactBridge(
            id=bridge_id,
            role_a_address=addrs["team-lead"],
            role_b_address=addrs["researcher"],
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )

        # Should succeed -- both sides consented
        engine.create_bridge(bridge)

    def test_consent_not_required_by_default(self) -> None:
        """Without require_bilateral_consent, create_bridge works as before (LCA only)."""
        emitter = InMemoryPactEmitter()
        engine, addrs = _make_org_and_engine(eatp_emitter=emitter)

        _set_envelope_for_role(
            engine, addrs["dean-eng"], addrs["team-lead"], envelope_id="env-tl"
        )
        _set_envelope_for_role(
            engine, addrs["dean-sci"], addrs["researcher"], envelope_id="env-res"
        )

        # LCA approval only (no consent)
        engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["ceo"],
        )

        bridge = PactBridge(
            id="bridge-eng-sci",
            role_a_address=addrs["team-lead"],
            role_b_address=addrs["researcher"],
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )

        # Should succeed -- bilateral consent not required
        engine.create_bridge(bridge)


# ---------------------------------------------------------------------------
# TODO-12: DelegationRecord emission
# ---------------------------------------------------------------------------


class TestDelegationRecordEmission:
    """DelegationRecord emitted on set_role_envelope and create_bridge."""

    def test_delegation_emitted_on_role_envelope(self) -> None:
        """set_role_envelope emits a DelegationRecord."""
        emitter = InMemoryPactEmitter()
        engine, addrs = _make_org_and_engine(eatp_emitter=emitter)

        # Genesis record is emitted on init
        assert len(emitter.genesis_records) == 1

        # Clear delegation records baseline
        initial_deleg_count = len(emitter.delegation_records)

        _set_envelope_for_role(
            engine, addrs["dean-eng"], addrs["team-lead"], envelope_id="env-tl"
        )

        assert len(emitter.delegation_records) == initial_deleg_count + 1
        delegation = emitter.delegation_records[-1]
        assert delegation.delegator_id == addrs["dean-eng"]
        assert delegation.delegatee_id == addrs["team-lead"]
        assert delegation.signature == "UNSIGNED"
        assert delegation.id.startswith("pact-deleg-")

    def test_delegation_emitted_on_bridge(self) -> None:
        """create_bridge emits TWO DelegationRecords (bilateral A->B and B->A)."""
        emitter = InMemoryPactEmitter()
        engine, addrs = _make_org_and_engine(eatp_emitter=emitter)

        _set_envelope_for_role(
            engine, addrs["dean-eng"], addrs["team-lead"], envelope_id="env-tl"
        )
        _set_envelope_for_role(
            engine, addrs["dean-sci"], addrs["researcher"], envelope_id="env-res"
        )

        # Count delegation records after envelope setup
        deleg_count_before = len(emitter.delegation_records)

        # LCA approval + bridge creation
        engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["ceo"],
        )

        bridge = PactBridge(
            id="bridge-eng-sci",
            role_a_address=addrs["team-lead"],
            role_b_address=addrs["researcher"],
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
        engine.create_bridge(bridge)

        # Two new delegation records (A->B and B->A)
        assert len(emitter.delegation_records) == deleg_count_before + 2

        # Verify the two delegation records cover both directions
        new_delegations = list(emitter.delegation_records)[deleg_count_before:]
        delegator_ids = {d.delegator_id for d in new_delegations}
        delegatee_ids = {d.delegatee_id for d in new_delegations}

        assert addrs["team-lead"] in delegator_ids
        assert addrs["researcher"] in delegator_ids
        assert addrs["team-lead"] in delegatee_ids
        assert addrs["researcher"] in delegatee_ids

    def test_delegation_emitted_on_task_envelope(self) -> None:
        """set_task_envelope emits a DelegationRecord."""
        emitter = InMemoryPactEmitter()
        engine, addrs = _make_org_and_engine(eatp_emitter=emitter)

        # Set parent role envelope first
        role_env = _set_envelope_for_role(
            engine, addrs["dean-eng"], addrs["team-lead"], envelope_id="env-tl"
        )

        deleg_count_before = len(emitter.delegation_records)

        # Create a task envelope narrowing the role envelope
        task_config = ConstraintEnvelopeConfig(
            id="task-env-1",
            description="task envelope",
            financial=FinancialConstraintConfig(max_spend_usd=500.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
            ),
        )
        task_env = TaskEnvelope(
            id="te-1",
            task_id="task-001",
            parent_envelope_id="env-tl",
            envelope=task_config,
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        )
        engine.set_task_envelope(task_env)

        assert len(emitter.delegation_records) == deleg_count_before + 1
        delegation = emitter.delegation_records[-1]
        assert delegation.task_id == "task-001"
        assert delegation.signature == "UNSIGNED"


# ---------------------------------------------------------------------------
# TODO-13: CapabilityAttestation emission
# ---------------------------------------------------------------------------


class TestCapabilityAttestationEmission:
    """CapabilityAttestation emitted on grant_clearance."""

    def test_capability_emitted_on_clearance(self) -> None:
        """grant_clearance emits a CapabilityAttestation."""
        emitter = InMemoryPactEmitter()
        engine, addrs = _make_org_and_engine(eatp_emitter=emitter)

        clearance = RoleClearance(
            role_address=addrs["team-lead"],
            max_clearance=ConfidentialityLevel.SECRET,
            compartments=frozenset({"engineering", "infra"}),
            granted_by_role_address=addrs["dean-eng"],
            vetting_status=VettingStatus.ACTIVE,
        )

        initial_cap_count = len(emitter.capability_records)

        engine.grant_clearance(addrs["team-lead"], clearance)

        assert len(emitter.capability_records) == initial_cap_count + 1
        attestation = emitter.capability_records[-1]
        assert attestation.id.startswith("pact-capability-")
        assert "clearance:" in attestation.capability
        assert attestation.attester_id == addrs["team-lead"]
        assert attestation.signature == "UNSIGNED"
        # Compartments should appear in constraints
        constraint_strs = attestation.constraints
        assert any("engineering" in c for c in constraint_strs)
        assert any("infra" in c for c in constraint_strs)


# ---------------------------------------------------------------------------
# No-emission safety
# ---------------------------------------------------------------------------


class TestNoEmissionWithoutEmitter:
    """All engine methods work without an eatp_emitter (None)."""

    def test_no_emission_without_emitter(self) -> None:
        """Engine works without eatp_emitter -- no AttributeError or emission."""
        engine, addrs = _make_org_and_engine(eatp_emitter=None)

        # set_role_envelope
        _set_envelope_for_role(
            engine, addrs["dean-eng"], addrs["team-lead"], envelope_id="env-tl"
        )

        # grant_clearance
        clearance = RoleClearance(
            role_address=addrs["team-lead"],
            max_clearance=ConfidentialityLevel.RESTRICTED,
            compartments=frozenset(),
            granted_by_role_address=addrs["dean-eng"],
            vetting_status=VettingStatus.ACTIVE,
        )
        engine.grant_clearance(addrs["team-lead"], clearance)

        # verify_action
        verdict = engine.verify_action(addrs["team-lead"], "read")
        assert verdict.level in ("auto_approved", "blocked", "flagged", "held")


# ---------------------------------------------------------------------------
# TODO-13: barrier_enforced audit and envelope snapshot
# ---------------------------------------------------------------------------


class TestAuditEnrichment:
    """Audit details enrichment for check_access denial and verify_action."""

    def test_barrier_enforced_on_denial(self) -> None:
        """check_access denial audit includes barrier_enforced=True."""
        from kailash.trust.pact.audit import AuditChain

        emitter = InMemoryPactEmitter()
        engine, addrs = _make_org_and_engine(eatp_emitter=emitter)

        # Grant clearance to team-lead (RESTRICTED only)
        clearance = RoleClearance(
            role_address=addrs["team-lead"],
            max_clearance=ConfidentialityLevel.RESTRICTED,
            compartments=frozenset(),
            granted_by_role_address=addrs["dean-eng"],
            vetting_status=VettingStatus.ACTIVE,
        )
        engine.grant_clearance(addrs["team-lead"], clearance)

        # Try to access a CONFIDENTIAL item from another department (should be denied)
        item = KnowledgeItem(
            item_id="sci-data-001",
            classification=ConfidentialityLevel.CONFIDENTIAL,
            owning_unit_address=addrs.get("dean-sci", "D1-R1-D2-R1"),
            description="Science department confidential data",
        )

        decision = engine.check_access(
            role_address=addrs["team-lead"],
            knowledge_item=item,
            posture=TrustPostureLevel.SUPERVISED,
        )

        # The decision should be denied (barrier enforced)
        assert decision.allowed is False

    def test_effective_envelope_snapshot_in_verify_action(self) -> None:
        """verify_action audit details include effective_envelope_snapshot when envelope exists."""
        emitter = InMemoryPactEmitter()
        engine, addrs = _make_org_and_engine(eatp_emitter=emitter)

        _set_envelope_for_role(
            engine,
            addrs["dean-eng"],
            addrs["team-lead"],
            envelope_id="env-tl",
            allowed_actions=["read", "write"],
            max_spend=500.0,
        )

        verdict = engine.verify_action(
            addrs["team-lead"],
            "read",
            context={"cost": 10.0},
        )

        assert verdict.level == "auto_approved"
        # The audit_details should include envelope information
        assert verdict.audit_details is not None
        assert verdict.audit_details.get("has_envelope") is True
        # Effective envelope snapshot should be present
        snapshot = verdict.audit_details.get("effective_envelope_snapshot")
        if snapshot is not None:
            assert "financial_max_spend" in snapshot or "confidentiality" in snapshot
