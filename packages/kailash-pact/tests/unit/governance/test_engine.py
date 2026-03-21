# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for GovernanceEngine -- the single entry point for PACT governance decisions.

Tests use the university example as fixtures. Written TDD-first: tests define
the expected behavior before the engine implementation exists.

Covers:
- Construction from OrgDefinition and CompiledOrg
- Default store initialization
- check_access (allowed and denied scenarios)
- verify_action (auto_approved, blocked, fail-closed)
- compute_envelope
- Query API (get_org, get_node)
- State mutation (grant/revoke clearance, create bridge/ksp, set envelopes)
- Audit chain integration
- Thread safety under concurrent access
"""

from __future__ import annotations

import concurrent.futures
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
)
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org
from pact.governance.access import AccessDecision, KnowledgeSharePolicy, PactBridge
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.compilation import CompiledOrg, OrgNode
from pact.governance.engine import GovernanceEngine
from pact.governance.envelopes import RoleEnvelope, TaskEnvelope
from pact.governance.knowledge import KnowledgeItem
from pact.governance.store import (
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
    MemoryEnvelopeStore,
    MemoryOrgStore,
)
from pact.governance.verdict import GovernanceVerdict
from pact.trust.audit.anchor import AuditChain


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def university_compiled() -> tuple[CompiledOrg, Any]:
    """Compiled university org and the original OrgDefinition."""
    return create_university_org()


@pytest.fixture
def compiled_org(university_compiled: tuple[CompiledOrg, Any]) -> CompiledOrg:
    """Just the compiled org."""
    return university_compiled[0]


@pytest.fixture
def org_definition(university_compiled: tuple[CompiledOrg, Any]) -> Any:
    """Just the OrgDefinition."""
    return university_compiled[1]


@pytest.fixture
def clearances(compiled_org: CompiledOrg) -> dict[str, RoleClearance]:
    """Clearance assignments for all university roles."""
    return create_university_clearances(compiled_org)


@pytest.fixture
def bridges() -> list[PactBridge]:
    """Cross-Functional Bridges for the university."""
    return create_university_bridges()


@pytest.fixture
def ksps() -> list[KnowledgeSharePolicy]:
    """Knowledge Share Policies for the university."""
    return create_university_ksps()


@pytest.fixture
def engine_from_compiled(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
) -> GovernanceEngine:
    """Engine built from a pre-compiled org with stores populated."""
    clearance_store = MemoryClearanceStore()
    for addr, clr in clearances.items():
        clearance_store.grant_clearance(clr)

    access_store = MemoryAccessPolicyStore()
    for bridge in bridges:
        access_store.save_bridge(bridge)
    for ksp in ksps:
        access_store.save_ksp(ksp)

    return GovernanceEngine(
        compiled_org,
        clearance_store=clearance_store,
        access_policy_store=access_store,
    )


@pytest.fixture
def engine_from_org_def(
    org_definition: Any,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
) -> GovernanceEngine:
    """Engine built from an OrgDefinition (auto-compiled)."""
    clearance_store = MemoryClearanceStore()
    for addr, clr in clearances.items():
        clearance_store.grant_clearance(clr)

    access_store = MemoryAccessPolicyStore()
    for bridge in bridges:
        access_store.save_bridge(bridge)
    for ksp in ksps:
        access_store.save_ksp(ksp)

    return GovernanceEngine(
        org_definition,
        clearance_store=clearance_store,
        access_policy_store=access_store,
    )


@pytest.fixture
def engine_with_audit(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
) -> GovernanceEngine:
    """Engine with an AuditChain configured."""
    clearance_store = MemoryClearanceStore()
    for clr in clearances.values():
        clearance_store.grant_clearance(clr)

    access_store = MemoryAccessPolicyStore()
    for bridge in bridges:
        access_store.save_bridge(bridge)
    for ksp in ksps:
        access_store.save_ksp(ksp)

    audit_chain = AuditChain(chain_id="test-audit-chain")

    return GovernanceEngine(
        compiled_org,
        clearance_store=clearance_store,
        access_policy_store=access_store,
        audit_chain=audit_chain,
    )


# ---------------------------------------------------------------------------
# Construction Tests
# ---------------------------------------------------------------------------


class TestConstruction:
    """GovernanceEngine construction from OrgDefinition and CompiledOrg."""

    def test_construct_from_org_definition(self, engine_from_org_def: GovernanceEngine) -> None:
        """Engine should accept an OrgDefinition and auto-compile it."""
        org = engine_from_org_def.get_org()
        assert isinstance(org, CompiledOrg)
        assert org.org_id == "university-001"
        assert len(org.nodes) > 0

    def test_construct_from_compiled_org(self, engine_from_compiled: GovernanceEngine) -> None:
        """Engine should accept a pre-compiled CompiledOrg directly."""
        org = engine_from_compiled.get_org()
        assert isinstance(org, CompiledOrg)
        assert org.org_id == "university-001"

    def test_default_stores(self, compiled_org: CompiledOrg) -> None:
        """When no stores are passed, engine should create MemoryXxxStore defaults."""
        engine = GovernanceEngine(compiled_org)
        # Should not raise; engine should have working stores
        org = engine.get_org()
        assert org.org_id == "university-001"

        # compute_envelope should work even with empty stores (returns None)
        result = engine.compute_envelope("D1-R1")
        assert result is None  # No envelopes stored yet


# ---------------------------------------------------------------------------
# check_access Tests
# ---------------------------------------------------------------------------


class TestCheckAccess:
    """Knowledge access enforcement through the engine facade."""

    def test_check_access_allowed_same_unit(self, engine_from_compiled: GovernanceEngine) -> None:
        """CS Chair should access RESTRICTED data owned by CS Department (same unit)."""
        item = KnowledgeItem(
            item_id="cs-syllabus-2026",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-D1-R1-D1-R1-T1",  # CS Department
            description="CS course syllabus",
        )
        decision = engine_from_compiled.check_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",  # CS Chair
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
        )
        assert isinstance(decision, AccessDecision)
        assert decision.allowed is True

    def test_check_access_denied_cross_barrier(
        self, engine_from_compiled: GovernanceEngine
    ) -> None:
        """CS Faculty should NOT access Student Affairs disciplinary records.

        There is no KSP or bridge between Academic Affairs and Student Affairs
        for student-records compartment data.
        """
        item = KnowledgeItem(
            item_id="disciplinary-case-2026-042",
            classification=ConfidentialityLevel.CONFIDENTIAL,
            owning_unit_address="D1-R1-D3",  # Student Affairs
            compartments=frozenset({"student-records"}),
            description="Student disciplinary case file",
        )
        decision = engine_from_compiled.check_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1-R1",  # CS Faculty
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
        )
        assert isinstance(decision, AccessDecision)
        assert decision.allowed is False


# ---------------------------------------------------------------------------
# verify_action Tests
# ---------------------------------------------------------------------------


class TestVerifyAction:
    """Primary decision API -- verify_action()."""

    def test_verify_action_auto_approved_within_envelope(
        self, engine_from_compiled: GovernanceEngine
    ) -> None:
        """An action within the role envelope should be auto_approved."""
        # First, set up a role envelope for the CS Chair
        envelope_config = ConstraintEnvelopeConfig(
            id="env-cs-chair",
            description="CS Chair envelope",
            financial=FinancialConstraintConfig(max_spend_usd=1000.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "grade", "teach"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-cs-chair",
            defining_role_address="D1-R1-D1-R1-D1-R1",  # Dean defines
            target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",  # CS Chair
            envelope=envelope_config,
        )
        engine_from_compiled.set_role_envelope(role_env)

        verdict = engine_from_compiled.verify_action(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            action="read",
            context={"cost": 10.0},
        )
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "auto_approved"
        assert verdict.allowed is True
        assert verdict.role_address == "D1-R1-D1-R1-D1-R1-T1-R1"
        assert verdict.action == "read"

    def test_verify_action_blocked_exceeds_envelope(
        self, engine_from_compiled: GovernanceEngine
    ) -> None:
        """An action that is not in the allowed actions list should be blocked."""
        envelope_config = ConstraintEnvelopeConfig(
            id="env-cs-chair-strict",
            description="CS Chair strict envelope",
            financial=FinancialConstraintConfig(max_spend_usd=100.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
                blocked_actions=["delete", "deploy"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-cs-chair-strict",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            envelope=envelope_config,
        )
        engine_from_compiled.set_role_envelope(role_env)

        verdict = engine_from_compiled.verify_action(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            action="delete",
        )
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "blocked"
        assert verdict.allowed is False

    def test_verify_action_blocked_exceeds_financial(
        self, engine_from_compiled: GovernanceEngine
    ) -> None:
        """An action whose cost exceeds the financial limit should be blocked."""
        envelope_config = ConstraintEnvelopeConfig(
            id="env-finance-dir",
            description="Finance Director envelope",
            financial=FinancialConstraintConfig(max_spend_usd=500.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "approve"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-finance-dir",
            defining_role_address="D1-R1-D2-R1",
            target_role_address="D1-R1-D2-R1-T2-R1",
            envelope=envelope_config,
        )
        engine_from_compiled.set_role_envelope(role_env)

        verdict = engine_from_compiled.verify_action(
            role_address="D1-R1-D2-R1-T2-R1",
            action="approve",
            context={"cost": 9999.0},
        )
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "blocked"
        assert verdict.allowed is False

    def test_verify_action_fail_closed_on_internal_error(self, compiled_org: CompiledOrg) -> None:
        """Any internal error during verify_action should return BLOCKED, not raise."""
        engine = GovernanceEngine(compiled_org)

        # Use an address that does not exist in the compiled org.
        # The engine should catch the error and return BLOCKED.
        verdict = engine.verify_action(
            role_address="INVALID-ADDRESS-DOES-NOT-EXIST",
            action="read",
        )
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "blocked"
        assert verdict.allowed is False
        assert "error" in verdict.reason.lower() or "fail" in verdict.reason.lower()

    def test_verify_action_no_envelope_auto_approved(
        self, engine_from_compiled: GovernanceEngine
    ) -> None:
        """When no envelope exists for a role, action is auto_approved (no constraints)."""
        # HR Director has no envelope set, so no constraints apply
        verdict = engine_from_compiled.verify_action(
            role_address="D1-R1-D2-R1-T1-R1",
            action="read",
        )
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "auto_approved"
        assert verdict.allowed is True


# ---------------------------------------------------------------------------
# compute_envelope Tests
# ---------------------------------------------------------------------------


class TestComputeEnvelope:
    """Effective envelope computation through the engine."""

    def test_compute_envelope_returns_config(self, engine_from_compiled: GovernanceEngine) -> None:
        """When a role envelope is set, compute_envelope returns the effective envelope."""
        envelope_config = ConstraintEnvelopeConfig(
            id="env-provost",
            description="Provost envelope",
            financial=FinancialConstraintConfig(max_spend_usd=50000.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "approve", "delegate"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-provost",
            defining_role_address="D1-R1",  # President defines
            target_role_address="D1-R1-D1-R1",  # Provost
            envelope=envelope_config,
        )
        engine_from_compiled.set_role_envelope(role_env)

        effective = engine_from_compiled.compute_envelope("D1-R1-D1-R1")
        assert effective is not None
        assert isinstance(effective, ConstraintEnvelopeConfig)
        assert effective.financial is not None
        assert effective.financial.max_spend_usd == 50000.0

    def test_compute_envelope_with_task_narrows(
        self, engine_from_compiled: GovernanceEngine
    ) -> None:
        """A task envelope should narrow the role envelope via intersection."""
        role_config = ConstraintEnvelopeConfig(
            id="env-dean-eng",
            description="Dean envelope",
            financial=FinancialConstraintConfig(max_spend_usd=20000.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "approve", "hire"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-dean-eng",
            defining_role_address="D1-R1-D1-R1",
            target_role_address="D1-R1-D1-R1-D1-R1",  # Dean of Eng
            envelope=role_config,
        )
        engine_from_compiled.set_role_envelope(role_env)

        task_config = ConstraintEnvelopeConfig(
            id="env-task-budget-review",
            description="Budget review task",
            financial=FinancialConstraintConfig(max_spend_usd=5000.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "approve"],
            ),
        )
        task_env = TaskEnvelope(
            id="te-budget-review",
            task_id="task-budget-2026",
            parent_envelope_id="re-dean-eng",
            envelope=task_config,
            expires_at=datetime.now(UTC) + timedelta(hours=4),
        )
        engine_from_compiled.set_task_envelope(task_env)

        effective = engine_from_compiled.compute_envelope(
            "D1-R1-D1-R1-D1-R1", task_id="task-budget-2026"
        )
        assert effective is not None
        # Task narrows financial to 5000
        assert effective.financial is not None
        assert effective.financial.max_spend_usd == 5000.0
        # Task narrows allowed actions to intersection: {"read", "approve"}
        assert set(effective.operational.allowed_actions) == {"read", "approve"}

    def test_compute_envelope_none_when_empty(self, engine_from_compiled: GovernanceEngine) -> None:
        """When no envelopes exist, compute_envelope returns None."""
        result = engine_from_compiled.compute_envelope("D1-R1-D2-R1")
        assert result is None


# ---------------------------------------------------------------------------
# Query API Tests
# ---------------------------------------------------------------------------


class TestQueryAPI:
    """Query operations through the engine."""

    def test_get_org_returns_compiled(self, engine_from_compiled: GovernanceEngine) -> None:
        """get_org() should return the CompiledOrg."""
        org = engine_from_compiled.get_org()
        assert isinstance(org, CompiledOrg)
        assert org.org_id == "university-001"
        assert "D1-R1" in org.nodes

    def test_get_node_by_address(self, engine_from_compiled: GovernanceEngine) -> None:
        """get_node() should return the OrgNode for a valid address."""
        node = engine_from_compiled.get_node("D1-R1")
        assert node is not None
        assert isinstance(node, OrgNode)
        assert node.name == "President"

    def test_get_node_returns_none_for_invalid(
        self, engine_from_compiled: GovernanceEngine
    ) -> None:
        """get_node() should return None for a nonexistent address."""
        node = engine_from_compiled.get_node("D99-R99")
        assert node is None


# ---------------------------------------------------------------------------
# State Mutation Tests
# ---------------------------------------------------------------------------


class TestStateMutation:
    """State mutation operations through the engine."""

    def test_grant_clearance_and_use(self, compiled_org: CompiledOrg) -> None:
        """Granting clearance through the engine should be usable in check_access."""
        engine = GovernanceEngine(compiled_org)

        # Initially no clearance -- access should be denied
        item = KnowledgeItem(
            item_id="cs-data-001",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-D1-R1-D1-R1-T1",
            description="CS internal data",
        )
        decision = engine.check_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
        )
        assert decision.allowed is False  # No clearance

        # Grant clearance
        clearance = RoleClearance(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            granted_by_role_address="D1-R1-D1-R1-D1-R1",
            vetting_status=VettingStatus.ACTIVE,
        )
        engine.grant_clearance("D1-R1-D1-R1-D1-R1-T1-R1", clearance)

        # Now access should be allowed (same unit, clearance sufficient)
        decision = engine.check_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
        )
        assert decision.allowed is True

    def test_revoke_clearance(self, compiled_org: CompiledOrg) -> None:
        """Revoking clearance should deny previously-allowed access."""
        engine = GovernanceEngine(compiled_org)

        clearance = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            granted_by_role_address="D1-R1",
            vetting_status=VettingStatus.ACTIVE,
        )
        engine.grant_clearance("D1-R1", clearance)

        item = KnowledgeItem(
            item_id="president-data-001",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
            description="Presidential briefing",
        )
        decision = engine.check_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
        )
        assert decision.allowed is True

        # Revoke
        engine.revoke_clearance("D1-R1")

        decision = engine.check_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
        )
        assert decision.allowed is False

    def test_create_bridge_enables_access(self, engine_from_compiled: GovernanceEngine) -> None:
        """Creating a bridge through the engine should enable cross-unit access."""
        # VP Student Affairs cannot normally access Academic Affairs data
        item = KnowledgeItem(
            item_id="acad-report-001",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-D1",  # Academic Affairs
            description="Academic performance report",
        )
        decision_before = engine_from_compiled.check_access(
            role_address="D1-R1-D3-R1",  # VP Student Affairs
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
        )
        assert decision_before.allowed is False

        # Create a bridge between VP Student Affairs and Provost
        bridge = PactBridge(
            id="bridge-student-affairs-acad",
            role_a_address="D1-R1-D3-R1",  # VP Student Affairs
            role_b_address="D1-R1-D1-R1",  # Provost
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
            bilateral=True,
        )
        engine_from_compiled.create_bridge(bridge)

        # Now VP Student Affairs should have access via the bridge
        decision_after = engine_from_compiled.check_access(
            role_address="D1-R1-D3-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
        )
        assert decision_after.allowed is True

    def test_create_ksp_enables_access(self, engine_from_compiled: GovernanceEngine) -> None:
        """Creating a KSP through the engine should enable one-way knowledge sharing."""
        # Finance team cannot normally read Student Affairs data
        item = KnowledgeItem(
            item_id="student-fees-001",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-D3",  # Student Affairs
            description="Student fee records",
        )
        decision_before = engine_from_compiled.check_access(
            role_address="D1-R1-D2-R1-T2-R1",  # Finance Director
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
        )
        assert decision_before.allowed is False

        # Create KSP: Student Affairs shares to Finance
        ksp = KnowledgeSharePolicy(
            id="ksp-student-to-finance",
            source_unit_address="D1-R1-D3",  # Student Affairs shares
            target_unit_address="D1-R1-D2-R1-T2",  # Finance receives
            max_classification=ConfidentialityLevel.RESTRICTED,
            created_by_role_address="D1-R1",
            active=True,
        )
        engine_from_compiled.create_ksp(ksp)

        decision_after = engine_from_compiled.check_access(
            role_address="D1-R1-D2-R1-T2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
        )
        assert decision_after.allowed is True

    def test_set_role_envelope(self, engine_from_compiled: GovernanceEngine) -> None:
        """Setting a role envelope should be retrievable via compute_envelope."""
        envelope_config = ConstraintEnvelopeConfig(
            id="env-hr-director",
            description="HR Director envelope",
            financial=FinancialConstraintConfig(max_spend_usd=5000.0),
        )
        role_env = RoleEnvelope(
            id="re-hr-director",
            defining_role_address="D1-R1-D2-R1",
            target_role_address="D1-R1-D2-R1-T1-R1",
            envelope=envelope_config,
        )
        engine_from_compiled.set_role_envelope(role_env)

        effective = engine_from_compiled.compute_envelope("D1-R1-D2-R1-T1-R1")
        assert effective is not None
        assert effective.financial is not None
        assert effective.financial.max_spend_usd == 5000.0


# ---------------------------------------------------------------------------
# Audit Chain Tests
# ---------------------------------------------------------------------------


class TestAuditChain:
    """Audit chain integration."""

    def test_audit_chain_records_decisions(self, engine_with_audit: GovernanceEngine) -> None:
        """When audit_chain is provided, verify_action should record audit anchors."""
        assert engine_with_audit.audit_chain is not None
        initial_length = engine_with_audit.audit_chain.length

        # Trigger a verify_action
        engine_with_audit.verify_action(
            role_address="D1-R1",
            action="read",
        )

        assert engine_with_audit.audit_chain.length > initial_length
        latest = engine_with_audit.audit_chain.latest
        assert latest is not None
        assert latest.action == "verify_action"

    def test_audit_chain_records_mutations(self, engine_with_audit: GovernanceEngine) -> None:
        """Mutations (grant_clearance, create_bridge) should emit audit anchors."""
        assert engine_with_audit.audit_chain is not None
        initial_length = engine_with_audit.audit_chain.length

        clearance = RoleClearance(
            role_address="D1-R1-D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            granted_by_role_address="D1-R1",
            vetting_status=VettingStatus.ACTIVE,
        )
        engine_with_audit.grant_clearance("D1-R1-D1-R1", clearance)

        assert engine_with_audit.audit_chain.length > initial_length

    def test_audit_chain_none_ok(self, engine_from_compiled: GovernanceEngine) -> None:
        """When no audit_chain is provided, operations should work silently."""
        assert engine_from_compiled.audit_chain is None

        # This should not raise
        verdict = engine_from_compiled.verify_action(
            role_address="D1-R1",
            action="read",
        )
        assert isinstance(verdict, GovernanceVerdict)

        # Mutations should also work silently
        clearance = RoleClearance(
            role_address="D1-R1-D1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            granted_by_role_address="D1-R1",
            vetting_status=VettingStatus.ACTIVE,
        )
        engine_from_compiled.grant_clearance("D1-R1-D1-R1", clearance)
        # No error means success


# ---------------------------------------------------------------------------
# Thread Safety Tests
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Concurrent access to GovernanceEngine."""

    def test_thread_safety_concurrent_verify_action(
        self, engine_from_compiled: GovernanceEngine
    ) -> None:
        """100 concurrent verify_action calls should all complete without error."""
        # Set up an envelope so verify_action has something to evaluate
        envelope_config = ConstraintEnvelopeConfig(
            id="env-president",
            description="President envelope",
            financial=FinancialConstraintConfig(max_spend_usd=100000.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "approve", "delegate"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-president",
            defining_role_address="D1-R1",
            target_role_address="D1-R1",
            envelope=envelope_config,
        )
        engine_from_compiled.set_role_envelope(role_env)

        errors: list[Exception] = []
        results: list[GovernanceVerdict] = []
        lock = threading.Lock()

        def worker(i: int) -> None:
            try:
                verdict = engine_from_compiled.verify_action(
                    role_address="D1-R1",
                    action="read",
                    context={"cost": float(i)},
                )
                with lock:
                    results.append(verdict)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, i) for i in range(100)]
            concurrent.futures.wait(futures)

        assert len(errors) == 0, f"Errors during concurrent execution: {errors}"
        assert len(results) == 100
        # All results should be valid verdicts
        for v in results:
            assert isinstance(v, GovernanceVerdict)
            assert v.level in ("auto_approved", "flagged", "held", "blocked")
