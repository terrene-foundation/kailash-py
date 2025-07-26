# Multi-Path Conditional Cycle Patterns

Complex workflows where SwitchNode routes to multiple processors, but only some paths form complete cycles.

## Common Multi-Path Patterns

### Pattern 1: Single Active Path with Fallback
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

# Only one condition creates a cycle, others terminate normally

workflow = WorkflowBuilder()
workflow.add_node("DataSourceNode", "data_source", {}))
workflow = WorkflowBuilder()
workflow.add_node("DataClassifierNode", "classifier", {}))
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "routing_switch", {}))
workflow = WorkflowBuilder()
workflow.add_node("FilterProcessorNode", "filter_processor", {}))
workflow = WorkflowBuilder()
workflow.add_node("ArchiveProcessorNode", "archive_processor", {}))

# Initial data flow
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Multiple exit paths from switch
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Only the filter path cycles back
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Archive processor doesn't cycle - workflow ends there

```

### Pattern 2: Multiple Cycle Paths (Complex)
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

# Multiple conditions can trigger different cycle paths

workflow = WorkflowBuilder()
workflow.add_node("DataAnalyzerNode", "analyzer", {}))
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "quality_switch", {}))
workflow = WorkflowBuilder()
workflow.add_node("QualityImproverNode", "improve_processor", {}))
workflow = WorkflowBuilder()
workflow.add_node("ValidationProcessorNode", "validate_processor", {}))
workflow = WorkflowBuilder()
workflow.add_node("CompletionProcessorNode", "complete_processor", {}))

# Main analysis flow
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Different quality levels trigger different processing
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature  # This path doesn't cycle

# Different cycle paths
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Complete processor terminates without cycling

```

## Configuration Patterns

### Multi-Case SwitchNode Setup
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

# Use cases parameter for multiple routing options
runtime = LocalRuntime()
# Parameters setup
workflow.{
    "quality_switch": {
        "condition_field": "quality_level",
        "cases": ["low", "medium", "high"],  # Multiple cases
        "case_prefix": "case_",
        "pass_condition_result": True
    }
})

# Results in outputs: case_low, case_medium, case_high, default

```

### Conditional Field Evaluation
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

# More complex condition evaluation
runtime = LocalRuntime()
# Parameters setup
workflow.{
    "routing_switch": {
        "condition_field": "status",
        "operator": "in",
        "value": ["needs_processing", "needs_validation"],  # Multiple trigger values
        "pass_condition_result": True
    }
})

```

## Best Practices

### ✅ Clear Cycle Termination
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

# Always ensure cycles have clear termination conditions
workflow = WorkflowBuilder()
# Workflow setup goes here  # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()  # Clear condition

```

### ✅ Asymmetric Flow Handling
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

# Document which paths cycle and which terminate
class DataClassifierNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        data = kwargs.get("data", [])
        quality = self.calculate_quality(data)

        return {
            "processed_data": data,
            "quality_level": quality,
            "needs_processing": quality < 0.8,      # Will cycle back
            "is_complete": quality >= 0.8,          # Will terminate
            "processing_complete": quality >= 0.95  # Final convergence
        }

```

### ✅ Entry Point Documentation
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

# Always use source nodes for complex multi-path cycles
class DataSourceNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "initial_data": NodeParameter(name="initial_data", type=list, required=False, default=[])
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {"data": kwargs.get("initial_data", [])}

# Execute with node-specific parameters
runtime = LocalRuntime()
# Parameters setup
workflow.{
    "data_source": {"initial_data": [1, 2, 3, 4, 5]}
})

```

## Common Mistakes

### ❌ Incomplete Cycle Paths
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

# Wrong - missing cycle connection for one path
workflow = WorkflowBuilder()
workflow.add_connection("switch", "result", "processor_a", "input")
workflow = WorkflowBuilder()
workflow.add_connection("switch", "result", "processor_b", "input")

# Only processor_a cycles back - processor_b path incomplete
workflow = WorkflowBuilder()
# Workflow setup goes here  # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()
# Missing: workflow.add_connection("source", "result", "target", "input")

```

### ❌ Conflicting Convergence Conditions
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

# Wrong - different cycle paths with conflicting convergence
workflow = WorkflowBuilder()
# Workflow setup goes here  # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()  # High threshold

workflow = WorkflowBuilder()
# Workflow setup goes here  # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()  # Low threshold
# These can interfere with each other

```

### ❌ Missing Default Cases
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

# Wrong - no handling for unmatched conditions
workflow = WorkflowBuilder()
workflow.add_connection("switch", "result", "processor", "input")
# What happens if condition doesn't match?
# Add default handling or ensure all cases are covered

```

## Testing Patterns

### Test Asymmetric Flows
```python
def test_multi_path_cycle():
    """Test multi-path routing with cycles."""

    # Test cycling path
    results_cycle = runtime.execute(workflow, parameters={
        "data_source": {"data": low_quality_data}  # Should cycle
    })

    # Verify cycling occurred
    assert results_cycle["processor"]["iteration"] > 1

    # Test terminating path
    results_terminate = runtime.execute(workflow, parameters={
        "data_source": {"data": high_quality_data}  # Should terminate
    })

    # Verify immediate termination
    assert results_terminate["complete_processor"]["processed"] is True

```

### Test All Switch Conditions
```python
def test_all_switch_paths():
    """Ensure all switch conditions are tested."""

    test_cases = [
        {"condition": "low", "expected_processor": "improve_processor"},
        {"condition": "medium", "expected_processor": "validate_processor"},
        {"condition": "high", "expected_processor": "complete_processor"}
    ]

    for case in test_cases:
        results = runtime.execute(workflow, parameters={
            "analyzer": {"quality_level": case["condition"]}
        })

        # Verify correct processor was triggered
        assert case["expected_processor"] in results

```

## Related Patterns
- [020-switchnode-conditional-routing.md](020-switchnode-conditional-routing.md) - Basic SwitchNode patterns
- [019-cyclic-workflows-basics.md](019-cyclic-workflows-basics.md) - Fundamental cycle setup
- [030-cycle-state-persistence-patterns.md](030-cycle-state-persistence-patterns.md) - State management

## Common Mistakes
- [072](../../mistakes/072-switchnode-mapping-specificity.md) - SwitchNode mapping issues
- [071](../../mistakes/071-cyclic-workflow-parameter-passing-patterns.md) - Parameter passing problems
