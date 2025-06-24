# SwitchNode Conditional Routing

## Basic Setup

```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode

# Boolean routing
workflow.add_node("switch", SwitchNode(
    condition_field="is_valid",
    operator="==",
    value=True
))

# Connect outputs: true_output or false_output
workflow.connect("switch", "success_handler", condition="true_output")
workflow.connect("switch", "retry_handler", condition="false_output")

```

## Critical Pattern: A → B → Switch → (Back to A | Exit)

```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode

# Quality improvement loop with conditional exit
workflow = Workflow("conditional-cycle")

# Linear flow
workflow.add_node("processor", PythonCodeNode())
workflow.add_node("checker", PythonCodeNode())
workflow.add_node("switch", SwitchNode(
    condition_field="needs_improvement",
    operator="==",
    value=True
))
workflow.add_node("output", PythonCodeNode())

# Connect flow
workflow.connect("processor", "checker")
workflow.connect("checker", "switch",
    mapping={"result": "input_data"})

# Conditional routing
workflow.connect("switch", "processor",
    condition="true_output", cycle=True, max_iterations=10)
workflow.connect("switch", "output",
    condition="false_output")

```

## Mapping Rules

### ✅ Correct Patterns
```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode

workflow = Workflow("mapping-examples")

# ✅ Complete output transfer
workflow.connect("processor", "switch",
    mapping={"result": "input_data"})  # Entire dict → input_data

# ✅ Specific field mapping
workflow.connect("processor", "switch",
    mapping={"result.status": "input_data"})  # Single field → input_data

# ✅ Multi-field mapping
workflow.connect("processor", "switch",
    mapping={
        "result.data": "input_data",
        "result.metadata": "metadata"
    })

```

### ❌ Common Mistakes
```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode

workflow = Workflow("mistake-examples")

# ❌ Missing input_data - THIS IS WRONG!
workflow.connect("processor", "switch")  # ERROR: No input_data

# ❌ Wrong parameter name - THIS IS WRONG!
workflow.connect("processor", "switch",
    mapping={"result": "data"})  # ERROR: Needs "input_data"

```

## Configuration Patterns

### Multi-Case Routing
```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode

workflow = Workflow("multi-case-example")

switch = SwitchNode(
    condition_field="status",
    cases=["success", "warning", "error"]
)

workflow.add_node("switch", switch)

# Outputs: case_success, case_warning, case_error, default
workflow.connect("switch", "success_proc", condition="case_success")
workflow.connect("switch", "warning_proc", condition="case_warning")
workflow.connect("switch", "error_proc", condition="case_error")
workflow.connect("switch", "default_proc", condition="default")

```

### Numeric Thresholds
```python
switch = SwitchNode(
    condition_field="score",
    operator=">=",
    value=0.8
)
# true_output: score >= 0.8
# false_output: score < 0.8

```

## Cycle Integration

### Complete Example with Source Node
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, CycleAwareNode

# Data source for cycle entry
class DataSourceNode(CycleAwareNode):
    def run(self, context, **kwargs):
        return {"data": kwargs.get("data", [])}

# Quality checker with routing decision
class QualityCheckerNode(Node):
    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        quality = len([x for x in data if x < 50]) / len(data)  # Simple quality calc

        return {
            "data": data,
            "quality": quality,
            "needs_improvement": quality < 0.85,
            "reason": f"Quality: {quality:.2f}"
        }

# Build workflow
workflow = Workflow("complete-switch-example")
workflow.add_node("source", DataSourceNode())
workflow.add_node("processor", PythonCodeNode())
workflow.add_node("checker", QualityCheckerNode())
workflow.add_node("switch", SwitchNode(
    condition_field="needs_improvement",
    operator="==",
    value=True
))

# Connect with proper mappings
workflow.connect("source", "processor")
workflow.connect("processor", "checker")
workflow.connect("checker", "switch",
    mapping={"result": "input_data"})

# Conditional paths
workflow.connect("switch", "processor",
    condition="true_output", cycle=True, max_iterations=5)

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "source": {"data": [1, 2, 3, 60, 4, 5]}
})

```

## Error Handling Pattern

```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode

workflow = Workflow("error-handling-example")

# Route based on error status
workflow.add_node("error_switch", SwitchNode(
    condition_field="has_error",
    operator="==",
    value=True
))

workflow.connect("processor", "error_switch",
    mapping={"result": "input_data"})
workflow.connect("error_switch", "error_handler", condition="true_output")
workflow.connect("error_switch", "success_flow", condition="false_output")

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

3. **Proper Cycle Limits**: Always set max_iterations
   ```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode

workflow = Workflow("cycle-limits-example")

workflow.connect("switch", "retry",
       condition="true_output",
       cycle=True,
       max_iterations=20)

   ```

## Common Pitfalls

1. **Empty Mapping**: `mapping={}` transfers no data
2. **Generic Output**: `mapping={"output": "output"}` loses fields
3. **Multiple cycle=True**: Only mark switch→retry edge
4. **Missing input_data**: SwitchNode requires this parameter

## Next Steps
- [Cyclic workflows](019-cyclic-workflows-basics.md)
- [Multi-path patterns](../features/conditional_routing.md)
- [Production examples](../workflows/by-pattern/control-flow/)
