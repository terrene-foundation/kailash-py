"""Unit tests for AdaptivePoolController."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.core.actors.adaptive_pool_controller import (
    AdaptivePoolController,
    PoolMetrics,
    PoolSizeCalculator,
    ResourceConstraints,
    ResourceMonitor,
    ScalingDecision,
    ScalingDecisionEngine,
)


class TestPoolSizeCalculator:
    """Test pool size calculation logic."""

    @pytest.fixture
    def calculator(self):
        return PoolSizeCalculator(target_utilization=0.75)

    def test_calculate_by_littles_law(self, calculator):
        """Test Little's Law calculation."""
        metrics = PoolMetrics(
            current_size=10,
            active_connections=8,
            idle_connections=2,
            queue_depth=0,
            avg_wait_time_ms=5.0,
            avg_query_time_ms=50.0,  # 50ms per query
            queries_per_second=100.0,  # 100 QPS
            utilization_rate=0.8,
            health_score=90.0,
        )

        # Little's Law: L = λW
        # L = 100 QPS * 0.05s = 5 connections needed
        # With 1.2x buffer = 6 connections
        size = calculator._calculate_by_littles_law(metrics)
        assert size == 6

    def test_calculate_by_utilization(self, calculator):
        """Test utilization-based calculation."""
        # High utilization - should scale up
        metrics_high = PoolMetrics(
            current_size=10,
            active_connections=9,
            idle_connections=1,
            queue_depth=0,
            avg_wait_time_ms=5.0,
            avg_query_time_ms=50.0,
            queries_per_second=100.0,
            utilization_rate=0.9,  # 90% > target 75%
            health_score=90.0,
        )

        size_high = calculator._calculate_by_utilization(metrics_high)
        assert size_high > metrics_high.current_size  # Should scale up

        # Low utilization - should scale down
        metrics_low = PoolMetrics(
            current_size=10,
            active_connections=3,
            idle_connections=7,
            queue_depth=0,
            avg_wait_time_ms=5.0,
            avg_query_time_ms=50.0,
            queries_per_second=30.0,
            utilization_rate=0.3,  # 30% < target 75%
            health_score=90.0,
        )

        size_low = calculator._calculate_by_utilization(metrics_low)
        assert size_low < metrics_low.current_size  # Should scale down

    def test_calculate_by_queue_depth(self, calculator):
        """Test queue depth based calculation."""
        # High queue depth - need more connections
        metrics = PoolMetrics(
            current_size=10,
            active_connections=10,
            idle_connections=0,
            queue_depth=8,  # Significant queue
            avg_wait_time_ms=100.0,
            avg_query_time_ms=50.0,
            queries_per_second=100.0,
            utilization_rate=1.0,
            health_score=90.0,
        )

        size = calculator._calculate_by_queue_depth(metrics)
        assert size > metrics.current_size  # Should add connections

    def test_apply_constraints(self, calculator):
        """Test resource constraint application."""
        constraints = ResourceConstraints(
            max_database_connections=50,
            available_memory_mb=1000.0,
            memory_per_connection_mb=20.0,  # Max 50 connections by memory
            cpu_usage_percent=30.0,
            network_bandwidth_mbps=100.0,
        )

        # Should respect database limit (80% of 50 = 40)
        size = calculator._apply_constraints(100, 20, constraints)
        assert size == 40

        # Should respect memory limit
        constraints.available_memory_mb = 200.0  # Only 10 connections possible
        size = calculator._apply_constraints(30, 20, constraints)
        assert size == 10

        # High CPU should prevent scale up
        constraints.cpu_usage_percent = 85.0
        constraints.available_memory_mb = 1000.0  # Reset memory constraint
        size = calculator._apply_constraints(30, 20, constraints)
        assert size == 20  # No scale up

    def test_calculate_optimal_size_integration(self, calculator):
        """Test integrated optimal size calculation."""
        metrics = PoolMetrics(
            current_size=10,
            active_connections=8,
            idle_connections=2,
            queue_depth=3,
            avg_wait_time_ms=80.0,
            avg_query_time_ms=50.0,
            queries_per_second=150.0,
            utilization_rate=0.8,
            health_score=85.0,
        )

        constraints = ResourceConstraints(
            max_database_connections=100,
            available_memory_mb=2000.0,
            memory_per_connection_mb=10.0,
            cpu_usage_percent=50.0,
            network_bandwidth_mbps=100.0,
        )

        optimal_size = calculator.calculate_optimal_size(metrics, constraints)

        # Should be reasonable size based on load
        assert 8 <= optimal_size <= 80  # Between min reasonable and max constraint
        assert optimal_size <= 80  # 80% of max DB connections


class TestScalingDecisionEngine:
    """Test scaling decision logic."""

    @pytest.fixture
    def engine(self):
        return ScalingDecisionEngine(
            scale_up_threshold=0.15,
            scale_down_threshold=0.20,
            max_adjustment_step=2,
            cooldown_seconds=60,
        )

    def test_scale_up_decision(self, engine):
        """Test scale up decision making."""
        metrics = PoolMetrics(
            current_size=10,
            active_connections=9,
            idle_connections=1,
            queue_depth=5,
            avg_wait_time_ms=100.0,
            avg_query_time_ms=50.0,
            queries_per_second=150.0,
            utilization_rate=0.9,
            health_score=85.0,
        )

        # Force cooldown to be expired
        engine.last_scaling_time = datetime.now() - timedelta(seconds=120)

        decision = engine.should_scale(
            current_size=10, optimal_size=14, metrics=metrics  # 40% increase
        )

        assert decision.action == "scale_up"
        assert decision.target_size == 12  # Limited by max_adjustment_step
        assert decision.confidence > 0.6  # Adjusted threshold

    def test_scale_down_decision(self, engine):
        """Test scale down decision making."""
        metrics = PoolMetrics(
            current_size=20,
            active_connections=5,
            idle_connections=15,
            queue_depth=0,
            avg_wait_time_ms=5.0,
            avg_query_time_ms=50.0,
            queries_per_second=50.0,
            utilization_rate=0.25,
            health_score=95.0,
        )

        # Force cooldown to be expired
        engine.last_scaling_time = datetime.now() - timedelta(seconds=120)

        decision = engine.should_scale(
            current_size=20, optimal_size=10, metrics=metrics  # 50% decrease
        )

        assert decision.action == "scale_down"
        assert decision.target_size == 18  # Limited by max_adjustment_step
        assert "Low utilization" in decision.reason

    def test_cooldown_period(self, engine):
        """Test cooldown period enforcement."""
        metrics = PoolMetrics(
            current_size=10,
            active_connections=9,
            idle_connections=1,
            queue_depth=5,
            avg_wait_time_ms=100.0,
            avg_query_time_ms=50.0,
            queries_per_second=150.0,
            utilization_rate=0.9,
            health_score=85.0,
        )

        # Recent scaling - should be in cooldown
        engine.last_scaling_time = datetime.now() - timedelta(seconds=30)

        decision = engine.should_scale(
            current_size=10, optimal_size=15, metrics=metrics
        )

        assert decision.action == "no_change"
        assert "cooldown" in decision.reason.lower()

    def test_emergency_scaling(self, engine):
        """Test emergency scaling bypasses cooldown."""
        metrics = PoolMetrics(
            current_size=10,
            active_connections=10,
            idle_connections=0,
            queue_depth=25,  # Very high queue
            avg_wait_time_ms=500.0,
            avg_query_time_ms=50.0,
            queries_per_second=200.0,
            utilization_rate=1.0,
            health_score=70.0,
        )

        # Even with recent scaling
        engine.last_scaling_time = datetime.now() - timedelta(seconds=10)

        decision = engine.should_scale(
            current_size=10, optimal_size=20, metrics=metrics, emergency=True
        )

        assert decision.action == "scale_up"
        assert "Emergency" in decision.reason
        assert decision.target_size == 14  # 2x max_adjustment_step

    def test_flapping_detection(self, engine):
        """Test flapping detection prevents oscillation."""
        # Simulate flapping history
        engine.decision_history.extend(
            [
                ScalingDecision("scale_up", 10, 12, "test", 0.8),
                ScalingDecision("scale_down", 12, 10, "test", 0.8),
                ScalingDecision("scale_up", 10, 12, "test", 0.8),
                ScalingDecision("scale_down", 12, 10, "test", 0.8),
            ]
        )

        metrics = PoolMetrics(
            current_size=10,
            active_connections=7,
            idle_connections=3,
            queue_depth=1,
            avg_wait_time_ms=50.0,
            avg_query_time_ms=50.0,
            queries_per_second=100.0,
            utilization_rate=0.7,
            health_score=85.0,
        )

        # Force cooldown to be expired
        engine.last_scaling_time = datetime.now() - timedelta(seconds=120)

        decision = engine.should_scale(
            current_size=10, optimal_size=12, metrics=metrics
        )

        assert decision.action == "no_change"
        assert "Flapping" in decision.reason


class TestResourceMonitor:
    """Test resource monitoring."""

    @pytest.fixture
    def monitor(self):
        return ResourceMonitor()

    @pytest.mark.asyncio
    async def test_get_resource_constraints(self, monitor):
        """Test resource constraint collection."""
        db_info = {"type": "postgresql", "host": "localhost", "database": "test"}

        constraints = await monitor.get_resource_constraints(db_info)

        assert constraints.max_database_connections == 100  # PostgreSQL default
        assert constraints.available_memory_mb > 0
        assert constraints.memory_per_connection_mb == 10.0
        assert 0 <= constraints.cpu_usage_percent <= 100
        assert constraints.network_bandwidth_mbps > 0

    @pytest.mark.asyncio
    async def test_constraint_caching(self, monitor):
        """Test that constraints are cached."""
        db_info = {"type": "postgresql"}

        # First call
        constraints1 = await monitor.get_resource_constraints(db_info)
        first_check_time = monitor.last_check_time

        # Second call (should use cache)
        await asyncio.sleep(0.1)
        constraints2 = await monitor.get_resource_constraints(db_info)
        second_check_time = monitor.last_check_time

        assert first_check_time == second_check_time  # Cache was used
        assert (
            constraints1.max_database_connections
            == constraints2.max_database_connections
        )


class TestAdaptivePoolController:
    """Test the main adaptive pool controller."""

    @pytest.fixture
    def controller(self):
        return AdaptivePoolController(
            min_size=5,
            max_size=50,
            target_utilization=0.75,
            adjustment_interval_seconds=30,
        )

    @pytest.fixture
    def mock_pool(self):
        """Create mock pool reference."""
        pool = AsyncMock()
        pool.db_config = {"type": "postgresql"}
        pool.get_pool_statistics = AsyncMock()
        pool.adjust_pool_size = AsyncMock(return_value=True)
        return pool

    @pytest.mark.asyncio
    async def test_start_stop(self, controller, mock_pool):
        """Test controller start/stop lifecycle."""
        # Start controller
        await controller.start(mock_pool)

        assert controller.running is True
        assert controller.adjustment_task is not None

        # Stop controller
        await controller.stop()

        assert controller.running is False
        assert controller.adjustment_task.cancelled()

    @pytest.mark.asyncio
    async def test_collect_metrics(self, controller, mock_pool):
        """Test metrics collection from pool."""
        mock_pool.get_pool_statistics.return_value = {
            "total_connections": 10,
            "active_connections": 7,
            "idle_connections": 3,
            "queue_depth": 2,
            "avg_acquisition_time_ms": 15.0,
            "avg_query_time_ms": 45.0,
            "queries_per_second": 120.0,
            "utilization_rate": 0.7,
            "avg_health_score": 88.0,
        }

        controller.pool_ref = mock_pool
        metrics = await controller._collect_metrics()

        assert metrics.current_size == 10
        assert metrics.active_connections == 7
        assert metrics.utilization_rate == 0.7
        assert metrics.queries_per_second == 120.0

    @pytest.mark.asyncio
    async def test_execute_scaling(self, controller, mock_pool):
        """Test scaling execution."""
        controller.pool_ref = mock_pool

        # Test scale up
        decision = ScalingDecision(
            action="scale_up",
            current_size=10,
            target_size=15,
            reason="High load",
            confidence=0.9,
        )

        await controller._execute_scaling(decision)

        mock_pool.adjust_pool_size.assert_called_once_with(15)

    @pytest.mark.asyncio
    async def test_emergency_detection(self, controller):
        """Test emergency situation detection."""
        # Normal metrics
        normal_metrics = PoolMetrics(
            current_size=10,
            active_connections=7,
            idle_connections=3,
            queue_depth=5,
            avg_wait_time_ms=50.0,
            avg_query_time_ms=45.0,
            queries_per_second=100.0,
            utilization_rate=0.7,
            health_score=85.0,
        )

        assert controller._is_emergency(normal_metrics) is False

        # Emergency metrics
        emergency_metrics = PoolMetrics(
            current_size=10,
            active_connections=10,
            idle_connections=0,
            queue_depth=25,  # > 2x pool size
            avg_wait_time_ms=1500.0,  # > 1 second
            avg_query_time_ms=50.0,
            queries_per_second=200.0,
            utilization_rate=1.0,
            health_score=60.0,
        )

        assert controller._is_emergency(emergency_metrics) is True

    def test_adjustment_history(self, controller):
        """Test adjustment history tracking."""
        # Add some decisions to history
        controller.decision_engine.decision_history.extend(
            [
                ScalingDecision("scale_up", 10, 12, "High load", 0.9),
                ScalingDecision("no_change", 12, 12, "Stable", 0.8),
                ScalingDecision("scale_down", 12, 10, "Low load", 0.85),
            ]
        )

        controller.decision_engine.last_scaling_time = datetime.now()

        history = controller.get_adjustment_history()

        assert len(history) == 2  # Only scaling actions
        assert history[0]["action"] == "scale_up"
        assert history[1]["action"] == "scale_down"
