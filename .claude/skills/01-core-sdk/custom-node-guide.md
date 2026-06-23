---
name: custom-node-guide
description: "Create custom workflow nodes with register_callback. Use when asking 'custom node', 'create node', 'register_callback', 'node development', or 'extend workflow'."
---

# Custom Node Guide

Create custom workflow nodes using `register_callback` for domain-specific logic.

## Quick Start: Custom Node via Callback

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

# Define a custom node as a Python function
def text_transform(inputs: dict) -> dict:
    text = inputs.get("text", "")
    operation = inputs.get("operation", "uppercase")

    if operation == "uppercase":
        return {"result": text.upper()}
    elif operation == "lowercase":
        return {"result": text.lower()}
    elif operation == "reverse":
        return {"result": text[::-1]}
    else:
        raise ValueError(f"Unknown operation: {operation}")


# Register and use in a workflow
workflow = WorkflowBuilder()
workflow.register_callback("TextTransform", text_transform)
workflow.add_node("TextTransform", "transform_1", {
    "operation": "uppercase",
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), {
    "text": "hello world",
})

print(results["transform_1"]["result"])  # "HELLO WORLD"
```

## Input/Output Contract

Custom node functions receive a dict of inputs and must return a dict of outputs.

```python
def my_node(inputs: dict) -> dict:
    """
    Args:
        inputs: Dict with string keys and any-typed values.
                Includes both config params and workflow inputs.

    Returns:
        Dict with string keys. These become the node's outputs
        that downstream nodes can consume.
    """
    # Access inputs
    value = inputs.get("key", "default")

    # Return outputs
    return {"output_key": "processed_value"}
```

## Error Handling in Custom Nodes

```python
def validated_node(inputs: dict) -> dict:
    """Custom node with input validation and error handling."""
    # Validate required inputs
    data = inputs.get("data")
    if data is None:
        raise ValueError("'data' input is required")

    if not isinstance(data, str):
        raise TypeError(f"'data' must be a string, got {type(data).__name__}")

    # Process with error handling
    try:
        result = process_data(data)
        return {"result": result, "status": "success"}
    except Exception as e:
        return {"error": str(e), "status": "failed"}
```

## Connecting Custom Nodes

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

def fetch_data(inputs: dict) -> dict:
    url = inputs.get("url", "")
    # Simulate API call
    return {"data": f"Data from {url}", "status_code": 200}

def transform_data(inputs: dict) -> dict:
    data = inputs.get("data", "")
    return {"result": data.upper()}

workflow = WorkflowBuilder()
workflow.register_callback("FetchData", fetch_data)
workflow.register_callback("TransformData", transform_data)

workflow.add_node("FetchData", "fetcher", {"url": "https://api.example.com"})
workflow.add_node("TransformData", "transformer", {})
workflow.connect("fetcher", "data", "transformer", "data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(results["transformer"]["result"])
```

## Testing Custom Nodes

```python
import pytest

def text_transform(inputs: dict) -> dict:
    text = inputs.get("text", "")
    operation = inputs.get("operation", "uppercase")
    if operation == "uppercase":
        return {"result": text.upper()}
    elif operation == "lowercase":
        return {"result": text.lower()}
    else:
        raise ValueError(f"Unknown operation: {operation}")


# Tier 1: Unit test the function directly
def test_text_transform_uppercase():
    result = text_transform({"text": "hello", "operation": "uppercase"})
    assert result["result"] == "HELLO"

def test_text_transform_lowercase():
    result = text_transform({"text": "HELLO", "operation": "lowercase"})
    assert result["result"] == "hello"

def test_text_transform_invalid_operation():
    with pytest.raises(ValueError, match="Unknown operation"):
        text_transform({"text": "hello", "operation": "invalid"})


# Tier 1: Integration test with workflow
def test_text_transform_in_workflow():
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime import LocalRuntime

    workflow = WorkflowBuilder()
    workflow.register_callback("TextTransform", text_transform)
    workflow.add_node("TextTransform", "upper", {"operation": "uppercase"})

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build(), {"text": "hello"})
    assert results["upper"]["result"] == "HELLO"
```

## Best Practices

1. **Validate inputs early** -- Check for required inputs before processing
2. **Return structured outputs** -- Always return a dict with descriptive keys
3. **Handle errors gracefully** -- Raise ValueError for bad inputs, catch and report processing errors
4. **Keep nodes focused** -- Each node should do one thing well
5. **Test independently** -- Unit test the function directly, then test in a workflow
6. **Use descriptive names** -- Node type names should indicate what they do

<!-- Trigger Keywords: custom node, create node, register_callback, node development, extend workflow, custom function -->
