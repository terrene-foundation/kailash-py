"""Simple test for PythonCodeNode functionality."""

import pytest
from kailash.nodes.code import (
    ClassWrapper,
    CodeExecutor,
    FunctionWrapper,
    PythonCodeNode,
)


def test_code_executor():
    """Test basic code execution."""
    executor = CodeExecutor()
    code = """
result = x + y
"""
    inputs = {"x": 5, "y": 3}
    outputs = executor.execute_code(code, inputs)
    print(f"Code execution result: {outputs['result']}")
    assert outputs["result"] == 8


def test_function_wrapper():
    """Test function wrapping."""

    def multiply(x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y

    wrapper = FunctionWrapper(multiply)
    node = wrapper.to_node(name="multiplier")

    result = node.execute(x=5, y=3)
    print(f"Function result: {result}")
    assert result["result"] == 15


def test_class_wrapper():
    """Test class wrapping."""

    class Accumulator:
        def __init__(self):
            self.total = 0

        def process(self, value: float) -> float:
            self.total += value
            return self.total

    # Test that each node execution creates a new instance
    # (stateful behavior requires using the same wrapper instance)
    wrapper = ClassWrapper(Accumulator)

    # First execution
    result1 = wrapper.execute({"value": 5.0})
    print(f"First class result: {result1}")
    assert result1["result"] == 5.0

    # Second execution on same wrapper instance maintains state
    result2 = wrapper.execute({"value": 3.0})
    print(f"Second class result: {result2}")
    assert result2["result"] == 8.0

    # Test node conversion (each execution creates new instance)
    node = wrapper.to_node(name="accumulator")
    result3 = node.execute(value=5.0)
    result4 = node.execute(value=3.0)
    print(f"Node results: {result3}, {result4}")
    # Each node execution creates a new instance, so no accumulation
    assert result3["result"] == 5.0
    assert result4["result"] == 3.0  # Not 8.0, because it's a new instance


def test_python_code_node():
    """Test PythonCodeNode directly."""
    # Test with code string
    code_node = PythonCodeNode(
        name="adder",
        code="result = a + b",
        input_types={"a": int, "b": int},
        output_type=int,
    )

    result = code_node.execute(a=10, b=20)
    print(f"Code node result: {result}")
    assert result["result"] == 30

    # Test with function that returns dict (JSON-serializable)
    def transform_data(data: list) -> dict:
        """Transform data and return summary."""
        values = [item["value"] for item in data]
        return {
            "count": len(values),
            "sum": sum(values),
            "doubled": [v * 2 for v in values],
        }

    func_node = PythonCodeNode.from_function(func=transform_data, name="transformer")

    data = [{"value": 1}, {"value": 2}, {"value": 3}]
    # Use run method - all outputs are now wrapped in "result" key
    result_dict = func_node.execute(data=data)
    print(f"Transform result: {result_dict}")
    # Function returns are now consistently wrapped in "result"
    actual_result = result_dict["result"]
    assert actual_result["count"] == 3
    assert actual_result["sum"] == 6
    assert actual_result["doubled"] == [2, 4, 6]

    # Test with a function that returns a non-dict value
    def compute_sum(values: list) -> int:
        """Compute sum of values."""
        return sum(values)

    sum_node = PythonCodeNode.from_function(func=compute_sum, name="summer")

    sum_result = sum_node.execute(values=[10, 20, 30])
    print(f"Sum result: {sum_result}")
    # Non-dict results are wrapped in {"result": value}
    assert sum_result == {"result": 60}
