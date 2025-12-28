"""Test Python code node with explicit input and output schemas."""

from typing import Any

import pytest
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.sdk_exceptions import NodeValidationError


def test_function_with_schemas():
    """Test function-based node with explicit schemas."""
    print("=== Testing Function with Schemas ===\n")

    # Define a simple function
    def process_data(x: int, y: int) -> dict[str, Any]:
        return {"sum": x + y, "product": x * y, "difference": x - y}

    # Define explicit input schema
    input_schema = {
        "x": NodeParameter(
            name="x", type=int, required=True, description="First number"
        ),
        "y": NodeParameter(
            name="y", type=int, required=True, description="Second number"
        ),
    }

    # Define explicit output schema
    output_schema = {
        "sum": NodeParameter(
            name="sum", type=int, required=True, description="Sum of x and y"
        ),
        "product": NodeParameter(
            name="product", type=int, required=True, description="Product of x and y"
        ),
        "difference": NodeParameter(
            name="difference",
            type=int,
            required=True,
            description="Difference of x and y",
        ),
    }

    # Create node with schemas
    node = PythonCodeNode.from_function(
        process_data,
        name="Calculator",
        input_schema=input_schema,
        output_schema=output_schema,
    )

    # Test 1: Valid execution
    try:
        result = node.execute(x=10, y=5)
        print(f"✓ Valid execution: {result}")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

    # Test 2: Invalid input type
    try:
        result = node.execute(x="10", y=5)  # String instead of int
        print(f"✓ Type conversion successful: {result}")
    except NodeValidationError as e:
        print(f"✗ Type validation failed: {e}")

    # Test 3: Missing required input
    try:
        result = node.execute(x=10)  # Missing 'y'
        print("✗ Should have failed for missing input")
    except NodeValidationError as e:
        print(f"✓ Correctly caught missing input: {e}")

    print()


def test_class_with_schemas():
    """Test class-based node with explicit schemas."""
    print("=== Testing Class with Schemas ===\n")

    class DataProcessor:
        def __init__(self):
            self.count = 0

        def process(self, data: list) -> dict[str, Any]:
            self.count += 1
            return {
                "length": len(data),
                "first": data[0] if data else None,
                "last": data[-1] if data else None,
                "process_count": self.count,
            }

    # Define schemas - use object for flexible types
    input_schema = {
        "data": NodeParameter(
            name="data", type=list, required=True, description="List of data to process"
        )
    }

    output_schema = {
        "length": NodeParameter(
            name="length", type=int, required=True, description="Number of items"
        ),
        "first": NodeParameter(
            name="first",
            type=object,  # Use object instead of Any
            required=False,
            description="First item",
        ),
        "last": NodeParameter(
            name="last",
            type=object,  # Use object instead of Any
            required=False,
            description="Last item",
        ),
        "process_count": NodeParameter(
            name="process_count",
            type=int,
            required=True,
            description="Number of times processed",
        ),
    }

    # Create node
    node = PythonCodeNode.from_class(
        DataProcessor,
        name="ListProcessor",
        input_schema=input_schema,
        output_schema=output_schema,
    )

    # Test execution
    try:
        result1 = node.execute(data=[1, 2, 3, 4, 5])
        print(f"✓ First execution: {result1}")

        result2 = node.execute(data=["a", "b", "c"])
        print(f"✓ Second execution: {result2}")
        print(f"✓ Process count incremented: {result2['process_count']}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()

    print()


def test_code_string_with_schemas():
    """Test code string with explicit schemas."""
    print("=== Testing Code String with Schemas ===\n")

    code = """
def analyze_text(text: str) -> dict:
    words = text.split()
    return {
        "word_count": len(words),
        "char_count": len(text),
        "unique_words": len(set(words))
    }

# Entry point
result = analyze_text(text)
"""

    # Define schemas
    input_schema = {
        "text": NodeParameter(
            name="text", type=str, required=True, description="Text to analyze"
        )
    }

    output_schema = {
        "word_count": NodeParameter(
            name="word_count", type=int, required=True, description="Number of words"
        ),
        "char_count": NodeParameter(
            name="char_count",
            type=int,
            required=True,
            description="Number of characters",
        ),
        "unique_words": NodeParameter(
            name="unique_words",
            type=int,
            required=True,
            description="Number of unique words",
        ),
    }

    # Create node
    node = PythonCodeNode(
        name="TextAnalyzer",
        code=code,
        input_schema=input_schema,
        output_schema=output_schema,
    )

    # Test execution
    try:
        result = node.execute(text="hello world hello python")
        print(f"✓ Text analysis: {result}")
    except Exception as e:
        print(f"✗ Error: {e}")

    print()


def test_output_schema_violations():
    """Test output schema validation failures."""
    print("=== Testing Output Schema Violations ===\n")

    def bad_function(x: int) -> dict[str, Any]:
        # This violates the schema - returns string instead of int
        return {"value": str(x), "doubled": x * 2}  # Wrong type!

    output_schema = {
        "value": NodeParameter(
            name="value", type=int, required=True, description="Original value"
        ),
        "doubled": NodeParameter(
            name="doubled", type=int, required=True, description="Doubled value"
        ),
    }

    node = PythonCodeNode.from_function(
        bad_function, name="BadFunction", output_schema=output_schema
    )

    # Test execution - this should fail due to type mismatch
    try:
        result = node.execute(x=42)
        print(f"✓ Type conversion worked: {result}")
        print("  Note: String '42' was converted to int 42")
    except NodeValidationError as e:
        print(f"✓ Correctly caught output type violation: {e}")

    # Test missing required output
    def missing_output(x: int) -> dict[str, Any]:
        # Missing 'doubled' field
        return {"value": x}

    node2 = PythonCodeNode.from_function(
        missing_output, name="MissingOutput", output_schema=output_schema
    )

    try:
        result = node2.execute(x=42)
        print("✗ Should have failed for missing output")
    except NodeValidationError as e:
        print(f"✓ Correctly caught missing output: {e}")

    # Test invalid type conversion
    def really_bad_function(x: int) -> dict[str, Any]:
        return {
            "value": [1, 2, 3],  # List instead of int - can't convert
            "doubled": x * 2,
        }

    node3 = PythonCodeNode.from_function(
        really_bad_function, name="ReallyBadFunction", output_schema=output_schema
    )

    try:
        result = node3.execute(x=42)
        print("✗ Should have failed for invalid type")
    except NodeValidationError as e:
        print(f"✓ Correctly caught invalid type: {e}")

    print()


def test_mixed_schemas():
    """Test node with explicit input schema but automatic output."""
    print("=== Testing Mixed Schema Definitions ===\n")

    def flexible_function(data: list, threshold: float = 0.5) -> dict[str, Any]:
        filtered = [x for x in data if x > threshold]
        return {
            "filtered": filtered,
            "count": len(filtered),
            "threshold": threshold,
            "metadata": {"version": "1.0"},
        }

    # Define only input schema
    input_schema = {
        "data": NodeParameter(
            name="data", type=list, required=True, description="List of numbers"
        ),
        "threshold": NodeParameter(
            name="threshold",
            type=float,
            required=False,
            default=0.5,
            description="Filter threshold",
        ),
    }

    # Create node with only input schema
    node = PythonCodeNode.from_function(
        flexible_function,
        name="FlexibleFilter",
        input_schema=input_schema,
        # No output_schema - allows any output
    )

    # Test execution
    try:
        result = node.execute(data=[0.1, 0.6, 0.3, 0.8, 0.4])
        print(f"✓ Execution with default threshold: {result}")

        result2 = node.execute(data=[0.1, 0.6, 0.3, 0.8, 0.4], threshold=0.7)
        print(f"✓ Execution with custom threshold: {result2}")
    except Exception as e:
        print(f"✗ Error: {e}")

    print()


def test_schema_flexibility():
    """Test schema flexibility and edge cases."""
    print("=== Testing Schema Flexibility ===\n")

    # Test with None as parameter type (allows any type)
    def any_type_function(value) -> dict[str, Any]:
        return {"type": type(value).__name__, "value": value}

    input_schema = {
        "value": NodeParameter(
            name="value",
            type=object,  # Accept any type
            required=True,
            description="Any value",
        )
    }

    output_schema = {
        "type": NodeParameter(
            name="type", type=str, required=True, description="Type name"
        ),
        "value": NodeParameter(
            name="value",
            type=object,  # Any type output
            required=True,
            description="Original value",
        ),
    }

    node = PythonCodeNode.from_function(
        any_type_function,
        name="TypeInspector",
        input_schema=input_schema,
        output_schema=output_schema,
    )

    # Test with different types
    try:
        print(f"Integer: {node.execute(value=42)}")
        print(f"String: {node.execute(value='hello')}")
        print(f"List: {node.execute(value=[1, 2, 3])}")
        print(f"Dict: {node.execute(value={'key': 'value'})}")
    except Exception as e:
        print(f"✗ Error: {e}")

    print()
