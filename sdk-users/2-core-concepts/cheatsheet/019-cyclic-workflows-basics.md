# Cyclic Workflows Basics

## Quick Setup

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create cycle with PythonCodeNode
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "counter", {
    "code": """
# First iteration starts with default values
current_count = count if 'count' in locals() else 0

current_count += 1
result = {
    "count": current_count,
    "done": current_count >= 5
}
"""
})

# Create cycle using CycleBuilder API
cycle_builder = workflow.create_cycle("counter_cycle")
cycle_builder.connect("counter", "result", "counter", "input_data") \
             .max_iterations(10) \
             .converge_when("done == True") \
             .timeout(300) \
             .build()

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

## Key Rules

### 1. Parameter Access Pattern
```python
# ALWAYS use try/except in PythonCodeNode
code = '''
try:
    # Access cycle parameters
    value = input_value
    data = input_data
except NameError:
    # First iteration defaults
    value = 0
    data = []

# Process and create result
result = {"value": value + 1, "data": data + [value]}
'''

```

### 2. Mapping for PythonCodeNode
```python
# Assuming standard imports from earlier examples

# ✅ CORRECT: 4-parameter connection syntax
workflow.add_connection("counter", "result", "processor", "count")  # Direct connection

# ✅ CORRECT: Nested field access with dot notation
workflow.add_connection("counter", "result.count", "processor", "count")  # Access nested field

# ❌ WRONG: Old mapping syntax - deprecated
# workflow.add_connection("counter", "processor", "count", "count")  # THIS IS DEPRECATED!

```

### 3. Multi-Node Cycles
```python
# Assuming standard imports from earlier examples

# For A → B → C → A cycle using CycleBuilder
workflow.add_connection("A", "result", "B", "input")  # Regular
workflow.add_connection("B", "result", "C", "input")  # Regular

# Create cycle for closing edge using CycleBuilder API
cycle_builder = workflow.create_cycle("multi_node_cycle")
cycle_builder.connect("C", "result", "A", "input") \
             .max_iterations(20) \
             .converge_when("converged == True") \
             .timeout(600) \
             .build()

```

## Data Entry Patterns

### Multi-Node Cycles Need Source
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import CycleAwareNode

# Use source node for data entry
class DataSourceNode(CycleAwareNode):
    def run(self, **kwargs):
        return {"data": kwargs.get("data", [])}

workflow = WorkflowBuilder()
workflow.add_node("DataSourceNode", "source", {}))
workflow.add_node("PythonCodeNode", "processor", {}))
workflow.add_connection("source", "result", "processor", "input")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Execute with node-specific parameters
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "source": {"data": [1, 2, 3]}
})

```

### Self-Loop Direct Parameters
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Single node cycles can use direct parameters
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "proc", {}))
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "value": 10  # Direct parameters work
})

```

## Convergence Patterns

### Expression-Based
```python
# Assuming standard imports from earlier examples

# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### Callback-Based
```python
# Assuming standard imports from earlier examples

def check_convergence(iteration, outputs, context):
    error = outputs.get("processor", {}).get("error", float('inf'))
    if error < 0.001:
        return True, "Error threshold reached"
    return False, f"Error: {error:.4f}"

# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

## Common Patterns

### Quality Improvement Loop
```python
# Assuming standard imports from earlier examples

workflow = WorkflowBuilder()

# Process → Validate → Process (if needed)
workflow.add_node("PythonCodeNode", "processor", {}))
workflow.add_node("PythonCodeNode", "validator", {}))

workflow.add_connection("processor", "result", "validator", "input")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### Iterative Optimization
```python
# Assuming standard imports from earlier examples

# Optimize → Evaluate → Optimize (until converged)
workflow.add_connection("optimizer", "result", "evaluator", "input")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

## Safety Limits

```python
# Assuming standard imports from earlier examples

# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

## Common Pitfalls

1. **Multiple # Use CycleBuilder API instead**: Only mark closing edge
2. **Wrong mapping**: Use "result.field" for PythonCodeNode
3. **No try/except**: Always handle first iteration
4. **No limits**: Set max_iterations and timeout

## Next Steps
- [SwitchNode routing](020-switchnode-conditional-routing.md)
- [Advanced patterns](037-cyclic-workflow-patterns.md)
- [Examples](../workflows/by-pattern/cyclic/)
