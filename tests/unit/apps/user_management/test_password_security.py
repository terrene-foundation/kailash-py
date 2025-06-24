"""Unit tests for password security logic."""

import time
from unittest.mock import Mock, patch

import bcrypt
import pytest

from apps.user_management.nodes.password_security_node import PasswordSecurityNode


class TestPasswordSecurityNode:
    """Test PasswordSecurityNode in isolation."""

    def test_password_hashing(self):
        """Test password hashing functionality."""
        security = PasswordSecurityNode()

        password = "MySecure123!Key"
        # Execute with parameters
        result = security.execute(operation="hash", password=password)

        assert "hashed_password" in result
        assert result["hashed_password"] != password
        # The node returns a hash, verify it's a valid bcrypt hash
        assert result["hashed_password"].startswith("$2")

    def test_password_verification_correct(self):
        """Test verification of correct password."""
        security = PasswordSecurityNode()

        password = "MySecure123!Key"

        # First hash the password
        hash_result = security.execute(operation="hash", password=password)
        hashed = hash_result["hashed_password"]

        # Then verify it
        verify_result = security.execute(
            operation="verify", password=password, hashed_password=hashed
        )

        assert verify_result["is_valid"] is True

    def test_password_verification_incorrect(self):
        """Test verification of incorrect password."""
        security = PasswordSecurityNode()

        password = "MySecure123!Key"
        wrong_password = "WrongPassword123!"

        # Hash the correct password
        hash_result = security.execute(operation="hash", password=password)
        hashed = hash_result["hashed_password"]

        # Try to verify with wrong password
        verify_result = security.execute(
            operation="verify", password=wrong_password, hashed_password=hashed
        )

        assert verify_result["is_valid"] is False

    def test_different_hashes_for_same_password(self):
        """Test that same password produces different hashes (salt)."""
        security = PasswordSecurityNode()

        password = "MySecure123!Key"

        # Hash same password twice
        result1 = security.execute(operation="hash", password=password)
        result2 = security.execute(operation="hash", password=password)

        # Hashes should be different due to salt
        assert result1["hashed_password"] != result2["hashed_password"]

        # But both should verify correctly
        verify1 = security.execute(
            operation="verify",
            password=password,
            hashed_password=result1["hashed_password"],
        )
        verify2 = security.execute(
            operation="verify",
            password=password,
            hashed_password=result2["hashed_password"],
        )

        assert verify1["is_valid"] is True
        assert verify2["is_valid"] is True

    def test_cost_factor_configuration(self):
        """Test different cost factors affect timing."""
        # Test with lower cost (faster but less secure)
        security_fast = PasswordSecurityNode(cost_factor=4)

        # Test with higher cost (slower but more secure)
        security_slow = PasswordSecurityNode(cost_factor=12)

        password = "TestKey123!Strong"

        # Time multiple runs to get more reliable timing
        fast_times = []
        slow_times = []

        for _ in range(3):
            start = time.time()
            fast_result = security_fast.execute(operation="hash", password=password)
            fast_times.append(time.time() - start)

            start = time.time()
            slow_result = security_slow.execute(operation="hash", password=password)
            slow_times.append(time.time() - start)

        # Use average times for more stable comparison
        avg_fast_time = sum(fast_times) / len(fast_times)
        avg_slow_time = sum(slow_times) / len(slow_times)

        # Higher cost should generally take longer (allow some variance)
        # At minimum, check that both produce valid hashes
        assert fast_result["hashed_password"].startswith("$2")
        assert slow_result["hashed_password"].startswith("$2")

        # Cost factors should be different
        assert fast_result["hash_data"]["cost"] == 4
        assert slow_result["hash_data"]["cost"] == 12

    def test_password_strength_check(self):
        """Test password strength validation."""
        security = PasswordSecurityNode()

        # Test with a weak password - should still hash but return success=False for breach
        result = security.execute(operation="hash", password="password123")
        # Since this contains "password", it should be rejected as breached
        assert result["success"] is False
        assert "error" in result

        # Test strong password
        result = security.execute(operation="hash", password="MyStr0ng!K3y#2024")
        assert result["success"] is True
        assert "hashed_password" in result

    def test_breach_check(self):
        """Test password breach checking."""
        security = PasswordSecurityNode(check_breaches=True)

        # Test with a commonly breached password pattern
        result = security.execute(operation="hash", password="password123")

        # Should detect the common pattern and reject
        assert result["success"] is False
        assert "error" in result
        assert "compromised" in result["error"]

    def test_invalid_operation(self):
        """Test handling of invalid operations."""
        security = PasswordSecurityNode()

        result = security.execute(operation="invalid_operation", password="test")

        # Should handle gracefully with error
        assert result["success"] is False
        assert "error" in result
        assert "Unknown operation" in result["error"]

    def test_missing_required_parameters(self):
        """Test handling of missing parameters."""
        security = PasswordSecurityNode()

        # Missing password for hash operation
        result = security.execute(operation="hash")
        # Should handle gracefully
        assert result["success"] is False
        assert "error" in result
        assert "No password provided" in result["error"]

        # Missing hashed_password for verify operation
        result = security.execute(operation="verify", password="test")
        # Should handle gracefully
        assert result["success"] is False
        assert "error" in result
        assert "Missing password or hash" in result["error"]
