# SwitchNode Conditional Routing

## Basic Setup

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Boolean routing
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "switch", {
    "condition_field": "is_valid",
    "operator": "==",
    "value": True
})

# Connect outputs: true_output or false_output
workflow.add_connection("switch", "true_output", "success_handler", "input")
workflow.add_connection("switch", "false_output", "retry_handler", "input")

```

## Critical Pattern: A → B → Switch → (Back to A | Exit)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Quality improvement loop with conditional exit
workflow = WorkflowBuilder()

# Linear flow nodes
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'data': data, 'iteration': iteration + 1}"
})
workflow.add_node("PythonCodeNode", "checker", {
    "code": "result = {'needs_improvement': iteration < 5, 'data': data, 'iteration': iteration}"
})
workflow.add_node("SwitchNode", "switch", {
    "condition_field": "needs_improvement",
    "operator": "==",
    "value": True
})
workflow.add_node("PythonCodeNode", "output", {
    "code": "result = {'final_data': data, 'iterations': iteration}"
})

# Connect linear flow
workflow.add_connection("processor", "result", "checker", "input_data")
workflow.add_connection("checker", "result", "switch", "input_data")

# Build workflow and create cycle using modern API
built_workflow = workflow.build()

# Create cycle using CycleBuilder API
cycle_builder = built_workflow.create_cycle("quality_improvement")
cycle_builder.connect("switch", "processor", mapping={"true_output": "input_data"}) \
             .max_iterations(10) \
             .converge_when("needs_improvement == False") \
             .timeout(300) \
             .build()

# Exit condition
workflow.add_connection("switch", "false_output", "output", "input_data")

```

## Mapping Rules

### ✅ Correct Patterns
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# ✅ Complete output transfer
workflow.add_connection("processor", "result", "switch", "input_data")  # Entire dict → input_data

# ✅ Specific field mapping with dot notation
workflow.add_connection("processor", "result.status", "switch", "input_data")  # Single field → input_data

# ✅ Multi-field connections (separate connections for each field)
workflow.add_connection("processor", "result.data", "switch", "input_data")
workflow.add_connection("processor", "result.metadata", "switch", "metadata")

```

## ⚠️ Dot Notation on SwitchNode Outputs

### The Issue
SwitchNode outputs are **mutually exclusive**:
- When `true_output` has data → `false_output` is `None`
- When `false_output` has data → `true_output` is `None`

Accessing `None.field_name` fails navigation.

### Solution: Depends on Execution Mode

#### ✅ skip_branches Mode (Recommended)
**Dot notation works** - runtime skips nodes with `None` inputs:

```python
from kailash.runtime.local import LocalRuntime

# Dot notation is SAFE in skip_branches mode
workflow.add_connection("switch", "true_output.name", "high_scorer", "name")
workflow.add_connection("switch", "false_output.name", "low_scorer", "name")

runtime = LocalRuntime(conditional_execution="skip_branches")
results, _ = runtime.execute(workflow.build())
# Only active branch executes - inactive branch skipped automatically
```

#### ⚠️ route_data Mode
**Avoid dot notation** - connect full output and handle `None`:

```python
# Connect full output (no dot notation)
workflow.add_connection("switch", "true_output", "high_scorer", "data")
workflow.add_connection("switch", "false_output", "low_scorer", "data")

# Handle None in node code
workflow.add_node("PythonCodeNode", "high_scorer", {
    "code": """
if data is not None:
    name = data.get('name', 'Unknown')
    result = f'High scorer: {name}'
else:
    result = 'No data (inactive branch)'
"""
})

runtime = LocalRuntime(conditional_execution="route_data")
```

### Best Practice

**Use `skip_branches` for conditional workflows** - faster (skips inactive nodes) and dot notation works seamlessly.

**Use `route_data` only when all branches must execute** (logging, auditing, side effects).

### ❌ Common Mistakes
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# ❌ Missing port names - THIS IS WRONG!
# workflow.add_connection("processor", "result", "switch", "input")  # ERROR: Missing ports

# ❌ Wrong parameter name - THIS IS WRONG!
# workflow.add_connection("processor", "result", "switch", "data")  # ERROR: Needs "input_data"

# ✅ CORRECT - Always use proper port names
workflow.add_connection("processor", "result", "switch", "input_data")

```

## Configuration Patterns

### Multi-Case Routing
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

workflow.add_node("SwitchNode", "switch", {
    "condition_field": "status",
    "cases": ["success", "warning", "error"]
})

# Add processor nodes
workflow.add_node("PythonCodeNode", "success_proc", {"code": "result = 'Success processed'"})
workflow.add_node("PythonCodeNode", "warning_proc", {"code": "result = 'Warning processed'"})
workflow.add_node("PythonCodeNode", "error_proc", {"code": "result = 'Error processed'"})
workflow.add_node("PythonCodeNode", "default_proc", {"code": "result = 'Default processed'"})

# Outputs: case_success, case_warning, case_error, default
workflow.add_connection("switch", "case_success", "success_proc", "input")
workflow.add_connection("switch", "case_warning", "warning_proc", "input")
workflow.add_connection("switch", "case_error", "error_proc", "input")
workflow.add_connection("switch", "default", "default_proc", "input")

```

### Numeric Thresholds
```python
workflow.add_node("SwitchNode", "threshold_switch", {
    "condition_field": "score",
    "operator": ">=",
    "value": 0.8
})
# true_output: score >= 0.8
# false_output: score < 0.8

```

## Cycle Integration

### Complete Example with Source Node
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build workflow using WorkflowBuilder
workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "source", {
    "code": "result = {'data': [1, 2, 3, 60, 4, 5]}"
})

# Processor
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Simulate processing
import random
processed_data = [x + random.randint(1, 10) for x in data.get('data', [])]
result = {'data': processed_data, 'iteration': iteration + 1 if 'iteration' in locals() else 1}
"""
})

# Quality checker
workflow.add_node("PythonCodeNode", "checker", {
    "code": """
data_list = data.get('data', [])
if data_list:
    quality = len([x for x in data_list if x < 50]) / len(data_list)
else:
    quality = 0.0

result = {
    'data': data_list,
    'quality': quality,
    'needs_improvement': quality < 0.85,
    'reason': f'Quality: {quality:.2f}',
    'iteration': data.get('iteration', 1)
}
"""
})

# Switch node
workflow.add_node("SwitchNode", "switch", {
    "condition_field": "needs_improvement",
    "operator": "==",
    "value": True
})

# Output node
workflow.add_node("PythonCodeNode", "output", {
    "code": "result = {'final_quality': data.get('quality'), 'iterations': data.get('iteration')}"
})

# Connect linear flow
workflow.add_connection("source", "result", "processor", "data")
workflow.add_connection("processor", "result", "checker", "data")
workflow.add_connection("checker", "result", "switch", "input_data")

# Build workflow and create cycle using modern API
built_workflow = workflow.build()

# Create cycle using CycleBuilder API
cycle_builder = built_workflow.create_cycle("quality_improvement")
cycle_builder.connect("switch", "processor", mapping={"true_output": "data"}) \
             .max_iterations(5) \
             .converge_when("needs_improvement == False") \
             .timeout(300) \
             .build()

# Exit path
workflow.add_connection("switch", "false_output", "output", "data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

## Error Handling Pattern

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Add processor and handlers
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'data': 'processed', 'has_error': False}"
})

# Route based on error status
workflow.add_node("SwitchNode", "error_switch", {
    "condition_field": "has_error",
    "operator": "==",
    "value": True
})

workflow.add_node("PythonCodeNode", "error_handler", {
    "code": "result = {'status': 'error handled'}"
})

workflow.add_node("PythonCodeNode", "success_flow", {
    "code": "result = {'status': 'success processed'}"
})

# Connect the flow
workflow.add_connection("processor", "result", "error_switch", "input_data")
workflow.add_connection("error_switch", "true_output", "error_handler", "input")
workflow.add_connection("error_switch", "false_output", "success_flow", "input")

```

## Best Practices

1. **Clear Field Names**: Use descriptive condition fields
   ```python
   # Good: "needs_retry", "quality_passed", "has_error"
   # Bad: "flag", "ok", "status"

   ```

2. **Handle All Routes**: Connect all possible outputs
   ```python
   # For cases=["a","b","c"], connect: case_a, case_b, case_c, default

   ```

3. **Proper Cycle Limits**: Always set max_iterations with CycleBuilder
   ```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Build workflow and create cycle with proper limits
built_workflow = workflow.build()

cycle_builder = built_workflow.create_cycle("retry_cycle")
cycle_builder.connect("switch", "retry", mapping={"true_output": "input"}) \
             .max_iterations(20) \
             .converge_when("success == True") \
             .timeout(600) \
             .build()

   ```

## Common Pitfalls

1. **Missing Port Names**: Always specify both source and target ports in connections
2. **Wrong Parameter Names**: SwitchNode requires `input_data` parameter
3. **Multiple Cycles**: Only create one cycle per workflow - use CycleBuilder
4. **Missing input_data**: SwitchNode always requires this input parameter

## Next Steps
- [Cyclic workflows](019-cyclic-workflows-basics.md)
- [Multi-path patterns](../features/conditional_routing.md)
- [Production examples](../workflows/by-pattern/control-flow/)
