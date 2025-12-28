"""
Production-focused E2E tests for the enhanced warning system.

Tests real-world scenarios with actual SDK nodes and custom node patterns.
"""

import warnings
from pathlib import Path

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.data.readers import CSVReaderNode, JSONReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestProductionWarningSystem:
    """Test warning system in production scenarios."""

    @pytest.fixture
    def capture_warnings(self):
        """Fixture to capture warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            yield w

    def test_sdk_node_misuse_detection(self, capture_warnings):
        """Test detection of SDK node misuse with class references."""
        workflow = WorkflowBuilder()

        # Misuse SDK nodes with class references
        workflow.add_node(CSVReaderNode, "csv_reader", {"file_path": "data.csv"})
        workflow.add_node(JSONReaderNode, "json_reader", {"file_path": "config.json"})

        # Check warnings were generated
        warning_messages = [str(w.message) for w in capture_warnings]
        sdk_warnings = [w for w in warning_messages if "SDK node detected" in w]

        assert len(sdk_warnings) == 2
        assert any("CSVReaderNode" in w for w in sdk_warnings)
        assert any("JSONReaderNode" in w for w in sdk_warnings)
        assert all("PREFERRED: add_node(" in w for w in sdk_warnings)

    def test_custom_node_correct_usage(self, capture_warnings):
        """Test that custom nodes with class references generate appropriate guidance."""
        workflow = WorkflowBuilder()

        # Define custom node
        class DataValidatorNode(Node):
            def get_parameters(self):
                return {
                    "data": NodeParameter(
                        name="data",
                        type=list,
                        required=True,
                        description="Data to validate",
                    ),
                    "rules": NodeParameter(
                        name="rules",
                        type=dict,
                        required=False,
                        default={},
                        description="Validation rules",
                    ),
                }

            def run(self, **kwargs):
                data = kwargs.get("data", [])
                # Simple validation
                valid_data = [item for item in data if isinstance(item, (int, float))]
                return {
                    "result": valid_data,
                    "invalid_count": len(data) - len(valid_data),
                }

        # Use custom node correctly
        workflow.add_node(DataValidatorNode, "validator", {"data": [1, 2, "3", 4]})

        # Check for custom node guidance
        warning_messages = [str(w.message) for w in capture_warnings]
        custom_warnings = [
            w for w in warning_messages if "CUSTOM NODE USAGE CORRECT" in w
        ]

        assert len(custom_warnings) == 1
        assert "DataValidatorNode" in custom_warnings[0]
        assert "This is the CORRECT pattern for custom nodes" in custom_warnings[0]

    def test_mixed_workflow_warnings(self, capture_warnings):
        """Test workflow with both SDK and custom nodes."""
        workflow = WorkflowBuilder()

        # Custom entry node
        class WorkflowEntryNode(Node):
            def get_parameters(self):
                return {
                    "config": NodeParameter(
                        name="config",
                        type=dict,
                        required=True,
                        description="Workflow configuration",
                    )
                }

            def run(self, **kwargs):
                config = kwargs.get("config", {})
                return {
                    "result": {"file_path": config.get("input_file", "default.csv")}
                }

        # Build workflow with mixed patterns
        workflow.add_node(
            WorkflowEntryNode, "entry", {"config": {"input_file": "data.csv"}}
        )
        workflow.add_node(
            "CSVReaderNode", "reader", {"file_path": "placeholder"}
        )  # Correct
        workflow.add_node(
            CSVWriterNode, "writer", {"file_path": "output.csv"}
        )  # Incorrect

        # Connect nodes
        workflow.connect("entry", "reader", mapping={"result.file_path": "file_path"})

        warning_messages = [str(w.message) for w in capture_warnings]

        # Should have one custom node confirmation and one SDK misuse warning
        custom_correct = [
            w for w in warning_messages if "CUSTOM NODE USAGE CORRECT" in w
        ]
        sdk_warnings = [w for w in warning_messages if "SDK node detected" in w]

        assert len(custom_correct) == 1
        assert "WorkflowEntryNode" in custom_correct[0]

        assert len(sdk_warnings) == 1
        assert "CSVWriterNode" in sdk_warnings[0]

    def test_no_warnings_for_correct_patterns(self, capture_warnings):
        """Test that correct patterns generate no warnings."""
        workflow = WorkflowBuilder()

        # Use SDK nodes correctly with string references
        workflow.add_node(
            "PythonCodeNode",
            "generator",
            {"code": "result = {'data': list(range(10))}"},
        )
        workflow.add_node("CSVReaderNode", "reader", {"file_path": "input.csv"})
        workflow.add_node("JSONReaderNode", "config", {"file_path": "config.json"})

        # Should have no warnings
        assert len(capture_warnings) == 0

    def test_warning_with_parameter_validation(self, capture_warnings):
        """Test warning system alongside parameter validation."""
        workflow = WorkflowBuilder()

        # Custom node with empty parameters (will trigger validation)
        class EmptyParamsNode(Node):
            def get_parameters(self):
                return {}  # No parameters declared

            def run(self, **kwargs):
                return {"result": "no params"}

        # Add node with parameters that will be rejected
        workflow.add_node(EmptyParamsNode, "empty", {"data": "will be ignored"})

        # Should get custom node warning
        warning_messages = [str(w.message) for w in capture_warnings]
        custom_warnings = [
            w for w in warning_messages if "CUSTOM NODE USAGE CORRECT" in w
        ]

        assert len(custom_warnings) == 1
        assert "EmptyParamsNode" in custom_warnings[0]

        # Parameter validation will happen at build time
        with pytest.raises(Exception) as exc_info:
            workflow.build()

        assert "parameter" in str(exc_info.value).lower()

    def test_enterprise_workflow_pattern(self, capture_warnings):
        """Test enterprise pattern with entry nodes and validation."""
        workflow = WorkflowBuilder()

        # Enterprise entry node pattern
        class UserManagementEntryNode(Node):
            def get_parameters(self):
                return {
                    "operation": NodeParameter(
                        name="operation",
                        type=str,
                        required=True,
                        description="Operation type",
                    ),
                    "user_data": NodeParameter(
                        name="user_data",
                        type=dict,
                        required=False,
                        description="User data",
                    ),
                    "tenant_id": NodeParameter(
                        name="tenant_id",
                        type=str,
                        required=True,
                        description="Tenant identifier",
                    ),
                }

            def run(self, **kwargs):
                operation = kwargs["operation"]
                tenant_id = kwargs["tenant_id"]
                user_data = kwargs.get("user_data", {})

                return {
                    "result": {
                        "operation": operation,
                        "tenant_id": tenant_id,
                        "user_data": user_data,
                        "validated": True,
                    }
                }

        # Use enterprise pattern
        workflow.add_node(
            UserManagementEntryNode,
            "entry",
            {
                "operation": "create_user",
                "tenant_id": "tenant_123",
                "user_data": {"username": "testuser"},
            },
        )

        # Add SDK node for processing
        workflow.add_node(
            "PythonCodeNode",
            "processor",
            {
                "code": """
# Process user creation
user_info = parameters.get('user_info', {})
result = {
    'created': True,
    'user_id': 'user_' + str(hash(user_info.get('username', '')))
}
"""
            },
        )

        workflow.connect("entry", "processor", mapping={"result": "user_info"})

        # Should only have custom node guidance
        warning_messages = [str(w.message) for w in capture_warnings]
        custom_warnings = [
            w for w in warning_messages if "CUSTOM NODE USAGE CORRECT" in w
        ]

        assert len(custom_warnings) == 1
        assert "UserManagementEntryNode" in custom_warnings[0]
        assert "CORRECT pattern for custom nodes" in custom_warnings[0]


class TestWarningSystemPerformance:
    """Test warning system performance impact."""

    def test_warning_overhead_minimal(self):
        """Test that warning system adds minimal overhead."""
        import time

        # Time workflow creation without warnings
        start = time.time()
        workflow1 = WorkflowBuilder()
        for i in range(100):
            workflow1.add_node(
                "PythonCodeNode", f"node_{i}", {"code": f"result = {{'value': {i}}}"}
            )
        no_warning_time = time.time() - start

        # Time workflow creation with warnings
        start = time.time()
        workflow2 = WorkflowBuilder()

        # Create a custom node class
        class TestNode(Node):
            def get_parameters(self):
                return {"value": NodeParameter(name="value", type=int, required=True)}

            def run(self, **kwargs):
                return {"result": kwargs.get("value", 0)}

        # This will generate warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Suppress output
            for i in range(100):
                workflow2.add_node(TestNode, f"custom_{i}", {"value": i})

        warning_time = time.time() - start

        # Warning overhead should be less than 50% (very generous margin)
        overhead_ratio = warning_time / no_warning_time
        assert overhead_ratio < 1.5, f"Warning overhead too high: {overhead_ratio:.2f}x"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
