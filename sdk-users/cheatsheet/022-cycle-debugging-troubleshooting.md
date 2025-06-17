# Cycle Debugging & Troubleshooting

*Quick fixes for common cycle issues*

## 🚨 Most Common Issues

### 1. Parameter Loss After First Iteration
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node, CycleAwareNode

# ❌ Problem: Parameters disappear after iteration 1
class ProcessorNode(Node):
    def run(self, context, **kwargs):
        quality = kwargs.get("quality", 0.0)  # Always 0.0 after iter 1!
        return {"quality": quality + 0.2}

# ✅ Solution: Use cycle state
class ProcessorNodeFixed(CycleAwareNode):
    def run(self, context, **kwargs):
        prev_state = self.get_previous_state(context)
        quality = kwargs.get("quality", prev_state.get("quality", 0.0))

        new_quality = quality + 0.2
        return {
            "quality": new_quality,
            **self.set_cycle_state({"quality": new_quality})
        }

```

### 2. PythonCodeNode Parameter Access
```python
# ❌ Problem: NameError on parameters
code = '''
current_count = count  # NameError on first iteration
result = {"count": current_count + 1}
'''

# ✅ Solution: Always use try/except
code = '''
try:
    current_count = count
except NameError:
    current_count = 0  # Default for first iteration

current_count += 1
done = current_count >= 5

result = {"count": current_count, "done": done}
'''

```

### 3. Infinite Cycles
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node
from kailash.nodes.code import PythonCodeNode

# ❌ Problem: Convergence never satisfied
workflow = Workflow("convergence-problem")
workflow.connect("processor", "processor",
    cycle=True, max_iterations=10,
    convergence_check="done == True")  # 'done' never becomes True

# ✅ Solution: Debug convergence field
class DebugNode(Node):
    def run(self, context, **kwargs):
        done = kwargs.get("done", False)
        print(f"Convergence field 'done': {done} (type: {type(done)})")
        return kwargs  # Pass through

# Insert debug node before convergence check
workflow = Workflow("debug-convergence")
workflow.add_node("processor", PythonCodeNode())
workflow.add_node("debug", DebugNode())
workflow.connect("processor", "debug")
workflow.connect("debug", "processor", cycle=True)

```

### 4. Multi-Node Cycle Detection Issues
```python
from kailash import Workflow
from kailash.nodes.code import PythonCodeNode

# ❌ Problem: Middle nodes not detected in A → B → C → A
workflow = Workflow("multi-node-cycle-problem")
workflow.connect("A", "B")           # Regular
workflow.connect("B", "C")           # Regular
workflow.connect("C", "A", cycle=True) # Only closing edge marked
# Result: B is treated as separate DAG node

# ✅ Solution: Use direct cycles when possible
workflow_fixed = Workflow("two-node-cycle")
workflow_fixed.add_node("A", PythonCodeNode())
workflow_fixed.add_node("B", PythonCodeNode())
workflow_fixed.connect("A", "B")
workflow_fixed.connect("B", "A", cycle=True)  # Simple 2-node cycle

# Note: cycle detection is internal to the runtime
print("Workflow configured with 2-node cycle")

```

## 🔧 Quick Debug Techniques

### Add Logging Node
```python
from kailash import Workflow
from kailash.nodes.base import Node
from kailash.nodes.code import PythonCodeNode

class CycleLoggerNode(Node):
    def run(self, context, **kwargs):
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        print(f"=== Iteration {iteration} ===")
        print(f"Parameters: {kwargs}")
        print(f"Node state: {cycle_info.get('node_state', {})}")

        return kwargs  # Pass through unchanged

# Insert into cycle for debugging
workflow = Workflow("debug-cycle")
workflow.add_node("processor", PythonCodeNode())
workflow.add_node("logger", CycleLoggerNode())
workflow.connect("processor", "logger")
workflow.connect("logger", "processor", cycle=True)

```

### Parameter Monitoring
```python
class ParameterMonitorNode(Node):
    def run(self, context, **kwargs):
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Check which parameters are received
        received_params = list(kwargs.keys())
        print(f"Iteration {iteration}: Received {received_params}")

        # Check for expected parameters
        expected = ["data", "quality", "threshold"]
        missing = [p for p in expected if p not in kwargs]
        if missing:
            print(f"WARNING: Missing parameters: {missing}")

        return kwargs

```

## ⚠️ Safe Context Access

```python
def run(self, context, **kwargs):
    # ✅ Always use .get() with defaults
    cycle_info = context.get("cycle", {})
    iteration = cycle_info.get("iteration", 0)
    node_state = cycle_info.get("node_state") or {}

    # ❌ Never access directly
    # iteration = context["cycle"]["iteration"]  # KeyError!

```

## 🧪 Testing Patterns

### Simple Test Cycle
```python
def test_cycle_execution():
    from kailash import Workflow
    from kailash.runtime.local import LocalRuntime
    from kailash.nodes.code import PythonCodeNode
    
    workflow = Workflow("test-cycle")
    
    # Simple counter node
    workflow.add_node("counter", PythonCodeNode(
        code='''
try:
    count = count
except:
    count = 0

count += 1
result = {"count": count, "done": count >= 3}
'''
    ))

    # Self-cycle
    workflow.connect("counter", "counter",
        mapping={"result.count": "count"},
        cycle=True, max_iterations=10,
        convergence_check="done == True")

    # Execute and verify
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow)

    final_result = results.get("counter", {})
    assert final_result.get("result", {}).get("count") == 3

```

### Flexible Test Assertions
```python
def test_cycle_with_ranges():
    # ✅ Test patterns, not exact values
    final_result = results.get("processor", {})
    quality = final_result.get("quality", 0)

    # Allow variation in iteration count
    iteration = final_result.get("iteration", 0)
    assert 3 <= iteration <= 7, f"Expected 3-7 iterations, got {iteration}"

    # Check convergence was achieved
    converged = final_result.get("converged", False)
    assert converged, "Cycle should have converged"

    # ❌ Avoid exact assertions
    # assert quality == 0.85  # Too rigid!

```

## 📝 Best Practices

1. **Start Simple** - Begin with minimal cycles
2. **Add Debugging Incrementally** - One feature at a time
3. **Use Descriptive Names** - Clear field names for debugging
4. **Validate Early** - Check inputs and outputs
5. **Test Error Scenarios** - Don't just test happy paths

## 🚀 Quick Reference

### Common Error Patterns
- Parameters lost after first iteration → Use cycle state
- NameError in PythonCodeNode → Use try/except pattern
- Infinite cycles → Debug convergence field
- KeyError on context → Use .get() with defaults

### Debug Node Templates
- **Logger**: Log all parameters and state
- **Monitor**: Track parameter propagation
- **Validator**: Check convergence fields

---
*Related: [021-cycle-aware-nodes.md](021-cycle-aware-nodes.md), [027-cycle-aware-testing-patterns.md](027-cycle-aware-testing-patterns.md)*
