"""
Unit Tests for Trust Posture Mapping (Tier 1)

Tests the trust posture mapping for Enterprise-App integration.
Part of TODO-204 Enterprise-App Streaming Integration.

Coverage:
- TrustPosture enum
- PostureConstraints dataclass
- PostureResult dataclass
- TrustPostureMapper
- Convenience functions
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest
from kaizen.trust.postures import (
    PostureConstraints,
    PostureResult,
    TrustPosture,
    TrustPostureMapper,
    get_posture_for_action,
    map_verification_to_posture,
)


class TestTrustPosture:
    """Test TrustPosture enum."""

    def test_posture_values(self):
        """Test all posture values exist."""
        assert TrustPosture.FULL_AUTONOMY.value == "full_autonomy"
        assert TrustPosture.ASSISTED.value == "assisted"
        assert TrustPosture.SUPERVISED.value == "supervised"
        assert TrustPosture.HUMAN_DECIDES.value == "human_decides"
        assert TrustPosture.BLOCKED.value == "blocked"

    def test_posture_count(self):
        """Test that we have exactly 5 postures."""
        assert len(TrustPosture) == 5

    def test_posture_is_string_enum(self):
        """Test that TrustPosture inherits from str."""
        assert isinstance(TrustPosture.FULL_AUTONOMY, str)
        assert TrustPosture.SUPERVISED == "supervised"


class TestPostureConstraints:
    """Test PostureConstraints dataclass."""

    def test_default_values(self):
        """Test default values."""
        constraints = PostureConstraints()

        assert constraints.audit_required is False
        assert constraints.approval_required is False
        assert constraints.log_level == "info"
        assert constraints.allowed_capabilities is None
        assert constraints.blocked_capabilities is None
        assert constraints.max_actions_before_review is None
        assert constraints.require_human_approval_for is None
        assert constraints.metadata == {}

    def test_custom_values(self):
        """Test custom values."""
        constraints = PostureConstraints(
            audit_required=True,
            approval_required=True,
            log_level="warning",
            allowed_capabilities=["read", "write"],
            blocked_capabilities=["delete"],
            max_actions_before_review=10,
            require_human_approval_for=["delete", "execute_code"],
            metadata={"policy": "strict"},
        )

        assert constraints.audit_required is True
        assert constraints.approval_required is True
        assert constraints.log_level == "warning"
        assert constraints.allowed_capabilities == ["read", "write"]
        assert constraints.blocked_capabilities == ["delete"]
        assert constraints.max_actions_before_review == 10
        assert constraints.require_human_approval_for == ["delete", "execute_code"]
        assert constraints.metadata == {"policy": "strict"}

    def test_to_dict(self):
        """Test serialization."""
        constraints = PostureConstraints(
            audit_required=True,
            log_level="error",
        )

        data = constraints.to_dict()

        assert data["audit_required"] is True
        assert data["log_level"] == "error"
        assert "allowed_capabilities" in data
        assert "metadata" in data


class TestPostureResult:
    """Test PostureResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = PostureResult(posture=TrustPosture.SUPERVISED)

        assert result.posture == TrustPosture.SUPERVISED
        assert isinstance(result.constraints, PostureConstraints)
        assert result.reason == ""
        assert result.verification_details == {}

    def test_full_initialization(self):
        """Test full initialization."""
        constraints = PostureConstraints(audit_required=True)
        result = PostureResult(
            posture=TrustPosture.HUMAN_DECIDES,
            constraints=constraints,
            reason="Sensitive operation",
            verification_details={"agent_id": "agent-001"},
        )

        assert result.posture == TrustPosture.HUMAN_DECIDES
        assert result.constraints.audit_required is True
        assert result.reason == "Sensitive operation"
        assert result.verification_details == {"agent_id": "agent-001"}

    def test_to_dict(self):
        """Test serialization."""
        result = PostureResult(
            posture=TrustPosture.BLOCKED,
            reason="Access denied",
        )

        data = result.to_dict()

        assert data["posture"] == "blocked"
        assert data["reason"] == "Access denied"
        assert "constraints" in data
        assert "verification_details" in data


class MockVerificationResult:
    """Mock VerificationResult for testing."""

    def __init__(
        self,
        valid: bool = True,
        reason: str = "",
        constraints: Optional[Dict[str, Any]] = None,
        agent_id: str = "mock-agent",
    ):
        self.valid = valid
        self.reason = reason
        self.constraints = constraints or {}
        self.agent_id = agent_id


class TestTrustPostureMapper:
    """Test TrustPostureMapper."""

    def test_default_initialization(self):
        """Test default initialization."""
        mapper = TrustPostureMapper()

        assert mapper._default_posture == TrustPosture.SUPERVISED
        assert len(mapper._sensitive_capabilities) > 0
        assert len(mapper._high_risk_tools) > 0

    def test_custom_initialization(self):
        """Test custom initialization."""
        mapper = TrustPostureMapper(
            default_posture=TrustPosture.FULL_AUTONOMY,
            sensitive_capabilities=["custom_sensitive"],
            high_risk_tools=["custom_risk"],
        )

        assert mapper._default_posture == TrustPosture.FULL_AUTONOMY
        assert mapper._sensitive_capabilities == ["custom_sensitive"]
        assert mapper._high_risk_tools == ["custom_risk"]

    def test_map_none_result_blocks(self):
        """Test that None verification result returns BLOCKED."""
        mapper = TrustPostureMapper()

        result = mapper.map_verification_result(None)

        assert result.posture == TrustPosture.BLOCKED
        assert "No verification result" in result.reason

    def test_map_invalid_result_blocks(self):
        """Test that invalid verification result returns BLOCKED."""
        mapper = TrustPostureMapper()
        verification = MockVerificationResult(valid=False, reason="Denied")

        result = mapper.map_verification_result(verification)

        assert result.posture == TrustPosture.BLOCKED
        assert result.reason == "Denied"

    def test_map_valid_result_default_posture(self):
        """Test valid result returns default posture."""
        mapper = TrustPostureMapper(default_posture=TrustPosture.SUPERVISED)
        verification = MockVerificationResult(valid=True)

        result = mapper.map_verification_result(verification)

        assert result.posture == TrustPosture.SUPERVISED

    def test_map_high_trust_level_full_autonomy(self):
        """Test high trust level returns FULL_AUTONOMY."""
        mapper = TrustPostureMapper()
        verification = MockVerificationResult(
            valid=True,
            constraints={"trust_level": "high"},
        )

        result = mapper.map_verification_result(verification)

        assert result.posture == TrustPosture.FULL_AUTONOMY

    def test_map_full_trust_level_full_autonomy(self):
        """Test full trust level returns FULL_AUTONOMY."""
        mapper = TrustPostureMapper()
        verification = MockVerificationResult(
            valid=True,
            constraints={"trust_level": "full"},
        )

        result = mapper.map_verification_result(verification)

        assert result.posture == TrustPosture.FULL_AUTONOMY

    def test_map_approval_required_human_decides(self):
        """Test approval_required returns HUMAN_DECIDES."""
        mapper = TrustPostureMapper()
        verification = MockVerificationResult(
            valid=True,
            constraints={"approval_required": True},
        )

        result = mapper.map_verification_result(verification)

        assert result.posture == TrustPosture.HUMAN_DECIDES
        assert result.constraints.approval_required is True

    def test_map_human_in_loop_human_decides(self):
        """Test human_in_loop returns HUMAN_DECIDES."""
        mapper = TrustPostureMapper()
        verification = MockVerificationResult(
            valid=True,
            constraints={"human_in_loop": True},
        )

        result = mapper.map_verification_result(verification)

        assert result.posture == TrustPosture.HUMAN_DECIDES

    def test_map_audit_required_assisted(self):
        """Test audit_required with normal trust returns ASSISTED."""
        mapper = TrustPostureMapper()
        verification = MockVerificationResult(
            valid=True,
            constraints={"audit_required": True},
        )

        result = mapper.map_verification_result(verification)

        # With normal trust level (default), audit_required now returns ASSISTED
        assert result.posture == TrustPosture.ASSISTED
        assert "Assisted mode" in result.reason

    def test_map_sensitive_capability_supervised(self):
        """Test sensitive capability returns SUPERVISED."""
        mapper = TrustPostureMapper(
            sensitive_capabilities=["delete", "execute_code"],
        )
        verification = MockVerificationResult(valid=True)

        result = mapper.map_verification_result(
            verification,
            requested_capability="delete_records",
        )

        assert result.posture == TrustPosture.SUPERVISED
        assert result.constraints.audit_required is True

    def test_map_high_risk_tool_supervised(self):
        """Test high-risk tool returns SUPERVISED."""
        mapper = TrustPostureMapper(
            high_risk_tools=["bash_command", "delete_file"],
        )
        verification = MockVerificationResult(valid=True)

        result = mapper.map_verification_result(
            verification,
            requested_tool="bash_command",
        )

        assert result.posture == TrustPosture.SUPERVISED
        assert result.constraints.audit_required is True

    def test_is_sensitive_capability_detection(self):
        """Test sensitive capability detection."""
        mapper = TrustPostureMapper(
            sensitive_capabilities=["delete", "modify_config"],
        )

        assert mapper._is_sensitive_capability("delete_user") is True
        assert mapper._is_sensitive_capability("modify_config_file") is True
        assert mapper._is_sensitive_capability("read_file") is False
        assert mapper._is_sensitive_capability(None) is False

    def test_is_high_risk_tool_detection(self):
        """Test high-risk tool detection."""
        mapper = TrustPostureMapper(
            high_risk_tools=["http_delete", "write_file"],
        )

        assert mapper._is_high_risk_tool("http_delete_request") is True
        assert mapper._is_high_risk_tool("write_file_contents") is True
        assert mapper._is_high_risk_tool("http_get") is False
        assert mapper._is_high_risk_tool(None) is False

    def test_extract_verification_details(self):
        """Test extraction of verification details."""
        mapper = TrustPostureMapper()
        verification = MockVerificationResult(
            valid=True,
            agent_id="test-agent-001",
        )

        result = mapper.map_verification_result(verification)

        assert result.verification_details.get("agent_id") == "test-agent-001"


class TestMapToPosture:
    """Test simplified map_to_posture method."""

    def test_blocked_when_not_valid(self):
        """Test BLOCKED when is_valid is False."""
        mapper = TrustPostureMapper()

        result = mapper.map_to_posture(
            is_valid=False,
            reason="Access denied",
        )

        assert result.posture == TrustPosture.BLOCKED
        assert result.reason == "Access denied"

    def test_human_decides_when_approval_required(self):
        """Test HUMAN_DECIDES when approval_required."""
        mapper = TrustPostureMapper()

        result = mapper.map_to_posture(
            is_valid=True,
            approval_required=True,
        )

        assert result.posture == TrustPosture.HUMAN_DECIDES
        assert result.constraints.approval_required is True
        assert result.constraints.audit_required is True

    def test_assisted_when_audit_required(self):
        """Test ASSISTED when audit_required with normal trust level."""
        mapper = TrustPostureMapper()

        result = mapper.map_to_posture(
            is_valid=True,
            audit_required=True,
        )

        # With normal trust level (default), audit_required now returns ASSISTED
        assert result.posture == TrustPosture.ASSISTED
        assert result.constraints.audit_required is True

    def test_supervised_for_low_trust(self):
        """Test SUPERVISED for low trust level."""
        mapper = TrustPostureMapper()

        result = mapper.map_to_posture(
            is_valid=True,
            trust_level="low",
        )

        assert result.posture == TrustPosture.SUPERVISED

    def test_full_autonomy_for_high_trust(self):
        """Test FULL_AUTONOMY for high trust level."""
        mapper = TrustPostureMapper()

        result = mapper.map_to_posture(
            is_valid=True,
            trust_level="high",
        )

        assert result.posture == TrustPosture.FULL_AUTONOMY

    def test_default_posture(self):
        """Test default posture."""
        mapper = TrustPostureMapper(default_posture=TrustPosture.SUPERVISED)

        result = mapper.map_to_posture(
            is_valid=True,
            trust_level="normal",
        )

        assert result.posture == TrustPosture.SUPERVISED


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_map_verification_to_posture(self):
        """Test map_verification_to_posture function."""
        verification = MockVerificationResult(valid=True)

        result = map_verification_to_posture(verification)

        assert isinstance(result, PostureResult)
        assert result.posture != TrustPosture.BLOCKED

    def test_map_verification_to_posture_with_capability(self):
        """Test with capability filter."""
        verification = MockVerificationResult(valid=True)

        result = map_verification_to_posture(
            verification,
            capability="delete_records",
        )

        # Should be supervised due to "delete" being sensitive
        assert result.posture == TrustPosture.SUPERVISED

    def test_get_posture_for_action_blocked(self):
        """Test get_posture_for_action when not allowed."""
        posture = get_posture_for_action(is_allowed=False)

        assert posture == TrustPosture.BLOCKED

    def test_get_posture_for_action_human_decides(self):
        """Test get_posture_for_action with approval required."""
        posture = get_posture_for_action(
            is_allowed=True,
            requires_approval=True,
        )

        assert posture == TrustPosture.HUMAN_DECIDES

    def test_get_posture_for_action_assisted(self):
        """Test get_posture_for_action with audit required returns ASSISTED."""
        posture = get_posture_for_action(
            is_allowed=True,
            requires_audit=True,
        )

        # Now returns ASSISTED instead of SUPERVISED when audit is required
        assert posture == TrustPosture.ASSISTED

    def test_get_posture_for_action_full_autonomy(self):
        """Test get_posture_for_action with full access."""
        posture = get_posture_for_action(
            is_allowed=True,
            requires_audit=False,
            requires_approval=False,
        )

        assert posture == TrustPosture.FULL_AUTONOMY
