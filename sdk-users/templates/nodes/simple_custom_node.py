"""
Template: Simple Custom Node
Purpose: Minimal template for creating a custom node
Use Case: When you need custom processing logic

This template shows the essential parts of a custom node.
"""

from typing import Any

from kailash.nodes.base import Node, NodeParameter


class MyCustomNode(Node):
    """A simple custom node that processes data."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the node's parameters."""
        return {
            "multiplier": NodeParameter(
                name="multiplier",
                type=float,
                required=False,
                default=1.0,
                description="Value to multiply by",
            ),
            "add_suffix": NodeParameter(
                name="add_suffix",
                type=str,
                required=False,
                default="",
                description="Suffix to add to string fields",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic."""
        # Get parameters
        data = kwargs.get("data", [])
        multiplier = kwargs.get("multiplier", 1.0)
        suffix = kwargs.get("add_suffix", "")

        # Process data
        if isinstance(data, list):
            result = []
            for item in data:
                new_item = item.copy() if isinstance(item, dict) else item

                # Example: multiply numeric fields
                if isinstance(new_item, dict):
                    for key, value in new_item.items():
                        if isinstance(value, (int, float)):
                            new_item[key] = value * multiplier
                        elif isinstance(value, str) and suffix:
                            new_item[key] = value + suffix

                result.append(new_item)
        else:
            result = data

        return {"data": result}


# Usage example
if __name__ == "__main__":
    from kailash.workflow.graph import Workflow

    # Create workflow with custom node
    workflow = Workflow()

    custom_node = MyCustomNode(multiplier=2.0, add_suffix="_processed")
    workflow.add_node("processor", custom_node)

    # Test with sample data
    test_data = [{"name": "Item1", "value": 10}, {"name": "Item2", "value": 20}]

    # Note: In a real workflow, data would come from connected nodes
    # This is just for demonstration
    print("Custom node created successfully!")
