# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""M6 parametrized access matrix -- exhaustive coverage of the 5-step algorithm.

86 parametrized cases covering:
- 15 containment x mechanism cases
- 25 clearance level cases (5x5 matrix)
- 25 posture capping cases (5x5 matrix)
- 8 compartment cases
- 4 expired/inactive mechanism cases
- 3 bridge directionality cases
- 4 vetting status cases
- 2 default deny cases

Uses the financial services org from test_flagship_scenario.py as the fixture
pattern (R1, D1, D1-R1-D1..D3, teams, bridges).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    DepartmentConfig,
    TeamConfig,
    TrustPostureLevel,
)
from pact.build.org.builder import OrgDefinition
from pact.governance.access import (
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
)
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.compilation import CompiledOrg, RoleDefinition, compile_org
from pact.governance.knowledge import KnowledgeItem


# ---------------------------------------------------------------------------
# Shared fixture: Financial services org (same structure as flagship scenario)
# ---------------------------------------------------------------------------


@pytest.fixture
def finserv_org() -> CompiledOrg:
    """Financial services org.

    Structure:
      R1 Board of Directors (external)
        D1 Executive Office
          D1-R1 CEO
            D1-R1-D1 Compliance Division
              D1-R1-D1-R1 CCO
                D1-R1-D1-R1-T1 AML/CFT Team
                  D1-R1-D1-R1-T1-R1 AML Officer
            D1-R1-D2 Advisory Division
              D1-R1-D2-R1 Head of Advisory
                D1-R1-D2-R1-T1 Client Advisory Team
                  D1-R1-D2-R1-T1-R1 Senior Advisor
            D1-R1-D3 Trading Division
              D1-R1-D3-R1 Head of Trading
                D1-R1-D3-R1-T1 Equities Desk
                  D1-R1-D3-R1-T1-R1 Senior Trader
    """
    roles = [
        RoleDefinition(
            role_id="r-bod",
            name="Board of Directors",
            reports_to_role_id=None,
            is_external=True,
        ),
        RoleDefinition(
            role_id="r-ceo",
            name="CEO",
            reports_to_role_id="r-bod",
            is_primary_for_unit="d-exec",
        ),
        RoleDefinition(
            role_id="r-cco",
            name="Chief Compliance Officer",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-compliance",
        ),
        RoleDefinition(
            role_id="r-aml",
            name="AML Officer",
            reports_to_role_id="r-cco",
            is_primary_for_unit="t-aml",
        ),
        RoleDefinition(
            role_id="r-adv-head",
            name="Head of Advisory",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-advisory",
        ),
        RoleDefinition(
            role_id="r-advisor",
            name="Senior Advisor",
            reports_to_role_id="r-adv-head",
            is_primary_for_unit="t-client-advisory",
        ),
        RoleDefinition(
            role_id="r-trd-head",
            name="Head of Trading",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-trading",
        ),
        RoleDefinition(
            role_id="r-trader",
            name="Senior Trader",
            reports_to_role_id="r-trd-head",
            is_primary_for_unit="t-equities",
        ),
    ]

    departments = [
        DepartmentConfig(department_id="d-exec", name="Executive Office"),
        DepartmentConfig(department_id="d-compliance", name="Compliance Division"),
        DepartmentConfig(department_id="d-advisory", name="Advisory Division"),
        DepartmentConfig(department_id="d-trading", name="Trading Division"),
    ]

    teams = [
        TeamConfig(id="t-aml", name="AML/CFT Team", workspace="ws-aml"),
        TeamConfig(id="t-client-advisory", name="Client Advisory Team", workspace="ws-advisory"),
        TeamConfig(id="t-equities", name="Equities Desk", workspace="ws-trading"),
    ]

    org = OrgDefinition(
        org_id="finserv-matrix",
        name="Financial Services Corp",
        departments=departments,
        teams=teams,
        roles=roles,
    )
    return compile_org(org)


def _make_clearances(**overrides: ConfidentialityLevel) -> dict[str, RoleClearance]:
    """Build a full clearance map with an optional per-address override.

    Default: SECRET for CCO, AML, CEO; CONFIDENTIAL for everyone else.
    """
    defaults: dict[str, ConfidentialityLevel] = {
        "D1-R1": ConfidentialityLevel.SECRET,
        "D1-R1-D1-R1": ConfidentialityLevel.SECRET,
        "D1-R1-D1-R1-T1-R1": ConfidentialityLevel.SECRET,
        "D1-R1-D2-R1": ConfidentialityLevel.CONFIDENTIAL,
        "D1-R1-D2-R1-T1-R1": ConfidentialityLevel.CONFIDENTIAL,
        "D1-R1-D3-R1": ConfidentialityLevel.CONFIDENTIAL,
        "D1-R1-D3-R1-T1-R1": ConfidentialityLevel.CONFIDENTIAL,
    }
    defaults.update(overrides)
    result: dict[str, RoleClearance] = {}
    for addr, level in defaults.items():
        compartments: frozenset[str] = frozenset()
        if addr == "D1-R1-D1-R1":
            compartments = frozenset({"compliance-monitoring"})
        elif addr == "D1-R1-D1-R1-T1-R1":
            compartments = frozenset({"aml-investigations"})
        result[addr] = RoleClearance(
            role_address=addr,
            max_clearance=level,
            compartments=compartments,
            nda_signed=level in (ConfidentialityLevel.SECRET, ConfidentialityLevel.TOP_SECRET),
        )
    return result


# ===========================================================================
# 1. Containment x mechanism matrix (15 cases)
# ===========================================================================

_CONTAINMENT_CASES = [
    # (id, role_addr, item_owner, ksps_fn, bridges_fn, expected)
    # --- 4a: Same unit ---
    ("same-unit-team", "D1-R1-D3-R1-T1-R1", "D1-R1-D3-R1-T1", None, None, True),
    ("same-unit-dept", "D1-R1-D2-R1", "D1-R1-D2", None, None, True),
    # --- 4b: Downward ---
    ("downward-dept-to-team", "D1-R1-D3-R1", "D1-R1-D3-R1-T1", None, None, True),
    ("downward-ceo-to-dept", "D1-R1", "D1-R1-D2", None, None, True),
    # --- 4c: T-inherits-D ---
    ("t-inherits-d", "D1-R1-D3-R1-T1-R1", "D1-R1-D3", None, None, True),
    ("t-inherits-grandparent-d", "D1-R1-D3-R1-T1-R1", "D1", None, None, True),
    # --- Cross-division: no mechanism -> DENY ---
    ("cross-div-no-mechanism", "D1-R1-D2-R1-T1-R1", "D1-R1-D3", None, None, False),
    ("cross-dept-no-mechanism", "D1-R1-D3-R1-T1-R1", "D1-R1-D2", None, None, False),
    # --- 4d: With KSP ---
    ("ksp-grants-cross-div", "D1-R1-D2-R1-T1-R1", "D1-R1-D3", "ksp_adv_to_trd", None, True),
    ("ksp-wrong-direction", "D1-R1-D3-R1-T1-R1", "D1-R1-D2", "ksp_adv_to_trd", None, False),
    # --- 4e: With bridge ---
    ("bridge-grants-cross-div", "D1-R1-D1-R1", "D1-R1-D3", None, "bridge_cco_trd", True),
    ("bridge-wrong-role", "D1-R1-D2-R1-T1-R1", "D1-R1-D3", None, "bridge_cco_trd", False),
    # --- Both KSP and bridge ---
    (
        "both-ksp-and-bridge",
        "D1-R1-D1-R1",
        "D1-R1-D2",
        "ksp_compliance_adv",
        "bridge_cco_adv",
        True,
    ),
    # --- Root (BOD) has no clearance -> step 1 deny ---
    ("root-external-no-clearance", "R1", "D1-R1-D2", None, None, False),
    # --- Cross-team within same dept ---
    ("cross-team-same-dept-no-mech", "D1-R1-D2-R1-T1-R1", "D1-R1-D3-R1-T1", None, None, False),
]


def _make_ksp(ksp_id: str) -> KnowledgeSharePolicy:
    """Factory for KSP test instances."""
    ksps = {
        "ksp_adv_to_trd": KnowledgeSharePolicy(
            id="ksp-adv-trd",
            source_unit_address="D1-R1-D3",
            target_unit_address="D1-R1-D2",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        ),
        "ksp_compliance_adv": KnowledgeSharePolicy(
            id="ksp-compliance-adv",
            source_unit_address="D1-R1-D2",
            target_unit_address="D1-R1-D1",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        ),
    }
    return ksps[ksp_id]


def _make_bridge(bridge_id: str) -> PactBridge:
    """Factory for bridge test instances."""
    bridges = {
        "bridge_cco_trd": PactBridge(
            id="bridge-cco-trading",
            role_a_address="D1-R1-D1-R1",
            role_b_address="D1-R1-D3-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            bilateral=True,
        ),
        "bridge_cco_adv": PactBridge(
            id="bridge-cco-advisory",
            role_a_address="D1-R1-D1-R1",
            role_b_address="D1-R1-D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            bilateral=True,
        ),
    }
    return bridges[bridge_id]


@pytest.mark.parametrize(
    "case_id, role_addr, item_owner, ksp_key, bridge_key, expected",
    _CONTAINMENT_CASES,
    ids=[c[0] for c in _CONTAINMENT_CASES],
)
def test_containment_x_mechanism(
    finserv_org: CompiledOrg,
    case_id: str,
    role_addr: str,
    item_owner: str,
    ksp_key: str | None,
    bridge_key: str | None,
    expected: bool,
) -> None:
    """Parametrized containment x mechanism matrix."""
    clearances = _make_clearances()
    item = KnowledgeItem(
        item_id=f"item-{case_id}",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address=item_owner,
    )
    ksps = [_make_ksp(ksp_key)] if ksp_key else []
    bridges = [_make_bridge(bridge_key)] if bridge_key else []

    decision = can_access(
        role_address=role_addr,
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=ksps,
        bridges=bridges,
    )
    assert decision.allowed is expected, (
        f"Case '{case_id}': expected allowed={expected}, got allowed={decision.allowed}. "
        f"Reason: {decision.reason}"
    )


# ===========================================================================
# 2. Clearance level matrix (25 cases = 5 role_clearance x 5 item_classification)
# ===========================================================================

_ALL_LEVELS = [
    ConfidentialityLevel.PUBLIC,
    ConfidentialityLevel.RESTRICTED,
    ConfidentialityLevel.CONFIDENTIAL,
    ConfidentialityLevel.SECRET,
    ConfidentialityLevel.TOP_SECRET,
]

_CLEARANCE_ORDER = {
    ConfidentialityLevel.PUBLIC: 0,
    ConfidentialityLevel.RESTRICTED: 1,
    ConfidentialityLevel.CONFIDENTIAL: 2,
    ConfidentialityLevel.SECRET: 3,
    ConfidentialityLevel.TOP_SECRET: 4,
}

_CLEARANCE_CASES = [(role_cl, item_cl) for role_cl in _ALL_LEVELS for item_cl in _ALL_LEVELS]


@pytest.mark.parametrize(
    "role_clearance, item_classification",
    _CLEARANCE_CASES,
    ids=[f"role={r.value}_item={i.value}" for r, i in _CLEARANCE_CASES],
)
def test_clearance_level_matrix(
    finserv_org: CompiledOrg,
    role_clearance: ConfidentialityLevel,
    item_classification: ConfidentialityLevel,
) -> None:
    """25-case clearance matrix: role clearance vs item classification.

    At DELEGATED posture (ceiling=TOP_SECRET), effective clearance = role clearance.
    Access allowed iff effective_clearance >= item_classification.
    """
    role_addr = "D1-R1-D3-R1-T1-R1"  # Senior Trader
    clearances = {
        role_addr: RoleClearance(
            role_address=role_addr,
            max_clearance=role_clearance,
        ),
    }
    item = KnowledgeItem(
        item_id="cl-matrix-item",
        classification=item_classification,
        owning_unit_address="D1-R1-D3-R1-T1",  # Same team -> structural access
    )
    decision = can_access(
        role_address=role_addr,
        knowledge_item=item,
        posture=TrustPostureLevel.DELEGATED,  # Ceiling = TOP_SECRET
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[],
    )
    expected = _CLEARANCE_ORDER[role_clearance] >= _CLEARANCE_ORDER[item_classification]
    assert decision.allowed is expected, (
        f"Clearance {role_clearance.value} vs classification {item_classification.value}: "
        f"expected {expected}, got {decision.allowed}. Reason: {decision.reason}"
    )


# ===========================================================================
# 3. Posture capping matrix (25 cases = 5 posture x 5 item_classification)
# ===========================================================================

_POSTURE_CEILING = {
    TrustPostureLevel.PSEUDO_AGENT: ConfidentialityLevel.PUBLIC,
    TrustPostureLevel.SUPERVISED: ConfidentialityLevel.RESTRICTED,
    TrustPostureLevel.SHARED_PLANNING: ConfidentialityLevel.CONFIDENTIAL,
    TrustPostureLevel.CONTINUOUS_INSIGHT: ConfidentialityLevel.SECRET,
    TrustPostureLevel.DELEGATED: ConfidentialityLevel.TOP_SECRET,
}

_POSTURE_CASES = [(posture, item_cl) for posture in TrustPostureLevel for item_cl in _ALL_LEVELS]


@pytest.mark.parametrize(
    "posture, item_classification",
    _POSTURE_CASES,
    ids=[f"posture={p.value}_item={i.value}" for p, i in _POSTURE_CASES],
)
def test_posture_capping_matrix(
    finserv_org: CompiledOrg,
    posture: TrustPostureLevel,
    item_classification: ConfidentialityLevel,
) -> None:
    """25-case posture capping matrix.

    Role has TOP_SECRET clearance, so effective = min(TOP_SECRET, posture_ceiling).
    Access allowed iff effective_clearance >= item_classification.
    """
    role_addr = "D1-R1-D3-R1-T1-R1"
    clearances = {
        role_addr: RoleClearance(
            role_address=role_addr,
            max_clearance=ConfidentialityLevel.TOP_SECRET,
        ),
    }
    item = KnowledgeItem(
        item_id="posture-matrix-item",
        classification=item_classification,
        owning_unit_address="D1-R1-D3-R1-T1",  # Same team
    )
    decision = can_access(
        role_address=role_addr,
        knowledge_item=item,
        posture=posture,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[],
    )
    ceiling = _POSTURE_CEILING[posture]
    effective_level = min(
        _CLEARANCE_ORDER[ConfidentialityLevel.TOP_SECRET],
        _CLEARANCE_ORDER[ceiling],
    )
    expected = effective_level >= _CLEARANCE_ORDER[item_classification]
    assert decision.allowed is expected, (
        f"Posture {posture.value} (ceiling={ceiling.value}) vs item {item_classification.value}: "
        f"expected {expected}, got {decision.allowed}. Reason: {decision.reason}"
    )


# ===========================================================================
# 4. Compartment cases (8 cases)
# ===========================================================================

_COMPARTMENT_CASES = [
    # (id, role_compartments, item_compartments, item_classification, expected)
    ("secret-matching", {"alpha"}, {"alpha"}, ConfidentialityLevel.SECRET, True),
    ("secret-superset", {"alpha", "beta"}, {"alpha"}, ConfidentialityLevel.SECRET, True),
    ("secret-missing-one", {"alpha"}, {"alpha", "beta"}, ConfidentialityLevel.SECRET, False),
    ("secret-disjoint", {"gamma"}, {"alpha"}, ConfidentialityLevel.SECRET, False),
    ("secret-empty-role", set(), {"alpha"}, ConfidentialityLevel.SECRET, False),
    ("top-secret-matching", {"ts-1"}, {"ts-1"}, ConfidentialityLevel.TOP_SECRET, True),
    ("top-secret-missing", set(), {"ts-1"}, ConfidentialityLevel.TOP_SECRET, False),
    (
        "confidential-skip-compartment",
        set(),
        {"some-comp"},
        ConfidentialityLevel.CONFIDENTIAL,
        True,
    ),
]


@pytest.mark.parametrize(
    "case_id, role_comps, item_comps, item_class, expected",
    _COMPARTMENT_CASES,
    ids=[c[0] for c in _COMPARTMENT_CASES],
)
def test_compartment_enforcement(
    finserv_org: CompiledOrg,
    case_id: str,
    role_comps: set[str],
    item_comps: set[str],
    item_class: ConfidentialityLevel,
    expected: bool,
) -> None:
    """8 compartment cases: matching, superset, missing, disjoint, empty, skip."""
    role_addr = "D1-R1"  # CEO in D1 — same unit for structural access
    clearances = {
        role_addr: RoleClearance(
            role_address=role_addr,
            max_clearance=ConfidentialityLevel.TOP_SECRET,
            compartments=frozenset(role_comps),
            nda_signed=True,
        ),
    }
    item = KnowledgeItem(
        item_id=f"comp-{case_id}",
        classification=item_class,
        owning_unit_address="D1",
        compartments=frozenset(item_comps),
    )
    decision = can_access(
        role_address=role_addr,
        knowledge_item=item,
        posture=TrustPostureLevel.DELEGATED,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[],
    )
    assert decision.allowed is expected, (
        f"Compartment case '{case_id}': expected {expected}, got {decision.allowed}. "
        f"Reason: {decision.reason}"
    )


# ===========================================================================
# 5. Expired / inactive mechanism cases (4 cases)
# ===========================================================================


def test_expired_ksp_denied(finserv_org: CompiledOrg) -> None:
    """Expired KSP (expires_at in the past) must not grant access."""
    clearances = _make_clearances()
    item = KnowledgeItem(
        item_id="expired-ksp-item",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D3",
    )
    expired_ksp = KnowledgeSharePolicy(
        id="ksp-expired",
        source_unit_address="D1-R1-D3",
        target_unit_address="D1-R1-D2",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    decision = can_access(
        role_address="D1-R1-D2-R1-T1-R1",
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[expired_ksp],
        bridges=[],
    )
    assert (
        decision.allowed is False
    ), f"Expired KSP should not grant access. Reason: {decision.reason}"


def test_expired_bridge_denied(finserv_org: CompiledOrg) -> None:
    """Expired bridge (expires_at in the past) must not grant access."""
    clearances = _make_clearances()
    item = KnowledgeItem(
        item_id="expired-bridge-item",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D3",
    )
    expired_bridge = PactBridge(
        id="bridge-expired",
        role_a_address="D1-R1-D1-R1",
        role_b_address="D1-R1-D3-R1",
        bridge_type="standing",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    decision = can_access(
        role_address="D1-R1-D1-R1",
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[expired_bridge],
    )
    assert (
        decision.allowed is False
    ), f"Expired bridge should not grant access. Reason: {decision.reason}"


def test_inactive_ksp_denied(finserv_org: CompiledOrg) -> None:
    """Inactive KSP (active=False) must not grant access."""
    clearances = _make_clearances()
    item = KnowledgeItem(
        item_id="inactive-ksp-item",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D3",
    )
    inactive_ksp = KnowledgeSharePolicy(
        id="ksp-inactive",
        source_unit_address="D1-R1-D3",
        target_unit_address="D1-R1-D2",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        active=False,
    )
    decision = can_access(
        role_address="D1-R1-D2-R1-T1-R1",
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[inactive_ksp],
        bridges=[],
    )
    assert decision.allowed is False


def test_inactive_bridge_denied(finserv_org: CompiledOrg) -> None:
    """Inactive bridge (active=False) must not grant access."""
    clearances = _make_clearances()
    item = KnowledgeItem(
        item_id="inactive-bridge-item",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D3",
    )
    inactive_bridge = PactBridge(
        id="bridge-inactive",
        role_a_address="D1-R1-D1-R1",
        role_b_address="D1-R1-D3-R1",
        bridge_type="standing",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        active=False,
    )
    decision = can_access(
        role_address="D1-R1-D1-R1",
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[inactive_bridge],
    )
    assert decision.allowed is False


# ===========================================================================
# 6. Bridge directionality cases (3 cases)
# ===========================================================================


def test_bilateral_bridge_a_to_b(finserv_org: CompiledOrg) -> None:
    """Bilateral bridge: A can access B's data."""
    clearances = _make_clearances()
    item = KnowledgeItem(
        item_id="b-data",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D3",
    )
    bridge = PactBridge(
        id="bridge-bilateral",
        role_a_address="D1-R1-D1-R1",  # CCO
        role_b_address="D1-R1-D3-R1",  # Head of Trading
        bridge_type="standing",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        bilateral=True,
    )
    decision = can_access(
        role_address="D1-R1-D1-R1",
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[bridge],
    )
    assert decision.allowed is True


def test_bilateral_bridge_b_to_a(finserv_org: CompiledOrg) -> None:
    """Bilateral bridge: B can access A's data."""
    clearances = _make_clearances()
    item = KnowledgeItem(
        item_id="a-data",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D1",
    )
    bridge = PactBridge(
        id="bridge-bilateral",
        role_a_address="D1-R1-D1-R1",  # CCO
        role_b_address="D1-R1-D3-R1",  # Head of Trading
        bridge_type="standing",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        bilateral=True,
    )
    decision = can_access(
        role_address="D1-R1-D3-R1",
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[bridge],
    )
    assert decision.allowed is True


def test_unilateral_bridge_blocks_reverse(finserv_org: CompiledOrg) -> None:
    """Unilateral bridge: only A->B direction allowed. B cannot read A's data."""
    clearances = _make_clearances()
    item = KnowledgeItem(
        item_id="a-data-unilateral",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D1",
    )
    bridge = PactBridge(
        id="bridge-unilateral",
        role_a_address="D1-R1-D1-R1",  # CCO
        role_b_address="D1-R1-D3-R1",  # Head of Trading
        bridge_type="standing",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        bilateral=False,
    )
    # B (Head of Trading) trying to access A's (Compliance) data -> BLOCKED
    decision = can_access(
        role_address="D1-R1-D3-R1",
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[bridge],
    )
    assert decision.allowed is False


# ===========================================================================
# 7. Vetting status cases (4 cases)
# ===========================================================================

_VETTING_CASES = [
    ("active", VettingStatus.ACTIVE, True),
    ("pending", VettingStatus.PENDING, False),
    ("expired", VettingStatus.EXPIRED, False),
    ("revoked", VettingStatus.REVOKED, False),
]


@pytest.mark.parametrize(
    "case_id, vetting_status, expected",
    _VETTING_CASES,
    ids=[c[0] for c in _VETTING_CASES],
)
def test_vetting_status(
    finserv_org: CompiledOrg,
    case_id: str,
    vetting_status: VettingStatus,
    expected: bool,
) -> None:
    """4 vetting status cases: only ACTIVE allows access."""
    role_addr = "D1-R1-D3-R1-T1-R1"
    clearances = {
        role_addr: RoleClearance(
            role_address=role_addr,
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            vetting_status=vetting_status,
        ),
    }
    item = KnowledgeItem(
        item_id=f"vetting-{case_id}",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D3-R1-T1",  # Same team
    )
    decision = can_access(
        role_address=role_addr,
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[],
    )
    assert decision.allowed is expected, (
        f"Vetting '{case_id}': expected {expected}, got {decision.allowed}. "
        f"Reason: {decision.reason}"
    )


# ===========================================================================
# 8. Default deny cases (2 cases)
# ===========================================================================


def test_default_deny_no_clearance(finserv_org: CompiledOrg) -> None:
    """Role with no clearance entry at all -> step 1 deny."""
    item = KnowledgeItem(
        item_id="deny-no-clearance",
        classification=ConfidentialityLevel.PUBLIC,
        owning_unit_address="D1-R1-D3-R1-T1",
    )
    decision = can_access(
        role_address="D1-R1-D3-R1-T1-R1",
        knowledge_item=item,
        posture=TrustPostureLevel.DELEGATED,
        compiled_org=finserv_org,
        clearances={},
        ksps=[],
        bridges=[],
    )
    assert decision.allowed is False
    assert decision.step_failed == 1


def test_default_deny_cross_division(finserv_org: CompiledOrg) -> None:
    """Cross-division access with no mechanisms -> step 5 deny."""
    clearances = _make_clearances()
    item = KnowledgeItem(
        item_id="deny-cross-div",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D3",
    )
    decision = can_access(
        role_address="D1-R1-D2-R1-T1-R1",
        knowledge_item=item,
        posture=TrustPostureLevel.SHARED_PLANNING,
        compiled_org=finserv_org,
        clearances=clearances,
        ksps=[],
        bridges=[],
    )
    assert decision.allowed is False
    assert decision.step_failed == 5
