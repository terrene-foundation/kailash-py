# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""P3-01 Security regression tests: NaN/Inf injection, state machine fuzzing.

All numeric paths must reject NaN/Inf. All state machines must reject
invalid transitions. All error paths must fail-closed.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from kaizen_agents.governance.budget import BudgetTracker
from kaizen_agents.governance.bypass import BypassManager
from kaizen_agents.governance.cascade import CascadeManager
from kaizen_agents.governance.clearance import (
    ClassificationAssigner,
    ClassifiedValue,
    ClearanceEnforcer,
    DataClassification,
)
from kaizen_agents.governance.dereliction import DerelictionDetector
from kaizen_agents.governance.vacancy import VacancyManager
from kaizen_agents.supervisor import GovernedSupervisor


# =========================================================================
# NaN/Inf Injection Tests
# =========================================================================


class TestNaNInjection:
    """NaN injection must be rejected on ALL numeric paths."""

    def test_budget_allocate_nan(self) -> None:
        tracker = BudgetTracker()
        with pytest.raises(ValueError, match="finite"):
            tracker.allocate("agent", float("nan"))

    def test_budget_allocate_inf(self) -> None:
        tracker = BudgetTracker()
        with pytest.raises(ValueError, match="finite"):
            tracker.allocate("agent", float("inf"))

    def test_budget_allocate_neg_inf(self) -> None:
        tracker = BudgetTracker()
        with pytest.raises(ValueError, match="finite"):
            tracker.allocate("agent", float("-inf"))

    def test_budget_consume_nan(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("agent", 100.0)
        with pytest.raises(ValueError, match="finite"):
            tracker.record_consumption("agent", float("nan"))

    def test_budget_consume_inf(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("agent", 100.0)
        with pytest.raises(ValueError, match="finite"):
            tracker.record_consumption("agent", float("inf"))

    def test_budget_reallocate_nan(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("a", 50.0)
        tracker.allocate("b", 50.0)
        with pytest.raises(ValueError, match="finite"):
            tracker.reallocate("a", "b", float("nan"))

    def test_budget_reallocate_inf(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("a", 50.0)
        tracker.allocate("b", 50.0)
        with pytest.raises(ValueError, match="finite"):
            tracker.reallocate("a", "b", float("inf"))

    def test_cascade_budget_nan(self) -> None:
        mgr = CascadeManager()
        with pytest.raises(ValueError, match="finite"):
            mgr.register("agent", None, {}, budget_allocated=float("nan"))

    def test_cascade_budget_inf(self) -> None:
        mgr = CascadeManager()
        with pytest.raises(ValueError, match="finite"):
            mgr.register("agent", None, {}, budget_allocated=float("inf"))

    def test_cascade_consume_nan(self) -> None:
        mgr = CascadeManager()
        mgr.register("agent", None, {})
        with pytest.raises(ValueError, match="finite"):
            mgr.record_consumption("agent", float("nan"))

    def test_dereliction_threshold_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DerelictionDetector(threshold=float("nan"))

    def test_dereliction_threshold_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            DerelictionDetector(threshold=float("inf"))

    def test_supervisor_budget_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            GovernedSupervisor(budget_usd=float("nan"))

    def test_supervisor_budget_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            GovernedSupervisor(budget_usd=float("inf"))

    def test_supervisor_timeout_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            GovernedSupervisor(timeout_seconds=float("nan"))

    def test_supervisor_warning_threshold_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            GovernedSupervisor(warning_threshold=float("nan"))

    def test_budget_tracker_threshold_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            BudgetTracker(warning_threshold=float("nan"))

    def test_budget_tracker_hold_threshold_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            BudgetTracker(hold_threshold=float("nan"))


# =========================================================================
# Negative Value Injection
# =========================================================================


class TestNegativeInjection:
    """Negative values must be rejected on budget paths."""

    def test_budget_allocate_negative(self) -> None:
        tracker = BudgetTracker()
        with pytest.raises(ValueError, match="non-negative"):
            tracker.allocate("agent", -10.0)

    def test_budget_consume_negative(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("agent", 100.0)
        with pytest.raises(ValueError, match="non-negative"):
            tracker.record_consumption("agent", -5.0)

    def test_budget_reallocate_zero(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("a", 50.0)
        tracker.allocate("b", 50.0)
        with pytest.raises(ValueError, match="positive"):
            tracker.reallocate("a", "b", 0.0)

    def test_cascade_budget_negative(self) -> None:
        mgr = CascadeManager()
        with pytest.raises(ValueError, match="non-negative"):
            mgr.register("agent", None, {}, budget_allocated=-1.0)


# =========================================================================
# Classification Bypass Attempts
# =========================================================================


class TestClassificationBypass:
    """Attempts to bypass classification through various vectors."""

    def test_monotonic_floor_enforced(self) -> None:
        """Cannot lower classification once set."""
        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("key", "val", DataClassification.C3_SECRET))
        with pytest.raises(ValueError, match="Monotonic floor"):
            enforcer.register_value(ClassifiedValue("key", "val", DataClassification.C0_PUBLIC))

    def test_hidden_api_key_in_text(self) -> None:
        """API key embedded in free text is still classified as secret."""
        assigner = ClassificationAssigner()
        text = "The config says api_key = sk-abc123def456ghi789jklmnop and that's the key"
        level = assigner.classify("config_text", text)
        assert level >= DataClassification.C3_SECRET

    def test_ssn_in_description(self) -> None:
        """SSN embedded in a description field is classified as top-secret."""
        assigner = ClassificationAssigner()
        level = assigner.classify("description", "Employee SSN: 123-45-6789")
        assert level >= DataClassification.C4_TOP_SECRET

    def test_c1_agent_cannot_see_c3(self) -> None:
        """C1-cleared agent cannot access C3 data through filter."""
        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("secret", "data", DataClassification.C3_SECRET))
        visible = enforcer.filter_for_clearance(DataClassification.C1_INTERNAL)
        assert "secret" not in visible

    def test_c0_agent_sees_nothing_classified(self) -> None:
        """C0 agent only sees C0 data."""
        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("pub", "x", DataClassification.C0_PUBLIC))
        enforcer.register_value(ClassifiedValue("int", "y", DataClassification.C1_INTERNAL))
        enforcer.register_value(ClassifiedValue("sec", "z", DataClassification.C3_SECRET))
        visible = enforcer.filter_for_clearance(DataClassification.C0_PUBLIC)
        assert visible == {"pub": "x"}


# =========================================================================
# Bypass Abuse Scenarios
# =========================================================================


class TestBypassAbuse:
    """Emergency bypass abuse prevention."""

    def test_bypass_requires_reason(self) -> None:
        mgr = BypassManager()
        with pytest.raises(ValueError, match="reason"):
            mgr.grant_bypass("agent", "", "admin", 60.0)

    def test_bypass_requires_authorizer(self) -> None:
        mgr = BypassManager()
        with pytest.raises(ValueError, match="authorizer"):
            mgr.grant_bypass("agent", "reason", "", 60.0)

    def test_bypass_requires_positive_duration(self) -> None:
        mgr = BypassManager()
        with pytest.raises(ValueError, match="positive"):
            mgr.grant_bypass("agent", "reason", "admin", 0.0)
        with pytest.raises(ValueError, match="positive"):
            mgr.grant_bypass("agent", "reason", "admin", -60.0)

    def test_bypass_auto_expires(self) -> None:
        """Bypass cannot persist indefinitely."""
        import time

        mgr = BypassManager()
        mgr.grant_bypass("agent", "test", "admin", 0.01)
        time.sleep(0.02)
        assert not mgr.is_bypassed("agent")

    def test_revoked_bypass_not_active(self) -> None:
        mgr = BypassManager()
        mgr.grant_bypass("agent", "test", "admin", 300.0)
        mgr.revoke_bypass("agent")
        assert not mgr.is_bypassed("agent")


# =========================================================================
# Bounded Collections
# =========================================================================


class TestRedTeamFixes:
    """Regression tests for specific red team findings."""

    def test_c1_cascade_intersect_nan_rejected(self) -> None:
        """C1: NaN in _intersect_dicts raises ValueError."""
        mgr = CascadeManager()
        mgr.register("root", None, {"financial": {"limit": 100.0}})
        mgr.register("child", "root", {"financial": {"limit": float("nan")}})
        with pytest.raises(ValueError, match="Non-finite"):
            mgr.tighten_envelope("root", {"financial": {"limit": 50.0}})

    def test_c1_cascade_intersect_inf_rejected(self) -> None:
        """C1: Inf in _intersect_dicts raises ValueError."""
        mgr = CascadeManager()
        mgr.register("root", None, {"financial": {"limit": 100.0}})
        mgr.register("child", "root", {"financial": {"limit": float("inf")}})
        with pytest.raises(ValueError, match="Non-finite"):
            mgr.tighten_envelope("root", {"financial": {"limit": 50.0}})

    def test_f01_supervisor_reentrant(self) -> None:
        """F-01: run() can be called multiple times on same supervisor."""
        import asyncio

        supervisor = GovernedSupervisor(budget_usd=10.0)

        async def run_twice() -> None:
            await supervisor.run("Task 1")
            await supervisor.run("Task 2")  # must not raise ValueError

        asyncio.run(run_twice())

    def test_f02_cascade_propagates_via_direct_parent(self) -> None:
        """F-02: tighten_envelope re-intersects against direct parent, not originator."""
        mgr = CascadeManager()
        mgr.register("root", None, {"financial": {"limit": 100.0}})
        mgr.register("child", "root", {"financial": {"limit": 80.0}})
        mgr.register("grandchild", "child", {"financial": {"limit": 60.0}})

        mgr.tighten_envelope("root", {"financial": {"limit": 50.0}})
        # child: min(50, 80) = 50
        # grandchild: min(child's new=50, grandchild's old=60) = 50
        assert mgr.get_envelope("child")["financial"]["limit"] == 50.0
        assert mgr.get_envelope("grandchild")["financial"]["limit"] == 50.0

    def test_f08_dereliction_stats_monotonic(self) -> None:
        """F-08: dereliction_count is monotonic even after deque eviction."""
        detector = DerelictionDetector(threshold=0.05, maxlen=5)
        for i in range(20):
            detector.check_delegation(
                "p",
                f"c-{i}",
                {"financial": {"limit": 100}},
                {"financial": {"limit": 100}},
            )
        stats = detector.get_stats()
        # All 20 had identical envelopes → all 20 flagged, but deque only keeps 5
        assert stats.dereliction_count == 20  # monotonic, not bounded by deque
        assert stats.total_delegations == 20

    def test_c3_bypass_nan_duration_rejected(self) -> None:
        """C3: NaN duration_seconds is rejected."""
        mgr = BypassManager()
        with pytest.raises(ValueError, match="finite"):
            mgr.grant_bypass("agent", "reason", "admin", float("nan"))

    def test_c3_bypass_inf_duration_rejected(self) -> None:
        """C3: Inf duration_seconds is rejected (would create permanent bypass)."""
        mgr = BypassManager()
        with pytest.raises(ValueError, match="finite"):
            mgr.grant_bypass("agent", "reason", "admin", float("inf"))

    def test_c4_tighten_cannot_widen(self) -> None:
        """C4: tighten_envelope enforces monotonic tightening via intersection."""
        mgr = CascadeManager()
        mgr.register("root", None, {"financial": {"limit": 50.0}})
        # Attempt to widen to 100.0 — should be intersected back to 50.0
        mgr.tighten_envelope("root", {"financial": {"limit": 100.0}})
        env = mgr.get_envelope("root")
        assert env["financial"]["limit"] == 50.0  # tightening enforced

    def test_h6_vacancy_nan_deadline_rejected(self) -> None:
        """H6: NaN deadline_seconds is rejected."""
        with pytest.raises(ValueError, match="finite"):
            VacancyManager(deadline_seconds=float("nan"))

    def test_h6_vacancy_inf_deadline_rejected(self) -> None:
        """H6: Inf deadline_seconds is rejected."""
        with pytest.raises(ValueError, match="finite"):
            VacancyManager(deadline_seconds=float("inf"))

    def test_f10_type_mismatch_uses_parent(self) -> None:
        """F-10: type mismatch in intersect takes parent (more restrictive)."""
        mgr = CascadeManager()
        mgr.register("root", None, {"financial": {"limit": 100.0}})
        mgr.register("child", "root", {"financial": {"limit": "unlimited"}})
        mgr.tighten_envelope("root", {"financial": {"limit": 50.0}})
        child_env = mgr.get_envelope("child")
        # Parent's numeric 50.0 should be used, not child's "unlimited" string
        assert child_env["financial"]["limit"] == 50.0


class TestBoundedCollections:
    """Verify bounded collections prevent OOM."""

    def test_audit_trail_bounded(self) -> None:
        from kaizen_agents.audit.trail import AuditTrail

        trail = AuditTrail(maxlen=100)
        for i in range(200):
            trail.record_action(f"agent-{i}", f"action-{i}", {})
        records = trail.to_list()
        assert len(records) == 100  # oldest evicted

    def test_dereliction_warnings_bounded(self) -> None:
        detector = DerelictionDetector(threshold=0.05, maxlen=50)
        for i in range(100):
            detector.check_delegation(
                "p",
                f"c-{i}",
                {"financial": {"limit": 100}},
                {"financial": {"limit": 100}},
            )
        assert len(detector.get_warnings()) == 50

    def test_bypass_history_bounded(self) -> None:
        mgr = BypassManager(maxlen=50)
        for i in range(100):
            mgr.grant_bypass(f"agent-{i}", "test", "admin", 0.01)
        assert len(mgr.get_history()) == 50
