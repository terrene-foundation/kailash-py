# Cycle-Aware Testing Patterns

*Essential testing patterns for cyclic workflows*

## 🔧 Core Testing Rules

### 1. SwitchNode Runtime Parameters
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# ❌ WRONG: Parameters at initialization
switch_node = SwitchNode(condition_field="should_continue")  # THIS IS WRONG!

# ✅ CORRECT: Parameters at runtime
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "switch", {})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "switch": {
        "condition_field": "should_continue",
        "operator": "==",
        "value": True,
        "input_data": {"should_continue": True}
    }
})

```

### 2. Quality Improvement Cycle Pattern
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Quality improvement using PythonCodeNode with cycle awareness
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "improver", {
    "code": """
# Get quality from input_data or use parameter default
try:
    quality = input_data.get('quality', 0.0)
    target = input_data.get('target', 0.8)
except NameError:
    # First iteration - use node parameters
    quality = 0.0
    target = 0.8

# Improve quality
improved_quality = min(1.0, quality + 0.1)
converged = improved_quality >= target

result = {
    'quality': improved_quality,
    'converged': converged,
    'target': target
}
"""
})

# Build workflow and create cycle
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle("quality_improvement")
# CRITICAL: Use "result." prefix for PythonCodeNode in mapping
cycle_builder.connect("improver", "improver", mapping={
    "result.quality": "input_data",
    "result.target": "target"
}) \
             .max_iterations(10) \
             .converge_when("converged == True") \
             .timeout(300) \
             .build()

runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow, parameters={
    "improver": {"quality": 0.0, "target": 0.8}
})

# Test for progress, not exact values
final_result = results.get("improver", {}).get("result", {})
assert final_result.get("quality", 0) >= 0.8
assert final_result.get("converged") == True

```

### 3. PythonCodeNode in Cycles
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# ✅ CORRECT: Use input_data with try/except pattern
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "calculator", {
    "code": """
# Cycle-aware parameter handling
try:
    x = input_data.get('result', 2)  # From previous iteration
except NameError:
    x = 2  # First iteration

result = x * x
"""
})

# Connect in cycle with proper mapping
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle("calculation_cycle")
# CRITICAL: Use "result." prefix for PythonCodeNode in mapping
cycle_builder.connect("calculator", "calculator", mapping={"result.result": "input_data"}) \
             .max_iterations(3) \
             .converge_when("result >= 16") \
             .timeout(300) \
             .build()

runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)

```

## 🧪 Test Patterns

### Simple Counter Test
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def test_simple_counter():
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "counter", {
        "code": """
# Get current count from input_data or start at 0
try:
    current_count = input_data.get('count', 0)
except NameError:
    current_count = 0

new_count = current_count + 1
done = new_count >= 3

result = {
    'count': new_count,
    'done': done
}
"""
    })

    # Build workflow and create cycle
    built_workflow = workflow.build()
    cycle_builder = built_workflow.create_cycle("counter_cycle")
    # CRITICAL: Use "result." prefix for PythonCodeNode in mapping
    cycle_builder.connect("counter", "counter", mapping={
        "result.count": "input_data",
        "result.done": "done"
    }) \
                 .max_iterations(5) \
                 .converge_when("done == True") \
                 .timeout(300) \
                 .build()

    runtime = LocalRuntime()
    results, run_id = runtime.execute(built_workflow)

    # Test that cycle worked
    final_result = results.get("counter", {}).get("result", {})
    assert final_result.get("count") == 3
    assert final_result.get("done") == True

```

### Flexible Test Expectations
```python
# ❌ WRONG: Expecting exact convergence
def test_unrealistic():
    # ... execute workflow ...
    assert final_quality >= 0.85  # May fail!

# ✅ CORRECT: Flexible expectations
def test_realistic():
    # ... execute workflow ...

    # Test for progress, not exact values
    initial_quality = 0.0
    final_quality = result.get("quality", 0)
    assert final_quality > initial_quality  # Progress made

    # Only check exact values if converged
    if result.get("converged"):
        assert final_quality >= 0.8

    # Test that process worked
    assert "quality" in result

```

### Conditional Routing Test
```python
def test_conditional_cycle():
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime.local import LocalRuntime

    # Simple processor for conditional routing
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": """
# Get data from input_data or use defaults
try:
    data = input_data.get('data', [1, 2, 3])
    iteration = input_data.get('iteration', 0)
except NameError:
    data = [1, 2, 3]
    iteration = 0

current_iteration = iteration + 1
processed_sum = sum(data) + current_iteration
should_exit = processed_sum >= 20

result = {
    'data': data,
    'iteration': current_iteration,
    'sum': processed_sum,
    'should_exit': should_exit
}
"""
    })

    workflow.add_node("SwitchNode", "switch", {})

    # Connect processor to switch
    workflow.add_connection("processor", "result", "switch", "input_data")

    # Build workflow and create cycle
    built_workflow = workflow.build()
    cycle_builder = built_workflow.create_cycle("conditional_cycle")
    # CRITICAL: Use "result." prefix for PythonCodeNode outputs in mapping
    cycle_builder.connect("switch", "processor", mapping={
        "result.data": "input_data",
        "result.iteration": "iteration"
    }) \
                 .max_iterations(10) \
                 .converge_when("should_exit == True") \
                 .timeout(300) \
                 .build()

    runtime = LocalRuntime()
    results, run_id = runtime.execute(built_workflow, parameters={
        "processor": {"data": [1, 2, 3]},
        "switch": {"condition_field": "should_exit", "operator": "==", "value": True}
    })

    # Test that workflow completed
    processor_result = results.get("processor", {}).get("result", {})
    assert processor_result is not None
    assert processor_result.get("should_exit") == True

```

## 📋 Testing Principles

1. **Test Patterns, Not Exact Values**
   ```python
   # ✅ Good
   assert final_quality > initial_quality  # Progress made

   # ❌ Bad
   assert final_quality == 0.85  # Too rigid

   ```

2. **Use input_data with try/except**
   ```python
   # ✅ Good: Handle both first iteration and cycles
   try:
       value = input_data.get('value', default)
   except NameError:
       value = default

   # ❌ Bad: Assumes input_data always exists
   value = input_data.get('value', default)

   ```

3. **Provide Required Configuration**
   - Always use `{"result": "input_data"}` mapping for cycles
   - Use `workflow.build()` before creating cycles
   - Always set max_iterations, converge_when, and timeout

4. **Test Incrementally**
   - Individual nodes first
   - Simple cycles second
   - Complex multi-node cycles last

---
*Related: [021-cycle-aware-nodes.md](021-cycle-aware-nodes.md), [022-cycle-debugging-troubleshooting.md](022-cycle-debugging-troubleshooting.md)*
