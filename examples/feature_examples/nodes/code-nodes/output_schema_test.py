"""Example demonstrating output schema validation in Kailash nodes."""

from typing import Any, Dict

from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.sdk_exceptions import NodeValidationError


class DataProcessorNode(Node):
    """Example node that processes data with output schema validation."""

    metadata = NodeMetadata(
        name="DataProcessorNode",
        description="Processes input data and produces validated outputs",
        version="1.0.0",
        tags={"data", "processing", "validation"},
    )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="List of numbers to process",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform: sum, average, or stats",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output schema for validation."""
        return {
            "result": NodeParameter(
                name="result",
                type=float,
                required=True,
                description="Calculation result",
            ),
            "count": NodeParameter(
                name="count",
                type=int,
                required=True,
                description="Number of items processed",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation performed",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                description="Additional processing metadata",
            ),
        }

    def run(self, data: list, operation: str) -> Dict[str, Any]:
        """Process the data according to the specified operation."""
        if not data:
            raise ValueError("Data list cannot be empty")

        if operation == "sum":
            result = sum(data)
        elif operation == "average":
            result = sum(data) / len(data)
        elif operation == "stats":
            result = {"min": min(data), "max": max(data), "mean": sum(data) / len(data)}
            # Note: This is intentionally wrong - stats returns a dict but schema expects float
            # This will demonstrate the schema validation
        else:
            raise ValueError(f"Unknown operation: {operation}")

        return {
            "result": result,
            "count": len(data),
            "operation": operation,
            "metadata": {"processed_at": "2024-01-01T00:00:00"},
        }


def main():
    """Demonstrate output schema validation."""
    print("=== Output Schema Validation Example ===\n")

    # Example 1: Valid outputs
    print("1. Valid operation (sum):")
    try:
        processor = DataProcessorNode(data=[1, 2, 3, 4, 5], operation="sum")
        result = processor.execute()
        print(f"✓ Success: {result}\n")
    except Exception as e:
        print(f"✗ Error: {e}\n")

    # Example 2: Valid operation (average)
    print("2. Valid operation (average):")
    try:
        processor = DataProcessorNode(data=[10, 20, 30], operation="average")
        result = processor.execute()
        print(f"✓ Success: {result}\n")
    except Exception as e:
        print(f"✗ Error: {e}\n")

    # Example 3: Invalid operation (stats) - returns dict instead of float
    print("3. Invalid operation (stats) - schema violation:")
    try:
        processor = DataProcessorNode(data=[1, 2, 3], operation="stats")
        result = processor.execute()
        print(f"✗ Should have failed: {result}\n")
    except NodeValidationError as e:
        print(f"✓ Correctly caught schema violation: {e}\n")

    # Example 4: Custom node without output schema
    class SimpleNode(Node):
        """Node without output schema - only JSON validation."""

        metadata = NodeMetadata(
            name="SimpleNode", description="Simple node without output schema"
        )

        def get_parameters(self) -> Dict[str, NodeParameter]:
            return {"value": NodeParameter(name="value", type=int, required=True)}

        def run(self, value: int) -> Dict[str, Any]:
            return {
                "result": value * 2,
                "any_field": "works",
                "nested": {"data": [1, 2, 3]},
            }

    print("4. Node without output schema (flexible outputs):")
    try:
        simple = SimpleNode(value=42)
        result = simple.execute()
        print(f"✓ Success: {result}\n")
    except Exception as e:
        print(f"✗ Error: {e}\n")

    # Example 5: Type conversion in outputs
    class TypeConversionNode(Node):
        """Node that demonstrates type conversion in outputs."""

        metadata = NodeMetadata(
            name="TypeConversionNode", description="Demonstrates output type conversion"
        )

        def get_parameters(self) -> Dict[str, NodeParameter]:
            return {}

        def get_output_schema(self) -> Dict[str, NodeParameter]:
            return {
                "integer": NodeParameter(name="integer", type=int, required=True),
                "string": NodeParameter(name="string", type=str, required=True),
                "float": NodeParameter(name="float", type=float, required=True),
            }

        def run(self) -> Dict[str, Any]:
            # Return wrong types that can be converted
            return {
                "integer": "42",  # String to int
                "string": 123,  # Int to string
                "float": "3.14",  # String to float
            }

    print("5. Type conversion in outputs:")
    try:
        converter = TypeConversionNode()
        result = converter.execute()
        print("✓ Types converted successfully:")
        for key, value in result.items():
            print(f"  {key}: {value} (type: {type(value).__name__})")
        print()
    except Exception as e:
        print(f"✗ Error: {e}\n")


if __name__ == "__main__":
    main()
