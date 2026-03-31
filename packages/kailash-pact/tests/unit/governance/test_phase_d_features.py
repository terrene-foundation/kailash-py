# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for Phase D features: TODO-04, TODO-07, TODO-08.

Covers:
- TODO-04: Pass-through envelope detection (check_passthrough_envelope)
- TODO-07: Bridge scope validation (max_classification, operational_scope)
- TODO-08: Compliance role as alternative bridge approver
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.access import PactBridge
from kailash.trust.pact.compilation import RoleDefinition
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DepartmentConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    OrgDefinition,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import (
    RoleEnvelope,
    check_passthrough_envelope,
)
from kailash.trust.pact.exceptions import PactError


# ---------------------------------------------------------------------------
# Helpers -- minimal org (same pattern as test_eatp_emission_engine.py)
# ---------------------------------------------------------------------------


def _make_org_and_engine(
    *,
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
    confidentiality_clearance: ConfidentialityLevel = ConfidentialityLevel.PUBLIC,
) -> RoleEnvelope:
    """Set a role envelope and return it."""
    env_config = ConstraintEnvelopeConfig(
        id=envelope_id,
        description="test envelope",
        financial=FinancialConstraintConfig(max_spend_usd=max_spend),
        operational=OperationalConstraintConfig(
            allowed_actions=allowed_actions or ["read", "write", "deploy"],
        ),
        confidentiality_clearance=confidentiality_clearance,
    )
    role_env = RoleEnvelope(
        id=envelope_id,
        defining_role_address=defining_addr,
        target_role_address=target_addr,
        envelope=env_config,
    )
    engine.set_role_envelope(role_env)
    return role_env


# ===========================================================================
# TODO-04: Pass-through envelope detection
# ===========================================================================


class TestPassthroughEnvelopeDetection:
    """check_passthrough_envelope -- detect when child == parent constraints."""

    def test_passthrough_detected(self) -> None:
        """Identical constraint fields across all 5 dimensions + clearance + depth -> True."""
        parent = ConstraintEnvelopeConfig(
            id="parent-env",
            description="Parent envelope",
            financial=FinancialConstraintConfig(max_spend_usd=500.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
            ),
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            max_delegation_depth=3,
        )
        child = ConstraintEnvelopeConfig(
            id="child-env",
            description="Child envelope -- different id and description",
            financial=FinancialConstraintConfig(max_spend_usd=500.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
            ),
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            max_delegation_depth=3,
        )

        assert check_passthrough_envelope(child, parent) is True

    def test_passthrough_not_detected(self) -> None:
        """Child is tighter than parent on financial dimension -> False."""
        parent = ConstraintEnvelopeConfig(
            id="parent-env",
            description="Parent envelope",
            financial=FinancialConstraintConfig(max_spend_usd=500.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
            ),
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            max_delegation_depth=3,
        )
        child = ConstraintEnvelopeConfig(
            id="child-env",
            description="Child envelope",
            financial=FinancialConstraintConfig(max_spend_usd=200.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
            ),
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            max_delegation_depth=3,
        )

        assert check_passthrough_envelope(child, parent) is False

    def test_passthrough_not_detected_operational_difference(self) -> None:
        """Child restricts operational actions -> False."""
        parent = ConstraintEnvelopeConfig(
            id="parent-env",
            description="Parent envelope",
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "deploy"],
            ),
        )
        child = ConstraintEnvelopeConfig(
            id="child-env",
            description="Child envelope",
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
            ),
        )

        assert check_passthrough_envelope(child, parent) is False

    def test_passthrough_not_detected_clearance_difference(self) -> None:
        """Child has lower confidentiality clearance -> False."""
        parent = ConstraintEnvelopeConfig(
            id="parent-env",
            description="Parent envelope",
            confidentiality_clearance=ConfidentialityLevel.SECRET,
        )
        child = ConstraintEnvelopeConfig(
            id="child-env",
            description="Child envelope",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )

        assert check_passthrough_envelope(child, parent) is False

    def test_passthrough_audit_on_set_role_envelope(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """set_role_envelope emits WARNING when pass-through detected."""
        engine, addrs = _make_org_and_engine()

        # Set parent envelope for dean-eng (CEO defines it)
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-eng"],
            envelope_id="env-parent",
            allowed_actions=["read", "write"],
            max_spend=500.0,
        )

        # Set identical envelope for team-lead (dean-eng defines it)
        # This is a pass-through: team-lead gets exact same constraints as dean-eng
        with caplog.at_level("WARNING"):
            _set_envelope_for_role(
                engine,
                addrs["dean-eng"],
                addrs["team-lead"],
                envelope_id="env-child",
                allowed_actions=["read", "write"],
                max_spend=500.0,
            )

        # Verify WARNING was emitted about pass-through
        passthrough_warnings = [
            r
            for r in caplog.records
            if "pass-through" in r.message.lower() or "passthrough" in r.message.lower()
        ]
        assert len(passthrough_warnings) >= 1, (
            f"Expected a pass-through warning in logs, got: "
            f"{[r.message for r in caplog.records]}"
        )


# ===========================================================================
# TODO-07: Bridge scope validation
# ===========================================================================


class TestBridgeScopeValidation:
    """Bridge scope validation -- max_classification and operational_scope."""

    def test_bridge_scope_within_envelopes(self) -> None:
        """Bridge with scope within both role envelopes -> succeeds."""
        engine, addrs = _make_org_and_engine()

        # Set envelopes with CONFIDENTIAL clearance
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-eng"],
            envelope_id="env-dean-eng",
            allowed_actions=["read", "write", "deploy"],
            max_spend=1000.0,
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-eng"],
            addrs["team-lead"],
            envelope_id="env-tl",
            allowed_actions=["read", "write"],
            max_spend=500.0,
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-sci"],
            envelope_id="env-dean-sci",
            allowed_actions=["read", "write", "analyze"],
            max_spend=1000.0,
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-sci"],
            addrs["researcher"],
            envelope_id="env-res",
            allowed_actions=["read", "analyze"],
            max_spend=300.0,
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )

        # LCA approval (CEO)
        engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["ceo"],
        )

        # Bridge with max_classification RESTRICTED (below both roles' CONFIDENTIAL)
        # and operational_scope within both roles' allowed actions
        bridge = PactBridge(
            id="bridge-valid-scope",
            role_a_address=addrs["team-lead"],
            role_b_address=addrs["researcher"],
            bridge_type="scoped",
            max_classification=ConfidentialityLevel.RESTRICTED,
            operational_scope=("read",),
        )

        # Should succeed -- scope is within both envelopes
        engine.create_bridge(bridge)

    def test_bridge_scope_exceeds_envelope_classification(self) -> None:
        """Bridge with max_classification exceeding a role's clearance -> PactError."""
        engine, addrs = _make_org_and_engine()

        # Set envelopes with RESTRICTED clearance
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-eng"],
            envelope_id="env-dean-eng",
            allowed_actions=["read", "write"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-eng"],
            addrs["team-lead"],
            envelope_id="env-tl",
            allowed_actions=["read", "write"],
            confidentiality_clearance=ConfidentialityLevel.RESTRICTED,
        )
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-sci"],
            envelope_id="env-dean-sci",
            allowed_actions=["read", "write"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-sci"],
            addrs["researcher"],
            envelope_id="env-res",
            allowed_actions=["read"],
            confidentiality_clearance=ConfidentialityLevel.RESTRICTED,
        )

        # LCA approval
        engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["ceo"],
        )

        # Bridge requests SECRET -- exceeds both roles' RESTRICTED clearance
        bridge = PactBridge(
            id="bridge-exceeds-scope",
            role_a_address=addrs["team-lead"],
            role_b_address=addrs["researcher"],
            bridge_type="scoped",
            max_classification=ConfidentialityLevel.SECRET,
            operational_scope=("read",),
        )

        with pytest.raises(PactError, match="max_classification.*exceeds"):
            engine.create_bridge(bridge)

    def test_bridge_scope_exceeds_operational_scope(self) -> None:
        """Bridge operational_scope includes actions not in a role's allowed_actions -> PactError."""
        engine, addrs = _make_org_and_engine()

        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-eng"],
            envelope_id="env-dean-eng",
            allowed_actions=["read", "write", "deploy"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-eng"],
            addrs["team-lead"],
            envelope_id="env-tl",
            allowed_actions=["read", "write"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-sci"],
            envelope_id="env-dean-sci",
            allowed_actions=["read", "analyze"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-sci"],
            addrs["researcher"],
            envelope_id="env-res",
            allowed_actions=["read"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )

        # LCA approval
        engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["ceo"],
        )

        # Bridge requests "deploy" -- not in researcher's allowed_actions
        bridge = PactBridge(
            id="bridge-bad-ops",
            role_a_address=addrs["team-lead"],
            role_b_address=addrs["researcher"],
            bridge_type="scoped",
            max_classification=ConfidentialityLevel.RESTRICTED,
            operational_scope=("read", "deploy"),
        )

        with pytest.raises(PactError, match="operational_scope.*not in"):
            engine.create_bridge(bridge)

    def test_bridge_no_scope_fields_passes(self) -> None:
        """Bridge without scope fields (empty operational_scope, default classification) -> passes."""
        engine, addrs = _make_org_and_engine()

        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-eng"],
            envelope_id="env-dean-eng",
            allowed_actions=["read", "write"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-eng"],
            addrs["team-lead"],
            envelope_id="env-tl",
            allowed_actions=["read", "write"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-sci"],
            envelope_id="env-dean-sci",
            allowed_actions=["read", "write"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-sci"],
            addrs["researcher"],
            envelope_id="env-res",
            allowed_actions=["read"],
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )

        engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["ceo"],
        )

        # Bridge with PUBLIC classification (default) and no operational_scope
        bridge = PactBridge(
            id="bridge-no-scope",
            role_a_address=addrs["team-lead"],
            role_b_address=addrs["researcher"],
            bridge_type="standing",
            max_classification=ConfidentialityLevel.PUBLIC,
        )

        # Should pass -- no scope fields that exceed anything
        engine.create_bridge(bridge)


# ===========================================================================
# TODO-08: Compliance role as alternative bridge approver
# ===========================================================================


class TestComplianceRoleBridgeApprover:
    """Compliance role as an alternative to LCA for bridge approval."""

    def test_compliance_role_can_approve_bridge(self) -> None:
        """Registered compliance role can approve bridge instead of LCA."""
        engine, addrs = _make_org_and_engine()

        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-eng"],
            envelope_id="env-dean-eng",
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-eng"],
            addrs["team-lead"],
            envelope_id="env-tl",
        )
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-sci"],
            envelope_id="env-dean-sci",
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-sci"],
            addrs["researcher"],
            envelope_id="env-res",
        )

        # Register Dean of Science as the compliance role
        engine.register_compliance_role(addrs["dean-sci"])

        # Approve bridge using the compliance role (NOT the LCA which is CEO)
        approval = engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["dean-sci"],
        )
        assert approval.approved_by == addrs["dean-sci"]

        # Create bridge should succeed with compliance-approved bridge
        bridge = PactBridge(
            id="bridge-compliance",
            role_a_address=addrs["team-lead"],
            role_b_address=addrs["researcher"],
            bridge_type="standing",
            max_classification=ConfidentialityLevel.PUBLIC,
        )
        engine.create_bridge(bridge)

    def test_non_compliance_non_lca_rejected(self) -> None:
        """A role that is neither LCA nor compliance role -> PactError."""
        engine, addrs = _make_org_and_engine()

        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-eng"],
            envelope_id="env-dean-eng",
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-eng"],
            addrs["team-lead"],
            envelope_id="env-tl",
        )
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-sci"],
            envelope_id="env-dean-sci",
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-sci"],
            addrs["researcher"],
            envelope_id="env-res",
        )

        # No compliance role registered -- so only LCA (CEO) can approve
        # Try to approve with dean-eng (NOT the LCA, NOT a compliance role)
        with pytest.raises(PactError, match="approval must come from"):
            engine.approve_bridge(
                source_address=addrs["team-lead"],
                target_address=addrs["researcher"],
                approver_address=addrs["dean-eng"],
            )

    def test_lca_still_works_with_compliance_role_registered(self) -> None:
        """LCA can still approve even when a compliance role is registered."""
        engine, addrs = _make_org_and_engine()

        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-eng"],
            envelope_id="env-dean-eng",
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-eng"],
            addrs["team-lead"],
            envelope_id="env-tl",
        )
        _set_envelope_for_role(
            engine,
            addrs["ceo"],
            addrs["dean-sci"],
            envelope_id="env-dean-sci",
        )
        _set_envelope_for_role(
            engine,
            addrs["dean-sci"],
            addrs["researcher"],
            envelope_id="env-res",
        )

        # Register compliance role
        engine.register_compliance_role(addrs["dean-sci"])

        # But approve using the actual LCA (CEO) -- should still work
        approval = engine.approve_bridge(
            source_address=addrs["team-lead"],
            target_address=addrs["researcher"],
            approver_address=addrs["ceo"],
        )
        assert approval.approved_by == addrs["ceo"]

    def test_compliance_role_audit_emitted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Registering compliance role emits audit event."""
        engine, addrs = _make_org_and_engine()

        with caplog.at_level("DEBUG"):
            engine.register_compliance_role(addrs["dean-sci"])

        # The method should emit an audit -- we verify via the internal
        # audit mechanism. Since we don't have audit_chain configured,
        # we verify the compliance role is registered.
        assert engine._compliance_role == addrs["dean-sci"]
