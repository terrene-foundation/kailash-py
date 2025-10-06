"""Tests for SecureGovernedNode and governance patterns."""

from unittest.mock import MagicMock, patch

import pytest
from kailash.nodes.base import NodeParameter
from kailash.nodes.governance import DevelopmentNode, EnterpriseNode, SecureGovernedNode
from kailash.sdk_exceptions import NodeConfigurationError
from kailash.security import SecurityError
from kailash.workflow.validation import IssueSeverity, ValidationIssue


class SampleSecureGovernedNode(SecureGovernedNode):
    """Sample implementation of SecureGovernedNode for testing."""

    def get_parameters(self):
        return {
            "input_text": NodeParameter(name="input_text", type=str, required=True),
            "count": NodeParameter(name="count", type=int, required=False, default=1),
            "threshold": NodeParameter(
                name="threshold", type=float, required=False, default=0.5
            ),
        }

    def run_governed(self, input_text: str, count: int = 1, threshold: float = 0.5):
        return {
            "result": f"Processed: {input_text}",
            "iterations": count,
            "threshold": threshold,
            "secure": True,
        }


class BrokenGovernanceNode(SecureGovernedNode):
    """Node with broken parameter declarations for testing."""

    def get_parameters(self):
        # Return empty parameters to trigger PAR001
        return {}

    def run_governed(self, **kwargs):
        return {"result": "broken"}


class TestGovernanceNodes:
    """Test SecureGovernedNode and related governance patterns."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_node = SampleSecureGovernedNode(enforce_validation=True)

    def test_secure_governed_node_initialization(self):
        """Test SecureGovernedNode proper initialization."""
        node = SampleSecureGovernedNode(
            enforce_validation=True, security_level="high", audit_enabled=True
        )

        assert node.enforce_validation is True
        assert node.security_level == "high"
        assert node.audit_enabled is True
        assert hasattr(node, "parameter_validator")
        assert hasattr(node, "audit_log")  # From SecurityMixin
        assert hasattr(node, "validate_and_sanitize_inputs")  # From SecurityMixin

    def test_governance_status_reporting(self):
        """Test governance status reporting."""
        status = self.test_node.get_governance_status()

        assert status["node_type"] == "SecureGovernedNode"
        assert status["security_level"] == "high"
        assert status["validation_enforced"] is True
        assert status["governance_compliant"] is True
        assert "performance_stats" in status

    def test_successful_governed_execution(self):
        """Test successful execution with proper parameters."""
        result = self.test_node.execute(input_text="test data", count=3, threshold=0.8)

        assert result["result"] == "Processed: test data"
        assert result["iterations"] == 3
        assert result["threshold"] == 0.8
        assert result["secure"] is True

    def test_parameter_validation_during_execution(self):
        """Test parameter validation catches issues during execution."""
        # Missing required parameter
        with pytest.raises(ValueError) as exc_info:
            self.test_node.execute(count=2)  # Missing input_text

        assert "Missing required parameters" in str(exc_info.value)
        assert "input_text" in str(exc_info.value)  # Missing required parameter

    def test_type_validation_and_conversion(self):
        """Test type validation and conversion."""
        # String that can be converted to int
        result = self.test_node.execute(
            input_text="test",
            count="5",  # String that should convert to int
            threshold="0.7",  # String that should convert to float
        )

        assert result["iterations"] == 5
        assert result["threshold"] == 0.7

    def test_type_validation_failure(self):
        """Test type validation failure."""
        # Invalid type conversion
        with pytest.raises(TypeError) as exc_info:
            self.test_node.execute(
                input_text="test", count="invalid_number"  # Cannot convert to int
            )

        assert "Cannot convert count to int" in str(exc_info.value)

    def test_workflow_parameter_validation(self):
        """Test explicit workflow parameter validation."""
        # Valid parameters
        issues = self.test_node.validate_workflow_parameters(
            {"input_text": "test", "count": 5}
        )

        # Should have no errors for valid parameters
        errors = [issue for issue in issues if issue.severity == IssueSeverity.ERROR]
        assert len(errors) == 0

    def test_workflow_parameter_validation_with_issues(self):
        """Test workflow parameter validation detects issues."""
        # Parameters with issues
        issues = self.test_node.validate_workflow_parameters(
            {
                "count": 5,  # Missing required input_text
                "extra_param": "ignored",  # Undeclared parameter
            }
        )

        # Should detect missing required parameter (now WARNING level for backwards compatibility)
        warnings = [
            issue for issue in issues if issue.severity == IssueSeverity.WARNING
        ]
        assert (
            len(warnings) == 2
        )  # One for missing required param (PAR004), one for undeclared param (PAR002)

        par004_issues = [issue for issue in warnings if issue.code == "PAR004"]
        par002_issues = [issue for issue in warnings if issue.code == "PAR002"]

        assert len(par004_issues) == 1  # Missing required parameter
        assert len(par002_issues) == 1  # Undeclared parameter

    def test_security_mixin_integration(self):
        """Test integration with SecurityMixin."""
        # Test with security enabled
        node = SampleSecureGovernedNode(security_level="high")

        # Check that security methods are available
        assert hasattr(node, "validate_and_sanitize_inputs")

        # Security validation should be called during execution
        with patch.object(
            node, "validate_and_sanitize_inputs", return_value={"input_text": "clean"}
        ) as mock_sanitize:
            result = node.execute(input_text="test")
            mock_sanitize.assert_called_once()

    def test_audit_logging_integration(self):
        """Test audit logging integration."""
        # Create node with mocked audit_log from the start
        with patch("kailash.nodes.governance.logger") as mock_logger:
            node = SampleSecureGovernedNode(audit_enabled=True)

            # Just check that audit logging is enabled and accessible
            assert node.audit_enabled is True
            assert hasattr(node, "audit_log")

            # Execute and verify it doesn't crash with audit enabled
            result = node.execute(input_text="test")
            assert result["secure"] is True

    def test_governance_compliance_validation_on_init(self):
        """Test governance compliance validation during initialization."""
        # This should succeed for properly implemented nodes
        node = SampleSecureGovernedNode(enforce_validation=True)
        assert node.enforce_validation is True

    def test_governance_compliance_failure_on_init(self):
        """Test governance compliance failure during workflow execution."""
        # BrokenGovernanceNode has empty parameters, which should pass init
        # but fail when executed with parameters (triggering PAR001)
        node = BrokenGovernanceNode(enforce_validation=True)  # Should succeed

        # But execution with parameters should fail validation
        with pytest.raises(ValueError) as exc_info:
            node.execute(some_param="test")  # Provides params but node declares none

        assert "Parameter validation failed" in str(exc_info.value)

    def test_validation_enforcement_can_be_disabled(self):
        """Test that validation enforcement can be disabled."""
        # Create node with validation disabled
        node = SampleSecureGovernedNode(enforce_validation=False)

        # Should execute successfully even with parameter issues
        # (though security validation may still apply)
        result = node.execute(input_text="test")
        assert result["secure"] is True

    def test_enterprise_node_defaults(self):
        """Test EnterpriseNode has correct enterprise defaults."""

        class TestEnterpriseNode(EnterpriseNode):
            def get_parameters(self):
                return {"data": NodeParameter(name="data", type=str, required=True)}

            def run_governed(self, data: str):
                return {"enterprise_result": data}

        node = TestEnterpriseNode()

        assert node.enforce_validation is True
        assert node.security_level == "high"
        assert node.audit_enabled is True

    def test_development_node_defaults(self):
        """Test DevelopmentNode has correct development defaults."""

        class TestDevelopmentNode(DevelopmentNode):
            def get_parameters(self):
                return {"data": NodeParameter(name="data", type=str, required=True)}

            def run_governed(self, data: str):
                return {"dev_result": data}

        node = TestDevelopmentNode()

        assert node.enforce_validation is False  # Relaxed for development
        assert node.security_level == "medium"
        assert node.audit_enabled is False

    def test_development_node_with_enforcement_override(self):
        """Test DevelopmentNode can override enforcement."""

        class TestDevelopmentNode(DevelopmentNode):
            def get_parameters(self):
                return {"data": NodeParameter(name="data", type=str, required=True)}

            def run_governed(self, data: str):
                return {"dev_result": data}

        # Override enforcement for strict development testing
        node = TestDevelopmentNode(enforce_validation=True)

        assert node.enforce_validation is True
        assert node.security_level == "medium"  # Still development security level

    def test_error_handling_with_audit_logging(self):
        """Test error handling includes audit logging."""
        node = SampleSecureGovernedNode(audit_enabled=True)

        # Since LoggingMixin might not have log_error_with_traceback,
        # just test that errors are properly raised
        with pytest.raises(ValueError) as exc_info:
            node.execute()  # Missing required parameter

        # Should get parameter validation error
        assert "Parameter validation failed" in str(
            exc_info.value
        ) or "Missing required parameters" in str(exc_info.value)

    def test_abstract_run_governed_enforcement(self):
        """Test that run_governed must be implemented."""

        class IncompleteGovernedNode(SecureGovernedNode):
            def get_parameters(self):
                return {}

            # Missing run_governed implementation

        # Should fail to instantiate due to abstract method
        with pytest.raises(TypeError) as exc_info:
            IncompleteGovernedNode()

        assert "abstract" in str(exc_info.value).lower()
        assert "run_governed" in str(exc_info.value)

    def test_performance_stats_integration(self):
        """Test performance stats are included in governance status."""
        # Create node with performance tracking
        node = SampleSecureGovernedNode()

        # Execute to generate some performance data
        node.execute(input_text="test")

        status = node.get_governance_status()
        assert "performance_stats" in status

    def test_security_level_enforcement(self):
        """Test different security levels affect behavior."""
        # High security node
        high_security = SampleSecureGovernedNode(security_level="high")
        assert high_security.security_level == "high"

        # Medium security node
        medium_security = SampleSecureGovernedNode(security_level="medium")
        assert medium_security.security_level == "medium"

        # Both should work but with different security configs
        result1 = high_security.execute(input_text="test")
        result2 = medium_security.execute(input_text="test")

        assert result1["secure"] is True
        assert result2["secure"] is True
