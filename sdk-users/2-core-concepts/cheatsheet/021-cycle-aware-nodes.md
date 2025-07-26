# Cycle-Aware Nodes

*Essential patterns for cycle-aware node development*

## 🚀 Quick Setup

```python
from kailash.nodes.base import CycleAwareNode, NodeParameter
from typing import Any, Dict

class OptimizerNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "quality": NodeParameter(name="quality", type=float, required=False, default=0.0),
            "target": NodeParameter(name="target", type=float, required=False, default=0.8)
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        # Get cycle info
        iteration = self.get_iteration()
        prev_state = self.get_previous_state()

        # Get parameters with state fallback
        quality = kwargs.get("quality", 0.0)
        target = kwargs.get("target", prev_state.get("target", 0.8))

        # Process one iteration
        new_quality = min(1.0, quality + 0.1)
        converged = new_quality >= target

        return {
            "quality": new_quality,
            "converged": converged,
            "iteration": iteration,
            **self.set_cycle_state({"target": target})
        }

```

## 🔧 Core Patterns

### State Preservation Pattern
```python
def run(self, **kwargs):
    prev_state = self.get_previous_state()

    # Preserve config from first iteration
    targets = kwargs.get("targets", prev_state.get("targets", {}))
    learning_rate = prev_state.get("learning_rate", 0.1)

    # Calculate current error (example calculation)
    data = kwargs.get("data", [])
    current_error = sum(abs(x - 50) for x in data) / len(data) if data else 1.0

    # Adaptive processing
    if prev_state.get("error"):
        improvement = prev_state["error"] - current_error
        if improvement < 0.01:
            learning_rate *= 0.9

    # Example processing function
    def process_data():
        return [x * learning_rate for x in data]

    return {
        "result": process_data(),
        **self.set_cycle_state({
            "targets": targets,
            "learning_rate": learning_rate,
            "error": current_error
        })
    }

```

### Accumulation Pattern
```python
def run(self, **kwargs):
    current_value = calculate_metric(kwargs.get("data"))

    # Track history with size limit
    history = self.accumulate_values(
        "metrics", current_value, max_history=10
    )

    # Calculate trend
    if len(history) >= 3:
        recent_avg = sum(history[-3:]) / 3
        trend = "improving" if recent_avg > history[0] else "stable"
    else:
        trend = "insufficient_data"

    return {
        "value": current_value,
        "trend": trend,
        "converged": current_value >= 0.95
    }

```

## 🎯 Convergence Patterns

### Self-Contained Convergence
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import CycleAwareNode

class SelfConvergingNode(CycleAwareNode):
    def run(self, **kwargs):
        quality = kwargs.get("quality", 0.0)
        target = kwargs.get("target", 0.8)

        # Improve quality
        new_quality = min(1.0, quality + 0.1)

        # Built-in convergence check
        converged = new_quality >= target

        return {
            "quality": new_quality,
            "converged": converged,  # Self-determines convergence
            "iteration": self.get_iteration()
        }

# Usage
workflow = WorkflowBuilder()
workflow.add_node("SelfConvergingNode", "improver", {}))
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### ConvergenceCheckerNode Usage
```python
from kailash.nodes.logic import ConvergenceCheckerNode

# Add to workflow
workflow.add_node("ConvergenceCheckerNode", "convergence", {}))

# Runtime parameters (not initialization)
runtime.execute(workflow, parameters={
    "convergence": {
        "threshold": 0.85,
        "mode": "threshold"  # or "stability", "improvement"
    }
})

```

## ⚠️ Critical Rules

### NodeParameter Requirements
```python
from kailash.nodes.base import NodeParameter
from typing import Dict

# ✅ ALWAYS use required=False in cycles
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        "data": NodeParameter(
            name="data", type=list,
            required=False, default=[]  # Required!
        ),
        "threshold": NodeParameter(
            name="threshold", type=float,
            required=False, default=0.8
        )
    }

# ❌ NEVER use required=True in cycles - THIS IS WRONG!
# def get_parameters(self):
#     return {
#         "data": NodeParameter(name="data", type=list, required=True)  # WRONG!
#     }

```

### Data Pass-Through
```python
def run(self, **kwargs):
    # Process main value
    result = process_value(kwargs.get("value", 0.0))

    # Always preserve data parameter
    output = {"processed_value": result}
    if "data" in kwargs:
        output["data"] = kwargs["data"]

    return output

```

## 🔄 Simple Cycle Setup

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create cycle-aware node (assuming OptimizerNode is defined above)
workflow = WorkflowBuilder()
workflow.add_node("OptimizerNode", "optimizer", {}))

# Connect to itself
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "optimizer": {"target": 0.9}
})

```

## 🔍 Common Issues

### ~~Parameter Loss After First Iteration~~ (Fixed in v0.5.1+)
**Update**: Initial parameters are now preserved throughout all cycle iterations!

```python
# ✅ This now works correctly (v0.5.1+)
def run(self, **kwargs):
    # Initial parameters are available in ALL iterations
    targets = kwargs.get("targets", {})  # No longer empty after iter 1!
    learning_rate = kwargs.get("learning_rate", 0.01)  # Consistent across iterations

    # You can still use state preservation for dynamic values
    prev_state = self.get_previous_state()
    accumulated_data = prev_state.get("accumulated_data", [])

    result = process(targets, learning_rate)
    accumulated_data.append(result)

    return {
        "result": result,
        **self.set_cycle_state({"accumulated_data": accumulated_data})
    }

```

### Safe Context Access
```python
def run(self, context, **kwargs):
    # ✅ Safe access patterns
    cycle_info = context.get("cycle", {})
    iteration = cycle_info.get("iteration", 0)
    node_state = cycle_info.get("node_state") or {}

    # ❌ Don't access directly
    # iteration = context["cycle"]["iteration"]  # KeyError!

```

## 📝 Quick Reference

### Essential Methods
- `self.get_iteration(context)` - Current iteration (0-based)
- `self.is_first_iteration(context)` - True if first iteration
- `self.get_previous_state(context)` - State from previous iteration
- `self.set_cycle_state(data)` - Save state for next iteration
- `self.accumulate_values(context, key, value, max_history)` - Track values

### Best Practices
1. Always use `required=False` in parameters
2. Preserve configuration in state
3. Use self-contained convergence
4. Handle missing parameters gracefully
5. Log progress periodically

---
*Related: [022-cycle-debugging-troubleshooting.md](022-cycle-debugging-troubleshooting.md), [027-cycle-aware-testing-patterns.md](027-cycle-aware-testing-patterns.md)*
