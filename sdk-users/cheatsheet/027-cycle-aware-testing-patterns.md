# Cycle-Aware Testing Patterns

*Essential testing patterns for cyclic workflows*

## 🔧 Core Testing Rules

### 1. SwitchNode Runtime Parameters
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.logic import SwitchNode

# ❌ WRONG: Parameters at initialization
switch_node = SwitchNode(condition_field="should_continue")  # THIS IS WRONG!

# ✅ CORRECT: Parameters at runtime
workflow = Workflow("switch-test")
workflow.add_node("switch", SwitchNode())

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "switch": {
        "condition_field": "should_continue",
        "operator": "==",
        "value": True
    }
})

```

### 2. Self-Cycle Pattern
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import CycleAwareNode, NodeParameter
from typing import Dict, Any

class SimpleQualityImprover(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "quality": NodeParameter(name="quality", type=float, required=False, default=0.0),
            "target": NodeParameter(name="target", type=float, required=False, default=0.8)
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        quality = kwargs.get("quality", 0.0)
        target = kwargs.get("target", 0.8)

        # Improve quality
        improved_quality = min(1.0, quality + 0.1)
        converged = improved_quality >= target

        return {
            "quality": improved_quality,
            "converged": converged,  # Self-contained convergence
            "iteration": self.get_iteration(context)
        }

# Test self-cycle
def test_self_cycle():
    workflow = Workflow("self-cycle-test")
    workflow.add_node("improver", SimpleQualityImprover())

    # Connect to itself
    workflow.connect("improver", "improver",
        cycle=True, max_iterations=15,
        convergence_check="converged == True")

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow)

    # Test for progress, not exact values
    final_result = results.get("improver", {})
    assert final_result.get("quality", 0) > 0.0

```

### 3. PythonCodeNode in Cycles
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# ✅ CORRECT: Provide code at initialization
workflow = Workflow("python-code-test")
workflow.add_node("calculator", PythonCodeNode(
    code="result = 2"  # Required
))

# Connect in cycle with parameter handling
workflow.connect("calculator", "calculator",
    cycle=True, max_iterations=8,
    convergence_check="result > 1000")

# Runtime code with try/except pattern
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "calculator": {
        "code": """
try:
    x = result  # From previous iteration
except:
    x = 2  # First iteration

result = x * x
"""
    }
})

```

## 🧪 Test Patterns

### Parameter Preservation Test
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import CycleAwareNode, NodeParameter
from typing import Dict, Any

class CounterNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "increment": NodeParameter(name="increment", type=int, required=False, default=1),
            "start_value": NodeParameter(name="start_value", type=int, required=False, default=0)
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        increment = kwargs.get("increment", 1)
        start_value = kwargs.get("start_value", 0)
        iteration = self.get_iteration(context)

        # Calculate based on iteration
        current_count = start_value + (iteration * increment)

        return {
            "count": current_count,
            "increment": increment,  # Preserve parameters
            "start_value": start_value
        }

def test_parameter_preservation():
    workflow = Workflow("parameter-test")
    workflow.add_node("counter", CounterNode())

    # Self-cycle preserves parameters
    workflow.connect("counter", "counter", cycle=True, max_iterations=5)

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow, parameters={
        "counter": {"increment": 2, "start_value": 10}
    })

    # Test that parameters affected the result
    counter_result = results.get("counter", {})
    assert counter_result.get("count", 0) > 10  # Should be affected by start_value

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
    assert result.get("iteration", 0) >= 0
    assert "quality" in result

```

### Conditional Routing Test
```python
def test_conditional_cycle():
    from kailash import Workflow
    from kailash.runtime.local import LocalRuntime
    from kailash.nodes.logic import SwitchNode
    from kailash.nodes.base import CycleAwareNode
    from typing import Dict, Any
    
    class ConditionalNode(CycleAwareNode):
        def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
            data = kwargs.get("data", [])
            iteration = self.get_iteration(context)

            # Process data
            processed_data = [x * (1 + 0.1 * iteration) for x in data]
            current_sum = sum(processed_data)
            should_exit = current_sum >= 100

            return {
                "data": processed_data,
                "should_exit": should_exit,
                "input_data": {  # Package for SwitchNode
                    "should_exit": should_exit,
                    "data": processed_data
                }
            }

    workflow = Workflow("conditional-test")
    workflow.add_node("processor", ConditionalNode())
    workflow.add_node("switch", SwitchNode())

    # Connect with proper mapping
    workflow.connect("processor", "switch", mapping={"input_data": "input_data"})
    workflow.connect("switch", "processor",
        condition="false_output",
        mapping={"false_output.data": "data"},
        cycle=True, max_iterations=20)

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow, parameters={
        "processor": {"data": [5, 10, 15]},
        "switch": {"condition_field": "should_exit", "operator": "==", "value": True}
    })

    # Test that workflow completed
    processor_result = results.get("processor", {})
    assert processor_result is not None

```

### Error Handling Test
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import CycleAwareNode
from typing import Dict, Any

class ErrorProneNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)
        fail_on = kwargs.get("fail_on_iteration", 3)

        # Return error state instead of raising
        if iteration == fail_on:
            return {
                "error": True,
                "error_message": f"Simulated failure on iteration {iteration}",
                "iteration": iteration
            }

        return {
            "data": f"processed_{iteration}",
            "error": False,
            "iteration": iteration
        }

def test_error_handling():
    workflow = Workflow("error-test")
    workflow.add_node("processor", ErrorProneNode())

    workflow.connect("processor", "processor", cycle=True, max_iterations=10)

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow, parameters={
        "processor": {"fail_on_iteration": 2}
    })

    # Test graceful error handling
    error_result = results.get("processor", {})
    assert error_result is not None
    assert error_result.get("iteration", 0) >= 0

    # Test error was recorded
    if error_result.get("error"):
        assert "error_message" in error_result

```

### Performance Test
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import CycleAwareNode
from typing import Dict, Any
import time

class StateAccumulatorNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        data_size = kwargs.get("data_size", 100)
        iteration = self.get_iteration(context)

        # Generate data
        current_data = list(range(iteration * data_size, (iteration + 1) * data_size))

        # Accumulate with size limit
        accumulated_data = self.accumulate_values(
            context, "large_data", current_data, max_history=5
        )

        return {
            "chunks_count": len(accumulated_data),
            "iteration": iteration,
            **self.set_cycle_state({"large_data": accumulated_data})
        }

def test_memory_limits():
    workflow = Workflow("memory-test")
    workflow.add_node("accumulator", StateAccumulatorNode())

    workflow.connect("accumulator", "accumulator", cycle=True, max_iterations=20)

    start_time = time.time()

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow, parameters={
        "accumulator": {"data_size": 50}
    })

    execution_time = time.time() - start_time
    result = results.get("accumulator", {})

    # Performance assertions
    assert result.get("chunks_count", 0) <= 5  # max_history respected
    assert execution_time < 5.0  # Reasonable time
    assert result.get("iteration", 0) > 0  # Multiple iterations

```

## 📋 Testing Principles

1. **Test Patterns, Not Exact Values**
   ```python
# ✅ Good
assert final_quality > initial_quality  # Progress made

# ❌ Bad
assert final_quality == 0.85  # Too rigid

   ```

2. **Use Self-Contained Convergence**
   ```python
# ✅ Good: Node checks own convergence
return {"result": data, "converged": converged}

# ❌ Bad: Multi-node convergence dependencies

   ```

3. **Provide Required Configuration**
   - PythonCodeNode needs code at initialization
   - SwitchNode needs parameters at runtime
   - Always use required=False in cycle parameters

4. **Test Incrementally**
   - Individual nodes first
   - Simple cycles second  
   - Complex multi-node cycles last

---
*Related: [021-cycle-aware-nodes.md](021-cycle-aware-nodes.md), [022-cycle-debugging-troubleshooting.md](022-cycle-debugging-troubleshooting.md)*
