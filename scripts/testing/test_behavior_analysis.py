#!/usr/bin/env python3
"""
Behavior Analysis Tests

Focused tests for user behavior analysis including
baseline establishment, anomaly detection, and pattern recognition.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from kailash.nodes.security.behavior_analysis import BehaviorAnalysisNode


class TestBehaviorAnalysis:
    """Test suite for behavior analysis functionality."""

    @pytest.fixture
    def behavior_node(self):
        """Create behavior analysis node with minimal config."""
        return BehaviorAnalysisNode(
            baseline_period=timedelta(days=7),
            anomaly_threshold=0.7,
            learning_enabled=True,
            ml_model="isolation_forest",
            update_baseline_automatically=False,  # Manual control for tests
        )

    @pytest.fixture
    def user_id(self):
        """Test user ID."""
        return "behavior_test_user"

    @pytest.fixture
    def normal_activities(self):
        """Generate normal activity patterns."""
        activities = []
        base_date = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=7)

        # Generate 7 days of normal 9-5 activity
        for day in range(7):
            if day % 7 not in [5, 6]:  # Skip weekends
                for hour in [9, 10, 11, 14, 15, 16]:
                    activities.append(
                        {
                            "timestamp": (
                                base_date + timedelta(days=day, hours=hour)
                            ).isoformat(),
                            "action": "login",
                            "location": "New York",
                            "device": "work_laptop",
                            "ip_address": "10.0.0.50",
                            "resources_accessed": ["email", "documents"],
                            "data_volume_mb": 10 + (hour % 3) * 5,
                        }
                    )

        return activities

    @pytest.mark.asyncio
    async def test_baseline_establishment(
        self, behavior_node, user_id, normal_activities
    ):
        """Test establishing a behavior baseline."""
        result = await behavior_node.execute_async(
            action="establish_baseline",
            user_id=user_id,
            historical_activities=normal_activities,
        )

        assert result["success"] is True
        assert result["baseline_established"] is True
        assert "baseline_stats" in result

        stats = result["baseline_stats"]
        assert "activity_hours" in stats
        assert "common_locations" in stats
        assert "typical_devices" in stats
        assert stats["common_locations"][0] == "New York"

    @pytest.mark.asyncio
    async def test_normal_behavior_analysis(
        self, behavior_node, user_id, normal_activities
    ):
        """Test analysis of normal behavior."""
        # Establish baseline first
        await behavior_node.execute_async(
            action="establish_baseline",
            user_id=user_id,
            historical_activities=normal_activities,
        )

        # Test normal activity
        normal_activity = {
            "timestamp": datetime.now(UTC).replace(hour=10).isoformat(),
            "action": "login",
            "location": "New York",
            "device": "work_laptop",
            "ip_address": "10.0.0.50",
            "resources_accessed": ["email", "documents"],
            "data_volume_mb": 15,
        }

        result = await behavior_node.execute_async(
            action="analyze", user_id=user_id, activity=normal_activity
        )

        assert result["success"] is True
        assert result["anomaly_score"] < 0.3
        assert result["risk_level"] == "low"
        assert len(result.get("anomaly_factors", [])) == 0

    @pytest.mark.asyncio
    async def test_location_anomaly_detection(
        self, behavior_node, user_id, normal_activities
    ):
        """Test detection of location anomalies."""
        # Establish baseline
        await behavior_node.execute_async(
            action="establish_baseline",
            user_id=user_id,
            historical_activities=normal_activities,
        )

        # Test activity from unusual location
        anomalous_activity = {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "login",
            "location": "Moscow",  # Unusual location
            "device": "unknown_device",
            "ip_address": "185.220.101.50",
            "resources_accessed": ["email"],
            "data_volume_mb": 10,
        }

        result = await behavior_node.execute_async(
            action="analyze", user_id=user_id, activity=anomalous_activity
        )

        assert result["success"] is True
        assert result["anomaly_score"] > 0.7
        assert result["risk_level"] in ["high", "critical"]
        assert "unusual_location" in result["anomaly_factors"]
        assert "unknown_device" in result["anomaly_factors"]

    @pytest.mark.asyncio
    async def test_time_anomaly_detection(
        self, behavior_node, user_id, normal_activities
    ):
        """Test detection of time-based anomalies."""
        # Establish baseline
        await behavior_node.execute_async(
            action="establish_baseline",
            user_id=user_id,
            historical_activities=normal_activities,
        )

        # Test activity at unusual time (3 AM)
        anomalous_activity = {
            "timestamp": datetime.now(UTC).replace(hour=3).isoformat(),
            "action": "login",
            "location": "New York",
            "device": "work_laptop",
            "ip_address": "10.0.0.50",
            "resources_accessed": ["sensitive_data"],
            "data_volume_mb": 100,
        }

        result = await behavior_node.execute_async(
            action="analyze", user_id=user_id, activity=anomalous_activity
        )

        assert result["success"] is True
        assert result["anomaly_score"] > 0.5
        assert "unusual_time" in result["anomaly_factors"]
        assert "high_data_volume" in result["anomaly_factors"]

    @pytest.mark.asyncio
    async def test_resource_access_anomaly(
        self, behavior_node, user_id, normal_activities
    ):
        """Test detection of unusual resource access patterns."""
        # Establish baseline
        await behavior_node.execute_async(
            action="establish_baseline",
            user_id=user_id,
            historical_activities=normal_activities,
        )

        # Access to unusual resources
        anomalous_activity = {
            "timestamp": datetime.now(UTC).replace(hour=10).isoformat(),
            "action": "data_access",
            "location": "New York",
            "device": "work_laptop",
            "ip_address": "10.0.0.50",
            "resources_accessed": [
                "customer_database",
                "financial_reports",
                "hr_records",
            ],
            "data_volume_mb": 500,
        }

        result = await behavior_node.execute_async(
            action="analyze", user_id=user_id, activity=anomalous_activity
        )

        assert result["success"] is True
        assert result["anomaly_score"] > 0.6
        assert "unusual_resources" in result["anomaly_factors"]
        assert "excessive_data_access" in result["anomaly_factors"]

    @pytest.mark.asyncio
    async def test_pattern_detection(self, behavior_node, user_id):
        """Test detection of behavioral patterns."""
        # Create activities with a pattern
        activities = []
        base_time = datetime.now(UTC) - timedelta(days=14)

        # Regular pattern: Access sensitive data every Friday at 4 PM
        for week in range(4):  # Increased to 4 weeks for more data points
            for day in range(7):
                timestamp = base_time + timedelta(weeks=week, days=day, hours=16)
                if day == 4:  # Friday
                    activities.append(
                        {
                            "timestamp": timestamp.isoformat(),
                            "action": "data_export",
                            "resources_accessed": [
                                "customer_data",
                                "financial_reports",
                            ],  # More resources
                            "data_volume_mb": 100,
                        }
                    )
                    # Add another activity same day different hour for more patterns
                    timestamp2 = base_time + timedelta(weeks=week, days=day, hours=9)
                    activities.append(
                        {
                            "timestamp": timestamp2.isoformat(),
                            "action": "login",
                            "resources_accessed": ["customer_data"],
                            "data_volume_mb": 10,
                        }
                    )

        result = await behavior_node.execute_async(
            action="detect_patterns",
            user_id=user_id,
            activities=activities,
            pattern_types=["temporal", "resource"],
        )

        assert result["success"] is True
        assert "patterns_detected" in result
        assert len(result["patterns_detected"]) > 0

        # Should detect the Friday pattern
        friday_pattern = next(
            (p for p in result["patterns_detected"] if p["type"] == "temporal"), None
        )
        assert friday_pattern is not None
        assert "weekly" in friday_pattern["description"].lower()

    @pytest.mark.asyncio
    async def test_adaptive_baseline_update(
        self, behavior_node, user_id, normal_activities
    ):
        """Test adaptive baseline updates."""
        # Establish initial baseline
        await behavior_node.execute_async(
            action="establish_baseline",
            user_id=user_id,
            historical_activities=normal_activities,
        )

        # New legitimate pattern (working late for a week)
        new_activities = []
        for day in range(5):
            for hour in [9, 10, 11, 14, 15, 16, 17, 18, 19]:  # Extended hours
                new_activities.append(
                    {
                        "timestamp": (
                            datetime.now(UTC) - timedelta(days=day, hours=24 - hour)
                        ).isoformat(),
                        "action": "login",
                        "location": "New York",
                        "device": "work_laptop",
                        "ip_address": "10.0.0.50",
                        "resources_accessed": ["email", "documents", "project_files"],
                        "data_volume_mb": 20,
                    }
                )

        # Update baseline with new pattern
        update_result = await behavior_node.execute_async(
            action="update_baseline",
            user_id=user_id,
            new_activities=new_activities,
            adaptation_rate=0.3,  # 30% weight to new patterns
        )

        assert update_result["success"] is True
        assert update_result["baseline_updated"] is True

        # Test that evening activity is now less anomalous
        evening_activity = {
            "timestamp": datetime.now(UTC).replace(hour=18).isoformat(),
            "action": "login",
            "location": "New York",
            "device": "work_laptop",
            "ip_address": "10.0.0.50",
            "resources_accessed": ["project_files"],
            "data_volume_mb": 20,
        }

        result = await behavior_node.execute_async(
            action="analyze", user_id=user_id, activity=evening_activity
        )

        assert result["anomaly_score"] < 0.5  # Should be more normal now

    @pytest.mark.asyncio
    async def test_peer_group_comparison(self, behavior_node):
        """Test behavior analysis with peer group comparison."""
        # First establish profiles for peer group
        peer_ids = ["peer1", "peer2", "peer3"]
        for peer_id in peer_ids:
            await behavior_node.execute_async(
                action="establish_baseline",
                user_id=peer_id,
                historical_activities=[
                    {
                        "timestamp": (
                            datetime.now(UTC) - timedelta(days=i)
                        ).isoformat(),
                        "action": "data_download",
                        "data_volume_mb": 50 + i * 10,  # 50-80 MB range
                        "location": "New York",
                    }
                    for i in range(5)
                ],
            )

        # Establish baseline for test user with high volume
        await behavior_node.execute_async(
            action="establish_baseline",
            user_id="test_user",
            historical_activities=[
                {
                    "timestamp": (datetime.now(UTC) - timedelta(days=i)).isoformat(),
                    "action": "data_download",
                    "data_volume_mb": 1000,  # Much higher than peers
                    "location": "New York",
                }
                for i in range(5)
            ],
        )

        # Compare to peer group
        result = await behavior_node.execute_async(
            action="compare_peer_group", user_id="test_user", peer_group=peer_ids
        )

        assert result["success"] is True
        assert result["anomalous"] is True  # User should be anomalous vs peers
        assert result["risk_score"] > 0.0  # Should have elevated risk
        assert len(result["deviations"]) > 0  # Should have deviations detected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
