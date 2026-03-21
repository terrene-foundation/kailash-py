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

from pact.build.config.schema import (
    ConfidentialityLevel,
    DepartmentConfig,
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
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.compilation import CompiledOrg, RoleDefinition, compile_org
from pact.governance.knowledge import KnowledgeItem


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
            audit_details={"effective_clearance": "restricted", "item_classification": "secret"},
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

    def test_clearance_meets_classification_allows(self, simple_org: CompiledOrg) -> None:
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

    def test_clearance_below_classification_denies(self, simple_org: CompiledOrg) -> None:
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

    def test_secret_item_with_matching_compartments_passes(self, simple_org: CompiledOrg) -> None:
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

    def test_secret_item_missing_compartment_denies(self, simple_org: CompiledOrg) -> None:
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

    def test_ksp_grants_cross_department_access(self, two_dept_org: CompiledOrg) -> None:
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

    def test_bridge_grants_cross_department_access(self, two_dept_org: CompiledOrg) -> None:
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

    def test_bridge_classification_limit_enforced(self, two_dept_org: CompiledOrg) -> None:
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
