# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for kaizen-agents governance modules (P2-02 through P2-08)."""

from __future__ import annotations

import time

import pytest

from kaizen_agents.governance.accountability import AccountabilityTracker
from kaizen_agents.governance.budget import BudgetTracker
from kaizen_agents.governance.bypass import BypassManager
from kaizen_agents.governance.cascade import CascadeEventType, CascadeManager
from kaizen_agents.governance.clearance import (
    ClassificationAssigner,
    ClassifiedValue,
    ClearanceEnforcer,
    DataClassification,
)
from kaizen_agents.governance.dereliction import DerelictionDetector
from kaizen_agents.governance.vacancy import VacancyManager


# =========================================================================
# P2-02: D/T/R Accountability
# =========================================================================


class TestAccountabilityTracker:
    """Test D/T/R positional addressing for agent hierarchies."""

    def test_root_gets_d1_r1(self) -> None:
        tracker = AccountabilityTracker()
        record = tracker.register_root("root-001")
        assert str(record.address) == "D1-R1"

    def test_child_gets_team_address(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root")
        child = tracker.register_child("child-1", "root")
        assert str(child.address) == "D1-R1-T1-R1"

    def test_multiple_children_sequential_numbering(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root")
        c1 = tracker.register_child("child-1", "root")
        c2 = tracker.register_child("child-2", "root")
        c3 = tracker.register_child("child-3", "root")
        assert str(c1.address) == "D1-R1-T1-R1"
        assert str(c2.address) == "D1-R1-T2-R1"
        assert str(c3.address) == "D1-R1-T3-R1"

    def test_grandchild_address(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root")
        tracker.register_child("child", "root")
        grandchild = tracker.register_child("grandchild", "child")
        assert str(grandchild.address) == "D1-R1-T1-R1-T1-R1"

    def test_sibling_detection(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root")
        tracker.register_child("c1", "root")
        tracker.register_child("c2", "root")
        siblings = tracker.get_siblings("c1")
        assert len(siblings) == 1
        assert siblings[0].instance_id == "c2"

    def test_root_has_no_siblings(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root")
        assert tracker.get_siblings("root") == []

    def test_accountability_trace(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root", policy_source="human-admin")
        tracker.register_child("child", "root")
        tracker.register_child("grandchild", "child")
        chain = tracker.trace_accountability("grandchild")
        assert [r.instance_id for r in chain] == ["root", "child", "grandchild"]

    def test_policy_source_query(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root", policy_source="human-admin")
        tracker.register_child("child", "root")
        assert tracker.query_policy_source("child") == "human-admin"

    def test_policy_source_inheritance(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root", policy_source="admin@corp.com")
        child = tracker.register_child("child", "root")
        assert child.policy_source == "admin@corp.com"

    def test_duplicate_registration_raises(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root")
        with pytest.raises(ValueError, match="already registered"):
            tracker.register_root("root")

    def test_unknown_parent_raises(self) -> None:
        tracker = AccountabilityTracker()
        with pytest.raises(ValueError, match="not registered"):
            tracker.register_child("orphan", "nonexistent")

    def test_unregister(self) -> None:
        tracker = AccountabilityTracker()
        tracker.register_root("root")
        tracker.unregister("root")
        assert tracker.get_address("root") is None
        assert tracker.agent_count == 0

    def test_get_address_unknown(self) -> None:
        tracker = AccountabilityTracker()
        assert tracker.get_address("nonexistent") is None

    def test_envelope_snapshot_stored(self) -> None:
        tracker = AccountabilityTracker()
        env = {"financial": {"limit": 100.0}}
        record = tracker.register_root("root", envelope=env)
        assert record.envelope_snapshot == env


# =========================================================================
# P2-03: Knowledge Clearance Enforcement
# =========================================================================


class TestClearanceEnforcer:
    """Test classification-aware context filtering."""

    def test_register_and_filter(self) -> None:
        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("public", "hello", DataClassification.PUBLIC))
        enforcer.register_value(ClassifiedValue("secret", "sk-123", DataClassification.SECRET))

        visible = enforcer.filter_for_clearance(DataClassification.RESTRICTED)
        assert "public" in visible
        assert "secret" not in visible

    def test_higher_clearance_sees_more(self) -> None:
        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("internal", "data", DataClassification.RESTRICTED))
        enforcer.register_value(ClassifiedValue("secret", "key", DataClassification.SECRET))

        c1 = enforcer.filter_for_clearance(DataClassification.RESTRICTED)
        c3 = enforcer.filter_for_clearance(DataClassification.SECRET)
        assert len(c1) == 1
        assert len(c3) == 2

    def test_monotonic_floor_prevents_downgrade(self) -> None:
        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("key", "val", DataClassification.SECRET))
        with pytest.raises(ValueError, match="Monotonic floor"):
            enforcer.register_value(ClassifiedValue("key", "val", DataClassification.RESTRICTED))

    def test_monotonic_floor_allows_upgrade(self) -> None:
        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("key", "val", DataClassification.RESTRICTED))
        enforcer.register_value(ClassifiedValue("key", "val", DataClassification.SECRET))
        assert enforcer.get_classification("key") == DataClassification.SECRET

    def test_is_visible(self) -> None:
        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("data", "x", DataClassification.CONFIDENTIAL))
        assert enforcer.is_visible("data", DataClassification.CONFIDENTIAL) is True
        assert enforcer.is_visible("data", DataClassification.RESTRICTED) is False
        assert enforcer.is_visible("data", DataClassification.SECRET) is True

    def test_is_visible_unknown_key(self) -> None:
        enforcer = ClearanceEnforcer()
        assert enforcer.is_visible("nonexistent", DataClassification.TOP_SECRET) is False


class TestClassificationAssigner:
    """Test deterministic pre-filter for known patterns."""

    def test_api_key_detected(self) -> None:
        assigner = ClassificationAssigner()
        level = assigner.classify("value", "sk-abc123def456ghi789jklmnop")
        assert level >= DataClassification.SECRET

    def test_email_detected(self) -> None:
        assigner = ClassificationAssigner()
        level = assigner.classify("contact", "user@example.com")
        assert level >= DataClassification.CONFIDENTIAL

    def test_ssn_detected(self) -> None:
        assigner = ClassificationAssigner()
        level = assigner.classify("data", "123-45-6789")
        assert level >= DataClassification.TOP_SECRET

    def test_private_key_detected(self) -> None:
        assigner = ClassificationAssigner()
        level = assigner.classify("cert", "-----BEGIN RSA PRIVATE KEY-----")
        assert level >= DataClassification.TOP_SECRET

    def test_key_name_heuristic(self) -> None:
        assigner = ClassificationAssigner()
        level = assigner.classify("api_key", "some_value")
        assert level >= DataClassification.SECRET

    def test_normal_value_gets_default(self) -> None:
        assigner = ClassificationAssigner()
        level = assigner.classify("greeting", "hello world")
        assert level == DataClassification.RESTRICTED

    def test_classify_and_wrap(self) -> None:
        assigner = ClassificationAssigner()
        cv = assigner.classify_and_wrap("secret_key", "sk-abcdefghijklmnopqrstuvwx")
        assert isinstance(cv, ClassifiedValue)
        assert cv.classification >= DataClassification.SECRET


# =========================================================================
# P2-04: Cascade Revocation
# =========================================================================


class TestCascadeManager:
    """Test envelope tightening propagation and cascade termination."""

    def test_register_agents(self) -> None:
        mgr = CascadeManager()
        mgr.register("root", None, {"financial": {"limit": 100.0}})
        mgr.register("child", "root", {"financial": {"limit": 50.0}})
        assert mgr.get_envelope("root") == {"financial": {"limit": 100.0}}
        assert mgr.get_envelope("child") == {"financial": {"limit": 50.0}}

    def test_tighten_propagates_to_children(self) -> None:
        mgr = CascadeManager()
        mgr.register("root", None, {"financial": {"limit": 100.0}})
        mgr.register("child", "root", {"financial": {"limit": 50.0}})
        events = mgr.tighten_envelope("root", {"financial": {"limit": 30.0}})

        tightened = [e for e in events if e.event_type == CascadeEventType.ENVELOPE_TIGHTENED]
        re_intersected = [
            e for e in events if e.event_type == CascadeEventType.CHILD_RE_INTERSECTED
        ]
        assert len(tightened) == 1
        assert len(re_intersected) == 1

        child_env = mgr.get_envelope("child")
        assert child_env is not None
        assert child_env["financial"]["limit"] == 30.0  # min(30, 50) = 30

    def test_tighten_propagates_deep_hierarchy(self) -> None:
        mgr = CascadeManager()
        mgr.register("root", None, {"financial": {"limit": 100.0}})
        mgr.register("child", "root", {"financial": {"limit": 80.0}})
        mgr.register("grandchild", "child", {"financial": {"limit": 60.0}})

        events = mgr.tighten_envelope("root", {"financial": {"limit": 40.0}})
        re_intersected = [
            e for e in events if e.event_type == CascadeEventType.CHILD_RE_INTERSECTED
        ]
        assert len(re_intersected) == 2  # child and grandchild

        assert mgr.get_envelope("grandchild")["financial"]["limit"] == 40.0

    def test_cascade_terminate(self) -> None:
        mgr = CascadeManager()
        mgr.register("root", None, {})
        mgr.register("child", "root", {})
        mgr.register("grandchild", "child", {})

        events = mgr.cascade_terminate("root")
        terminated = [e for e in events if e.event_type == CascadeEventType.CASCADE_TERMINATE]
        # grandchild, child, root
        assert len(terminated) == 3
        assert mgr.get_envelope("root") is None
        assert mgr.get_envelope("child") is None
        assert mgr.get_envelope("grandchild") is None

    def test_budget_reclaimed_on_cascade(self) -> None:
        mgr = CascadeManager()
        mgr.register("root", None, {}, budget_allocated=100.0)
        mgr.register("child", "root", {}, budget_allocated=30.0)
        mgr.record_consumption("child", 10.0)

        events = mgr.cascade_terminate("root")
        reclaimed = [e for e in events if e.event_type == CascadeEventType.BUDGET_RECLAIMED]
        assert len(reclaimed) == 1
        assert reclaimed[0].details["amount"] == 20.0  # 30 - 10 = 20

    def test_nan_budget_rejected(self) -> None:
        mgr = CascadeManager()
        with pytest.raises(ValueError, match="finite"):
            mgr.register("agent", None, {}, budget_allocated=float("nan"))

    def test_negative_budget_rejected(self) -> None:
        mgr = CascadeManager()
        with pytest.raises(ValueError, match="non-negative"):
            mgr.register("agent", None, {}, budget_allocated=-10.0)

    def test_duplicate_registration_raises(self) -> None:
        mgr = CascadeManager()
        mgr.register("root", None, {})
        with pytest.raises(ValueError, match="already registered"):
            mgr.register("root", None, {})

    def test_tighten_unregistered_raises(self) -> None:
        mgr = CascadeManager()
        with pytest.raises(ValueError, match="not registered"):
            mgr.tighten_envelope("ghost", {})

    def test_list_intersection(self) -> None:
        mgr = CascadeManager()
        mgr.register(
            "root",
            None,
            {"operational": {"allowed": ["read", "write", "deploy"]}},
        )
        mgr.register(
            "child",
            "root",
            {"operational": {"allowed": ["read", "write"]}},
        )
        events = mgr.tighten_envelope(
            "root",
            {"operational": {"allowed": ["read"]}},
        )
        child_env = mgr.get_envelope("child")
        assert child_env is not None
        assert child_env["operational"]["allowed"] == ["read"]


# =========================================================================
# P2-05: Vacancy Handling
# =========================================================================


class TestVacancyManager:
    """Test orphan detection, acting parent, and suspension."""

    def test_orphan_detected(self) -> None:
        mgr = VacancyManager()
        mgr.register("root", None)
        mgr.register("child", "root")
        events = mgr.handle_parent_termination("root")
        orphan_events = [e for e in events if e.event_type == "orphan_detected"]
        assert len(orphan_events) == 1
        assert orphan_events[0].agent_id == "child"

    def test_grandparent_auto_designated(self) -> None:
        mgr = VacancyManager()
        mgr.register("grandparent", None)
        mgr.register("parent", "grandparent")
        mgr.register("child", "parent")
        events = mgr.handle_parent_termination("parent")
        acting = [e for e in events if e.event_type == "acting_parent_designated"]
        assert len(acting) == 1
        assert acting[0].details["acting_parent"] == "grandparent"

    def test_manual_acting_parent_designation(self) -> None:
        mgr = VacancyManager()
        mgr.register("root", None)
        mgr.register("child", "root")
        mgr.handle_parent_termination("root")
        mgr.register("foster", None)
        event = mgr.designate_acting_parent("child", "foster")
        assert event is not None
        assert event.details["acting_parent"] == "foster"

    def test_deadline_expiration_suspends(self) -> None:
        mgr = VacancyManager(deadline_seconds=0.01)
        mgr.register("root", None)
        mgr.register("child", "root")
        mgr.handle_parent_termination("root")
        time.sleep(0.02)
        events = mgr.check_deadlines()
        suspended = [e for e in events if e.event_type == "orphan_suspended"]
        assert len(suspended) == 1
        assert suspended[0].agent_id == "child"

    def test_no_suspension_with_acting_parent(self) -> None:
        mgr = VacancyManager(deadline_seconds=0.01)
        mgr.register("grandparent", None)
        mgr.register("parent", "grandparent")
        mgr.register("child", "parent")
        mgr.handle_parent_termination("parent")  # grandparent auto-designated
        time.sleep(0.02)
        events = mgr.check_deadlines()
        suspended = [e for e in events if e.event_type == "orphan_suspended"]
        assert len(suspended) == 0

    def test_is_orphaned(self) -> None:
        mgr = VacancyManager()
        mgr.register("root", None)
        mgr.register("child", "root")
        mgr.handle_parent_termination("root")
        assert mgr.is_orphaned("child") is True

    def test_is_orphaned_with_acting_parent(self) -> None:
        mgr = VacancyManager()
        mgr.register("grandparent", None)
        mgr.register("parent", "grandparent")
        mgr.register("child", "parent")
        mgr.handle_parent_termination("parent")
        # grandparent was auto-designated, so child has acting parent
        assert mgr.is_orphaned("child") is False

    def test_invalid_deadline_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            VacancyManager(deadline_seconds=0)


# =========================================================================
# P2-06: Gradient Dereliction Detection
# =========================================================================


class TestDerelictionDetector:
    """Test detection of insufficient envelope tightening."""

    def test_identical_envelopes_flagged(self) -> None:
        detector = DerelictionDetector(threshold=0.05)
        warning = detector.check_delegation(
            parent_id="root",
            child_id="child",
            parent_envelope={"financial": {"limit": 100.0}},
            child_envelope={"financial": {"limit": 100.0}},
        )
        assert warning is not None
        assert warning.tightening_ratio < 0.05

    def test_sufficient_tightening_not_flagged(self) -> None:
        detector = DerelictionDetector(threshold=0.05)
        warning = detector.check_delegation(
            parent_id="root",
            child_id="child",
            parent_envelope={
                "financial": {"limit": 100.0},
                "operational": {"allowed": ["read", "write", "deploy"]},
            },
            child_envelope={
                "financial": {"limit": 50.0},
                "operational": {"allowed": ["read"]},
            },
        )
        assert warning is None

    def test_stats_tracking(self) -> None:
        detector = DerelictionDetector(threshold=0.05)
        detector.check_delegation(
            "p", "c1", {"financial": {"limit": 100}}, {"financial": {"limit": 100}}
        )
        detector.check_delegation(
            "p", "c2", {"financial": {"limit": 100}}, {"financial": {"limit": 50}}
        )
        stats = detector.get_stats()
        assert stats.total_delegations == 2
        assert stats.dereliction_count == 1
        assert stats.dereliction_rate == 0.5

    def test_warnings_stored(self) -> None:
        detector = DerelictionDetector(threshold=0.05)
        detector.check_delegation(
            "p", "c", {"financial": {"limit": 100}}, {"financial": {"limit": 100}}
        )
        warnings = detector.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].parent_id == "p"

    def test_invalid_threshold(self) -> None:
        with pytest.raises(ValueError):
            DerelictionDetector(threshold=float("nan"))
        with pytest.raises(ValueError):
            DerelictionDetector(threshold=-0.1)
        with pytest.raises(ValueError):
            DerelictionDetector(threshold=1.5)


# =========================================================================
# P2-07: Emergency Bypass
# =========================================================================


class TestBypassManager:
    """Test emergency bypass with audit trail."""

    def test_grant_bypass(self) -> None:
        mgr = BypassManager()
        record = mgr.grant_bypass(
            agent_id="agent-001",
            reason="Incident P-123",
            authorizer="admin@corp.com",
            duration_seconds=300.0,
            original_envelope={"financial": {"limit": 100.0}},
        )
        assert record.agent_id == "agent-001"
        assert record.reason == "Incident P-123"
        assert mgr.is_bypassed("agent-001") is True

    def test_bypass_not_bypassed(self) -> None:
        mgr = BypassManager()
        assert mgr.is_bypassed("nobody") is False

    def test_bypass_expiration(self) -> None:
        mgr = BypassManager()
        mgr.grant_bypass(
            agent_id="agent-001",
            reason="test",
            authorizer="admin",
            duration_seconds=0.01,
        )
        time.sleep(0.02)
        assert mgr.is_bypassed("agent-001") is False

    def test_revoke_bypass(self) -> None:
        mgr = BypassManager()
        mgr.grant_bypass(
            agent_id="agent-001",
            reason="test",
            authorizer="admin",
            duration_seconds=300.0,
        )
        revoked = mgr.revoke_bypass("agent-001")
        assert revoked is not None
        assert revoked.revoked is True
        assert mgr.is_bypassed("agent-001") is False

    def test_original_envelope_retrieval(self) -> None:
        mgr = BypassManager()
        env = {"financial": {"limit": 50.0}}
        mgr.grant_bypass(
            agent_id="agent-001",
            reason="test",
            authorizer="admin",
            duration_seconds=300.0,
            original_envelope=env,
        )
        assert mgr.get_original_envelope("agent-001") == env

    def test_empty_reason_rejected(self) -> None:
        mgr = BypassManager()
        with pytest.raises(ValueError, match="reason"):
            mgr.grant_bypass("a", "", "admin", 60.0)

    def test_empty_authorizer_rejected(self) -> None:
        mgr = BypassManager()
        with pytest.raises(ValueError, match="authorizer"):
            mgr.grant_bypass("a", "reason", "", 60.0)

    def test_negative_duration_rejected(self) -> None:
        mgr = BypassManager()
        with pytest.raises(ValueError, match="positive"):
            mgr.grant_bypass("a", "reason", "admin", -10.0)

    def test_check_expirations(self) -> None:
        mgr = BypassManager()
        mgr.grant_bypass("a1", "test", "admin", 0.01)
        mgr.grant_bypass("a2", "test", "admin", 300.0)
        time.sleep(0.02)
        expired = mgr.check_expirations()
        assert len(expired) == 1
        assert expired[0].agent_id == "a1"

    def test_history(self) -> None:
        mgr = BypassManager()
        mgr.grant_bypass("a", "reason", "admin", 300.0)
        history = mgr.get_history()
        assert len(history) == 1


# =========================================================================
# P2-08: Budget Reclamation and Warnings
# =========================================================================


class TestBudgetTracker:
    """Test budget tracking, warnings, reclamation, and reallocation."""

    def test_allocate_and_consume(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("agent-001", 100.0)
        tracker.record_consumption("agent-001", 40.0)
        snap = tracker.get_snapshot("agent-001")
        assert snap is not None
        assert snap.allocated == 100.0
        assert snap.consumed == 40.0
        assert snap.remaining == 60.0
        assert snap.utilization == pytest.approx(0.4)

    def test_warning_at_threshold(self) -> None:
        tracker = BudgetTracker(warning_threshold=0.70)
        tracker.allocate("agent-001", 100.0)
        events = tracker.record_consumption("agent-001", 75.0)
        warnings = [e for e in events if e.event_type == "warning"]
        assert len(warnings) == 1
        assert warnings[0].details["utilization"] == pytest.approx(0.75)

    def test_no_warning_below_threshold(self) -> None:
        tracker = BudgetTracker(warning_threshold=0.70)
        tracker.allocate("agent-001", 100.0)
        events = tracker.record_consumption("agent-001", 50.0)
        warnings = [e for e in events if e.event_type == "warning"]
        assert len(warnings) == 0

    def test_exhaustion_held(self) -> None:
        tracker = BudgetTracker(warning_threshold=0.70, hold_threshold=1.0)
        tracker.allocate("agent-001", 100.0)
        events = tracker.record_consumption("agent-001", 100.0)
        held = [e for e in events if e.event_type == "exhaustion_held"]
        assert len(held) == 1
        assert tracker.is_held("agent-001") is True

    def test_reclaim_on_completion(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("root", 100.0)
        tracker.allocate("child", 30.0, parent_id="root")
        tracker.record_consumption("child", 10.0)
        event = tracker.reclaim("child")
        assert event is not None
        assert event.details["reclaimed"] == 20.0
        assert event.details["returned_to"] == "root"
        # Root should have original 100 + 20 reclaimed
        snap = tracker.get_snapshot("root")
        assert snap is not None
        assert snap.allocated == 120.0

    def test_reallocation_resolves_hold(self) -> None:
        tracker = BudgetTracker(warning_threshold=0.70, hold_threshold=1.0)
        tracker.allocate("root", 200.0)
        tracker.allocate("a", 50.0, parent_id="root")
        tracker.allocate("b", 50.0, parent_id="root")
        tracker.record_consumption("a", 50.0)  # a is exhausted
        assert tracker.is_held("a") is True
        event = tracker.reallocate("b", "a", 20.0)
        assert event is not None
        assert tracker.is_held("a") is False  # resolved by reallocation

    def test_nan_allocation_rejected(self) -> None:
        tracker = BudgetTracker()
        with pytest.raises(ValueError, match="finite"):
            tracker.allocate("agent", float("nan"))

    def test_negative_allocation_rejected(self) -> None:
        tracker = BudgetTracker()
        with pytest.raises(ValueError, match="non-negative"):
            tracker.allocate("agent", -10.0)

    def test_nan_consumption_rejected(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("agent", 100.0)
        with pytest.raises(ValueError, match="finite"):
            tracker.record_consumption("agent", float("nan"))

    def test_unallocated_consumption_rejected(self) -> None:
        tracker = BudgetTracker()
        with pytest.raises(ValueError, match="no budget"):
            tracker.record_consumption("ghost", 10.0)

    def test_reallocation_insufficient_donor(self) -> None:
        tracker = BudgetTracker()
        tracker.allocate("a", 10.0)
        tracker.allocate("b", 10.0)
        tracker.record_consumption("a", 8.0)
        event = tracker.reallocate("a", "b", 5.0)
        assert event is None  # only 2.0 remaining, can't donate 5.0

    def test_warning_not_repeated(self) -> None:
        tracker = BudgetTracker(warning_threshold=0.70)
        tracker.allocate("agent", 100.0)
        events1 = tracker.record_consumption("agent", 75.0)
        events2 = tracker.record_consumption("agent", 5.0)
        assert len([e for e in events1 if e.event_type == "warning"]) == 1
        assert len([e for e in events2 if e.event_type == "warning"]) == 0

    def test_snapshot_unknown_agent(self) -> None:
        tracker = BudgetTracker()
        assert tracker.get_snapshot("nobody") is None
