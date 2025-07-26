# Cycle Debugging & Troubleshooting

*Quick fixes for common cycle issues*

## 🚨 Most Common Issues

### 1. ~~Parameter Loss After First Iteration~~ (Fixed in v0.5.1+)
**Update**: Initial parameters are now preserved throughout all cycle iterations!

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node, CycleAwareNode

# ✅ This now works correctly (v0.5.1+)
class ProcessorNode(CycleAwareNode):
    def get_parameters(self):
        return {
            "quality_target": NodeParameter(type=float, required=False, default=0.95),
            "improvement_rate": NodeParameter(type=float, required=False, default=0.1)
        }

    def run(self, **kwargs):
        # Initial parameters are available in ALL iterations
        quality_target = kwargs.get("quality_target", 0.95)
        improvement_rate = kwargs.get("improvement_rate", 0.1)

        context = kwargs.get("context", {})
        prev_quality = self.get_previous_state(context).get("quality", 0.0)

        new_quality = min(prev_quality + improvement_rate, 1.0)
        converged = new_quality >= quality_target

        return {
            "quality": new_quality,
            "converged": converged,
            **self.set_cycle_state({"quality": new_quality})
        }

# Parameters persist across all iterations
runtime.execute(workflow, parameters={
    "processor": {
        "quality_target": 0.90,      # Available in iterations 0-N
        "improvement_rate": 0.05     # No longer reverts to default!
    }
})
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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node
from kailash.nodes.code import PythonCodeNode

# ❌ Problem: Convergence never satisfied
workflow = WorkflowBuilder()
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()  # 'done' never becomes True

# ✅ Solution: Debug convergence field
class DebugNode(Node):
    def run(self, **kwargs):
        done = kwargs.get("done", False)
        print(f"Convergence field 'done': {done} (type: {type(done)})")
        return kwargs  # Pass through

# Insert debug node before convergence check
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {}))
workflow.add_node("DebugNode", "debug", {}))
workflow.add_connection("processor", "result", "debug", "input")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### 4. Multi-Node Cycle Detection Issues
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode

# ❌ Problem: Middle nodes not detected in A → B → C → A
workflow = WorkflowBuilder()
workflow.add_connection("A", "result", "B", "input")           # Regular
workflow.add_connection("B", "result", "C", "input")           # Regular
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build() # Only closing edge marked
# Result: B is treated as separate DAG node

# ✅ Solution: Use direct cycles when possible
workflow_fixed = Workflow("two-node-cycle")
workflow_fixed.add_node("A", "PythonCodeNode")
workflow_fixed.add_node("B", "PythonCodeNode")
workflow_fixed.connect("A", "B")
workflow_fixed.connect("B", "A", # Use CycleBuilder API instead)  # Simple 2-node cycle

# Note: cycle detection is internal to the runtime
print("Workflow configured with 2-node cycle")

```

## 🔧 Quick Debug Techniques

### Add Logging Node
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.base import Node
from kailash.nodes.code import PythonCodeNode

class CycleLoggerNode(Node):
    def run(self, **kwargs):
        cycle_info = self.context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        print(f"=== Iteration {iteration} ===")
        print(f"Parameters: {kwargs}")
        print(f"Node state: {cycle_info.get('node_state', {})}")

        return kwargs  # Pass through unchanged

# Insert into cycle for debugging
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {}))
workflow.add_node("CycleLoggerNode", "logger", {}))
workflow.add_connection("processor", "result", "logger", "input")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### Parameter Monitoring
```python
class ParameterMonitorNode(Node):
    def run(self, **kwargs):
        cycle_info = self.context.get("cycle", {})
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
def run(self, **kwargs):
    # ✅ Always use .get() with defaults
    cycle_info = self.context.get("cycle", {})
    iteration = cycle_info.get("iteration", 0)
    node_state = cycle_info.get("node_state") or {}

    # ❌ Never access directly
    # iteration = self.context["cycle"]["iteration"]  # KeyError!

```

## 🧪 Testing Patterns

### Simple Test Cycle
```python
def test_cycle_execution():
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime.local import LocalRuntime
    from kailash.nodes.code import PythonCodeNode

    workflow = WorkflowBuilder()

    # Simple counter node
    workflow.add_node("PythonCodeNode", "counter", {}))

    # Self-cycle
    # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

    # Execute and verify
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

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
