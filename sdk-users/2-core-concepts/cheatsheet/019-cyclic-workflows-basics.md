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

# CRITICAL: Build workflow FIRST (WorkflowBuilder doesn't have create_cycle)
built_workflow = workflow.build()

# Create cycle using CycleBuilder API on BUILT workflow
cycle_builder = built_workflow.create_cycle("counter_cycle")
# CRITICAL: Use "result." prefix for PythonCodeNode outputs in mapping
cycle_builder.connect("counter", "counter", mapping={"result.count": "count"}) \
             .max_iterations(10) \
             .converge_when("done == True") \
             .timeout(300) \
             .build()

runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)

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

# CRITICAL: Build workflow first
built_workflow = workflow.build()

# Create cycle for closing edge using CycleBuilder API on built workflow
cycle_builder = built_workflow.create_cycle("multi_node_cycle")
cycle_builder.connect("C", "A", mapping={"result": "input"}) \
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
workflow.add_node("PythonCodeNode", "source", {
    "code": "result = {'data': [1, 2, 3], 'iteration': 0}"
})
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
try:
    data = input_data.get('data', [])
    iteration = input_data.get('iteration', 0)
except NameError:
    data = []
    iteration = 0

# Simple processing
processed = [x * 2 for x in data]
iteration += 1

result = {
    'data': processed,
    'iteration': iteration,
    'done': iteration >= 3
}
"""
})

workflow.add_connection("source", "result", "processor", "input_data")

# Build workflow and create cycle
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle("processing_cycle")
cycle_builder.connect("processor", "processor", mapping={"result": "input_data"}) \
             .max_iterations(5) \
             .converge_when("done == True") \
             .timeout(300) \
             .build()

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)

```

### Self-Loop Direct Parameters
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Single node cycles with self-loop
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "proc", {
    "code": """
try:
    value = input_value
    count = input_count
except NameError:
    value = 10
    count = 0

# Process value
value = value * 0.9
count += 1

result = {
    'value': value,
    'count': count,
    'done': value < 1.0
}
"""
})

# Create self-loop cycle
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle("self_loop")
cycle_builder.connect("proc", "proc", mapping={"result": "input_value"}) \
             .max_iterations(20) \
             .converge_when("done == True") \
             .timeout(300) \
             .build()

runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)

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
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
try:
    data = input_data.get('data', [100, 110, 120])
    iteration = input_data.get('iteration', 0)
except NameError:
    data = [100, 110, 120]
    iteration = 0

# Improve data quality
improved_data = [x * 0.95 for x in data]
iteration += 1

result = {
    'data': improved_data,
    'iteration': iteration,
    'quality': sum(improved_data) / len(improved_data)
}
"""
})

workflow.add_node("PythonCodeNode", "validator", {
    "code": """
data = input_data.get('data', [])
iteration = input_data.get('iteration', 0)
quality = input_data.get('quality', 0)

# Check if quality is acceptable
quality_acceptable = quality < 100
result = {
    'data': data,
    'iteration': iteration,
    'quality': quality,
    'converged': quality_acceptable
}
"""
})

workflow.add_connection("processor", "result", "validator", "input_data")

# Build workflow and create quality improvement cycle
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle("quality_improvement")
cycle_builder.connect("validator", "processor", mapping={"result": "input_data"}) \
             .max_iterations(10) \
             .converge_when("converged == True") \
             .timeout(300) \
             .build()

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
