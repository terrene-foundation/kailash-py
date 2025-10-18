# Cycle State Persistence Patterns

## ⚠️ Critical: Field-Specific Mapping Required

**IMPORTANT**: Generic `{"output": "output"}` mapping **DOES NOT** preserve individual fields between cycle iterations. Always use specific field mapping.

### ❌ Wrong: Generic Mapping (Causes State Loss)
```python
# This fails - state variables reset each iteration
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "counter", {
    "code": """
try:
    counter = input_data.get('counter', 0)
except NameError:
    counter = 0

result = {'counter': counter + 1, 'done': counter >= 5}
"""
})

built_workflow = workflow.build()
cycle = built_workflow.create_cycle("bad_cycle")
# ❌ WRONG: Generic mapping loses field values
cycle.connect("counter", "counter", mapping={"output": "input"}) \
     .max_iterations(10) \
     .converge_when("done == True") \
     .build()
# Result: counter = 1, 1, 1... (never increments)

```

### ✅ Correct: Specific Field Mapping (Preserves State)
```python
# This works - explicitly map each field that needs to persist
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "counter", {
    "code": """
try:
    counter = input_data.get('counter', 0)
except NameError:
    counter = 0

result = {'counter': counter + 1, 'done': counter >= 5}
"""
})

# 1. Build FIRST
built_workflow = workflow.build()

# 2. Create cycle
cycle = built_workflow.create_cycle("good_cycle")

# 3. CRITICAL: Use "result." prefix for PythonCodeNode + specific field mapping
cycle.connect("counter", "counter", mapping={"result.counter": "input_data"}) \
     .max_iterations(10) \
     .converge_when("done == True") \
     .build()
# Result: counter = 1, 2, 3... (increments correctly)

```

## Understanding State Persistence in Cycles

Cycle state persistence determines whether data accumulated across iterations is preserved. Understanding when state persists vs when it doesn't helps design robust cycle logic.

## Common State Persistence Issues

### ✅ Correct: Design for State Loss Scenarios
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create robust cycle node using PythonCodeNode
robust_cycle_code = '''
# Always check if state exists and provide fallbacks
accumulated_data = input_data.get("accumulated", []) if input_data else []
new_data = input_data.get("data", []) if input_data else []

# Use iteration count when state history is unreliable
iteration = input_data.get("iteration", 0)
if iteration >= 3:  # Simple iteration-based convergence
    converged = True
else:
    converged = len(accumulated_data) > 10  # State-based when available

result = {
    "processed_data": new_data,
    "accumulated": accumulated_data + new_data,
    "iteration": iteration + 1,
    "converged": converged
}
'''

workflow.add_node("PythonCodeNode", "robust_cycle", {"code": robust_cycle_code})

```

### ✅ Correct: Simplified Convergence When State Fails
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create simple convergence node using PythonCodeNode
simple_convergence_code = '''
data = input_data.get("data", []) if input_data else []
iteration = input_data.get("iteration", 0)

# Use simple iteration-based convergence instead of complex state tracking
# when state persistence is unreliable
improved_data = [x for x in data if x <= 50]  # Simple processing
quality_score = len(improved_data) / max(len(data), 1) if data else 0

# Iteration-based convergence (works regardless of state persistence)
converged = iteration >= 2 or quality_score >= 0.8

result = {
    "improved_data": improved_data,
    "quality_score": quality_score,
    "converged": converged,
    "iteration": iteration + 1
}
'''

workflow.add_node("PythonCodeNode", "simple_convergence", {"code": simple_convergence_code})

```

### ❌ Wrong: Relying on Complex State History
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Example of fragile cycle logic (DON'T USE)
fragile_cycle_code = '''
# This breaks when state doesn't persist
try:
    all_previous_results = input_data["results"]  # KeyError if state lost
    # Complex history-dependent logic would go here
    converged = len(all_previous_results) > 10
except (KeyError, TypeError):
    # This logic fails without state persistence
    converged = False

result = {"converged": converged}
'''

# DON'T USE: workflow.add_node("PythonCodeNode", "fragile_cycle", {"code": fragile_cycle_code})

```

## State Persistence Debugging

### Check State Availability
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create state debugging node using PythonCodeNode
state_debugging_code = '''
iteration = input_data.get("iteration", 0)
prev_state = input_data.get("prev_state")

# Debug state persistence
print(f"Iteration {iteration}: State available: {prev_state is not None}")
if prev_state:
    print(f"State keys: {list(prev_state.keys())}")
else:
    print("No previous state - using defaults")

# Graceful handling regardless of state
accumulated_count = prev_state.get("count", 0) if prev_state else 0

result = {
    "count": accumulated_count + 1,
    "state_available": prev_state is not None,
    "iteration": iteration
}
'''

workflow.add_node("PythonCodeNode", "state_debugging", {"code": state_debugging_code})

```

### Workaround Patterns

#### Use Data Flow Instead of State
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Instead of relying on state, pass data through connections
# Create data flow node using PythonCodeNode
data_flow_code = '''
# Get accumulated data from input (passed via mapping)
accumulated = input_data.get("accumulated_data", [])
new_item = input_data.get("new_item")

# Update accumulation
if new_item:
    accumulated.append(new_item)

# Return updated accumulation for next iteration
result = {
    "accumulated_data": accumulated,
    "converged": len(accumulated) >= 5
}
'''

workflow.add_node("PythonCodeNode", "data_flow", {"code": data_flow_code})

# Build workflow and create cycle with proper mapping
built_workflow = workflow.build()

# Create cycle with field-specific mapping
cycle = built_workflow.create_cycle("data_flow_cycle")
# CRITICAL: Use "result." prefix for PythonCodeNode outputs
cycle.connect("data_flow", "data_flow", mapping={"result.accumulated_data": "input_data"}) \
     .max_iterations(10) \
     .converge_when("converged == True") \
     .build()

```

#### Iteration-Based Logic
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create iteration-based node using PythonCodeNode
iteration_based_code = '''
iteration = input_data.get("iteration", 0)

# Base logic on iteration count rather than accumulated state
# This works regardless of state persistence

if iteration < 3:
    processing_intensity = "low"
elif iteration < 6:
    processing_intensity = "medium"
else:
    processing_intensity = "high"

# Simple convergence based on iteration
converged = iteration >= 5

result = {
    "processing_intensity": processing_intensity,
    "converged": converged,
    "iteration": iteration + 1
}
'''

workflow.add_node("PythonCodeNode", "iteration_based", {"code": iteration_based_code})

```

#### External State Storage
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create external state node using PythonCodeNode with global state
external_state_code = '''
import json
import os

iteration = input_data.get("iteration", 0)
run_id = input_data.get("run_id", "default")
new_data = input_data.get("data", [])

# Use external state storage (file-based for persistence)
state_file = f"/tmp/cycle_state_{run_id}.json"

try:
    with open(state_file, "r") as f:
        external_state = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    external_state = {}

state_key = f"{run_id}_{iteration}"

if state_key in external_state:
    previous_data = external_state[state_key]
else:
    previous_data = []

# Process and store
combined_data = previous_data + new_data
external_state[f"{run_id}_{iteration + 1}"] = combined_data

# Save state back to file
with open(state_file, "w") as f:
    json.dump(external_state, f)

result = {
    "combined_data": combined_data,
    "converged": len(combined_data) >= 10
}
'''

workflow.add_node("PythonCodeNode", "external_state", {"code": external_state_code})

```

## Best Practices

### Design for State Loss
1. **Always provide defaults** when accessing previous state
2. **Use iteration count** as backup for convergence logic
3. **Test both scenarios**: with and without state persistence
4. **Avoid complex state dependencies** in critical paths

### State Persistence Testing
```python
def test_node_without_state_persistence():
    """Test node behavior when state doesn't persist."""
    node = YourCycleNode()

    # Simulate multiple iterations without state
    for iteration in range(3):
        context = {"cycle": {"iteration": iteration}}
        result = node.execute(context, data=[1, 2, 3])

        # Node should still work without accumulated state
        assert "converged" in result
        assert result["iteration"] == iteration + 1

def test_node_with_state_persistence():
    """Test node behavior when state persists."""
    node = YourCycleNode()
    accumulated_state = {}

    for iteration in range(3):
        context = {
            "cycle": {
                "iteration": iteration,
                "node_state": accumulated_state
            }
        }
        result = node.execute(context, data=[1, 2, 3])

        # Update accumulated state for next iteration
        accumulated_state = {"count": result.get("count", 0)}

```

## Related Patterns
- [019-cyclic-workflows-basics.md](019-cyclic-workflows-basics.md) - Basic cycle patterns
- [022-cycle-debugging-troubleshooting.md](022-cycle-debugging-troubleshooting.md) - Debugging techniques
- [027-cycle-aware-testing-patterns.md](027-cycle-aware-testing-patterns.md) - Testing approaches

## Common Mistakes
- [060](../../../mistakes/060-incorrect-cycle-state-access-patterns.md) - Incorrect state access
- [061](../../../mistakes/061-overly-rigid-test-assertions-for-cycles.md) - Rigid test assertions
- [071](../../../mistakes/071-cyclic-workflow-parameter-passing-patterns.md) - Parameter passing issues
- [074](../../../mistakes/074-generic-output-mapping-in-cycles.md) - Generic output mapping fails ⚠️
