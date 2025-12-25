"""
Integration tests for parameter validation in production scenarios.

Tests the parameter declaration validator in realistic production workflows.
"""

import warnings
from typing import Any, Dict

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import WorkflowValidationError
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.validation import (
    IssueSeverity,
    ParameterDeclarationValidator,
    ValidationIssue,
)


class TestParameterValidationProduction:
    """Test parameter validation in production scenarios."""

    def test_empty_parameters_detection(self):
        """Test detection of nodes with empty parameter declarations."""
        workflow = WorkflowBuilder()

        # Create node with empty parameters (common mistake)
        class EmptyParamsNode(Node):
            def get_parameters(self):
                return {}  # Empty - will drop all parameters!

            def run(self, **kwargs):
                # This will never receive parameters
                return {"result": kwargs.get("data", "no data")}

        # Add node with parameters that will be silently dropped
        workflow.add_node(EmptyParamsNode, "processor", {"data": [1, 2, 3]})

        # Validation should fail
        with pytest.raises(WorkflowValidationError) as exc_info:
            workflow.build()

        error_message = str(exc_info.value)
        assert "declares no parameters but workflow provides ['data']" in error_message
        assert "processor" in error_message

    def test_undeclared_parameters_detection(self):
        """Test detection of undeclared parameters being passed."""
        workflow = WorkflowBuilder()

        # Node that declares some but not all parameters
        class PartialParamsNode(Node):
            def get_parameters(self):
                return {
                    "input_data": NodeParameter(
                        name="input_data",
                        type=list,
                        required=True,
                        description="Input data",
                    )
                    # Missing: config, threshold
                }

            def run(self, **kwargs):
                data = kwargs.get("input_data", [])
                # These will be None - parameters not declared!
                config = kwargs.get("config", {})
                threshold = kwargs.get("threshold", 0.5)
                return {"result": len(data)}

        # Try to pass undeclared parameters
        workflow.add_node(
            PartialParamsNode,
            "processor",
            {
                "input_data": [1, 2, 3],
                "config": {"mode": "fast"},  # Not declared!
                "threshold": 0.8,  # Not declared!
            },
        )

        # Should fail validation
        with pytest.raises(WorkflowValidationError) as exc_info:
            workflow.build()

        error_message = str(exc_info.value)
        assert "undeclared parameters" in error_message.lower()
        assert "config" in error_message
        assert "threshold" in error_message

    def test_missing_required_parameters(self):
        """Test detection of missing required parameters."""
        workflow = WorkflowBuilder()

        # Node with required parameters
        class RequiredParamsNode(Node):
            def get_parameters(self):
                return {
                    "user_id": NodeParameter(
                        name="user_id",
                        type=str,
                        required=True,
                        description="User identifier",
                    ),
                    "action": NodeParameter(
                        name="action",
                        type=str,
                        required=True,
                        description="Action to perform",
                    ),
                    "options": NodeParameter(
                        name="options",
                        type=dict,
                        required=False,
                        default={},
                        description="Optional settings",
                    ),
                }

            def run(self, **kwargs):
                return {
                    "result": f"User {kwargs['user_id']} performed {kwargs['action']}"
                }

        # Add node without required parameters
        workflow.add_node(
            RequiredParamsNode,
            "processor",
            {
                "user_id": "user123"
                # Missing required 'action' parameter!
            },
        )

        # Should fail validation
        with pytest.raises(WorkflowValidationError) as exc_info:
            workflow.build()

        error_message = str(exc_info.value)
        assert "Required parameter 'action' not provided" in error_message

    def test_parameter_type_validation(self):
        """Test parameter type information validation."""
        validator = ParameterDeclarationValidator()

        # Node missing type information
        class NoTypeNode(Node):
            def get_parameters(self):
                return {
                    "data": NodeParameter(
                        name="data",
                        # Missing type!
                        required=True,
                        description="Input data",
                    )
                }

            def run(self, **kwargs):
                return {"result": kwargs.get("data")}

        node = NoTypeNode()
        issues = validator.validate_node_parameters(node, {"data": [1, 2, 3]})

        # Should have warning about missing type
        type_issues = [i for i in issues if i.code == "PAR003"]
        assert len(type_issues) == 1
        assert "data" in type_issues[0].details["parameter"]

    def test_enterprise_workflow_validation(self):
        """Test validation in enterprise workflow patterns."""
        workflow = WorkflowBuilder()

        # Enterprise entry node pattern
        class UserManagementNode(Node):
            def get_parameters(self):
                return {
                    "operation": NodeParameter(
                        name="operation",
                        type=str,
                        required=True,
                        description="Operation: create, update, delete",
                    ),
                    "user_data": NodeParameter(
                        name="user_data",
                        type=dict,
                        required=False,
                        description="User data for create/update",
                    ),
                    "user_id": NodeParameter(
                        name="user_id",
                        type=str,
                        required=False,
                        description="User ID for update/delete",
                    ),
                    "tenant_id": NodeParameter(
                        name="tenant_id",
                        type=str,
                        required=True,
                        description="Tenant identifier",
                    ),
                    "audit_context": NodeParameter(
                        name="audit_context",
                        type=dict,
                        required=False,
                        default={},
                        description="Audit information",
                    ),
                }

            def run(self, **kwargs):
                operation = kwargs["operation"]
                tenant_id = kwargs["tenant_id"]

                # Business logic validation
                if operation in ["update", "delete"] and not kwargs.get("user_id"):
                    raise ValueError(f"user_id required for {operation}")

                return {
                    "result": {
                        "success": True,
                        "operation": operation,
                        "tenant_id": tenant_id,
                    }
                }

        # Valid enterprise pattern
        workflow.add_node(
            UserManagementNode,
            "user_mgmt",
            {
                "operation": "create",
                "user_data": {"username": "testuser"},
                "tenant_id": "tenant_123",
            },
        )

        # Should build successfully
        built_workflow = workflow.build()
        assert built_workflow is not None

        # Execute to verify
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)
        assert results["user_mgmt"]["result"]["success"] is True

    def test_connection_parameter_validation(self):
        """Test validation of parameters passed through connections."""
        workflow = WorkflowBuilder()

        # Source node
        class DataSourceNode(Node):
            def get_parameters(self):
                return {
                    "query": NodeParameter(
                        name="query", type=str, required=True, description="Data query"
                    )
                }

            def run(self, **kwargs):
                return {"result": {"data": [1, 2, 3, 4, 5], "metadata": {"count": 5}}}

        # Target node expecting specific parameters
        class DataProcessorNode(Node):
            def get_parameters(self):
                return {
                    "input_data": NodeParameter(
                        name="input_data",
                        type=list,
                        required=True,
                        description="Data to process",
                    ),
                    "options": NodeParameter(
                        name="options",
                        type=dict,
                        required=False,
                        default={},
                        description="Processing options",
                    ),
                }

            def run(self, **kwargs):
                data = kwargs["input_data"]
                return {"result": {"processed": len(data)}}

        # Build workflow with connections
        workflow.add_node(DataSourceNode, "source", {"query": "SELECT * FROM users"})
        workflow.add_node(DataProcessorNode, "processor", {"options": {"mode": "fast"}})

        # Connect source output to processor input
        workflow.connect("source", "processor", mapping={"result.data": "input_data"})

        # Should build successfully - connection provides required parameter
        built_workflow = workflow.build()

        # Execute to verify
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)
        assert results["processor"]["result"]["processed"] == 5

    def test_cyclic_workflow_parameter_validation(self):
        """Test parameter validation in cyclic workflows."""
        workflow = WorkflowBuilder()

        # Cycle-aware node
        class IterativeProcessorNode(Node):
            def get_parameters(self):
                return {
                    "data": NodeParameter(
                        name="data",
                        type=list,
                        required=True,
                        description="Data to process iteratively",
                    ),
                    "max_iterations": NodeParameter(
                        name="max_iterations",
                        type=int,
                        required=False,
                        default=10,
                        description="Maximum iterations",
                    ),
                    "threshold": NodeParameter(
                        name="threshold",
                        type=float,
                        required=False,
                        default=0.95,
                        description="Convergence threshold",
                    ),
                }

            def run(self, **kwargs):
                data = kwargs["data"]
                context = kwargs.get("context", {})
                iteration = context.get("cycle", {}).get("iteration", 0)

                # Simple iterative improvement
                improved_data = [x * 1.1 for x in data]
                quality = min(sum(improved_data) / (len(improved_data) * 100), 1.0)

                return {
                    "result": improved_data,
                    "quality": quality,
                    "converged": quality >= kwargs.get("threshold", 0.95),
                    "iteration": iteration,
                }

        # Create cyclic workflow using CycleBuilder
        workflow.add_node(
            IterativeProcessorNode,
            "processor",
            {"data": [10, 20, 30], "threshold": 0.9},
        )

        # Create self-cycle
        cycle_builder = workflow.create_cycle("optimization")
        cycle_builder.connect("processor", "processor", mapping={"result": "data"})
        cycle_builder.max_iterations(5)
        cycle_builder.converge_when("converged == True")
        cycle_builder.build()

        # Should build successfully
        built_workflow = workflow.build()

        # Execute to verify
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)
        assert "processor" in results
        assert results["processor"]["converged"] is True

    def test_validation_error_aggregation(self):
        """Test that multiple validation errors are aggregated properly."""
        workflow = WorkflowBuilder()

        # Node with multiple issues
        class ProblematicNode(Node):
            def get_parameters(self):
                return {
                    "param1": NodeParameter(
                        name="param1",
                        # Missing type
                        required=True,
                    )
                    # Missing other parameters that will be passed
                }

            def run(self, **kwargs):
                return {"result": "problematic"}

        # Add with multiple issues
        workflow.add_node(
            ProblematicNode,
            "problem",
            {
                "param1": "value1",
                "param2": "undeclared",  # Not declared
                "param3": "also undeclared",  # Not declared
            },
        )

        # Add another problematic node
        workflow.add_node(
            ProblematicNode,
            "problem2",
            {
                # Missing required param1
                "extra": "not declared"
            },
        )

        # Should fail with multiple errors
        with pytest.raises(WorkflowValidationError) as exc_info:
            workflow.build()

        error_message = str(exc_info.value)
        # Should mention both nodes
        assert "problem" in error_message
        assert "problem2" in error_message
        # Should mention various issues
        assert (
            "undeclared" in error_message.lower()
            or "not declared" in error_message.lower()
        )
        assert "required" in error_message.lower()


class TestParameterValidationEdgeCases:
    """Test edge cases in parameter validation."""

    def test_node_with_context_parameter(self):
        """Test that context parameter is handled correctly."""
        workflow = WorkflowBuilder()

        # Node that uses context (should not be declared)
        class ContextAwareNode(Node):
            def get_parameters(self):
                return {
                    "data": NodeParameter(
                        name="data", type=list, required=True, description="Input data"
                    )
                    # context should NOT be declared
                }

            def run(self, **kwargs):
                data = kwargs["data"]
                context = kwargs.get("context", {})  # Always available

                return {"result": data, "has_context": context is not None}

        workflow.add_node(ContextAwareNode, "context_node", {"data": [1, 2, 3]})

        # Should build successfully
        built_workflow = workflow.build()

        # Execute to verify context is passed
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)
        assert results["context_node"]["has_context"] is True

    def test_node_with_default_values(self):
        """Test validation with default parameter values."""
        workflow = WorkflowBuilder()

        # Node with all optional parameters with defaults
        class DefaultParamsNode(Node):
            def get_parameters(self):
                return {
                    "mode": NodeParameter(
                        name="mode",
                        type=str,
                        required=False,
                        default="standard",
                        description="Processing mode",
                    ),
                    "batch_size": NodeParameter(
                        name="batch_size",
                        type=int,
                        required=False,
                        default=32,
                        description="Batch size",
                    ),
                    "config": NodeParameter(
                        name="config",
                        type=dict,
                        required=False,
                        default={},
                        description="Configuration",
                    ),
                }

            def run(self, **kwargs):
                return {
                    "result": {
                        "mode": kwargs.get("mode", "standard"),
                        "batch_size": kwargs.get("batch_size", 32),
                    }
                }

        # Add node without any parameters (all use defaults)
        workflow.add_node(DefaultParamsNode, "defaults", {})

        # Should build successfully
        built_workflow = workflow.build()

        # Execute to verify defaults are used
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)
        assert results["defaults"]["result"]["mode"] == "standard"
        assert results["defaults"]["result"]["batch_size"] == 32

    def test_pythoncode_node_parameter_validation(self):
        """Test parameter validation for PythonCodeNode."""
        workflow = WorkflowBuilder()

        # PythonCodeNode with parameters
        workflow.add_node(
            "PythonCodeNode",
            "processor",
            {
                "code": """
# Access parameters
data = parameters.get('data', [])
multiplier = parameters.get('multiplier', 2)

# Process
result = {
    'processed': [x * multiplier for x in data],
    'count': len(data)
}
""",
                "parameters": {"data": [1, 2, 3, 4, 5], "multiplier": 3},
            },
        )

        # Should build successfully - PythonCodeNode handles parameters differently
        built_workflow = workflow.build()

        # Execute to verify
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)
        assert results["processor"]["processed"] == [3, 6, 9, 12, 15]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
