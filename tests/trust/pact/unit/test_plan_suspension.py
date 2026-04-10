# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for PACT N3 Plan Re-Entry Guarantee -- suspension and resumption.

Covers:
- Each of 4 triggers creates proper PlanSuspension
- Resume requires ALL conditions satisfied
- Partial conditions remain suspended
- Suspended plans block verify_action
- Snapshot is frozen (immutable dataclass)
- Suspension/resume events in audit trail
- Serialization round-trip (to_dict / from_dict)
"""

from __future__ import annotations

from typing import Any

import pytest
from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.audit import AuditChain
from kailash.trust.pact.clearance import RoleClearance
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.store import MemoryAccessPolicyStore, MemoryClearanceStore
from kailash.trust.pact.suspension import (
    PlanSuspension,
    ResumeCondition,
    SuspensionTrigger,
    resume_condition_for_trigger,
)
from kailash.trust.pact.verdict import GovernanceVerdict
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org

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
def engine(
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
def engine_with_audit(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
) -> tuple[GovernanceEngine, AuditChain]:
    """Engine with audit chain for verifying audit trail."""
    clearance_store = MemoryClearanceStore()
    for addr, clr in clearances.items():
        clearance_store.grant_clearance(clr)

    access_store = MemoryAccessPolicyStore()
    for bridge in bridges:
        access_store.save_bridge(bridge)
    for ksp in ksps:
        access_store.save_ksp(ksp)

    audit_chain = AuditChain(chain_id="test-suspension-audit")
    eng = GovernanceEngine(
        compiled_org,
        clearance_store=clearance_store,
        access_policy_store=access_store,
        audit_chain=audit_chain,
    )
    return eng, audit_chain


# CS Chair address in the university example
CS_CHAIR = "D1-R1-D1-R1-D1-R1-T1-R1"
DEAN = "D1-R1-D1-R1-D1-R1"


def _setup_envelope(engine: GovernanceEngine) -> None:
    """Set up a role envelope for the CS Chair so verify_action works."""
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
        defining_role_address=DEAN,
        target_role_address=CS_CHAIR,
        envelope=envelope_config,
    )
    engine.set_role_envelope(role_env)


# ---------------------------------------------------------------------------
# Tests: SuspensionTrigger creates proper PlanSuspension
# ---------------------------------------------------------------------------


class TestSuspensionTriggers:
    """Each of the 4 triggers creates a proper PlanSuspension with correct
    condition type."""

    def test_budget_trigger(self, engine: GovernanceEngine) -> None:
        """BUDGET trigger creates suspension with budget_replenished condition."""
        suspension = engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-budget-1",
            trigger=SuspensionTrigger.BUDGET,
            snapshot={"remaining_budget": 0.0},
        )
        assert isinstance(suspension, PlanSuspension)
        assert suspension.plan_id == "plan-budget-1"
        assert suspension.trigger == SuspensionTrigger.BUDGET
        assert suspension.role_address == CS_CHAIR
        assert len(suspension.resume_conditions) == 1
        assert suspension.resume_conditions[0].condition_type == "budget_replenished"
        assert suspension.resume_conditions[0].satisfied is False

    def test_temporal_trigger(self, engine: GovernanceEngine) -> None:
        """TEMPORAL trigger creates suspension with deadline_extended condition."""
        suspension = engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-temporal-1",
            trigger=SuspensionTrigger.TEMPORAL,
        )
        assert suspension.trigger == SuspensionTrigger.TEMPORAL
        assert len(suspension.resume_conditions) == 1
        assert suspension.resume_conditions[0].condition_type == "deadline_extended"
        assert suspension.resume_conditions[0].satisfied is False

    def test_posture_trigger(self, engine: GovernanceEngine) -> None:
        """POSTURE trigger creates suspension with posture_restored condition."""
        suspension = engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-posture-1",
            trigger=SuspensionTrigger.POSTURE,
        )
        assert suspension.trigger == SuspensionTrigger.POSTURE
        assert len(suspension.resume_conditions) == 1
        assert suspension.resume_conditions[0].condition_type == "posture_restored"
        assert suspension.resume_conditions[0].satisfied is False

    def test_envelope_trigger(self, engine: GovernanceEngine) -> None:
        """ENVELOPE trigger creates suspension with envelope_granted condition."""
        suspension = engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-envelope-1",
            trigger=SuspensionTrigger.ENVELOPE,
        )
        assert suspension.trigger == SuspensionTrigger.ENVELOPE
        assert len(suspension.resume_conditions) == 1
        assert suspension.resume_conditions[0].condition_type == "envelope_granted"
        assert suspension.resume_conditions[0].satisfied is False


# ---------------------------------------------------------------------------
# Tests: Resume requires ALL conditions satisfied
# ---------------------------------------------------------------------------


class TestResumeConditions:
    """resume_plan() succeeds only when ALL conditions are met."""

    def test_resume_with_all_conditions_met(self, engine: GovernanceEngine) -> None:
        """Resume succeeds when all conditions are satisfied."""
        engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-1",
            trigger=SuspensionTrigger.BUDGET,
        )

        # Mark the condition as satisfied
        engine.update_resume_condition(
            plan_id="plan-1",
            condition_type="budget_replenished",
            satisfied=True,
            details="Budget topped up to $500",
        )

        verdict = engine.resume_plan("plan-1")
        assert verdict.level == "auto_approved"
        assert verdict.allowed is True
        assert "resumed" in verdict.reason.lower()

        # Suspension should be gone
        assert engine.get_suspension("plan-1") is None

    def test_resume_with_unmet_conditions_blocked(
        self, engine: GovernanceEngine
    ) -> None:
        """Resume is blocked when conditions are not yet met."""
        engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-2",
            trigger=SuspensionTrigger.TEMPORAL,
        )

        # Do NOT update the condition
        verdict = engine.resume_plan("plan-2")
        assert verdict.level == "blocked"
        assert verdict.is_blocked is True
        assert "unmet conditions" in verdict.reason.lower()

        # Suspension should still exist
        assert engine.get_suspension("plan-2") is not None

    def test_resume_nonexistent_plan_blocked(self, engine: GovernanceEngine) -> None:
        """Attempting to resume a plan that does not exist returns blocked."""
        verdict = engine.resume_plan("nonexistent-plan")
        assert verdict.level == "blocked"
        assert "no active suspension" in verdict.reason.lower()


# ---------------------------------------------------------------------------
# Tests: Suspended plans block verify_action
# ---------------------------------------------------------------------------


class TestSuspendedPlansBlockVerifyAction:
    """verify_action() returns BLOCKED when a plan is suspended."""

    def test_verify_action_blocked_when_plan_suspended(
        self, engine: GovernanceEngine
    ) -> None:
        """An action with a suspended plan_id should be blocked."""
        _setup_envelope(engine)

        engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-blocked",
            trigger=SuspensionTrigger.BUDGET,
        )

        verdict = engine.verify_action(
            role_address=CS_CHAIR,
            action="read",
            context={"plan_id": "plan-blocked", "cost": 10.0},
        )
        assert verdict.level == "blocked"
        assert verdict.is_blocked is True
        assert "suspended" in verdict.reason.lower()
        assert verdict.audit_details.get("plan_suspended") is True

    def test_verify_action_allowed_without_plan_id(
        self, engine: GovernanceEngine
    ) -> None:
        """An action without a plan_id is not affected by suspensions."""
        _setup_envelope(engine)

        engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-other",
            trigger=SuspensionTrigger.BUDGET,
        )

        # No plan_id in context -- should evaluate normally
        verdict = engine.verify_action(
            role_address=CS_CHAIR,
            action="read",
            context={"cost": 10.0},
        )
        assert verdict.level == "auto_approved"

    def test_verify_action_allowed_after_resume(self, engine: GovernanceEngine) -> None:
        """After a plan is resumed, verify_action should succeed."""
        _setup_envelope(engine)

        engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-resume",
            trigger=SuspensionTrigger.POSTURE,
        )

        # Mark condition met and resume
        engine.update_resume_condition(
            "plan-resume", "posture_restored", satisfied=True
        )
        resume_verdict = engine.resume_plan("plan-resume")
        assert resume_verdict.level == "auto_approved"

        # Now verify_action should work
        verdict = engine.verify_action(
            role_address=CS_CHAIR,
            action="read",
            context={"plan_id": "plan-resume", "cost": 10.0},
        )
        assert verdict.level == "auto_approved"

    def test_verify_action_different_plan_not_affected(
        self, engine: GovernanceEngine
    ) -> None:
        """Suspending plan A should not block plan B."""
        _setup_envelope(engine)

        engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-a",
            trigger=SuspensionTrigger.BUDGET,
        )

        verdict = engine.verify_action(
            role_address=CS_CHAIR,
            action="read",
            context={"plan_id": "plan-b", "cost": 10.0},
        )
        assert verdict.level == "auto_approved"


# ---------------------------------------------------------------------------
# Tests: Snapshot is frozen (immutable)
# ---------------------------------------------------------------------------


class TestSnapshotFrozen:
    """PlanSuspension is a frozen dataclass."""

    def test_plan_suspension_is_frozen(self, engine: GovernanceEngine) -> None:
        """Attributes of PlanSuspension cannot be reassigned."""
        suspension = engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-frozen",
            trigger=SuspensionTrigger.BUDGET,
            snapshot={"remaining_budget": 0.0},
        )

        with pytest.raises(AttributeError):
            suspension.plan_id = "modified"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            suspension.trigger = SuspensionTrigger.TEMPORAL  # type: ignore[misc]

        with pytest.raises(AttributeError):
            suspension.snapshot = {}  # type: ignore[misc]

    def test_resume_condition_is_frozen(self) -> None:
        """Attributes of ResumeCondition cannot be reassigned."""
        cond = ResumeCondition(
            condition_type="budget_replenished",
            satisfied=False,
            details="waiting",
        )
        with pytest.raises(AttributeError):
            cond.satisfied = True  # type: ignore[misc]

    def test_snapshot_content_preserved(self, engine: GovernanceEngine) -> None:
        """The snapshot dict content is preserved exactly as provided."""
        snapshot = {"remaining_budget": 0.0, "actions_completed": 42}
        suspension = engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-snap",
            trigger=SuspensionTrigger.BUDGET,
            snapshot=snapshot,
        )
        assert suspension.snapshot == snapshot
        assert suspension.snapshot["remaining_budget"] == 0.0
        assert suspension.snapshot["actions_completed"] == 42


# ---------------------------------------------------------------------------
# Tests: Audit trail records suspension and resume events
# ---------------------------------------------------------------------------


class TestAuditTrail:
    """Suspension and resume events are recorded in the audit chain."""

    def test_suspend_emits_audit(
        self, engine_with_audit: tuple[GovernanceEngine, AuditChain]
    ) -> None:
        """suspend_plan() emits an audit anchor."""
        eng, chain = engine_with_audit
        initial_count = len(chain.anchors)

        eng.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-audit-1",
            trigger=SuspensionTrigger.BUDGET,
        )

        assert len(chain.anchors) > initial_count
        last_entry = chain.anchors[-1]
        assert last_entry.action == "plan_suspended"
        assert last_entry.metadata["plan_id"] == "plan-audit-1"
        assert last_entry.metadata["trigger"] == "budget"

    def test_resume_emits_audit(
        self, engine_with_audit: tuple[GovernanceEngine, AuditChain]
    ) -> None:
        """resume_plan() emits an audit anchor on success."""
        eng, chain = engine_with_audit

        eng.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-audit-2",
            trigger=SuspensionTrigger.TEMPORAL,
        )
        eng.update_resume_condition("plan-audit-2", "deadline_extended", satisfied=True)

        pre_count = len(chain.anchors)
        eng.resume_plan("plan-audit-2")

        assert len(chain.anchors) > pre_count
        last_entry = chain.anchors[-1]
        assert last_entry.action == "plan_resumed"
        assert last_entry.metadata["plan_id"] == "plan-audit-2"

    def test_blocked_verify_action_emits_suspension_audit(
        self, engine_with_audit: tuple[GovernanceEngine, AuditChain]
    ) -> None:
        """verify_action blocked by suspension emits an audit entry."""
        eng, chain = engine_with_audit
        _setup_envelope(eng)

        eng.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-audit-3",
            trigger=SuspensionTrigger.ENVELOPE,
        )

        pre_count = len(chain.anchors)
        eng.verify_action(
            role_address=CS_CHAIR,
            action="read",
            context={"plan_id": "plan-audit-3"},
        )

        # At least one new audit entry for the blocked action
        new_entries = chain.anchors[pre_count:]
        suspended_entries = [e for e in new_entries if e.action == "plan_suspended"]
        assert len(suspended_entries) >= 1

    def test_update_condition_emits_audit(
        self, engine_with_audit: tuple[GovernanceEngine, AuditChain]
    ) -> None:
        """update_resume_condition() emits an audit entry."""
        eng, chain = engine_with_audit

        eng.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-audit-4",
            trigger=SuspensionTrigger.BUDGET,
        )

        pre_count = len(chain.anchors)
        eng.update_resume_condition(
            "plan-audit-4", "budget_replenished", satisfied=True
        )

        assert len(chain.anchors) > pre_count
        last_entry = chain.anchors[-1]
        assert last_entry.action == "resume_condition_updated"


# ---------------------------------------------------------------------------
# Tests: Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    """PlanSuspension and ResumeCondition serialize and deserialize correctly."""

    def test_resume_condition_round_trip(self) -> None:
        """ResumeCondition survives to_dict / from_dict."""
        cond = ResumeCondition(
            condition_type="budget_replenished",
            satisfied=True,
            details="Budget restored to $1000",
        )
        data = cond.to_dict()
        restored = ResumeCondition.from_dict(data)

        assert restored.condition_type == cond.condition_type
        assert restored.satisfied == cond.satisfied
        assert restored.details == cond.details

    def test_plan_suspension_round_trip(self) -> None:
        """PlanSuspension survives to_dict / from_dict."""
        suspension = PlanSuspension(
            plan_id="plan-rt",
            trigger=SuspensionTrigger.BUDGET,
            suspended_at="2026-04-09T10:00:00+00:00",
            resume_conditions=(
                ResumeCondition(
                    condition_type="budget_replenished",
                    satisfied=False,
                    details="Waiting for budget top-up",
                ),
            ),
            snapshot={"remaining": 0.0, "spent": 500.0},
            role_address="D1-R1",
            suspension_id="abc123",
        )
        data = suspension.to_dict()
        restored = PlanSuspension.from_dict(data)

        assert restored.plan_id == suspension.plan_id
        assert restored.trigger == suspension.trigger
        assert restored.suspended_at == suspension.suspended_at
        assert len(restored.resume_conditions) == 1
        assert restored.resume_conditions[0].condition_type == "budget_replenished"
        assert restored.snapshot == suspension.snapshot
        assert restored.role_address == suspension.role_address
        assert restored.suspension_id == suspension.suspension_id

    def test_suspension_trigger_enum_values(self) -> None:
        """SuspensionTrigger enum values match expected strings."""
        assert SuspensionTrigger.BUDGET.value == "budget"
        assert SuspensionTrigger.TEMPORAL.value == "temporal"
        assert SuspensionTrigger.POSTURE.value == "posture"
        assert SuspensionTrigger.ENVELOPE.value == "envelope"

    def test_all_conditions_met_true(self) -> None:
        """all_conditions_met returns True when all conditions are satisfied."""
        suspension = PlanSuspension(
            plan_id="plan-met",
            trigger=SuspensionTrigger.BUDGET,
            suspended_at="2026-04-09T10:00:00+00:00",
            resume_conditions=(ResumeCondition("budget_replenished", satisfied=True),),
        )
        assert suspension.all_conditions_met() is True

    def test_all_conditions_met_false(self) -> None:
        """all_conditions_met returns False when any condition is unsatisfied."""
        suspension = PlanSuspension(
            plan_id="plan-unmet",
            trigger=SuspensionTrigger.BUDGET,
            suspended_at="2026-04-09T10:00:00+00:00",
            resume_conditions=(ResumeCondition("budget_replenished", satisfied=False),),
        )
        assert suspension.all_conditions_met() is False

    def test_all_conditions_met_empty(self) -> None:
        """all_conditions_met returns True vacuously when no conditions exist."""
        suspension = PlanSuspension(
            plan_id="plan-empty",
            trigger=SuspensionTrigger.BUDGET,
            suspended_at="2026-04-09T10:00:00+00:00",
            resume_conditions=(),
        )
        assert suspension.all_conditions_met() is True


# ---------------------------------------------------------------------------
# Tests: resume_condition_for_trigger helper
# ---------------------------------------------------------------------------


class TestResumeConditionForTrigger:
    """resume_condition_for_trigger generates the correct condition type."""

    def test_budget_trigger_condition(self) -> None:
        cond = resume_condition_for_trigger(SuspensionTrigger.BUDGET)
        assert cond.condition_type == "budget_replenished"
        assert cond.satisfied is False

    def test_temporal_trigger_condition(self) -> None:
        cond = resume_condition_for_trigger(SuspensionTrigger.TEMPORAL)
        assert cond.condition_type == "deadline_extended"
        assert cond.satisfied is False

    def test_posture_trigger_condition(self) -> None:
        cond = resume_condition_for_trigger(SuspensionTrigger.POSTURE)
        assert cond.condition_type == "posture_restored"
        assert cond.satisfied is False

    def test_envelope_trigger_condition(self) -> None:
        cond = resume_condition_for_trigger(SuspensionTrigger.ENVELOPE)
        assert cond.condition_type == "envelope_granted"
        assert cond.satisfied is False

    def test_custom_details(self) -> None:
        cond = resume_condition_for_trigger(
            SuspensionTrigger.BUDGET, details="Budget exhausted at $0.00"
        )
        assert cond.details == "Budget exhausted at $0.00"


# ---------------------------------------------------------------------------
# Tests: update_resume_condition
# ---------------------------------------------------------------------------


class TestUpdateResumeCondition:
    """update_resume_condition replaces frozen conditions correctly."""

    def test_update_marks_satisfied(self, engine: GovernanceEngine) -> None:
        """Updating a condition marks it as satisfied."""
        engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-upd",
            trigger=SuspensionTrigger.BUDGET,
        )

        updated = engine.update_resume_condition(
            "plan-upd", "budget_replenished", satisfied=True
        )
        assert updated is not None
        assert updated.resume_conditions[0].satisfied is True

    def test_update_nonexistent_plan_returns_none(
        self, engine: GovernanceEngine
    ) -> None:
        """Updating a condition for a nonexistent plan returns None."""
        result = engine.update_resume_condition(
            "no-such-plan", "budget_replenished", satisfied=True
        )
        assert result is None

    def test_get_suspension_returns_updated(self, engine: GovernanceEngine) -> None:
        """get_suspension reflects the latest update_resume_condition."""
        engine.suspend_plan(
            role_address=CS_CHAIR,
            plan_id="plan-get",
            trigger=SuspensionTrigger.TEMPORAL,
        )

        engine.update_resume_condition(
            "plan-get", "deadline_extended", satisfied=True, details="Extended to EOD"
        )

        suspension = engine.get_suspension("plan-get")
        assert suspension is not None
        assert suspension.resume_conditions[0].satisfied is True
        assert suspension.resume_conditions[0].details == "Extended to EOD"

    def test_get_suspension_nonexistent_returns_none(
        self, engine: GovernanceEngine
    ) -> None:
        """get_suspension for a non-suspended plan returns None."""
        assert engine.get_suspension("nonexistent") is None
