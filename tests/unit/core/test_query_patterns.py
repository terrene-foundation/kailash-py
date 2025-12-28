"""Unit tests for query pattern learning and prediction."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from kailash.core.ml.query_patterns import (
    PatternLearningOptimizer,
    PredictedQuery,
    QueryExecution,
    QueryPattern,
    QueryPatternTracker,
)


class TestQueryPatternTracker:
    """Test query pattern tracking and analysis."""

    @pytest.fixture
    def tracker(self):
        return QueryPatternTracker(retention_hours=24, min_pattern_frequency=3)

    def test_record_execution(self, tracker):
        """Test recording query executions."""
        # Record executions
        tracker.record_execution(
            fingerprint="select_users",
            execution_time_ms=50.0,
            connection_id="conn1",
            parameters={"status": "active"},
            success=True,
            result_size=100,
        )

        assert len(tracker.executions) == 1
        assert "select_users" in tracker.execution_by_fingerprint
        assert len(tracker.execution_by_fingerprint["select_users"]) == 1

        # Record more executions
        for i in range(5):
            tracker.record_execution(
                fingerprint="select_users",
                execution_time_ms=45.0 + i,
                connection_id="conn1",
                parameters={"status": "active"},
                success=True,
                result_size=100 + i,
            )

        assert len(tracker.executions) == 6
        assert len(tracker.execution_by_fingerprint["select_users"]) == 6

    def test_sequence_pattern_detection(self, tracker):
        """Test detection of query sequences."""
        # Simulate pattern: check_user -> fetch_orders -> update_stats
        for _ in range(5):
            tracker.record_execution("check_user", 10.0, "conn1", {}, True, 1)
            tracker.record_execution("fetch_orders", 50.0, "conn1", {}, True, 20)
            tracker.record_execution("update_stats", 30.0, "conn1", {}, True, 0)

        # Check sequence patterns
        assert tracker.sequence_patterns["check_user"]["fetch_orders"] == 5
        assert tracker.sequence_patterns["fetch_orders"]["update_stats"] == 5

        # Predict next queries
        predictions = tracker.predict_next_queries("check_user", time_window_minutes=5)

        assert len(predictions) > 0
        predicted_fingerprints = [p.fingerprint for p in predictions]
        assert "fetch_orders" in predicted_fingerprints

    def test_pattern_analysis(self, tracker):
        """Test pattern analysis for a query."""
        # Record enough executions to create a pattern
        for i in range(10):
            tracker.record_execution(
                fingerprint="analytics_query",
                execution_time_ms=100.0 + (i * 5),
                connection_id="conn1",
                parameters={"date": f"2024-01-{i+1}"},
                success=True,
                result_size=1000 + (i * 100),
            )

        pattern = tracker.get_pattern("analytics_query")

        assert pattern is not None
        assert pattern.fingerprint == "analytics_query"
        assert pattern.frequency > 0
        assert pattern.avg_execution_time > 100
        assert pattern.typical_result_size > 1000

    def test_temporal_pattern_detection(self, tracker):
        """Test detection of temporal patterns."""
        # Simulate hourly pattern - all executions at same hour
        base_time = datetime.now().replace(minute=0, second=0, microsecond=0)

        # Override time for testing
        for day in range(7):
            execution = QueryExecution(
                fingerprint="hourly_report",
                timestamp=base_time - timedelta(days=day),
                execution_time_ms=200.0,
                connection_id="conn1",
                parameters={},
                success=True,
                result_size=500,
            )
            tracker.executions.append(execution)
            tracker.execution_by_fingerprint["hourly_report"].append(execution)

        pattern = tracker._analyze_single_pattern("hourly_report")

        # Should detect some temporal pattern
        assert pattern is not None
        # The specific pattern depends on test execution time

    def test_workload_forecast(self, tracker):
        """Test workload forecasting."""
        # Simulate historical workload
        for i in range(100):
            tracker.record_execution(
                fingerprint=f"query_{i % 5}",
                execution_time_ms=50.0,
                connection_id="conn1",
                parameters={},
                success=True,
                result_size=100,
            )

        forecast = tracker.get_workload_forecast(horizon_minutes=30)

        assert "horizon_minutes" in forecast
        assert "expected_total_queries" in forecast
        assert "recommended_pool_size" in forecast
        assert forecast["recommended_pool_size"] >= 5  # Minimum size

    def test_data_cleanup(self, tracker):
        """Test old data cleanup."""
        # Add old execution
        old_execution = QueryExecution(
            fingerprint="old_query",
            timestamp=datetime.now() - timedelta(hours=25),  # Older than retention
            execution_time_ms=100.0,
            connection_id="conn1",
            parameters={},
            success=True,
            result_size=50,
        )
        tracker.executions.append(old_execution)
        tracker.execution_by_fingerprint["old_query"].append(old_execution)

        # Add recent execution
        tracker.record_execution("recent_query", 50.0, "conn1", {}, True, 100)

        # Cleanup should remove old execution
        assert len(tracker.executions) == 1
        assert tracker.executions[0].fingerprint == "recent_query"
        assert "old_query" not in tracker.execution_by_fingerprint

    def test_parameter_analysis(self, tracker):
        """Test common parameter value detection."""
        # Record executions with various parameters
        params_list = [
            {"user_id": 1, "status": "active"},
            {"user_id": 2, "status": "active"},
            {"user_id": 3, "status": "inactive"},
            {"user_id": 1, "status": "active"},
            {"user_id": 2, "status": "active"},
        ]

        for params in params_list:
            tracker.record_execution(
                fingerprint="user_query",
                execution_time_ms=30.0,
                connection_id="conn1",
                parameters=params,
                success=True,
                result_size=10,
            )

        pattern = tracker.get_pattern("user_query")

        assert pattern is not None
        assert "status" in pattern.common_parameters
        assert "active" in pattern.common_parameters["status"]

    def test_confidence_calculation(self, tracker):
        """Test prediction confidence calculation."""
        # Strong pattern - high confidence
        for _ in range(20):
            tracker.record_execution("query_a", 10.0, "conn1", {}, True, 5)
            tracker.record_execution("query_b", 20.0, "conn1", {}, True, 10)

        predictions = tracker.predict_next_queries("query_a", time_window_minutes=5)

        # Should have high confidence for query_b after query_a
        query_b_predictions = [p for p in predictions if p.fingerprint == "query_b"]
        assert len(query_b_predictions) > 0
        assert query_b_predictions[0].confidence > 0.8

    def test_average_delay_calculation(self, tracker):
        """Test calculation of average delay between queries."""
        # Record sequences with consistent timing
        for i in range(5):
            # Use manual timestamp control for consistent delays
            timestamp1 = datetime.now() - timedelta(seconds=60 - i * 10)
            execution1 = QueryExecution(
                fingerprint="step1",
                timestamp=timestamp1,
                execution_time_ms=10.0,
                connection_id="conn1",
                parameters={},
                success=True,
                result_size=1,
            )

            timestamp2 = timestamp1 + timedelta(seconds=5)  # 5 second delay
            execution2 = QueryExecution(
                fingerprint="step2",
                timestamp=timestamp2,
                execution_time_ms=20.0,
                connection_id="conn1",
                parameters={},
                success=True,
                result_size=1,
            )

            tracker.executions.extend([execution1, execution2])

        delay = tracker._calculate_average_delay("step1", "step2")

        # Should be close to 5 seconds
        assert 4 <= delay.total_seconds() <= 6


class TestPatternLearningOptimizer:
    """Test pattern-based optimization."""

    @pytest.fixture
    def optimizer(self):
        tracker = QueryPatternTracker()
        return PatternLearningOptimizer(tracker)

    def test_optimize_routing_high_frequency(self, optimizer):
        """Test optimization for high-frequency queries."""
        # Create high-frequency pattern
        pattern = QueryPattern(
            fingerprint="frequent_query",
            frequency=50.0,  # 50 queries per minute
            avg_execution_time=100.0,
            temporal_pattern=None,
            common_parameters={},
            typical_result_size=1000,
            follows_queries=[],
            followed_by_queries=[],
        )

        # Mock pattern tracker
        optimizer.pattern_tracker.pattern_cache["frequent_query"] = pattern

        # Optimize routing decision
        current_decision = {"connection_id": "conn1"}
        optimized = optimizer.optimize_routing("frequent_query", current_decision)

        assert optimized["connection_affinity"] is True
        assert optimized["cache_priority"] == "high"

    def test_optimize_routing_slow_query(self, optimizer):
        """Test optimization for slow queries."""
        # Create slow query pattern
        pattern = QueryPattern(
            fingerprint="slow_query",
            frequency=5.0,
            avg_execution_time=2000.0,  # 2 seconds
            temporal_pattern=None,
            common_parameters={},
            typical_result_size=5000,
            follows_queries=[],
            followed_by_queries=[],
        )

        optimizer.pattern_tracker.pattern_cache["slow_query"] = pattern

        current_decision = {"connection_id": "conn1"}
        optimized = optimizer.optimize_routing("slow_query", current_decision)

        assert optimized["dedicated_connection"] is True
        assert optimized["timeout_extension"] == 2.0

    def test_optimize_routing_large_results(self, optimizer):
        """Test optimization for queries with large results."""
        # Create pattern with large results
        pattern = QueryPattern(
            fingerprint="large_result_query",
            frequency=10.0,
            avg_execution_time=500.0,
            temporal_pattern=None,
            common_parameters={},
            typical_result_size=50000,  # Large result set
            follows_queries=[],
            followed_by_queries=[],
        )

        optimizer.pattern_tracker.pattern_cache["large_result_query"] = pattern

        current_decision = {"connection_id": "conn1"}
        optimized = optimizer.optimize_routing("large_result_query", current_decision)

        assert optimized["streaming_enabled"] is True

    def test_suggest_pre_warming(self, optimizer):
        """Test pre-warming suggestions."""
        # Create patterns with sequences
        for i in range(3):
            pattern = QueryPattern(
                fingerprint=f"query_{i}",
                frequency=20.0,
                avg_execution_time=50.0,
                temporal_pattern="hourly" if i == 0 else None,
                common_parameters={},
                typical_result_size=100,
                follows_queries=[],
                followed_by_queries=[f"query_{i+1}"] if i < 2 else [],
            )
            optimizer.pattern_tracker.pattern_cache[f"query_{i}"] = pattern

        # Mock predictions
        optimizer.pattern_tracker.predict_next_queries = MagicMock(
            return_value=[
                PredictedQuery(
                    fingerprint="query_1",
                    probability=0.8,
                    expected_time=datetime.now() + timedelta(minutes=2),
                    confidence=0.9,
                    reason="Follows query_0",
                ),
                PredictedQuery(
                    fingerprint="query_2",
                    probability=0.6,
                    expected_time=datetime.now() + timedelta(minutes=3),
                    confidence=0.7,
                    reason="Follows query_1",
                ),
            ]
        )

        suggestions = optimizer.suggest_pre_warming(datetime.now())

        assert len(suggestions) > 0
        assert "query_1" in suggestions  # High probability and confidence
