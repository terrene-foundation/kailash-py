# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for access enforcement — KnowledgeSharePolicy, PactBridge, and can_access().

Covers:
- TODO-2003: KnowledgeSharePolicy dataclass
- TODO-2004: PactBridge dataclass
- TODO-2005: Knowledge cascade rules (same-unit, downward, T-inherits-D)
- TODO-2006: 5-step access enforcement algorithm
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.pact.access import (
    AccessDecision,
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
)
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.compilation import CompiledOrg, RoleDefinition, compile_org
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    DepartmentConfig,
    OrgDefinition,
    TeamConfig,
    TrustPostureLevel,
)
from kailash.trust.pact.knowledge import KnowledgeItem

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_org() -> CompiledOrg:
    """Simple org: D1 (Engineering) with T1 (Backend) and T2 (Frontend).

    Structure:
      D1-R1 VP Engineering
        D1-R1-T1-R1 Backend Lead
        D1-R1-T2-R1 Frontend Lead
    """
    roles = [
        RoleDefinition(
            role_id="r-vp",
            name="VP Engineering",
            reports_to_role_id=None,
            is_primary_for_unit="d-eng",
        ),
        RoleDefinition(
            role_id="r-backend-lead",
            name="Backend Lead",
            reports_to_role_id="r-vp",
            is_primary_for_unit="t-backend",
        ),
        RoleDefinition(
            role_id="r-frontend-lead",
            name="Frontend Lead",
            reports_to_role_id="r-vp",
            is_primary_for_unit="t-frontend",
        ),
    ]
    departments = [DepartmentConfig(department_id="d-eng", name="Engineering")]
    teams = [
        TeamConfig(id="t-backend", name="Backend", workspace="ws-eng"),
        TeamConfig(id="t-frontend", name="Frontend", workspace="ws-eng"),
    ]
    org = OrgDefinition(
        org_id="simple-001",
        name="Simple Org",
        departments=departments,
        teams=teams,
        roles=roles,
    )
    return compile_org(org)


@pytest.fixture
def two_dept_org() -> CompiledOrg:
    """Two-department org for cross-department testing.

    Structure:
      D1-R1 Head of Dept A
        D1-R1-T1-R1 Team A1 Lead
      D2-R1 Head of Dept B
        D2-R1-T1-R1 Team B1 Lead
    """
    roles = [
        RoleDefinition(
            role_id="r-head-a",
            name="Head of Dept A",
            reports_to_role_id=None,
            is_primary_for_unit="d-a",
        ),
        RoleDefinition(
            role_id="r-team-a1",
            name="Team A1 Lead",
            reports_to_role_id="r-head-a",
            is_primary_for_unit="t-a1",
        ),
        RoleDefinition(
            role_id="r-head-b",
            name="Head of Dept B",
            reports_to_role_id=None,
            is_primary_for_unit="d-b",
        ),
        RoleDefinition(
            role_id="r-team-b1",
            name="Team B1 Lead",
            reports_to_role_id="r-head-b",
            is_primary_for_unit="t-b1",
        ),
    ]
    departments = [
        DepartmentConfig(department_id="d-a", name="Department A"),
        DepartmentConfig(department_id="d-b", name="Department B"),
    ]
    teams = [
        TeamConfig(id="t-a1", name="Team A1", workspace="ws-a"),
        TeamConfig(id="t-b1", name="Team B1", workspace="ws-b"),
    ]
    org = OrgDefinition(
        org_id="two-dept-001",
        name="Two Dept Org",
        departments=departments,
        teams=teams,
        roles=roles,
    )
    return compile_org(org)


# ---------------------------------------------------------------------------
# TODO-2003: KnowledgeSharePolicy
# ---------------------------------------------------------------------------


class TestKnowledgeSharePolicy:
    """KnowledgeSharePolicy frozen dataclass."""

    def test_basic_construction(self) -> None:
        ksp = KnowledgeSharePolicy(
            id="ksp-001",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
        assert ksp.id == "ksp-001"
        assert ksp.source_unit_address == "D1"
        assert ksp.target_unit_address == "D2"
        assert ksp.max_classification == ConfidentialityLevel.RESTRICTED

    def test_defaults(self) -> None:
        ksp = KnowledgeSharePolicy(
            id="ksp-002",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.PUBLIC,
        )
        assert ksp.compartments == frozenset()
        assert ksp.created_by_role_address == ""
        assert ksp.active is True
        assert ksp.expires_at is None

    def test_with_compartments(self) -> None:
        ksp = KnowledgeSharePolicy(
            id="ksp-003",
            source_unit_address="D1-R1-D1",
            target_unit_address="D1-R1-D2",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            compartments=frozenset({"compliance-reports"}),
        )
        assert "compliance-reports" in ksp.compartments

    def test_frozen_immutability(self) -> None:
        ksp = KnowledgeSharePolicy(
            id="ksp-004",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.PUBLIC,
        )
        with pytest.raises(AttributeError):
            ksp.active = False  # type: ignore[misc]

    def test_with_expiry(self) -> None:
        expiry = datetime(2026, 12, 31, tzinfo=timezone.utc)
        ksp = KnowledgeSharePolicy(
            id="ksp-005",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.RESTRICTED,
            expires_at=expiry,
        )
        assert ksp.expires_at == expiry


# ---------------------------------------------------------------------------
# TODO-2004: PactBridge
# ---------------------------------------------------------------------------


class TestPactBridge:
    """PactBridge frozen dataclass."""

    def test_basic_construction(self) -> None:
        bridge = PactBridge(
            id="bridge-001",
            role_a_address="D1-R1-D1-R1",
            role_b_address="D1-R1-D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        assert bridge.id == "bridge-001"
        assert bridge.role_a_address == "D1-R1-D1-R1"
        assert bridge.role_b_address == "D1-R1-D2-R1"
        assert bridge.bridge_type == "standing"
        assert bridge.max_classification == ConfidentialityLevel.CONFIDENTIAL

    def test_defaults(self) -> None:
        bridge = PactBridge(
            id="bridge-002",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="scoped",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
        assert bridge.operational_scope == ()
        assert bridge.bilateral is True
        assert bridge.expires_at is None
        assert bridge.active is True

    def test_with_operational_scope(self) -> None:
        bridge = PactBridge(
            id="bridge-003",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="scoped",
            max_classification=ConfidentialityLevel.RESTRICTED,
            operational_scope=("audit", "reporting"),
        )
        assert "audit" in bridge.operational_scope
        assert "reporting" in bridge.operational_scope

    def test_bridge_types(self) -> None:
        """Allowed bridge types: standing, scoped, ad_hoc."""
        for btype in ("standing", "scoped", "ad_hoc"):
            bridge = PactBridge(
                id=f"bridge-{btype}",
                role_a_address="D1-R1",
                role_b_address="D2-R1",
                bridge_type=btype,
                max_classification=ConfidentialityLevel.PUBLIC,
            )
            assert bridge.bridge_type == btype

    def test_frozen_immutability(self) -> None:
        bridge = PactBridge(
            id="bridge-004",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.PUBLIC,
        )
        with pytest.raises(AttributeError):
            bridge.active = False  # type: ignore[misc]

    def test_unilateral_bridge(self) -> None:
        bridge = PactBridge(
            id="bridge-005",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
            bilateral=False,
        )
        assert bridge.bilateral is False


# ---------------------------------------------------------------------------
# TODO-2006: AccessDecision dataclass
# ---------------------------------------------------------------------------


class TestAccessDecision:
    """AccessDecision frozen dataclass."""

    def test_allowed_decision(self) -> None:
        dec = AccessDecision(allowed=True, reason="Same unit access")
        assert dec.allowed is True
        assert dec.step_failed is None
        assert dec.audit_details == {}

    def test_denied_decision(self) -> None:
        dec = AccessDecision(
            allowed=False,
            reason="No access path found",
            step_failed=5,
        )
        assert dec.allowed is False
        assert dec.step_failed == 5

    def test_denied_with_audit_details(self) -> None:
        dec = AccessDecision(
            allowed=False,
            reason="Classification check failed",
            step_failed=2,
            audit_details={
                "effective_clearance": "restricted",
                "item_classification": "secret",
            },
        )
        assert dec.audit_details["effective_clearance"] == "restricted"

    def test_frozen_immutability(self) -> None:
        dec = AccessDecision(allowed=True, reason="test")
        with pytest.raises(AttributeError):
            dec.allowed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TODO-2006: can_access() — Step 1 & 2: Classification check
# ---------------------------------------------------------------------------


class TestCanAccessClassification:
    """Steps 1 and 2: effective clearance vs item classification."""

    def test_clearance_meets_classification_allows(
        self, simple_org: CompiledOrg
    ) -> None:
        """Role with CONFIDENTIAL clearance can access RESTRICTED item."""
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="test-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is True

    def test_clearance_below_classification_denies(
        self, simple_org: CompiledOrg
    ) -> None:
        """Role with RESTRICTED clearance cannot access SECRET item."""
        clearances = {
            "D1-R1-T1-R1": RoleClearance(
                role_address="D1-R1-T1-R1",
                max_clearance=ConfidentialityLevel.RESTRICTED,
            ),
        }
        item = KnowledgeItem(
            item_id="secret-item",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1-R1-T1",
        )
        decision = can_access(
            role_address="D1-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 2

    def test_posture_caps_clearance(self, simple_org: CompiledOrg) -> None:
        """Role has TOP_SECRET clearance but PSEUDO_AGENT posture caps to PUBLIC."""
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.TOP_SECRET,
            ),
        }
        item = KnowledgeItem(
            item_id="restricted-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.PSEUDO_AGENT,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 2

    def test_missing_clearance_denies(self, simple_org: CompiledOrg) -> None:
        """Role with no clearance entry is denied."""
        item = KnowledgeItem(
            item_id="any-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=simple_org,
            clearances={},  # No clearance for D1-R1
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 1


# ---------------------------------------------------------------------------
# TODO-2006: can_access() — Step 3: Compartment check
# ---------------------------------------------------------------------------


class TestCanAccessCompartments:
    """Step 3: SECRET/TOP_SECRET items require compartment match."""

    def test_secret_item_with_matching_compartments_passes(
        self, simple_org: CompiledOrg
    ) -> None:
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.SECRET,
                compartments=frozenset({"alpha", "beta"}),
            ),
        }
        item = KnowledgeItem(
            item_id="secret-item",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1",
            compartments=frozenset({"alpha"}),
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is True

    def test_secret_item_missing_compartment_denies(
        self, simple_org: CompiledOrg
    ) -> None:
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.SECRET,
                compartments=frozenset({"alpha"}),
            ),
        }
        item = KnowledgeItem(
            item_id="secret-item",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1",
            compartments=frozenset({"alpha", "beta"}),
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 3

    def test_public_item_no_compartment_check(self, simple_org: CompiledOrg) -> None:
        """PUBLIC/RESTRICTED/CONFIDENTIAL items skip compartment check."""
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                compartments=frozenset(),  # No compartments
            ),
        }
        item = KnowledgeItem(
            item_id="conf-item",
            classification=ConfidentialityLevel.CONFIDENTIAL,
            owning_unit_address="D1",
            compartments=frozenset({"some-compartment"}),  # Has compartments
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        # Should pass compartment check (only enforced at SECRET+)
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# TODO-2005/2006: can_access() — Step 4a: Same unit
# ---------------------------------------------------------------------------


class TestCanAccessSameUnit:
    """Step 4a: role in same unit as item owner."""

    def test_role_in_same_team_allowed(self, simple_org: CompiledOrg) -> None:
        """Role in T1 can access T1-owned item."""
        clearances = {
            "D1-R1-T1-R1": RoleClearance(
                role_address="D1-R1-T1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="backend-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-T1",
        )
        decision = can_access(
            role_address="D1-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# TODO-2005/2006: can_access() — Step 4b: Downward access
# ---------------------------------------------------------------------------


class TestCanAccessDownward:
    """Step 4b: role address is prefix of item owner (downward visibility)."""

    def test_department_head_sees_team_data(self, simple_org: CompiledOrg) -> None:
        """VP Engineering (D1-R1) can see Backend team (D1-R1-T1) data."""
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="team-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-T1",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# TODO-2005/2006: can_access() — Step 4c: T-inherits-D
# ---------------------------------------------------------------------------


class TestCanAccessTInheritsD:
    """Step 4c: role in T can access parent D's data."""

    def test_team_role_accesses_department_data(self, simple_org: CompiledOrg) -> None:
        """Backend Lead (D1-R1-T1-R1) can access Engineering department (D1) data."""
        clearances = {
            "D1-R1-T1-R1": RoleClearance(
                role_address="D1-R1-T1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="dept-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        decision = can_access(
            role_address="D1-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# TODO-2006: can_access() — Step 4d: KSP
# ---------------------------------------------------------------------------


class TestCanAccessKSP:
    """Step 4d: KnowledgeSharePolicy grants cross-unit access."""

    def test_ksp_grants_cross_department_access(
        self, two_dept_org: CompiledOrg
    ) -> None:
        """KSP from Dept A to Dept B allows Team B1 to read Dept A data."""
        clearances = {
            "D2-R1-T1-R1": RoleClearance(
                role_address="D2-R1-T1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="dept-a-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        ksp = KnowledgeSharePolicy(
            id="ksp-a-to-b",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        decision = can_access(
            role_address="D2-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[ksp],
            bridges=[],
        )
        assert decision.allowed is True

    def test_ksp_classification_limit_enforced(self, two_dept_org: CompiledOrg) -> None:
        """KSP with max RESTRICTED blocks SECRET items."""
        clearances = {
            "D2-R1-T1-R1": RoleClearance(
                role_address="D2-R1-T1-R1",
                max_clearance=ConfidentialityLevel.SECRET,
            ),
        }
        item = KnowledgeItem(
            item_id="secret-a-item",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1",
        )
        ksp = KnowledgeSharePolicy(
            id="ksp-limited",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
        decision = can_access(
            role_address="D2-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[ksp],
            bridges=[],
        )
        assert decision.allowed is False

    def test_inactive_ksp_ignored(self, two_dept_org: CompiledOrg) -> None:
        """Inactive KSP does not grant access."""
        clearances = {
            "D2-R1-T1-R1": RoleClearance(
                role_address="D2-R1-T1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="dept-a-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        ksp = KnowledgeSharePolicy(
            id="ksp-inactive",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            active=False,
        )
        decision = can_access(
            role_address="D2-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[ksp],
            bridges=[],
        )
        assert decision.allowed is False


# ---------------------------------------------------------------------------
# TODO-2006: can_access() — Step 4e: Bridge
# ---------------------------------------------------------------------------


class TestCanAccessBridge:
    """Step 4e: PactBridge grants role-to-role cross-unit access."""

    def test_bridge_grants_cross_department_access(
        self, two_dept_org: CompiledOrg
    ) -> None:
        """Bridge from Head of Dept A to Head of Dept B allows access."""
        clearances = {
            "D2-R1": RoleClearance(
                role_address="D2-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="dept-a-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        bridge = PactBridge(
            id="bridge-ab",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        decision = can_access(
            role_address="D2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[bridge],
        )
        assert decision.allowed is True

    def test_bridge_classification_limit_enforced(
        self, two_dept_org: CompiledOrg
    ) -> None:
        """Bridge with max RESTRICTED blocks SECRET items."""
        clearances = {
            "D2-R1": RoleClearance(
                role_address="D2-R1",
                max_clearance=ConfidentialityLevel.SECRET,
            ),
        }
        item = KnowledgeItem(
            item_id="secret-a-item",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1",
        )
        bridge = PactBridge(
            id="bridge-limited",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
        decision = can_access(
            role_address="D2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[bridge],
        )
        assert decision.allowed is False

    def test_bridge_bilateral_works_both_ways(self, two_dept_org: CompiledOrg) -> None:
        """Bilateral bridge allows access from B to A (role_b accessing role_a's data)."""
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="dept-b-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D2",
        )
        bridge = PactBridge(
            id="bridge-bilateral",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            bilateral=True,
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[bridge],
        )
        assert decision.allowed is True

    def test_bridge_unilateral_blocks_reverse(self, two_dept_org: CompiledOrg) -> None:
        """Unilateral bridge: role_a can access role_b's data but not reverse."""
        clearances = {
            "D2-R1": RoleClearance(
                role_address="D2-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="dept-a-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        bridge = PactBridge(
            id="bridge-unilateral",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            bilateral=False,
        )
        # role_b (D2-R1) trying to access role_a's data (D1) — unilateral blocks this
        decision = can_access(
            role_address="D2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[bridge],
        )
        assert decision.allowed is False

    def test_inactive_bridge_ignored(self, two_dept_org: CompiledOrg) -> None:
        """Inactive bridge does not grant access."""
        clearances = {
            "D2-R1": RoleClearance(
                role_address="D2-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="dept-a-item",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        bridge = PactBridge(
            id="bridge-inactive",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            active=False,
        )
        decision = can_access(
            role_address="D2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[bridge],
        )
        assert decision.allowed is False


# ---------------------------------------------------------------------------
# TODO-2006: can_access() — Step 5: Default deny
# ---------------------------------------------------------------------------


class TestCanAccessDefaultDeny:
    """Step 5: no access path found means DENY (fail-closed)."""

    def test_no_access_path_denies(self, two_dept_org: CompiledOrg) -> None:
        """Cross-department access with no KSP or bridge is denied."""
        clearances = {
            "D2-R1-T1-R1": RoleClearance(
                role_address="D2-R1-T1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="dept-a-secret",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        decision = can_access(
            role_address="D2-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=two_dept_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 5

    def test_cross_team_no_access_path(self, simple_org: CompiledOrg) -> None:
        """Team A cannot access Team B data without KSP or bridge."""
        clearances = {
            "D1-R1-T2-R1": RoleClearance(
                role_address="D1-R1-T2-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="backend-only",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-T1",
        )
        decision = can_access(
            role_address="D1-R1-T2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 5


# ---------------------------------------------------------------------------
# Vetting status check
# ---------------------------------------------------------------------------


class TestCanAccessVettingStatus:
    """Non-ACTIVE vetting status should deny access."""

    def test_expired_vetting_denies(self, simple_org: CompiledOrg) -> None:
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                vetting_status=VettingStatus.EXPIRED,
            ),
        }
        item = KnowledgeItem(
            item_id="any",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D1",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 1

    def test_revoked_vetting_denies(self, simple_org: CompiledOrg) -> None:
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                vetting_status=VettingStatus.REVOKED,
            ),
        }
        item = KnowledgeItem(
            item_id="any",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D1",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 1


# ===========================================================================
# Epic #1375: KSP/Bridge access-control scoping & precedence (#1368-#1374)
# ===========================================================================


def _clearance(addr: str, level: ConfidentialityLevel) -> RoleClearance:
    return RoleClearance(role_address=addr, max_clearance=level)


def _cross_barrier_item(
    classification: ConfidentialityLevel = ConfidentialityLevel.RESTRICTED,
    *,
    path: str | None = None,
    knowledge_type: str | None = None,
) -> KnowledgeItem:
    """Item owned by D2 (no structural path from a D1 role -> forces 4d/4e)."""
    return KnowledgeItem(
        item_id="x-item",
        classification=classification,
        owning_unit_address="D2",
        path=path,
        knowledge_type=knowledge_type,
    )


def _permissive_bridge(
    max_classification: ConfidentialityLevel = ConfidentialityLevel.SECRET,
    *,
    shared_paths: tuple[str, ...] = (),
) -> PactBridge:
    """A bridge D1-R1 <-> D2-R1 that grants D1-R1 access to D2-owned items."""
    return PactBridge(
        id="b-permissive",
        role_a_address="D1-R1",
        role_b_address="D2-R1",
        bridge_type="standing",
        max_classification=max_classification,
        shared_paths=shared_paths,
    )


# ---------------------------------------------------------------------------
# #1368-#1374: new KSP scope fields (dataclass surface)
# ---------------------------------------------------------------------------


class TestKSPScopeFields:
    """New KnowledgeSharePolicy scoping fields and their defaults."""

    def test_scope_field_defaults(self) -> None:
        ksp = KnowledgeSharePolicy(
            id="k",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
        assert ksp.min_clearance is None
        assert ksp.shared_paths == ()
        assert ksp.shared_types == frozenset()
        assert ksp.shared_classifications == frozenset()
        assert ksp.conditions == {}

    def test_scope_fields_set(self) -> None:
        ksp = KnowledgeSharePolicy(
            id="k",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
            min_clearance=ConfidentialityLevel.CONFIDENTIAL,
            shared_paths=("/finance/*",),
            shared_types=frozenset({"report"}),
            shared_classifications=frozenset({ConfidentialityLevel.RESTRICTED}),
            conditions={"time_window": {"start": "09:00", "end": "17:00"}},
        )
        assert ksp.min_clearance == ConfidentialityLevel.CONFIDENTIAL
        assert ksp.shared_paths == ("/finance/*",)
        assert ksp.shared_types == frozenset({"report"})

    def test_shared_paths_traversal_rejected_at_construction(self) -> None:
        with pytest.raises(ValueError, match="traversal"):
            KnowledgeSharePolicy(
                id="k",
                source_unit_address="D2",
                target_unit_address="D1",
                max_classification=ConfidentialityLevel.RESTRICTED,
                shared_paths=("/finance/../etc",),
            )


class TestBridgeScopeFields:
    """New PactBridge.shared_paths field and traversal rejection."""

    def test_shared_paths_default_empty(self) -> None:
        bridge = PactBridge(
            id="b",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
        assert bridge.shared_paths == ()

    def test_shared_paths_traversal_rejected_at_construction(self) -> None:
        with pytest.raises(ValueError, match="traversal"):
            PactBridge(
                id="b",
                role_a_address="D1-R1",
                role_b_address="D2-R1",
                bridge_type="standing",
                max_classification=ConfidentialityLevel.RESTRICTED,
                shared_paths=("../secret",),
            )


# ---------------------------------------------------------------------------
# #1372: deny-precedence — a matching deny-KSP suppresses a permissive bridge
# ---------------------------------------------------------------------------


class TestKSPDenyPrecedence:
    """The #1372 keystone: KSP deny suppresses the bridge fallback."""

    def test_matching_deny_ksp_suppresses_permissive_bridge(
        self, two_dept_org: CompiledOrg
    ) -> None:
        # KSP matches D2->D1 addressing but DENIES (item path outside scope);
        # a permissive bridge that would otherwise grant MUST be suppressed.
        ksp = KnowledgeSharePolicy(
            id="k-deny",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
            shared_paths=("/finance/*",),
        )
        item = _cross_barrier_item(path="/hr/payroll")  # outside /finance/*
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=two_dept_org,
            clearances={"D1-R1": _clearance("D1-R1", ConfidentialityLevel.SECRET)},
            ksps=[ksp],
            bridges=[_permissive_bridge()],
        )
        assert decision.allowed is False
        assert decision.step_failed == 4
        assert decision.audit_details["access_path"] == "ksp_deny"
        assert "shared_paths" in decision.audit_details["deny_reason"]

    def test_no_matching_ksp_leaves_bridge_available(
        self, two_dept_org: CompiledOrg
    ) -> None:
        # KSP targets a DIFFERENT unit (D3) -> does not apply -> bridge grants.
        ksp = KnowledgeSharePolicy(
            id="k-other",
            source_unit_address="D2",
            target_unit_address="D3",
            max_classification=ConfidentialityLevel.SECRET,
            shared_paths=("/finance/*",),
        )
        item = _cross_barrier_item(path="/hr/payroll")
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=two_dept_org,
            clearances={"D1-R1": _clearance("D1-R1", ConfidentialityLevel.SECRET)},
            ksps=[ksp],
            bridges=[_permissive_bridge()],
        )
        assert decision.allowed is True
        assert decision.audit_details["access_path"] == "bridge"

    def test_granting_ksp_wins_over_sibling_deny_ksp(
        self, two_dept_org: CompiledOrg
    ) -> None:
        deny_ksp = KnowledgeSharePolicy(
            id="k-deny",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
            shared_types=frozenset({"report"}),
        )
        grant_ksp = KnowledgeSharePolicy(
            id="k-grant",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
        )
        item = _cross_barrier_item(knowledge_type="dataset")  # fails deny_ksp
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=two_dept_org,
            clearances={"D1-R1": _clearance("D1-R1", ConfidentialityLevel.SECRET)},
            ksps=[deny_ksp, grant_ksp],
            bridges=[],
        )
        assert decision.allowed is True
        assert decision.audit_details["ksp_id"] == "k-grant"

    def test_unscoped_ksp_still_grants(self, two_dept_org: CompiledOrg) -> None:
        ksp = KnowledgeSharePolicy(
            id="k",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=_cross_barrier_item(),
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=two_dept_org,
            clearances={"D1-R1": _clearance("D1-R1", ConfidentialityLevel.SECRET)},
            ksps=[ksp],
            bridges=[],
        )
        assert decision.allowed is True
        assert decision.audit_details["access_path"] == "ksp"


# ---------------------------------------------------------------------------
# #1368: recipient clearance floor
# ---------------------------------------------------------------------------


class TestKSPClearanceFloor:
    def _decide(self, org, recipient_level, min_clearance):
        ksp = KnowledgeSharePolicy(
            id="k",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
            min_clearance=min_clearance,
        )
        return can_access(
            role_address="D1-R1",
            knowledge_item=_cross_barrier_item(ConfidentialityLevel.RESTRICTED),
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=org,
            clearances={"D1-R1": _clearance("D1-R1", recipient_level)},
            ksps=[ksp],
            bridges=[],
        )

    def test_recipient_below_floor_denied(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            ConfidentialityLevel.CONFIDENTIAL,
            ConfidentialityLevel.SECRET,
        )
        assert d.allowed is False
        assert "min_clearance" in d.audit_details["deny_reason"]

    def test_recipient_at_floor_allowed(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org, ConfidentialityLevel.SECRET, ConfidentialityLevel.SECRET
        )
        assert d.allowed is True


# ---------------------------------------------------------------------------
# #1369 / #1370 / #1371: path / type / classification-set scope
# ---------------------------------------------------------------------------


class TestKSPItemScoping:
    def _ksp(self, **kw) -> KnowledgeSharePolicy:
        return KnowledgeSharePolicy(
            id="k",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
            **kw,
        )

    def _decide(self, org, ksp, item) -> AccessDecision:
        return can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=org,
            clearances={"D1-R1": _clearance("D1-R1", ConfidentialityLevel.SECRET)},
            ksps=[ksp],
            bridges=[],
        )

    def test_shared_paths_match_allows(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            self._ksp(shared_paths=("/finance/*",)),
            _cross_barrier_item(path="/finance/q3"),
        )
        assert d.allowed is True

    def test_shared_paths_nonmatch_denies(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            self._ksp(shared_paths=("/finance/*",)),
            _cross_barrier_item(path="/hr/x"),
        )
        assert d.allowed is False
        assert "shared_paths" in d.audit_details["deny_reason"]

    def test_shared_paths_untagged_item_denied(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org, self._ksp(shared_paths=("/finance/*",)), _cross_barrier_item()
        )
        assert d.allowed is False

    def test_shared_paths_traversal_item_denied(
        self, two_dept_org: CompiledOrg
    ) -> None:
        d = self._decide(
            two_dept_org,
            self._ksp(shared_paths=("*",)),
            _cross_barrier_item(path="/finance/../etc"),
        )
        assert d.allowed is False

    def test_shared_types_match_allows(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            self._ksp(shared_types=frozenset({"report"})),
            _cross_barrier_item(knowledge_type="report"),
        )
        assert d.allowed is True

    def test_shared_types_nonmatch_denies(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            self._ksp(shared_types=frozenset({"report"})),
            _cross_barrier_item(knowledge_type="memo"),
        )
        assert d.allowed is False
        assert "shared_types" in d.audit_details["deny_reason"]

    def test_shared_classifications_excluded_below_ceiling_denied(
        self, two_dept_org: CompiledOrg
    ) -> None:
        # ceiling SECRET admits SECRET, but the SET excludes it.
        d = self._decide(
            two_dept_org,
            self._ksp(
                shared_classifications=frozenset(
                    {ConfidentialityLevel.RESTRICTED, ConfidentialityLevel.CONFIDENTIAL}
                )
            ),
            _cross_barrier_item(ConfidentialityLevel.SECRET),
        )
        assert d.allowed is False
        assert "shared_classifications" in d.audit_details["deny_reason"]

    def test_shared_classifications_member_allowed(
        self, two_dept_org: CompiledOrg
    ) -> None:
        d = self._decide(
            two_dept_org,
            self._ksp(
                shared_classifications=frozenset({ConfidentialityLevel.CONFIDENTIAL})
            ),
            _cross_barrier_item(ConfidentialityLevel.CONFIDENTIAL),
        )
        assert d.allowed is True


# ---------------------------------------------------------------------------
# #1374: time_window / environment conditions
# ---------------------------------------------------------------------------


class TestKSPConditions:
    def _ksp(self, conditions) -> KnowledgeSharePolicy:
        return KnowledgeSharePolicy(
            id="k",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
            conditions=conditions,
        )

    def _decide(self, org, ksp, *, now=None, environment=None) -> AccessDecision:
        return can_access(
            role_address="D1-R1",
            knowledge_item=_cross_barrier_item(),
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=org,
            clearances={"D1-R1": _clearance("D1-R1", ConfidentialityLevel.SECRET)},
            ksps=[ksp],
            bridges=[],
            now=now,
            environment=environment,
        )

    def test_time_window_inside_allows(self, two_dept_org: CompiledOrg) -> None:
        noon = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        d = self._decide(
            two_dept_org,
            self._ksp({"time_window": {"start": "09:00", "end": "17:00"}}),
            now=noon,
        )
        assert d.allowed is True

    def test_time_window_outside_denies(self, two_dept_org: CompiledOrg) -> None:
        night = datetime(2026, 6, 18, 23, 0, tzinfo=timezone.utc)
        d = self._decide(
            two_dept_org,
            self._ksp({"time_window": {"start": "09:00", "end": "17:00"}}),
            now=night,
        )
        assert d.allowed is False
        assert "time_window" in d.audit_details["deny_reason"]

    def test_overnight_window_allows(self, two_dept_org: CompiledOrg) -> None:
        night = datetime(2026, 6, 18, 23, 0, tzinfo=timezone.utc)
        d = self._decide(
            two_dept_org,
            self._ksp({"time_window": {"start": "22:00", "end": "06:00"}}),
            now=night,
        )
        assert d.allowed is True

    def test_environment_match_allows(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            self._ksp({"environment": {"network_zone": "internal"}}),
            environment={"network_zone": "internal"},
        )
        assert d.allowed is True

    def test_environment_mismatch_denies(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            self._ksp({"environment": {"network_zone": "internal"}}),
            environment={"network_zone": "dmz"},
        )
        assert d.allowed is False
        assert "environment" in d.audit_details["deny_reason"]

    def test_unknown_condition_fails_closed(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(two_dept_org, self._ksp({"bogus_key": 1}))
        assert d.allowed is False
        assert "unrecognized condition" in d.audit_details["deny_reason"]


# ---------------------------------------------------------------------------
# #1373: bridge path scope + traversal guard
# ---------------------------------------------------------------------------


class TestBridgeSharedPaths:
    def _decide(self, org, bridge, item) -> AccessDecision:
        return can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=org,
            clearances={"D1-R1": _clearance("D1-R1", ConfidentialityLevel.SECRET)},
            ksps=[],
            bridges=[bridge],
        )

    def test_bridge_path_match_allows(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            _permissive_bridge(shared_paths=("/finance/*",)),
            _cross_barrier_item(path="/finance/q3"),
        )
        assert d.allowed is True

    def test_bridge_path_nonmatch_denies(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            _permissive_bridge(shared_paths=("/finance/*",)),
            _cross_barrier_item(path="/hr/x"),
        )
        assert d.allowed is False
        assert d.step_failed == 5  # no bridge grants -> fall-closed deny

    def test_bridge_traversal_item_denied(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org,
            _permissive_bridge(shared_paths=("*",)),
            _cross_barrier_item(path="/a/../etc"),
        )
        assert d.allowed is False

    def test_unscoped_bridge_still_grants(self, two_dept_org: CompiledOrg) -> None:
        d = self._decide(
            two_dept_org, _permissive_bridge(), _cross_barrier_item(path="/anywhere")
        )
        assert d.allowed is True


# ---------------------------------------------------------------------------
# #1374 follow-up: injected `now` governs ALL time-evaluated checks
# (KSP expiry AND bridge expiry — determinism parity, redteam MED-1)
# ---------------------------------------------------------------------------


class TestExpiryNowSymmetry:
    """Both KSP and bridge expiry MUST honor the injected `now` (not wall-clock)."""

    def _decide(self, org, *, ksps, bridges, now) -> AccessDecision:
        return can_access(
            role_address="D1-R1",
            knowledge_item=_cross_barrier_item(),
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=org,
            clearances={"D1-R1": _clearance("D1-R1", ConfidentialityLevel.SECRET)},
            ksps=ksps,
            bridges=bridges,
            now=now,
        )

    def test_bridge_expired_per_injected_now_denied(
        self, two_dept_org: CompiledOrg
    ) -> None:
        bridge = PactBridge(
            id="b-exp",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.SECRET,
            expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        # now is AFTER expiry -> bridge treated as expired -> no access path.
        d = self._decide(
            two_dept_org,
            ksps=[],
            bridges=[bridge],
            now=datetime(2026, 6, 18, tzinfo=timezone.utc),
        )
        assert d.allowed is False
        assert d.step_failed == 5

    def test_bridge_unexpired_per_injected_now_allowed(
        self, two_dept_org: CompiledOrg
    ) -> None:
        bridge = PactBridge(
            id="b-live",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.SECRET,
            expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        d = self._decide(
            two_dept_org,
            ksps=[],
            bridges=[bridge],
            now=datetime(2026, 6, 18, tzinfo=timezone.utc),
        )
        assert d.allowed is True
        assert d.audit_details["access_path"] == "bridge"

    def test_ksp_expired_per_injected_now_denied(
        self, two_dept_org: CompiledOrg
    ) -> None:
        ksp = KnowledgeSharePolicy(
            id="k-exp",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
            expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        # KSP expired per injected now -> not applicable -> falls to step 5.
        d = self._decide(
            two_dept_org,
            ksps=[ksp],
            bridges=[],
            now=datetime(2026, 6, 18, tzinfo=timezone.utc),
        )
        assert d.allowed is False
        assert d.step_failed == 5


class TestKSPMalformedTimeWindow:
    """#1374 fail-closed: a str-typed-but-non-HH:MM time_window MUST deny (redteam MED-3)."""

    def _decide(self, org, window, now) -> AccessDecision:
        ksp = KnowledgeSharePolicy(
            id="k",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
            conditions={"time_window": window},
        )
        return can_access(
            role_address="D1-R1",
            knowledge_item=_cross_barrier_item(),
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=org,
            clearances={"D1-R1": _clearance("D1-R1", ConfidentialityLevel.SECRET)},
            ksps=[ksp],
            bridges=[],
            now=now,
        )

    def test_unpadded_hour_denies_even_at_noon(self, two_dept_org: CompiledOrg) -> None:
        # "9" sorts lexicographically ABOVE "17"; without HH:MM validation this
        # silently GRANTED at noon. MUST now fail closed.
        noon = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        d = self._decide(two_dept_org, {"start": "9", "end": "17"}, noon)
        assert d.allowed is False
        assert "malformed time_window" in d.audit_details["deny_reason"]

    def test_out_of_range_hour_denies(self, two_dept_org: CompiledOrg) -> None:
        noon = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        d = self._decide(two_dept_org, {"start": "25:00", "end": "17:00"}, noon)
        assert d.allowed is False
        assert "malformed time_window" in d.audit_details["deny_reason"]

    def test_non_time_garbage_denies(self, two_dept_org: CompiledOrg) -> None:
        noon = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        d = self._decide(two_dept_org, {"start": "morning", "end": "evening"}, noon)
        assert d.allowed is False
