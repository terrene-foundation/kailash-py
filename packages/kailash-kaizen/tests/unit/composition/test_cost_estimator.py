# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Tier 1 (Unit) tests for composition cost estimator.

Tests estimate_cost() for known costs, missing agents, confidence levels,
and empty compositions.

Self-contained: imports ONLY from kaizen.composition, never from kaizen.core.
"""

from __future__ import annotations

from kaizen.composition.cost_estimator import estimate_cost
from kaizen.composition.models import CostEstimate


class TestKnownCosts:
    """Two agents with known historical costs sum correctly."""

    def test_known_costs(self) -> None:
        composition = [
            {"name": "agent_a"},
            {"name": "agent_b"},
        ]
        historical_data = {
            "agent_a": {"avg_cost_microdollars": 50000, "invocation_count": 200},
            "agent_b": {"avg_cost_microdollars": 30000, "invocation_count": 150},
        }

        result = estimate_cost(composition, historical_data)

        assert result.estimated_total_microdollars == 80000
        assert result.per_agent["agent_a"] == 50000
        assert result.per_agent["agent_b"] == 30000


class TestMissingAgentWarning:
    """Agent not in historical_data produces a warning and 0 cost."""

    def test_missing_agent_warning(self) -> None:
        composition = [
            {"name": "agent_a"},
            {"name": "agent_unknown"},
        ]
        historical_data = {
            "agent_a": {"avg_cost_microdollars": 50000, "invocation_count": 200},
        }

        result = estimate_cost(composition, historical_data)

        assert result.per_agent["agent_unknown"] == 0
        assert result.estimated_total_microdollars == 50000
        assert len(result.warnings) > 0
        assert any("agent_unknown" in w for w in result.warnings)
        assert result.confidence == "low"


class TestHighConfidence:
    """All agents with 100+ invocations produce high confidence."""

    def test_high_confidence(self) -> None:
        composition = [
            {"name": "agent_a"},
            {"name": "agent_b"},
        ]
        historical_data = {
            "agent_a": {"avg_cost_microdollars": 10000, "invocation_count": 100},
            "agent_b": {"avg_cost_microdollars": 20000, "invocation_count": 500},
        }

        result = estimate_cost(composition, historical_data)

        assert result.confidence == "high"


class TestMediumConfidence:
    """All agents with 10-99 invocations produce medium confidence."""

    def test_medium_confidence(self) -> None:
        composition = [
            {"name": "agent_a"},
            {"name": "agent_b"},
        ]
        historical_data = {
            "agent_a": {"avg_cost_microdollars": 10000, "invocation_count": 50},
            "agent_b": {"avg_cost_microdollars": 20000, "invocation_count": 99},
        }

        result = estimate_cost(composition, historical_data)

        assert result.confidence == "medium"


class TestLowConfidence:
    """Some agents with < 10 invocations produce low confidence."""

    def test_low_confidence(self) -> None:
        composition = [
            {"name": "agent_a"},
            {"name": "agent_b"},
        ]
        historical_data = {
            "agent_a": {"avg_cost_microdollars": 10000, "invocation_count": 5},
            "agent_b": {"avg_cost_microdollars": 20000, "invocation_count": 200},
        }

        result = estimate_cost(composition, historical_data)

        assert result.confidence == "low"


class TestEmptyComposition:
    """Empty composition has zero cost."""

    def test_empty_composition(self) -> None:
        result = estimate_cost([], {})

        assert result.estimated_total_microdollars == 0
        assert len(result.per_agent) == 0


class TestCostEstimateSerialization:
    """CostEstimate to_dict/from_dict round-trip."""

    def test_round_trip(self) -> None:
        original = CostEstimate(
            estimated_total_microdollars=80000,
            per_agent={"agent_a": 50000, "agent_b": 30000},
            confidence="high",
            warnings=["test warning"],
        )
        data = original.to_dict()
        restored = CostEstimate.from_dict(data)

        assert (
            restored.estimated_total_microdollars
            == original.estimated_total_microdollars
        )
        assert restored.per_agent == original.per_agent
        assert restored.confidence == original.confidence
        assert restored.warnings == original.warnings
