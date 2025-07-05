# Multi-Path Conditional Cycle Patterns

Complex workflows where SwitchNode routes to multiple processors, but only some paths form complete cycles.

## Common Multi-Path Patterns

### Pattern 1: Single Active Path with Fallback
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

# Only one condition creates a cycle, others terminate normally

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("data_source", DataSourceNode())
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("classifier", DataClassifierNode())
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("routing_switch", SwitchNode())
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("filter_processor", FilterProcessorNode())
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("archive_processor", ArchiveProcessorNode())

# Initial data flow
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Multiple exit paths from switch
workflow = Workflow("example", name="Example")
workflow.  # Method signature

workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Only the filter path cycles back
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Archive processor doesn't cycle - workflow ends there

```

### Pattern 2: Multiple Cycle Paths (Complex)
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

# Multiple conditions can trigger different cycle paths

workflow = Workflow("example", name="Example")
workflow.workflow.add_node("analyzer", DataAnalyzerNode())
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("quality_switch", SwitchNode())
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("improve_processor", QualityImproverNode())
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("validate_processor", ValidationProcessorNode())
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("complete_processor", CompletionProcessorNode())

# Main analysis flow
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Different quality levels trigger different processing
workflow = Workflow("example", name="Example")
workflow.  # Method signature

workflow = Workflow("example", name="Example")
workflow.  # Method signature

workflow = Workflow("example", name="Example")
workflow.  # Method signature  # This path doesn't cycle

# Different cycle paths
workflow = Workflow("example", name="Example")
workflow.  # Method signature

workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Complete processor terminates without cycling

```

## Configuration Patterns

### Multi-Case SwitchNode Setup
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

# Always ensure cycles have clear termination conditions
workflow = Workflow("example", name="Example")
workflow.workflow.connect("processor", "analyzer",
    cycle=True,
    max_iterations=10,  # Safety limit
    convergence_check="is_complete == True")  # Clear condition

```

### ✅ Asymmetric Flow Handling
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

# Wrong - missing cycle connection for one path
workflow = Workflow("example", name="Example")
workflow.workflow.connect("switch", "processor_a", condition="path_a")
workflow = Workflow("example", name="Example")
workflow.workflow.connect("switch", "processor_b", condition="path_b")

# Only processor_a cycles back - processor_b path incomplete
workflow = Workflow("example", name="Example")
workflow.workflow.connect("processor_a", "switch", cycle=True)
# Missing: workflow.connect("processor_b", ???)

```

### ❌ Conflicting Convergence Conditions
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

# Wrong - different cycle paths with conflicting convergence
workflow = Workflow("example", name="Example")
workflow.workflow.connect("processor_a", "analyzer",
    cycle=True, convergence_check="quality > 0.8")  # High threshold

workflow = Workflow("example", name="Example")
workflow.workflow.connect("processor_b", "analyzer",
    cycle=True, convergence_check="quality > 0.5")  # Low threshold
# These can interfere with each other

```

### ❌ Missing Default Cases
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

# Wrong - no handling for unmatched conditions
workflow = Workflow("example", name="Example")
workflow.workflow.connect("switch", "processor", condition="specific_case")
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
