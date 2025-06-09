# Mistake #054: Workflow Execution Input Parameter Confusion

## Problem
Confusion about how to pass inputs when executing workflows.

### Bad Example
```python
# BAD - Wrong parameter names
runtime.execute(workflow, inputs={"data": [1, 2, 3]})  # WRONG: should be 'parameters'

# BAD - Positional arguments
runtime.execute(workflow, {"node": {"param": "value"}})  # WRONG: must use keyword

# GOOD - Correct usage
# Runtime.execute uses 'parameters' (node-specific overrides)
results, run_id = runtime.execute(
    workflow,
    parameters={
        "node_id": {"param1": "value1", "param2": 123}
    }
)

```

## Solution
Updated documentation to clarify:
- Always use `runtime.execute()` for workflow execution
- Use `parameters` keyword argument for node-specific overrides
- Parameters dict maps node IDs to their parameter overrides
- While workflow.execute() exists in the codebase, it's not used in practice

**Key Learning**:
- Production code exclusively uses runtime.execute() for benefits like task tracking
- The parameters argument allows runtime override of node configurations
- Always use keyword arguments, never positional

## Impact
- Runtime errors about unexpected arguments
- Confusion about why inputs aren't being passed correctly
- Incorrect assumptions about workflow.execute() method

## Fixed In
Session 40 - Updated validation-guide.md and cheatsheet.md

## Related Issues
#53 (Configuration vs Runtime Parameters)

## Categories
api-design, workflow, configuration

---
