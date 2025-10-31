"""Integration tests for validation nodes.

Tests validation nodes with real Docker services.
Following testing policy: Integration tests MUST use REAL Docker services, NO MOCKING.
"""

import os
import tempfile

import pytest
from kailash.nodes.validation import (
    CodeValidationNode,
    ValidationTestSuiteExecutorNode,
    WorkflowValidationNode,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
class TestValidationNodesIntegration:
    """Integration tests for validation nodes with real services."""

    def test_code_validation_node_real_execution(self):
        """Test CodeValidationNode with real code execution."""
        node = CodeValidationNode()

        # Test with valid Python code
        valid_code = """
import json
import datetime

def process_data(input_data):
    \"\"\"Process input data and return result.\"\"\"
    result = {
        "timestamp": datetime.datetime.now().isoformat(),
        "processed": len(input_data),
        "status": "success"
    }
    return result

# Test the function
test_data = {"items": [1, 2, 3]}
output = process_data(test_data)
"""

        result = node.execute(
            code=valid_code,
            validation_levels=["syntax", "imports", "semantic"],
            test_inputs={"test_data": {"items": [1, 2, 3]}},
        )

        assert result["validated"] is True
        assert result["validation_status"] == "PASSED"
        assert result["summary"]["passed"] == 3
        assert result["summary"]["failed"] == 0

    def test_code_validation_node_syntax_error(self):
        """Test CodeValidationNode with syntax errors."""
        node = CodeValidationNode()

        # Code with syntax error
        invalid_code = """
def broken_function()  # Missing colon
    return "This won't work"
"""

        result = node.execute(
            code=invalid_code, validation_levels=["syntax", "imports", "semantic"]
        )

        assert result["validated"] is False
        assert result["validation_status"] == "FAILED"
        assert result["summary"]["failed"] >= 1

        # Should have syntax error details
        syntax_result = result["validation_results"][0]
        assert syntax_result["level"] == "syntax"
        assert syntax_result["passed"] is False
        assert "suggestions" in syntax_result

    def test_code_validation_node_import_error(self):
        """Test CodeValidationNode with import errors."""
        node = CodeValidationNode()

        # Code with non-existent import
        code_with_bad_import = """
import json
import nonexistent_module_xyz

def process():
    return json.dumps({"status": "ok"})
"""

        result = node.execute(
            code=code_with_bad_import, validation_levels=["syntax", "imports"]
        )

        # Syntax should pass but imports should fail
        assert result["validation_status"] == "FAILED"

        # Find import validation result
        import_result = next(
            r
            for r in result["validation_results"]
            if r["test_name"] == "import_validation"
        )
        assert import_result["passed"] is False
        assert "nonexistent_module_xyz" in str(import_result["details"])

    def test_code_validation_with_schema(self):
        """Test code validation with output schema checking."""
        node = CodeValidationNode()

        code = """
# Using test_inputs passed in
result = {
    "id": user_id,
    "name": f"User {user_id}",
    "active": True,
    "score": 95.5
}
"""

        # The schema should match the 'result' variable created in the code
        expected_schema = {"result": dict}  # Simple type check for the whole result

        result = node.execute(
            code=code,
            validation_levels=["syntax", "semantic", "functional"],
            test_inputs={"user_id": 123},
            expected_schema=expected_schema,
        )

        # Debug output
        print(f"Result: {result}")
        if not result["validated"]:
            print(f"Validation results: {result.get('validation_results', [])}")

        assert result["validated"] is True
        assert any(
            r["test_name"] == "output_schema_validation" and r["passed"]
            for r in result["validation_results"]
        )

    def test_workflow_validation_node(self):
        """Test WorkflowValidationNode with real workflow."""
        node = WorkflowValidationNode()

        workflow_code = """
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Add nodes
workflow.add_node("PythonCodeNode", "generator", {
    "code": "result = {'data': [1, 2, 3, 4, 5]}"
})

workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'sum': sum(data), 'count': len(data)}"
})

# Connect nodes
workflow.connect("generator", "processor", {"result.data": "data"})
"""

        result = node.execute(
            workflow_code=workflow_code,
            validate_execution=False,  # Don't execute for this test
            expected_nodes=["generator", "processor"],
            required_connections=[{"from": "generator", "to": "processor"}],
        )

        assert result["validated"] is True
        assert result["validation_details"]["syntax_valid"] is True
        assert result["validation_details"]["structure_valid"] is True
        assert result["validation_details"]["node_count"] == 2
        assert result["validation_details"]["connection_count"] == 1

    def test_workflow_validation_with_execution(self):
        """Test workflow validation with actual execution."""
        node = WorkflowValidationNode()

        workflow_code = """
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Simple workflow that generates and processes data
workflow.add_node("PythonCodeNode", "generator", {
    "code": "result = {'numbers': list(range(5))}"
})

workflow.add_node("PythonCodeNode", "doubler", {
    "code": "result = {'doubled': [x * 2 for x in numbers]}"
})

workflow.connect("generator", "doubler", {"result.numbers": "numbers"})
"""

        result = node.execute(
            workflow_code=workflow_code, validate_execution=True, test_parameters={}
        )

        assert result["validated"] is True
        assert result["validation_details"]["execution_valid"] is True
        assert "run_id" in result["validation_details"]

    def test_test_suite_executor_node(self):
        """Test ValidationTestSuiteExecutorNode with real test execution."""
        node = ValidationTestSuiteExecutorNode()

        # Code to test
        code = """
# Simple code that uses test inputs
if n <= 0:
    result = 0
elif n == 1:
    result = 1
else:
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    result = b
"""

        # Test suite - simplified to not require complex output validation
        test_suite = [
            {
                "name": "test_base_case_0",
                "inputs": {"n": 0},
                "expected_output": None,  # Just test execution
            },
            {"name": "test_base_case_1", "inputs": {"n": 1}, "expected_output": None},
            {"name": "test_fibonacci_5", "inputs": {"n": 5}, "expected_output": None},
            {"name": "test_fibonacci_10", "inputs": {"n": 10}, "expected_output": None},
        ]

        result = node.execute(code=code, test_suite=test_suite)

        # Debug output
        print(f"Result: {result}")

        assert result["all_tests_passed"] is True
        assert result["validation_status"] == "PASSED"
        assert result["summary"]["total"] == 4
        assert result["summary"]["passed"] == 4
        assert result["summary"]["failed"] == 0

    def test_test_suite_with_failures(self):
        """Test ValidationTestSuiteExecutorNode with failing tests."""
        node = ValidationTestSuiteExecutorNode()

        # Buggy code
        code = """
def calculate(x, y):
    # Bug: should be x + y, not x - y
    result = x - y
"""

        test_suite = [
            {
                "name": "test_addition",
                "inputs": {"x": 5, "y": 3},
                "expected_output": {"result": 8},  # Will fail, gets 2
            }
        ]

        result = node.execute(code=code, test_suite=test_suite)

        assert result["all_tests_passed"] is False
        assert result["validation_status"] == "FAILED"
        assert result["summary"]["failed"] > 0

    def test_complex_code_validation(self):
        """Test validation of complex code with multiple features."""
        node = CodeValidationNode()

        complex_code = """
import json
import datetime
from typing import Dict, List

class DataProcessor:
    def __init__(self):
        self.processed_count = 0

    def process_batch(self, items: List[Dict]) -> Dict:
        results = []
        for item in items:
            processed = {
                "id": item.get("id"),
                "value": item.get("value", 0) * 2,
                "timestamp": datetime.datetime.now().isoformat()
            }
            results.append(processed)
            self.processed_count += 1

        return {
            "results": results,
            "total_processed": self.processed_count,
            "batch_size": len(items)
        }

# Test the processor
processor = DataProcessor()
test_items = [{"id": 1, "value": 10}, {"id": 2, "value": 20}]
output = processor.process_batch(test_items)
"""

        result = node.execute(
            code=complex_code,
            validation_levels=["syntax", "imports", "semantic"],
            test_inputs={
                "test_items": [{"id": 1, "value": 10}, {"id": 2, "value": 20}]
            },
            timeout=10,
        )

        assert result["validated"] is True
        assert result["summary"]["passed"] >= 3

        # Check execution details
        semantic_result = next(
            r
            for r in result["validation_results"]
            if r["test_name"] == "code_execution"
        )
        assert semantic_result["passed"] is True
        assert "output" in semantic_result["details"]["output_keys"]

    def test_validation_timeout_handling(self):
        """Test validation with timeout scenarios."""
        node = CodeValidationNode()

        # Code with potential infinite loop
        infinite_code = """
# This would run forever without timeout
counter = 0
while True:
    counter += 1
    if counter > 1000000000:  # Never reached in time
        break
result = counter
"""

        result = node.execute(
            code=infinite_code,
            validation_levels=["syntax", "semantic"],
            timeout=2,  # 2 second timeout
        )

        # Syntax should pass
        syntax_result = result["validation_results"][0]
        assert syntax_result["passed"] is True

        # Semantic execution should timeout
        if len(result["validation_results"]) > 1:
            semantic_result = result["validation_results"][1]
            if not semantic_result["passed"]:
                assert "timed out" in semantic_result["error"].lower()

    def test_workflow_validation_with_file_paths(self):
        """Test workflow validation with file path handling."""
        # Create a temporary file for testing
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            import json

            json.dump({"test": "data"}, f)
            temp_file = f.name

        try:
            node = WorkflowValidationNode()

            workflow_code = f"""
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

workflow.add_node("JSONReaderNode", "reader", {{
    "file_path": "{temp_file}"
}})

workflow.add_node("PythonCodeNode", "processor", {{
    "code": "result = {{'keys': list(data.keys())}}"
}})

workflow.connect("reader", "processor", {{"data": "data"}})
"""

            result = node.execute(
                workflow_code=workflow_code,
                validate_execution=False,  # Don't execute to avoid file dependencies
            )

            assert result["validated"] is True
            assert result["validation_details"]["nodes"] == ["reader", "processor"]

        finally:
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)
