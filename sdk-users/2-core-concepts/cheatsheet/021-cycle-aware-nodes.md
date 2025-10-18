# Cycle-Aware Nodes

*Essential patterns for cycle-aware node development*

## 🚀 Quick Setup

```python
# Cycle-aware functionality using PythonCodeNode with persistent state
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create optimizer using PythonCodeNode with cycle-aware patterns
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "optimizer", {
    "code": """
# Cycle-aware state management using class variables
class CycleState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.iteration = 0
            cls._instance.state = {}
        return cls._instance

    def get_iteration(self):
        return self.iteration

    def increment_iteration(self):
        self.iteration += 1

    def get_previous_state(self):
        return self.state.copy()

    def set_cycle_state(self, data):
        self.state.update(data)
        return data

# Initialize cycle state
cycle_state = CycleState()

# Get parameters with state fallback
quality = input_data.get("quality", 0.0)
target = input_data.get("target", cycle_state.get_previous_state().get("target", 0.8))

# Process one iteration
new_quality = min(1.0, quality + 0.1)
converged = new_quality >= target

# Update state and increment iteration
cycle_state.set_cycle_state({"target": target})
cycle_state.increment_iteration()

result = {
    "quality": new_quality,
    "converged": converged,
    "iteration": cycle_state.get_iteration()
}
"""
})

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
workflow.add_node("PythonCodeNode", "self_converging", {
    "code": """
try:
    quality = input_data.get('quality', 0.0)
    target = input_data.get('target', 0.8)
except NameError:
    quality = 0.0
    target = 0.8

new_quality = min(1.0, quality + 0.1)
converged = new_quality >= target

result = {
    'quality': new_quality,
    'converged': converged
}
"""
})

# Build BEFORE creating cycle
built_workflow = workflow.build()

# Create cycle - CRITICAL: Use "result." prefix for PythonCodeNode
cycle = built_workflow.create_cycle("self_converging_cycle")
cycle.connect("self_converging", "self_converging", mapping={"result.quality": "input_data"}) \
     .max_iterations(15) \
     .converge_when("converged == True") \
     .build()

```

### ConvergenceCheckerNode Usage
```python
from kailash.nodes.logic import ConvergenceCheckerNode

# Add to workflow
workflow.add_node("PythonCodeNode", "convergence", {"code": "result = {"converged": input_data.get("value", 0.0) >= input_data.get("threshold", 0.85)}"})

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

# Create cycle-aware node using PythonCodeNode with state management
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "optimizer", {
    "code": """
# Cycle-aware state management
class OptimizerState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.quality = 0.0
        return cls._instance

state = OptimizerState()

try:
    target = input_data.get('target', 0.9)
except NameError:
    target = 0.9

state.quality = min(1.0, state.quality + 0.1)
converged = state.quality >= target

result = {
    'quality': state.quality,
    'target': target,
    'converged': converged
}
"""
})

# Build BEFORE creating cycle
built_workflow = workflow.build()

# Create cycle - CRITICAL: Use "result." prefix for PythonCodeNode
cycle = built_workflow.create_cycle("optimizer_cycle")
cycle.connect("optimizer", "optimizer", mapping={"result.quality": "input_data", "result.target": "target"}) \
     .max_iterations(20) \
     .converge_when("converged == True") \
     .build()

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow, parameters={
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
