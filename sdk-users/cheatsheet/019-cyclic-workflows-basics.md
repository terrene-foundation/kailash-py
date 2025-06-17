# Cyclic Workflows Basics

## Quick Setup

```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Create cycle with PythonCodeNode
workflow = Workflow("cycle-001", name="basic_cycle")

workflow.add_node("counter", PythonCodeNode(), code='''
try:
    current_count = count  # From previous iteration
except:
    current_count = 0      # First iteration default

current_count += 1
result = {
    "count": current_count,
    "done": current_count >= 5
}
''')

# ONLY mark closing edge as cycle=True
workflow.connect("counter", "counter",
    mapping={"result.count": "count"},  # Nested path for PythonCodeNode
    cycle=True,
    max_iterations=10,
    convergence_check="done == True")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

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

# ✅ CORRECT: Nested paths
workflow.connect("counter", "processor", 
    mapping={"result.count": "count"})  # result.field syntax

# ❌ WRONG: Flat mapping
workflow.connect("counter", "processor",
    mapping={"count": "count"})  # Missing result prefix - THIS IS WRONG!

```

### 3. Multi-Node Cycles
```python
# Assuming standard imports from earlier examples

# For A → B → C → A cycle
workflow.connect("A", "B")  # Regular
workflow.connect("B", "C")  # Regular
workflow.connect("C", "A",  # ONLY closing edge
    cycle=True,
    max_iterations=20,
    convergence_check="converged == True")

```

## Data Entry Patterns

### Multi-Node Cycles Need Source
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import CycleAwareNode

# Use source node for data entry
class DataSourceNode(CycleAwareNode):
    def run(self, context, **kwargs):
        return {"data": kwargs.get("data", [])}

workflow = Workflow("source-cycle")
workflow.add_node("source", DataSourceNode())
workflow.add_node("processor", PythonCodeNode())
workflow.connect("source", "processor")
workflow.connect("processor", "processor", cycle=True)

# Execute with node-specific parameters
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "source": {"data": [1, 2, 3]}
})

```

### Self-Loop Direct Parameters
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Single node cycles can use direct parameters
workflow = Workflow("self-loop")
workflow.add_node("proc", PythonCodeNode())
workflow.connect("proc", "proc", cycle=True)

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "value": 10  # Direct parameters work
})

```

## Convergence Patterns

### Expression-Based
```python
# Assuming standard imports from earlier examples

workflow.connect("node", "node",
    cycle=True,
    max_iterations=50,
    convergence_check="quality >= 0.95 and stable == True")

```

### Callback-Based
```python
# Assuming standard imports from earlier examples

def check_convergence(iteration, outputs, context):
    error = outputs.get("processor", {}).get("error", float('inf'))
    if error < 0.001:
        return True, "Error threshold reached"
    return False, f"Error: {error:.4f}"

workflow.connect("processor", "processor",
    cycle=True,
    convergence_callback=check_convergence)

```

## Common Patterns

### Quality Improvement Loop
```python
# Assuming standard imports from earlier examples

workflow = Workflow("quality-loop")

# Process → Validate → Process (if needed)
workflow.add_node("processor", PythonCodeNode())
workflow.add_node("validator", PythonCodeNode())

workflow.connect("processor", "validator")
workflow.connect("validator", "processor", 
    cycle=True, 
    convergence_check="quality >= 0.95")

```

### Iterative Optimization
```python
# Assuming standard imports from earlier examples

# Optimize → Evaluate → Optimize (until converged)
workflow.connect("optimizer", "evaluator")
workflow.connect("evaluator", "optimizer",
    cycle=True,
    convergence_check="converged == True")

```

## Safety Limits

```python
# Assuming standard imports from earlier examples

workflow.connect("processor", "processor",
    cycle=True,
    max_iterations=50,      # Prevent infinite loops
    timeout=300.0,          # 5 minute timeout
    convergence_check="done == True")

```

## Common Pitfalls

1. **Multiple cycle=True**: Only mark closing edge
2. **Wrong mapping**: Use "result.field" for PythonCodeNode
3. **No try/except**: Always handle first iteration
4. **No limits**: Set max_iterations and timeout

## Next Steps
- [SwitchNode routing](020-switchnode-conditional-routing.md)
- [Advanced patterns](037-cyclic-workflow-patterns.md)
- [Examples](../workflows/by-pattern/cyclic/)