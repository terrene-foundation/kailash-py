"""
Data processing node example with complex type handling.

This example demonstrates:
- Using 'Any' type for complex data structures
- Runtime type validation
- Error handling
- Processing lists and dictionaries
"""

from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter


class DataProcessorNode(Node):
    """Process structured data with filtering and transformation."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters using Any for complex types."""
        return {
            "data": NodeParameter(
                name="data",
                type=Any,  # ✅ Use Any instead of List[Dict[str, Any]]
                required=True,
                description="List of dictionaries to process",
            ),
            "filters": NodeParameter(
                name="filters",
                type=dict,  # ✅ Basic dict type, not Dict[str, Any]
                required=False,
                default={},
                description="Filter criteria as key-value pairs",
            ),
            "transform": NodeParameter(
                name="transform",
                type=dict,
                required=False,
                default={},
                description="Field transformations to apply",
            ),
            "output_fields": NodeParameter(
                name="output_fields",
                type=list,  # ✅ Basic list type, not List[str]
                required=False,
                default=None,
                description="Fields to include in output",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Process the data with validation."""
        data = kwargs["data"]
        filters = kwargs.get("filters", {})
        transform = kwargs.get("transform", {})
        output_fields = kwargs.get("output_fields")

        # Runtime validation
        if not isinstance(data, list):
            raise ValueError(f"Data must be a list, got {type(data).__name__}")

        processed = []
        errors = []

        for idx, item in enumerate(data):
            try:
                # Validate item is a dict
                if not isinstance(item, dict):
                    errors.append(f"Item {idx} is not a dictionary")
                    continue

                # Apply filters
                if filters:
                    match = all(
                        item.get(key) == value for key, value in filters.items()
                    )
                    if not match:
                        continue

                # Apply transformations
                transformed = item.copy()
                for field, operation in transform.items():
                    if field in transformed:
                        if operation == "uppercase":
                            transformed[field] = str(transformed[field]).upper()
                        elif operation == "lowercase":
                            transformed[field] = str(transformed[field]).lower()
                        elif operation == "number":
                            try:
                                transformed[field] = float(transformed[field])
                            except (ValueError, TypeError):
                                pass

                # Filter output fields
                if output_fields:
                    transformed = {
                        k: v for k, v in transformed.items() if k in output_fields
                    }

                processed.append(transformed)

            except Exception as e:
                errors.append(f"Error processing item {idx}: {str(e)}")

        return {
            "processed": processed,
            "count": len(processed),
            "original_count": len(data),
            "errors": errors if errors else None,
        }


# Example usage
if __name__ == "__main__":
    # Create node
    node = DataProcessorNode(name="processor")

    # Test data
    test_data = [
        {"name": "Alice", "age": "30", "city": "NYC"},
        {"name": "Bob", "age": "25", "city": "LA"},
        {"name": "Charlie", "age": "35", "city": "NYC"},
        "invalid_item",  # This will be caught
    ]

    # Process with filters and transformations
    result = node.run(
        data=test_data,
        filters={"city": "NYC"},
        transform={"name": "uppercase", "age": "number"},
        output_fields=["name", "age"],
    )

    print("Processing result:")
    print(f"Processed items: {result['processed']}")
    print(f"Count: {result['count']}/{result['original_count']}")
    print(f"Errors: {result['errors']}")
