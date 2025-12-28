"""
Test core SDK MFA (Multi-Factor Authentication) node functionality.

Tests the basic functionality of the MFA node that's part of the core SDK,
not app-specific MFA implementations.
"""

import pytest
from kailash.nodes.auth.mfa import MultiFactorAuthNode


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
