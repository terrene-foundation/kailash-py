# Cycle Parameter Passing Guide

## Overview

Parameter passing in cyclic workflows is one of the most common sources of errors. This guide provides definitive patterns for correctly passing parameters through cycles, especially when using `PythonCodeNode`.

## Critical Rules

### 1. PythonCodeNode Output Mapping

**Rule**: `PythonCodeNode.from_function()` wraps outputs in a `result` dictionary.

```python
# ✅ CORRECT - Use dot notation for PythonCodeNode outputs
workflow.add_connection("counter", "result", "counter", "input")

# ❌ WRONG - Direct mapping doesn't work
workflow.add_connection("counter", "result", "counter", "input")
```

### 2. Initial Parameters for Cycles

**Rule**: Cycles need initial parameters on first iteration.

```python
# ✅ CORRECT - Provide initial parameters
runtime.execute(workflow, parameters={
    "counter": {"count": 0}  # Node-specific parameters
})

# ❌ WRONG - No initial parameters causes "parameter not provided" error
runtime.execute(workflow.build())
```

### 3. Convergence Check Syntax

**Rule**: Convergence checks use flattened field names, not dot notation.

```python
# ✅ CORRECT - Flattened field name
.converge_when("converged == True")

# ❌ WRONG - Dot notation in convergence check
.converge_when("result.converged == True")
```

## Complete Working Examples

### Example 1: Simple Self-Cycle

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Define counter function
def counter_func(count=0):
    new_count = count + 1
    return {
        "count": new_count,
        "converged": new_count >= 5
    }

# Add node
counter_node = PythonCodeNode.from_function(counter_func, name="counter")
workflow.add_node("counter", counter_node)

# Create cycle with proper mapping
workflow.create_cycle("counter_cycle") \
    .connect("counter", "counter", {"result.count": "count"}) \
    .max_iterations(10) \
    .converge_when("converged == True") \
    .build()

# Execute with initial parameters
runtime = LocalRuntime()
result, _ = runtime.execute(workflow, parameters={
    "counter": {"count": 0}
})

# Access results
print(result["counter"]["result"]["count"])  # Note: result.field structure
```

### Example 2: Two-Node Cycle

```python
# Node A: Processes data
node_a = PythonCodeNode.from_function(
    lambda value=1, increment=0: {
        "value": value + increment
    },
    name="node_a"
)

# Node B: Calculates increment
node_b = PythonCodeNode.from_function(
    lambda value: {
        "increment": 2 if value < 10 else 0,
        "converged": value >= 10,
        "final_value": value
    },
    name="node_b"
)

workflow.add_node("a", node_a)
workflow.add_node("b", node_b)

# Connect with proper dot notation
workflow.add_connection("a", "result", "b", "input")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Execute with initial parameters for node a
result, _ = runtime.execute(workflow, parameters={
    "a": {"value": 1, "increment": 0}
})
```

### Example 3: CycleAwareNode with State

```python
from kailash.nodes.base import NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode

class AccumulatorNode(CycleAwareNode):
    def get_parameters(self):
        return {
            # CRITICAL: Include 'name' parameter
            "value": NodeParameter(name="value", type=int, default=0),
            "threshold": NodeParameter(name="threshold", type=int, default=100)
        }

    def run(self, **kwargs):
        value = kwargs.get("value", 0)
        threshold = kwargs.get("threshold", 100)
        context = kwargs.get("context", {})

        # Get previous state
        total = self.get_previous_state(context).get("total", 0)

        # Update
        new_value = value + 10
        new_total = total + new_value

        return {
            "value": new_value,
            "total": new_total,
            "converged": new_total >= threshold,
            **self.set_cycle_state({"total": new_total})
        }

# For CycleAwareNode, mapping uses direct field names
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()
```

## Common Errors and Solutions

### Error: "Required parameter 'X' not provided"
**Cause**: Missing initial parameters or incorrect mapping.
**Solution**:
1. Provide initial parameters via `runtime.execute(workflow, parameters={...})`
2. Check mapping uses correct dot notation for PythonCodeNode

### Error: "Expression evaluation failed: name 'result' is not defined"
**Cause**: Using dot notation in convergence check.
**Solution**: Use flattened field name: `converged == True`

### Error: "'>=' not supported between instances of 'int' and 'NoneType'"
**Cause**: Missing `max_iterations` parameter.
**Solution**: Always specify `max_iterations` (must be > 0)

### Error: "Failed to get node parameters: Field required"
**Cause**: Missing 'name' in NodeParameter definition.
**Solution**: Include name: `NodeParameter(name="field", type=int)`

## Testing Patterns

When writing tests for cyclic workflows:

```python
# 1. Always provide initial parameters
result, _ = runtime.execute(workflow, parameters={
    "node_id": {"param": initial_value}
})

# 2. Assert on the correct path for PythonCodeNode
assert result["node"]["result"]["field"] == expected_value

# 3. Test edge cases
# - Immediate convergence
# - Maximum iterations reached
# - Complex state propagation
```

## Migration from Old Patterns

If migrating from older code:

1. **Add dot notation to mappings**: `"field"` → `"result.field"`
2. **Remove context parameters**: `lambda x, context=None:` → `lambda x:`
3. **Add initial parameters**: Identify all cycle entry points
4. **Fix convergence checks**: Remove `result.` prefix
5. **Add name to NodeParameter**: `NodeParameter(type=int)` → `NodeParameter(name="x", type=int)`

## Best Practices

1. **Always test cycles with real data** - Use Docker infrastructure for integration tests
2. **Set reasonable max_iterations** - Prevent infinite loops (must be > 0)
3. **Log iteration progress** - Helps debug convergence issues
4. **Validate parameter propagation** - Ensure state carries through iterations
5. **Document convergence criteria** - Make it clear when cycles should stop
6. **Simplify complex cycles** - Break down nested cycles into simpler patterns
7. **Use CycleAwareNode for stateful processing** - Provides built-in state management

## Common Patterns from Test Suite

### Pattern 1: Simple Self-Referencing Cycle
```python
workflow.create_cycle("cycle_name") \
    .connect("node", "node", {"result.field": "param"}) \
    .max_iterations(10) \
    .converge_when("converged == True") \
    .build()
```

### Pattern 2: Two-Node Cycle
```python
workflow.add_connection("node_a", "result", "node_b", "input")
workflow.create_cycle("ab_cycle") \
    .connect("node_b", "node_a", {"result.value": "data"}) \
    .max_iterations(20) \
    .converge_when("done == True") \
    .build()
```

### Pattern 3: CycleAwareNode Pattern
```python
class MyProcessor(CycleAwareNode):
    def get_parameters(self):
        return {
            "value": NodeParameter(name="value", type=int, default=0)
        }

    def run(self, **kwargs):
        # Access state and iteration
        state = self.get_previous_state(kwargs.get("context", {}))
        iteration = self.get_iteration(kwargs.get("context", {}))

        # Process and update state
        return {
            "result": "processed",
            **self.set_cycle_state({"key": "value"})
        }
```

## Related Documentation

- [Unified Async Runtime Guide](09-unified-async-runtime-guide.md) - For async cycle patterns
- [Troubleshooting Guide](05-troubleshooting.md) - For debugging cycle issues
- [Workflow Builder Guide](08-async-workflow-builder.md) - For advanced workflow patterns
