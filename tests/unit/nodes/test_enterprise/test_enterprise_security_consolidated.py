"""Consolidated tests for enterprise security nodes (MFA and Threat Detection)."""

import pytest
from kailash.nodes.auth.mfa import MultiFactorAuthNode
from kailash.nodes.security.threat_detection import ThreatDetectionNode


class TestMultiFactorAuthNode:
    """Test core MFA node functionality."""

    def test_initialization(self):
        """Test MFA node can be initialized."""
        node = MultiFactorAuthNode(name="test_mfa")
        assert node.metadata.name == "test_mfa"

    def test_get_parameters(self):
        """Test MFA node parameter definition."""
        node = MultiFactorAuthNode(name="test_mfa")
        params = node.get_parameters()

        # Basic parameter validation
        assert isinstance(params, dict)
        assert "action" in params
        assert params["action"].required is True

    def test_supports_totp(self):
        """Test MFA node supports TOTP method."""
        node = MultiFactorAuthNode(name="test_mfa")
        result = node.execute(action="get_methods", user_id="test_user")

        assert result["success"] is True
        # Check that the result includes available methods
        assert "available_methods" in result or "methods" in result

    def test_backup_codes_format(self):
        """Test backup codes are generated in correct format."""
        node = MultiFactorAuthNode(name="test_mfa")
        result = node.execute(action="generate_backup_codes", user_id="test_user")

        assert result["success"] is True
        assert "backup_codes" in result
        # Backup codes should be 8 characters each
        for code in result["backup_codes"]:
            assert len(code) == 8
            assert code.isalnum()


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
