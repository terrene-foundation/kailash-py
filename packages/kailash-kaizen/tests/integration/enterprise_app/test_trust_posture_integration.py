"""
Integration Tests for Trust Posture Mapping (Tier 2)

Tests the trust posture system with real verification flows.
Part of TODO-204 Enterprise-App Streaming Integration.

NO MOCKING: Uses real verification and posture mapping.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest
from kailash.trust.posture.postures import (
    PostureConstraints,
    PostureResult,
    TrustPosture,
    TrustPostureMapper,
    get_posture_for_action,
    map_verification_to_posture,
)


@dataclass
class VerificationResult:
    """Real verification result for testing."""

    valid: bool
    reason: str = ""
    constraints: Optional[Dict[str, Any]] = None
    agent_id: str = "test-agent"
    action: str = "execute"
    trust_chain_id: str = "chain-001"
    timestamp: str = "2024-01-01T00:00:00Z"

    def __post_init__(self):
        if self.constraints is None:
            self.constraints = {}


class TestTrustPostureMapperIntegration:
    """Integration tests for TrustPostureMapper."""

    def test_full_autonomy_flow(self):
        """Test full autonomy posture determination."""
        mapper = TrustPostureMapper()

        verification = VerificationResult(
            valid=True,
            reason="Trusted agent",
            constraints={"trust_level": "high"},
            agent_id="trusted-agent-001",
        )

        result = mapper.map_verification_result(verification)

        assert result.posture == TrustPosture.AUTONOMOUS
        assert result.verification_details["agent_id"] == "trusted-agent-001"

    def test_supervised_flow_for_sensitive_capability(self):
        """Test supervised posture for sensitive capabilities."""
        mapper = TrustPostureMapper(
            sensitive_capabilities=["delete", "modify", "execute"]
        )

        verification = VerificationResult(
            valid=True,
            reason="Allowed with monitoring",
        )

        result = mapper.map_verification_result(
            verification,
            requested_capability="delete_records",
        )

        assert result.posture == TrustPosture.SUPERVISED
        assert result.constraints.audit_required is True

    def test_supervised_flow_for_high_risk_tool(self):
        """Test supervised posture for high-risk tools."""
        mapper = TrustPostureMapper(
            high_risk_tools=["bash_command", "delete_file", "http_delete"]
        )

        verification = VerificationResult(
            valid=True,
            reason="Allowed with monitoring",
        )

        result = mapper.map_verification_result(
            verification,
            requested_tool="bash_command",
        )

        assert result.posture == TrustPosture.SUPERVISED
        assert result.constraints.audit_required is True

    def test_human_decides_flow(self):
        """Test human decides posture."""
        mapper = TrustPostureMapper()

        verification = VerificationResult(
            valid=True,
            reason="Requires approval",
            constraints={"approval_required": True},
        )

        result = mapper.map_verification_result(verification)

        # approval_required → TOOL (autonomy_level=2): human and agent co-plan,
        # agent executes approved plans. See TrustPostureMapper.map_verification_result.
        assert result.posture == TrustPosture.TOOL
        assert result.constraints.approval_required is True

    def test_blocked_flow(self):
        """Test blocked posture for invalid verification."""
        mapper = TrustPostureMapper()

        verification = VerificationResult(
            valid=False,
            reason="Access denied by policy",
        )

        result = mapper.map_verification_result(verification)

        assert result.posture == TrustPosture.PSEUDO
        assert result.reason == "Access denied by policy"

    def test_posture_with_complex_constraints(self):
        """Test posture with complex constraints."""
        mapper = TrustPostureMapper()

        verification = VerificationResult(
            valid=True,
            reason="Limited access",
            constraints={
                "trust_level": "normal",
                "audit_required": True,
                "max_actions": 10,
                "allowed_tools": ["search", "read"],
            },
        )

        result = mapper.map_verification_result(verification)

        # With trust_level="normal" and audit_required=True (no approval),
        # mapper returns DELEGATING (audit logging, real-time monitoring, no blocking).
        assert result.posture == TrustPosture.DELEGATING
        assert result.constraints.audit_required is True
        assert "max_actions" in result.constraints.metadata

    def test_posture_escalation_chain(self):
        """Test posture changes through trust levels."""
        mapper = TrustPostureMapper()

        # Start with no trust
        no_trust = VerificationResult(valid=False)
        result1 = mapper.map_verification_result(no_trust)
        assert result1.posture == TrustPosture.PSEUDO

        # Low trust
        low_trust = VerificationResult(
            valid=True,
            constraints={"trust_level": "low"},
        )
        result2 = mapper.map_verification_result(low_trust)
        assert result2.posture == TrustPosture.SUPERVISED

        # Normal trust (default)
        normal_trust = VerificationResult(
            valid=True,
            constraints={"trust_level": "normal"},
        )
        result3 = mapper.map_verification_result(normal_trust)
        assert result3.posture == mapper._default_posture

        # High trust
        high_trust = VerificationResult(
            valid=True,
            constraints={"trust_level": "high"},
        )
        result4 = mapper.map_verification_result(high_trust)
        assert result4.posture == TrustPosture.AUTONOMOUS


class TestPostureConstraintsIntegration:
    """Integration tests for posture constraints."""

    def test_constraints_serialization(self):
        """Test constraints complete serialization."""
        constraints = PostureConstraints(
            audit_required=True,
            approval_required=True,
            log_level="warning",
            allowed_capabilities=["read", "search"],
            blocked_capabilities=["delete", "write"],
            max_actions_before_review=5,
            require_human_approval_for=["delete_account", "transfer_funds"],
            metadata={"policy_id": "policy-001", "version": "1.0"},
        )

        data = constraints.to_dict()

        assert data["audit_required"] is True
        assert data["approval_required"] is True
        assert data["log_level"] == "warning"
        assert "read" in data["allowed_capabilities"]
        assert "delete" in data["blocked_capabilities"]
        assert data["max_actions_before_review"] == 5
        assert "delete_account" in data["require_human_approval_for"]
        assert data["metadata"]["policy_id"] == "policy-001"

    def test_posture_result_full_serialization(self):
        """Test PostureResult complete serialization."""
        constraints = PostureConstraints(
            audit_required=True,
            require_human_approval_for=["sensitive_action"],
        )

        # "Sensitive action requires approval" maps to TOOL posture —
        # human and agent co-plan, human approves each execution.
        result = PostureResult(
            posture=TrustPosture.TOOL,
            constraints=constraints,
            reason="Sensitive action requires approval",
            verification_details={
                "agent_id": "agent-001",
                "action": "execute",
                "trust_chain_id": "chain-001",
            },
        )

        data = result.to_dict()

        assert data["posture"] == "tool"
        assert data["constraints"]["audit_required"] is True
        assert data["reason"] == "Sensitive action requires approval"
        assert data["verification_details"]["agent_id"] == "agent-001"


class TestConvenienceFunctionsIntegration:
    """Integration tests for convenience functions."""

    def test_map_verification_to_posture_complete(self):
        """Test convenience function with full verification."""
        verification = VerificationResult(
            valid=True,
            reason="Full access granted",
            constraints={"trust_level": "full"},
            agent_id="full-agent-001",
        )

        result = map_verification_to_posture(verification)

        assert result.posture == TrustPosture.AUTONOMOUS

    def test_map_verification_with_capability(self):
        """Test with capability filter."""
        verification = VerificationResult(
            valid=True,
            constraints={},
        )

        # With delete capability - should be supervised
        result = map_verification_to_posture(
            verification,
            capability="delete_records",
        )

        assert result.posture == TrustPosture.SUPERVISED

    def test_map_verification_with_tool(self):
        """Test with tool filter."""
        verification = VerificationResult(
            valid=True,
            constraints={},
        )

        # With high-risk tool - should be supervised
        result = map_verification_to_posture(
            verification,
            tool="bash_command",
        )

        assert result.posture == TrustPosture.SUPERVISED

    def test_get_posture_for_action_all_cases(self):
        """Test get_posture_for_action for all cases."""
        # Blocked: is_allowed=False → PSEUDO (lowest autonomy)
        assert get_posture_for_action(is_allowed=False) == TrustPosture.PSEUDO

        # Human decides: approval required → TOOL (agent proposes, human approves)
        assert (
            get_posture_for_action(
                is_allowed=True,
                requires_approval=True,
            )
            == TrustPosture.TOOL
        )

        # Audit required: → DELEGATING (agent executes, human monitors real-time)
        assert (
            get_posture_for_action(
                is_allowed=True,
                requires_audit=True,
            )
            == TrustPosture.DELEGATING
        )

        # Full autonomy: no audit, no approval → AUTONOMOUS
        assert (
            get_posture_for_action(
                is_allowed=True,
                requires_audit=False,
                requires_approval=False,
            )
            == TrustPosture.AUTONOMOUS
        )


class TestMapToPostureIntegration:
    """Integration tests for simplified posture mapping."""

    def test_map_to_posture_all_levels(self):
        """Test map_to_posture for all trust levels."""
        mapper = TrustPostureMapper()

        # None trust
        result_none = mapper.map_to_posture(
            is_valid=True,
            trust_level="none",
        )
        assert result_none.posture == TrustPosture.SUPERVISED

        # Low trust
        result_low = mapper.map_to_posture(
            is_valid=True,
            trust_level="low",
        )
        assert result_low.posture == TrustPosture.SUPERVISED

        # Normal trust
        result_normal = mapper.map_to_posture(
            is_valid=True,
            trust_level="normal",
        )
        assert result_normal.posture == mapper._default_posture

        # High trust
        result_high = mapper.map_to_posture(
            is_valid=True,
            trust_level="high",
        )
        assert result_high.posture == TrustPosture.AUTONOMOUS

        # Full trust
        result_full = mapper.map_to_posture(
            is_valid=True,
            trust_level="full",
        )
        assert result_full.posture == TrustPosture.AUTONOMOUS

    def test_map_to_posture_with_reason(self):
        """Test custom reason propagation."""
        mapper = TrustPostureMapper()

        result = mapper.map_to_posture(
            is_valid=True,
            trust_level="high",
            reason="Custom reason for high trust",
        )

        assert result.posture == TrustPosture.AUTONOMOUS
        assert result.reason == "Custom reason for high trust"


class TestPostureIntegrationScenarios:
    """Real-world integration scenarios for posture system."""

    def test_enterprise_policy_scenario(self):
        """Test enterprise policy with multiple constraints."""
        mapper = TrustPostureMapper(
            sensitive_capabilities=[
                "financial_transaction",
                "data_export",
                "user_deletion",
            ],
            high_risk_tools=[
                "database_write",
                "file_delete",
                "external_api_post",
            ],
        )

        # Regular read operation
        read_verification = VerificationResult(
            valid=True,
            constraints={"trust_level": "normal"},
        )
        read_result = mapper.map_verification_result(
            read_verification,
            requested_capability="data_read",
        )
        assert read_result.posture == TrustPosture.SUPERVISED

        # Financial transaction
        finance_verification = VerificationResult(
            valid=True,
            constraints={"trust_level": "high"},
        )
        finance_result = mapper.map_verification_result(
            finance_verification,
            requested_capability="financial_transaction",
        )
        assert finance_result.posture == TrustPosture.SUPERVISED  # Sensitive overrides

        # Database write
        db_verification = VerificationResult(
            valid=True,
            constraints={"trust_level": "high"},
        )
        db_result = mapper.map_verification_result(
            db_verification,
            requested_tool="database_write",
        )
        assert db_result.posture == TrustPosture.SUPERVISED  # High-risk tool

    def test_human_in_loop_workflow(self):
        """Test human-in-loop workflow scenario."""
        mapper = TrustPostureMapper()

        # Action requires human approval
        verification = VerificationResult(
            valid=True,
            constraints={
                "human_in_loop": True,
                "approval_workflow": "manager_approval",
            },
        )

        result = mapper.map_verification_result(verification)

        # human_in_loop=True takes the approval_required branch → TOOL.
        assert result.posture == TrustPosture.TOOL
        assert "approval_workflow" in result.constraints.metadata

    def test_audit_compliance_scenario(self):
        """Test audit compliance scenario."""
        mapper = TrustPostureMapper()

        # Audit required for compliance
        verification = VerificationResult(
            valid=True,
            constraints={
                "audit_required": True,
                "compliance_policy": "SOC2",
                "retention_days": 365,
            },
        )

        result = mapper.map_verification_result(verification)

        # With audit_required=True and default trust_level (normal),
        # mapper returns DELEGATING (real-time monitoring, no blocking).
        assert result.posture == TrustPosture.DELEGATING
        assert result.constraints.audit_required is True
        assert "compliance_policy" in result.constraints.metadata
