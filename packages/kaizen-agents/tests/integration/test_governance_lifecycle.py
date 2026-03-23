# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""P3-02 Integration tests: cross-cutting governance lifecycle flows.

These test the full lifecycle flows required for convergence:
1. Plan lifecycle: objective → execute → complete
2. Budget lifecycle: allocate → track → warn → reclaim → reallocate
3. Governance enforcement: tool denied → audit recorded
4. Cascade lifecycle: parent tightened → children re-intersected
5. Vacancy lifecycle: parent terminated → orphan → acting parent → resume
"""

from __future__ import annotations

from typing import Any

import pytest

from kaizen_agents.audit.trail import AuditTrail
from kaizen_agents.governance.accountability import AccountabilityTracker
from kaizen_agents.governance.budget import BudgetTracker
from kaizen_agents.governance.cascade import CascadeEventType, CascadeManager
from kaizen_agents.governance.clearance import (
    ClassifiedValue,
    ClearanceEnforcer,
    DataClassification,
)
from kaizen_agents.governance.vacancy import VacancyManager
from kaizen_agents.supervisor import GovernedSupervisor
from kaizen_agents.types import (
    AgentSpec,
    Plan,
    PlanEdge,
    PlanNode,
    PlanNodeOutput,
)


# ---------------------------------------------------------------------------
# Shared test executors
# ---------------------------------------------------------------------------


async def tracked_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor that returns spec name with cost proportional to name length."""
    cost = len(spec.name) * 0.01
    return {"result": f"completed:{spec.name}", "cost": cost}


# ---------------------------------------------------------------------------
# Flow 1: Full plan lifecycle
# ---------------------------------------------------------------------------


class TestPlanLifecycle:
    """E2E: objective → decompose → execute → complete with audit."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_single_objective(self) -> None:
        supervisor = GovernedSupervisor(budget_usd=10.0)
        result = await supervisor.run(
            "Analyze security vulnerabilities",
            execute_node=tracked_executor,
        )
        assert result.success is True
        assert len(result.audit_trail) >= 2  # genesis + at least 1 action
        assert result.budget_consumed > 0
        assert result.plan is not None

    @pytest.mark.asyncio
    async def test_multi_node_lifecycle(self) -> None:
        supervisor = GovernedSupervisor(budget_usd=10.0)

        plan = Plan(
            name="lifecycle-test",
            nodes={
                "research": PlanNode(
                    node_id="research",
                    agent_spec=AgentSpec(spec_id="r", name="research", description="Research"),
                ),
                "analyze": PlanNode(
                    node_id="analyze",
                    agent_spec=AgentSpec(spec_id="a", name="analyze", description="Analyze"),
                    input_mapping={"data": PlanNodeOutput("research", "result")},
                ),
                "report": PlanNode(
                    node_id="report",
                    agent_spec=AgentSpec(spec_id="w", name="report", description="Report"),
                    input_mapping={"analysis": PlanNodeOutput("analyze", "result")},
                ),
            },
            edges=[
                PlanEdge(from_node="research", to_node="analyze"),
                PlanEdge(from_node="analyze", to_node="report"),
            ],
        )

        result = await supervisor.run_plan(plan, execute_node=tracked_executor)
        assert result.success is True
        assert len(result.results) == 3
        assert result.budget_consumed > 0

        # Verify audit trail contains genesis
        genesis_records = [r for r in result.audit_trail if r["record_type"] == "genesis"]
        assert len(genesis_records) >= 1


# ---------------------------------------------------------------------------
# Flow 2: Budget lifecycle
# ---------------------------------------------------------------------------


class TestBudgetLifecycle:
    """E2E: allocate → track → warn → reclaim → reallocate."""

    def test_full_budget_lifecycle(self) -> None:
        tracker = BudgetTracker(warning_threshold=0.70, hold_threshold=1.0)

        # Allocate root and children
        tracker.allocate("root", 100.0)
        tracker.allocate("child-a", 30.0, parent_id="root")
        tracker.allocate("child-b", 30.0, parent_id="root")

        # Consume within child-a
        events = tracker.record_consumption("child-a", 25.0)
        warnings = [e for e in events if e.event_type == "warning"]
        assert len(warnings) == 1  # 25/30 = 83% > 70% threshold

        # Child-b completes with budget remaining
        tracker.record_consumption("child-b", 5.0)
        reclaim_event = tracker.reclaim("child-b")
        assert reclaim_event is not None
        assert reclaim_event.details["reclaimed"] == 25.0  # 30 - 5

        # Root now has 100 + 25 = 125
        snap = tracker.get_snapshot("root")
        assert snap is not None
        assert snap.allocated == 125.0

        # Exhaust child-a → HELD
        events = tracker.record_consumption("child-a", 5.0)  # 30/30 = 100%
        held = [e for e in events if e.event_type == "exhaustion_held"]
        assert len(held) == 1
        assert tracker.is_held("child-a")

        # Reallocate from root reserve to child-a
        realloc = tracker.reallocate("root", "child-a", 10.0)
        assert realloc is not None
        assert not tracker.is_held("child-a")  # resolved

    def test_budget_accounting_invariant(self) -> None:
        """Total consumed never exceeds total allocated at any point."""
        tracker = BudgetTracker(warning_threshold=0.80)
        tracker.allocate("root", 50.0)
        tracker.allocate("a", 15.0, parent_id="root")
        tracker.allocate("b", 15.0, parent_id="root")

        for i in range(10):
            tracker.record_consumption("a", 1.0)
            tracker.record_consumption("b", 1.0)

            snap_a = tracker.get_snapshot("a")
            snap_b = tracker.get_snapshot("b")
            assert snap_a is not None and snap_a.consumed <= snap_a.allocated
            assert snap_b is not None and snap_b.consumed <= snap_b.allocated


# ---------------------------------------------------------------------------
# Flow 3: Governance enforcement with audit
# ---------------------------------------------------------------------------


class TestGovernanceEnforcement:
    """E2E: clearance enforcement + audit recording."""

    def test_clearance_enforcement_with_audit(self) -> None:
        audit = AuditTrail()
        enforcer = ClearanceEnforcer()
        tracker = AccountabilityTracker()

        # Register root with clearance
        tracker.register_root("root", policy_source="admin@corp.com")
        audit.record_genesis("root", {"clearance": "C3"})

        # Register classified values
        enforcer.register_value(
            ClassifiedValue("public_data", "hello", DataClassification.C0_PUBLIC)
        )
        enforcer.register_value(
            ClassifiedValue("api_key", "sk-secret", DataClassification.C3_SECRET)
        )

        # Child with C1 clearance
        tracker.register_child("child", "root")

        # C1 agent cannot see C3 data
        visible = enforcer.filter_for_clearance(DataClassification.C1_INTERNAL)
        assert "public_data" in visible
        assert "api_key" not in visible

        # Record the access attempt in audit
        audit.record_action(
            agent_id="child",
            action="access_denied:api_key",
            details={"clearance": "C1", "required": "C3"},
        )

        # Verify audit chain
        assert audit.verify_chain()
        child_records = audit.query_by_agent("child")
        assert len(child_records) == 1
        assert child_records[0].action == "access_denied:api_key"


# ---------------------------------------------------------------------------
# Flow 4: Cascade lifecycle
# ---------------------------------------------------------------------------


class TestCascadeLifecycle:
    """E2E: parent tightened → children re-intersected → terminate → reclaim."""

    def test_full_cascade_lifecycle(self) -> None:
        mgr = CascadeManager()

        # Build hierarchy
        mgr.register("ceo", None, {"financial": {"limit": 1000.0}}, budget_allocated=1000.0)
        mgr.register("vp", "ceo", {"financial": {"limit": 500.0}}, budget_allocated=500.0)
        mgr.register("lead", "vp", {"financial": {"limit": 200.0}}, budget_allocated=200.0)
        mgr.register("dev-1", "lead", {"financial": {"limit": 50.0}}, budget_allocated=50.0)
        mgr.register("dev-2", "lead", {"financial": {"limit": 50.0}}, budget_allocated=50.0)

        # CEO tightens envelope
        events = mgr.tighten_envelope("ceo", {"financial": {"limit": 300.0}})
        re_intersected = [
            e for e in events if e.event_type == CascadeEventType.CHILD_RE_INTERSECTED
        ]
        assert len(re_intersected) == 4  # vp, lead, dev-1, dev-2

        # All descendants' limits are now <= 300
        for agent_id in ["vp", "lead", "dev-1", "dev-2"]:
            env = mgr.get_envelope(agent_id)
            assert env is not None
            assert env["financial"]["limit"] <= 300.0

        # Terminate lead → dev-1 and dev-2 cascade
        mgr.record_consumption("dev-1", 20.0)
        events = mgr.cascade_terminate("lead")
        terminated = [e for e in events if e.event_type == CascadeEventType.CASCADE_TERMINATE]
        assert len(terminated) == 3  # dev-1, dev-2, lead

        reclaimed = [e for e in events if e.event_type == CascadeEventType.BUDGET_RECLAIMED]
        assert len(reclaimed) >= 1  # at least dev-1 had unused budget

    def test_no_orphaned_agents(self) -> None:
        """After cascade terminate, no agents remain tracked."""
        mgr = CascadeManager()
        mgr.register("root", None, {})
        mgr.register("a", "root", {})
        mgr.register("b", "root", {})
        mgr.cascade_terminate("root")
        assert mgr.get_envelope("root") is None
        assert mgr.get_envelope("a") is None
        assert mgr.get_envelope("b") is None


# ---------------------------------------------------------------------------
# Flow 5: Vacancy lifecycle
# ---------------------------------------------------------------------------


class TestVacancyLifecycle:
    """E2E: parent terminated → orphan → acting parent → resume."""

    def test_full_vacancy_lifecycle(self) -> None:
        mgr = VacancyManager(deadline_seconds=60.0)

        # Build hierarchy: CEO → VP → Lead → Dev
        mgr.register("ceo", None)
        mgr.register("vp", "ceo")
        mgr.register("lead", "vp")
        mgr.register("dev", "lead")

        # VP terminates → Lead gets CEO as acting parent
        events = mgr.handle_parent_termination("vp")
        orphan_events = [e for e in events if e.event_type == "orphan_detected"]
        acting_events = [e for e in events if e.event_type == "acting_parent_designated"]
        assert len(orphan_events) == 1  # lead is orphaned
        assert len(acting_events) == 1  # ceo auto-designated
        assert acting_events[0].details["acting_parent"] == "ceo"

        # Lead is NOT orphaned (has acting parent)
        assert not mgr.is_orphaned("lead")
