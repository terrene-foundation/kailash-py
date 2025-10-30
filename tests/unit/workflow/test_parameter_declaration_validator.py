"""Test Parameter Declaration Validator - addresses gold standard issue #2."""

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.validation import (
    IssueSeverity,
    ParameterDeclarationValidator,
    ValidationIssue,
)


class EmptyParametersNode(Node):
    """Node with empty parameter declarations - triggers PAR001."""

    def get_parameters(self):
        return {}  # CRITICAL: Empty parameters but workflow will provide config

    def run(self, **kwargs):
        return {"result": "no_params_received"}


class MissingTypeParameterNode(Node):
    """Node with missing type definitions - triggers PAR003."""

    def get_parameters(self):
        # Create a dict with an object that looks like NodeParameter but is missing type
        from types import SimpleNamespace

        # Create a fake parameter that has name and required but no type
        fake_param = SimpleNamespace()
        fake_param.name = "bad_param"
        fake_param.required = True
        fake_param.default = None  # Add default to prevent early validation errors
        fake_param.description = "Test parameter without type"
        # Intentionally missing: type attribute

        return {
            "good_param": NodeParameter(name="good_param", type=str, required=True),
            "bad_param": fake_param,  # Missing type attribute!
        }

    def run(self, **kwargs):
        return {"result": "mixed_params"}


class ProperParametersNode(Node):
    """Node with correct parameter declarations."""

    def get_parameters(self):
        return {
            "input_text": NodeParameter(name="input_text", type=str, required=True),
            "count": NodeParameter(name="count", type=int, required=False, default=1),
        }

    def run(self, input_text, count=1):
        return {"result": f"{input_text} * {count}"}


class BrokenGetParametersNode(Node):
    """Node with broken get_parameters() method - triggers PAR000."""

    def __init__(self):
        # Override the base class initialization to avoid calling get_parameters()
        # during init, so we can test the validation behavior separately
        self.node_id = "test_node"
        # Use _node_metadata directly since metadata is now a property
        from kailash.nodes.base import NodeMetadata

        self._node_metadata = NodeMetadata(
            name="BrokenNode", description="", version="1.0.0"
        )
        self._cached_params = None
        self.config = {}  # Add config to avoid AttributeError
        # Don't call super().__init__() to avoid parameter validation during construction

    def get_parameters(self):
        # Always raise error to test PAR000 validation
        raise ValueError("Intentionally broken for testing")

    def run(self, **kwargs):
        return {"result": "broken"}


class TestParameterDeclarationValidator:
    """Test Parameter Declaration Validator functionality."""

    def setup_method(self):
        """Set up validator for each test."""
        self.validator = ParameterDeclarationValidator()

    def test_empty_parameters_with_workflow_config(self):
        """Test PAR001: Node declares no parameters but workflow provides config."""
        node = EmptyParametersNode()
        workflow_params = {"input_data": "test", "count": 5}

        issues = self.validator.validate_node_parameters(node, workflow_params)

        assert len(issues) == 1
        issue = issues[0]
        # Changed to WARNING for backwards compatibility (build time vs runtime validation)
        assert issue.severity == IssueSeverity.WARNING
        assert issue.code == "PAR001"
        assert "declares no parameters but workflow provides" in issue.message
        assert "['input_data', 'count']" in issue.message
        assert "SDK only injects explicitly declared parameters" in issue.suggestion
        assert (
            "enterprise-parameter-passing-gold-standard.md" in issue.documentation_link
        )

    def test_empty_parameters_no_workflow_config(self):
        """Test that empty parameters with no workflow config is fine."""
        node = EmptyParametersNode()
        workflow_params = {}

        issues = self.validator.validate_node_parameters(node, workflow_params)

        assert len(issues) == 0

    def test_undeclared_parameters_warning(self):
        """Test PAR002: Workflow provides parameters not declared by node."""
        node = ProperParametersNode()
        workflow_params = {
            "input_text": "hello",
            "count": 3,
            "extra_param": "ignored",  # Not declared
            "another_extra": "also_ignored",  # Not declared
        }

        issues = self.validator.validate_node_parameters(node, workflow_params)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == IssueSeverity.WARNING
        assert issue.code == "PAR002"
        assert (
            "not declared in get_parameters() - will be ignored by SDK" in issue.message
        )
        assert "extra_param" in issue.message
        assert "another_extra" in issue.message

    def test_missing_type_definition(self):
        """Test PAR003: Parameter missing type definition."""
        node = MissingTypeParameterNode()
        workflow_params = {"good_param": "test", "bad_param": "also_test"}

        issues = self.validator.validate_node_parameters(node, workflow_params)

        # Should have one warning for missing type
        type_issues = [issue for issue in issues if issue.code == "PAR003"]
        assert len(type_issues) == 1

        issue = type_issues[0]
        assert issue.severity == IssueSeverity.WARNING
        assert issue.code == "PAR003"
        assert "missing type definition" in issue.message
        assert "bad_param" in issue.message
        assert "NodeParameter(name='bad_param', type=str" in issue.suggestion

    def test_missing_required_parameter(self):
        """Test PAR004: Required parameter not provided by workflow."""
        node = ProperParametersNode()
        workflow_params = {"count": 3}  # Missing required input_text

        issues = self.validator.validate_node_parameters(node, workflow_params)

        error_issues = [issue for issue in issues if issue.code == "PAR004"]
        assert len(error_issues) == 1

        issue = error_issues[0]
        # Changed to WARNING for backwards compatibility (build time vs runtime validation)
        assert issue.severity == IssueSeverity.WARNING
        assert issue.code == "PAR004"
        assert (
            "Required parameter 'input_text' not provided by workflow" in issue.message
        )
        assert "provide 'input_text' in workflow configuration" in issue.suggestion

    def test_broken_get_parameters_method(self):
        """Test PAR000: get_parameters() method fails."""
        node = BrokenGetParametersNode()
        workflow_params = {"any": "config"}

        issues = self.validator.validate_node_parameters(node, workflow_params)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == IssueSeverity.ERROR
        assert issue.code == "PAR000"
        assert "get_parameters() failed" in issue.message
        assert "Intentionally broken for testing" in issue.message
        assert "Fix get_parameters() method implementation" in issue.suggestion

    def test_valid_parameters_no_issues(self):
        """Test that properly declared parameters generate no issues."""
        node = ProperParametersNode()
        workflow_params = {"input_text": "hello", "count": 2}

        issues = self.validator.validate_node_parameters(node, workflow_params)

        assert len(issues) == 0

    def test_optional_parameter_not_provided(self):
        """Test that optional parameters can be omitted without error."""
        node = ProperParametersNode()
        workflow_params = {"input_text": "hello"}  # count is optional

        issues = self.validator.validate_node_parameters(node, workflow_params)

        assert len(issues) == 0

    def test_multiple_issues_in_single_node(self):
        """Test that multiple issues are detected for a single node."""
        node = MissingTypeParameterNode()
        workflow_params = {
            "good_param": "test",
            # bad_param is missing (required with no default)
            "extra_param": "ignored",  # Not declared
        }

        issues = self.validator.validate_node_parameters(node, workflow_params)

        # Should have multiple issues
        assert len(issues) >= 2

        # Check that we get the undeclared parameter warning
        undeclared_issues = [issue for issue in issues if issue.code == "PAR002"]
        assert len(undeclared_issues) == 1

        # Check that we get the missing type warning
        type_issues = [issue for issue in issues if issue.code == "PAR003"]
        assert len(type_issues) == 1

    def test_validation_code_property(self):
        """Test that validator has correct validation code."""
        assert self.validator.validation_code == "PAR"

    def test_issue_categories(self):
        """Test that all generated issues have correct categories."""
        node = EmptyParametersNode()
        workflow_params = {"test": "param"}

        issues = self.validator.validate_node_parameters(node, workflow_params)

        for issue in issues:
            assert issue.category == "parameter_declaration"
