# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""M6 adversarial tests -- 5 threats from PACT thesis Section 12.9.

Threat 1: Envelope dereliction (pass-through detection)
Threat 2: Compromised agent within envelope (correct behavior)
Threat 3: Bridge collusion (no approval check)
Threat 4: Posture gaming (no evidence validation)
Threat 5: TOCTOU (frozen dataclass verification)

Each threat documents the current security posture: what is enforced,
what is a known gap, and what is correct-by-design.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DepartmentConfig,
    OperationalConstraintConfig,
    TeamConfig,
    TrustPostureLevel,
)
from pact.build.org.builder import OrgDefinition
from pact.governance.access import (
    AccessDecision,
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
)
from pact.governance.addressing import Address, AddressSegment
from pact.governance.clearance import RoleClearance
from pact.governance.compilation import CompiledOrg, OrgNode, RoleDefinition, compile_org
from pact.governance.envelopes import (
    MonotonicTighteningError,
    RoleEnvelope,
    TaskEnvelope,
    intersect_envelopes,
)
from pact.governance.knowledge import KnowledgeItem


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def two_dept_org() -> CompiledOrg:
    """Two-department org for adversarial tests."""
    roles = [
        RoleDefinition(
            role_id="r-head-a",
            name="Head A",
            reports_to_role_id=None,
            is_primary_for_unit="d-a",
        ),
        RoleDefinition(
            role_id="r-member-a",
            name="Member A",
            reports_to_role_id="r-head-a",
            is_primary_for_unit="t-a1",
        ),
        RoleDefinition(
            role_id="r-head-b",
            name="Head B",
            reports_to_role_id=None,
            is_primary_for_unit="d-b",
        ),
        RoleDefinition(
            role_id="r-member-b",
            name="Member B",
            reports_to_role_id="r-head-b",
            is_primary_for_unit="t-b1",
        ),
    ]
    depts = [
        DepartmentConfig(department_id="d-a", name="Dept A"),
        DepartmentConfig(department_id="d-b", name="Dept B"),
    ]
    teams = [
        TeamConfig(id="t-a1", name="Team A1", workspace="ws-a"),
        TeamConfig(id="t-b1", name="Team B1", workspace="ws-b"),
    ]
    org = OrgDefinition(
        org_id="adversarial-test",
        name="Adversarial Org",
        departments=depts,
        teams=teams,
        roles=roles,
    )
    return compile_org(org)


# ===========================================================================
# Threat 1: Envelope dereliction
# ===========================================================================


class TestEnvelopeDereliction:
    """Thesis Section 12.9.1: Supervisor passes through identical envelope.

    A derelict supervisor copies their own envelope verbatim to a subordinate,
    providing no actual constraint narrowing. The monotonic tightening check
    allows identical envelopes (equal is valid, only strictly looser is rejected).

    DOCUMENTED GAP: There is no pass-through detection in the current implementation.
    The validate_tightening() method accepts child == parent as valid because
    equal envelopes do satisfy the tightening invariant (child <= parent).
    Detecting dereliction would require comparing the child envelope to the parent
    and flagging identity, which is a policy decision rather than a structural invariant.
    """

    def test_identical_envelope_passes_validation(self) -> None:
        """Identical child envelope passes monotonic tightening -- this is by design."""
        envelope = ConstraintEnvelopeConfig(
            id="env-1",
            description="Parent envelope",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
            ),
        )
        # Identical envelope should NOT raise MonotonicTighteningError
        # (equal <= parent is valid per the tightening invariant)
        RoleEnvelope.validate_tightening(
            parent_envelope=envelope,
            child_envelope=envelope,
        )
        # If we get here, the test documents that pass-through is not detected

    def test_tighter_child_still_valid(self) -> None:
        """A properly tightened child envelope is valid."""
        parent = ConstraintEnvelopeConfig(
            id="parent",
            description="Parent",
            confidentiality_clearance=ConfidentialityLevel.SECRET,
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "execute"],
            ),
        )
        child = ConstraintEnvelopeConfig(
            id="child",
            description="Child",
            confidentiality_clearance=ConfidentialityLevel.RESTRICTED,
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
            ),
        )
        RoleEnvelope.validate_tightening(
            parent_envelope=parent,
            child_envelope=child,
        )

    def test_looser_child_rejected(self) -> None:
        """A child envelope that exceeds the parent is rejected."""
        parent = ConstraintEnvelopeConfig(
            id="parent",
            description="Parent",
            confidentiality_clearance=ConfidentialityLevel.RESTRICTED,
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
            ),
        )
        child = ConstraintEnvelopeConfig(
            id="child",
            description="Child",
            confidentiality_clearance=ConfidentialityLevel.SECRET,
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "execute"],
            ),
        )
        with pytest.raises(MonotonicTighteningError):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent,
                child_envelope=child,
            )


# ===========================================================================
# Threat 2: Compromised agent within envelope
# ===========================================================================


class TestCompromisedAgentWithinEnvelope:
    """Thesis Section 12.9.2: Agent acting maliciously but within its envelope.

    If an agent is compromised but acts within its assigned envelope, PACT
    correctly allows the actions. This is correct behavior -- PACT enforces
    boundaries, not intent. A compromised agent within its envelope is bounded
    by its constraints.

    This test verifies that in-envelope access IS allowed (correct behavior),
    confirming that PACT's defense is boundary enforcement, not behavior analysis.
    """

    def test_in_envelope_access_allowed(self, two_dept_org: CompiledOrg) -> None:
        """A 'compromised' agent accessing data within its own unit is allowed."""
        clearances = {
            "D1-R1-T1-R1": RoleClearance(
                role_address="D1-R1-T1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="own-unit-data",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-T1",  # Same team
        )
        decision = can_access(
            role_address="D1-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is True, (
            "In-envelope access must be allowed. PACT enforces boundaries, not intent. "
            "A compromised agent within its envelope is bounded by constraints."
        )

    def test_cross_boundary_access_blocked(self, two_dept_org: CompiledOrg) -> None:
        """A compromised agent trying to access data outside its envelope is blocked."""
        clearances = {
            "D1-R1-T1-R1": RoleClearance(
                role_address="D1-R1-T1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="other-dept-data",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D2",  # Different department
        )
        decision = can_access(
            role_address="D1-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False, (
            "Cross-boundary access must be blocked even if the agent is compromised. "
            "The boundary is the defense."
        )


# ===========================================================================
# Threat 3: Bridge collusion
# ===========================================================================


class TestBridgeCollusion:
    """Thesis Section 12.9.3: Two colluding agents use an unauthorized bridge.

    DOCUMENTED GAP: The current can_access() implementation accepts any PactBridge
    in the bridges list parameter without verifying that the bridge was approved
    through a governance process. The caller is responsible for only passing
    approved bridges. There is no approval chain, creation authority, or
    governance workflow check within can_access() itself.

    This is a pre-retrieval gate design: the access algorithm is stateless and
    trusts its inputs. The governance enforcement (who may create bridges,
    approval requirements, etc.) must happen at the layer that constructs
    the bridges list before calling can_access().
    """

    def test_unauthorized_bridge_accepted_by_can_access(self, two_dept_org: CompiledOrg) -> None:
        """can_access() does not validate bridge approval status.

        DOCUMENTED GAP: An attacker who can inject a PactBridge into the bridges
        list can bypass access controls. The defense must be at the store/governance
        layer that constructs the bridge list, not at the access algorithm level.
        """
        clearances = {
            "D2-R1": RoleClearance(
                role_address="D2-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="protected-data",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        # This bridge was never "approved" -- just created by attacker
        unauthorized_bridge = PactBridge(
            id="bridge-unauthorized",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="ad_hoc",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        decision = can_access(
            role_address="D2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[unauthorized_bridge],
        )
        # This documents the gap: can_access() accepts the bridge
        assert decision.allowed is True, (
            "DOCUMENTED GAP: can_access() accepts any bridge in the input list. "
            "Bridge governance (approval, authority) must be enforced at the store layer."
        )


# ===========================================================================
# Threat 4: Posture gaming
# ===========================================================================


class TestPostureGaming:
    """Thesis Section 12.9.4: Agent claims a higher posture than justified.

    DOCUMENTED GAP: The posture parameter to can_access() is caller-determined.
    There is no evidence validation within the access algorithm -- it trusts
    the posture value it receives. An agent that can control its own posture
    parameter can access higher-classification data by claiming DELEGATED posture.

    The defense must be at the posture assignment layer: posture should be
    determined by the runtime/supervisor based on verifiable evidence, not
    self-reported by the agent.
    """

    def test_posture_is_caller_determined(self, two_dept_org: CompiledOrg) -> None:
        """Posture is a parameter -- higher posture grants higher effective clearance.

        DOCUMENTED GAP: No evidence validation for posture claims.
        """
        role_addr = "D1-R1-T1-R1"
        clearances = {
            role_addr: RoleClearance(
                role_address=role_addr,
                max_clearance=ConfidentialityLevel.SECRET,
            ),
        }
        item = KnowledgeItem(
            item_id="secret-data",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1-R1-T1",
        )

        # At SUPERVISED posture (ceiling=RESTRICTED), SECRET data is blocked
        decision_low = can_access(
            role_address=role_addr,
            knowledge_item=item,
            posture=TrustPostureLevel.SUPERVISED,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision_low.allowed is False

        # At CONTINUOUS_INSIGHT posture (ceiling=SECRET), same data is allowed
        decision_high = can_access(
            role_address=role_addr,
            knowledge_item=item,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision_high.allowed is True, (
            "DOCUMENTED GAP: Posture is caller-determined. An agent claiming "
            "CONTINUOUS_INSIGHT when it should be SUPERVISED gains access. "
            "Posture assignment must be enforced at the runtime layer."
        )


# ===========================================================================
# Threat 5: TOCTOU (Time-of-check to Time-of-use)
# ===========================================================================


class TestTOCTOU:
    """Verify frozen dataclasses prevent post-check mutation.

    Frozen dataclasses prevent the TOCTOU attack where an attacker mutates
    an object between the access check and the actual use. If Address,
    KnowledgeItem, RoleClearance, etc. are frozen, their fields cannot be
    changed after construction.

    Also documents which types are NOT frozen (build-time types) and why.
    """

    def test_address_is_frozen(self) -> None:
        """Address dataclass must be frozen (immutable after creation)."""
        addr = Address.parse("D1-R1")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            addr.segments = ()  # type: ignore[misc]

    def test_address_segment_is_frozen(self) -> None:
        """AddressSegment must be frozen."""
        seg = AddressSegment.parse("D1")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            seg.sequence = 999  # type: ignore[misc]

    def test_knowledge_item_is_frozen(self) -> None:
        """KnowledgeItem must be frozen."""
        item = KnowledgeItem(
            item_id="test",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1",
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            item.classification = ConfidentialityLevel.PUBLIC  # type: ignore[misc]

    def test_role_clearance_is_frozen(self) -> None:
        """RoleClearance must be frozen."""
        rc = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            rc.max_clearance = ConfidentialityLevel.TOP_SECRET  # type: ignore[misc]

    def test_ksp_is_frozen(self) -> None:
        """KnowledgeSharePolicy must be frozen."""
        ksp = KnowledgeSharePolicy(
            id="ksp-1",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ksp.max_classification = ConfidentialityLevel.TOP_SECRET  # type: ignore[misc]

    def test_pact_bridge_is_frozen(self) -> None:
        """PactBridge must be frozen."""
        bridge = PactBridge(
            id="bridge-1",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            bridge.max_classification = ConfidentialityLevel.TOP_SECRET  # type: ignore[misc]

    def test_access_decision_is_frozen(self) -> None:
        """AccessDecision must be frozen."""
        dec = AccessDecision(allowed=False, reason="test")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            dec.allowed = True  # type: ignore[misc]

    def test_role_envelope_is_frozen(self) -> None:
        """RoleEnvelope must be frozen."""
        env = RoleEnvelope(
            id="env-1",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=ConstraintEnvelopeConfig(
                id="e1",
                description="test",
                confidentiality_clearance=ConfidentialityLevel.RESTRICTED,
            ),
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            env.defining_role_address = "HACKED"  # type: ignore[misc]

    def test_task_envelope_is_frozen(self) -> None:
        """TaskEnvelope must be frozen."""
        from datetime import UTC, datetime, timedelta

        te = TaskEnvelope(
            id="te-1",
            task_id="task-1",
            parent_envelope_id="env-1",
            envelope=ConstraintEnvelopeConfig(
                id="e1",
                description="test",
                confidentiality_clearance=ConfidentialityLevel.RESTRICTED,
            ),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            te.task_id = "HACKED"  # type: ignore[misc]

    def test_org_node_is_frozen(self) -> None:
        """OrgNode must be frozen (C2 security fix).

        OrgNode was made frozen=True to prevent post-compilation mutation.
        During compilation, object.__setattr__ is used for the build phase.
        After compilation, the node is immutable.
        """
        from pact.governance.addressing import NodeType

        node = OrgNode(
            address="D1-R1",
            node_type=NodeType.ROLE,
            name="Test",
            node_id="test",
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            node.name = "HACKED"  # type: ignore[misc]

    def test_compiled_org_is_frozen(self) -> None:
        """CompiledOrg must be frozen (C2 security fix).

        CompiledOrg was made frozen=True to prevent post-compilation mutation.
        The nodes dict is mutable during compilation (dict contents can be
        modified), but the CompiledOrg fields themselves cannot be reassigned.
        """
        compiled = CompiledOrg(org_id="test")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            compiled.org_id = "HACKED"  # type: ignore[misc]

    def test_role_definition_is_frozen(self) -> None:
        """RoleDefinition IS frozen (TODO-7006 security fix).

        RoleDefinition is now frozen=True to prevent post-construction mutation.
        During compilation, object.__setattr__ is used to set the address field.
        After compilation, the RoleDefinition is immutable.
        """
        rd = RoleDefinition(role_id="test", name="Test")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            rd.address = "D1-R1"  # type: ignore[misc]
