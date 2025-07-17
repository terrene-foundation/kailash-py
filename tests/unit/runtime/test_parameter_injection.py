"""Tests for production-quality parameter injection in LocalRuntime."""

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow, WorkflowBuilder


class MockParameterNode(Node):
    """Test node with various parameter configurations."""

    def get_parameters(self):
        return {
            "required_param": NodeParameter(
                name="required_param",
                type=str,
                required=True,
                description="Required parameter",
            ),
            "optional_param": NodeParameter(
                name="optional_param",
                type=str,
                required=False,
                default="default_value",
                description="Optional parameter",
            ),
            "workflow_alias_param": NodeParameter(
                name="workflow_alias_param",
                type=str,
                required=False,
                workflow_alias="user_data",
                description="Parameter with workflow alias",
            ),
            "auto_map_param": NodeParameter(
                name="auto_map_param",
                type=str,
                required=False,
                auto_map_from=["input", "data"],
                description="Parameter with auto mapping",
            ),
            "primary_param": NodeParameter(
                name="primary_param",
                type=str,
                required=False,
                auto_map_primary=True,
                description="Primary auto-mapped parameter",
            ),
        }

    def run(self, **kwargs):
        return {
            "received_params": kwargs,
            "required": kwargs.get("required_param"),
            "optional": kwargs.get("optional_param"),
            "alias": kwargs.get("workflow_alias_param"),
            "auto": kwargs.get("auto_map_param"),
            "primary": kwargs.get("primary_param"),
        }


class TestWorkflowParameterInjection:
    """Test automatic parameter injection for workflow-level parameters."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure nodes are registered
        from kailash.nodes.base import NodeRegistry

        if "PythonCodeNode" not in NodeRegistry._nodes:
            try:
                NodeRegistry.register(PythonCodeNode, "PythonCodeNode")
            except Exception:
                pass
        if "MockParameterNode" not in NodeRegistry._nodes:
            try:
                NodeRegistry.register(MockParameterNode, "MockParameterNode")
            except Exception:
                pass

    def test_workflow_level_parameters_basic(self):
        """Test basic workflow-level parameter injection."""
        # Create workflow with entry node
        workflow = Workflow("test", "Test workflow")
        workflow.add_node("entry", MockParameterNode())

        # Execute with workflow-level parameters
        runtime = LocalRuntime(debug=True)
        results, _ = runtime.execute(
            workflow,
            parameters={
                "required_param": "test_value",
                "optional_param": "custom_value",
            },
        )

        # Verify parameters were injected
        assert results["entry"]["required"] == "test_value"
        assert results["entry"]["optional"] == "custom_value"

    def test_workflow_alias_mapping(self):
        """Test workflow alias parameter mapping."""
        workflow = Workflow("test", "Test workflow")
        workflow.add_node("entry", MockParameterNode())

        runtime = LocalRuntime(debug=True)
        results, _ = runtime.execute(
            workflow,
            parameters={
                "required_param": "test",  # Still need required param
                "user_data": "aliased_value",
            },
        )

        # Verify alias was mapped
        assert results["entry"]["alias"] == "aliased_value"

    def test_auto_map_from_alternatives(self):
        """Test auto_map_from alternative names."""
        workflow = Workflow("test", "Test workflow")
        workflow.add_node("entry", MockParameterNode())

        runtime = LocalRuntime(debug=True)

        # Test with "input" alternative
        results, _ = runtime.execute(
            workflow, parameters={"required_param": "req", "input": "auto_mapped_input"}
        )
        assert results["entry"]["auto"] == "auto_mapped_input"

        # Test with "data" alternative
        results, _ = runtime.execute(
            workflow, parameters={"required_param": "req", "data": "auto_mapped_data"}
        )
        assert results["entry"]["auto"] == "auto_mapped_data"

    def test_auto_map_primary(self):
        """Test auto_map_primary for unmapped parameters."""
        workflow = Workflow("test", "Test workflow")
        workflow.add_node("entry", MockParameterNode())

        runtime = LocalRuntime(debug=True)
        results, _ = runtime.execute(
            workflow,
            parameters={
                "required_param": "req",
                "some_unmapped_param": "primary_value",
            },
        )

        # Primary param should get the unmapped value
        assert results["entry"]["primary"] == "primary_value"

    def test_mixed_format_parameters(self):
        """Test backward compatibility with node-specific format."""
        workflow = Workflow("test", "Test workflow")
        workflow.add_node("entry", MockParameterNode())

        runtime = LocalRuntime(debug=True)

        # Node-specific format should still work
        results, _ = runtime.execute(
            workflow, parameters={"entry": {"required_param": "node_specific_value"}}
        )

        assert results["entry"]["required"] == "node_specific_value"

    def test_workflow_builder_input_mappings(self):
        """Test WorkflowBuilder's add_workflow_inputs method."""
        # Create a simple test node
        from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
        
        @register_node()
        class SimpleParamNode(Node):
            def __init__(self, **kwargs):
                metadata = NodeMetadata(
                    name="SimpleParamNode",
                    description="Simple parameter test node"
                )
                super().__init__(metadata=metadata, **kwargs)
            
            def get_parameters(self):
                return {
                    "required_param": NodeParameter(
                        name="required_param",
                        type=str,
                        required=True,
                        description="Required parameter"
                    ),
                    "optional_param": NodeParameter(
                        name="optional_param",
                        type=str,
                        required=False,
                        default="default",
                        description="Optional parameter"
                    )
                }
            
            def run(self, **kwargs):
                return {
                    "required": kwargs.get("required_param"),
                    "optional": kwargs.get("optional_param", "default")
                }
        
        builder = WorkflowBuilder()
        builder.add_node(
            "SimpleParamNode",
            "processor",
            {}
        )
        builder.add_workflow_inputs(
            "processor",
            {"user_input": "required_param", "config_data": "optional_param"},
        )

        workflow = builder.build()

        runtime = LocalRuntime(debug=True)
        results, _ = runtime.execute(
            workflow,
            parameters={
                "user_input": "mapped_required",
                "config_data": "mapped_optional",
            },
        )

        assert results["processor"]["result"]["required"] == "mapped_required"
        assert results["processor"]["result"]["optional"] == "mapped_optional"

    def test_multiple_entry_nodes(self):
        """Test parameter injection with multiple entry nodes."""
        workflow = Workflow("test", "Test workflow")

        # Add two entry nodes
        workflow.add_node("entry1", MockParameterNode())
        workflow.add_node("entry2", MockParameterNode())

        # Add a node that depends on both
        def merge_func(a, b):
            return {"merged": f"{a}+{b}"}

        workflow.add_node("merge", PythonCodeNode.from_function(merge_func))

        workflow.connect("entry1", "merge", {"required": "a"})
        workflow.connect("entry2", "merge", {"required": "b"})

        runtime = LocalRuntime(debug=True)
        results, _ = runtime.execute(
            workflow, parameters={"required_param": "shared_value"}
        )

        # Both entry nodes should receive the parameter
        assert results["entry1"]["required"] == "shared_value"
        assert results["entry2"]["required"] == "shared_value"
        assert results["merge"]["result"]["merged"] == "shared_value+shared_value"

    def test_parameter_precedence(self):
        """Test parameter precedence rules."""
        workflow = Workflow("test", "Test workflow")
        workflow.add_node("entry", MockParameterNode())

        runtime = LocalRuntime(debug=True)

        # Mix workflow-level and node-specific parameters
        results, _ = runtime.execute(
            workflow,
            parameters={
                "required_param": "workflow_level",
                "entry": {"required_param": "node_specific"},  # Should take precedence
            },
        )

        # Node-specific should override workflow-level
        assert results["entry"]["required"] == "node_specific"

    def test_validation_warnings(self):
        """Test validation warnings for missing required parameters."""
        workflow = Workflow("test", "Test workflow")
        workflow.add_node("entry", MockParameterNode())

        runtime = LocalRuntime(debug=True)

        # Execute without required parameter
        with pytest.raises(Exception):  # Should fail validation
            runtime.execute(workflow, parameters={"optional_param": "only_optional"})

    def test_complex_workflow_scenario(self):
        """Test complex real-world workflow scenario."""
        # Simulate user management workflow
        workflow = Workflow("user_mgmt", "User management workflow")

        # Validator node
        def validate_user(email, password):
            return {"valid": "@" in email and len(password) >= 8, "email": email}

        validator_node = PythonCodeNode.from_function(validate_user)
        workflow.add_node("validator", validator_node)

        # User creator node
        def create_user(email, password, tenant_id="default"):
            return {
                "user_id": f"user_{email.split('@')[0]}",
                "email": email,
                "tenant_id": tenant_id,
            }

        creator_node = PythonCodeNode.from_function(create_user)
        workflow.add_node("creator", creator_node)

        # Connect validator to creator
        workflow.connect("validator", "creator", {"result.email": "email"})

        # Map workflow inputs via metadata
        workflow.metadata["_workflow_inputs"] = {
            "validator": {"user_email": "email", "user_password": "password"},
            "creator": {"user_password": "password", "tenant": "tenant_id"},
        }

        runtime = LocalRuntime(debug=True)
        results, _ = runtime.execute(
            workflow,
            parameters={
                "user_email": "test@example.com",
                "user_password": "secure123",
                "tenant": "production",
            },
        )

        # Verify workflow execution
        assert results["validator"]["result"]["valid"] is True
        assert results["creator"]["result"]["user_id"] == "user_test"
        assert results["creator"]["result"]["tenant_id"] == "production"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
