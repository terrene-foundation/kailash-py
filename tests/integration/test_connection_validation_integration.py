"""
Integration tests for connection parameter validation.

Tests the full integration of connection validation with real nodes
and workflow execution.
"""

import os

import pytest
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode, JSONReaderNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestConnectionValidationIntegration:
    """Integration tests for connection validation with real nodes."""

    @pytest.fixture
    def temp_files(self, tmp_path):
        """Create temporary test files."""
        # CSV file
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("name,age,role\nAlice,30,admin\nBob,25,user")

        # JSON file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"users": [{"name": "Alice", "admin": true}]}')

        return {"csv": str(csv_file), "json": str(json_file)}

    def test_csv_to_python_code_validation(self, temp_files):
        """Test validation between CSV reader and Python code node."""
        workflow = WorkflowBuilder()

        # CSV reader outputs list of dicts
        workflow.add_node("CSVReaderNode", "reader", {"file_path": temp_files["csv"]})

        # Python code expects specific structure
        workflow.add_node(
            "PythonCodeNode",
            "processor",
            {
                "code": """
# Process CSV data - csv_data is directly available as a variable
admin_count = sum(1 for row in csv_data if row.get('role') == 'admin')
result = {'admin_count': admin_count, 'total': len(csv_data)}
"""
            },
        )

        # Connect CSV output to Python input
        workflow.add_connection("reader", "data", "processor", "csv_data")

        # Test with validation disabled first
        runtime = LocalRuntime(connection_validation="off")
        results, _ = runtime.execute(workflow.build(), {})

        assert results["processor"]["result"]["admin_count"] == 1
        assert results["processor"]["result"]["total"] == 2

        # Now test with strict validation
        runtime_strict = LocalRuntime(connection_validation="strict")
        results_strict, _ = runtime_strict.execute(workflow.build(), {})

        assert results_strict["processor"]["result"]["admin_count"] == 1
        assert results_strict["processor"]["result"]["total"] == 2

    def test_type_mismatch_detection(self, temp_files):
        """Test detection of type mismatches in connections."""
        workflow = WorkflowBuilder()

        # JSON reader outputs dict
        workflow.add_node(
            "JSONReaderNode", "json_reader", {"file_path": temp_files["json"]}
        )

        # Create a node expecting a list
        class ListProcessorNode(Node):
            def get_parameters(self):
                return {"items": NodeParameter(type=list, required=True)}

            def run(self, **kwargs):
                items = kwargs["items"]
                return {"count": len(items)}

        # Register the custom node first
        from kailash.nodes.base import register_node

        register_node()(ListProcessorNode)

        workflow.add_node("ListProcessorNode", "processor", {})

        # Connect dict output to list input (type mismatch)
        workflow.add_connection("json_reader", "data", "processor", "items")

        runtime = LocalRuntime(connection_validation="strict")

        # Should fail due to type mismatch
        with pytest.raises(Exception) as exc_info:
            runtime.execute(workflow.build(), {})
        assert "type" in str(exc_info.value).lower()

    def test_switch_node_conditional_validation(self):
        """Test validation with conditional routing."""
        workflow = WorkflowBuilder()

        # Data source
        workflow.add_node(
            "PythonCodeNode", "source", {"code": "result = {'value': 42, 'flag': True}"}
        )

        # Switch node for routing
        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "value", "operator": ">", "value": 40},
        )

        # Use PythonCodeNode for branches to avoid custom node registration issues
        workflow.add_node(
            "PythonCodeNode",
            "true_branch",
            {
                "code": """
# True branch - receives input_data from switch node
value = input_data.get('value', 0)
flag = input_data.get('flag', False)
result = {"processed": value * 2}
"""
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "false_branch",
            {
                "code": """
# False branch - receives input_data from switch node
# Handle case where this branch isn't executed (input_data is None)
if input_data is None:
    result = {"processed": None, "skipped": True}
else:
    value = input_data.get('value', 0)
    result = {"processed": value / 2}
"""
            },
        )

        # Connect source to switch
        workflow.add_connection("source", "result", "switch", "input_data")

        # Connect switch to branches - map outputs to input variables
        workflow.add_connection("switch", "true_output", "true_branch", "input_data")
        workflow.add_connection("switch", "false_output", "false_branch", "input_data")

        runtime = LocalRuntime(connection_validation="strict")
        results, _ = runtime.execute(workflow.build(), {})

        # Should execute true branch successfully
        assert "true_branch" in results
        assert results["true_branch"]["result"]["processed"] == 84

    def test_nested_workflow_validation(self):
        """Test validation with nested workflows."""
        # Create inner workflow
        inner_workflow = WorkflowBuilder()

        # Use PythonCodeNode for validation
        inner_workflow.add_node(
            "PythonCodeNode",
            "validator",
            {
                "code": """
# Validate email and age parameters
if "@" not in email:
    raise ValueError(f"Invalid email: {email}")
if age < 0 or age > 150:
    raise ValueError(f"Invalid age: {age}")

result = {"valid": True, "user": {"email": email, "age": age}}
"""
            },
        )

        # Create outer workflow
        outer_workflow = WorkflowBuilder()

        # Data source with valid data
        outer_workflow.add_node(
            "PythonCodeNode",
            "source",
            {
                "code": """
# Prepare data for WorkflowNode inputs parameter
# The inputs parameter expects a dict mapping node_id to parameters
result = {
    'workflow_inputs': {
        'validator': {
            'email': 'test@example.com',
            'age': 25
        }
    }
}
"""
            },
        )

        # Add inner workflow as a node
        outer_workflow.add_node(
            "WorkflowNode", "inner", {"workflow": inner_workflow.build()}
        )

        # Connect source to inner workflow using inputs parameter
        # WorkflowNode expects inputs as a dict mapping node_id to parameters
        outer_workflow.add_connection(
            "source", "result.workflow_inputs", "inner", "inputs"
        )

        # Test with validation
        runtime = LocalRuntime(connection_validation="strict")
        results, _ = runtime.execute(outer_workflow.build(), {})

        # WorkflowNode returns results under "results" key
        inner_results = results["inner"]["results"]["validator"]
        assert inner_results["result"]["valid"] is True
        assert inner_results["result"]["user"]["age"] == 25
        assert inner_results["result"]["user"]["email"] == "test@example.com"

    def test_parallel_execution_validation(self):
        """Test validation with parallel node execution."""
        workflow = WorkflowBuilder()

        # Source node
        workflow.add_node(
            "PythonCodeNode",
            "source",
            {
                "code": """
result = {
    'numbers': [1, 2, 3, 4, 5],
    'multiplier': 2
}
"""
            },
        )

        # Multiple parallel processors
        for i in range(3):
            workflow.add_node(
                "PythonCodeNode",
                f"processor_{i}",
                {
                    "code": f"""
# Get data from the source - connection maps source.result to processor_N.data
numbers = data.get('numbers', [])
multiplier = data.get('multiplier', 1)

result = {{
    'processed': [n * multiplier * {i+1} for n in numbers],
    'processor_id': {i}
}}
"""
                },
            )

            # Connect source to each processor - map to 'data' input
            workflow.add_connection("source", "result", f"processor_{i}", "data")

        # Aggregator node using PythonCodeNode
        workflow.add_node(
            "PythonCodeNode",
            "aggregator",
            {
                "code": """
# Aggregate results from multiple processors
# Each processor's result is mapped to input_0, input_1, input_2
results = []
# Access each input directly
if 'input_0' in vars():
    results.extend(input_0.get("processed", []))
if 'input_1' in vars():
    results.extend(input_1.get("processed", []))
if 'input_2' in vars():
    results.extend(input_2.get("processed", []))
result = {"aggregated": results}
"""
            },
        )

        # Connect processors to aggregator
        for i in range(3):
            workflow.add_connection(
                f"processor_{i}", "result", "aggregator", f"input_{i}"
            )

        # Use LocalRuntime with validation (ParallelRuntime doesn't support connection validation)
        runtime = LocalRuntime(connection_validation="strict")
        results, _ = runtime.execute(workflow.build(), {})

        # Should validate all parallel connections
        assert "aggregator" in results
        assert (
            len(results["aggregator"]["result"]["aggregated"]) == 15
        )  # 5 numbers * 3 processors

    def test_error_propagation_with_validation(self):
        """Test how validation errors propagate through the workflow."""
        workflow = WorkflowBuilder()

        # Node that produces invalid data
        workflow.add_node(
            "PythonCodeNode",
            "bad_source",
            {
                "code": """
# Intentionally produce wrong type
result = {
    'user_id': None,  # Should be string
    'score': 'invalid'  # Should be number
}
"""
            },
        )

        # Strict consumer node using PythonCodeNode
        workflow.add_node(
            "PythonCodeNode",
            "consumer",
            {
                "code": """
# Expect user_id as string and score as float
# Connection maps bad_source.result to consumer.data
user_id = data.get('user_id')
score = data.get('score')

if not isinstance(user_id, str):
    raise TypeError(f"user_id must be string, got {type(user_id)}")
if not isinstance(score, (int, float)):
    raise TypeError(f"score must be number, got {type(score)}")

result = {"processed": True}
"""
            },
        )
        # Connect bad source to consumer - map to 'data' input
        workflow.add_connection("bad_source", "result", "consumer", "data")

        # Test different validation modes

        # Off mode - should execute but consumer fails (no exception since it has no dependents)
        runtime_off = LocalRuntime(connection_validation="off")
        results, _ = runtime_off.execute(workflow.build(), {})
        # Check that bad_source succeeded but consumer failed
        assert "bad_source" in results
        assert results["bad_source"]["result"]["user_id"] is None
        assert "consumer" in results
        assert results["consumer"]["failed"] is True
        assert "error" in results["consumer"]

        # Warn mode - should log warning and continue (same behavior)
        runtime_warn = LocalRuntime(connection_validation="warn")
        results, _ = runtime_warn.execute(workflow.build(), {})
        assert "bad_source" in results
        assert "consumer" in results
        assert results["consumer"]["failed"] is True

        # Strict mode - connection validation might not catch this specific type mismatch
        # since both nodes use generic 'data' parameters. The failure happens at runtime.
        runtime_strict = LocalRuntime(connection_validation="strict")
        results, _ = runtime_strict.execute(workflow.build(), {})
        assert "bad_source" in results
        assert "consumer" in results
        assert results["consumer"]["failed"] is True
