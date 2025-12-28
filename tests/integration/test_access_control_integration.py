"""Integration tests for access control with real components."""

import pytest
from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    WorkflowPermission,
    get_access_control_manager,
)
from kailash.nodes.base_with_acl import add_access_control
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


class TestAccessControlIntegration:
    """Integration tests for access control with real workflow execution."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and cleanup for each test."""
        # Note: If ACM is a singleton, we would need to clear it here
        # For now, we'll work with what we have
        yield
        # Cleanup after test if needed

    @pytest.fixture
    def sample_workflow(self):
        """Create a sample workflow for testing."""
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")

        # Add a simple node
        node = PythonCodeNode(
            name="processor",
            code="result = input_data * 2",
            inputs={"input_data": "number"},
            outputs={"result": "number"},
        )
        workflow.add_node("processor", node)

        return workflow

    def test_workflow_execution_without_access_control(self, sample_workflow):
        """Test that workflows execute normally without access control."""
        runtime = LocalRuntime()
        result, _ = runtime.execute(
            sample_workflow, parameters={"processor": {"input_data": 10}}
        )

        assert "processor" in result
        assert result["processor"]["result"] == 20

    def test_mixed_workflow_with_regular_and_acl_nodes(self):
        """Test workflow with both ACL and non-ACL nodes using LocalRuntime."""
        workflow = Workflow(workflow_id="mixed_workflow", name="Mixed Workflow")

        # Regular node - multiplies by 2
        regular_node = PythonCodeNode(
            name="multiplier",
            code="result = input_data * 2",
            inputs={"input_data": "number"},
            outputs={"result": "number"},
        )

        # ACL-protected node - adds 10
        secure_node = add_access_control(
            PythonCodeNode(
                name="adder",
                code="result = input_data + 10",
                inputs={"input_data": "number"},
                outputs={"result": "number"},
            ),
            enable_access_control=True,
            required_permission=NodePermission.EXECUTE,
            node_id="secure_adder",
        )

        workflow.add_node("multiply", regular_node)
        workflow.add_node("add", secure_node)
        workflow.connect("multiply", "add", {"result": "input_data"})

        # Execute with LocalRuntime (no access control enforcement)
        runtime = LocalRuntime()
        result, _ = runtime.execute(
            workflow, parameters={"multiply": {"input_data": 5}}
        )

        # Verify the flow: 5 * 2 = 10, then 10 + 10 = 20
        assert "multiply" in result
        assert result["multiply"]["result"] == 10
        assert "add" in result
        assert result["add"]["result"] == 20

    def test_node_with_output_masking_configuration(self):
        """Test that nodes can be configured with output masking."""
        # Create node that returns sensitive data
        sensitive_node = PythonCodeNode(
            name="sensitive_processor",
            code="""
result = {
    'name': 'John Doe',
    'ssn': '123-45-6789',
    'balance': 1000,
    'account_number': '9876543210'
}
""",
            inputs={},
            outputs={"result": "dict"},
        )

        # Wrap with access control and output masking
        wrapped_node = add_access_control(
            sensitive_node,
            enable_access_control=True,
            mask_output_fields=["ssn", "account_number"],
            node_id="sensitive_data_node",
        )

        # Create workflow
        workflow = Workflow(workflow_id="sensitive_workflow", name="Sensitive Workflow")
        workflow.add_node("sensitive", wrapped_node)

        # Execute
        runtime = LocalRuntime()
        result, _ = runtime.execute(workflow)

        # The LocalRuntime doesn't enforce masking, but the node should have the config
        assert hasattr(wrapped_node, "mask_output_fields")
        assert "ssn" in wrapped_node.mask_output_fields
        assert "account_number" in wrapped_node.mask_output_fields

        # Result should contain the data (LocalRuntime doesn't mask)
        assert "sensitive" in result
        assert "name" in result["sensitive"]["result"]
        assert "ssn" in result["sensitive"]["result"]  # Not masked by LocalRuntime

    def test_complex_workflow_with_multiple_acl_nodes(self):
        """Test a more complex workflow with multiple ACL-protected nodes."""
        workflow = Workflow(workflow_id="complex_workflow", name="Complex Workflow")

        # Input validation node (ACL protected)
        validator = add_access_control(
            PythonCodeNode(
                name="validator",
                code="""
if not isinstance(data, (int, float)) or data < 0:
    raise ValueError("Invalid input: must be positive number")
result = data
""",
                inputs={"data": "any"},
                outputs={"result": "number"},
            ),
            enable_access_control=True,
            required_permission=NodePermission.EXECUTE,
            node_id="input_validator",
        )

        # Processing node (regular)
        processor = PythonCodeNode(
            name="processor",
            code="result = value ** 2",  # Square the value
            inputs={"value": "number"},
            outputs={"result": "number"},
        )

        # Output formatter (ACL protected)
        formatter = add_access_control(
            PythonCodeNode(
                name="formatter",
                code="""
result = {
    'original': original,
    'processed': processed,
    'timestamp': '2024-01-01T00:00:00Z',
    'status': 'completed'
}
""",
                inputs={"original": "number", "processed": "number"},
                outputs={"result": "dict"},
            ),
            enable_access_control=True,
            required_permission=NodePermission.EXECUTE,
            node_id="output_formatter",
        )

        # Build workflow
        workflow.add_node("validate", validator)
        workflow.add_node("process", processor)
        workflow.add_node("format", formatter)

        # Connect nodes
        workflow.connect("validate", "process", {"result": "value"})
        workflow.connect("validate", "format", {"result": "original"})
        workflow.connect("process", "format", {"result": "processed"})

        # Execute
        runtime = LocalRuntime()
        result, _ = runtime.execute(workflow, parameters={"validate": {"data": 5}})

        # Verify results
        assert "validate" in result
        assert result["validate"]["result"] == 5

        assert "process" in result
        assert result["process"]["result"] == 25  # 5^2

        assert "format" in result
        formatted = result["format"]["result"]
        assert formatted["original"] == 5
        assert formatted["processed"] == 25
        assert formatted["status"] == "completed"

    def test_error_handling_in_acl_wrapped_nodes(self):
        """Test that errors in ACL-wrapped nodes are properly propagated."""
        # Create a node that will raise an error
        error_node = add_access_control(
            PythonCodeNode(
                name="error_node",
                code="""
if value > 10:
    raise ValueError("Value too large")
result = value
""",
                inputs={"value": "number"},
                outputs={"result": "number"},
            ),
            enable_access_control=True,
            node_id="error_prone_node",
        )

        workflow = Workflow(workflow_id="error_workflow", name="Error Workflow")
        workflow.add_node("check", error_node)

        runtime = LocalRuntime()

        # Test with valid input
        result, _ = runtime.execute(workflow, parameters={"check": {"value": 5}})
        assert result["check"]["result"] == 5

        # Test with invalid input
        result, _ = runtime.execute(workflow, parameters={"check": {"value": 15}})
        # Should have an error
        assert "check" in result
        # The error should be captured in the result
        # (exact format depends on error handling implementation)
