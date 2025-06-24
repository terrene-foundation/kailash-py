"""Consolidated validation tests for PythonCodeNode."""

import pandas as pd
import pytest

from kailash.nodes.code import PythonCodeNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class TestValidation:
    """Test validation behavior in PythonCodeNode."""

    def test_base_class_validation(self):
        """Test that base class validation works correctly."""

        # For code strings, PythonCodeNode now passes through all inputs without validation
        # Let's test with a function-based node instead which does validate
        def add_numbers(x: int, y: int) -> int:
            return x + y

        node = PythonCodeNode.from_function(func=add_numbers, name="validator")

        # Test missing required parameter
        with pytest.raises(
            NodeValidationError, match="Required parameter 'y' not provided"
        ):
            node.execute(x=5)  # Missing y

        # Test type conversion
        result = node.execute(x=5, y="10")  # String should be converted to int
        assert result == {"result": 15}

        # Test normal execution
        result = node.execute(x=5, y=10)
        assert result == {"result": 15}

    def test_code_string_node_no_validation(self):
        """Test that code string nodes don't validate inputs."""
        # Create a code string node - these don't validate inputs
        code_node = PythonCodeNode(
            name="code_validator",
            code="result = x + y",
            input_types={"x": int, "y": int},
            output_type=int,
        )

        # Code string nodes accept any inputs (no validation)
        with pytest.raises(Exception):  # Will fail at execution, not validation
            code_node.execute(x=5)  # Missing y - will fail at execution

        # Direct executor.execute_code works the same way
        result = code_node.executor.execute_code(code_node.code, {"x": 5, "y": 10})
        assert result == {"result": 15}

    def test_type_validation_issue(self):
        """Test that type validation correctly catches mismatches."""
        # Create test data
        df = pd.DataFrame(
            {
                "Total Claim Amount": [100, 200, 300, 400, 500],
                "Name": ["A", "B", "C", "D", "E"],
            }
        )

        # Define function with str threshold
        def custom_filter(data: pd.DataFrame, threshold: str) -> pd.DataFrame:
            # This will actually fail at runtime since we can't compare with string
            return data[data["Total Claim Amount"] > threshold].to_dict(
                orient="records"
            )

        # Create node
        node = PythonCodeNode.from_function(func=custom_filter, name="threshold_filter")

        # Check parameters
        params = node.get_parameters()
        assert params["threshold"].type == str

        # The float will be converted to string, but this will cause a runtime error
        # when trying to compare numbers with string
        with pytest.raises(
            NodeExecutionError, match="Invalid comparison between dtype=int64 and str"
        ):
            node.execute(data=df, threshold=1000.0)

    def test_trace_validation_flow(self):
        """Trace how validation works in PythonCodeNode."""

        # Create a node with typed inputs
        def add(x: int, y: int) -> int:
            return x + y

        node = PythonCodeNode.from_function(func=add, name="adder")

        # Verify parameters
        params = node.get_parameters()
        assert "x" in params
        assert "y" in params
        assert params["x"].type == int
        assert params["y"].type == int

        # Test missing parameter
        with pytest.raises(
            NodeValidationError, match="Required parameter 'y' not provided"
        ):
            node.execute(x=5)  # Missing y

        # Test type conversion
        result = node.execute(x=5, y="10")
        assert result == {"result": 15}

        # Test normal execution
        result = node.execute(x=5, y=10)
        assert result == {"result": 15}

    def test_type_conversion_behavior(self):
        """Test how validation handles type conversion."""
        # Create test data
        df = pd.DataFrame(
            {
                "Total Claim Amount": [100, 200, 300, 400, 500],
                "Name": ["A", "B", "C", "D", "E"],
            }
        )

        # Define function with str threshold
        def custom_filter(data: pd.DataFrame, threshold: str) -> dict:
            # Convert back to float for comparison
            threshold_float = float(threshold)
            filtered = data[data["Total Claim Amount"] > threshold_float]
            return {
                "result": {"filtered_count": len(filtered), "threshold_used": threshold}
            }

        # Create node
        node = PythonCodeNode.from_function(func=custom_filter, name="threshold_filter")

        # Pass a float, expect it to be converted to str
        result = node.execute(data=df, threshold=1000.0)
        # Note: PythonCodeNode wraps the return value in 'result', so we have double nesting
        assert result["result"]["result"]["filtered_count"] == 0
        assert result["result"]["result"]["threshold_used"] == "1000.0"

        # Test with actual string
        result2 = node.execute(data=df, threshold="300")
        assert result2["result"]["result"]["filtered_count"] == 2
        assert result2["result"]["result"]["threshold_used"] == "300"

    def test_strict_type_check(self):
        """Test a case where type conversion should fail."""

        # Define function expecting a complex type that can't be converted
        def process_data(data: pd.DataFrame) -> dict:
            return {"result": {"rows": len(data)}}

        node = PythonCodeNode.from_function(func=process_data, name="processor")

        # This should fail - can't convert string to DataFrame
        with pytest.raises(
            NodeValidationError, match="Input 'data' must be of type DataFrame"
        ):
            node.execute(data="not a dataframe")
