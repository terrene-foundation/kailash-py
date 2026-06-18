# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: a matching deny-KSP must suppress a permissive bridge (#1372).

Epic #1375 — before this fix, ``_check_ksps`` returned ``AccessDecision | None``
with no deny branch: a KSP that matched source/target addressing but failed a
narrowing condition simply fell through to the bridge path, which could still
ALLOW. A deliberate KSP deny was therefore bypassable via a more permissive
bridge (over-grant). This test pins the deny-precedence security boundary at
the GovernanceEngine.check_access surface.
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.clearance import RoleClearance
from kailash.trust.pact.compilation import RoleDefinition, compile_org
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    DepartmentConfig,
    OrgDefinition,
    TrustPostureLevel,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.knowledge import KnowledgeItem
from kailash.trust.pact.store import MemoryAccessPolicyStore


def _two_dept_engine() -> GovernanceEngine:
    """Engine over two independent departments (D1 + D2, no structural path)."""
    org = OrgDefinition(
        org_id="deny-precedence-001",
        name="Deny Precedence Org",
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
    return GovernanceEngine(compile_org(org))


def _grant(engine: GovernanceEngine, addr: str) -> None:
    engine.grant_clearance(
        addr,
        RoleClearance(role_address=addr, max_clearance=ConfidentialityLevel.SECRET),
    )


# D1-R1 (Head A) requests a D2-owned item -> cross-barrier (forces 4d/4e).
_ROLE = "D1-R1"
_ITEM = KnowledgeItem(
    item_id="cross-item",
    classification=ConfidentialityLevel.RESTRICTED,
    owning_unit_address="D2",
    path="/hr/payroll",  # outside the KSP's /finance/* scope
)
_DENY_KSP = KnowledgeSharePolicy(
    id="ksp-deny",
    source_unit_address="D2",
    target_unit_address="D1",
    max_classification=ConfidentialityLevel.SECRET,
    shared_paths=("/finance/*",),  # item path /hr/payroll does NOT match -> deny
)
_PERMISSIVE_BRIDGE = PactBridge(
    id="bridge-permissive",
    role_a_address="D1-R1",
    role_b_address="D2-R1",
    bridge_type="standing",
    max_classification=ConfidentialityLevel.SECRET,  # would grant if reached
)


@pytest.mark.regression
def test_deny_ksp_suppresses_permissive_bridge() -> None:
    """KSP matches+denies AND a permissive bridge exists -> DENY (bridge suppressed)."""
    store = MemoryAccessPolicyStore()
    store.save_ksp(_DENY_KSP)
    store.save_bridge(_PERMISSIVE_BRIDGE)
    engine = _two_dept_engine()
    # Inject the policy store post-construction (bypass LCA ceremony; the
    # security boundary under test is check_access composition, not creation).
    engine._access_policy_store = store  # noqa: SLF001 — regression harness
    _grant(engine, _ROLE)

    decision = engine.check_access(_ROLE, _ITEM, TrustPostureLevel.DELEGATED)

    assert decision.allowed is False, "deny-KSP must suppress the permissive bridge"
    assert decision.step_failed == 4
    assert decision.audit_details["access_path"] == "ksp_deny"


@pytest.mark.regression
def test_bridge_alone_still_grants() -> None:
    """Control: without the KSP, the permissive bridge grants (no over-block)."""
    store = MemoryAccessPolicyStore()
    store.save_bridge(_PERMISSIVE_BRIDGE)
    engine = _two_dept_engine()
    engine._access_policy_store = store  # noqa: SLF001
    _grant(engine, _ROLE)

    decision = engine.check_access(_ROLE, _ITEM, TrustPostureLevel.DELEGATED)

    assert decision.allowed is True
    assert decision.audit_details["access_path"] == "bridge"


@pytest.mark.regression
def test_deny_ksp_alone_denies() -> None:
    """Control: the matching deny-KSP denies even with no bridge present."""
    store = MemoryAccessPolicyStore()
    store.save_ksp(_DENY_KSP)
    engine = _two_dept_engine()
    engine._access_policy_store = store  # noqa: SLF001
    _grant(engine, _ROLE)

    decision = engine.check_access(_ROLE, _ITEM, TrustPostureLevel.DELEGATED)

    assert decision.allowed is False
    assert decision.audit_details["access_path"] == "ksp_deny"


@pytest.mark.regression
def test_granting_sibling_ksp_wins_over_deny_ksp() -> None:
    """Composition branch: a granting KSP wins over a sibling denying KSP (ALLOW)."""
    store = MemoryAccessPolicyStore()
    store.save_ksp(_DENY_KSP)  # /finance/* scope -> denies the /hr/payroll item
    store.save_ksp(
        KnowledgeSharePolicy(
            id="ksp-grant",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.SECRET,
        )
    )
    engine = _two_dept_engine()
    engine._access_policy_store = store  # noqa: SLF001
    _grant(engine, _ROLE)

    decision = engine.check_access(_ROLE, _ITEM, TrustPostureLevel.DELEGATED)

    assert decision.allowed is True
    assert decision.audit_details["ksp_id"] == "ksp-grant"


@pytest.mark.regression
def test_persisted_deny_ksp_enforces_via_sqlite() -> None:
    """Persistence+enforcement parity: a deny-KSP stored in SQLite actually denies.

    Round-trip tests prove the column survives; this proves the persisted
    policy is read back AND enforced by the engine's check_access path
    (closes the facade/orphan gap — the stored policy is not inert data).
    """
    from kailash.trust.pact.stores.sqlite import SqliteAccessPolicyStore

    store = SqliteAccessPolicyStore(":memory:")
    store.save_ksp(_DENY_KSP)
    store.save_bridge(_PERMISSIVE_BRIDGE)
    org = _two_dept_engine().get_org()
    engine = GovernanceEngine(org, access_policy_store=store)
    _grant(engine, _ROLE)

    decision = engine.check_access(_ROLE, _ITEM, TrustPostureLevel.DELEGATED)

    assert (
        decision.allowed is False
    ), "persisted deny-KSP must enforce + suppress bridge"
    assert decision.audit_details["access_path"] == "ksp_deny"
    store.close()
