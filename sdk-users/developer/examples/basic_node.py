"""
Basic custom node example showing minimal implementation.

This example demonstrates:
- Correct parameter type usage (no generic types)
- Both required methods implemented
- Proper return types
"""

from typing import Any

from kailash.nodes.base import Node, NodeParameter


class BasicTransformNode(Node):
    """A simple node that transforms text."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define node parameters using basic types only."""
        return {
            "text": NodeParameter(
                name="text",
                type=str,  # ✅ Basic type, not Optional[str]
                required=True,
                description="Text to transform",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="uppercase",
                description="Transform operation: uppercase, lowercase, title",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the transformation."""
        text = kwargs["text"]
        operation = kwargs.get("operation", "uppercase")

        if operation == "uppercase":
            result = text.upper()
        elif operation == "lowercase":
            result = text.lower()
        elif operation == "title":
            result = text.title()
        else:
            result = text

        return {"transformed": result, "original": text, "operation": operation}


# Example usage
if __name__ == "__main__":
    # Create node instance
    node = BasicTransformNode(name="text_transform")

    # Check parameters
    print("Node parameters:")
    for name, param in node.get_parameters().items():
        print(f"  {name}: {param.type.__name__}, required={param.required}")

    # Test execution
    result = node.run(text="Hello World", operation="lowercase")
    print("\nExecution result:")
    print(result)
    # Output: {'transformed': 'hello world', 'original': 'Hello World', 'operation': 'lowercase'}
