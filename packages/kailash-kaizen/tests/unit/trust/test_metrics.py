"""
Unit Tests for TrustMetricsCollector (Tier 1)

Tests metrics collection for postures, transitions,
circuit breaker events, and constraint evaluations.
Part of CARE-030 implementation.

Coverage:
- record_posture
- record_transition
- record_circuit_breaker_open
- record_emergency_downgrade
- record_constraint_evaluation
- get_posture_metrics with distribution
- get_constraint_metrics
- average_posture_level calculation
- reset clears all
- evaluation_time rolling window (last 1000)
"""

import pytest
from kailash.trust.metrics import (
    POSTURE_LEVEL_MAP,
    ConstraintMetrics,
    PostureMetrics,
    TrustMetricsCollector,
)
from kailash.trust.posture.postures import TrustPosture


@pytest.fixture
def collector() -> TrustMetricsCollector:
    """Create a fresh metrics collector."""
    return TrustMetricsCollector()


class TestRecordPosture:
    """Test record_posture method."""

    def test_record_posture(self, collector: TrustMetricsCollector):
        """Test recording posture for an agent."""
        collector.record_posture("agent-001", TrustPosture.AUTONOMOUS)

        metrics = collector.get_posture_metrics()
        assert metrics.posture_distribution["autonomous"] == 1
        assert metrics.posture_distribution["pseudo"] == 0

    def test_record_posture_multiple_agents(self, collector: TrustMetricsCollector):
        """Test recording postures for multiple agents."""
        collector.record_posture("agent-001", TrustPosture.AUTONOMOUS)
        collector.record_posture("agent-002", TrustPosture.SUPERVISED)
        collector.record_posture("agent-003", TrustPosture.SUPERVISED)

        metrics = collector.get_posture_metrics()
        assert metrics.posture_distribution["autonomous"] == 1
        assert metrics.posture_distribution["supervised"] == 2

    def test_record_posture_update(self, collector: TrustMetricsCollector):
        """Test updating posture for same agent."""
        collector.record_posture("agent-001", TrustPosture.PSEUDO)
        collector.record_posture("agent-001", TrustPosture.SUPERVISED)

        metrics = collector.get_posture_metrics()
        # Should only count latest posture
        assert metrics.posture_distribution["pseudo"] == 0
        assert metrics.posture_distribution["supervised"] == 1


class TestRecordTransition:
    """Test record_transition method."""

    def test_record_transition(self, collector: TrustMetricsCollector):
        """Test recording a transition."""
        collector.record_transition("upgrade")

        metrics = collector.get_posture_metrics()
        assert metrics.transitions_by_type["upgrade"] == 1

    def test_record_transition_multiple(self, collector: TrustMetricsCollector):
        """Test recording multiple transitions of same type."""
        collector.record_transition("upgrade")
        collector.record_transition("upgrade")
        collector.record_transition("downgrade")

        metrics = collector.get_posture_metrics()
        assert metrics.transitions_by_type["upgrade"] == 2
        assert metrics.transitions_by_type["downgrade"] == 1

    def test_record_transition_different_types(self, collector: TrustMetricsCollector):
        """Test recording different transition types."""
        collector.record_transition("upgrade")
        collector.record_transition("downgrade")
        collector.record_transition("maintain")
        collector.record_transition("emergency_downgrade")

        metrics = collector.get_posture_metrics()
        assert metrics.transitions_by_type["upgrade"] == 1
        assert metrics.transitions_by_type["downgrade"] == 1
        assert metrics.transitions_by_type["maintain"] == 1
        assert metrics.transitions_by_type["emergency_downgrade"] == 1


class TestRecordCircuitBreakerOpen:
    """Test record_circuit_breaker_open method."""

    def test_record_circuit_breaker_open(self, collector: TrustMetricsCollector):
        """Test recording circuit breaker open event."""
        collector.record_circuit_breaker_open()

        metrics = collector.get_posture_metrics()
        assert metrics.circuit_breaker_opens == 1

    def test_record_circuit_breaker_open_multiple(
        self, collector: TrustMetricsCollector
    ):
        """Test recording multiple circuit breaker open events."""
        collector.record_circuit_breaker_open()
        collector.record_circuit_breaker_open()
        collector.record_circuit_breaker_open()

        metrics = collector.get_posture_metrics()
        assert metrics.circuit_breaker_opens == 3


class TestRecordEmergencyDowngrade:
    """Test record_emergency_downgrade method."""

    def test_record_emergency_downgrade(self, collector: TrustMetricsCollector):
        """Test recording emergency downgrade event."""
        collector.record_emergency_downgrade()

        metrics = collector.get_posture_metrics()
        assert metrics.emergency_downgrades == 1

    def test_record_emergency_downgrade_multiple(
        self, collector: TrustMetricsCollector
    ):
        """Test recording multiple emergency downgrades."""
        collector.record_emergency_downgrade()
        collector.record_emergency_downgrade()

        metrics = collector.get_posture_metrics()
        assert metrics.emergency_downgrades == 2


class TestRecordConstraintEvaluation:
    """Test record_constraint_evaluation method."""

    def test_record_constraint_evaluation_passed(
        self, collector: TrustMetricsCollector
    ):
        """Test recording passed constraint evaluation."""
        collector.record_constraint_evaluation(
            passed=True,
            failed_dimensions=[],
            gaming_flags=[],
            duration_ms=5.0,
        )

        metrics = collector.get_constraint_metrics()
        assert metrics.evaluations_total == 1
        assert metrics.evaluations_passed == 1
        assert metrics.evaluations_failed == 0

    def test_record_constraint_evaluation_failed(
        self, collector: TrustMetricsCollector
    ):
        """Test recording failed constraint evaluation."""
        collector.record_constraint_evaluation(
            passed=False,
            failed_dimensions=["rate_limit", "budget"],
            gaming_flags=["rapid_retry"],
            duration_ms=10.0,
        )

        metrics = collector.get_constraint_metrics()
        assert metrics.evaluations_total == 1
        assert metrics.evaluations_passed == 0
        assert metrics.evaluations_failed == 1
        assert metrics.dimension_failures["rate_limit"] == 1
        assert metrics.dimension_failures["budget"] == 1
        assert metrics.anti_gaming_flags["rapid_retry"] == 1

    def test_record_constraint_evaluation_accumulates(
        self, collector: TrustMetricsCollector
    ):
        """Test that dimension failures accumulate correctly."""
        collector.record_constraint_evaluation(
            passed=False,
            failed_dimensions=["rate_limit"],
            gaming_flags=[],
            duration_ms=5.0,
        )
        collector.record_constraint_evaluation(
            passed=False,
            failed_dimensions=["rate_limit", "timeout"],
            gaming_flags=[],
            duration_ms=5.0,
        )

        metrics = collector.get_constraint_metrics()
        assert metrics.evaluations_failed == 2
        assert metrics.dimension_failures["rate_limit"] == 2
        assert metrics.dimension_failures["timeout"] == 1


class TestGetPostureMetricsWithDistribution:
    """Test get_posture_metrics with full distribution."""

    def test_get_posture_metrics_with_distribution(
        self, collector: TrustMetricsCollector
    ):
        """Test getting posture metrics includes all posture types."""
        collector.record_posture("agent-001", TrustPosture.AUTONOMOUS)
        collector.record_posture("agent-002", TrustPosture.SUPERVISED)
        collector.record_posture("agent-003", TrustPosture.SUPERVISED)
        collector.record_posture("agent-004", TrustPosture.PSEUDO)
        collector.record_posture("agent-005", TrustPosture.PSEUDO)

        metrics = collector.get_posture_metrics()

        # All posture types should be in distribution
        assert len(metrics.posture_distribution) == 5
        assert metrics.posture_distribution["autonomous"] == 1
        assert metrics.posture_distribution["supervised"] == 1
        assert metrics.posture_distribution["supervised"] == 1
        assert metrics.posture_distribution["pseudo"] == 1
        assert metrics.posture_distribution["pseudo"] == 1

    def test_get_posture_metrics_empty_distribution(
        self, collector: TrustMetricsCollector
    ):
        """Test getting posture metrics when no agents recorded."""
        metrics = collector.get_posture_metrics()

        # All posture types should exist with 0 count
        assert len(metrics.posture_distribution) == 5
        for posture_value in [
            "autonomous",
            "supervised",
            "supervised",
            "pseudo",
            "blocked",
        ]:
            assert metrics.posture_distribution[posture_value] == 0


class TestGetConstraintMetrics:
    """Test get_constraint_metrics method."""

    def test_get_constraint_metrics(self, collector: TrustMetricsCollector):
        """Test getting constraint metrics."""
        collector.record_constraint_evaluation(passed=True, duration_ms=5.0)
        collector.record_constraint_evaluation(
            passed=False,
            failed_dimensions=["rate_limit"],
            gaming_flags=["rapid_retry"],
            duration_ms=15.0,
        )

        metrics = collector.get_constraint_metrics()

        assert metrics.evaluations_total == 2
        assert metrics.evaluations_passed == 1
        assert metrics.evaluations_failed == 1
        assert metrics.dimension_failures == {"rate_limit": 1}
        assert metrics.anti_gaming_flags == {"rapid_retry": 1}
        assert metrics.average_evaluation_time_ms == 10.0  # (5 + 15) / 2

    def test_get_constraint_metrics_empty(self, collector: TrustMetricsCollector):
        """Test getting constraint metrics when empty."""
        metrics = collector.get_constraint_metrics()

        assert metrics.evaluations_total == 0
        assert metrics.evaluations_passed == 0
        assert metrics.evaluations_failed == 0
        assert metrics.dimension_failures == {}
        assert metrics.anti_gaming_flags == {}
        assert metrics.average_evaluation_time_ms == 0.0


class TestAveragePostureLevelCalculation:
    """Test average_posture_level calculation."""

    def test_average_posture_level_calculation(self, collector: TrustMetricsCollector):
        """Test average posture level with mixed agents."""
        # FULL_AUTONOMY (5) + BLOCKED (1) = 6 / 2 = 3.0
        collector.record_posture("agent-001", TrustPosture.AUTONOMOUS)
        collector.record_posture("agent-002", TrustPosture.PSEUDO)

        metrics = collector.get_posture_metrics()
        assert metrics.average_posture_level == 3.0

    def test_average_posture_level_all_same(self, collector: TrustMetricsCollector):
        """Test average when all agents have same posture."""
        collector.record_posture("agent-001", TrustPosture.SUPERVISED)
        collector.record_posture("agent-002", TrustPosture.SUPERVISED)
        collector.record_posture("agent-003", TrustPosture.SUPERVISED)

        metrics = collector.get_posture_metrics()
        # SUPERVISED = 3
        assert metrics.average_posture_level == 3.0

    def test_average_posture_level_empty(self, collector: TrustMetricsCollector):
        """Test average when no agents recorded."""
        metrics = collector.get_posture_metrics()
        assert metrics.average_posture_level == 0.0

    def test_average_posture_level_all_postures(self, collector: TrustMetricsCollector):
        """Test average with one agent at each posture."""
        # 5 + 4 + 3 + 2 + 1 = 15 / 5 = 3.0
        collector.record_posture("a1", TrustPosture.AUTONOMOUS)
        collector.record_posture("a2", TrustPosture.SUPERVISED)
        collector.record_posture("a3", TrustPosture.SUPERVISED)
        collector.record_posture("a4", TrustPosture.PSEUDO)
        collector.record_posture("a5", TrustPosture.PSEUDO)

        metrics = collector.get_posture_metrics()
        assert metrics.average_posture_level == 3.0

    def test_posture_level_map_values(self):
        """Test that posture level map has correct values."""
        assert POSTURE_LEVEL_MAP[TrustPosture.AUTONOMOUS] == 5
        assert POSTURE_LEVEL_MAP[TrustPosture.SUPERVISED] == 4
        assert POSTURE_LEVEL_MAP[TrustPosture.SUPERVISED] == 3
        assert POSTURE_LEVEL_MAP[TrustPosture.PSEUDO] == 2
        assert POSTURE_LEVEL_MAP[TrustPosture.PSEUDO] == 1


class TestResetClearsAll:
    """Test reset method clears all metrics."""

    def test_reset_clears_all(self, collector: TrustMetricsCollector):
        """Test that reset clears all collected metrics."""
        # Add some data
        collector.record_posture("agent-001", TrustPosture.AUTONOMOUS)
        collector.record_transition("upgrade")
        collector.record_circuit_breaker_open()
        collector.record_emergency_downgrade()
        collector.record_constraint_evaluation(
            passed=False,
            failed_dimensions=["rate_limit"],
            gaming_flags=["rapid_retry"],
            duration_ms=10.0,
        )

        # Verify data was recorded
        posture_metrics = collector.get_posture_metrics()
        constraint_metrics = collector.get_constraint_metrics()
        assert posture_metrics.posture_distribution["autonomous"] == 1
        assert constraint_metrics.evaluations_total == 1

        # Reset
        collector.reset()

        # Verify all cleared
        posture_metrics = collector.get_posture_metrics()
        constraint_metrics = collector.get_constraint_metrics()

        assert posture_metrics.posture_distribution["autonomous"] == 0
        assert posture_metrics.transitions_by_type == {}
        assert posture_metrics.circuit_breaker_opens == 0
        assert posture_metrics.emergency_downgrades == 0
        assert posture_metrics.average_posture_level == 0.0

        assert constraint_metrics.evaluations_total == 0
        assert constraint_metrics.evaluations_passed == 0
        assert constraint_metrics.evaluations_failed == 0
        assert constraint_metrics.dimension_failures == {}
        assert constraint_metrics.anti_gaming_flags == {}
        assert constraint_metrics.average_evaluation_time_ms == 0.0


class TestEvaluationTimeRollingWindow:
    """Test evaluation time rolling window behavior."""

    def test_evaluation_time_rolling_window(self):
        """Test that evaluation times keep only last 1000."""
        collector = TrustMetricsCollector()

        # Add 1500 evaluations
        for i in range(1500):
            collector.record_constraint_evaluation(
                passed=True,
                duration_ms=float(i),
            )

        # Should keep only last 1000 (indices 500-1499)
        metrics = collector.get_constraint_metrics()

        # Average of 500-1499 = (500 + 1499) / 2 = 999.5
        expected_avg = sum(range(500, 1500)) / 1000
        assert abs(metrics.average_evaluation_time_ms - expected_avg) < 0.001

    def test_evaluation_time_under_limit(self):
        """Test average when under the rolling window limit."""
        collector = TrustMetricsCollector()

        collector.record_constraint_evaluation(passed=True, duration_ms=10.0)
        collector.record_constraint_evaluation(passed=True, duration_ms=20.0)
        collector.record_constraint_evaluation(passed=True, duration_ms=30.0)

        metrics = collector.get_constraint_metrics()
        assert metrics.average_evaluation_time_ms == 20.0  # (10 + 20 + 30) / 3


class TestMetricsDataclasses:
    """Test metrics dataclass functionality."""

    def test_posture_metrics_to_dict(self, collector: TrustMetricsCollector):
        """Test PostureMetrics.to_dict serialization."""
        collector.record_posture("agent-001", TrustPosture.AUTONOMOUS)
        collector.record_transition("upgrade")
        collector.record_circuit_breaker_open()

        metrics = collector.get_posture_metrics()
        data = metrics.to_dict()

        assert "posture_distribution" in data
        assert "transitions_by_type" in data
        assert "circuit_breaker_opens" in data
        assert "emergency_downgrades" in data
        assert "average_posture_level" in data
        assert "timestamp" in data

        # Check types
        assert isinstance(data["posture_distribution"], dict)
        assert isinstance(data["timestamp"], str)

    def test_constraint_metrics_to_dict(self, collector: TrustMetricsCollector):
        """Test ConstraintMetrics.to_dict serialization."""
        collector.record_constraint_evaluation(
            passed=False,
            failed_dimensions=["rate_limit"],
            gaming_flags=["rapid_retry"],
            duration_ms=10.0,
        )

        metrics = collector.get_constraint_metrics()
        data = metrics.to_dict()

        assert "evaluations_total" in data
        assert "evaluations_passed" in data
        assert "evaluations_failed" in data
        assert "dimension_failures" in data
        assert "anti_gaming_flags" in data
        assert "average_evaluation_time_ms" in data

    def test_posture_metrics_has_timestamp(self):
        """Test that PostureMetrics includes timestamp."""
        metrics = PostureMetrics()
        assert metrics.timestamp is not None

    def test_constraint_metrics_default_values(self):
        """Test ConstraintMetrics default values."""
        metrics = ConstraintMetrics()
        assert metrics.evaluations_total == 0
        assert metrics.evaluations_passed == 0
        assert metrics.evaluations_failed == 0
        assert metrics.dimension_failures == {}
        assert metrics.anti_gaming_flags == {}
        assert metrics.average_evaluation_time_ms == 0.0
