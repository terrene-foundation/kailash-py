# Cyclic Workflows Phase 1 - Reference Document

## Current Status: ✅ RESOLVED - Ready for Phase 2

### The Core Problem (FIXED)

Runtime parameters were not propagating correctly through cycle iterations. This issue has been resolved with two key fixes:

1. **Graph edge mapping fix**: The `connect()` method was overwriting mappings when multiple fields were specified. Fixed by storing the complete mapping dictionary in a single edge.

2. **Initial parameters fix**: The CyclicWorkflowExecutor was treating initial parameters as outputs, causing DAG nodes to be skipped. Fixed by storing initial parameters separately.

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

# Example of the issue:
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Iteration 0: quality = 0.3 (from initial input)
# Iteration 1: quality = 0.0 (reverted to default!)  ❌
# Expected: quality = 0.5 (from previous output)     ✅

```

### Root Cause Analysis

Based on testing and the mistakes documentation, particularly:
- **Mistake 058**: Node Configuration vs Runtime Parameters Confusion
- **Mistake 060**: Incorrect Cycle State Access Patterns

The issue appears to be in how `CyclicWorkflowExecutor` handles parameter passing between iterations. The executor is likely:

1. Not preserving the output → input mapping through the cycle
2. Applying node defaults instead of cycle-mapped values
3. Possibly confusing configuration parameters with runtime parameters

### What Works ✅

1. **Simple Self-Loop Cycles**
   - Single node with self-connection
   - Basic state tracking via `_cycle_state`
   - Iteration counting and convergence checks

2. **Core Infrastructure**
   - Cycle detection and validation
   - Convergence conditions (expressions, max iterations)
   - Safety limits (timeouts, memory)
   - All unit tests pass (12/12)

### What Doesn't Work ❌

1. **Parameter Propagation in Cycles**
   - Mapped values don't flow to next iteration
   - Defaults override runtime values
   - Multi-field mappings unreliable

2. **Complex Multi-Node Cycles**
   - Data loss between nodes
   - Convergence evaluates wrong values
   - Difficult to debug flow

### Evidence from Examples

#### Working Example (Simplified)
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

class CounterNode(Node):
    def run(self, context, **kwargs):
        count = kwargs.get("count", 0)
        return {"count": count + 1}

# Self-loop works because it's simple
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

#### Failing Example (Parameter Issue)
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

class ProcessorNode(Node):
    def run(self, context, **kwargs):
        quality = kwargs.get("quality", 0.0)  # Always gets 0.0 after iteration 0!
        print(f"Received quality: {quality}")
        return {"quality": quality + 0.2}

# Mapping doesn't preserve quality value
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### Debugging Approach

1. **Examine CyclicWorkflowExecutor**
   - How does it handle output → input for cycles?
   - Where are parameters merged/overridden?
   - Is there special handling for cycle connections?

2. **Check Parameter Flow**
   - Are outputs correctly captured?
   - How are they transformed for next iteration?
   - When do defaults get applied?

3. **Test Minimal Case**
   - Single parameter, single node
   - Print parameter values at each step
   - Trace through executor code

### Temporary Workarounds (Not Recommended)

1. **Use _cycle_state**
   ```python
   # Store in cycle state
   return {
       "quality": new_quality,
       "_cycle_state": {"saved_quality": new_quality}
   }

   # Retrieve in next iteration
   saved = cycle_info.get("node_state", {}).get("saved_quality", default)

   ```

2. **External State Management**
   - Store state outside the cycle
   - Not a clean solution

### Required Fix

The CyclicWorkflowExecutor needs to:

1. Preserve output values from cycle connections
2. Apply mappings correctly for next iteration
3. Only use defaults for first iteration or missing values
4. Handle both simple and complex mappings

### Test Case for Verification

```python
def test_cycle_parameter_propagation():
    """Test that parameters propagate through cycle iterations."""

    class AccumulatorNode(Node):
        def run(self, **kwargs):
            value = kwargs.get("value", 0)
            # In v0.5.0+, cycle info is accessed differently
            # This example shows the old pattern for historical reference

            # Should accumulate: 0 → 10 → 20 → 30
            return {"value": value + 10}

    workflow = WorkflowBuilder()
workflow.    workflow.add_node("AccumulatorNode", "acc", {}))
    # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

    executor = CyclicWorkflowExecutor()
    results, _ = executor.execute(workflow,
                                parameters={"acc": {"value": 0}})

    # This should pass but currently fails!
    assert results["acc"]["value"] == 30  # 0 + 10 + 10 + 10

```

### The Fix (Implemented)

Two critical fixes were applied:

1. **Fixed graph.py connect() method**:
   ```python
   # Before: Multiple add_connection calls overwrote mappings
   for src, dst in mapping.items():
       self.graph.add_connection(source, target, # mapping removed)  # ❌ Overwrites!

   # After: Single add_connection call with complete mapping
   edge_data = {
       "from_output": list(mapping.keys()),
       "to_input": list(mapping.values()),
       "mapping": mapping,  # Complete mapping dictionary
   }
   self.graph.add_connection(source_node, target_node, **edge_data)  # ✅ Preserves all!

   ```

2. **Fixed CyclicWorkflowExecutor initial parameters handling**:
   ```python
   # Before: Initial params treated as outputs
   if parameters:
       for node_id, node_params in parameters.items():
           state.node_outputs[node_id] = node_params  # ❌ Skips execution!

   # After: Initial params stored separately
# Parameters setup
workflow. parameters or {}  # ✅ Allows execution!

   ```

### Verification

All tests now pass:
- ✅ Single-field parameter propagation
- ✅ Multi-field parameter propagation
- ✅ DAG nodes feeding into cycles
- ✅ Complex workflows with initial parameters

### Next Steps

With parameter propagation fixed, we can now proceed to:

1. **Phase 2 Examples**: Create examples demonstrating convergence conditions and safety features
2. **Phase 2 Tests**: Add comprehensive tests for the Phase 2 features
3. **Documentation**: Update the cyclic workflows guide with working examples

### References

- `src/kailash/workflow/cyclic_runner.py` - The executor that needs fixing
- `guide/mistakes/058-*.md` - Config vs runtime parameters
- `guide/mistakes/060-*.md` - Cycle state access patterns
- `tests/test_workflow/test_cyclic_workflows.py` - Existing tests (need more)

## Conclusion

Phase 1 successfully implemented the core cyclic infrastructure, but parameter propagation issues prevent practical use. This must be fixed before proceeding to Phase 2. The issue is likely a simple oversight in the executor's parameter handling logic.
