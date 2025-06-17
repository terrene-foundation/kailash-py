# Custom Node Creation

```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter, register_node

@register_node()
class MyCustomNode(Node):
    """Process data with a threshold filter.

    Custom node that filters input data based on a configurable threshold.
    """

    def __init__(self, **kwargs):
        """Initialize the node with configuration."""
        super().__init__(**kwargs)
        # Access config during initialization if needed
        self.threshold = self.config.get("threshold", 0.5)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters (REQUIRED method)."""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to process"
            ),
            "options": NodeParameter(
                name="options",
                type=dict,
                required=False,
                default={},
                description="Processing options"
            )
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output schema for validation (OPTIONAL method)."""
        return {
            "result": NodeParameter(
                name="result",
                type=dict,
                required=True,
                description="Processing result with filtered data and count"
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=True,
                description="Processing metadata"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node logic (REQUIRED method).

        This method receives validated parameters as keyword arguments.
        """
        # Get inputs
        data = kwargs["data"]
        options = kwargs.get("options", {})

        # Use configuration from initialization
        threshold = options.get("threshold", self.threshold)

        # Process data
        filtered = [item for item in data if item > threshold]

        # Return outputs matching the schema
        return {
            "result": {
                "filtered": filtered,
                "count": len(filtered),
                "threshold_used": threshold
            },
            "metadata": {
                "total_items": len(data),
                "filtered_items": len(filtered),
                "filter_rate": len(filtered) / len(data) if data else 0
            }
        }

```
