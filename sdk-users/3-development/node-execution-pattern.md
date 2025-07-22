# Node Execution Pattern - Critical Documentation

## Overview

This document clarifies the **critical distinction** between how users interact with nodes and how node developers implement them. This pattern is fundamental to the Kailash SDK architecture.

## The Two-Method Pattern

### 1. `execute(**kwargs)` - Public API (Users Call This)

```python
# This is what users call
result = node.execute(
    input_data="data.csv",
    threshold=0.8
)
```

**Purpose**:
- Public-facing API method
- Handles parameter validation
- Manages error handling and recovery
- Collects execution metrics
- Provides consistent interface across all nodes

**Never Override This**: Node implementations should NEVER override `execute()` as it breaks the framework's validation and error handling.

### 2. `run(**kwargs)` - Protected Implementation (Nodes Implement This)

```python
@register_node
class MyCustomNode(Node):
    def run(self, **kwargs) -> dict[str, Any]:
        """This is what node developers implement."""
        input_data = kwargs.get("input_data")
        threshold = kwargs.get("threshold", 0.5)

        # Your actual node logic here
        result = process_data(input_data, threshold)

        return {"output": result}
```

**Purpose**:
- Contains the actual node logic
- Receives pre-validated parameters
- Focuses purely on business logic
- Returns results as a dictionary

## Complete Example

### Creating a Custom Node (For Node Developers)

```python
from kailash.nodes.base import Node, NodeParameter, register_node
from typing import Dict, Any

@register_node
class DataProcessorNode(Node):
    """Example custom node showing correct implementation pattern."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "input_file": NodeParameter(
                type=str,
                required=True,
                description="Path to input data file"
            ),
            "threshold": NodeParameter(
                type=float,
                required=False,
                default=0.5,
                description="Processing threshold"
            ),
            "action": NodeParameter(
                type=str,
                required=False,
                default="process",
                description="Action to perform",
                choices=["process", "validate", "transform"]
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Implement the node logic here.

        This method receives validated parameters and should:
        1. Extract parameters from kwargs
        2. Perform the node's operation
        3. Return results as a dictionary
        """
        # Extract parameters
        input_file = kwargs.get("input_file")
        threshold = kwargs.get("threshold", 0.5)
        action = kwargs.get("action", "process")

        # Perform operation based on action
        if action == "process":
            result = self._process_data(input_file, threshold)
        elif action == "validate":
            result = self._validate_data(input_file)
        elif action == "transform":
            result = self._transform_data(input_file)
        else:
            raise ValueError(f"Unknown action: {action}")

        # Return results
        return {
            "success": True,
            "action": action,
            "data": result,
            "metadata": {
                "threshold_used": threshold,
                "input_file": input_file
            }
        }

    def _process_data(self, file_path: str, threshold: float) -> Any:
        """Private method for data processing."""
        # Implementation details
        pass

    def _validate_data(self, file_path: str) -> Any:
        """Private method for data validation."""
        # Implementation details
        pass

    def _transform_data(self, file_path: str) -> Any:
        """Private method for data transformation."""
        # Implementation details
        pass
```

### Using the Node (For SDK Users)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build workflow
workflow = WorkflowBuilder()

# Add the custom node
workflow.add_node(
    "DataProcessorNode",
    "processor",
    {
        "input_file": "/data/input.csv",
        "threshold": 0.8,
        "action": "process"  # Note: using 'action' not 'operation'
    }
)

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Or execute node directly
from kailash.nodes.data import DataProcessorNode

node = DataProcessorNode()
result = node.execute(
    input_file="/data/input.csv",
    threshold=0.8,
    action="validate"
)
```

## Common Mistakes and Fixes

### ❌ Mistake 1: Overriding execute()

```python
# WRONG - Don't do this!
class MyNode(Node):
    def execute(self, **kwargs):  # This breaks validation!
        return {"result": "data"}
```

### ✅ Fix: Implement run() instead

```python
# CORRECT
class MyNode(Node):
    def run(self, **kwargs):
        return {"result": "data"}
```

### ❌ Mistake 2: Using operation parameter

```python
# WRONG - Inconsistent with SDK conventions
def run(self, **kwargs):
    operation = kwargs.get("operation")  # Most nodes use 'action'
```

### ✅ Fix: Use action parameter

```python
# CORRECT - Consistent with majority of nodes
def run(self, **kwargs):
    action = kwargs.get("action", "default")
```

### ❌ Mistake 3: Calling run() directly

```python
# WRONG - Bypasses validation
result = node.run(input_data="file.csv")
```

### ✅ Fix: Always use execute()

```python
# CORRECT - Goes through validation
result = node.execute(input_data="file.csv")
```

## Execution Flow Diagram

```
User Code                    Framework                    Node Implementation
---------                    ---------                    ------------------
node.execute(params) ──────> validate_parameters()
                            check_required_params()
                            apply_defaults()
                            │
                            ├─> run(**validated_params) ──> Your node logic
                            │                                Returns dict
                            │<─────────────────────────────┘
                            │
                            handle_errors()
                            collect_metrics()
                            format_response()
                            │
                <───────────┘
Returns formatted result
```

## Benefits of This Pattern

1. **Validation**: All inputs are automatically validated against parameter schema
2. **Error Handling**: Consistent error messages and exception handling
3. **Metrics**: Automatic collection of execution time and success metrics
4. **Defaults**: Parameter defaults are applied consistently
5. **Type Safety**: Type checking happens before your code runs
6. **Documentation**: Parameters are self-documenting through schema

## Parameter Naming Conventions

For consistency across the SDK:

- Use `action` (not `operation`) for action selection parameters
- Use `file_path` (not `filename` or `path`) for file paths
- Use `timeout` (not `timeout_seconds`) for timeout values
- Use `retry_count` (not `retries` or `max_retries`) for retry attempts

## Summary

- **Users**: Always call `node.execute(**params)`
- **Node Developers**: Always implement `run(**kwargs)`
- **Framework**: Handles validation, errors, and metrics between the two
- **Never**: Override `execute()` in custom nodes
- **Always**: Use `action` parameter for consistency

This separation of concerns ensures robust, validated, and monitored node execution across the entire SDK.
