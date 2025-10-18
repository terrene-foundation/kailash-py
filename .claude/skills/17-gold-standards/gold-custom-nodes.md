---
name: gold-custom-nodes
description: "Gold standard for custom node development. Use when asking 'create custom node', 'custom node standard', or 'node development'."
---

# Gold Standard: Custom Node Development

> **Skill Metadata**
> Category: `gold-standards`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`

## Custom Node Template

```python
from kailash.nodes.base import BaseNode
from typing import Dict, Any

class MyCustomNode(BaseNode):
    """Custom node for specific business logic.

    Parameters:
        input_data (str): Input data to process
        config (dict): Configuration options
    """

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the custom node logic.

        Args:
            context: Execution context with inputs and state

        Returns:
            Dict with outputs: {"result": processed_data}
        """
        input_data = context.get("input_data")
        config = context.get("config", {})

        # Your custom logic here
        result = self._process(input_data, config)

        return {"result": result}

    def _process(self, data: str, config: dict) -> str:
        """Private helper method for processing."""
        # Implementation
        return data.upper()

    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate required parameters."""
        required = ["input_data"]
        return all(key in params for key in required)
```

## Gold Standard Checklist

- [ ] Inherits from `BaseNode`
- [ ] Docstring with parameter descriptions
- [ ] `execute()` method returns Dict
- [ ] `validate_parameters()` implemented
- [ ] Type hints for all methods
- [ ] Error handling for invalid inputs
- [ ] Unit tests for execute logic
- [ ] Integration test in workflow

## Documentation

- **Custom Nodes**: [`# contrib (removed)/3-development/05-custom-nodes.md`](../../../../# contrib (removed)/3-development/05-custom-nodes.md)

<!-- Trigger Keywords: create custom node, custom node standard, node development, custom node gold standard -->
