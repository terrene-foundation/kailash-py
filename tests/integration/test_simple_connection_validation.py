"""
Simple integration test for connection validation to verify basic functionality.
"""

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestSimpleConnectionValidation:
    """Basic integration tests for connection validation."""

    def test_type_validation_between_nodes(self):
        """Test that type validation works between connected nodes."""
        workflow = WorkflowBuilder()

        # Source node outputs correct types that can be validated
        workflow.add_node(
            PythonCodeNode,
            "source",
            {
                "code": "result = {'count': '123', 'valid': 'true'}"
            },  # Strings that can convert
        )

        # Create a node that expects specific types
        class TypedConsumerNode(Node):
            def get_parameters(self):
                return {
                    "count": NodeParameter(name="count", type=int, required=False),
                    "valid": NodeParameter(name="valid", type=bool, required=False),
                }

            def run(self, **kwargs):
                # validate_inputs should have converted types
                count = kwargs.get("count")
                valid = kwargs.get("valid")

                if count is None or valid is None:
                    return {"error": f"Missing parameters. Got: {list(kwargs.keys())}"}

                assert isinstance(count, int), f"Expected int, got {type(count)}"
                assert isinstance(valid, bool), f"Expected bool, got {type(valid)}"
                return {"success": True, "count": count, "valid": valid}

        workflow.add_node(TypedConsumerNode, "consumer", {})
        # Map the result dict to individual parameters
        workflow.add_connection("source", "result.count", "consumer", "count")
        workflow.add_connection("source", "result.valid", "consumer", "valid")

        # Test with warn mode (default) - should convert types
        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build(), {})

        # Type conversion should work
        assert results["consumer"]["success"] is True
        assert results["consumer"]["count"] == 123
        assert results["consumer"]["valid"] is True

        # Test with a value that can't convert
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            PythonCodeNode,
            "bad_source",
            {"code": "result = {'count': 'not_a_number', 'valid': True}"},
        )
        workflow2.add_node(TypedConsumerNode, "consumer", {})
        workflow2.add_connection("bad_source", "result.count", "consumer", "count")
        workflow2.add_connection("bad_source", "result.valid", "consumer", "valid")

        # This should fail even in warn mode due to type conversion failure
        runtime_warn = LocalRuntime(connection_validation="warn")
        try:
            results, _ = runtime_warn.execute(workflow2.build(), {})
            # If it works, the value wasn't converted
            assert False, "Should have failed on type conversion"
        except Exception as e:
            # Expected - type conversion failed
            assert "count" in str(e) or "int" in str(e) or "type" in str(e).lower()

    def test_required_parameters_through_connections(self):
        """Test that required parameters are validated in connections."""
        workflow = WorkflowBuilder()

        # Source provides incomplete data
        workflow.add_node(
            PythonCodeNode,
            "source",
            {"code": "result = {'name': 'test'}"},  # Missing 'age' field
        )

        class StrictNode(Node):
            def get_parameters(self):
                return {
                    "name": NodeParameter(name="name", type=str, required=True),
                    "age": NodeParameter(name="age", type=int, required=True),
                }

            def run(self, **kwargs):
                return {"processed": True}

        workflow.add_node(StrictNode, "strict", {})
        workflow.add_connection("source", "result", "strict", "")

        # Strict mode should fail due to missing required parameter
        runtime = LocalRuntime(connection_validation="strict")
        with pytest.raises(Exception) as exc_info:
            runtime.execute(workflow.build(), {})
        # Should mention the missing parameter
        error_msg = str(exc_info.value).lower()
        assert "age" in error_msg or "required" in error_msg

    def test_backward_compatibility_mode(self):
        """Test that off mode maintains backward compatibility."""
        workflow = WorkflowBuilder()

        # Create nodes with potential type mismatches
        workflow.add_node(
            PythonCodeNode, "node1", {"code": "result = {'data': [1, 2, 3]}"}
        )

        workflow.add_node(
            PythonCodeNode,
            "node2",
            {
                "code": """
# Input parameters are injected as variables
try:
    data = input_data
except NameError:
    data = 'default'
result = {'received': str(data)}
"""
            },
        )

        workflow.add_connection("node1", "result.data", "node2", "input_data")

        # Off mode - should work without validation
        runtime_off = LocalRuntime(connection_validation="off")
        results, _ = runtime_off.execute(workflow.build(), {})

        # PythonCodeNode returns 'result' not direct dict
        assert "node2" in results
        assert "result" in results["node2"]
        assert results["node2"]["result"]["received"] == "[1, 2, 3]"

    def test_warn_mode_logs_but_continues(self):
        """Test that warn mode logs issues but continues execution."""
        workflow = WorkflowBuilder()

        # Create a type mismatch scenario
        workflow.add_node(
            PythonCodeNode, "source", {"code": "result = {'value': '123'}"}
        )  # String

        class NumberNode(Node):
            def get_parameters(self):
                return {"value": NodeParameter(name="value", type=float, required=True)}

            def run(self, **kwargs):
                # In warn mode, validate_inputs converts '123' to 123.0
                value = kwargs["value"]
                return {"doubled": value * 2}

        workflow.add_node(NumberNode, "processor", {})
        workflow.add_connection("source", "result.value", "processor", "value")

        # Warn mode - should convert and continue
        runtime_warn = LocalRuntime(connection_validation="warn")
        results, _ = runtime_warn.execute(workflow.build(), {})

        # String '123' should be converted to float 123.0
        assert results["processor"]["doubled"] == 246.0
