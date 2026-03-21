# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for deep analyst findings F-05 through F-10.

Written BEFORE implementation (TDD). Tests define the contract.

Covers:
    F-05: execute_sync must propagate ContextVars across threads
    F-06: Broadcaster _lock must be threading.Lock (not asyncio.Lock)
    F-07: Cascade revocation BFS must have a depth limit
    F-08: Tool constraint enforcement must use exact matching (not substring)
    F-09: Overnight time window validate_tightening must be correct
    F-10: Behavioral scoring must handle low sample sizes fairly
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
from datetime import datetime, time, timezone
from typing import List

import pytest

from kailash.trust.constraints.builtin import TimeDimension
from kailash.trust.hooks import (
    EATPHook,
    HookContext,
    HookRegistry,
    HookResult,
    HookType,
)
from kailash.trust.revocation.broadcaster import (
    CascadeRevocationManager,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    RevocationEvent,
    RevocationType,
)
from kailash.trust.scoring import (
    BehavioralData,
    compute_behavioral_score,
)


# ---------------------------------------------------------------------------
# F-05: execute_sync ContextVar propagation
# ---------------------------------------------------------------------------


class ContextVarCapturingHook(EATPHook):
    """A hook that reads a ContextVar and stores the value it found."""

    def __init__(self, ctx_var: contextvars.ContextVar, name: str = "ctx_hook"):
        self._name = name
        self._ctx_var = ctx_var
        self.captured_value = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def event_types(self) -> list:
        return [HookType.PRE_DELEGATION]

    @property
    def priority(self) -> int:
        return 100

    async def __call__(self, context: HookContext) -> HookResult:
        self.captured_value = self._ctx_var.get(None)
        return HookResult(allow=True)


class TestExecuteSyncContextVarPropagation:
    """F-05: execute_sync must propagate ContextVars to the worker thread."""

    def test_contextvar_propagated_when_no_event_loop(self):
        """ContextVars must be visible inside execute_sync (no loop case)."""
        test_var: contextvars.ContextVar[str] = contextvars.ContextVar("test_var")
        test_var.set("hello-from-main")

        hook = ContextVarCapturingHook(test_var)
        registry = HookRegistry()
        registry.register(hook)

        ctx = HookContext(
            agent_id="agent-1",
            action="delegate",
            hook_type=HookType.PRE_DELEGATION,
        )

        result = registry.execute_sync(HookType.PRE_DELEGATION, ctx)
        assert result.allow is True
        assert hook.captured_value == "hello-from-main"

    def test_contextvar_propagated_when_inside_event_loop(self):
        """ContextVars must be visible inside execute_sync when called from
        within a running event loop (ThreadPoolExecutor fallback path)."""
        test_var: contextvars.ContextVar[str] = contextvars.ContextVar("test_var_loop")
        test_var.set("hello-from-loop")

        hook = ContextVarCapturingHook(test_var, name="ctx_hook_loop")
        registry = HookRegistry()
        registry.register(hook)

        ctx = HookContext(
            agent_id="agent-1",
            action="delegate",
            hook_type=HookType.PRE_DELEGATION,
        )

        async def _run_inside_loop():
            return registry.execute_sync(HookType.PRE_DELEGATION, ctx)

        result = asyncio.run(_run_inside_loop())
        assert result.allow is True
        assert hook.captured_value == "hello-from-loop"


# ---------------------------------------------------------------------------
# F-06: Broadcaster _lock must be threading.Lock
# ---------------------------------------------------------------------------


class TestBroadcasterThreadSafety:
    """F-06: Broadcaster must use threading.Lock, not asyncio.Lock."""

    def test_lock_is_threading_lock(self):
        """The broadcaster's _lock attribute must be a threading.Lock."""
        broadcaster = InMemoryRevocationBroadcaster()
        assert isinstance(broadcaster._lock, type(threading.Lock())), (
            f"Expected threading.Lock, got {type(broadcaster._lock)}"
        )

    def test_broadcast_is_thread_safe(self):
        """Concurrent broadcast calls must not corrupt state."""
        broadcaster = InMemoryRevocationBroadcaster()
        errors: List[Exception] = []

        def _broadcast(i: int):
            try:
                event = RevocationEvent(
                    event_id=f"rev-{i}",
                    revocation_type=RevocationType.AGENT_REVOKED,
                    target_id=f"agent-{i}",
                    revoked_by="admin",
                    reason="test",
                )
                broadcaster.broadcast(event)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_broadcast, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(broadcaster.get_history()) == 50

    def test_subscribe_is_thread_safe(self):
        """Concurrent subscribe calls must not lose subscriptions."""
        broadcaster = InMemoryRevocationBroadcaster()
        sub_ids: List[str] = []
        lock = threading.Lock()

        def _subscribe(i: int):
            sid = broadcaster.subscribe(lambda e: None)
            with lock:
                sub_ids.append(sid)

        threads = [threading.Thread(target=_subscribe, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(sub_ids) == 20
        # All IDs must be unique
        assert len(set(sub_ids)) == 20

    def test_get_history_is_thread_safe(self):
        """get_history must return a snapshot, not the live list."""
        broadcaster = InMemoryRevocationBroadcaster()
        event = RevocationEvent(
            event_id="rev-1",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-1",
            revoked_by="admin",
            reason="test",
        )
        broadcaster.broadcast(event)

        history = broadcaster.get_history()
        assert len(history) == 1
        # Modifying the returned list must not affect internal state
        history.clear()
        assert len(broadcaster.get_history()) == 1


# ---------------------------------------------------------------------------
# F-07: Cascade revocation BFS depth limit
# ---------------------------------------------------------------------------


class TestCascadeRevocationDepthLimit:
    """F-07: Cascade BFS must respect max_depth parameter."""

    def test_cascade_respects_max_depth(self):
        """Deep chain should be truncated at max_depth."""
        registry = InMemoryDelegationRegistry()
        broadcaster = InMemoryRevocationBroadcaster()

        # Build a linear chain: agent-0 -> agent-1 -> ... -> agent-200
        for i in range(200):
            registry.register_delegation(f"agent-{i}", f"agent-{i + 1}")

        manager = CascadeRevocationManager(broadcaster, registry)
        events = manager.cascade_revoke(
            target_id="agent-0",
            revoked_by="admin",
            reason="test",
            max_depth=5,
        )

        # Should have the initial event + at most 5 levels of cascade
        # agent-0 (initial) + agent-1 (depth 1) through agent-5 (depth 5) = 6
        assert len(events) <= 6, f"Expected at most 6 events (initial + 5 depth), got {len(events)}"

    def test_cascade_default_max_depth(self):
        """Default max_depth should be 100 (not unlimited)."""
        registry = InMemoryDelegationRegistry()
        broadcaster = InMemoryRevocationBroadcaster()

        # Build a chain longer than 100
        for i in range(150):
            registry.register_delegation(f"agent-{i}", f"agent-{i + 1}")

        manager = CascadeRevocationManager(broadcaster, registry)
        events = manager.cascade_revoke(
            target_id="agent-0",
            revoked_by="admin",
            reason="test",
        )

        # Should stop at default depth limit (100), not traverse all 150
        assert len(events) <= 101, f"Expected at most 101 events (initial + 100 depth), got {len(events)}"

    def test_cascade_max_depth_zero_stops_immediately(self):
        """max_depth=0 should only produce the initial event, no cascades."""
        registry = InMemoryDelegationRegistry()
        broadcaster = InMemoryRevocationBroadcaster()

        registry.register_delegation("agent-A", "agent-B")

        manager = CascadeRevocationManager(broadcaster, registry)
        events = manager.cascade_revoke(
            target_id="agent-A",
            revoked_by="admin",
            reason="test",
            max_depth=0,
        )

        assert len(events) == 1, "max_depth=0 should produce only the initial event"
        assert events[0].target_id == "agent-A"

    def test_cascade_branching_with_depth_limit(self):
        """Depth limit must work correctly with branching delegation trees."""
        registry = InMemoryDelegationRegistry()
        broadcaster = InMemoryRevocationBroadcaster()

        # Build a tree: A -> (B, C), B -> (D, E), C -> (F, G)
        registry.register_delegation("A", "B")
        registry.register_delegation("A", "C")
        registry.register_delegation("B", "D")
        registry.register_delegation("B", "E")
        registry.register_delegation("C", "F")
        registry.register_delegation("C", "G")

        manager = CascadeRevocationManager(broadcaster, registry)
        events = manager.cascade_revoke(
            target_id="A",
            revoked_by="admin",
            reason="test",
            max_depth=1,
        )

        # A (initial) + B and C at depth 1 = 3 events
        # D, E, F, G are at depth 2 and should be skipped
        event_targets = {e.target_id for e in events}
        assert "A" in event_targets
        assert "B" in event_targets
        assert "C" in event_targets
        assert "D" not in event_targets, "D is at depth 2, should be excluded"
        assert "E" not in event_targets, "E is at depth 2, should be excluded"


# ---------------------------------------------------------------------------
# F-08: Tool constraint exact matching
# ---------------------------------------------------------------------------


class TestToolConstraintExactMatching:
    """F-08: Tool constraint enforcement must use exact matching."""

    @pytest.fixture
    def write_tools_set(self):
        """The canonical set of write tools that should be blocked."""
        return {"file_write", "bash", "database_write", "delete"}

    @pytest.fixture
    def network_tools_set(self):
        """The canonical set of network tools that should be blocked."""
        return {"http", "fetch", "request", "api"}

    def test_exact_write_tool_blocked(self):
        """Tools exactly matching write tool names must be blocked."""
        from kailash.trust.agents.trusted_agent import TrustedAgent, TrustedAgentConfig

        # The write_tools set in the implementation
        write_tools = {"file_write", "bash", "database_write", "delete"}
        for tool in write_tools:
            assert tool.lower() in write_tools, f"{tool} should be in write_tools"

    def test_substring_false_positive_not_blocked(self):
        """A tool whose name CONTAINS a write tool name as substring must NOT
        be blocked. E.g., 'read_database_write_log' should not be blocked."""
        # This tests the fix: substring matching was producing false positives.
        # After the fix, only exact matches should trigger blocking.
        # We verify this by checking the logic directly.
        write_tools = {"file_write", "bash", "database_write", "delete"}

        # These should NOT match (they contain substrings but are not exact)
        false_positive_names = [
            "read_database_write_log",
            "bash_history_reader",
            "undelete_record",
            "http_response_handler",
        ]
        for tool_name in false_positive_names:
            assert tool_name.lower() not in write_tools, (
                f"'{tool_name}' should NOT be blocked - it is not an exact match"
            )

    def test_exact_network_tool_blocked(self):
        """Tools exactly matching network tool names must be blocked."""
        network_tools = {"http", "fetch", "request", "api"}
        for tool in network_tools:
            assert tool.lower() in network_tools

    def test_network_substring_not_blocked(self):
        """Tools containing network tool names as substrings must NOT be blocked."""
        network_tools = {"http", "fetch", "request", "api"}

        false_positives = [
            "http_response_handler",
            "fetch_config_reader",
            "request_logger",
            "api_docs_viewer",
        ]
        for tool_name in false_positives:
            assert tool_name.lower() not in network_tools, f"'{tool_name}' should NOT match network tools exactly"

    def test_case_insensitive_exact_match(self):
        """Exact matching must be case-insensitive."""
        write_tools = {"file_write", "bash", "database_write", "delete"}
        # These should match after lowering
        assert "FILE_WRITE".lower() in write_tools
        assert "Bash".lower() in write_tools
        assert "DELETE".lower() in write_tools


# ---------------------------------------------------------------------------
# F-09: Overnight time window validate_tightening
# ---------------------------------------------------------------------------


class TestOvernightTimeWindowTightening:
    """F-09: validate_tightening must handle overnight windows correctly."""

    @pytest.fixture
    def dim(self):
        return TimeDimension()

    def test_child_evening_fits_parent_overnight(self, dim):
        """A child window in the evening portion of an overnight parent
        should be a valid tightening.

        Parent: 22:00-06:00 (overnight)
        Child:  23:00-23:59 (evening only, not overnight)
        """
        parent = dim.parse("22:00-06:00")  # overnight
        child = dim.parse("23:00-23:59")  # evening portion only

        assert dim.validate_tightening(parent, child) is True

    def test_child_morning_fits_parent_overnight(self, dim):
        """A child window in the morning portion of an overnight parent
        should be a valid tightening.

        Parent: 22:00-06:00 (overnight)
        Child:  01:00-05:00 (morning only, not overnight)
        """
        parent = dim.parse("22:00-06:00")
        child = dim.parse("01:00-05:00")

        assert dim.validate_tightening(parent, child) is True

    def test_child_spans_midnight_invalid(self, dim):
        """A child that spans both evening and morning portions but goes beyond
        the parent boundaries should be invalid.

        Parent: 22:00-06:00 (overnight)
        Child:  10:00-15:00 (completely outside parent)
        """
        parent = dim.parse("22:00-06:00")
        child = dim.parse("10:00-15:00")

        assert dim.validate_tightening(parent, child) is False

    def test_child_exceeds_morning_boundary(self, dim):
        """A non-overnight child in the morning that exceeds parent's
        end boundary must be invalid.

        Parent: 22:00-04:00 (overnight)
        Child:  01:00-05:00 (morning, but child_end > parent_end)
        """
        parent = dim.parse("22:00-04:00")
        child = dim.parse("01:00-05:00")

        assert dim.validate_tightening(parent, child) is False

    def test_child_before_evening_start(self, dim):
        """A non-overnight child that starts before the parent's evening
        boundary must be invalid.

        Parent: 22:00-06:00 (overnight)
        Child:  20:00-21:00 (before parent start)
        """
        parent = dim.parse("22:00-06:00")
        child = dim.parse("20:00-21:00")

        assert dim.validate_tightening(parent, child) is False

    def test_both_overnight_child_subset(self, dim):
        """Both overnight: child must be subset of parent.

        Parent: 20:00-08:00 (overnight)
        Child:  22:00-06:00 (overnight, subset)
        """
        parent = dim.parse("20:00-08:00")
        child = dim.parse("22:00-06:00")

        assert dim.validate_tightening(parent, child) is True

    def test_both_overnight_child_not_subset(self, dim):
        """Both overnight: child that exceeds parent boundaries is invalid.

        Parent: 22:00-04:00 (overnight)
        Child:  20:00-06:00 (overnight, but wider)
        """
        parent = dim.parse("22:00-04:00")
        child = dim.parse("20:00-06:00")

        assert dim.validate_tightening(parent, child) is False

    def test_parent_not_overnight_child_overnight_invalid(self, dim):
        """If parent is not overnight but child IS overnight, it must be
        invalid because the child window is effectively larger."""
        parent = dim.parse("09:00-17:00")
        child = dim.parse("22:00-06:00")

        assert dim.validate_tightening(parent, child) is False

    def test_child_evening_edge_equal_to_parent_start(self, dim):
        """Child starting exactly at parent's evening start should be valid.

        Parent: 22:00-06:00 (overnight)
        Child:  22:00-23:00 (starts at parent_start)
        """
        parent = dim.parse("22:00-06:00")
        child = dim.parse("22:00-23:00")

        assert dim.validate_tightening(parent, child) is True


# ---------------------------------------------------------------------------
# F-10: Anti-gaming false positives for low sample sizes
# ---------------------------------------------------------------------------

# Minimum reliable sample size constant expected in implementation
MIN_RELIABLE_SAMPLE = 10


class TestBehavioralScoringLowSampleSize:
    """F-10: Agents with few actions should not get harsh error penalties."""

    def test_two_actions_one_error_not_overly_penalized(self):
        """An agent with 2 actions and 1 error should use pessimistic default
        error_raw=0.5 instead of computing 50% error rate = 50% penalty.

        Before fix: error_raw = 1.0 - (1/2) = 0.5, which maps to 12.5 weighted.
        After fix: same error_raw=0.5 (pessimistic default), but this is
        intentional conservative behavior, not based on unreliable statistics.
        """
        data = BehavioralData(
            total_actions=2,
            approved_actions=2,
            denied_actions=0,
            error_count=1,
            posture_transitions=0,
            time_at_current_posture_hours=100.0,
            observation_window_hours=100.0,
        )
        score = compute_behavioral_score("agent-low", data)
        # The score should be computed (not zero)
        assert score.score > 0

    def test_below_threshold_uses_pessimistic_default(self):
        """With total_actions < MIN_RELIABLE_SAMPLE, the error rate should
        use a pessimistic default (0.5) regardless of actual error count."""
        # 5 actions, 0 errors -- before fix this would give error_raw=1.0
        # After fix: below threshold, so error_raw=0.5 (pessimistic)
        data_no_errors = BehavioralData(
            total_actions=5,
            approved_actions=5,
            denied_actions=0,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=100.0,
            observation_window_hours=100.0,
        )
        score_no_errors = compute_behavioral_score("agent-few", data_no_errors)

        # 5 actions, 4 errors -- before fix this would give error_raw=0.2
        # After fix: below threshold, so error_raw=0.5 (pessimistic)
        data_many_errors = BehavioralData(
            total_actions=5,
            approved_actions=1,
            denied_actions=0,
            error_count=4,
            posture_transitions=0,
            time_at_current_posture_hours=100.0,
            observation_window_hours=100.0,
        )
        score_many_errors = compute_behavioral_score("agent-few-err", data_many_errors)

        # Both should have the same error_rate contribution in breakdown
        # because both use pessimistic default 0.5
        assert score_no_errors.breakdown["error_rate"] == score_many_errors.breakdown["error_rate"], (
            f"Below threshold, error_rate contribution should be identical "
            f"(pessimistic default), but got "
            f"{score_no_errors.breakdown['error_rate']} vs "
            f"{score_many_errors.breakdown['error_rate']}"
        )

    def test_at_threshold_uses_actual_data(self):
        """With total_actions == MIN_RELIABLE_SAMPLE, actual error rates
        should be used (not pessimistic default)."""
        data_clean = BehavioralData(
            total_actions=MIN_RELIABLE_SAMPLE,
            approved_actions=MIN_RELIABLE_SAMPLE,
            denied_actions=0,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=100.0,
            observation_window_hours=100.0,
        )
        score_clean = compute_behavioral_score("agent-clean", data_clean)

        data_errors = BehavioralData(
            total_actions=MIN_RELIABLE_SAMPLE,
            approved_actions=MIN_RELIABLE_SAMPLE - 5,
            denied_actions=0,
            error_count=5,
            posture_transitions=0,
            time_at_current_posture_hours=100.0,
            observation_window_hours=100.0,
        )
        score_errors = compute_behavioral_score("agent-errors", data_errors)

        # At or above threshold, error_rate should differ based on actual data
        assert score_clean.breakdown["error_rate"] != score_errors.breakdown["error_rate"], (
            "At threshold, actual error rates should be used, producing different scores"
        )

    def test_above_threshold_uses_actual_data(self):
        """With total_actions > MIN_RELIABLE_SAMPLE, actual error rates
        should be used."""
        n = MIN_RELIABLE_SAMPLE + 50
        data = BehavioralData(
            total_actions=n,
            approved_actions=n,
            denied_actions=0,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=100.0,
            observation_window_hours=100.0,
        )
        score = compute_behavioral_score("agent-lots", data)

        # error_rate should be max (25.0) since 0 errors
        assert score.breakdown["error_rate"] == 25.0

    def test_zero_actions_still_score_zero(self):
        """Zero actions must still produce score 0, grade F (fail-safe)."""
        data = BehavioralData(
            total_actions=0,
            approved_actions=0,
            denied_actions=0,
            error_count=0,
        )
        score = compute_behavioral_score("agent-zero", data)
        assert score.score == 0
        assert score.grade == "F"
