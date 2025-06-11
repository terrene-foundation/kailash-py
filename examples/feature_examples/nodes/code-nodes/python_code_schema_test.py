"""Example demonstrating Python code nodes with explicit schemas."""

from typing import Any

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.sdk_exceptions import NodeValidationError


def main():
    """Demonstrate PythonCodeNode with input and output schemas."""
    print("=== Python Code Node with Schemas Example ===\n")

    # Example 1: Data transformation with schemas
    print("1. Data Transformation with Schemas")
    print("-" * 35)

    def transform_user_data(
        user_id: int, name: str, age: int, active: bool = True
    ) -> dict[str, Any]:
        """Transform user data into a standardized format."""
        return {
            "id": user_id,
            "display_name": name.upper(),
            "age_group": "adult" if age >= 18 else "minor",
            "status": "active" if active else "inactive",
            "metadata": {"processed": True, "version": "2.0"},
        }

    # Define comprehensive schemas
    user_input_schema = {
        "user_id": NodeParameter(
            name="user_id",
            type=int,
            required=True,
            description="Unique user identifier",
        ),
        "name": NodeParameter(
            name="name", type=str, required=True, description="User's full name"
        ),
        "age": NodeParameter(
            name="age", type=int, required=True, description="User's age in years"
        ),
        "active": NodeParameter(
            name="active",
            type=bool,
            required=False,
            default=True,
            description="Whether user is active",
        ),
    }

    user_output_schema = {
        "id": NodeParameter(name="id", type=int, required=True, description="User ID"),
        "display_name": NodeParameter(
            name="display_name",
            type=str,
            required=True,
            description="Formatted display name",
        ),
        "age_group": NodeParameter(
            name="age_group", type=str, required=True, description="Age classification"
        ),
        "status": NodeParameter(
            name="status", type=str, required=True, description="User status"
        ),
        "metadata": NodeParameter(
            name="metadata", type=dict, required=True, description="Processing metadata"
        ),
    }

    # Create node with explicit schemas
    user_transformer = PythonCodeNode.from_function(
        transform_user_data,
        name="UserDataTransformer",
        description="Transforms raw user data into standardized format",
        input_schema=user_input_schema,
        output_schema=user_output_schema,
    )

    # Test the transformer
    try:
        result = user_transformer.execute(user_id=12345, name="John Doe", age=25)
        print(f"Transformed data: {result}")

        # Test with optional parameter
        result2 = user_transformer.execute(
            user_id=67890, name="Jane Smith", age=17, active=False
        )
        print(f"Minor user: {result2}")

    except Exception as e:
        print(f"Error: {e}")

    print()

    # Example 2: Stateful processing with class
    print("2. Stateful Processing with Class-based Node")
    print("-" * 40)

    class DataAggregator:
        """Aggregates data across multiple invocations."""

        def __init__(self):
            self.total_count = 0
            self.total_sum = 0.0
            self.values = []

        def process(self, values: list, operation: str = "sum") -> dict[str, Any]:
            """Process a batch of values."""
            self.values.extend(values)
            self.total_count += len(values)

            if operation == "sum":
                batch_result = sum(values)
                self.total_sum += batch_result
            elif operation == "average":
                batch_result = sum(values) / len(values) if values else 0
            elif operation == "max":
                batch_result = max(values) if values else None
            else:
                raise ValueError(f"Unknown operation: {operation}")

            return {
                "batch_result": batch_result,
                "batch_size": len(values),
                "total_processed": self.total_count,
                "running_sum": self.total_sum,
                "operation": operation,
            }

    # Define schemas for the aggregator
    aggregator_input = {
        "values": NodeParameter(
            name="values",
            type=list,
            required=True,
            description="List of numeric values to process",
        ),
        "operation": NodeParameter(
            name="operation",
            type=str,
            required=False,
            default="sum",
            description="Operation to perform: sum, average, or max",
        ),
    }

    aggregator_output = {
        "batch_result": NodeParameter(
            name="batch_result",
            type=float,
            required=True,
            description="Result of the batch operation",
        ),
        "batch_size": NodeParameter(
            name="batch_size",
            type=int,
            required=True,
            description="Number of values in this batch",
        ),
        "total_processed": NodeParameter(
            name="total_processed",
            type=int,
            required=True,
            description="Total values processed across all batches",
        ),
        "running_sum": NodeParameter(
            name="running_sum",
            type=float,
            required=True,
            description="Running sum of all values",
        ),
        "operation": NodeParameter(
            name="operation", type=str, required=True, description="Operation performed"
        ),
    }

    # Create aggregator node
    aggregator = PythonCodeNode.from_class(
        DataAggregator,
        name="DataAggregator",
        description="Stateful data aggregation across batches",
        input_schema=aggregator_input,
        output_schema=aggregator_output,
    )

    # Process multiple batches
    try:
        batch1 = aggregator.execute(values=[1, 2, 3, 4, 5])
        print(f"Batch 1: {batch1}")

        batch2 = aggregator.execute(values=[6, 7, 8], operation="average")
        print(f"Batch 2: {batch2}")

        batch3 = aggregator.execute(values=[9, 10], operation="max")
        print(f"Batch 3: {batch3}")

        print(f"Total processed: {batch3['total_processed']} values")

    except Exception as e:
        print(f"Error: {e}")

    print()

    # Example 3: Schema validation in action
    print("3. Schema Validation Examples")
    print("-" * 28)

    def strict_calculator(a: float, b: float, operation: str) -> dict[str, Any]:
        """Strict calculator with validation."""
        if operation not in ["add", "subtract", "multiply", "divide"]:
            raise ValueError(f"Invalid operation: {operation}")

        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            if b == 0:
                raise ValueError("Division by zero")
            result = a / b

        return {"result": result, "operation": operation, "inputs": {"a": a, "b": b}}

    # Strict schemas
    calc_input = {
        "a": NodeParameter(
            name="a", type=float, required=True, description="First operand"
        ),
        "b": NodeParameter(
            name="b", type=float, required=True, description="Second operand"
        ),
        "operation": NodeParameter(
            name="operation",
            type=str,
            required=True,
            description="Operation: add, subtract, multiply, or divide",
        ),
    }

    calc_output = {
        "result": NodeParameter(
            name="result", type=float, required=True, description="Calculation result"
        ),
        "operation": NodeParameter(
            name="operation", type=str, required=True, description="Operation performed"
        ),
        "inputs": NodeParameter(
            name="inputs", type=dict, required=True, description="Input values used"
        ),
    }

    calculator = PythonCodeNode.from_function(
        strict_calculator,
        name="StrictCalculator",
        input_schema=calc_input,
        output_schema=calc_output,
    )

    # Test validation
    print("Testing input validation:")
    try:
        # Valid operation
        result = calculator.execute(a=10, b=5, operation="multiply")
        print(f"✓ Valid: {result}")

        # Type conversion
        result = calculator.execute(a="15", b=3, operation="divide")
        print(f"✓ Type conversion: {result}")

        # Missing required input
        try:
            result = calculator.execute(a=10, operation="add")
            print("✗ Should have failed")
        except NodeValidationError as e:
            print(f"✓ Caught missing input: {e}")

        # Invalid operation (caught at runtime, not schema)
        try:
            result = calculator.execute(a=10, b=5, operation="power")
            print("✗ Should have failed")
        except Exception as e:
            print(f"✓ Caught invalid operation: {e}")

    except Exception as e:
        print(f"Error: {e}")

    print("\n=== Summary ===")
    print("PythonCodeNode with explicit schemas provides:")
    print("- Type validation for inputs and outputs")
    print("- Automatic type conversion when possible")
    print("- Clear error messages for validation failures")
    print("- Documentation of expected inputs/outputs")
    print("- Flexibility to use schemas or rely on automatic inference")


if __name__ == "__main__":
    main()
