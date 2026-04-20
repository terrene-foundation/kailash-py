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
