"""Integration tests for Parameter Declaration Validator with WorkflowBuilder."""

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.validation import IssueSeverity, ValidationIssue


class ParameterValidationNode(Node):
    """Test node with proper parameter declarations."""

    def get_parameters(self):
        return {
            "input_data": NodeParameter(name="input_data", type=str, required=True),
            "count": NodeParameter(name="count", type=int, required=False, default=1),
        }

    def run(self, input_data, count=1):
        return {"result": f"{input_data} processed {count} times"}


class EmptyParameterNode(Node):
    """Test node with empty parameters - should trigger PAR001."""

    def get_parameters(self):
        return {}

    def run(self, **kwargs):
        return {"result": "no parameters"}


class TestParameterValidationIntegration:
    """Test Parameter Declaration Validator integration with WorkflowBuilder."""

    def test_workflow_builder_integration_with_parameter_issues(self, caplog):
        """Test that WorkflowBuilder detects parameter declaration issues during build."""
        import logging

        workflow = WorkflowBuilder()

        # Add node with empty parameters but provide workflow config
        workflow.add_node(
            EmptyParameterNode, "empty_node", parameters={"input": "test", "count": 5}
        )

        # Build workflow - should log warning for parameter validation issues
        with caplog.at_level(logging.WARNING):
            workflow.build()

        # Should warn about empty parameter declaration with provided workflow config
        assert any(
            "declares no parameters but workflow provides" in record.message
            for record in caplog.records
        )

    def test_workflow_builder_integration_with_valid_parameters(self):
        """Test that WorkflowBuilder works normally with properly declared parameters."""
        workflow = WorkflowBuilder()

        # Add node with proper parameter declarations using individual parameters
        workflow.add_node(
            ParameterValidationNode, "test_node", input_data="hello", count=3
        )

        # Build workflow - should work without issues
        built_workflow = workflow.build()

        assert built_workflow is not None
        assert len(built_workflow.nodes) == 1

    def test_workflow_builder_integration_with_undeclared_parameters(self):
        """Test detection of parameters provided by workflow but not declared by node."""
        workflow = WorkflowBuilder()

        # Add node with some parameters declared, but workflow provides extra ones
        workflow.add_node(
            ParameterValidationNode,
            "test_node",
            parameters={
                "input_data": "hello",  # Declared
                "count": 2,  # Declared
                "extra_param": "ignored",  # Not declared - should trigger PAR002
                "another_extra": "also_ignored",  # Not declared - should trigger PAR002
            },
        )

        # Build workflow
        built_workflow = workflow.build()

        # Should build successfully but validation should detect undeclared parameters
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 1

    def test_workflow_builder_integration_with_missing_required_parameters(self):
        """Test detection of required parameters not provided by workflow."""
        workflow = WorkflowBuilder()

        # Add node but don't provide required parameter
        workflow.add_node(
            ParameterValidationNode, "test_node", parameters={"count": 3}
        )  # Missing required "input_data"

        # Build workflow
        built_workflow = workflow.build()

        # Should build successfully but validation should detect missing required parameter
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 1

    def test_multiple_nodes_with_different_parameter_issues(self):
        """Test validation across multiple nodes with different parameter issues."""
        workflow = WorkflowBuilder()

        # Node 1: Proper parameters
        workflow.add_node(
            ParameterValidationNode,
            "good_node",
            parameters={"input_data": "test", "count": 2},
        )

        # Node 2: Empty parameters but workflow provides config
        workflow.add_node(
            EmptyParameterNode, "bad_node", parameters={"unexpected": "param"}
        )

        # Node 3: Missing required parameters
        workflow.add_node(
            ParameterValidationNode, "incomplete_node", parameters={"count": 1}
        )  # Missing required input_data

        # Build workflow
        built_workflow = workflow.build()

        # Should build successfully but validation should detect multiple issues
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3
