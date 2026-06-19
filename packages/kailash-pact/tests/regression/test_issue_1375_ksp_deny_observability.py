# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: KSP-deny decisions carry discrete, SIEM-queryable audit fields.

Epic #1375 follow-up (security-reviewer R1 Finding 5 — SIEM queryability). The
KSP Step-4d deny path historically collapsed all structured deny-context into a
single free-text ``deny_reason`` string, so a SIEM could not query "which
narrowing condition denied" or "which compartments were missing" without regex.

This pins the parity with the Step-3 clearance compartment-deny (which already
emits discrete ``missing_compartments`` / ``item_compartments``): every KSP deny
now emits a ``deny_code`` discriminator plus condition-specific discrete fields
spread as top-level ``audit_details`` keys, while keeping the human
``deny_reason`` string for backward compatibility. ``/explain`` surfaces the
``deny_code`` + denying KSP id.
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.access import KnowledgeSharePolicy, can_access
from kailash.trust.pact.clearance import RoleClearance
from kailash.trust.pact.compilation import RoleDefinition, compile_org
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    DepartmentConfig,
    OrgDefinition,
    TrustPostureLevel,
)
from kailash.trust.pact.explain import explain_access
from kailash.trust.pact.knowledge import KnowledgeItem

_ROLE = "D1-R1"


def _two_dept_org():
    """Two independent departments (D1 + D2, no structural access path)."""
    org = OrgDefinition(
        org_id="ksp-deny-obs-001",
        name="KSP Deny Observability Org",
        departments=[
            DepartmentConfig(department_id="d-a", name="Dept A"),
            DepartmentConfig(department_id="d-b", name="Dept B"),
        ],
        teams=[],
        roles=[
            RoleDefinition(role_id="r-a", name="Head A", is_primary_for_unit="d-a"),
            RoleDefinition(role_id="r-b", name="Head B", is_primary_for_unit="d-b"),
        ],
    )
    return compile_org(org)


def _secret_clearance() -> dict[str, RoleClearance]:
    # SECRET clearance holding both compartments so the requesting role passes
    # the Step-3 clearance checks and the KSP narrowing (Step-4d) is reached.
    return {
        _ROLE: RoleClearance(
            role_address=_ROLE,
            max_clearance=ConfidentialityLevel.SECRET,
            compartments=frozenset({"alpha", "beta"}),
        )
    }


def _deny_decision(item: KnowledgeItem, ksp: KnowledgeSharePolicy):
    """Run can_access for a cross-barrier D2-owned item under one deny-KSP."""
    return can_access(
        role_address=_ROLE,
        knowledge_item=item,
        posture=TrustPostureLevel.DELEGATING,
        compiled_org=_two_dept_org(),
        clearances=_secret_clearance(),
        ksps=[ksp],
        bridges=[],
    )


@pytest.mark.regression
def test_path_scope_deny_emits_discrete_fields() -> None:
    """A shared_paths mismatch emits deny_code=path_scope + discrete fields."""
    item = KnowledgeItem(
        item_id="cross-item",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D2",
        path="/hr/payroll",  # outside /finance/*
    )
    ksp = KnowledgeSharePolicy(
        id="ksp-deny-path",
        source_unit_address="D2",
        target_unit_address="D1",
        max_classification=ConfidentialityLevel.SECRET,
        shared_paths=("/finance/*",),
    )
    decision = _deny_decision(item, ksp)

    assert decision.allowed is False
    ad = decision.audit_details
    assert ad["access_path"] == "ksp_deny"
    assert ad["ksp_id"] == "ksp-deny-path"
    assert ad["deny_code"] == "path_scope"
    assert ad["item_path"] == "/hr/payroll"
    assert ad["ksp_shared_paths"] == ["/finance/*"]
    # Back-compat: the human string survives.
    assert "does not match KSP shared_paths" in ad["deny_reason"]


@pytest.mark.regression
def test_compartment_scope_deny_emits_discrete_fields() -> None:
    """A KSP compartment narrowing emits deny_code=compartment_scope + fields.

    The item is RESTRICTED (so the Step-3 SECRET/TOP_SECRET clearance
    compartment check is skipped) and the requesting role holds 'alpha', so the
    deny originates at the KSP narrowing (Step-4d, #1375), not at clearance.
    """
    item = KnowledgeItem(
        item_id="cross-item",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D2",
        compartments=frozenset({"alpha"}),
    )
    ksp = KnowledgeSharePolicy(
        id="ksp-deny-comp",
        source_unit_address="D2",
        target_unit_address="D1",
        max_classification=ConfidentialityLevel.SECRET,
        compartments=frozenset({"beta"}),  # does NOT authorize 'alpha'
    )
    decision = _deny_decision(item, ksp)

    assert decision.allowed is False
    ad = decision.audit_details
    assert ad["access_path"] == "ksp_deny"
    assert ad["deny_code"] == "compartment_scope"
    # SIEM parity with the Step-3 clearance compartment-deny shape.
    assert ad["missing_compartments"] == ["alpha"]
    assert ad["item_compartments"] == ["alpha"]
    assert ad["ksp_compartments"] == ["beta"]
    assert "not authorized by KSP compartments" in ad["deny_reason"]


@pytest.mark.regression
def test_type_scope_deny_emits_discrete_fields() -> None:
    """A shared_types mismatch emits deny_code=type_scope + discrete fields."""
    item = KnowledgeItem(
        item_id="cross-item",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D2",
        knowledge_type="memo",
    )
    ksp = KnowledgeSharePolicy(
        id="ksp-deny-type",
        source_unit_address="D2",
        target_unit_address="D1",
        max_classification=ConfidentialityLevel.SECRET,
        shared_types=frozenset({"report"}),
    )
    decision = _deny_decision(item, ksp)

    assert decision.allowed is False
    ad = decision.audit_details
    assert ad["deny_code"] == "type_scope"
    assert ad["item_knowledge_type"] == "memo"
    assert ad["ksp_shared_types"] == ["report"]


@pytest.mark.regression
def test_classification_ceiling_deny_emits_discrete_fields() -> None:
    """A classification ceiling breach emits deny_code=classification_ceiling."""
    item = KnowledgeItem(
        item_id="cross-item",
        classification=ConfidentialityLevel.SECRET,
        owning_unit_address="D2",
    )
    ksp = KnowledgeSharePolicy(
        id="ksp-deny-ceiling",
        source_unit_address="D2",
        target_unit_address="D1",
        max_classification=ConfidentialityLevel.RESTRICTED,  # below SECRET item
    )
    decision = _deny_decision(item, ksp)

    assert decision.allowed is False
    ad = decision.audit_details
    assert ad["deny_code"] == "classification_ceiling"
    assert ad["item_classification"] == "secret"
    assert ad["ksp_max_classification"] == "restricted"


@pytest.mark.regression
def test_explain_surfaces_ksp_deny_code() -> None:
    """/explain renders the deny_code discriminator + denying KSP id."""
    item = KnowledgeItem(
        item_id="cross-item",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D2",
        path="/hr/payroll",
    )
    ksp = KnowledgeSharePolicy(
        id="ksp-deny-path",
        source_unit_address="D2",
        target_unit_address="D1",
        max_classification=ConfidentialityLevel.SECRET,
        shared_paths=("/finance/*",),
    )
    explanation = explain_access(
        role_address=_ROLE,
        knowledge_item=item,
        posture=TrustPostureLevel.DELEGATING,
        compiled_org=_two_dept_org(),
        clearances=_secret_clearance(),
        ksps=[ksp],
        bridges=[],
    )

    assert "DENY (ksp-deny-path) [path_scope]" in explanation
    assert "DENIED by KSP 'ksp-deny-path' (path_scope)" in explanation
    assert "suppressed by deny-KSP" in explanation
