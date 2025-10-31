"""Unit tests for predictive edge warming."""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from kailash.edge.prediction.predictive_warmer import (
    PredictionStrategy,
    PredictiveWarmer,
    UsagePattern,
    WarmingDecision,
)


class TestPredictiveWarmer:
    """Test predictive warmer functionality."""

    @pytest.fixture
    def warmer(self):
        """Create a predictive warmer instance."""
        return PredictiveWarmer(
            history_window=3600,  # 1 hour
            prediction_horizon=300,  # 5 minutes
            confidence_threshold=0.1,  # Lower threshold for testing
            max_prewarmed_nodes=5,
        )

    @pytest.fixture
    def sample_patterns(self):
        """Create sample usage patterns."""
        base_time = datetime.now()
        patterns = []

        # Create patterns for edge-1 with morning usage
        for i in range(10):
            patterns.append(
                UsagePattern(
                    timestamp=base_time.replace(hour=9) - timedelta(days=i),
                    edge_node="edge-1",
                    user_id="user1",
                    location=(37.7749, -122.4194),
                    workload_type="ml_inference",
                    response_time=0.250,
                    resource_usage={"cpu": 0.3, "memory": 512},
                )
            )

        # Create patterns for edge-2 with evening usage
        for i in range(10):
            patterns.append(
                UsagePattern(
                    timestamp=base_time.replace(hour=18) - timedelta(days=i),
                    edge_node="edge-2",
                    user_id="user2",
                    location=(40.7128, -74.0060),
                    workload_type="data_processing",
                    response_time=0.500,
                    resource_usage={"cpu": 0.5, "memory": 1024},
                )
            )

        return patterns

    @pytest.mark.asyncio
    async def test_record_usage(self, warmer, sample_patterns):
        """Test recording usage patterns."""
        # Record patterns
        for pattern in sample_patterns[:5]:
            await warmer.record_usage(pattern)

        # Verify patterns recorded
        assert len(warmer.usage_history) == 5
        assert "edge-1" in warmer.pattern_cache
        assert "user_user1" in warmer.pattern_cache
        assert "ml_inference" in warmer.pattern_cache

    @pytest.mark.asyncio
    async def test_time_series_prediction(self, warmer, sample_patterns):
        """Test time series prediction strategy."""
        # Record historical patterns
        for pattern in sample_patterns:
            await warmer.record_usage(pattern)

        # Manually set model as trained for testing
        warmer.model_trained = True

        # Mock current time to morning (should predict edge-1)
        with patch(
            "kailash.edge.prediction.predictive_warmer.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = datetime.now().replace(hour=9)

            decisions = await warmer._predict_time_series()

            # Debug: Check what patterns were recorded
            if len(decisions) == 0:
                print(f"Debug: usage_history length: {len(warmer.usage_history)}")
                print(f"Debug: pattern_cache keys: {list(warmer.pattern_cache.keys())}")
                morning_patterns = [
                    p for p in warmer.usage_history if p.timestamp.hour == 9
                ]
                print(f"Debug: morning patterns: {len(morning_patterns)}")

            # Should predict edge-1 for morning usage (reduce threshold if needed)
            assert len(decisions) > 0
            edge_1_decisions = [d for d in decisions if d.edge_node == "edge-1"]
            assert len(edge_1_decisions) > 0
            assert edge_1_decisions[0].confidence > 0.5

    @pytest.mark.asyncio
    async def test_geographic_prediction(self, warmer, sample_patterns):
        """Test geographic prediction strategy."""
        # Record patterns with location
        for pattern in sample_patterns[:10]:
            await warmer.record_usage(pattern)

        # Add multiple recent patterns to make location active (need >5)
        for i in range(6):
            recent_pattern = UsagePattern(
                timestamp=datetime.now() - timedelta(minutes=i * 5),  # Every 5 minutes
                edge_node="edge-1",
                user_id=f"user{i}",
                location=(37.7749, -122.4194),  # Same as edge-1 patterns
                workload_type="ml_inference",
                response_time=0.200,
                resource_usage={"cpu": 0.3, "memory": 512},
            )
            await warmer.record_usage(recent_pattern)

        # Manually set model as trained for testing
        warmer.model_trained = True

        decisions = await warmer._predict_geographic()

        # Debug: Check geographic analysis
        if len(decisions) == 0:
            print(f"Debug: usage_history length: {len(warmer.usage_history)}")
            location_patterns = defaultdict(list)
            for pattern in warmer.usage_history:
                if pattern.location:
                    lat_grid = int(pattern.location[0] * 10) / 10
                    lon_grid = int(pattern.location[1] * 10) / 10
                    location_patterns[(lat_grid, lon_grid)].append(pattern)
            print(f"Debug: location patterns: {dict(location_patterns)}")

            current_time = datetime.now()
            for location, patterns in location_patterns.items():
                recent_patterns = [
                    p
                    for p in patterns
                    if (current_time - p.timestamp).total_seconds() < 3600  # Last hour
                ]
                print(
                    f"Debug: location {location} has {len(recent_patterns)} recent patterns"
                )

        # Should predict based on active location
        assert len(decisions) > 0
        assert any(d.strategy_used == PredictionStrategy.GEOGRAPHIC for d in decisions)

    @pytest.mark.asyncio
    async def test_user_behavior_prediction(self, warmer, sample_patterns):
        """Test user behavior prediction strategy."""
        # Record patterns
        for pattern in sample_patterns:
            await warmer.record_usage(pattern)

        # Mock current time to match user1's typical usage
        with patch(
            "kailash.edge.prediction.predictive_warmer.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = datetime.now().replace(hour=9)

            decisions = await warmer._predict_user_behavior()

            # Should predict based on user patterns
            assert len(decisions) > 0
            user_decisions = [d for d in decisions if "user1" in d.reasoning]
            assert len(user_decisions) > 0

    @pytest.mark.asyncio
    async def test_workload_prediction(self, warmer):
        """Test workload-based prediction strategy."""
        # Create surge in specific workload type
        base_time = datetime.now()
        for i in range(10):
            pattern = UsagePattern(
                timestamp=base_time - timedelta(minutes=i),
                edge_node="edge-3",
                user_id=f"user{i}",
                location=None,
                workload_type="batch_processing",
                response_time=1.0,
                resource_usage={"cpu": 0.8, "memory": 2048},
            )
            await warmer.record_usage(pattern)

        decisions = await warmer._predict_workload()

        # Should detect surge in batch_processing
        assert len(decisions) > 0
        assert any("batch_processing" in d.reasoning for d in decisions)

    @pytest.mark.asyncio
    async def test_hybrid_prediction(self, warmer, sample_patterns):
        """Test hybrid prediction strategy."""
        # Record diverse patterns
        for pattern in sample_patterns:
            await warmer.record_usage(pattern)

        # Manually set model as trained for testing
        warmer.model_trained = True

        decisions = await warmer.predict_warming_needs(PredictionStrategy.HYBRID)

        # Should combine multiple strategies
        assert len(decisions) > 0
        assert decisions[0].strategy_used == PredictionStrategy.HYBRID
        assert decisions[0].confidence >= warmer.confidence_threshold

    @pytest.mark.asyncio
    async def test_confidence_filtering(self, warmer):
        """Test confidence threshold filtering."""
        # Create patterns with varying confidence
        pattern = UsagePattern(
            timestamp=datetime.now(),
            edge_node="edge-low-conf",
            user_id="user1",
            location=None,
            workload_type="rare_workload",
            response_time=0.100,
            resource_usage={"cpu": 0.1, "memory": 64},
        )
        await warmer.record_usage(pattern)

        # Set high confidence threshold
        warmer.confidence_threshold = 0.9

        decisions = await warmer.predict_warming_needs()

        # Low confidence predictions should be filtered
        assert all(d.confidence >= 0.9 for d in decisions)

    @pytest.mark.asyncio
    async def test_max_nodes_limit(self, warmer, sample_patterns):
        """Test maximum prewarmed nodes limit."""
        # Record many patterns
        for pattern in sample_patterns * 3:  # Triple patterns
            await warmer.record_usage(pattern)

        # Set low limit
        warmer.max_prewarmed_nodes = 2

        decisions = await warmer.predict_warming_needs()

        # Should respect limit
        assert len(decisions) <= 2

    def test_resource_estimation(self, warmer, sample_patterns):
        """Test resource estimation."""
        resources = warmer._estimate_resources(sample_patterns[:5])

        # Should estimate based on patterns
        assert "cpu" in resources
        assert "memory" in resources
        assert resources["cpu"] > 0
        assert resources["memory"] > 0

    def test_decision_aggregation(self, warmer):
        """Test decision aggregation from multiple strategies."""
        # Create decisions from different strategies
        decisions = [
            WarmingDecision(
                edge_node="edge-1",
                confidence=0.8,
                predicted_time=datetime.now(),
                resources_needed={"cpu": 0.3, "memory": 512},
                strategy_used=PredictionStrategy.TIME_SERIES,
                reasoning="Time pattern",
            ),
            WarmingDecision(
                edge_node="edge-1",
                confidence=0.7,
                predicted_time=datetime.now(),
                resources_needed={"cpu": 0.4, "memory": 768},
                strategy_used=PredictionStrategy.GEOGRAPHIC,
                reasoning="Location pattern",
            ),
            WarmingDecision(
                edge_node="edge-2",
                confidence=0.9,
                predicted_time=datetime.now(),
                resources_needed={"cpu": 0.5, "memory": 1024},
                strategy_used=PredictionStrategy.WORKLOAD,
                reasoning="Workload surge",
            ),
        ]

        aggregated = warmer._aggregate_decisions(decisions)

        # Should aggregate by node
        assert len(aggregated) == 2

        # edge-1 should have combined confidence
        edge_1_agg = [d for d in aggregated if d.edge_node == "edge-1"][0]
        assert edge_1_agg.strategy_used == PredictionStrategy.HYBRID
        assert 0.7 < edge_1_agg.confidence < 0.8  # Weighted average

        # Resources should be max of estimates
        assert edge_1_agg.resources_needed["cpu"] == 0.4
        assert edge_1_agg.resources_needed["memory"] == 768

    def test_prediction_evaluation(self, warmer):
        """Test prediction evaluation."""
        # Simulate predictions and usage
        warmer.warmed_nodes.add("edge-1")
        warmer.warmed_nodes.add("edge-2")

        # edge-1 was used (correct prediction)
        warmer.evaluate_prediction("edge-1", True)

        # edge-2 was not used (false positive)
        warmer.evaluate_prediction("edge-2", False)

        # edge-3 was used but not predicted (miss)
        warmer.evaluate_prediction("edge-3", True)

        metrics = warmer.get_metrics()

        assert metrics["successful_predictions"] == 1
        assert metrics["false_positives"] == 1
        assert metrics["missed_predictions"] == 1
        assert 0.4 < metrics["precision"] < 0.6  # 1/(1+1) = 0.5
        assert 0.4 < metrics["recall"] < 0.6  # 1/(1+1) = 0.5

    @pytest.mark.asyncio
    async def test_prediction_loop(self, warmer):
        """Test automatic prediction loop."""
        # Start warmer
        await warmer.start()

        # Should have started prediction task
        assert warmer._prediction_task is not None
        assert warmer._running is True

        # Let it run briefly
        await asyncio.sleep(0.1)

        # Stop warmer
        await warmer.stop()

        # Should be stopped
        assert warmer._running is False

    def test_usage_pattern_features(self):
        """Test usage pattern feature extraction."""
        pattern = UsagePattern(
            timestamp=datetime.now().replace(hour=14),
            edge_node="edge-1",
            user_id="user1",
            location=(37.7749, -122.4194),
            workload_type="ml_inference",
            response_time=0.250,
            resource_usage={"cpu": 0.3, "memory": 512},
        )

        features = pattern.to_features()

        # Should extract features
        assert len(features) == 7  # hour, weekday, response_time, cpu, memory, lat, lon
        assert features[0] == 14  # hour
        assert features[2] == 0.250  # response_time
        assert features[3] == 0.3  # cpu
        assert features[4] == 512  # memory
        assert features[5] == 37.7749  # latitude
        assert features[6] == -122.4194  # longitude
