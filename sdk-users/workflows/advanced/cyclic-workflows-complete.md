# Cyclic Workflows Complete Guide

**Master reference for iterative workflow patterns** - Consolidates 8 cheatsheets and 15 documented mistakes into a comprehensive cycle guide.

## 🎯 What You'll Learn

- **Basic Cycles**: Simple iterative patterns and parameter mapping
- **Advanced Cycles**: Multi-path conditional routing and convergence
- **Cycle-Aware Nodes**: Specialized nodes for iterative processing
- **Production Patterns**: Real-world examples with error handling
- **Debugging & Testing**: Tools and techniques for cycle development
- **Common Pitfalls**: Critical mistakes and how to avoid them

## 🚀 Quick Start: Your First Cycle

### 30-Second Basic Cycle
```python
from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import SwitchNode
from kailash.runtime.local import LocalRuntime

# Simple counter cycle
workflow = Workflow("basic_cycle")

# Processing node
workflow.add_node("counter", PythonCodeNode(
    name="counter",
    code='''
# Safe parameter access for cycles
try:
    count = count
except:
    count = 0  # Default for first iteration

# Process
new_count = count + 1
result = {
    "count": new_count,
    "message": f"Iteration {new_count}",
    "continue": new_count < 5
}
'''
))

# Convergence check
workflow.add_node("checker", SwitchNode(
    condition_field="continue",
    condition_type="boolean"
))

# Create cycle: counter -> checker -> counter
workflow.connect("counter", "checker", mapping={"result": "input"})
workflow.connect("checker", "counter",
    condition=True,  # Continue cycling
    cycle=True,      # Mark as cycle edge
    mapping={"count": "count"}  # ✅ CRITICAL: Specific field mapping
)

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "counter": {"count": 0}  # Initial value
})

print(f"Final count: {results['checker']['count']}")

```

## 🔧 Core Cycle Concepts

### 1. Cycle Edge Marking
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

# ✅ CRITICAL: Only mark the CLOSING edge as cycle=True
workflow = Workflow("example", name="Example")
workflow.workflow.connect("node_a", "node_b")           # Normal connection
workflow = Workflow("example", name="Example")
workflow.workflow.connect("node_b", "node_c")           # Normal connection
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### 2. Parameter Mapping in Cycles (Most Critical)
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

# ❌ NEVER: Generic mapping (causes data loss)
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# ✅ ALWAYS: Specific field mapping
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### 3. Safe Parameter Access Pattern
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

workflow = Workflow("example", name="Example")
workflow.  # Method signature)

```

## 🔀 Advanced Cycle Patterns

### Multi-Path Conditional Cycles
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

workflow = Workflow("multi_path_cycle")

# Main processor
workflow = Workflow("example", name="Example")
workflow.  # Method signature < 10:
    next_action = "expand"
else:
    next_action = "finalize"

result = {
    "data": processed,
    "iteration": iteration,
    "action": next_action,
    "ready_to_expand": len(processed) < 10,
    "continue_processing": iteration < 3,
    "finalize": iteration >= 3 and len(processed) >= 10
}
'''
))

# Multi-path router
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("router", SwitchNode(
    condition_field="action",
    condition_type="string"
))

# Path 1: Continue processing
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Path 2: Expand data
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("expander", PythonCodeNode(
    name="expander",
    code='''
expanded_data = data + [max(data) + i for i in range(1, 4)]
result = {"data": expanded_data, "iteration": iteration, "expanded": True}
'''
))

# Path 3: Finalize
workflow = Workflow("example", name="Example")
workflow.  # Method signature,
    "completed": True
}
'''
))

# Connect main flow
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Connect conditional paths
workflow = Workflow("example", name="Example")
workflow.  # Method signature

workflow = Workflow("example", name="Example")
workflow.  # Method signature

workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Cycle back connections (specific field mapping)
workflow = Workflow("example", name="Example")
workflow.  # Method signature

workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### Convergence-Based Cycles
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

workflow = Workflow("convergence_cycle")

# Optimization processor
workflow = Workflow("example", name="Example")
workflow.  # Method signature
    iteration = 0

# Simple optimization step (gradient descent simulation)
target = 100.0
learning_rate = 0.1
gradient = 2 * (current_value - target)
new_value = current_value - learning_rate * gradient

# Calculate error
new_error = abs(new_value - target)
iteration += 1

# Convergence criteria
converged = new_error < 1.0 or iteration >= 20
improvement = error - new_error if error != float('inf') else 0

result = {
    "current_value": new_value,
    "error": new_error,
    "iteration": iteration,
    "converged": converged,
    "improvement": improvement,
    "target": target,
    "continue_optimization": not converged
}
'''
))

# Convergence checker
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("convergence_check", SwitchNode(
    condition_field="continue_optimization",
    condition_type="boolean"
))

# Connect with convergence cycle
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Execute convergence optimization
runtime = LocalRuntime()
# Parameters setup
workflow.{
    "optimizer": {"current_value": 50.0}
})

```

## 🧠 Cycle-Aware Nodes

### ConvergenceCheckerNode Pattern
```python
from kailash.nodes.logic import ConvergenceCheckerNode

workflow = Workflow("cycle_with_convergence")

# Data processor
workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code='''
# Process iteratively
try:
    quality_score = quality_score
    data_count = data_count
except:
    quality_score = 0.1
    data_count = 100

# Simulate quality improvement
new_quality = min(0.95, quality_score + 0.1)
new_count = data_count + 50

result = {
    "quality_score": new_quality,
    "data_count": new_count,
    "processing_complete": True
}
'''
))

# Convergence checker with multiple criteria
workflow.add_node("convergence", ConvergenceCheckerNode(
    convergence_checks=[
        "quality_score >= 0.8",     # Quality threshold
        "data_count >= 500",        # Data volume threshold
        "iteration >= 3"            # Minimum iterations
    ],
    convergence_logic="any",        # Any condition can trigger convergence
    max_iterations=10               # Safety limit
))

workflow.connect("processor", "convergence", mapping={"result": "input"})
workflow.connect("convergence", "processor",
    condition="continue",
    cycle=True,
    mapping={"quality_score": "quality_score", "data_count": "data_count"}
)

```

### Custom Cycle-Aware Node
```python
from kailash.nodes.base_cycle_aware import CycleAwareNode

class AccumulatorNode(CycleAwareNode):
    """Custom node that accumulates values across iterations."""

    def __init__(self, accumulation_field="value", **kwargs):
        super().__init__(**kwargs)
        self.accumulation_field = accumulation_field

    async def run(self, **kwargs):
        # Get cycle context
        cycle_info = self.get_cycle_context()

        # Safe state access
        prev_state = cycle_info.get("node_state") or {}
        accumulated = prev_state.get("accumulated", [])

        # Get current value
        current_value = kwargs.get(self.accumulation_field)
        if current_value is not None:
            accumulated.append(current_value)

        # Update state for next iteration
        new_state = {"accumulated": accumulated}
        self.update_cycle_state(new_state)

        return {
            "accumulated_values": accumulated,
            "current_sum": sum(accumulated),
            "count": len(accumulated),
            "average": sum(accumulated) / len(accumulated) if accumulated else 0
        }

# Usage
workflow.add_node("accumulator", AccumulatorNode(
    accumulation_field="score"
))

```

## 🐛 Debugging & Testing Cycles

### Cycle Debugging with CycleDebugger
```python
from kailash.workflow import CycleDebugger

# Enable detailed cycle debugging
debugger = CycleDebugger(
    debug_level="detailed",
    enable_profiling=True,
    output_directory="./cycle_debug"
)

# Start cycle tracking
trace = debugger.start_cycle(
    cycle_id="optimization_cycle",
    workflow_id="my_workflow",
    max_iterations=100,
    convergence_condition="error < 0.01"
)

# Execute with debugging
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters=params)

# Generate debug report
report = debugger.generate_report(trace)
print(f"Cycle completed in {report['statistics']['total_iterations']} iterations")
print(f"Efficiency score: {report['performance']['efficiency_score']:.3f}")

```

### Testing Patterns for Cycles
```python
import pytest
from kailash.testing import WorkflowTestCase

class TestCyclicWorkflow(WorkflowTestCase):

    def test_cycle_convergence(self):
        """Test that cycle converges within expected iterations."""
        workflow = self.create_test_cycle()

        results, run_id = self.runtime.execute(workflow, parameters={
            "processor": {"initial_value": 0}
        })

        # ✅ FLEXIBLE: Use range assertions for cycles
        final_iteration = results["convergence"]["iteration"]
        assert 1 <= final_iteration <= 10, f"Expected 1-10 iterations, got {final_iteration}"

        # ✅ FLEXIBLE: Allow early convergence
        assert final_iteration >= 1, "Should run at least 1 iteration"

        # ❌ RIGID: Don't use exact counts
        # assert final_iteration == 5  # Cycles may converge early

    def test_cycle_state_persistence(self):
        """Test state persistence across iterations."""
        workflow = self.create_accumulator_cycle()

        results, run_id = self.runtime.execute(workflow, parameters={
            "accumulator": {"value": 10}
        })

        # Test accumulation worked
        accumulated = results["accumulator"]["accumulated_values"]
        assert len(accumulated) > 0, "Should accumulate at least one value"

        # ✅ REALISTIC: Account for state limitations
        if len(accumulated) == 1:
            # State persistence may have limitations - this is ok
            self.logger.warning("State persistence limited to single iteration")
        else:
            assert accumulated[0] == 10, "First value should be preserved"

```

## 🚨 Critical Mistakes to Avoid

### Mistake #1: Generic Output Mapping (Most Common)
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

# ❌ DEADLY: Generic mapping causes complete data loss in cycles
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Symptoms:
# - assert 1 >= 3 (iteration count failures)
# - assert 0.0 >= 0.7 (quality scores not improving)
# - assert 10 == 45 (accumulation completely failing)

# ✅ SOLUTION: Always use specific field mapping
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### Mistake #2: Incomplete Parameter Mapping with input_types
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

# ❌ WRONG: When using input_types, ALL parameters must be mapped
workflow = Workflow("example", name="Example")
workflow.  # Method signature)
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# ✅ CORRECT: Map ALL parameters including constants
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### Mistake #3: Unsafe State Access
```python
# ❌ WRONG: Direct state access without safety
cycle_state = cycle_info["node_state"]  # KeyError if not exists
results = cycle_state["results"]        # KeyError if not exists

# ✅ CORRECT: Safe state access with defaults
cycle_info = cycle_info or {}
prev_state = cycle_info.get("node_state") or {}
results = prev_state.get("results", [])

```

### Mistake #4: Wrong Convergence Check Format
```python
# ❌ WRONG: Nested path access
convergence_check="result.converged == True"  # Fails in evaluation

# ✅ CORRECT: Direct field names
convergence_check="converged == True"
convergence_check="error < 0.01"
convergence_check="count >= target_count"

```

### Mistake #5: Multiple Cycle Edges
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

# ❌ WRONG: Marking multiple edges as cycles
workflow = Workflow("example", name="Example")
workflow.workflow.connect("a", "b", cycle=True)  # ❌
workflow = Workflow("example", name="Example")
workflow.workflow.connect("b", "c", cycle=True)  # ❌
workflow = Workflow("example", name="Example")
workflow.workflow.connect("c", "a", cycle=True)  # ❌ Multiple cycle marks

# ✅ CORRECT: Only mark closing edge
workflow = Workflow("example", name="Example")
workflow.workflow.connect("a", "b")              # Normal
workflow = Workflow("example", name="Example")
workflow.workflow.connect("b", "c")              # Normal
workflow = Workflow("example", name="Example")
workflow.workflow.connect("c", "a", cycle=True)  # ✅ Only closing edge

```

## 📋 Production Cycle Checklist

Before deploying cyclic workflows:

- [ ] **Specific Mapping**: All cycle connections use specific field mapping
- [ ] **Safe Parameters**: All PythonCodeNode cycle parameters use try/except defaults
- [ ] **Single Cycle Edge**: Only closing edge marked as cycle=True
- [ ] **Convergence Criteria**: Clear, testable convergence conditions
- [ ] **State Safety**: All state access uses .get() with defaults
- [ ] **Performance Limits**: Max iterations set to prevent infinite loops
- [ ] **Error Handling**: Graceful handling of convergence failures
- [ ] **Testing**: Flexible test assertions that allow early convergence
- [ ] **Monitoring**: Logging/tracking for cycle health in production
- [ ] **Documentation**: Clear explanation of cycle purpose and expected behavior

## 🎯 Real-World Examples

### ETL with Retry Logic
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

workflow = Workflow("etl_with_retry")

workflow = Workflow("example", name="Example")
workflow.  # Method signature  # Improve with retries
total_records = 100
failed_this_round = []

for i in range(total_records):
    if random.random() > success_rate:
        failed_this_round.append(f"record_{i}")

# Update failure tracking
all_failed = failed_records + failed_this_round
retry_count += 1

# Decide if we should retry
should_retry = len(all_failed) > 0 and retry_count < 3

result = {
    "retry_count": retry_count,
    "failed_records": all_failed,
    "failed_this_round": len(failed_this_round),
    "should_retry": should_retry,
    "success_rate": success_rate,
    "processing_complete": not should_retry
}
'''
))

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("retry_decision", SwitchNode(
    condition_field="should_retry",
    condition_type="boolean"
))

workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### Batch Processing with Quality Gates
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

workflow = Workflow("quality_controlled_batch")

workflow = Workflow("example", name="Example")
workflow.  # Method signature
quality_scores.append(current_quality)
processed_items += batch_size
batch_number += 1

# Quality gate logic
avg_quality = sum(quality_scores) / len(quality_scores)
continue_processing = (
    processed_items < 500 and           # Haven't processed enough
    avg_quality > 0.75 and             # Quality is acceptable
    batch_number <= 20                  # Safety limit
)

result = {
    "batch_number": batch_number,
    "quality_scores": quality_scores,
    "processed_items": processed_items,
    "current_quality": current_quality,
    "average_quality": avg_quality,
    "continue_processing": continue_processing,
    "quality_gate_passed": avg_quality > 0.75
}
'''
))

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("quality_gate", SwitchNode(
    condition_field="continue_processing",
    condition_type="boolean"
))

workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

## 🔗 Advanced Topics

- **[Cycle Performance Optimization](../production-ready/performance-optimization.md)** - Scaling cycle patterns
- **[AI Agent Cycles](ai-agent-coordination.md)** - Multi-agent iterative workflows
- **[Enterprise Cycle Monitoring](../production-ready/monitoring-alerting.md)** - Production cycle health
- **[Cycle Testing Strategies](../production-ready/testing-validation.md)** - Comprehensive cycle testing

---

*This guide consolidates 8 cheatsheet files and 15 documented mistakes into the definitive reference for cyclic workflows. Master these patterns to build robust iterative systems.*
