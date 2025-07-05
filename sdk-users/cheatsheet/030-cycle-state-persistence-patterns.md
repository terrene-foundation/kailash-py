# Cycle State Persistence Patterns

## ⚠️ Critical: Field-Specific Mapping Required

**IMPORTANT**: Generic `{"output": "output"}` mapping **DOES NOT** preserve individual fields between cycle iterations. Always use specific field mapping.

### ❌ Wrong: Generic Mapping (Causes State Loss)
```python
# This fails - state variables reset each iteration
workflow.connect("processor", "processor",
    mapping={"output": "output"},  # Generic mapping fails
    cycle=True)
# Result: counter = 1, 1, 1... (never increments)

```

### ✅ Correct: Specific Field Mapping (Preserves State)
```python
# This works - explicitly map each field that needs to persist
workflow.connect("processor", "processor",
    mapping={
        "counter": "counter",           # State variables
        "quality_score": "quality_score",  # Progress metrics
        "accumulated_data": "accumulated_data",  # Accumulated results
        "config": "config"              # Static configuration
    },
    cycle=True)
# Result: counter = 1, 2, 3... (increments correctly)

```

## Understanding State Persistence in Cycles

Cycle state persistence determines whether data accumulated across iterations is preserved. Understanding when state persists vs when it doesn't helps design robust cycle logic.

## Common State Persistence Issues

### ✅ Correct: Design for State Loss Scenarios
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

class RobustCycleNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)

        # Always check if state exists and provide fallbacks
        prev_state = self.get_previous_state(context)
        accumulated_data = prev_state.get("accumulated", []) if prev_state else []

        # Process data with iteration-based logic as backup
        new_data = kwargs.get("data", [])

        # Use iteration count when state history is unreliable
        if iteration >= 3:  # Simple iteration-based convergence
            converged = True
        else:
            converged = len(accumulated_data) > 10  # State-based when available

        # Update state (may or may not persist)
        self.set_cycle_state({"accumulated": accumulated_data + new_data})

        return {
            "processed_data": new_data,
            "iteration": iteration + 1,
            "converged": converged
        }

```

### ✅ Correct: Simplified Convergence When State Fails
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

class SimpleConvergenceNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)
        data = kwargs.get("data", [])

        # Use simple iteration-based convergence instead of complex state tracking
        # when state persistence is unreliable
        improved_data = [x for x in data if x <= 50]  # Simple processing
        quality_score = len(improved_data) / max(len(data), 1) if data else 0

        # Iteration-based convergence (works regardless of state persistence)
        converged = iteration >= 2 or quality_score >= 0.8

        return {
            "improved_data": improved_data,
            "quality_score": quality_score,
            "converged": converged,
            "iteration": iteration + 1
        }

```

### ❌ Wrong: Relying on Complex State History
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

class FragileCycleNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        # This breaks when state doesn't persist
        prev_state = self.get_previous_state(context)
        all_previous_results = prev_state["results"]  # KeyError if state lost

        # Complex history-dependent logic
        improvement_trend = self._calculate_trend(all_previous_results)
        converged = improvement_trend < 0.01

        # This logic fails without state persistence
        return {"converged": converged}

```

## State Persistence Debugging

### Check State Availability
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

class StateDebuggingNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Debug state persistence
        if self.logger:
            self.logger.debug(f"Iteration {iteration}: State available: {prev_state is not None}")
            if prev_state:
                self.logger.debug(f"State keys: {list(prev_state.keys())}")
            else:
                self.logger.debug("No previous state - using defaults")

        # Graceful handling regardless of state
        accumulated_count = prev_state.get("count", 0) if prev_state else 0

        return {
            "count": accumulated_count + 1,
            "state_available": prev_state is not None,
            "iteration": iteration
        }

```

### Workaround Patterns

#### Use Data Flow Instead of State
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Instead of relying on state, pass data through connections
class DataFlowNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        # Get accumulated data from input (passed via mapping)
        accumulated = kwargs.get("accumulated_data", [])
        new_item = kwargs.get("new_item", None)

        # Update accumulation
        if new_item:
            accumulated.append(new_item)

        # Return updated accumulation for next iteration
        return {
            "accumulated_data": accumulated,
            "converged": len(accumulated) >= 5
        }

# Use mapping to pass accumulated data between iterations
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

#### Iteration-Based Logic
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

class IterationBasedNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)

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

        return {
            "processing_intensity": processing_intensity,
            "converged": converged,
            "iteration": iteration + 1
        }

```

#### External State Storage
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

class ExternalStateNode(CycleAwareNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.external_state = {}  # Store state externally

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)
        run_id = context.get("run_id", "default")

        # Use external state storage
        state_key = f"{run_id}_{iteration}"

        if state_key in self.external_state:
            previous_data = self.external_state[state_key]
        else:
            previous_data = []

        # Process and store
        new_data = kwargs.get("data", [])
        combined_data = previous_data + new_data
        self.external_state[f"{run_id}_{iteration + 1}"] = combined_data

        return {
            "combined_data": combined_data,
            "converged": len(combined_data) >= 10
        }

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
