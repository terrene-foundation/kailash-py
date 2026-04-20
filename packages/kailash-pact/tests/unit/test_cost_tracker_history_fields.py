# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""CostTracker history-record field extension (B3, kailash-py#567 prereq).

Verifies that ``CostTracker.record()`` persists the optional ``envelope_id``
and ``agent_id`` fields into each history entry, enabling the forthcoming
``consumption_report(envelope_id=..., agent_id=...)`` rollup primitive
(synthesis proposal §PR#7, GovernanceEngine method extensions).

The fields are additive and backwards-compatible — existing callers that
omit them record ``None`` for both, matching the prior shape.
"""

from __future__ import annotations

import pytest

from pact.costs import CostTracker


class TestHistoryFieldsBackwardsCompatible:
    """Existing callers without the new kwargs still work."""

    def test_record_without_kwargs_stores_none_for_new_fields(self) -> None:
        tracker = CostTracker(budget_usd=100.0)
        tracker.record(1.0, "legacy caller")

        assert len(tracker.history) == 1
        entry = tracker.history[0]
        assert entry["envelope_id"] is None
        assert entry["agent_id"] is None

    def test_record_preserves_prior_fields_unchanged(self) -> None:
        """Prior keys (amount, description, timestamp, cumulative) still present."""
        tracker = CostTracker()
        tracker.record(2.5, "some description")

        entry = tracker.history[0]
        assert entry["amount"] == 2.5
        assert entry["description"] == "some description"
        assert "timestamp" in entry
        assert entry["cumulative"] == 2.5


class TestHistoryFieldsPopulated:
    """New kwargs are stored verbatim on the history record."""

    def test_envelope_id_stored(self) -> None:
        tracker = CostTracker()
        tracker.record(1.0, "call", envelope_id="env-prod-001")

        assert tracker.history[0]["envelope_id"] == "env-prod-001"

    def test_agent_id_stored(self) -> None:
        tracker = CostTracker()
        tracker.record(1.0, "call", agent_id="D1-R1-D2-R2")

        assert tracker.history[0]["agent_id"] == "D1-R1-D2-R2"

    def test_both_fields_stored(self) -> None:
        tracker = CostTracker()
        tracker.record(1.0, "call", envelope_id="env-prod-001", agent_id="D1-R1-D2-R2")

        entry = tracker.history[0]
        assert entry["envelope_id"] == "env-prod-001"
        assert entry["agent_id"] == "D1-R1-D2-R2"

    def test_record_enforces_keyword_only(self) -> None:
        """New kwargs are keyword-only — positional args still mean
        (amount, description) for binary compatibility."""
        tracker = CostTracker()
        with pytest.raises(TypeError):
            tracker.record(1.0, "call", "env-prod-001")  # type: ignore[misc]


class TestConsumptionReportReadiness:
    """Confirm the history shape supports the forthcoming consumption_report
    rollups without further field changes.
    """

    def test_history_supports_per_envelope_filter(self) -> None:
        tracker = CostTracker()
        tracker.record(1.0, "a", envelope_id="env-A", agent_id="D1-R1")
        tracker.record(2.0, "b", envelope_id="env-B", agent_id="D1-R1")
        tracker.record(3.0, "c", envelope_id="env-A", agent_id="D1-R2")

        env_a = [e for e in tracker.history if e["envelope_id"] == "env-A"]
        env_a_total = sum(e["amount"] for e in env_a)

        assert len(env_a) == 2
        assert env_a_total == 4.0

    def test_history_supports_per_agent_filter(self) -> None:
        tracker = CostTracker()
        tracker.record(1.0, "a", envelope_id="env-A", agent_id="D1-R1")
        tracker.record(2.0, "b", envelope_id="env-A", agent_id="D1-R2")
        tracker.record(3.0, "c", envelope_id="env-A", agent_id="D1-R1")

        r1 = [e for e in tracker.history if e["agent_id"] == "D1-R1"]
        r1_total = sum(e["amount"] for e in r1)

        assert len(r1) == 2
        assert r1_total == 4.0

    def test_history_supports_compound_filter(self) -> None:
        tracker = CostTracker()
        tracker.record(1.0, "a", envelope_id="env-A", agent_id="D1-R1")
        tracker.record(2.0, "b", envelope_id="env-B", agent_id="D1-R1")
        tracker.record(3.0, "c", envelope_id="env-A", agent_id="D1-R2")
        tracker.record(4.0, "d", envelope_id="env-A", agent_id="D1-R1")

        matches = [
            e
            for e in tracker.history
            if e["envelope_id"] == "env-A" and e["agent_id"] == "D1-R1"
        ]
        total = sum(e["amount"] for e in matches)

        assert len(matches) == 2
        assert total == 5.0


class TestValidationStillEnforced:
    """NaN/Inf/negative validation unchanged by the field extension."""

    def test_nan_amount_rejected(self) -> None:
        tracker = CostTracker()
        with pytest.raises(ValueError, match="finite"):
            tracker.record(float("nan"), "bad", envelope_id="env-A")

    def test_negative_amount_rejected(self) -> None:
        tracker = CostTracker()
        with pytest.raises(ValueError, match="non-negative"):
            tracker.record(-1.0, "bad", agent_id="D1-R1")


class TestThreadSafetyWithNewFields:
    """The ``_lock`` contract from pact-governance.md §8 holds when the new
    kwargs are in play. Concurrent ``record()`` calls must not drop, dedup,
    or interleave history entries even when every caller passes envelope_id
    and agent_id.
    """

    def test_concurrent_record_preserves_all_entries(self) -> None:
        import threading

        tracker = CostTracker(budget_usd=10_000.0)
        per_thread = 200
        thread_count = 8

        def worker(thread_id: int) -> None:
            for i in range(per_thread):
                tracker.record(
                    0.01,
                    f"t{thread_id}-i{i}",
                    envelope_id=f"env-thread-{thread_id}",
                    agent_id=f"D1-R{thread_id}",
                )

        threads = [
            threading.Thread(target=worker, args=(tid,)) for tid in range(thread_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected_count = per_thread * thread_count
        assert len(tracker.history) == expected_count

        # Every entry must have both fields populated and match its thread.
        for entry in tracker.history:
            assert entry["envelope_id"] is not None
            assert entry["agent_id"] is not None
            assert entry["envelope_id"].startswith("env-thread-")
            assert entry["agent_id"].startswith("D1-R")

        # Cumulative sum must match total spent (no lost or double-counted
        # records).
        final_cumulative = tracker.history[-1]["cumulative"]
        assert abs(final_cumulative - tracker.spent) < 1e-9
        assert abs(tracker.spent - (expected_count * 0.01)) < 1e-6


class TestBoundedDequeWrap:
    """The bounded history deque (maxlen=10_000) wraps correctly with the
    new fields — oldest entries evict, newest retain their envelope_id and
    agent_id, and ``cumulative`` stays monotonically increasing across the
    eviction boundary.
    """

    def test_history_wrap_preserves_new_fields(self) -> None:
        from pact.costs import CostTracker as _CT

        tracker = _CT()
        # Shrink the deque for a cheap test.
        tracker._history.clear()
        from collections import deque

        tracker._history = deque(maxlen=5)  # type: ignore[misc]

        # Record 8 entries — deque keeps only the last 5.
        for i in range(8):
            tracker.record(
                1.0,
                f"entry-{i}",
                envelope_id=f"env-{i}",
                agent_id=f"D1-R{i}",
            )

        assert len(tracker.history) == 5
        retained = tracker.history

        # Oldest three (0, 1, 2) evicted; retained are entries 3-7.
        assert retained[0]["description"] == "entry-3"
        assert retained[0]["envelope_id"] == "env-3"
        assert retained[0]["agent_id"] == "D1-R3"
        assert retained[-1]["description"] == "entry-7"
        assert retained[-1]["envelope_id"] == "env-7"
        assert retained[-1]["agent_id"] == "D1-R7"

        # Cumulative stays monotone across the retained window.
        cumulatives = [e["cumulative"] for e in retained]
        assert cumulatives == sorted(cumulatives)
        # spent reflects ALL 8 recordings even though history only has 5.
        assert tracker.spent == 8.0
        assert retained[-1]["cumulative"] == 8.0
