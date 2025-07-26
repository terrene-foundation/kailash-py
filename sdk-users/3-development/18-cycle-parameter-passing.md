# Cycle Parameter Passing Guide

*Master parameter flow in cyclic workflows*

## Overview

Parameter passing in cyclic workflows requires special attention. This guide provides definitive patterns for correctly passing parameters through cycles, especially with `PythonCodeNode`.

## Prerequisites

- Completed [Parameter Passing Guide](11-parameter-passing-guide.md)
- Understanding of [Workflows](02-workflows.md)
- Basic knowledge of cyclic patterns

## Critical Rules

### 1. PythonCodeNode Output Mapping

**Rule**: `PythonCodeNode` wraps outputs in a `result` dictionary.

```python
# ✅ CORRECT - Use dot notation for PythonCodeNode outputs
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# ❌ WRONG - Direct mapping doesn't work
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()
```

### 2. Initial Parameters for Cycles

**Rule**: Cycles need initial parameters on first iteration.

```python
# ✅ CORRECT - Provide initial parameters
runtime.execute(workflow, parameters={
    "counter": {"count": 0}  # Node-specific initial value
})

# ❌ WRONG - No initial parameters
runtime.execute(workflow.build())  # Error: parameter 'count' not provided
```

### 3. Convergence Check Syntax

**Rule**: Use the correct field reference in convergence checks.

```python
# ✅ CORRECT - Check output field
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Note: The convergence check evaluates the OUTPUT of the node
```

## Complete Working Examples

### Simple Self-Cycle

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow with self-cycle
workflow = WorkflowBuilder()

# Counter that increments until target
workflow.add_node("PythonCodeNode", "counter", {
    "code": """
# Get current count (from initial params or previous iteration)
current = count + 1

# Check if we've reached target
result = {
    "count": current,
    "converged": current >= 5,
    "history": f"Iteration {current}"
}
"""
})

# Create self-cycle with proper mapping
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Execute with initial parameters
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "counter": {"count": 0}  # REQUIRED: Initial value
})

# Access final result
print(f"Final count: {results['counter']['count']}")  # 5
print(f"Converged: {results['counter']['converged']}")  # True
```

### Two-Node Cycle

```python
# Create producer-validator cycle
workflow = WorkflowBuilder()

# Producer generates values
workflow.add_node("PythonCodeNode", "producer", {
    "code": """
# Generate next value
next_value = current_value * 2 if current_value > 0 else 1

result = {
    "value": next_value,
    "iteration": iteration + 1
}
"""
})

# Validator checks values
workflow.add_node("PythonCodeNode", "validator", {
    "code": """
# Validate the value
is_valid = value < 1000
should_continue = is_valid and iteration < 10

result = {
    "validated_value": value if is_valid else current_value,
    "converged": not should_continue,
    "iteration": iteration
}
"""
})

# Connect in a cycle
workflow.add_connection("producer", "result", "validator", "data")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()
workflow.add_connection("validator", "result.iteration", "producer", "iteration")

# Execute with initial parameters for both nodes
results, _ = runtime.execute(workflow.build(), parameters={
    "producer": {"current_value": 1, "iteration": 0},
    "validator": {"current_value": 1, "iteration": 0}
})
```

### Complex Multi-Parameter Cycle

```python
# Optimization workflow with multiple parameters
workflow = WorkflowBuilder()

# Optimizer node
workflow.add_node("PythonCodeNode", "optimizer", {
    "code": """
import json

# Parse previous state if exists
if isinstance(state, str):
    state = json.loads(state) if state else {}

# Current parameters
learning_rate = config.get("learning_rate", 0.01)
momentum = config.get("momentum", 0.9)

# Update weights (simplified)
current_loss = state.get("loss", 1.0)
velocity = state.get("velocity", 0.0)

# Apply momentum
velocity = momentum * velocity + learning_rate * current_loss
new_loss = max(0, current_loss - velocity)

# Prepare result
result = {
    "loss": new_loss,
    "converged": new_loss < 0.01,
    "state": json.dumps({
        "loss": new_loss,
        "velocity": velocity,
        "iteration": state.get("iteration", 0) + 1
    }),
    "metrics": {
        "improvement": current_loss - new_loss,
        "convergence_rate": velocity
    }
}
"""
})

# Create self-cycle with state preservation
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Execute with initial configuration
results, _ = runtime.execute(workflow.build(), parameters={
    "optimizer": {
        "state": json.dumps({"loss": 1.0, "velocity": 0.0, "iteration": 0}),
        "config": {"learning_rate": 0.05, "momentum": 0.9}
    }
})

final_state = json.loads(results["optimizer"]["state"])
print(f"Final loss: {final_state['loss']}")
print(f"Total iterations: {final_state['iteration']}")
```

## Advanced Patterns

### Conditional Cycles

```python
# Cycle with conditional paths
workflow = WorkflowBuilder()

# Processing node
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Process data based on mode
if mode == "fast":
    processed = data * 2
    threshold = 100
else:
    processed = data ** 2
    threshold = 1000

result = {
    "data": processed,
    "converged": processed > threshold,
    "mode": "slow" if processed > 50 else "fast"
}
"""
})

# Conditional routing
workflow.add_node("SwitchNode", "router", {
    "condition": "converged == True"
})

# Connect with cycle through router
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
```

### Nested State Management

```python
# Complex state with nested cycles
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "state_manager", {
    "code": """
import json

# Initialize or parse state
if isinstance(full_state, str):
    state = json.loads(full_state)
else:
    state = {
        "counters": {"main": 0, "sub": 0},
        "data": [],
        "config": full_state.get("config", {})
    }

# Update counters
state["counters"]["main"] += 1
if state["counters"]["main"] % 5 == 0:
    state["counters"]["sub"] += 1

# Accumulate data
state["data"].append({
    "iteration": state["counters"]["main"],
    "value": state["counters"]["main"] * state["counters"]["sub"]
})

# Check convergence
converged = (
    state["counters"]["main"] >= 20 or
    state["counters"]["sub"] >= 5
)

result = {
    "state": json.dumps(state),
    "converged": converged,
    "summary": {
        "total_iterations": state["counters"]["main"],
        "sub_cycles": state["counters"]["sub"],
        "data_points": len(state["data"])
    }
}
"""
})

# Self-cycle with state
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()
```

## Common Pitfalls and Solutions

### 1. Missing Initial Parameters

```python
# ❌ PROBLEM: No initial parameters
results, _ = runtime.execute(workflow.build())
# Error: Parameter 'count' not provided for node 'counter'

# ✅ SOLUTION: Always provide initial parameters for cycle nodes
results, _ = runtime.execute(workflow.build(), parameters={
    "counter": {"count": 0}
})
```

### 2. Incorrect Output Mapping

```python
# ❌ PROBLEM: Forgetting result wrapper
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()
# Error: Output 'value' not found

# ✅ SOLUTION: Use dot notation for PythonCodeNode
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()
```

### 3. State Serialization Issues

```python
# ❌ PROBLEM: Passing complex objects
result = {
    "state": {"obj": some_complex_object}  # Can't serialize
}

# ✅ SOLUTION: Serialize to JSON
import json
result = {
    "state": json.dumps({"data": simple_data})
}
```

### 4. Convergence Check Errors

```python
# ❌ PROBLEM: Checking nested fields in convergence
convergence_check="result.converged == True"  # Won't work

# ✅ SOLUTION: Check top-level output fields
convergence_check="converged == True"  # Correct
```

## Best Practices

### 1. Clear State Structure

```python
# Define state schema clearly
STATE_SCHEMA = {
    "iteration": 0,
    "current_value": 0.0,
    "history": [],
    "converged": False
}

# Use consistent serialization
def serialize_state(state):
    return json.dumps(state)

def deserialize_state(state_str):
    return json.loads(state_str) if state_str else STATE_SCHEMA.copy()
```

### 2. Debugging Cycles

```python
# Add debug information to outputs
result = {
    "value": processed_value,
    "converged": is_converged,
    "_debug": {
        "iteration": current_iteration,
        "input_params": kwargs,
        "state_size": len(str(state))
    }
}
```

### 3. Performance Optimization

```python
# Limit state size in long-running cycles
MAX_HISTORY = 100

# Trim history to prevent memory growth
if len(state["history"]) > MAX_HISTORY:
    state["history"] = state["history"][-MAX_HISTORY:]
```

### 4. Error Handling in Cycles

```python
# Graceful error handling
try:
    processed = process_data(data)
    result = {"data": processed, "converged": False}
except Exception as e:
    # Don't let errors break the cycle
    result = {
        "data": data,  # Pass through unchanged
        "converged": True,  # Stop on error
        "error": str(e)
    }
```

## Testing Cycle Workflows

```python
def test_cycle_convergence():
    """Test that cycle converges correctly."""
    workflow = create_cycle_workflow()

    # Test with different initial values
    test_cases = [
        {"count": 0, "expected_iterations": 5},
        {"count": 3, "expected_iterations": 2},
        {"count": 10, "expected_iterations": 1}  # Already converged
    ]

    for case in test_cases:
        results, _ = runtime.execute(workflow.build(), parameters={
            "counter": {"count": case["count"]}
        })

        assert results["counter"]["converged"] == True
        # Verify iteration count matches expectation
```

## Related Guides

**Prerequisites:**
- [Parameter Passing Guide](11-parameter-passing-guide.md) - Basic parameter concepts
- [Workflows](02-workflows.md) - Workflow fundamentals

**Advanced Topics:**
- [Async Workflow Builder](07-async-workflow-builder.md) - Async cycles
- [Testing Guide](12-testing-production-quality.md) - Testing cycles

---

**Master cyclic workflows with proper parameter passing for iterative algorithms and feedback loops!**
