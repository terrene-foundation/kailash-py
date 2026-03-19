# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for bounded metrics collections (G2).

G2: TrustMetricsCollector._agent_postures, _transitions, _dimension_failures,
    and _anti_gaming_flags dicts grow per-agent and must be bounded at
    maxlen=10000 with oldest-10% trimming.

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

import pytest

from eatp.metrics import TrustMetricsCollector
from eatp.postures import TrustPosture


# ---------------------------------------------------------------------------
# G2: TrustMetricsCollector bounded collections
# ---------------------------------------------------------------------------


class TestMetricsCollectorAgentPosturesBounded:
    """G2: _agent_postures must be bounded."""

    def test_default_max_agents_is_10000(self):
        """Default max tracked agents should be 10,000."""
        collector = TrustMetricsCollector()
        assert collector._max_agents == 10_000

    def test_custom_max_agents(self):
        """max_agents should be configurable."""
        collector = TrustMetricsCollector(max_agents=500)
        assert collector._max_agents == 500

    def test_agent_postures_trimmed_at_capacity(self):
        """When agent postures exceed max, oldest 10% are trimmed."""
        maxlen = 20
        collector = TrustMetricsCollector(max_agents=maxlen)

        for i in range(maxlen + 5):
            collector.record_posture(f"agent-{i:04d}", TrustPosture.DELEGATED)

        assert len(collector._agent_postures) <= maxlen

    def test_oldest_agents_trimmed(self):
        """Trim should remove oldest recorded agents."""
        maxlen = 20
        collector = TrustMetricsCollector(max_agents=maxlen)

        for i in range(maxlen + 5):
            collector.record_posture(f"agent-{i:04d}", TrustPosture.DELEGATED)

        remaining = set(collector._agent_postures.keys())
        # Oldest agents should be gone
        assert "agent-0000" not in remaining
        assert "agent-0001" not in remaining
        # Newest should remain
        assert f"agent-{maxlen + 4:04d}" in remaining


class TestMetricsCollectorDimensionFailuresBounded:
    """G2: _dimension_failures must be bounded."""

    def test_dimension_failures_trimmed_at_capacity(self):
        """When dimension_failures entries exceed max, oldest 10% are trimmed."""
        maxlen = 20
        collector = TrustMetricsCollector(max_agents=maxlen)

        for i in range(maxlen + 5):
            collector.record_constraint_evaluation(
                passed=False,
                failed_dimensions=[f"dim-{i:04d}"],
            )

        assert len(collector._dimension_failures) <= maxlen


class TestMetricsCollectorAntiGamingFlagsBounded:
    """G2: _anti_gaming_flags must be bounded."""

    def test_anti_gaming_flags_trimmed_at_capacity(self):
        """When anti_gaming_flags entries exceed max, oldest 10% are trimmed."""
        maxlen = 20
        collector = TrustMetricsCollector(max_agents=maxlen)

        for i in range(maxlen + 5):
            collector.record_constraint_evaluation(
                passed=True,
                gaming_flags=[f"flag-{i:04d}"],
            )

        assert len(collector._anti_gaming_flags) <= maxlen


class TestMetricsCollectorTransitionsBounded:
    """G2: _transitions must be bounded."""

    def test_transitions_trimmed_at_capacity(self):
        """When transition type entries exceed max, oldest 10% are trimmed."""
        maxlen = 20
        collector = TrustMetricsCollector(max_agents=maxlen)

        for i in range(maxlen + 5):
            collector.record_transition(f"transition-type-{i:04d}")

        assert len(collector._transitions) <= maxlen


class TestMetricsCollectorBackwardCompat:
    """G2: Bounded collections must not change default behavior."""

    def test_no_args_works(self):
        """TrustMetricsCollector() with no args still works."""
        collector = TrustMetricsCollector()
        collector.record_posture("agent-001", TrustPosture.DELEGATED)
        collector.record_transition("upgrade")
        collector.record_constraint_evaluation(
            passed=True,
            failed_dimensions=[],
            gaming_flags=[],
            duration_ms=5.0,
        )
        metrics = collector.get_posture_metrics()
        assert metrics.average_posture_level > 0.0

    def test_metrics_accuracy_after_trimming(self):
        """Counters (evaluations_total etc.) must remain accurate after trimming."""
        maxlen = 20
        collector = TrustMetricsCollector(max_agents=maxlen)

        total_evals = maxlen + 5
        for i in range(total_evals):
            collector.record_constraint_evaluation(
                passed=i % 2 == 0,
                failed_dimensions=[f"dim-{i:04d}"] if i % 2 != 0 else [],
            )

        constraint_metrics = collector.get_constraint_metrics()
        # Total counter must remain accurate (not affected by dict trimming)
        assert constraint_metrics.evaluations_total == total_evals

    def test_reset_clears_all(self):
        """reset() should clear all bounded collections."""
        collector = TrustMetricsCollector(max_agents=100)
        collector.record_posture("agent-001", TrustPosture.DELEGATED)
        collector.record_transition("upgrade")
        collector.record_constraint_evaluation(passed=False, failed_dimensions=["test"], gaming_flags=["flag"])

        collector.reset()

        assert len(collector._agent_postures) == 0
        assert len(collector._transitions) == 0
        assert len(collector._dimension_failures) == 0
        assert len(collector._anti_gaming_flags) == 0
