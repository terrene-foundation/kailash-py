# Mistake #001: Config vs Runtime Parameters

## Category
API/Integration

## Severity
Critical

## Problem
Passing runtime data as configuration parameters when adding nodes to a workflow. This is the #1 most common mistake in Kailash SDK usage.

## Symptoms
- Error message: `TypeError: 'data' is not a valid config parameter`
- Error message: `ValueError: Unknown parameter 'input_data' for PythonCodeNode`
- Workflow fails during node addition, not execution
- Parameters meant for runtime are rejected at workflow build time

## Example
```python
# ❌ WRONG - Trying to pass runtime data as config
workflow = Workflow(name="processor")
workflow.add_node("process", PythonCodeNode(),
    data=[1, 2, 3],  # ERROR: 'data' is runtime, not config!
    code="result = [x * 2 for x in data]"
)

# ✅ CORRECT - Config defines behavior, data flows at runtime
workflow = Workflow(name="processor")
workflow.add_node("process", PythonCodeNode(),
    code="result = [x * 2 for x in data]"  # Config: HOW to process
)
# Data passed at execution time:
runtime = LocalRuntime()
result = runtime.execute(workflow, parameters={
    "process": {"data": [1, 2, 3]}  # Runtime: WHAT to process
})
```

## Root Cause
Confusion between two distinct concepts:
1. **Configuration parameters** - Define HOW a node behaves (code, file paths, settings)
2. **Runtime parameters** - Define WHAT data flows through (input data, dynamic values)

This happens because:
- Traditional function calls mix behavior and data
- The separation isn't intuitive coming from imperative programming
- Documentation wasn't clear enough about this distinction

## Solution
1. When adding nodes, only pass configuration parameters
2. Check `get_parameters()` to see what's config vs runtime
3. Pass all data through `runtime.execute()` parameters or node connections

## Prevention
- Remember: Config = HOW (static behavior), Runtime = WHAT (dynamic data)
- Always check the node's `get_parameters()` method
- Use the validation tool before running
- Think of nodes as reusable processors, not one-time functions

## Related Mistakes
- [#004 - Wrong Parameter Format](004-wrong-parameter-format.md)
- [#008 - Direct Node Execution](008-direct-node-execution.md)

## Fixed In
- Session: Multiple sessions from early development through 2024
- This has been the most persistent issue throughout development

## References
- [API Registry](../reference/api-registry.yaml) - Node parameter definitions
- [Workflow Guide](../features/workflow_pattern.md) - Correct workflow patterns
- [Cheatsheet](../reference/cheatsheet.md) - Quick reference for parameters
