# Mistake 074: Generic "output" Mapping Fails in Cycle Data Persistence

**Category**: Workflow & Execution
**Severity**: High
**Impact**: Cycle iterations don't preserve state between iterations

## Problem Description

Using generic `mapping={"output": "output"}` in cycle connections fails to preserve individual field values between cycle iterations, causing state variables like counters, quality scores, and accumulative data to reset each iteration.

## ❌ Wrong Patterns

### Generic Output Mapping (Fails)
```python
# This fails - individual fields are not preserved
workflow.connect("processor", "processor",
    mapping={"output": "output"},  # Generic mapping
    cycle=True,
    max_iterations=10,
    convergence_check="converged == True")

# Result: All state variables reset each iteration
# polling_count = 1, 1, 1, 1... (never increments)
# quality_score = 0.0, 0.0, 0.0... (never improves)
```

### Empty Mapping (Also Fails)
```python
# This also fails - no data transfer at all
workflow.connect("processor", "processor",
    mapping={},  # Empty mapping
    cycle=True)
# Result: Nodes receive no input parameters in subsequent iterations
```

## ✅ Correct Patterns

### Specific Field Mapping (Works)
```python
# Correct - explicitly map each field that needs to persist
workflow.connect("processor", "processor",
    mapping={
        "polling_count": "polling_count",      # State counter
        "quality_score": "quality_score",     # Progress metric
        "processed_data": "processed_data",   # Accumulated results
        "configuration": "configuration"      # Static config
    },
    cycle=True,
    max_iterations=10,
    convergence_check="converged == True")

# Result: Fields properly increment and accumulate
# polling_count = 1, 2, 3, 4... (increments correctly)
# quality_score = 0.2, 0.4, 0.7, 0.9... (improves over time)
```

### Complete Node Pattern with Source
```python
class DataSourceNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "initial_data": NodeParameter(name="initial_data", type=list, required=False)
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {"data": kwargs.get("initial_data", [])}

class ProcessorNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "iteration_count": NodeParameter(name="iteration_count", type=int, required=False, default=0),
            "quality_score": NodeParameter(name="quality_score", type=float, required=False, default=0.0)
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        data = kwargs.get("data", [])
        iteration_count = kwargs.get("iteration_count", 0) + 1
        quality_score = kwargs.get("quality_score", 0.0) + 0.1  # Improve each iteration

        # Process data
        processed_data = [x * 2 for x in data]
        converged = quality_score >= 0.8

        return {
            "data": processed_data,
            "iteration_count": iteration_count,
            "quality_score": quality_score,
            "converged": converged
        }

# Workflow setup
workflow.add_node("data_source", DataSourceNode())
workflow.add_node("processor", ProcessorNode())

# Initial data flow
workflow.connect("data_source", "processor",
    mapping={"data": "data"})

# Cycle with specific field mapping
workflow.connect("processor", "processor",
    mapping={
        "data": "data",
        "iteration_count": "iteration_count",
        "quality_score": "quality_score"
    },
    cycle=True,
    max_iterations=10,
    convergence_check="converged == True")

# Execute with node-specific parameters
runtime.execute(workflow, parameters={
    "data_source": {"initial_data": [1, 2, 3, 4]}
})
```

## Root Cause Analysis

### Why Generic Mapping Fails
1. **Field Granularity**: The `{"output": "output"}` pattern treats the entire output as a single blob
2. **Type Mismatch**: Individual fields within the output aren't accessible for parameter mapping
3. **State Loss**: Node state variables aren't properly threaded between iterations
4. **Parameter Resolution**: CycleAwareNode helper methods can't access preserved state

### Technical Details
```python
# What happens with generic mapping:
iteration_0: node.run(context, data=[1,2,3])
    → returns {"count": 1, "data": [2,4,6], "converged": False}
iteration_1: node.run(context, output={"count": 1, "data": [2,4,6], "converged": False})
    → count parameter not found, defaults to 0 again
    → returns {"count": 1, "data": [4,8,12], "converged": False}  # count reset!

# What happens with specific mapping:
iteration_0: node.run(context, data=[1,2,3])
    → returns {"count": 1, "data": [2,4,6], "converged": False}
iteration_1: node.run(context, count=1, data=[2,4,6])
    → count parameter found, increments to 2
    → returns {"count": 2, "data": [4,8,12], "converged": False}  # count preserved!
```

## Common Symptoms

### Symptom 1: Counters Don't Increment
```python
# Test fails with assertion error
assert final_output["polling_count"] >= 3
# AssertionError: assert 1 >= 3  (counter never increments)
```

### Symptom 2: Quality Scores Don't Improve
```python
# Test fails with assertion error
assert final_output["quality_score"] >= 0.7
# AssertionError: assert 0.0 >= 0.7  (score never improves)
```

### Symptom 3: Data Accumulation Fails
```python
# Test fails with assertion error
assert final_output["total_fetched"] == 45
# AssertionError: assert 10 == 45  (only first page fetched repeatedly)
```

## Detection Strategies

### Test Pattern to Detect the Issue
```python
def test_cycle_state_persistence():
    """Test that cycle state persists between iterations."""

    # Run a simple counter cycle
    results = runtime.execute(workflow, parameters={"initial_count": 0})

    # Check if counter actually incremented
    final_count = results["counter_node"]["count"]
    iterations = results["counter_node"]["iteration"]

    # If generic mapping is used, count will equal 1 regardless of iterations
    # If specific mapping is used, count will equal iterations
    assert final_count == iterations, f"State not persisting: count={final_count}, iterations={iterations}"
```

### Debug Logging Pattern
```python
class DebugCycleNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)

        # Log what parameters were received
        self.log_cycle_info(context, f"Iteration {iteration} received: {list(kwargs.keys())}")

        # Check if expected state is preserved
        expected_count = kwargs.get("count", 0)
        self.log_cycle_info(context, f"Expected count: {expected_count}, iteration: {iteration}")

        # If count != iteration, mapping is not working
        if expected_count != iteration and iteration > 0:
            self.log_cycle_info(context, "WARNING: State not preserved between iterations!")
```

## Prevention Guidelines

### 1. Always Use Specific Field Mapping in Cycles
```python
# ✅ Always specify exact fields to transfer
mapping = {
    "state_field_1": "state_field_1",
    "state_field_2": "state_field_2",
    "config_field": "config_field"
}
```

### 2. Include All Stateful Fields
```python
# ✅ Map every field that needs to persist
mapping = {
    "counter": "counter",           # Iteration counters
    "accumulator": "accumulator",   # Accumulated results
    "quality": "quality",           # Progress metrics
    "config": "config",             # Static configuration
    "threshold": "threshold"        # Convergence criteria
}
```

### 3. Use Source Nodes for Initial Data
```python
# ✅ Provide initial data through source nodes
class DataSourceNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {"initial_data": kwargs.get("data", [])}

# ✅ Use node-specific parameters
runtime.execute(workflow, parameters={
    "data_source": {"data": [1, 2, 3]}  # Node-specific
})
```

### 4. Test State Persistence Explicitly
```python
def test_state_persistence():
    """Verify that cycle state persists correctly."""
    # Test should verify that stateful fields increment/change appropriately
    assert counter_increments_correctly()
    assert quality_improves_over_time()
    assert accumulation_works_properly()
```

## Impact Assessment

### Development Impact
- **Test Failures**: Cycle tests fail due to state not persisting
- **Debugging Difficulty**: Hard to diagnose why cycles don't converge
- **False Convergence**: Cycles may appear to work but don't actually progress

### Runtime Impact
- **Infinite Loops**: Cycles that never converge due to lack of progress
- **Performance Degradation**: Repeated processing of same data
- **Incorrect Results**: Accumulated data lost between iterations

## Related Mistakes
- [071](071-cyclic-workflow-parameter-passing-patterns.md) - Parameter passing patterns
- [072](072-switchnode-mapping-specificity.md) - SwitchNode mapping requirements
- [073](073-cycle-state-persistence-assumptions.md) - State persistence assumptions

## Related Documentation
- [020-switchnode-conditional-routing.md](../reference/cheatsheet/020-switchnode-conditional-routing.md) - SwitchNode patterns
- [030-cycle-state-persistence-patterns.md](../reference/cheatsheet/030-cycle-state-persistence-patterns.md) - State persistence

---

**Key Takeaway**: In cyclic workflows, **specific field mapping is essential** for state persistence. Never use generic `{"output": "output"}` mapping - always explicitly map each field that needs to persist between cycle iterations.
