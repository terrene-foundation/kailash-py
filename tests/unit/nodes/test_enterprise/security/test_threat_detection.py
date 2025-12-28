"""
Test core SDK threat detection node functionality.

Tests the basic functionality of the threat detection node that's part of the core SDK.
"""

import pytest
from kailash.nodes.security.threat_detection import ThreatDetectionNode


class TestThreatDetectionNode:
    """Test core threat detection node functionality."""

    def test_initialization(self):
        """Test threat detection node can be initialized."""
        node = ThreatDetectionNode(name="test_threat_detection")
        assert node.metadata.name == "test_threat_detection"

    def test_get_parameters(self):
        """Test threat detection node parameter definition."""
        node = ThreatDetectionNode(name="test_threat_detection")
        params = node.get_parameters()

        # Basic parameter validation
        assert isinstance(params, dict)
        assert "events" in params
        assert params["events"].required is True

    def test_basic_threat_analysis(self):
        """Test basic threat analysis with events."""
        node = ThreatDetectionNode(name="test_threat_detection")
        result = node.execute(
            events=[
                {
                    "type": "login_attempt",
                    "ip_address": "8.8.8.8",
                    "user_id": "test_user",
                    "timestamp": "2024-06-15T10:00:00Z",
                }
            ]
        )

        assert result["success"] is True
        assert "threats" in result

    def test_multiple_events_analysis(self):
        """Test analysis with multiple events."""
        node = ThreatDetectionNode(name="test_threat_detection")
        result = node.execute(
            events=[
                {
                    "type": "login_attempt",
                    "ip_address": "192.168.1.1",
                    "user_id": "test_user",
                    "timestamp": "2024-06-15T10:00:00Z",
                    "status": "success",
                },
                {
                    "type": "login_attempt",
                    "ip_address": "192.168.1.1",
                    "user_id": "test_user",
                    "timestamp": "2024-06-15T10:01:00Z",
                    "status": "success",
                },
            ]
        )

        assert result["success"] is True
        assert "threats" in result
