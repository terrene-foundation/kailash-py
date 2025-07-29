# Mistake 074: Generic "output" Mapping Fails in Cycle Data Persistence

**Category**: Workflow & Execution
**Severity**: High
**Impact**: Cycle iterations don't preserve state between iterations

## Problem Description

Using generic `mapping={"output": "output"}` in cycle connections fails to preserve individual field values between cycle iterations, causing state variables like counters, quality scores, and accumulative data to reset each iteration.

## ❌ Wrong Patterns

### Generic Output Mapping (Fails)
```python
# ❌ WRONG #1: Deprecated cycle=True with generic mapping
workflow.connect("processor", "processor",
    mapping={"output": "output"},  # Generic mapping
    cycle=True,  # DEPRECATED!
    max_iterations=10,
    convergence_check="converged == True")

# ❌ WRONG #2: Even with CycleBuilder, generic mapping fails
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle('failed_cycle')
cycle_builder.connect('processor', 'processor', mapping={'output': 'output'})  # Generic mapping fails!
cycle_builder.max_iterations(10)
cycle_builder.build()

# Result: All state variables reset each iteration
# polling_count = 1, 1, 1, 1... (never increments)
# quality_score = 0.0, 0.0, 0.0... (never improves)
```

### Empty Mapping (Also Fails)
```python
# ❌ WRONG: Empty mapping with deprecated cycle=True
workflow.connect("processor", "processor",
    mapping={},  # Empty mapping
    cycle=True)  # DEPRECATED!
# Result: Nodes receive no input parameters in subsequent iterations
```

## ✅ Correct Patterns

### Specific Field Mapping (Works)
```python
# ✅ CORRECT - Modern CycleBuilder API with specific field mapping
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Access specific fields via parameter names
try:
    polling_count = processor_data.get("polling_count", 0)
    quality_score = processor_data.get("quality_score", 0.0)
    processed_data = processor_data.get("processed_data", [])
    configuration = processor_data.get("configuration", {})
except NameError:
    # First iteration
    polling_count = 0
    quality_score = 0.0
    processed_data = []
    configuration = {"threshold": 0.8}

# Increment state values
new_polling_count = polling_count + 1
new_quality_score = min(quality_score + 0.15, 1.0)
new_processed_data = processed_data + [f"item_{new_polling_count}"]

result = {
    "polling_count": new_polling_count,
    "quality_score": new_quality_score,
    "processed_data": new_processed_data,
    "configuration": configuration,
    "converged": new_quality_score >= configuration["threshold"]
}
"""
})

# Build workflow and create cycle with correct mapping pattern
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle('state_persistence_cycle')
cycle_builder.connect('processor', 'processor', mapping={'result': 'processor_data'})
cycle_builder.max_iterations(10)
cycle_builder.converge_when('converged == True')
cycle_builder.build()

# Execute with runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)

# Result: Fields properly increment and accumulate
# polling_count = 1, 2, 3, 4... (increments correctly)
# quality_score = 0.15, 0.30, 0.45, 0.60... (improves over time)
```

### Complete Pattern with Source Node
```python
# ✅ CORRECT - Complete WorkflowBuilder pattern with source node
workflow = WorkflowBuilder()

# Data source node provides initial data
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'data': [1, 2, 3, 4], 'initial': True}"
})

# Processor node that maintains state across iterations
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Get data from source or previous iteration
try:
    data = source_data.get("data", [])
    iteration_count = source_data.get("iteration_count", 0)
    quality_score = source_data.get("quality_score", 0.0)
except NameError:
    # Access from processor_data for cycle iterations
    try:
        data = processor_data.get("data", [])
        iteration_count = processor_data.get("iteration_count", 0)
        quality_score = processor_data.get("quality_score", 0.0)
    except NameError:
        data = []
        iteration_count = 0
        quality_score = 0.0

# Increment state
new_iteration_count = iteration_count + 1
new_quality_score = min(quality_score + 0.1, 1.0)

# Process data
processed_data = [x * 2 for x in data]
converged = new_quality_score >= 0.8

result = {
    "data": processed_data,
    "iteration_count": new_iteration_count,
    "quality_score": new_quality_score,
    "converged": converged
}
"""
})

# Initial data flow from source to processor
workflow.add_connection("data_source", "result", "processor", "source_data")

# Build workflow and create cycle with specific field mapping
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle('complete_cycle')
cycle_builder.connect('processor', 'processor', mapping={
    "data": "data",
    "iteration_count": "iteration_count",
    "quality_score": "quality_score"
})
cycle_builder.max_iterations(10)
cycle_builder.converge_when('converged == True')
cycle_builder.build()

# Execute with runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)
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
