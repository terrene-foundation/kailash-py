# AsyncNode Implementation Guide

## 🚨 CRITICAL: AsyncNode API Usage

When working with AsyncNode subclasses, you MUST understand the execution API:

### 1. Node Implementation (for developers creating nodes)

```python
from kailash.nodes.base_async import AsyncNode

class MyAsyncNode(AsyncNode):
    # ✅ CORRECT: Implement async_run()
    async def async_run(self, **kwargs) -> Dict[str, Any]:
        # Your async logic here
        result = await some_async_operation()
        return {"result": result}

    # ❌ WRONG: Don't implement run()
    def run(self, **kwargs):
        # This will raise NotImplementedError!
        pass
```

### 2. Node Usage (for tests and external callers)

#### For Async Contexts (tests, async functions):
```python
# ✅ CORRECT: Use execute_async() in async contexts
@pytest.mark.asyncio
async def test_my_async_node():
    node = MyAsyncNode()
    result = await node.execute_async(param1="value1")
    assert result["success"] is True

# ❌ WRONG: Don't use execute() in async contexts
@pytest.mark.asyncio
async def test_my_async_node():
    node = MyAsyncNode()
    result = await node.execute(param1="value1")  # This won't work!
```

#### For Sync Contexts (regular functions):
```python
# ✅ CORRECT: Use execute() in sync contexts
def use_async_node_sync():
    node = MyAsyncNode()
    result = node.execute(param1="value1")  # Handles async internally
    return result

# ❌ WRONG: Don't try to await in sync contexts
def use_async_node_sync():
    node = MyAsyncNode()
    result = await node.execute_async(param1="value1")  # Syntax error!
```

### 3. NodeParameter Type Requirements

**CRITICAL**: All NodeParameter definitions MUST include a `type` field:

```python
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        # ✅ CORRECT: Include type field
        "value": NodeParameter(
            name="value",
            type=object,  # or str, int, dict, list, etc.
            required=False,
            description="Value to process"
        ),

        # ❌ WRONG: Missing type field
        "value": NodeParameter(
            name="value",
            required=False,
            description="Value to process"
        ),  # This will fail validation!
    }
```

### 4. Complete AsyncNode Example

```python
from typing import Any, Dict
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.base import NodeParameter, register_node

@register_node()
class ExampleAsyncNode(AsyncNode):
    """Example async node showing correct implementation."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,  # ✅ Type is required!
                required=True,
                description="Action to perform"
            ),
            "data": NodeParameter(
                name="data",
                type=dict,  # ✅ Type is required!
                required=False,
                default={},
                description="Data to process"
            )
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Implement async logic here."""
        action = kwargs.get("action")
        data = kwargs.get("data", {})

        # Async operation
        await asyncio.sleep(0.1)  # Simulate async work

        return {
            "success": True,
            "action": action,
            "processed_data": data
        }

# Test example
@pytest.mark.asyncio
async def test_example_async_node():
    node = ExampleAsyncNode()

    # ✅ CORRECT: Use execute_async in async test
    result = await node.execute_async(
        action="process",
        data={"key": "value"}
    )

    assert result["success"] is True
    assert result["action"] == "process"
```

## Common Mistakes and Solutions

### Mistake 1: Using run() instead of async_run()
```python
# ❌ WRONG
class MyAsyncNode(AsyncNode):
    def run(self, **kwargs):  # Wrong method!
        return {"result": "data"}

# ✅ CORRECT
class MyAsyncNode(AsyncNode):
    async def async_run(self, **kwargs):  # Correct method!
        return {"result": "data"}
```

### Mistake 2: Using execute() in async tests
```python
# ❌ WRONG
@pytest.mark.asyncio
async def test_node():
    result = await node.execute()  # execute() is not awaitable!

# ✅ CORRECT
@pytest.mark.asyncio
async def test_node():
    result = await node.execute_async()  # Use execute_async()!
```

### Mistake 3: Missing type in NodeParameter
```python
# ❌ WRONG
"param": NodeParameter(
    name="param",
    required=True,
    description="A parameter"
)  # Missing type!

# ✅ CORRECT
"param": NodeParameter(
    name="param",
    type=str,  # Type is required!
    required=True,
    description="A parameter"
)
```

### Mistake 4: Calling async methods from sync context
```python
# ❌ WRONG
def sync_function():
    result = await node.execute_async()  # Can't await in sync function!

# ✅ CORRECT
def sync_function():
    result = node.execute()  # Use sync execute()
```

## Quick Reference Table

| Context | Method to Call | Returns | Example |
|---------|---------------|---------|---------|
| Async test/function | `execute_async()` | Awaitable | `await node.execute_async(**params)` |
| Sync function | `execute()` | Dict | `node.execute(**params)` |
| Node implementation | `async_run()` | Dict | `async def async_run(self, **kwargs)` |

## Testing AsyncNodes

```python
import pytest
import asyncio
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_async_node():
    """Proper async node testing pattern."""
    node = MyAsyncNode()

    # Mock async dependencies
    node.some_async_method = AsyncMock(return_value="mocked")

    # Execute with execute_async
    result = await node.execute_async(
        param1="value1",
        param2="value2"
    )

    # Assertions
    assert result["success"] is True

    # Verify async method was called
    node.some_async_method.assert_called_once()
```

## Integration with Workflows

AsyncNodes work seamlessly with workflows:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("ExampleAsyncNode", "async_task", {
    "action": "process",
    "data": {"key": "value"}
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # Runtime handles async
```

## Summary

1. **Implement** `async_run()` in your AsyncNode subclass
2. **Use** `execute_async()` in async contexts (tests, async functions)
3. **Use** `execute()` in sync contexts (regular functions, workflows)
4. **Always** include `type` field in NodeParameter definitions
5. **Never** implement `run()` in AsyncNode subclasses
