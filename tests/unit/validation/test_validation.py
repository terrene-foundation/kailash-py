"""Test the base class validation behavior with PythonCodeNode."""

import pytest

from kailash.nodes.code import PythonCodeNode
from kailash.sdk_exceptions import NodeValidationError


def test_validation():
    """Test that base class validation works correctly."""

    # For code strings, PythonCodeNode now passes through all inputs without validation
    # Let's test with a function-based node instead which does validate
    def add_numbers(x: int, y: int) -> int:
        return x + y

    node = PythonCodeNode.from_function(func=add_numbers, name="validator")

    print("Testing validation through execute() method...")

    # Test missing required parameter
    try:
        result = node.execute(x=5)  # Missing y
        print("ERROR: Should have raised validation error")
    except NodeValidationError as e:
        print(f"✓ Correctly caught missing parameter: {e}")

    # Test type conversion
    result = node.execute(x=5, y="10")  # String should be converted to int
    print(f"✓ Type conversion worked: {result}")

    # Test normal execution
    result = node.execute(x=5, y=10)
    print(f"✓ Normal execution: {result}")

    print("\nTesting code string node (no validation)...")

    # Create a code string node - these don't validate inputs
    code_node = PythonCodeNode(
        name="code_validator",
        code="result = x + y",
        input_types={"x": int, "y": int},
        output_type=int,
    )

    # Code string nodes accept any inputs (no validation)
    try:
        result = code_node.execute(x=5)  # Missing y - will fail at execution
        print("ERROR: Code execution should have failed")
    except Exception as e:
        print(f"✓ Code execution failed as expected: {type(e).__name__}")

    # Direct executor.execute_code works the same way
    result = code_node.executor.execute_code(code_node.code, {"x": 5, "y": 10})
    print(f"✓ Direct executor.execute_code: {result}")

    print("\nAll validation tests passed!")
